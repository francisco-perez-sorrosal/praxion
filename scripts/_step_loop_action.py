"""The pure decision of the step-loop driver: spawn a request, complete, or stop.

Everything arrives through `LoopInputs` and nothing is read or written here, so a stop that
holds while its evidence holds is simply re-derived by the next call, and it clears when the
evidence changes: a plan revision clears an exhausted or marked step (a fresh series), a
review file reading `accept` clears the review stops, a step done outside the loop clears a
hand-back, and a changed reconciler verdict clears a human verdict.

Normative precedence, a total function of the inputs, first match wins:

1. `Complete` when every step is done.
2. A human stop, in this order: `loop-state-defect` (more than one outstanding request),
   `unnamed-attempts`, `dependency-defect`, then the stop of the selected step, which is the
   earliest step in plan order that is not done.
3. `iteration-budget` when the iterations used have reached the budget.
4. A `Spawn` for the selected step.

The budget is derived from the plan alone, so a plan revision opens a new series without
growing it. `commit-disturbed-tree` is a cause only the commit adapter raises.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

from _loop_fields import ATTEMPT_CAP, OutstandingAttempt
from _plan_steps import PlanStep
from _step_loop_render import Kind, RequestKey
from _step_loop_review import (
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
    Verified,
    is_driven,
    select_step,
    spent,
)

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

BUDGET_CAUSE = "iteration-budget"
HUMAN_CAUSES = tuple(
    """attempts-exhausted blocked-marker conflict-marker human-verdict unnamed-attempts
    review-revised-twice review-unfinished revision-failed not-driven dependency-defect
    commit-disturbed-tree loop-state-defect""".split()
)
NULL_STEP_CAUSES = ("unnamed-attempts", "loop-state-defect", BUDGET_CAUSE)
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
    replan request exists exactly for an exhausted step."""

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
        if (self.replan_request is not None) != (self.cause == "attempts-exhausted"):
            raise ValueError("a replan request goes with attempts-exhausted and nothing else")


Action = Union[Spawn, Complete, Stop]  # noqa: UP007 -- runtime value, 3.9 floor


def iteration_budget(steps: Iterable[PlanStep]) -> int:
    """The cap for each driven step, plus one review for each the trigger marks."""
    return sum(ATTEMPT_CAP + needs_review(step) for step in steps if is_driven(step))


def iterations_used(inputs: LoopInputs) -> int:
    """The ledger records that carry a request: every request that started an agent."""
    return sum(record.request is not None for record in inputs.records)


def next_action(inputs: LoopInputs) -> Action:
    """The one thing the loop does next."""
    selection = select_step(inputs)
    if isinstance(selection, AllDone):
        return Complete()
    return _human_stop(inputs, selection) or _budget_stop(inputs) or _spawn(selection)


def _human_stop(inputs: LoopInputs, selection: Next | Defects) -> Stop | None:
    outstanding = sorted(s for s, a in inputs.attempts.items() if isinstance(a, OutstandingAttempt))
    if len(outstanding) > 1:
        named = ", ".join(f"{STEP_LABEL}{step}" for step in outstanding)
        return Stop("loop-state-defect", None, f"WIP.md names an outstanding request on {named}")
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
    return _step_stop(inputs, selection)


def _step_stop(inputs: LoopInputs, selection: Next) -> Stop | None:
    step, state = selection.step, selection.state
    where = f"{STEP_LABEL}{step.id}"
    if isinstance(state, Exhausted):
        evidence = f"{ATTEMPT_CAP} of {ATTEMPT_CAP} fresh attempts at {where} ended unverified"
        replan = getattr(inputs.attempts.get(step.id), "replan", None) or evidence
        return Stop("attempts-exhausted", step.id, evidence, state.attempts, replan)
    if isinstance(state, Marked):
        cause = f"{state.marker.lower()}-marker"
        return Stop(
            cause, step.id, f"the latest return at {where} carried [{state.marker}]", state.attempts
        )
    if isinstance(state, HumanVerdict):
        evidence = state.evidence or f"the reconciler reads {where} {state.verdict}"
        if state.verdict == EXHAUSTED:
            return Stop("attempts-exhausted", step.id, evidence, (), evidence)
        return Stop("human-verdict", step.id, evidence)
    if isinstance(state, NotDriven):
        return Stop("not-driven", step.id, f"{where} is assigned to {state.assignee}")
    if isinstance(state, Running) and _running_key(step, state).id != state.request:
        return Stop("loop-state-defect", None, f"WIP.md names {state.request}, not the series' own")
    if isinstance(state, Verified) and type(state.review) in _REVIEW_STOPS:
        cause, what = _REVIEW_STOPS[type(state.review)]
        return Stop(cause, step.id, f"{what} at {where}")
    return None


def _budget_stop(inputs: LoopInputs) -> Stop | None:
    used, budget = iterations_used(inputs), iteration_budget(inputs.steps)
    return (
        Stop(BUDGET_CAUSE, None, f"{used} of {budget} iterations used") if used >= budget else None
    )


def _running_key(step: PlanStep, state: Running) -> RequestKey:
    return RequestKey(step.id, state.n, "implement", state.series)


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
    if isinstance(state, Running):
        return Spawn(step, _running_key(step, state), reissued=True)
    if isinstance(state, Verified) and isinstance(state.review, (Due, Requested, ReviseDue)):
        review = state.review
        kind: Kind = "revise" if isinstance(review, ReviseDue) else "review"
        key = RequestKey(step.id, state.n, kind, state.series, review.round)
        return Spawn(step, key, reissued=isinstance(review, Requested))
    raise ValueError(f"no request follows {type(state).__name__}")
