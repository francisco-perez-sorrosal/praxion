"""A move's verdict: the shared flip rule over the move's pairs, and the floor's sensitivity figure.

The move takes the role's place in :func:`praxion_evals.adherence.verdict.role_verdict`: each
paired task becomes a ``model.Pair`` whose outcomes are the governed checks graded on final
state, so the verdict, its exact own-discordance allowances and its worst-case recount are the
shared rule's, unchanged. History and arrival timing are kept on the measurement for the report
and enter no pair, so they cannot gate. Floor sessions enter no pair and no allowance. A session
that left nothing to grade fails its pair (:func:`in_pair`), but on the floor it is counted apart
and enters neither the failures nor the rate.

The sensitivity figure asks whether the paired run could have seen the failure the floor shows:
the target pairs times the floor's failure rate minus the full arm's. It is exact ``Fraction``
arithmetic, compared unrounded against the check's allowance; the one-decimal form is only how
it is shown. It is information beside a verdict and changes none.

``Measurement.from_json`` is the one place the wire form becomes typed values.
Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, assert_never

from praxion_evals.adherence import verdict
from praxion_evals.adherence.model import (
    OWN_DISCORDANCE_EXACT,
    Assessed,
    CheckOutcome,
    Counts,
    DeclaredSettings,
    Errored,
    Failed,
    Measured,
    NoRegression,
    Pair,
    Passed,
    Regression,
    SessionStatus,
    Underpowered,
    _frozen,
    _non_empty,
    _require,
    verdict_label,
)
from praxion_evals.adherence.moves.model import (
    Arrival,
    Arrived,
    Channel,
    FinalState,
    FixtureKind,
    History,
    NeverArrived,
    NothingToGrade,
    Unknown,
)

CONFIDENCE = 0.95
ANY_COMPLETE_PAIR = 1  # the arithmetic shows from the first pair; clearing needs the target
UNREADABLE_SESSION = "the session errored"  # an errored side's detail; nothing reads it back
ERRORED_KIND = "exit_nonzero"
SHOWN_DECIMALS = 1
_SHOWN_SCALE = 10**SHOWN_DECIMALS
MOVE_RETRY_POLICY = "none: an errored session is an errored side of its pair"
FAILED_ON_FINAL_STATE = "the check failed on final state"
NOTHING_ON_FINAL_STATE = "the session left nothing to grade"


@dataclass(frozen=True)
class Side:
    """One arm's graded session: each governed check's final state, and what the report shows."""

    final: Mapping[str, FinalState]
    history: Mapping[str, History]
    arrivals: Mapping[str, Mapping[Channel, Arrival]]

    def __post_init__(self) -> None:
        _require(bool(self.final), "a graded session holds at least one final state")
        _frozen(self, "final", self.final)
        _frozen(self, "history", self.history)
        _frozen(self, "arrivals", self.arrivals)


@dataclass(frozen=True)
class MovePair:
    """One task's two sessions; ``None`` is a session that errored."""

    task_id: str
    fixture_kind: FixtureKind
    full: Side | None
    lean: Side | None

    def __post_init__(self) -> None:
        _non_empty(self.task_id, "a pair's task id")

    def as_pair(self) -> Pair:
        return Pair(
            task_id=self.task_id,
            template_id=self.fixture_kind,
            full=_status(self.full),
            lean=_status(self.lean),
        )


@dataclass(frozen=True)
class FloorTally:
    """A check's floor sessions: the failures out of the sessions that graded it, and apart from
    both, the sessions that left nothing to grade."""

    failures: int
    scored: int
    ungraded: int = 0

    @property
    def rate(self) -> Fraction:
        return Fraction(self.failures, self.scored)


