"""The pure state of the step-loop driver: where each step stands and which step is next.

Plan steps, WIP attempt readings, ledger records and reconciler verdicts arrive by value;
no file is opened and no clock is read, so unchanged inputs give the same answer. Their
`Step <id>` keys are re-keyed once, in `LoopInputs.read`, to the bare id a `PlanStep` carries.

Normative reading of a step's series -- first match wins:

1. Not driven, no admitted `Files:` entry, no `Check:`, WIP claims `COMPLETE`: done outside
   the loop, since nothing is left for a gate to judge.
2. Reconciler verdict `unknown` or `blocked`: a human verdict, whoever the assignee.
3. Not driven otherwise: done outside only with the claim AND `verified-complete` (a step that
   declares files can be credited a commit it never made); else not driven.
4. Driven, WIP names an unrecorded request: running. A driver that died between that
   write-ahead and its record leaves it so: `next` derives the same request id again and
   `record` refuses until the agent's end shows.
5. Driven with no driver record in any series: claimed and `verified-complete` is done outside,
   `attempts-exhausted` (a line written without the loop) a human verdict, else a fresh series.
6. Otherwise the series is the driver records whose `step_digest` equals the step's current
   digest, so revising the step block opens a fresh series and reverting it restores the old
   one. A `[BLOCKED]` or `[CONFLICT]` on its latest implement or revise return marks it; else
   a verified implement record verifies it; else the cap exhausts it; else it failed.

Selection is the first step in plan order not done whose `[depends-on]` steps are all done; a
`[parallel-group]` never makes a step wait for a sibling. When steps remain but none can
start, each stuck step is named with each dependency that holds it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Union

from _loop_fields import ATTEMPT_CAP, AnyAttempt, OutstandingAttempt
from _plan_steps import Implementer, PlanStep
from _step_loop_review import NotRequired, ReviewState, needs_review, review_state, satisfied

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

STEP_LABEL = "Step "
CLAIMED_COMPLETE = "COMPLETE"
VERIFIED = "verified-complete"
HUMAN_WORDS = ("unknown", "blocked")
EXHAUSTED = "attempts-exhausted"
WORK_KINDS = ("implement", "revise")  # the returns that carry a step's own work

_KIND_RE = re.compile(r"-(implement|revise|review)(?:-r\d+)?$")

Marker = Literal["BLOCKED", "CONFLICT"]
MARKED_STOPS: dict[str, Marker] = {"blocked": "BLOCKED", "conflict": "CONFLICT"}  # stop -> marker
DefectKind = Literal["missing", "cycle", "held"]


def bare_id(key: str) -> str:
    """The step id of a `Step <id>` key (a bare id passes through)."""
    return key[len(STEP_LABEL) :] if key.startswith(STEP_LABEL) else key


def request_kind(record: IterationRecord) -> str | None:
    """`implement`, `revise` or `review`, read off the record's request id (None: no request)."""
    found = _KIND_RE.search(record.request or "")
    return found[1] if found else None


@dataclass(frozen=True)
class LoopInputs:
    """Everything the state is derived from, keyed by bare step id and never mutated."""

    steps: tuple[PlanStep, ...]
    attempts: Mapping[str, AnyAttempt]
    records: tuple[IterationRecord, ...]
    verdicts: Mapping[str, Mapping[str, Any]]
    reviews: Mapping[str, str] = field(default_factory=dict)  # review file text by step id
    unnamed: tuple[str, ...] = ()  # `Attempts:` lines that name no step

    @classmethod
    def read(
        cls,
        steps: Iterable[PlanStep],
        attempts: Mapping[str, AnyAttempt],
        records: Iterable[IterationRecord],
        verdicts: Iterable[Mapping[str, Any]],
        reviews: Mapping[str, str] | None = None,
        unnamed: Iterable[str] = (),
    ) -> LoopInputs:
        """Parse the `Step <id>` keys of WIP, ledger and reconciler once, at the boundary."""
        return cls(
            tuple(steps),
            {bare_id(key): attempt for key, attempt in attempts.items()},
            tuple(records),
            {bare_id(verdict["step"]): verdict for verdict in verdicts},
            dict(reviews or {}),
            tuple(unnamed),
        )

    def driver_records(self, step_id: str) -> tuple[IterationRecord, ...]:
        """The step's ledger records that carry a request, in append order."""
        return tuple(
            r for r in self.records if bare_id(r.step) == step_id and r.request is not None
        )


