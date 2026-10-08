"""Tests that a goal step holds its own failing tests as pending and nothing else.

The goal's targets are the failing nodes of its check's own run. The pure rule is pinned on
pytest output text; the gate is then driven over a scratch git repository holding a hand-written
goal plan and a two-test module, one test the goal's target and one a bystander, so the rule is
shown to reach both the check's run and the derived scope's. An ordinary step keeps its rule.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record_gate as gating  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_gate import GoalTargets, Ownership, classify_run  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402

STEP = "Step "
STEP_ID = "1"
OTHER_ID = "2"
REQUEST = "s1-a1-implement"
COMMAND = "uv run pytest scripts/test_x.py -q"
TARGET = "test_pair.py::test_target"
BYSTANDER = "test_pair.py::test_bystander"
LATER_OWNED = "tests/acceptance/test_later.py::test_one"
MODULE = "test_pair.py"
PASSING = "def test_{name}():\n    assert True\n"
FAILING = "def test_{name}():\n    assert False\n"
GREEN_BYSTANDER = FAILING.format(name="target") + "\n\n" + PASSING.format(name="bystander")
RED_BYSTANDER = FAILING.format(name="target") + "\n\n" + FAILING.format(name="bystander")
BROKEN_IMPORT = "import module_that_does_not_exist\n\n\n" + FAILING.format(name="target")
PRE_EXISTING = "def test_old():\n    assert True\n"
STEADY_MODULE = "test_steady.py"
STEADY = PASSING.format(name="one") + "\n\n" + PASSING.format(name="two")
TALLIED = ("pass", "fail", "error", "pending")
PENDING_SCOPE = ("pass=1", "fail=0", "pending=1")
PENDING_CHECK = ("pass=2", "fail=0", "pending=1")
RED_SCOPE = ("pass=0", "fail=1", "pending=1")
FAILING_SCOPE = ("pass=1", "fail=1", "pending=0")
FAILING_CHECK = ("pass=2", "fail=1", "pending=0")
ERRORED = ("pass=0", "fail=0", "error=1", "pending=0")
FAIL_TWO = f"FAILED {TARGET} - assert False\nFAILED {BYSTANDER} - assert False\n"


def summary(*lines, counts="2 failed, 3 passed in 0.10s"):
    return "\n".join([*lines, counts, ""])


def goal(*targets):
    return GoalTargets(frozenset(targets))


# --- The rule, on pytest output ------------------------------------------------------------


def test_a_target_that_fails_is_pending_and_leaves_the_run_green_of_failures():
    run = classify_run(
        COMMAND, summary(f"FAILED {TARGET} - boom", counts="1 failed in 0.1s"), goal(TARGET)
    )

    assert (run.counts.failed, run.pending_ids, run.failed_ids, run.red) == (0, (TARGET,), (), True)


def test_a_failing_node_that_is_not_a_target_keeps_the_run_red():
    run = classify_run(COMMAND, summary(FAIL_TWO), goal(TARGET))

    assert (run.counts.failed, run.pending_ids, run.failed_ids) == (1, (TARGET,), (BYSTANDER,))


def test_an_empty_set_of_targets_pends_nothing():
    run = classify_run(COMMAND, summary(FAIL_TWO), goal())

    assert (run.counts.failed, run.pending_ids, run.failed_ids) == (2, (), (TARGET, BYSTANDER))


def test_an_error_node_is_never_pending_even_when_its_id_is_a_target():
    output = summary(f"ERROR {TARGET} - fixture missing", counts="1 error in 0.1s")

    run = classify_run(COMMAND, output, goal(TARGET))

    assert (run.counts.errors, run.pending_ids, run.failed_ids, run.red) == (1, (), (TARGET,), True)


def test_a_target_failing_beside_its_own_error_still_reads_red():
    output = summary(
        f"FAILED {TARGET} - boom",
        f"ERROR {TARGET} - teardown",
        counts="1 failed, 1 error in 0.1s",
    )

    run = classify_run(COMMAND, output, goal(TARGET))

    assert (run.counts.failed, run.counts.errors, run.pending_ids) == (0, 1, (TARGET,))


def test_the_goal_rule_ignores_the_read_only_entries_other_steps_declare():
    output = summary(f"FAILED {LATER_OWNED} - boom", counts="1 failed in 0.1s")
    owners = {STEP_ID: (), OTHER_ID: ("tests/acceptance/",)}

    as_goal = classify_run(COMMAND, output, goal(TARGET))
    as_ordinary = classify_run(COMMAND, output, Ownership(STEP_ID, owners, frozenset()))

    assert (as_goal.pending_ids, as_ordinary.pending_ids) == ((), (LATER_OWNED,))


def test_an_ordinary_rule_still_pends_an_errored_node_a_later_step_owns():
    output = summary(f"ERROR {LATER_OWNED} - boom", counts="1 error in 0.1s")
    owners = {STEP_ID: (), OTHER_ID: ("tests/acceptance/",)}

    run = classify_run(COMMAND, output, Ownership(STEP_ID, owners, frozenset()))

    assert (run.counts.errors, run.pending_ids) == (0, (LATER_OWNED,))


# --- The gate, over a scratch repository ---------------------------------------------------


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=60)


def scratch_repo(root):
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    for key, value in (
        ("user.name", "Goal Targets"),
        ("user.email", "goal-targets@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(repo, "config", key, value)
    (repo / ".gitignore").write_text(".ai-work/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "goal-widget"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\npythonpath = ["."]\n',
        encoding="utf-8",
    )
    (repo / MODULE).write_text(PRE_EXISTING, encoding="utf-8")
    (repo / STEADY_MODULE).write_text(STEADY, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def plan_text(*, goal_step):
    pytest_command = f"{shlex.quote(sys.executable)} -m pytest -q -p no:cacheprovider"
    check = f"{pytest_command} {TARGET} {STEADY_MODULE}"
    bound = "**Iterations**: 3\n" if goal_step else ""
    return (
        "# Plan\n\n## Steps\n\n"
        f"### {STEP}{STEP_ID} \u2014 Turn the target test green\n\n"
        "**Assignee**: implementer\n"
        f"**Files**: `{MODULE}`\n"
        f"**Check**: `{check}` expects pass>=1 fail=0\n"
        f"{bound}"
        "**Done when**: the check is met and no protected path changed\n\n"
        "Turn the target test green.\n"
    )


def task_over(tmp_path, monkeypatch, *, goal_step, module_text):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    repo = scratch_repo(tmp_path)
    steps = parse_plan_steps(plan_text(goal_step=goal_step))
    work = tmp_path / "work"
    (work / "task").mkdir(parents=True)
    (repo / MODULE).write_text(module_text, encoding="utf-8")
    inputs = LoopInputs.read(steps, {}, (), ())
    task = SimpleNamespace(
        slug="task", repo=repo, work=work, dir=work / "task", base_ref="HEAD", inputs=inputs
    )
    return task, steps[0]


def gated(tmp_path, monkeypatch, *, goal_step, module_text):
    task, step = task_over(tmp_path, monkeypatch, goal_step=goal_step, module_text=module_text)
    return gating.run_gate(task, step, REQUEST)


def result_lines(gate):
    return [line for line in gate.body if line.startswith("Result:")]


def tally(gate):
    """Each result line's counted tokens (no `skip`, no marker), in the order written."""
    return [
        tuple(token for token in line.split()[1:] if token.partition("=")[0] in TALLIED)
        for line in result_lines(gate)
    ]


