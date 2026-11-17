"""The pure decision of the step-loop driver: spawn a request, complete, or stop.

Everything arrives through `LoopInputs` and nothing is read or written here, so a stop that
holds while its evidence holds is simply re-derived by the next call, and it clears when the
evidence changes: a plan revision clears an exhausted or marked step (a fresh series), a
review file reading `accept` clears the review stops, a step done outside the loop clears a
hand-back, and a changed reconciler verdict clears a human verdict.

Normative precedence, a total function of the inputs, first match wins:

1. `Complete` when every step is done.
2. A human stop, in this order: the stop of the outstanding request's reading (below),
   `unnamed-attempts`, `dependency-defect`, `commit-disturbed-tree`, a marker, then the stop of
   the selected step, which is the earliest step in plan order that is not done.
3. `iteration-budget` when the iterations used have reached the budget, or when the selected
   goal step has used its own `Iterations:` without a stall or a verification.
4. A `Spawn` for the selected step.

A goal step whose bound is spent is the stop `stalled`, an ordinary one `attempts-exhausted`;
the stall outranks a spent budget because the human stops come first. The budget is derived
from the plan alone, so a plan revision opens a new series without growing it.
`commit-disturbed-tree` holds while the tree snapshot of the step's latest recorded request
exists beside the task documents, and clears when a person deletes the file.

At most one request is out after any sequence of calls: the outstanding request is read once
against the plan (`read_outstanding`), and only `NoneOut` lets the plan's own action through.
`Current` reissues the request; `Several` and `Malformed` stop as `loop-state-defect`,
`Miscounted` as `attempts-disagree` and `Superseded` as `request-outstanding`, so a plan changed
while a request is out costs one corrected call (the withdrawal, or the return's record).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union, cast

from _loop_fields import STALL_RUN, GoalBudget, OutstandingAttempt, request_cap
from _plan_steps import PlanStep
from _step_loop_render import Kind, RequestKey, parse_request_id
from _step_loop_review import (
    REVIEW_CYCLE,
    Due,
    Requested,
    RevisedTwice,
    ReviseDue,
    RevisionFailed,
    Unfinished,
    needs_review,
)
from _step_loop_state import (
    EXHAUSTED,
    SNAPSHOT_STEM,
    SNAPSHOT_SUFFIX,
    STEP_LABEL,
    AllDone,
    Defects,
    Exhausted,
    Failed,
    Fresh,
    HumanVerdict,
    LoopInputs,
    Marked,
    Next,
    NotDriven,
    Running,
    Selection,
    UnreadableField,
    Verified,
    is_driven,
    review_range,
    select_step,
    series_states,
    spent,
    step_cap,
    step_series,
)

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

BUDGET_CAUSE = "iteration-budget"
CHECK_CANNOT_COLLECT = "check-cannot-collect"
GLOB_MARKS = "*?["
UNCOMMITTED_SHOWN = 5  # file names a marked stop spells out; the rest are counted
HUMAN_CAUSES = tuple(
    """attempts-exhausted stalled blocked-marker conflict-marker human-verdict unnamed-attempts
    review-revised-twice review-unfinished revision-failed review-without-work not-driven
    dependency-defect commit-disturbed-tree loop-state-defect files-glob request-outstanding
    attempts-disagree unreadable-plan-field check-cannot-collect""".split()
)
NULL_STEP_CAUSES = ("unnamed-attempts", "loop-state-defect", BUDGET_CAUSE)
REPLAN_CAUSES = ("attempts-exhausted", "stalled")  # the stops of a spent bound
_REVIEW_STOPS = {
    RevisedTwice: ("review-revised-twice", "the light review asked for revision twice"),
    Unfinished: ("review-unfinished", "the light reviewer ended without a verdict"),
    RevisionFailed: ("revision-failed", "the revision did not pass the gate"),
}
_DEFECT_WORDS = {
    "missing": "is not in the plan",
    "cycle": "leads back to the step",
    "held": "is itself stuck",
}


@dataclass(frozen=True)
class Spawn:
    """Start the agent for `key`; `reissued` when the request already went out."""

    step: PlanStep
    key: RequestKey
    reissued: bool = False


@dataclass(frozen=True)
class Complete:
    """Every step is done."""


@dataclass(frozen=True)
class Stop:
    """The loop halts. `step` is None exactly for the causes that belong to no one step, and a
    replan request exists exactly for a step whose bound is spent."""

    cause: str
    step: str | None
    evidence: str
    attempts: tuple[IterationRecord, ...] = ()
    replan_request: str | None = None

    def __post_init__(self) -> None:
        if self.cause not in (*HUMAN_CAUSES, BUDGET_CAUSE):
            raise ValueError(f"not a stop cause: {self.cause!r}")
        if (self.step is None) != (self.cause in NULL_STEP_CAUSES):
            raise ValueError(f"cause {self.cause!r} and step {self.step!r} disagree")
        if (self.replan_request is not None) != (self.cause in REPLAN_CAUSES):
            raise ValueError("a replan request goes with attempts-exhausted or stalled, no other")


Action = Union[Spawn, Complete, Stop]  # noqa: UP007 -- runtime value, 3.9 floor


# --- The outstanding request, read against the plan -------------------------------------------


@dataclass(frozen=True)
class NoneOut:
    """No `Attempts:` line names a request the ledger has not recorded."""


@dataclass(frozen=True)
class Several:
    """More than one line names an outstanding request, as `(step, request)` pairs in step
    order: a state only a hand edit or an earlier driver could leave."""

    requests: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Malformed:
    """The line's request is no request id, names another step, or a series its step has not
    reached."""

    step: str
    request: str


@dataclass(frozen=True)
class Miscounted:
    """The request's attempt differs from the count on its own line."""

    step: str
    request: str
    count: int