@dataclass(frozen=True)
class Fresh:
    """No attempt in the current series (`series` is its index, 1 for the first)."""

    series: int

    def __post_init__(self) -> None:
        if self.series < 1:
            raise ValueError(f"a series index is at least 1, got {self.series}")


@dataclass(frozen=True)
class Running:
    """WIP names an implement request the ledger has not recorded."""

    n: int
    request: str
    series: int = 1


def spent(attempts: tuple[IterationRecord, ...]) -> int:
    """The highest attempt number among a series' implement records."""
    if not attempts:
        raise ValueError("a series with attempts holds at least one record")
    return max(record.attempt for record in attempts)


@dataclass(frozen=True)
class Failed:
    """The last recorded attempt did not verify and the cap is not reached."""

    series: int
    attempts: tuple[IterationRecord, ...]

    def __post_init__(self) -> None:
        if not 1 <= spent(self.attempts) < ATTEMPT_CAP:
            raise ValueError("a failed series is under the attempt cap")


@dataclass(frozen=True)
class Exhausted:
    """The cap is reached without verification."""

    attempts: tuple[IterationRecord, ...]

    def __post_init__(self) -> None:
        if spent(self.attempts) < ATTEMPT_CAP:
            raise ValueError("an exhausted series has reached the attempt cap")


@dataclass(frozen=True)
class Marked:
    """The latest work return of the series carried `[BLOCKED]` or `[CONFLICT]`."""

    marker: Marker
    attempts: tuple[IterationRecord, ...]


@dataclass(frozen=True)
class Verified:
    """The series holds a verified implement record (`n` is its attempt, `commit` may be None)."""

    n: int
    series: int
    commit: str | None
    review: ReviewState = NotRequired()


@dataclass(frozen=True)
class DoneOutside:
    """Done without the loop: nothing for the driver to run, spawn or gate."""


@dataclass(frozen=True)
class NotDriven:
    """Assigned outside the loop and not done."""

    assignee: str


@dataclass(frozen=True)
class HumanVerdict:
    """The reconciler's own verdict stands: a person decides."""

    verdict: str
    evidence: str


Series = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    Fresh, Running, Failed, Exhausted, Marked, Verified, DoneOutside, NotDriven, HumanVerdict
]


def is_done(state: Series) -> bool:
    """Done outside the loop, or verified by the driver with its light review satisfied.

    A marked series whose work verified is done too: the marker still stops the loop while
    other steps remain (completion outranks that stop only once every step is done).
    """
    if isinstance(state, Marked):
        return any(record.verdict == VERIFIED for record in state.attempts)
    return isinstance(state, DoneOutside) or (
        isinstance(state, Verified) and satisfied(state.review)
    )


def is_driven(step: PlanStep) -> bool:
    """Whether the loop runs the step (it is the implementer's)."""
    return isinstance(step.assignee, Implementer)


def step_series(step: PlanStep, inputs: LoopInputs) -> Series:
    """Where one step stands (see the module docstring for the order of the rules)."""
    verdict = inputs.verdicts.get(step.id, {})
    word, claimed = verdict.get("verdict"), verdict.get("wip_claim") == CLAIMED_COMPLETE
    driven = is_driven(step)
    if not driven and not step.files and step.check is None and claimed:
        return DoneOutside()
    if word in HUMAN_WORDS:
        return HumanVerdict(word, verdict.get("evidence", ""))
    if not driven:
        done = claimed and word == VERIFIED
        return DoneOutside() if done else NotDriven(getattr(step.assignee, "name", ""))
    attempt, own = inputs.attempts.get(step.id), inputs.driver_records(step.id)
    if isinstance(attempt, OutstandingAttempt):
        return Running(attempt.count, attempt.request, _series_index(own, step.digest))
    if not own:
        return _without_driver_record(word, claimed, verdict)
    return _series_of_records(step, own, inputs.reviews.get(step.id))


