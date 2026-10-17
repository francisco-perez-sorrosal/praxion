"""The run's infrastructure stop: what an errored session keeps, when two failures are the same,
and the rule that ends a run on a repeated one.

A dead credential or a broken channel errors every session the same way, so spending on after
the third identical failure buys nothing. The stop reads only what the failure left behind (its
kind and its evidence tail) and never a graded outcome, an arm's standing or a verdict.

Four values carry the design:

- ``EvidenceTail`` is the redacted, bounded end of a session's two output streams. Its only
  constructor redacts before it clips, so a clip can never cut a secret in half and leave its
  prefix behind.
- ``mask`` makes two tails equal when they differ only in volatile tokens (ids, timestamps,
  durations, byte counts); anything else keeps them apart.
- ``StopRule`` is the declared count, counting kinds and bound, refused at ``parse`` when it
  could stop a run on one task's session and its retry, or count a failure that is not
  infrastructure.
- ``step`` folds one session record at a time into the run's ``FoldState`` and answers
  ``Continue`` or ``Stop(StopReason)``. The state is just what was seen, in order: a streak is
  the trailing run of equal failures of one arm, derived rather than stored, so it cannot
  disagree with the record it summarises.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import takewhile
from typing import Literal

from praxion_evals.adherence.model import Arm, Errored, Role, SessionRecord

# ---------------------------------------------------------------------------
# The declared rule
# ---------------------------------------------------------------------------

# The kinds that mean "the session could not run as launched". Everything else (an isolation
# breach, a refused launch, an evaluation exception, a spent budget) is about the eval or the
# task, not the channel, and never counts.
COUNTING_KINDS: frozenset[str] = frozenset(
    {
        "timeout",
        "exit_nonzero",
        "no_result_event",
        "envelope_unparseable",
        "result_error",
        "kernel_missing",
    }
)
# One task's session and its retry are two sessions of one arm; three always span two tasks.
MIN_STOP_COUNT = 3
DEFAULT_STOP_COUNT = 3
MASKING_RULE = "v1"


@dataclass(frozen=True)
class StopRule:
    """The declared settings of the stop, written to the results file before the first launch."""

    count: int
    kinds: frozenset[str]
    tail_chars: int
    masking: Literal["v1"] = MASKING_RULE

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or self.count < MIN_STOP_COUNT:
            raise ValueError(
                f"the stop count must be at least {MIN_STOP_COUNT} so that one task's session "
                f"and its retry can never stop a run, got {self.count!r}"
            )
        if isinstance(self.tail_chars, bool) or self.tail_chars <= 0:
            raise ValueError(f"the tail bound must be positive, got {self.tail_chars!r}")
        if not self.kinds:
            raise ValueError("the stop counts at least one error kind")
        outside = sorted(self.kinds - COUNTING_KINDS)
        if outside:
            raise ValueError(
                f"{outside} cannot count toward the stop; the counting kinds are "
                f"{sorted(COUNTING_KINDS)}"
            )
        if self.masking != MASKING_RULE:
            raise ValueError(f"the masking rule is {MASKING_RULE!r}, got {self.masking!r}")

    @classmethod
    def parse(cls, count: int, kinds: Iterable[str], tail_chars: int) -> StopRule:
        return cls(count, frozenset(kinds), tail_chars)


# ---------------------------------------------------------------------------
# What an errored session keeps
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"
_API_KEY = re.compile(r"sk-ant-[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class EvidenceTail:
    """The last ``bound`` characters of a session's error output and of its result text, with
    every secret redacted. An empty stream is ``""``, never omitted."""

    error_tail: str
    result_tail: str

    @classmethod
    def capture(
        cls, raw_error: str, raw_result: str, bound: int, secrets: Iterable[str]
    ) -> EvidenceTail:
        if bound <= 0:
            raise ValueError(f"the tail bound must be positive, got {bound!r}")
        # Longest first, so a secret that contains another is redacted whole.
        needles = sorted({s for s in secrets if s}, key=len, reverse=True)
        return cls(
            _redact(raw_error, needles)[-bound:],
            _redact(raw_result, needles)[-bound:],
        )

    def masked(self) -> str:
        """The tail as two sessions are compared: the streams masked, kept in their own halves."""
        return f"{mask(self.error_tail)}\n{mask(self.result_tail)}"


def _redact(text: str, needles: Iterable[str]) -> str:
    for needle in needles:
        text = text.replace(needle, REDACTED)
    return _API_KEY.sub(REDACTED, text)


# ---------------------------------------------------------------------------
# When two tails are the same
# ---------------------------------------------------------------------------

# Order matters: a UUID is one token before its groups are hexadecimal ids, and a timestamp is
# one token before its digits are anything else.
_MASKS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), placeholder)
    for pattern, placeholder in (
        (
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
            "<uuid>",
        ),
        (
            r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}(?::?\d{2})?)?",
            "<timestamp>",
        ),
        (r"\breq_[A-Za-z0-9]+", "<request-id>"),
        (r"\b\d+(?:\.\d+)?ms\b", "<duration>"),
        (r"\b\d+ bytes\b", "<bytes>"),
        (r"\b[0-9a-fA-F]{8,}\b", "<hex-id>"),
    )
)


def mask(text: str) -> str:
    """``text`` with every volatile token replaced by a fixed placeholder."""
    for pattern, placeholder in _MASKS:
        text = pattern.sub(placeholder, text)
    return text


# ---------------------------------------------------------------------------
# The fold: one session record at a time
# ---------------------------------------------------------------------------

Scope = Literal["both-arms", "one-arm"]


@dataclass(frozen=True)
class Launched:
    """A session as the stop reason names it: a task's first session in an arm is attempt 1,
    its retry attempt 2."""

    task_id: str
    arm: Arm
    attempt: int


@dataclass(frozen=True)
class Failure:
    """What makes two failures the same: the kind and the masked evidence."""

    kind: str
    masked_tail: str


@dataclass(frozen=True)
class Seen:
    """One recorded session; ``failure`` is ``None`` unless the session counted."""

    role: Role
    session: Launched
    failure: Failure | None


@dataclass(frozen=True)
class FoldState:
    """Every session recorded so far, in order. A role's arm has a streak only as the trailing
    run of equal failures among that arm's sessions; nothing else is stored."""

    seen: tuple[Seen, ...] = ()


