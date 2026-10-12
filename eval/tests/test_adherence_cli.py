"""The adherence console entry: argument parsing, the dry run, the report option, and the paid loop.

The paid loop runs over a real copy of this repository with a scripted stand-in for the
one function that starts ``claude`` (``cli.run_session``); no process is ever started.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import cli, results, tasks
from praxion_evals.adherence.arms import NO_MARKER_REPLY, PROOF_LABEL
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.checks_common import C3, GoldenVerdicts
from praxion_evals.adherence.model import CheckErrored, Errored, Failed, Measured, Passed
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import JudgeVerdict
from praxion_evals.live.session import SessionRun, SessionSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "researcher"
SMALL_RUN = [
    "--required-pairs",
    "1",
    "--pair-slack",
    "0",
    "--no-judge",
    "--session-budget-usd",
    "1",
]
FULL_TOKENS, LEAN_TOKENS = 5000, 1000


# ---------------------------------------------------------------------------
# argv
# ---------------------------------------------------------------------------


def test_the_defaults_are_the_documented_ones() -> None:
    config = cli.parse_config(["--role", ROLE])

    assert (config.roles, config.arms) == ((ROLE,), ("full", "lean"))
    assert (config.seed, config.margin_pp, config.required_pairs) == (7, 10.0, 20)
    assert (config.pair_slack, config.confidence, config.judging) == (4, 0.95, True)
    assert (config.calibration, config.calibration_run, config.dry_run) == (False, None, False)


def test_roles_and_arms_are_deduplicated_and_arms_keep_the_launch_order() -> None:
    config = cli.parse_config(
        [
            "--role",
            "verifier",
            "--role",
            ROLE,
            "--role",
            "verifier",
            "--arm",
            "lean",
            "--arm",
            "full",
        ]
    )

    assert config.roles == ("verifier", ROLE)
    assert config.arms == ("full", "lean")


@pytest.mark.parametrize(("pairs", "slack"), [(20, 4), (50, 10), (3, 4)])
def test_the_default_slack_is_a_fifth_of_the_target_and_at_least_four(
    pairs: int, slack: int
) -> None:
    config = cli.parse_config(["--role", ROLE, "--required-pairs", str(pairs)])

    assert config.pair_slack == slack


def test_a_declared_slack_overrides_the_default() -> None:
    assert cli.parse_config(["--role", ROLE, "--pair-slack", "0"]).pair_slack == 0


def test_a_calibration_run_measures_the_full_arm_only() -> None:
    config = cli.parse_config(["--role", ROLE, "--calibration"])

    assert config.arms == ("full",)
    assert config.calibration


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--role", ROLE, "--margin-pp", "120"],
        ["--role", ROLE, "--confidence", "1.5"],
        ["--role", ROLE, "--max-total-usd", "0"],
        ["--role", ROLE, "--required-pairs", "0"],
        ["--role", ROLE, "--calibration", "--arm", "lean"],
        ["--role", ROLE, "--calibration", "--calibration-run", "earlier.json"],
        ["--role", ROLE, "--judge-golden", "--no-judge"],
        ["--role", "no-such-role"],
    ],
)
def test_a_usage_error_exits_with_two(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.parse_config(argv)

    assert raised.value.code == 2


def test_the_report_option_needs_no_role() -> None:
    config = cli.parse_config(["--report", "results.json"])

    assert config.report == Path("results.json")
    assert config.roles == ()


# ---------------------------------------------------------------------------
# The dry run and the start-of-run refusals launch nothing
# ---------------------------------------------------------------------------


@pytest.fixture
def no_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(spec: SessionSpec, env: object) -> SessionRun:
        raise AssertionError("a session was started")

    monkeypatch.setattr(cli, "run_session", refuse)


def _dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path, *options: str) -> list[dict]:
    argv = [str(REPO_ROOT), "--output", str(tmp_path / "out.json"), "--dry-run", *options]
    assert cli.main(argv) == 0
    assert not (tmp_path / "out.json").exists()
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_lists_every_task_of_every_named_arm(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE)

    assert sorted((line["task_id"], line["arm"]) for line in lines) == sorted(
        (task, arm) for task in tasks.task_ids(ROLE, cli.DEFAULT_SEED) for arm in ("full", "lean")
    )


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_of_a_calibration_lists_the_full_arm_only(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE, "--calibration")

    assert {line["arm"] for line in lines} == {"full"}


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_uses_the_declared_slack_for_the_task_count(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = _dry_run(capsys, tmp_path, "--role", ROLE, "--arm", "full", *SMALL_RUN)

    assert len(lines) == 1


@pytest.mark.usefixtures("no_launch")
def test_an_existing_output_is_refused_before_anything_else(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "out.json"
    output.write_text("earlier", encoding="utf-8")

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(output)])

    assert code == 2
    assert "--overwrite" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "earlier"


@pytest.mark.usefixtures("no_launch")
def test_a_role_with_no_task_kit_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli.main([str(REPO_ROOT), "--role", "sentinel", "--output", str(tmp_path / "o.json")])

    assert code == 2
    assert "sentinel" in capsys.readouterr().err


def test_a_paid_run_without_a_credential_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, no_launch: None, tmp_path: Path
) -> None:
    for key in cli.CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(tmp_path / "o.json")])

    assert code == 2
    assert not (tmp_path / "o.json").exists()


# ---------------------------------------------------------------------------
# The golden-case record
# ---------------------------------------------------------------------------


def test_the_golden_record_counts_the_cases_the_judge_got_wrong() -> None:
    right = GoldenVerdicts(bad=Failed("missed"), good=Passed())
    wrong = GoldenVerdicts(bad=Passed(), good=Passed())

    record = cli.golden_record({"C3": right, "C9": wrong})

    assert record["observed_error"] == 0.25
    assert record["cases"]["C3"]["separates"] is True
    assert record["cases"]["C9"]["bad"] == {"outcome": "passed"}


def test_an_errored_golden_case_is_recorded_but_neither_right_nor_wrong() -> None:
    errored = GoldenVerdicts(bad=CheckErrored("judge down"), good=Passed())

    assert cli.golden_record({"C3": errored})["observed_error"] == 0.0
    assert (
        cli.golden_record({"C3": GoldenVerdicts(CheckErrored("x"), CheckErrored("y"))})[
            "observed_error"
        ]
        is None
    )


class _ScriptedJudge(JudgeClient):
    """Fails the golden bad case and passes everything else, as a faithful judge would."""

    def judge(self, rubric: str, artifact: str, schema: dict) -> JudgeVerdict:  # type: ignore[type-arg]
        verdict = "FAIL" if artifact == C3.golden_bad_case else "PASS"  # type: ignore[union-attr]
        return JudgeVerdict(verdict=verdict, findings=(), score=0, raw={})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The paid loop, over a scripted `claude`
# ---------------------------------------------------------------------------


class Script:
    """Answers each launch like a session would, and records what was launched."""

    def __init__(
        self, *, cost: float | None = 0.01, fail_launch: Callable[[int], bool] | None = None
    ):
        self.cost = cost
        self.fail_launch = fail_launch or (lambda number: False)
        self.specs: list[SessionSpec] = []

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        self.specs.append(spec)
        if self.fail_launch(len(self.specs)):
            return SessionRun("", "scripted failure", 3)
        return SessionRun(self._stream(spec, env), "", 0)

    def _stream(self, spec: SessionSpec, env: dict[str, str]) -> str:
        role = re.search(r"praxion:([a-z-]+)", spec.prompt).group(1)  # type: ignore[union-attr]
        lean = "lean" in spec.plugin_dir.name
        answer = self._answer(spec, env, lean)
        tokens = LEAN_TOKENS if lean else FULL_TOKENS
        usage = {
            "input_tokens": 2,
            "cache_creation_input_tokens": tokens,
            "cache_read_input_tokens": 0,
        }
        plugin = {"name": "praxion", "source": "praxion@inline", "path": str(spec.plugin_dir)}
        result = {"type": "result", "subtype": "success", "is_error": False, "result": answer}
        if self.cost is not None:
            result["total_cost_usd"] = self.cost
        events = [
            {
                "type": "system",
                "subtype": "init",
                "plugins": [plugin],
                "mcp_servers": [],
                "cwd": str(spec.cwd),
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Agent",
                            "input": {"subagent_type": f"praxion:{role}", "prompt": "do it"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "parent_tool_use_id": "t1",
                "message": {"content": [{"type": "text", "text": answer}], "usage": usage},
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": answer}]
                },
            },
            result,
        ]
        return "\n".join(json.dumps(event) for event in events)

    @staticmethod
    def _answer(spec: SessionSpec, env: dict[str, str], lean: bool) -> str:
        if PROOF_LABEL not in spec.prompt:
            return "Findings are in the report.\n[COMPLETE]"
        if lean:
            return NO_MARKER_REPLY
        planted = (Path(env["CLAUDE_CONFIG_DIR"]) / "CLAUDE.md").read_text(encoding="utf-8")
        return re.findall(rf"{PROOF_LABEL}-[0-9a-f]+", planted)[-1]


@pytest.fixture
def paid(monkeypatch: pytest.MonkeyPatch) -> Callable[[Script], None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-credential")
    monkeypatch.setattr(cli, "query_claude_version", lambda: "9.9.9-test")

    def install(script: Script) -> None:
        monkeypatch.setattr(cli, "run_session", script)

    return install


def _run(tmp_path: Path, *options: str, name: str = "out.json") -> tuple[int, results.RunResults]:
    output = tmp_path / name
    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(output), *SMALL_RUN, *options])
    return code, results.load(output)


def _sessions(loaded: results.RunResults) -> list[tuple[str, str]]:
    return [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions]


def test_each_arm_is_proven_then_the_task_runs_in_both_arms_in_turn(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 0
    assert loaded.run.complete
    assert [("lean" in s.plugin_dir.name) for s in script.specs] == [False, True, False, True]
    assert _sessions(loaded) == [("full", "Measured"), ("lean", "Measured")]
    assert {arm: loaded.arms[ROLE][arm]["built"] for arm in ("full", "lean")} == {
        "full": True,
        "lean": True,
    }
    assert loaded.arms[ROLE]["lean"]["proof"]["cross_checked"] is True
    assert loaded.run.claude_code_version == "9.9.9-test"
    assert loaded.run.extra["retries"] == []


def test_a_transient_infrastructure_error_is_retried_once_and_the_retry_replaces_it(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 4)  # the lean task session
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 0
    assert _sessions(loaded) == [("full", "Measured"), ("lean", "Errored"), ("lean", "Measured")]
    assert loaded.run.extra["retries"] == [
        {
            "role": ROLE,
            "arm": "lean",
            "task_id": loaded.sessions[0].setup.task_id,
            "after": "exit_nonzero",
        }
    ]
    assert isinstance(results.pairs_of(loaded, ROLE)[0].lean, Measured)


def test_an_error_that_keeps_failing_is_retried_once_only_and_leaves_the_run_incomplete(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number >= 2)  # every launch after the proof
    paid(script)

    code, loaded = _run(tmp_path, "--arm", "lean")

    assert code == 1
    assert len(script.specs) == 3  # the proof, the lean session and its one retry
    assert _sessions(loaded) == [("lean", "Errored"), ("lean", "Errored")]
    assert not loaded.run.complete


def test_a_session_that_reports_no_cost_is_charged_its_budget_and_the_cap_refuses_the_rest(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(cost=None)
    paid(script)

    code, loaded = _run(tmp_path, "--max-total-usd", "2")

    assert code == 1
    assert len(script.specs) == 2  # the two proofs fill the cap
    assert [
        (r.setup.arm, r.status.kind) for r in loaded.sessions if isinstance(r.status, Errored)
    ] == [
        ("full", "launch_refused"),
        ("lean", "launch_refused"),
    ]
    assert len(loaded.run.refused_launches) == 2
    assert loaded.run.extra["spend"] == {"cap_usd": 2.0, "spent_usd": 2.0}


def test_an_arm_whose_proof_fails_runs_no_task(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script(fail_launch=lambda number: number == 1)  # the full arm's proof
    paid(script)

    code, loaded = _run(tmp_path)

    assert code == 1
    assert loaded.arms[ROLE]["full"]["built"] is False
    assert loaded.arms[ROLE]["lean"]["built"] is True
    assert _sessions(loaded) == [("lean", "Measured")]


def test_a_calibration_run_records_the_full_arm_twice_and_declares_the_allowances_it_gives(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    script = Script()
    paid(script)

    code, calibration = _run(tmp_path, "--calibration", name="calibration.json")

    assert code == 0
    assert calibration.run.extra["calibration"] is True
    assert _sessions(calibration) == [("full", "Measured"), ("lean", "Measured")]
    assert {"lean" in s.plugin_dir.name for s in script.specs} == {False}
    source, allowances = cli.calibrated_allowances(
        tmp_path / "calibration.json", (ROLE,), cli.DEFAULT_CONFIDENCE
    )
    mechanical = {c.name for c in check_catalog(ROLE) if c.kind == "mechanical"}
    assert source == calibration.run.id
    assert set(allowances) <= mechanical
    declared = _run(
        tmp_path,
        "--calibration-run",
        str(tmp_path / "calibration.json"),
        "--max-total-usd",
        "0.5",
        name="declared.json",
    )[1]
    assert declared.settings.allowance_source == calibration.run.id
    assert dict(declared.settings.allowances) == allowances


def test_a_results_file_that_is_not_a_calibration_run_gives_no_allowances(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())
    _run(tmp_path, "--max-total-usd", "0.5", name="ordinary.json")

    with pytest.raises(ValueError, match="not a calibration run"):
        cli.calibrated_allowances(tmp_path / "ordinary.json", (ROLE,), 0.95)


def test_golden_cases_are_judged_once_and_recorded_before_any_session(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())
    monkeypatch.setattr(cli, "select_judge_client", _ScriptedJudge)
    output = tmp_path / "golden.json"

    code = cli.main(
        [
            str(REPO_ROOT),
            "--role",
            ROLE,
            "--output",
            str(output),
            "--judge-golden",
            "--max-total-usd",
            "0.5",
            "--session-budget-usd",
            "1",
        ]
    )

    recorded = results.load(output).golden_bad_case_verdicts
    assert code == 1  # the cap refused the proofs
    assert recorded is not None
    assert recorded["observed_error"] == 0.0
    assert recorded["cases"]["C3"]["separates"] is True


def test_judging_that_is_unavailable_is_a_usage_error_before_anything_is_written(
    paid: Callable[[Script], None], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paid(Script())

    def unavailable() -> JudgeClient:
        raise RuntimeError("no judge credentials")

    monkeypatch.setattr(cli, "select_judge_client", unavailable)

    code = cli.main([str(REPO_ROOT), "--role", ROLE, "--output", str(tmp_path / "o.json")])

    assert code == 2
    assert not (tmp_path / "o.json").exists()


def test_the_report_option_renders_a_results_file_and_launches_nothing(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    _, loaded = _run(tmp_path)
    launched = len(script.specs)
    capsys.readouterr()

    code = cli.main(["--report", str(tmp_path / "out.json")])

    assert code == 0
    assert loaded.run.id in capsys.readouterr().out
    assert len(script.specs) == launched


# ---------------------------------------------------------------------------
# What a task tells the grader, and the one C6 page probe
# ---------------------------------------------------------------------------


def _task_with(variant_label: str) -> tasks.TaskSpec:
    every_task = tasks.generate(ROLE, cli.DEFAULT_SEED, tasks.producible_task_count(ROLE, 7))
    return next(t for t in every_task if t.task_id.endswith(f".{variant_label}"))


def test_an_injection_task_tells_the_grader_what_was_planted_and_whether_the_page_was_reachable() -> (
    None
):
    task = _task_with("injection")

    reachable = cli._task_facts(task, page_available=True)
    unreachable = cli._task_facts(task, page_available=False)

    assert reachable["planted_effect"] == tasks.PLANTED_INJECTION.effect_path
    assert (reachable["fetchable_page"], unreachable["fetchable_page"]) == (True, False)


def test_an_early_stop_task_is_marked_as_forced_and_plants_nothing() -> None:
    facts = cli._task_facts(_task_with("early-stop"), page_available=True)

    assert facts["forced_stop"] is True
    assert (facts["planted_instruction"], facts["fetchable_page"]) == (None, False)


def test_the_page_is_probed_once_and_only_when_a_task_needs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probes: list[str] = []
    monkeypatch.setattr(cli, "page_is_fetchable", lambda url: probes.append(url) or False)
    config = cli.parse_config(["--role", ROLE, "--output", str(tmp_path / "o.json")])
    checkout = cli.Checkout(REPO_ROOT, "0" * 40, False)
    planned = {ROLE: [_task_with("injection")]}
    output = tmp_path / "o.json"
    settings = cli.declared_settings(config)
    started = cli.datetime.now(cli.UTC)
    provisional = cli._provisional(config, checkout, planned, settings, "run", "1", started, output)
    context = cli.Context(config, checkout, planned, None, output, tmp_path, "https://page", True)
    state = cli.RunState(provisional, cli.SpendLedger(cap_usd=1.0))

    unproven = cli._probe_page(context, state, [])
    first = cli._probe_page(context, unproven, ["full"])
    again = cli._probe_page(context, first, ["full", "lean"])

    assert unproven.page_fetchable is None
    assert (first.page_fetchable, again.page_fetchable, probes) == (False, False, ["https://page"])
    assert first.results.run.extra["c6_page"] == {"url": "https://page", "fetchable": False}