def _without_driver_record(word: str | None, claimed: bool, verdict: Mapping[str, Any]) -> Series:
    if claimed and word == VERIFIED:
        return DoneOutside()
    if word == EXHAUSTED:
        return HumanVerdict(word, verdict.get("evidence", ""))
    return Fresh(1)


def _series_index(own: tuple[IterationRecord, ...], digest: str) -> int:
    """The order of first appearance of the digest among the step's records, 1-based."""
    digests = list(dict.fromkeys(r.step_digest for r in own if r.step_digest))
    return digests.index(digest) + 1 if digest in digests else len(digests) + 1


def _series_of_records(
    step: PlanStep, own: tuple[IterationRecord, ...], review_text: str | None
) -> Series:
    index = _series_index(own, step.digest)
    current = tuple(r for r in own if r.step_digest == step.digest)
    implement = tuple(r for r in current if request_kind(r) == "implement")
    work = [r for r in current if request_kind(r) in WORK_KINDS]
    if not implement:
        return Fresh(index)
    if work[-1].stop_reason in MARKED_STOPS:
        return Marked(MARKED_STOPS[work[-1].stop_reason], implement)
    verified = [r for r in implement if r.verdict == VERIFIED]
    if verified:
        review = _review_of(step, current, review_text)
        return Verified(verified[-1].attempt, index, verified[-1].commit, review)
    if spent(implement) >= ATTEMPT_CAP:
        return Exhausted(implement)
    return Failed(index, implement)


def _review_of(
    step: PlanStep, current: tuple[IterationRecord, ...], review_text: str | None
) -> ReviewState:
    reviews = [r for r in current if request_kind(r) == "review"]
    revises = [r for r in current if request_kind(r) == "revise"]
    failed = bool(revises) and revises[-1].verdict != VERIFIED
    return review_state(needs_review(step), len(reviews), len(revises), failed, review_text)


def series_states(inputs: LoopInputs) -> dict[str, Series]:
    """Every step's series by bare id, in plan order."""
    return {step.id: step_series(step, inputs) for step in inputs.steps}


@dataclass(frozen=True)
class Next:
    """The step to act on now, with its series."""

    step: PlanStep
    state: Series


@dataclass(frozen=True)
class AllDone:
    """Every step is done."""


@dataclass(frozen=True)
class Defect:
    """A step that cannot start and the dependency that holds it.

    `missing`: the plan has no such step. `cycle`: the dependency leads back to the step.
    `held`: the dependency is itself stuck.
    """

    step: str
    dependency: str
    kind: DefectKind


@dataclass(frozen=True)
class Defects:
    """Steps remain and none can start; `found` names every holding dependency."""

    found: tuple[Defect, ...]


Selection = Union[Next, AllDone, Defects]  # noqa: UP007 -- runtime value, 3.9 floor


def select_step(inputs: LoopInputs) -> Selection:
    """The first step not done whose dependencies are all done."""
    states = series_states(inputs)
    done = {step_id for step_id, state in states.items() if is_done(state)}
    remaining = [step for step in inputs.steps if step.id not in done]
    for step in remaining:
        if all(dependency in done for dependency in step.depends_on):
            return Next(step, states[step.id])
    if not remaining:
        return AllDone()
    graph = {step.id: step.depends_on for step in inputs.steps}
    return Defects(
        tuple(
            Defect(step.id, dependency, _defect_kind(step.id, dependency, graph))
            for step in remaining
            for dependency in step.depends_on
            if dependency not in done
        )
    )


def _defect_kind(step_id: str, dependency: str, graph: Mapping[str, tuple[str, ...]]) -> DefectKind:
    if dependency not in graph:
        return "missing"
    return "cycle" if _leads_to(dependency, step_id, graph) else "held"


def _leads_to(start: str, target: str, graph: Mapping[str, tuple[str, ...]]) -> bool:
    """Whether `target` is reachable from `start` along dependencies."""
    seen: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(graph.get(current, ()))
    return False