@dataclass(frozen=True)
class Measurement:
    checks: tuple[str, ...]
    margin_pp: float
    target_pairs: int
    kind_restriction: FixtureKind | None
    pairs: tuple[MovePair, ...]
    floor: tuple[Side | None, ...]  # an errored floor session is None and counts nowhere

    def __post_init__(self) -> None:
        _require(bool(self.checks), "a measurement names at least one governed check")
        _require(len(set(self.checks)) == len(self.checks), "governed check names are distinct")
        _require(self.target_pairs >= 1, "the target is at least one pair")

    def floor_tally(self, check: str) -> FloorTally:
        outcomes = [
            session.final[check] for session in self.floor if session and check in session.final
        ]
        return FloorTally(
            failures=sum(isinstance(o, Failed) for o in outcomes),
            scored=sum(isinstance(o, Passed | Failed) for o in outcomes),
            ungraded=sum(isinstance(o, NothingToGrade) for o in outcomes),
        )

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Measurement:
        return cls(
            checks=tuple(data["checks"]),
            margin_pp=float(data["margin_pp"]),
            target_pairs=int(data["target_pairs"]),
            kind_restriction=_restriction(data["kind_restriction"]),
            pairs=tuple(_pair_from_json(p) for p in data["pairs"]),
            floor=tuple(_side_or_errored(s) for s in data["floor"]),
        )


@dataclass(frozen=True)
class MoveVerdict:
    """The verdict as plain mappings, so it serialises as it is.

    ``check_verdicts``, ``allowances``, ``discordant`` and ``counts`` hold the checks that have a
    usable pair; ``not_covered`` names why the flip claim is silent on a check, and ``cleared`` is
    ``None`` until the target's worth of complete pairs has run.
    """

    check_verdicts: dict[str, str]
    allowances: dict[str, int]
    discordant: dict[str, int]
    counts: dict[str, Counts]
    not_covered: dict[str, str]
    complete_pairs: int
    cleared: bool | None


def move_verdict(measurement: Measurement) -> MoveVerdict:
    """The shared flip rule over the move's pairs, each governed check on final state."""
    assessed = verdict.role_verdict(
        dict.fromkeys(measurement.checks, "mechanical"),
        [pair.as_pair() for pair in measurement.pairs],
        _settings(measurement),
    )
    match assessed:
        case Underpowered():
            return MoveVerdict({}, {}, {}, {}, {}, assessed.complete_pairs, None)
        case Assessed():
            return _move_verdict(assessed, measurement.target_pairs)
        case _:
            assert_never(assessed)


def _move_verdict(assessed: Assessed, target_pairs: int) -> MoveVerdict:
    held = assessed.check_verdicts
    reached_target = assessed.complete_pairs >= target_pairs
    return MoveVerdict(
        check_verdicts={name: verdict_label(v) for name, v in held.items()},
        allowances={
            name: v.allowance
            for name, v in held.items()
            if isinstance(v, NoRegression | Regression)
        },
        discordant={name: v.counts.discordant for name, v in held.items()},
        counts={name: v.counts for name, v in held.items()},
        not_covered=dict(assessed.not_covered),
        complete_pairs=assessed.complete_pairs,
        cleared=(assessed.flip == "clear") if reached_target else None,
    )


def _settings(measurement: Measurement) -> DeclaredSettings:
    return DeclaredSettings(
        margin_pp=measurement.margin_pp,
        method="tango-score",
        confidence=CONFIDENCE,
        sidedness="one-sided",
        required_pairs=ANY_COMPLETE_PAIR,
        pair_slack=0,
        retry_policy=MOVE_RETRY_POLICY,
        allowance_source=None,
        allowances={},
        allowance_method=OWN_DISCORDANCE_EXACT,
    )


# -- The sensitivity figure -------------------------------------------------------------------


@dataclass(frozen=True)
class Sensitivity:
    """What the paired target could see: it times the floor's failure rate less the full arm's."""

    figure: Fraction
    allowance: int

    @property
    def exceeds_allowance(self) -> bool:
        """Read on the unrounded figure: 2.02 exceeds an allowance of 2 though it shows as 2.0."""
        return self.figure > self.allowance

    @property
    def shown(self) -> str:
        return _one_decimal(self.figure)