@dataclass(frozen=True)
class StopReason:
    """Why the run stopped itself. ``scope`` is ``both-arms`` when the role's other arm failed
    the same way inside the streak's window, which alone makes the stop continuable."""

    kind: str
    masked_tail: str
    role: Role
    arm: Arm
    sessions: tuple[Launched, ...]
    scope: Scope


@dataclass(frozen=True)
class Continue:
    pass


@dataclass(frozen=True)
class Stop:
    reason: StopReason


Decision = Continue | Stop


def step(
    rule: StopRule,
    state: FoldState,
    record: SessionRecord,
    tails: EvidenceTail | None = None,
) -> tuple[FoldState, Decision]:
    """Fold ``record`` into ``state``. An errored record's evidence is its own ``tails``;
    ``tails`` given here stands in for them.

    A counting failure extends its arm's streak when it matches the streak's kind and masked
    tail and starts a new one otherwise; any other record of the arm (one that ran, one that
    errored outside the counting kinds) ends it. A retry is simply the arm's next session.
    """
    setup = record.setup
    seen = Seen(
        setup.role,
        Launched(setup.task_id, setup.arm, _attempt(state, record)),
        _failure(rule, record, tails),
    )
    state = FoldState((*state.seen, seen))
    if seen.failure is None:
        return state, Continue()
    streak = _streak(state, seen.role, setup.arm, seen.failure)
    if len(streak) < rule.count:
        return state, Continue()
    return state, Stop(_stop_reason(state, seen.role, setup.arm, seen.failure, streak))


def _attempt(state: FoldState, record: SessionRecord) -> int:
    setup = record.setup
    earlier = sum(
        1
        for s in state.seen
        if (s.role, s.session.task_id, s.session.arm) == (setup.role, setup.task_id, setup.arm)
    )
    return earlier + 1


def _failure(rule: StopRule, record: SessionRecord, tails: EvidenceTail | None) -> Failure | None:
    status = record.status
    if not (isinstance(status, Errored) and status.kind in rule.kinds):
        return None
    # A record written before tails were kept has none: its kind alone makes it the same.
    return Failure(status.kind, (tails or status.tails or EvidenceTail("", "")).masked())


def _streak(
    state: FoldState, role: Role, arm: Arm, failure: Failure
) -> tuple[tuple[int, Seen], ...]:
    """The trailing run of ``failure`` among ``arm``'s sessions, as (position, session)."""
    mine = [(i, s) for i, s in enumerate(state.seen) if s.role == role and s.session.arm == arm]
    run = takewhile(lambda item: item[1].failure == failure, reversed(mine))
    return tuple(reversed(list(run)))


def _stop_reason(
    state: FoldState, role: Role, arm: Arm, failure: Failure, streak: tuple[tuple[int, Seen], ...]
) -> StopReason:
    first, last = streak[0][0], streak[-1][0]
    other_arm_failed_alike = any(
        s.role == role and s.session.arm != arm and s.failure == failure
        for s in state.seen[first : last + 1]
    )
    return StopReason(
        failure.kind,
        failure.masked_tail,
        role,
        arm,
        tuple(s.session for _, s in streak),
        "both-arms" if other_arm_failed_alike else "one-arm",
    )
