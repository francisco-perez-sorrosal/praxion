"""Behavioral tests for the paid orchestration path of the live scenario runner.

``praxion_evals.live.cli``'s ``main``/``_run``/``_run_variant``/``_run_tasks``/
``_isolation_proof`` and ``praxion_evals.live.report``'s ``build_output`` drive
real, API-metered ``claude -p``
sessions and had no test at all before this file. Every test here either
drives that orchestration end-to-end against the ``fake_claude`` stand-in
(never a real session — see ``conftest.py``), or exercises one of its pure
aggregation/isolation helpers directly with hand-built inputs. No test in
this file spends API money or reaches the network.

These tests encode the behavior a rework of the orchestration path must
produce; several currently fail against unfixed production code — read each
test's docstring for the specific gap it reproduces.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "live_scenarios"


def _fixture_text(name: str) -> str:
    return (FIXTURES_DIR / f"{name}.stream.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Hand-built variant records — the shape `report.variant_record` produces,
# used to drive the pure aggregation path (`build_output`) without a live run.
# ---------------------------------------------------------------------------


def _spawn_selection_block(case_outcome_counts: list[tuple[int, int, int]]) -> dict[str, object]:
    """One `spawn-selection` scenario block; ``case_outcome_counts`` is
    ``(pass, fail, error)`` per case, five entries."""
    from praxion_evals.live.results import compute_pass_rate

    cases = []
    totals = {"pass": 0, "fail": 0, "error": 0}
    for index, (passed, failed, errored) in enumerate(case_outcome_counts, start=1):
        counts = {"pass": passed, "fail": failed, "error": errored}
        for key, value in counts.items():
            totals[key] += value
        cases.append(
            {
                "case_id": f"spawn-selection#{index}",
                "counts": counts,
                "pass_rate": compute_pass_rate(passed=passed, failed=failed),
                "sessions": [],
            }
        )
    return {
        "scenario_id": "spawn-selection",
        "counts": totals,
        "pass_rate": compute_pass_rate(passed=totals["pass"], failed=totals["fail"]),
        "cases": cases,
    }


def _variant_stub(variant: str, spawn_selection_block: dict[str, object]) -> dict[str, object]:
    return {
        "variant": variant,
        "target": {"kind": "ref", "ref": "HEAD", "sha": "deadbeef"},
        "degradation": None,
        "isolation_proof": {"status": "proven"},
        "scenarios": [spawn_selection_block],
        "totals": {"scenario_sessions": 5, "errors": 0},
    }


_STUB_ARGS = argparse.Namespace(canary=True, model="opus", effort="medium", k=1, judge=False)


# ---------------------------------------------------------------------------
# `lowered` must reflect a per-case guard, not pooled scenario rates
# ---------------------------------------------------------------------------


def test_lowered_is_null_when_pooled_rates_move_but_three_cases_never_graded_in_canary():
    """Reproduces the verifier's exact scenario: HEAD passes all five cases;
    in the canary, three cases error out (never graded) and two fail. The
    pooled canary rate (0/2) reads as a large drop from HEAD's pooled rate
    (5/5), but no single case has a measurement in both variants for three
    of the five cases — `lowered` must be `None`, not `True`."""
    from praxion_evals.live import report

    head = _variant_stub("head", _spawn_selection_block([(1, 0, 0)] * 5))
    canary = _variant_stub(
        "canary", _spawn_selection_block([(0, 0, 1), (0, 0, 1), (0, 0, 1), (0, 1, 0), (0, 1, 0)])
    )

    output = report.build_output(_STUB_ARGS, "2026-01-01T00:00:00Z", [head, canary])

    assert output["canary"]["lowered"] is None


def test_lowered_is_true_when_every_case_is_graded_in_both_variants_and_all_moved():
    """The positive case the guard must not over-suppress: every case has a
    graded session in both variants, and every one moved from pass to fail."""
    from praxion_evals.live import report

    head = _variant_stub("head", _spawn_selection_block([(1, 0, 0)] * 5))
    canary = _variant_stub("canary", _spawn_selection_block([(0, 1, 0)] * 5))

    output = report.build_output(_STUB_ARGS, "2026-01-01T00:00:00Z", [head, canary])

    assert output["canary"]["lowered"] is True


# ---------------------------------------------------------------------------
# EVAL_LOG row draft: 9 columns, per-scenario pass rates and the canary
# verdict carried in the notes cell
# ---------------------------------------------------------------------------


def test_eval_log_row_keeps_nine_columns_and_carries_pass_rates_and_verdict_in_notes(capsys):
    from praxion_evals.live import report

    head = _variant_stub("head", _spawn_selection_block([(1, 0, 0)] * 5))
    canary = _variant_stub("canary", _spawn_selection_block([(0, 1, 0)] * 5))
    output = report.build_output(_STUB_ARGS, "2026-01-01T00:00:00Z", [head, canary])

    report.print_eval_log_row(output, "494dccaa")

    printed = capsys.readouterr().out
    row = next(line for line in printed.splitlines() if line.startswith("| "))
    cells = [c.strip() for c in row.strip("|").split("|")]

    assert len(cells) == 9
    assert "spawn-selection" in cells[-1]  # per-scenario pass rate named in notes
    assert "lowered=True" in cells[-1]  # the canary verdict, not swallowed


# ---------------------------------------------------------------------------
# The materialized copy is read-only, and a digest mismatch after a variant
# turns that variant's sessions into an isolation breach
# ---------------------------------------------------------------------------


def test_materialized_copy_rejects_a_write_after_build(tmp_path, repo_root):
    """A session's `--add-dir` grant lets it edit files under the plugin
    copy; nothing should stop that write from reaching the shared copy
    every other session of the variant subsequently loads unless the copy
    itself is read-only on disk."""
    from praxion_evals.live.materialize import materialize_head

    materialization = materialize_head(repo_root, tmp_path / "copy")

    with pytest.raises((PermissionError, OSError)):
        (materialization.root / "README.md").write_text("mutated\n", encoding="utf-8")


def test_digest_mismatch_after_a_variant_marks_every_session_isolation_breach(
    tmp_path, fake_claude, repo_root
):
    """A session mutates the shared copy (bypassing the read-only guard, the
    way a bug or a permissive tool grant could); the variant's post-run
    digest recheck must catch it and mark every session of that variant as
    an isolation breach rather than recording a silently-corrupted result."""
    from praxion_evals.live import cli
    from praxion_evals.live.materialize import materialize_head
    from praxion_evals.live.spend import SpendLedger

    fake_claude.configure(mutate_copy_relpath="README.md")
    fixtures_by_id = cli._load_fixtures_by_id()
    copy = materialize_head(repo_root, tmp_path / "copy")
    tasks = [
        cli.SessionTask("lightweight-fix", 1, 1, repeat, fixtures_by_id["lightweight-fix"])
        for repeat in (1, 2)
    ]
    args = argparse.Namespace(model="opus", effort="medium", judge=False)
    ledger = SpendLedger(cap_usd=50.0)

    records, _ = cli._run_tasks(tasks, copy, tmp_path / "run", args, fixtures_by_id, ledger)

    assert len(records) == 2
    for _, record in records:
        assert record["outcome"] == "error"
        assert record["error_kind"] == "isolation_breach"


# ---------------------------------------------------------------------------
# commit-staging: `git add .` stages the trap file and must not read as PASS
# ---------------------------------------------------------------------------


def test_commit_staging_bare_git_add_dot_is_not_captured_as_a_legitimate_staging_command():
    """`git add .` cannot discriminate which files it swept in — including
    an untracked trap file the seeded scenario never asked for. It must not
    be treated as evidence of correct, deliberate staging."""
    from praxion_evals.live.results import NotElicited
    from praxion_evals.live.scenarios import capture_commit_staging
    from praxion_evals.live.session import SessionEnvelope, ToolUse

    envelope = SessionEnvelope(
        init=None,
        tool_uses=(
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "git add . && git commit -m 'Fix typo'"},
                parent_tool_use_id=None,
            ),
        ),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )

    capture = capture_commit_staging(envelope, None, {})

    assert isinstance(capture, NotElicited)


# ---------------------------------------------------------------------------
# Default `--output` and default target
# ---------------------------------------------------------------------------


def test_default_output_resolves_under_the_repo_root_not_the_cwd(repo_root):
    """Every documented invocation starts with `cd eval`; the default output
    must resolve against the repo root, not whatever the cwd happens to be —
    otherwise a run from `eval/` silently writes into `eval/.ai-state/…`
    instead of the tracked `.ai-state/eval_ledger/` at the repo root. An
    explicit `--output` is honored as given, relative to the cwd, exactly
    like every other CLI path argument."""
    from praxion_evals.live import cli

    default_args = cli._parse_args([])
    explicit_args = cli._parse_args(["--output", "explicit.json"])

    assert cli._resolve_output(default_args.output, repo_root) == repo_root / cli.DEFAULT_OUTPUT
    assert cli._resolve_output(explicit_args.output, repo_root) == Path("explicit.json")


def test_default_target_resolves_to_head_not_main(monkeypatch, capsys, repo_root, fake_claude):
    """The CLI's own help text and dry-run label say "HEAD", but an unset
    target must actually resolve the checkout's current HEAD commit — not
    the `main` branch, which can be behind (as it is in this worktree)."""
    from praxion_evals.live import cli

    monkeypatch.chdir(repo_root / "eval")

    exit_code = cli.main(["--dry-run"])
    printed = capsys.readouterr().out

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()
    main_sha = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert exit_code == 0
    assert head_sha in printed
    if head_sha != main_sha:
        assert main_sha not in printed


# ---------------------------------------------------------------------------
# Preflight isolation and the rule nonce's file
# ---------------------------------------------------------------------------


def test_preflight_isolation_breach_fails_the_proof_even_with_every_nonce_echoed():
    """A preflight that echoes all four nonces but whose own `init` reports
    a foreign plugin must not be trusted — the isolation proof is telemetry-
    first, not "the model said the right words"."""
    from praxion_evals.live import cli
    from praxion_evals.live.materialize import NoncePlant
    from praxion_evals.live.session import InitInfo, ResultInfo, SessionEnvelope, SessionRun

    plant = NoncePlant(
        global_claude_md="11111111",
        coordination_rule="22222222",
        plugin_agent="33333333",
        hook_delivered_rule="44444444",
    )
    copy_root = Path("/tmp/preflight-copy")
    envelope = SessionEnvelope(
        init=InitInfo(
            model="claude-sonnet-5",
            plugins=(
                {"name": "praxion", "source": "praxion@inline", "path": str(copy_root)},
                {"name": "rogue", "source": "rogue@marketplace", "path": "/somewhere/else"},
            ),
            mcp_servers=(),
            api_key_source="ANTHROPIC_API_KEY",
            claude_code_version="test",
            cwd=str(copy_root / "fixture"),
        ),
        tool_uses=(),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=ResultInfo(
            result_text="\n".join(plant.markers().values()),
            structured_output=None,
            is_error=False,
            subtype="success",
            total_cost_usd=0.1,
            session_id="s",
        ),
        result_count=1,
        unparseable=False,
    )
    run = SessionRun(stdout="", stderr="", exit_code=0)

    proof = cli._isolation_proof({"run": run, "envelope": envelope}, plant, copy_root=copy_root)

    assert proof["status"] == "failed"


def test_head_preflight_nonce_lands_in_the_coordination_protocol_rule():
    """REQ-level intent and the JSON key `coordination_rule` both name the
    coordination-protocol rule; the HEAD preflight must plant its nonce
    there — the same file the canary degrades — not in an unrelated rule."""
    import inspect

    from praxion_evals.live import cli

    source = inspect.getsource(cli._run_variant)

    assert "plant_nonces(preflight_copy.root, CANARY_FILE)" in source


# ---------------------------------------------------------------------------
# A tool_use naming a path under the operator's real home is an isolation
# breach; spawn-selection gets no Bash tools at all
# ---------------------------------------------------------------------------


def _isolated_envelope(copy_root: Path, tool_uses: tuple) -> object:
    from praxion_evals.live.session import InitInfo, SessionEnvelope

    return SessionEnvelope(
        init=InitInfo(
            model="m",
            plugins=({"name": "praxion", "source": "praxion@inline", "path": str(copy_root)},),
            mcp_servers=(),
            api_key_source="k",
            claude_code_version="v",
            cwd="/tmp/run/head-spawn-selection-1-0/fixture",
        ),
        tool_uses=tool_uses,
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )


def test_tool_use_naming_a_path_under_the_real_home_is_an_isolation_breach():
    """A glob allowlist (`cat *`, `tail *`) cannot distinguish stdin from
    `~/.ssh/…`; any tool_use input naming a path under the operator's real
    home is telemetry proof of a breach, detected regardless of which
    command carried it — `real_home` is passed in, never read from the
    environment by the check itself."""
    from praxion_evals.live.session import ToolUse, isolation_breach

    copy_root = Path("/tmp/run/head-copy")
    real_home = Path("/Users/real-operator")
    envelope = _isolated_envelope(
        copy_root,
        (
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "cat /Users/real-operator/.claude/CLAUDE.md"},
                parent_tool_use_id=None,
            ),
        ),
    )

    breach = isolation_breach(envelope, copy_root, real_home=real_home)

    assert breach is not None


def test_tool_use_naming_ssh_keys_under_the_real_home_is_an_isolation_breach():
    from praxion_evals.live.session import ToolUse, isolation_breach

    copy_root = Path("/tmp/run/head-copy")
    real_home = Path("/Users/real-operator")
    envelope = _isolated_envelope(
        copy_root,
        (
            ToolUse(
                id="t1",
                name="Read",
                input={"file_path": "/Users/real-operator/.ssh/id_ed25519"},
                parent_tool_use_id=None,
            ),
        ),
    )

    breach = isolation_breach(envelope, copy_root, real_home=real_home)

    assert breach is not None


def test_dev_null_urls_and_the_sessions_own_fixture_are_not_isolation_breaches():
    """Ordinary, genuinely isolated tool calls must not trip the check:
    `/dev/null`, a URL that merely looks like a path, and the session's own
    fixture/copy paths are all legitimate."""
    from praxion_evals.live.session import ToolUse, isolation_breach

    copy_root = Path("/tmp/run/head-copy")
    real_home = Path("/Users/real-operator")
    envelope = _isolated_envelope(
        copy_root,
        (
            ToolUse(
                id="t1",
                name="Bash",
                input={"command": "pytest -q 2>&1 | tail -3 > /dev/null"},
                parent_tool_use_id=None,
            ),
            ToolUse(
                id="t2",
                name="Write",
                input={
                    "file_path": "/tmp/run/head-spawn-selection-1-0/fixture/a.txt",
                    "content": "see https://example.com/a for details, and <ul></ul>",
                },
                parent_tool_use_id=None,
            ),
        ),
    )

    breach = isolation_breach(envelope, copy_root, real_home=real_home)

    assert breach is None


def test_real_envelope_fixtures_pass_clean_against_their_own_recorded_roots():
    """The oracle: every committed verbatim envelope that reached `init` is a
    genuinely isolated session and must never trip the real-home check
    against the operator's actual home — this is the regression #refail-1
    reproduced from real recordings, not synthetic ones."""
    from praxion_evals.live.session import isolation_breach, parse_stream

    fixture_names = [
        "isolated_marker_preflight_sonnet",
        "spawn_selection_standard_opus",
        "subagent_implementer_background_sonnet",
        "ui_step_conformance",
        "adr_authoring",
        "commit_staging",
        "lightweight_fix",
    ]
    real_home = Path("/Users/operator")  # the README's substituted operator identity
    for name in fixture_names:
        envelope = parse_stream(_fixture_text(name))
        assert envelope.init is not None, name
        copy_root = Path(
            next(p["path"] for p in envelope.init.plugins if p.get("path") not in (None, "builtin"))
        )

        breach = isolation_breach(envelope, copy_root, real_home=real_home)

        assert breach is None, (name, breach)


def test_spawn_selection_session_grants_no_bash_tools_at_all():
    """A glob allowlist cannot tell `tail` on stdin from `tail ~/.ssh/…` — so
    spawn-selection, which needs no tool at all to answer its declaration-
    only prompt, gets none, rather than the "harmless" utility set that can
    read any file the operator can read."""
    from praxion_evals.live import scenarios

    assert scenarios.SCENARIOS["spawn-selection"].allowed_tools == ()


# ---------------------------------------------------------------------------
# End-to-end: the paid orchestration loop, against the fake `claude` only
# ---------------------------------------------------------------------------


def test_canary_run_completes_with_both_variants_recorded(tmp_path, fake_claude):
    """The session-root collision (`spawn-selection#1-1-0` colliding across
    variants) crashes every `--canary` run before any output is written.
    A namespaced session root per variant lets the run actually finish."""
    from praxion_evals.live import cli

    output = tmp_path / "baseline.json"

    exit_code = cli.main(["--k", "1", "--canary", "--output", str(output)])

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    variants = {v["variant"]: v for v in data["variants"]}
    assert set(variants) == {"head", "canary"}
    assert variants["head"]["totals"]["scenario_sessions"] == 9
    assert variants["canary"]["totals"]["scenario_sessions"] == 5


def test_baseline_json_records_per_session_metrics_and_the_resolved_model(tmp_path, fake_claude):
    """Cost, tokens, turns and permission denials are parsed from every
    envelope and then discarded — the baseline JSON must actually carry
    them, and `run.model.resolved` must reflect what sessions reported."""
    from praxion_evals.live import cli

    output = tmp_path / "baseline.json"

    cli.main(["--k", "1", "--output", str(output)])

    data = json.loads(output.read_text(encoding="utf-8"))
    head = next(v for v in data["variants"] if v["variant"] == "head")
    session = head["scenarios"][0]["cases"][0]["sessions"][0]

    assert session.get("cost_usd") == pytest.approx(0.25)
    assert session.get("model_resolved") == "claude-opus-5-5"
    assert session.get("num_turns") == 2
    assert session.get("permission_denials") == 0
    assert session.get("usage") == {
        "input": 10,
        "output": 20,
        "cache_creation": 0,
        "cache_read": 0,
    }
    assert data["run"]["model"]["resolved"] == ["claude-opus-5-5"]
    assert head["totals"].get("cost_usd") is not None
    # 9 head sessions x the fake's fixed usage.
    assert head["totals"].get("tokens") == {
        "input": 90,
        "output": 180,
        "cache_creation": 0,
        "cache_read": 0,
    }


def test_head_preflight_abort_skips_the_canary_variant_entirely(tmp_path, fake_claude):
    """A HEAD preflight that fails to prove isolation must stop the run
    there — spending on a canary variant whose own `lowered` verdict will
    read `null` anyway (per the per-case guard) is a pure waste."""
    from praxion_evals.live import cli

    fake_claude.configure(preflight_breach=True)
    output = tmp_path / "baseline.json"

    exit_code = cli.main(["--k", "1", "--canary", "--output", str(output)])

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data["variants"]) == 1
    assert data["variants"][0]["variant"] == "head"
    assert data["variants"][0]["isolation_proof"]["status"] == "failed"
    assert data["canary"] is None


def test_judge_exception_becomes_that_sessions_error_record_without_discarding_the_run(
    tmp_path, fake_claude, monkeypatch
):
    """A raised judge error currently propagates out of `main()` uncaught,
    discarding every already-paid-for result. It must instead become that
    one session's error record, and the run must still write its (partial)
    output, flagged incomplete."""
    import praxion_evals.harness.judge_client as judge_client_module
    from praxion_evals.harness.schemas import JudgeVerdict
    from praxion_evals.live import cli

    class FlakyJudge:
        calls = 0

        def judge(self, rubric, artifact, schema):
            FlakyJudge.calls += 1
            if FlakyJudge.calls >= 2:
                raise RuntimeError("simulated 529 overloaded from the judge API")
            return JudgeVerdict(verdict="PASS", findings=("ok",), score=90, raw={})

    monkeypatch.setattr(judge_client_module, "select_judge_client", lambda: FlakyJudge())
    output = tmp_path / "baseline.json"

    exit_code = cli.main(["--k", "1", "--judge", "--output", str(output)])

    assert exit_code == 0
    assert output.exists(), "output must be written even when a session errors mid-run"
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["run"].get("complete") is False
    outcomes = {
        session["outcome"]
        for variant in data["variants"]
        for scenario in variant["scenarios"]
        for case in scenario["cases"]
        for session in case["sessions"]
    }
    assert "error" in outcomes


def test_run_leaves_the_invoking_repo_and_a_real_home_stand_in_untouched(
    tmp_path, fake_claude, monkeypatch, repo_root
):
    """No pre-mortem guard test exists for this: a run must never write
    outside its own sandbox root and the declared output file — not into
    the invoking repo, and not into whatever `$HOME` happens to be set to
    outside the per-session sandbox override."""
    from praxion_evals.live import cli

    real_home_stand_in = tmp_path / "real-home"
    (real_home_stand_in / ".claude").mkdir(parents=True)
    marker = real_home_stand_in / ".claude" / "untouched.txt"
    marker.write_text("before\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(real_home_stand_in))

    status_before = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    output = tmp_path / "baseline.json"
    exit_code = cli.main(["--k", "1", "--output", str(output)])

    status_after = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert exit_code == 0
    assert status_before == status_after
    assert marker.read_text(encoding="utf-8") == "before\n"
    assert sorted(p.name for p in (real_home_stand_in / ".claude").iterdir()) == ["untouched.txt"]