def sensitivity(
    counts: Counts, floor: FloorTally, target_pairs: int, allowance: int
) -> Sensitivity | None:
    """The figure for one check, or ``None`` when no floor session scored it or no pair did."""
    if floor.scored == 0 or counts.n == 0:
        return None
    full_failures = counts.n - counts.passes_full
    full_rate = Fraction(full_failures, counts.n)
    return Sensitivity(target_pairs * (floor.rate - full_rate), allowance)


def _one_decimal(figure: Fraction) -> str:
    """Half away from zero, in exact arithmetic; a figure that rounds to zero shows unsigned."""
    tenths = int(abs(figure) * _SHOWN_SCALE + Fraction(1, 2))
    sign = "-" if figure < 0 and tenths else ""
    whole, decimals = divmod(tenths, _SHOWN_SCALE)
    return f"{sign}{whole}.{decimals:0{SHOWN_DECIMALS}d}"


# -- Wire form to typed values ----------------------------------------------------------------


def in_pair(final: FinalState) -> Passed | Failed:
    """How a pair reads a final state: nothing left to grade fails, since the arm left the task
    the check governs undone."""
    match final:
        case NothingToGrade(reason=reason):
            return Failed(reason)
        case Passed() | Failed():
            return final
        case _:
            assert_never(final)


def _status(side: Side | None) -> SessionStatus:
    if side is None:
        return Errored(ERRORED_KIND, UNREADABLE_SESSION)
    outcomes: dict[str, CheckOutcome] = {name: in_pair(f) for name, f in side.final.items()}
    return Measured(outcomes, None)


def _pair_from_json(data: Mapping[str, Any]) -> MovePair:
    return MovePair(
        task_id=data["task_id"],
        fixture_kind=_fixture_kind(data["fixture_kind"]),
        full=_side_or_errored(data["full"]),
        lean=_side_or_errored(data["lean"]),
    )


def _restriction(word: str | None) -> FixtureKind | None:
    return None if word is None else _fixture_kind(word)


def _side_or_errored(data: Mapping[str, Any] | None) -> Side | None:
    return None if data is None else _side_from_json(data)


def _side_from_json(data: Mapping[str, Any]) -> Side:
    return Side(
        final={check: _final(word) for check, word in data["final"].items()},
        history={check: _history(word) for check, word in data.get("history", {}).items()},
        arrivals={
            check: {_channel(name): _arrival(word) for name, word in arrived.items()}
            for check, arrived in data.get("arrivals", {}).items()
        },
    )


def _final(word: str) -> FinalState:
    match word:
        case "passed":
            return Passed()
        case "failed":
            return Failed(FAILED_ON_FINAL_STATE)
        case "nothing_to_grade":
            return NothingToGrade(NOTHING_ON_FINAL_STATE)
        case _:
            raise ValueError(f"a final state is passed, failed or nothing_to_grade, got {word!r}")


def _fixture_kind(word: str) -> FixtureKind:
    match word:
        case "managed" | "unmanaged":
            return word
        case _:
            raise ValueError(f"a fixture kind is managed or unmanaged, got {word!r}")


def _channel(word: str) -> Channel:
    match word:
        case "session_start" | "path_matched" | "hook_context" | "gate_refusal" | "project_gating":
            return word
        case _:
            raise ValueError(f"unknown delivery channel {word!r}")


def _history(word: str) -> History:
    """The model's names, or the specification's words (spaces, and 'action never taken')."""
    match word.replace(" ", "_"):
        case "right_first_time":
            return "right_first_time"
        case "repaired":
            return "repaired"
        case "not_repaired":
            return "not_repaired"
        case "never_taken" | "action_never_taken":
            return "never_taken"
        case _:
            raise ValueError(f"unknown history outcome {word!r}")


def _arrival(word: str) -> Arrival:
    match word:
        case "before composition" | "before execution" | "after execution":
            return Arrived(word)
        case "never":
            return NeverArrived()
        case "unknown":
            return Unknown()
        case _:
            raise ValueError(f"unknown arrival timing {word!r}")
