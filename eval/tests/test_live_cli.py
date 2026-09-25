"""Behavioral tests for the `praxion-evals-live` CLI's testable surfaces.

Only three surfaces are exercised here, per the runner's own health guard:
the credential check, `--dry-run`'s output shape, and the spend-guard abort
path. No test in this file starts a real `claude` process — `--dry-run` is
asserted to never reach `run_argv`, and the spend guard is tested through the
pure `SpendLedger` decision it is built on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "scenario"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "scenario@example.invalid"], cwd=root, check=True
    )
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=root, check=True)


# ---------------------------------------------------------------------------
# Credential check — exits before anything else, names the three variables
# ---------------------------------------------------------------------------


def test_missing_credential_is_true_when_none_of_the_three_variables_are_set():
    from praxion_evals.live.cli import _missing_credential

    assert _missing_credential({"PATH": "/usr/bin"}) is True


def test_missing_credential_is_false_when_any_one_variable_is_set():
    from praxion_evals.live.cli import _missing_credential

    for key in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
        assert _missing_credential({key: "x"}) is False


def test_main_exits_nonzero_and_names_the_credential_variables_when_none_are_set(
    monkeypatch, capsys
):
    from praxion_evals.live.cli import CREDENTIAL_KEYS, main

    for key in CREDENTIAL_KEYS:
        monkeypatch.delenv(key, raising=False)

    exit_code = main([])

    assert exit_code == 2
    output = capsys.readouterr().out
    assert all(key in output for key in CREDENTIAL_KEYS)


def test_main_refuses_to_overwrite_an_existing_output_without_the_flag(monkeypatch, tmp_path):
    from praxion_evals.live.cli import main

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    existing = tmp_path / "baseline.json"
    existing.write_text("{}\n", encoding="utf-8")

    exit_code = main(["--output", str(existing)])

    assert exit_code == 2


# ---------------------------------------------------------------------------
# --dry-run — prints argv + env keys, never starts a real session
# ---------------------------------------------------------------------------


def test_dry_run_prints_argv_and_env_keys_and_spawns_nothing(monkeypatch, tmp_path, capsys):
    from praxion_evals.live import cli

    def _forbidden(*args, **kwargs):
        raise AssertionError("--dry-run must never invoke a claude process")

    monkeypatch.setattr("praxion_evals.live.session.run_argv", _forbidden)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    exit_code = cli.main(["--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "argv:" in output
    assert "env keys:" in output
    assert "claude" in output


def test_dry_run_covers_every_registered_scenario():
    from praxion_evals.live import cli, scenarios

    fixtures_by_id = cli._load_fixtures_by_id()
    tasks = cli.build_tasks(fixtures_by_id, k=3)
    representative_ids = {task.scenario_id for task in tasks if task.repeat == 1}

    assert representative_ids == set(scenarios.SCENARIOS)


def test_canary_variant_runs_only_the_spawn_selection_cases():
    from praxion_evals.live import cli

    fixtures_by_id = cli._load_fixtures_by_id()

    head_tasks = cli.variant_tasks(fixtures_by_id, k=3, variant="head")
    canary_tasks = cli.variant_tasks(fixtures_by_id, k=3, variant="canary")

    assert {t.scenario_id for t in head_tasks} == set(cli.scenarios.SCENARIOS)
    assert {t.scenario_id for t in canary_tasks} == {"spawn-selection"}
    assert len(canary_tasks) == 5 * 3  # 5 cases x k


def test_scenario_filter_restricts_the_run_to_the_named_scenarios():
    """A targeted re-measure (one scenario after an instrument fix) must not pay
    for the other four."""
    from praxion_evals.live import cli

    fixtures_by_id = cli._load_fixtures_by_id()
    args = cli._parse_args(["--scenario", "lightweight-fix", "--k", "3"])

    tasks = cli.variant_tasks(fixtures_by_id, args.k, "head", args.scenario)

    assert {t.scenario_id for t in tasks} == {"lightweight-fix"}
    assert len(tasks) == 3


def test_scenario_filter_rejects_an_unknown_scenario_id():
    from praxion_evals.live import cli

    with pytest.raises(SystemExit):
        cli._parse_args(["--scenario", "lightweight_fix"])


def test_no_scenario_filter_keeps_every_scenario():
    from praxion_evals.live import cli

    fixtures_by_id = cli._load_fixtures_by_id()
    args = cli._parse_args([])

    tasks = cli.variant_tasks(fixtures_by_id, 1, "head", args.scenario)

    assert {t.scenario_id for t in tasks} == set(cli.scenarios.SCENARIOS)


# ---------------------------------------------------------------------------
# Spend guard — a launch that would cross the cap is refused, never silently
# skipped, and the ledger never charges more than the cap
# ---------------------------------------------------------------------------


def test_reserve_refuses_a_launch_that_would_cross_the_cap():

    from praxion_evals.live.cli import _reserve
    from praxion_evals.live.results import Errored
    from praxion_evals.live.spend import SpendLedger

    ledger = SpendLedger(cap_usd=1.0, spent_usd=0.9)

    admitted, next_ledger = _reserve(ledger, 0.5)

    assert isinstance(admitted, Errored)
    assert admitted.kind == "not_run_budget_exhausted"
    assert next_ledger is ledger  # a refusal never mutates the committed ledger


def test_a_budget_exhausted_session_becomes_an_error_record_not_a_skip():
    from praxion_evals.live.results import Errored, to_session_record

    record = to_session_record(
        Errored(kind="not_run_budget_exhausted", detail="cap reached"), repeat=2
    )

    assert record["outcome"] == "error"
    assert record["error_kind"] == "not_run_budget_exhausted"
    assert "recorded" not in record


def test_settle_charges_the_full_budget_when_the_envelope_reports_no_cost():

    from praxion_evals.live.cli import _settle
    from praxion_evals.live.session import SessionEnvelope
    from praxion_evals.live.spend import SpendLedger

    ledger = SpendLedger(cap_usd=10.0)
    empty_envelope = SessionEnvelope(
        init=None,
        tool_uses=(),
        subagent_texts=(),
        task_notifications=(),
        hook_outputs=(),
        final_result=None,
        result_count=0,
        unparseable=False,
    )

    settled = _settle(ledger, 3.0, empty_envelope)

    assert settled.spent_usd == 3.0


# ---------------------------------------------------------------------------
# Pure task-building and grading-data helpers
# ---------------------------------------------------------------------------


def test_build_tasks_covers_all_five_spawn_selection_cases_times_k():
    from praxion_evals.live import cli

    fixtures_by_id = cli._load_fixtures_by_id()

    tasks = cli.build_tasks(fixtures_by_id, k=2)

    spawn_tasks = [t for t in tasks if t.scenario_id == "spawn-selection"]
    assert len(spawn_tasks) == 5 * 2
    assert {t.case_index for t in spawn_tasks} == {1, 2, 3, 4, 5}


def test_case_id_is_bare_for_single_case_scenarios_and_indexed_for_spawn_selection():
    from praxion_evals.live.cli import SessionTask, case_id

    single = SessionTask("lightweight-fix", 1, 1, 1, {})
    spawn = SessionTask("spawn-selection", 3, 5, 1, {})

    assert case_id(single) == "lightweight-fix"
    assert case_id(spawn) == "spawn-selection#3"


def test_graded_data_replaces_only_the_one_spawn_selection_case_under_grade():
    from praxion_evals.live.cli import SessionTask, _graded_data

    fixture_yaml = {
        "scenario_id": "spawn-selection",
        "cases": [{"task": "a", "recorded_tier": "x"}, {"task": "b", "recorded_tier": "y"}],
    }
    task = SessionTask("spawn-selection", 2, 2, 1, fixture_yaml["cases"][1])

    data = _graded_data(task, fixture_yaml, {"recorded_tier": "standard", "recorded_agents": []})

    assert len(data["cases"]) == 1
    assert data["cases"][0]["task"] == "b"
    assert data["cases"][0]["recorded_tier"] == "standard"


def test_graded_data_replaces_the_recorded_field_for_a_single_case_scenario():
    from praxion_evals.live.cli import SessionTask, _graded_data

    fixture_yaml = {"scenario_id": "commit-staging", "recorded_command": "old"}
    task = SessionTask("commit-staging", 1, 1, 1, fixture_yaml)

    data = _graded_data(task, fixture_yaml, "git add a.py")

    assert data["recorded_command"] == "git add a.py"
