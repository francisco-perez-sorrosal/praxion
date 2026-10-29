"""The move run's infrastructure stop: the role stop's rule, folded over a move's three arms.

A move's sessions fail the way a role's do, so the declared rule, the redacted tail and the
masking are the role's own (``infra_stop``). What differs is the subject: a move's arms are
``full``, ``lean`` and ``floor`` and its sessions carry no role. The streak is the same value,
the trailing run of equal failures among one arm's sessions, taken by ``infra_stop.trailing_streak``
so the two folds cannot drift; the other arm's sessions launched between them neither break nor
extend it, and a retry is simply the arm's next session.

Continuability follows the role's rule for a paired run (a stop is an outage only when the other
arm failed alike inside the streak's window) and stands on its own for a floor run, which has no
other arm to agree with: its stop is continuable on its own streak.

A session counts toward a streak only when it errored in one of the rule's counting kinds. A
session that ran, one its own spend budget stopped, or one that errored outside the counting
kinds is no failure and ends its arm's streak, a floor session included.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from praxion_evals.adherence import infra_stop
from praxion_evals.adherence.infra_stop import Continue, EvidenceTail, Failure, StopRule
from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.moves.model import MoveArm

Scope = Literal["both-arms", "one-arm"]


@dataclass(frozen=True)
class Launched:
    """A session as the stop reason names it: a task's first session in an arm is attempt 1,
    its retry attempt 2."""

    task_id: str
    arm: MoveArm
    attempt: int


@dataclass(frozen=True)
class Seen:
    """One recorded session; ``failure`` is ``None`` unless the session counted."""

    session: Launched
    failure: Failure | None


@dataclass(frozen=True)
class MoveFold:
    """Every session recorded so far, in order; a streak is derived from it, never stored."""

    seen: tuple[Seen, ...] = ()


@dataclass(frozen=True)
class MoveStopReason:
    """Why the run stopped itself. ``scope`` is ``both-arms`` when another arm failed the same way
    inside the streak's window; only a paired run has another arm to do so."""

    kind: str
    masked_tail: str
    arm: MoveArm
    sessions: tuple[Launched, ...]
    scope: Scope

    @property
    def continuable(self) -> bool:
        """A paired stop seen in both arms is an outage; a floor stop is one arm's own streak."""
        return self.arm == "floor" or self.scope == "both-arms"


@dataclass(frozen=True)
class MoveStop:
    reason: MoveStopReason


Decision = Continue | MoveStop


def step(
    rule: StopRule, state: MoveFold, task_id: str, arm: MoveArm, error: Errored | None
) -> tuple[MoveFold, Decision]:
    """Fold one session into ``state``; ``error`` is how it errored, ``None`` when it ran."""
    seen = Seen(Launched(task_id, arm, _attempt(state, task_id, arm)), failure_of(rule, error))
    state = MoveFold((*state.seen, seen))
    if seen.failure is None:
        return state, Continue()
    streak = _streak(state, arm, seen.failure)
    if len(streak) < rule.count:
        return state, Continue()
    return state, MoveStop(_reason(state, arm, seen.failure, streak))


def failure_of(rule: StopRule, error: Errored | None) -> Failure | None:
    """What makes this session the same failure as another, or ``None`` when it counts for none."""
    if error is None or error.kind not in rule.kinds:
        return None
    # The role fold's private budget-stop test, shared so both folds keep one definition of it.
    if infra_stop._BUDGET_STOPPED.search(error.detail):
        return None
    # A record written before tails were kept has none: its kind alone makes it the same.
    return Failure(error.kind, (error.tails or EvidenceTail("", "")).masked())


def _attempt(state: MoveFold, task_id: str, arm: MoveArm) -> int:
    earlier = sum(1 for s in state.seen if (s.session.task_id, s.session.arm) == (task_id, arm))
    return earlier + 1


def _streak(state: MoveFold, arm: MoveArm, failure: Failure) -> tuple[tuple[int, Seen], ...]:
    """The trailing run of ``failure`` among ``arm``'s sessions, as (position, session)."""
    mine = [(i, s) for i, s in enumerate(state.seen) if s.session.arm == arm]
    length = infra_stop.trailing_streak([s.failure for _, s in mine], failure)
    return tuple(mine[len(mine) - length :])


def _reason(
    state: MoveFold, arm: MoveArm, failure: Failure, streak: tuple[tuple[int, Seen], ...]
) -> MoveStopReason:
    first, last = streak[0][0], streak[-1][0]
    other_arm_failed_alike = any(
        s.session.arm != arm and s.failure == failure for s in state.seen[first : last + 1]
    )
    return MoveStopReason(
        failure.kind,
        failure.masked_tail,
        arm,
        tuple(s.session for _, s in streak),
        "both-arms" if other_arm_failed_alike else "one-arm",
    )