@dataclass(frozen=True)
class Current:
    """The plan issues exactly this request now, or would once the stop it meets clears."""

    step: str
    key: RequestKey


@dataclass(frozen=True)
class Superseded:
    """The plan no longer issues this request; `why` says what moved, and `block_kept` says
    whether the step's block still holds the request's series, so its return can be gated."""

    step: str
    key: RequestKey
    why: str
    block_kept: bool


OutstandingReading = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    NoneOut, Several, Malformed, Miscounted, Current, Superseded
]


def read_outstanding(inputs: LoopInputs) -> OutstandingReading:
    """The outstanding request against the plan; the series is checked only for a step that is
    running, so a step that stops for another reason keeps its own stop."""
    out = tuple(
        (step, a.request, a.count)
        for step, a in sorted(inputs.attempts.items())
        if isinstance(a, OutstandingAttempt)
    )
    if len(out) > 1:
        return Several(tuple((step, request) for step, request, _ in out))
    if not out:
        return NoneOut()
    step_id, request, count = out[0]
    key = parse_request_id(request)
    if key is None or key.step != step_id:
        return Malformed(step_id, request)
    if key.attempt != count:
        return Miscounted(step_id, request, count)
    step = next((s for s in inputs.steps if s.id == step_id), None)
    if step is None:
        return Superseded(step_id, key, f"{STEP_LABEL}{step_id} is no longer in the plan", False)
    state = step_series(step, inputs)
    if isinstance(state, Running) and key.series != state.series:
        if key.series > state.series:
            return Malformed(step_id, request)
        why = f"the block of {STEP_LABEL}{step_id} was revised after the request's series"
        return Superseded(step_id, key, why, False)
    selection = select_step(inputs)
    if isinstance(selection, Next) and selection.step.id != step_id:
        why = f"the plan now issues {STEP_LABEL}{selection.step.id} first"
        return Superseded(step_id, key, why, True)
    return Current(step_id, key)


def outstanding_id(reading: OutstandingReading) -> str | None:
    """The request a reading still holds out: the id of a current or a superseded one."""
    return reading.key.id if isinstance(reading, (Current, Superseded)) else None


def _outstanding_stop(reading: OutstandingReading) -> Stop | None:
    if isinstance(reading, Several):
        named = ", ".join(f"{STEP_LABEL}{step}" for step, _ in reading.requests)
        return Stop("loop-state-defect", None, f"WIP.md names an outstanding request on {named}")
    if isinstance(reading, Malformed):
        evidence = f"WIP.md names {reading.request}, not the series' own"
        return Stop("loop-state-defect", None, evidence)
    if isinstance(reading, Miscounted):
        evidence = (
            f"the Attempts: line of {STEP_LABEL}{reading.step} names {reading.request}, whose"
            f" attempt is not the line's own count={reading.count}"
        )
        return Stop("attempts-disagree", reading.step, evidence)
    if isinstance(reading, Superseded):
        evidence = f"{reading.key.id} is outstanding and {reading.why}"
        return Stop("request-outstanding", reading.step, evidence)
    return None


