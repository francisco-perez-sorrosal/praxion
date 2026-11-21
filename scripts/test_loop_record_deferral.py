"""A checked step's gate leaves each widened pocket unrun and says so on a `Deferred:` line.

The resolver and the runs are real subprocesses (a stub resolver script, `python -c` runs); only
the step's `Check:` run and the git readers are stood in for. The whole call runs in the
acceptance suite over a real checkout; these pin the filter, the block's line order and the
read-back, and that a goal step and a step with no check gate as before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _step_loop_io as step_io  # noqa: E402
import _step_loop_record_gate as gating  # noqa: E402
import step_loop  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import Checkpoint  # noqa: E402
from _step_loop_checkpoint import WaitingPocket  # noqa: E402
from _step_loop_checkpoint_run import CheckpointGreen  # noqa: E402
from _step_loop_io import CommandRun, ScopeRuns, run_derived_scope  # noqa: E402
from _step_loop_record import Taken  # noqa: E402
from _step_loop_render import Invocation  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402

REQUEST = "s1-a1-implement"
HEAD = "0123456789abcdef0123456789abcdef01234567"
WIDENED, NARROW = "full", "tests"
PASSED = CommandRun(("python3", "-m", "pytest", "-q"), ".", "3 passed in 0.1s", 0)
STEP = "Step "
STEP_HEAD = f"## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n**Files**: `a.py`\n"
CHECK_LINE = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0\n"


class NothingPends:
    """A pending rule under which no failing node belongs to a later step."""

    def is_pending(self, node_id: str) -> bool:
        return False

    def is_pending_error(self, node_id: str) -> bool:
        return False


NOTHING_PENDING = NothingPends()


def writes_marker_then_passes(marker: Path) -> tuple[str, ...]:
    code = f"open({str(marker)!r}, 'w').close(); print('3 passed in 0.1s')"
    return (sys.executable, "-c", code)


def pocket_answer(root: str, selection: str, marker: Path) -> dict:
    argv = list(writes_marker_then_passes(marker))
    return {
        "root": root,
        "selection": selection,
        "tests": [{"path": f"{root}/t.py"}],
        "invocations": [{"cwd": root, "argv": argv}],
    }


class World:
    """A repository holding a narrow pocket `.` and a widened pocket `eval`, each of whose runs
    leaves a marker file, behind a stub resolver that answers them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, only_widened=False):
        self.root = tmp_path
        (tmp_path / "eval").mkdir()
        self.narrow_marker = tmp_path / "narrow.ran"
        self.widened_marker = tmp_path / "widened.ran"
        pockets = [pocket_answer("eval", WIDENED, self.widened_marker)]
        if not only_widened:
            pockets.insert(0, pocket_answer(".", NARROW, self.narrow_marker))
        answer = json.dumps({"schema": 2, "decision": "narrow", "pockets": pockets})
        stub = tmp_path / "stub_resolver.py"
        stub.write_text(f"print({answer!r})\n")
        monkeypatch.setattr(step_io, "RESOLVER", stub)
        monkeypatch.setattr(gating, "head_sha", lambda _repo: HEAD)
        monkeypatch.setattr(gating, "paths_differing_from_head", lambda *_: ("a.py",))
        monkeypatch.setattr(gating, "run_bounded_check", lambda *_: PASSED)

    def gate(self, *plan_lines: str) -> gating.Gate:
        steps = tuple(parse_plan_steps(STEP_HEAD + "".join(plan_lines)))
        stand_in = SimpleNamespace(
            slug="demo",
            repo=self.root,
            work=self.root,
            dir=self.root,
            base_ref="HEAD",
            inputs=LoopInputs(steps, {}, (), {}),
        )
        return gating.run_gate(cast(gating.TaskView, stand_in), steps[0], REQUEST)


def lines_starting(gate: gating.Gate, prefix: str) -> list[str]:
    return [line for line in gate.body if line.startswith(prefix)]


# -- The filter ----------------------------------------------------------------------------------


def test_a_widened_pocket_is_not_run_and_its_root_is_returned_when_asked_to_defer(
    tmp_path, monkeypatch
):
    world = World(tmp_path, monkeypatch)

    scope = run_derived_scope(tmp_path, ["a.py"], tmp_path / "gate", {}, defer_widened=True)

    assert isinstance(scope, ScopeRuns)
    assert (
        [pocket.pocket for pocket in scope.pockets],
        scope.deferred,
        world.narrow_marker.exists(),
        world.widened_marker.exists(),
    ) == (["."], ("eval",), True, False)


def test_a_widened_pocket_runs_whole_and_nothing_is_deferred_unless_asked(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)

    scope = run_derived_scope(tmp_path, ["a.py"], tmp_path / "gate", {})

    assert isinstance(scope, ScopeRuns)
    assert (
        [pocket.pocket for pocket in scope.pockets],
        scope.deferred,
        world.widened_marker.exists(),
    ) == ([".", "eval"], (), True)


def test_a_scope_whose_only_pocket_is_deferred_is_no_run_but_keeps_the_deferral(
    tmp_path, monkeypatch
):
    World(tmp_path, monkeypatch, only_widened=True)

    reading, deferred = gating.scope_run(
        tmp_path, tmp_path / "gate", ["a.py"], NOTHING_PENDING, defer_widened=True
    )

    assert (reading, deferred) == (None, ("eval",))