def test_the_plan_text_reads_as_a_goal_step_bound_by_its_budget(tmp_path, monkeypatch):
    _, step = task_over(tmp_path, monkeypatch, goal_step=True, module_text=GREEN_BYSTANDER)

    assert (step.id, type(step.bound).__name__, step.files) == (STEP_ID, "GoalBudget", (MODULE,))


def test_a_goal_whose_only_failure_is_its_target_is_pending_in_both_runs(tmp_path, monkeypatch):
    gate = gated(tmp_path, monkeypatch, goal_step=True, module_text=GREEN_BYSTANDER)

    assert (gate.red, tally(gate)) == (False, [PENDING_SCOPE, PENDING_CHECK])


def test_a_goal_leaves_the_gate_red_when_a_test_that_is_not_its_target_fails(tmp_path, monkeypatch):
    gate = gated(tmp_path, monkeypatch, goal_step=True, module_text=RED_BYSTANDER)

    assert (gate.red, tally(gate)) == (True, [PENDING_CHECK, RED_SCOPE])


def test_a_goal_whose_module_no_longer_imports_is_red_and_pends_nothing(tmp_path, monkeypatch):
    gate = gated(tmp_path, monkeypatch, goal_step=True, module_text=BROKEN_IMPORT)

    assert (gate.red, tally(gate)) == (True, [ERRORED, ERRORED])


def test_an_ordinary_step_over_the_same_module_gets_no_pending_pass(tmp_path, monkeypatch):
    gate = gated(tmp_path, monkeypatch, goal_step=False, module_text=GREEN_BYSTANDER)

    assert (gate.red, tally(gate)) == (True, [FAILING_SCOPE, FAILING_CHECK])


def test_a_goal_that_declares_no_check_pends_nothing_in_its_derived_scope(tmp_path, monkeypatch):
    task, step = task_over(tmp_path, monkeypatch, goal_step=True, module_text=GREEN_BYSTANDER)

    gate = gating.run_gate(task, replace(step, check=None), REQUEST)

    assert (gate.red, tally(gate)) == (True, [FAILING_SCOPE])