def iteration_budget(steps: Iterable[PlanStep]) -> int:
    """The request cap of each driven step's bound, plus the review cycle of each the trigger
    marks: every request the steps' own bounds allow, so a plan that is never revised meets a
    step's own stop before the budget's, and only revised series can spend the budget."""
    return sum(
        step_cap(step) + REVIEW_CYCLE * needs_review(step) for step in steps if is_driven(step)
    )


def iterations_used(inputs: LoopInputs) -> int:
    """The ledger records that carry a request: every request that started an agent."""
    return sum(record.request is not None for record in inputs.records)


def next_action(inputs: LoopInputs) -> Action:
    """The one thing the loop does next."""
    selection = select_step(inputs)
    if isinstance(selection, AllDone):
        return Complete()
    return _human_stop(inputs, selection) or _budget_stop(inputs, selection) or _spawn(selection)


def issuable_action(inputs: LoopInputs) -> Action:
    """The action a call can issue: `next_action`, except that a review request with no commit
    to read, in its series or made outside the loop since the step began, is a stop, because
    the reviewer's prompt names the diff to read."""
    action = next_action(inputs)
    if not (isinstance(action, Spawn) and action.key.kind == "review"):
        return action
    if review_range(inputs, action.step) is not None:
        return action
    why = (
        f"{STEP_LABEL}{action.step.id} is due a light review and no commit holds its work, "
        "in its series or since the step began"
    )
    return Stop("review-without-work", action.step.id, why)


def _human_stop(inputs: LoopInputs, selection: Next | Defects) -> Stop | None:
    if stop := _outstanding_stop(read_outstanding(inputs)):
        return stop
    if inputs.unnamed:
        return Stop(
            "unnamed-attempts", None, f"an Attempts: line names no step: {inputs.unnamed[0]}"
        )
    if isinstance(selection, Defects):
        found = selection.found
        why = "; ".join(
            f"{STEP_LABEL}{d.step} waits on {d.dependency}, which {_DEFECT_WORDS[d.kind]}"
            for d in found
        )
        return Stop("dependency-defect", found[0].step, why)
    return _snapshot_stop(inputs) or _marked_stop(inputs) or _step_stop(inputs, selection)


def _snapshot_stop(inputs: LoopInputs) -> Stop | None:
    """A disturbed commit stays a stop while its snapshot file is there: the person who reads
    the tree deletes the file to say they have, and the next call carries on."""
    for step in inputs.steps:
        records = inputs.driver_records(step.id)
        if records and records[-1].request in inputs.snapshots:
            last = records[-1]
            series = tuple(r for r in records if r.step_digest == step.digest)
            name = f"{SNAPSHOT_STEM}_{last.request}{SNAPSHOT_SUFFIX}"
            evidence = (
                f"{last.request} ended with `{last.test_result}`; the tree is saved in {name}"
            )
            return Stop("commit-disturbed-tree", step.id, evidence, series)
    return None


def _marked_stop(inputs: LoopInputs) -> Stop | None:
    """A blocked or conflict marker stops the loop while steps remain, even on a done step."""
    states = series_states(inputs)
    for step in inputs.steps:
        state = states.get(step.id)
        if isinstance(state, Marked):
            evidence = f"the latest return at {STEP_LABEL}{step.id} carried [{state.marker}]"
            if left := inputs.uncommitted.get(step.id):
                evidence += f"; uncommitted: {_some_files(left)}"
            return Stop(f"{state.marker.lower()}-marker", step.id, evidence, state.attempts)
    return None


def _some_files(files: tuple[str, ...]) -> str:
    """The first few names, and the count when there are more: a stop's text stays short."""
    shown = ", ".join(files[:UNCOMMITTED_SHOWN])
    return shown if len(files) <= UNCOMMITTED_SHOWN else f"{shown} ... ({len(files)} files)"


