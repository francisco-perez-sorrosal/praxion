"""A dry run shows what a paid run would launch, and launches nothing.

The operator names roles, a checkout and arms and adds `--dry-run`: the eval
prints one representative session per task for each arm named -- its command
line and the names of its environment variables -- and starts no session and
writes no results file.
The printed sessions show the isolation every session gets: a sandbox `HOME` and
`CLAUDE_CONFIG_DIR`, the checkout passed only through `--plugin-dir`, MCP servers
off, and a per-session budget.

A stand-in `claude` sits first on the run's PATH: any launch would be recorded
by it rather than reach a real, paying session.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.adherence_eval import (
    DUMMY_CREDENTIAL,
    SEED,
    PlannedSession,
    RunRequest,
    checkout_under_test,
    install_fake_claude,
    planned_sessions,
    run_adherence_eval,
    task_ids,
)

_PLANTED_VARIABLE = "PRAXION_ADHERENCE_LEAK_PROBE"


def _dry_run(tmp_path: Path, roles: tuple[str, ...], arms: tuple[str, ...], **env: str):
    fake = install_fake_claude(tmp_path)
    request = RunRequest(
        roles=roles,
        arms=arms,
        checkout=checkout_under_test(tmp_path),
        output=tmp_path / "results" / "adherence.json",
        dry_run=True,
    )
    result = run_adherence_eval(request, fake.bin_dir, extra_env=env)
    assert result.exit_code == 0, f"the dry run failed: {result.stderr[-2000:]}"
    return request, fake, result


def _sessions(
    tmp_path: Path, roles: tuple[str, ...], arms: tuple[str, ...]
) -> list[PlannedSession]:
    _, _, result = _dry_run(tmp_path, roles, arms)
    return planned_sessions(result.stdout)


def test_a_dry_run_starts_no_session_and_writes_no_results_file(tmp_path):
    request, fake, _ = _dry_run(tmp_path, ("researcher",), ("lean",))

    assert fake.launches() == [], "a dry run started a session"
    assert not request.output.exists(), "a dry run wrote a results file"


def test_a_dry_run_prints_sessions_only_for_the_named_role_and_arm(tmp_path):
    sessions = _sessions(tmp_path, ("researcher",), ("lean",))

    assert sessions, "the dry run printed no session"
    assert {(s.role, s.arm) for s in sessions} == {("researcher", "lean")}


def test_a_dry_run_prints_exactly_one_session_for_each_task_of_the_role(tmp_path):
    sessions = _sessions(tmp_path, ("verifier",), ("full",))

    printed = [s.task_id for s in sessions]

    assert sorted(printed) == sorted(task_ids("verifier", SEED)), (
        "the dry run's sessions are not one per task of the verifier's task set"
    )
    assert len(printed) == len(set(printed)), "a task was printed more than once"


def test_a_dry_run_naming_both_arms_prints_one_session_per_task_for_each_arm(tmp_path):
    sessions = _sessions(tmp_path, ("verifier",), ("full", "lean"))

    printed = sorted((s.task_id, s.arm) for s in sessions)

    assert printed == sorted(
        (task, arm) for task in task_ids("verifier", SEED) for arm in ("full", "lean")
    ), "a two-arm dry run does not print exactly one session per task for each arm"


def test_a_dry_run_names_environment_variables_and_never_prints_their_values(tmp_path):
    _, _, result = _dry_run(
        tmp_path, ("researcher",), ("full",), **{_PLANTED_VARIABLE: "leaked-value"}
    )

    sessions = planned_sessions(result.stdout)

    assert DUMMY_CREDENTIAL not in result.stdout, "the dry run printed a credential's value"
    assert all({"HOME", "CLAUDE_CONFIG_DIR"} <= s.env_names for s in sessions), (
        "a printed session does not set its own HOME and CLAUDE_CONFIG_DIR"
    )
    assert not any(_PLANTED_VARIABLE in s.env_names for s in sessions), (
        "an operator variable outside the allowlist reaches the session environment"
    )


def test_every_printed_session_receives_the_checkout_only_through_one_plugin_dir(tmp_path):
    sessions = _sessions(tmp_path, ("researcher",), ("lean",))

    plugin_dirs = [s.option_values("--plugin-dir") for s in sessions]

    assert all(len(dirs) == 1 for dirs in plugin_dirs), f"--plugin-dir counts: {plugin_dirs[:3]}"
    assert not any(str(Path.home() / ".claude") in d[0] for d in plugin_dirs), (
        "a session is handed the operator's own ~/.claude as its plugin"
    )


def test_every_printed_session_runs_with_mcp_servers_off(tmp_path):
    sessions = _sessions(tmp_path, ("researcher",), ("full",))

    assert sessions, "the dry run printed no session"
    assert all("--strict-mcp-config" in s.argv for s in sessions), (
        "a session may load MCP servers from outside its own empty configuration"
    )


def test_every_printed_session_carries_its_own_positive_budget(tmp_path):
    sessions = _sessions(tmp_path, ("verifier",), ("lean",))

    budgets = [s.option_values("--max-budget-usd") for s in sessions]

    assert sessions, "the dry run printed no session"
    assert all(len(b) == 1 and float(b[0]) > 0 for b in budgets), f"budgets: {budgets[:3]}"


def test_both_arms_of_a_task_give_the_main_session_the_same_prompt(tmp_path):
    full = _sessions(tmp_path / "full", ("researcher",), ("full",))
    lean = _sessions(tmp_path / "lean", ("researcher",), ("lean",))

    full_prompts = {s.task_id: s.prompt for s in full}
    lean_prompts = {s.task_id: s.prompt for s in lean}

    assert set(full_prompts) == set(lean_prompts), "the two arms do not run the same tasks"
    assert full_prompts == lean_prompts, "a task's main-session prompt differs between the arms"