# -- The block -----------------------------------------------------------------------------------


def test_a_checked_step_writes_a_deferred_line_after_the_scope_lines_and_before_every_result(
    tmp_path, monkeypatch
):
    world = World(tmp_path, monkeypatch)

    gate = world.gate(CHECK_LINE)

    kinds = [line.split(":")[0] for line in gate.body]
    assert (
        kinds.index("Scope") < kinds.index("Derived from") < kinds.index("Deferred"),
        kinds.index("Deferred") < kinds.index("Result"),
        gate.deciding.startswith("Result:"),
        gate.deferred,
        world.widened_marker.exists(),
    ) == (True, True, True, ("eval",), False)


def test_no_scope_or_result_line_names_a_deferred_pocket(tmp_path, monkeypatch):
    gate = World(tmp_path, monkeypatch).gate(CHECK_LINE)

    named = [line for line in lines_starting(gate, "Scope:") if "eval" in line]
    assert (named, len(lines_starting(gate, "Deferred:"))) == ([], 1)


def test_a_step_whose_only_pocket_is_deferred_is_decided_by_its_check_not_red(
    tmp_path, monkeypatch
):
    gate = World(tmp_path, monkeypatch, only_widened=True).gate(CHECK_LINE)

    assert (gate.red, gate.deferred, lines_starting(gate, "Scope:")) == (False, ("eval",), [])


def test_a_gate_block_read_back_after_a_cut_off_call_carries_the_same_deferral(
    tmp_path, monkeypatch
):
    world = World(tmp_path, monkeypatch)
    written = world.gate(CHECK_LINE)

    read_back = gating.recorded_gate(
        tmp_path / gating.RESULTS_FILE, gating.gate_heading("1", REQUEST)
    )

    assert read_back is not None
    assert (read_back.deferred, read_back.body) == (written.deferred, written.body)


# -- What the deferral leaves as it was -----------------------------------------------------------


def test_a_step_with_no_check_runs_its_widened_pocket_whole_and_defers_nothing(
    tmp_path, monkeypatch
):
    world = World(tmp_path, monkeypatch)

    gate = world.gate()

    assert (gate.deferred, world.widened_marker.exists()) == ((), True)


def test_a_step_whose_check_cannot_be_read_runs_its_widened_pocket_whole(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)

    gate = world.gate("**Check**: not a command in backticks\n")

    assert (gate.deferred, world.widened_marker.exists()) == ((), True)


def test_a_goal_step_runs_its_widened_pocket_whole_and_defers_nothing(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)
    step = tuple(parse_plan_steps(STEP_HEAD + CHECK_LINE))[0]

    scope, _ = gating.goal_runs(tmp_path, tmp_path / "gate", step, ("a.py",), float("inf"))

    assert scope is not None
    assert (world.widened_marker.exists(), "eval" in " ".join(scope.scopes)) == (True, True)


# -- A record never runs the checkpoint; the next after it does ------------------------------------


class CheckpointDue:
    """A task whose every step is done with two pockets waiting, and a checkpoint run that logs
    each start instead of running a suite (the run itself is covered by the checkpoint's tests)."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self.waiting = (WaitingPocket("eval", ("2", "3")), WaitingPocket(".", ("3",)))
        self.started: list[tuple[str, ...]] = []
        directory = tmp_path / ".ai-work" / "demo"
        directory.mkdir(parents=True)
        self.task = SimpleNamespace(
            slug="demo",
            repo=tmp_path,
            work=tmp_path,
            dir=directory,
            base_ref="HEAD",
            inputs=LoopInputs((), {}, (), {}),
        )
        monkeypatch.setattr(step_loop, "issuable_action", lambda _inputs: Checkpoint(self.waiting))
        monkeypatch.setattr(step_loop, "run_checkpoint", self.run_checkpoint)

    def run_checkpoint(self, _repo, _directory, waiting, *_):
        self.started.append(tuple(pocket.root for pocket in waiting))
        return CheckpointGreen()

    def call(self, took: Taken | None):
        task = cast(step_loop.Task, self.task)
        return step_loop.run_next(task, cast(object, None), Invocation("step_loop.py"), took)


def test_the_record_that_leaves_only_the_checkpoint_stops_checkpoint_due_and_starts_no_run(
    tmp_path, monkeypatch
):
    due = CheckpointDue(tmp_path, monkeypatch)

    reply = due.call(Taken({}, "3"))

    stop = reply.doc["stop"]
    assert (reply.exit, reply.doc["outcome"], stop["cause"], stop["step"]) == (
        2,
        "needs-human",
        "checkpoint-due",
        None,
    )
    assert (due.started, stop["resume"]) == ([], "step_loop.py next demo")
    assert stop["evidence"] == (
        "every step is done and these pockets wait: "
        f"eval (waiting steps: {STEP}2, {STEP}3); . (waiting steps: {STEP}3)"
    )


def test_the_next_after_the_stop_runs_the_checkpoint_once_and_prints_complete(
    tmp_path, monkeypatch
):
    due = CheckpointDue(tmp_path, monkeypatch)

    reply = due.call(None)

    assert (reply.doc["outcome"], due.started) == ("complete", [("eval", ".")])