def _step_stop(inputs: LoopInputs, selection: Next) -> Stop | None:
    step, state = selection.step, selection.state
    where = f"{STEP_LABEL}{step.id}"
    if isinstance(state, Exhausted):
        return _spent_stop(inputs, step, state)
    if isinstance(state, HumanVerdict):
        evidence = state.evidence or f"the reconciler reads {where} {state.verdict}"
        if state.verdict == EXHAUSTED:
            return Stop("attempts-exhausted", step.id, evidence, (), evidence)
        return Stop("human-verdict", step.id, evidence)
    if isinstance(state, UnreadableField):
        evidence = f"{where}: the {state.field}: value cannot be read: {state.text}; {state.fix}"
        return Stop("unreadable-plan-field", step.id, evidence)
    if isinstance(state, NotDriven):
        return Stop("not-driven", step.id, f"{where} is assigned to {state.assignee}")
    globbed = [path for path in step.files if any(mark in path for mark in GLOB_MARKS)]
    if globbed:
        why = f"{where} names {', '.join(globbed)} in Files:, and the driver commits literal paths"
        return Stop("files-glob", step.id, why)
    if isinstance(state, Verified) and type(state.review) in _REVIEW_STOPS:
        cause, what = _REVIEW_STOPS[type(state.review)]
        return Stop(cause, step.id, f"{what} at {where}")
    return None


def _spent_stop(inputs: LoopInputs, step: PlanStep, state: Exhausted) -> Stop:
    """The stop of a spent bound: a goal step stalled (its last `STALL_RUN` iterations are the
    attempts shown), an ordinary step used its fresh attempts."""
    where = f"{STEP_LABEL}{step.id}"
    replan = getattr(inputs.attempts.get(step.id), "replan", None)
    if isinstance(state.bound, GoalBudget):
        evidence = f"the last {STALL_RUN} iterations at {where} kept nothing"
        return Stop("stalled", step.id, evidence, state.attempts[-STALL_RUN:], replan or evidence)
    cap = request_cap(state.bound)
    evidence = f"{cap} of {cap} fresh attempts at {where} ended unverified"
    return Stop("attempts-exhausted", step.id, evidence, state.attempts, replan or evidence)


def _budget_stop(inputs: LoopInputs, selection: Selection) -> Stop | None:
    used, budget = iterations_used(inputs), iteration_budget(inputs.steps)
    if used >= budget:
        return Stop(BUDGET_CAUSE, None, f"{used} of {budget} iterations used")
    return _goal_budget_stop(selection)


def _goal_budget_stop(selection: Selection) -> Stop | None:
    """A goal step that has used its own `Iterations:` unstalled and unverified: no request goes
    past the number its plan states, whatever budget the other steps of the plan leave over."""
    if not (isinstance(selection, Next) and isinstance(selection.state, Failed)):
        return None
    bound, used = selection.state.bound, spent(selection.state.attempts)
    if not (isinstance(bound, GoalBudget) and used >= bound.iterations):
        return None
    evidence = f"{used} of {bound.iterations} iterations used at {STEP_LABEL}{selection.step.id}"
    return Stop(BUDGET_CAUSE, None, evidence)


def _spawn(selection: Selection) -> Spawn:
    if not isinstance(selection, Next):
        raise ValueError("a spawn needs a selected step")
    step, state = selection.step, selection.state
    if isinstance(state, Fresh):
        return Spawn(step, RequestKey(step.id, 1, "implement", state.series))
    if isinstance(state, Failed):
        return Spawn(
            step, RequestKey(step.id, spent(state.attempts) + 1, "implement", state.series)
        )
    if isinstance(state, Running):  # the reading found it current, so its id parses
        return Spawn(step, cast(RequestKey, parse_request_id(state.request)), reissued=True)
    if isinstance(state, Verified) and isinstance(state.review, (Due, Requested, ReviseDue)):
        review = state.review
        kind: Kind = "revise" if isinstance(review, ReviseDue) else "review"
        key = RequestKey(step.id, state.n, kind, state.series, review.round)
        return Spawn(step, key, reissued=isinstance(review, Requested))
    raise ValueError(f"no request follows {type(state).__name__}")
