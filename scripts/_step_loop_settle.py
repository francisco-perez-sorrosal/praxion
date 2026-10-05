"""What `record` leaves in the working tree once an attempt ended or a request was withdrawn.

* **The capped attempt ended unverified**: the line reads `[BLOCKED] replan: <text>`, one line
  naming each attempt of the series with what stopped it, the gate's evidence and its commit,
  so the person who must decide, and the reconciler, read why the loop stopped. Whether the
  series is exhausted is the state module's reading, never a second one here.
* **A request that never started**: the line returns to what it was before the write-ahead,
  `count=<n-1>` for an implement request (a review or revise request leaves the count alone),
  or is removed when nothing was counted before.

* **The step's checklist line** in `WIP.md` is ticked once its work is committed.
* **Edits the commit leaves behind** are named in warnings: files changed since the request's
  prompt was written that are outside the step's `Files:`, or outer-loop files.

The two line writes replace the step's own line and write nothing when it already reads so, which lets
a `record` cut off after its ledger record settle the line when the same call runs again.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from _loop_fields import Attempt, OutstandingAttempt
from _plan_steps import PlanStep
from _step_loop_files import STEP_LABEL, set_attempts_line, write_atomic
from _step_loop_io import paths_differing_from_head, split_outer_loop
from _step_loop_record_gate import TaskView
from _step_loop_state import Exhausted, LoopInputs, spent, step_series
from _step_schema import checklist_step_id
from iteration_ledger import IterationRecord

PROMPT_FILE = "PROMPT_{}.md"
ATTEMPT_SEPARATOR = " | "
NO_COMMIT = "no commit"

Warnings = tuple[tuple[str, str], ...]  # (code, message)


def replan_text(attempts: tuple[IterationRecord, ...]) -> str:
    """One line: for each attempt, what stopped it, the gate's evidence and its commit."""
    parts = (
        f"attempt {one.attempt}: {one.stop_reason}; {one.test_result}; {one.commit or NO_COMMIT}"
        for one in attempts
    )
    return " ".join(ATTEMPT_SEPARATOR.join(parts).split())


def settle_replan(wip_path: Path, inputs: LoopInputs, step: PlanStep, request: str) -> bool:
    """Write the replan line when the step's series, `inputs` holding the ended `request`, is
    exhausted; True when it wrote."""
    ended = replace(inputs, attempts={k: v for k, v in inputs.attempts.items() if k != step.id})
    state = step_series(step, ended)
    if not isinstance(state, Exhausted):
        return False
    text = replan_text(state.attempts)
    return set_attempts_line(wip_path, step.id, Attempt(spent(state.attempts), text, request))


def withdraw_line(wip_path: Path, step_id: str, outstanding: OutstandingAttempt, kind: str) -> bool:
    """Restore the line the write-ahead replaced (see the module docstring)."""
    before = outstanding.count - 1 if kind == "implement" else outstanding.count
    return set_attempts_line(wip_path, step_id, Attempt(before) if before > 0 else None)


def tick_step(wip_path: Path, step_id: str) -> bool:
    """Tick the step's checklist line in `WIP.md` when it is unticked; True when it wrote."""
    lines = wip_path.read_text(encoding="utf-8").split("\n")
    label = STEP_LABEL + step_id
    at = next(
        (i for i, line in enumerate(lines) if checklist_step_id(line) == label and "[ ]" in line),
        None,
    )
    if at is None:
        return False
    lines[at] = lines[at].replace("[ ]", "[x]", 1)
    return write_atomic(wip_path, "\n".join(lines))


# --- Warnings about the tree -----------------------------------------------------------------


def edit_warnings(task: TaskView, step: PlanStep, request: str) -> Warnings:
    """Files changed since the request's prompt was written that its commit leaves behind:
    outside the step's `Files:`, or outer-loop files, which are never committed. A change
    older than the prompt is the user's own and is not reported."""
    prompt = task.dir / PROMPT_FILE.format(request)
    since = prompt.stat().st_mtime if prompt.exists() else float("-inf")
    changed = [
        path
        for path in paths_differing_from_head(task.repo, ["."])
        if _changed_since(task.repo / path, since)
    ]
    read_only = tuple(entry for s in task.inputs.steps for entry in s.read_only)
    kept, outer = split_outer_loop(changed, read_only, task.repo)
    declared = set(paths_differing_from_head(task.repo, step.files)) if step.files else set()
    stray = [path for path in kept if path not in declared]
    left = "left uncommitted"
    return (
        *(
            ("undeclared-edit", f"{path} changed outside the step's Files:; {left}")
            for path in stray
        ),
        *(("outer-loop-edit", f"{path} is an outer-loop file; {left}") for path in outer),
    )


def _changed_since(path: Path, since: float) -> bool:
    try:
        return path.lstat().st_mtime >= since
    except OSError:  # deleted during the attempt, or unreadable: report it rather than hide it
        return True
