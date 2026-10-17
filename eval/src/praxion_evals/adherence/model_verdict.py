"""The flip rule's verdict value types: counts, intervals, per-check and per-role verdicts.

Split from :mod:`praxion_evals.adherence.model`, which serves every public name
here, so ``from praxion_evals.adherence.model import Assessed`` stays the import
path the scorer, the codecs and the report bind to. Nothing changes on the wire.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from praxion_evals.adherence.model import _frozen, _non_empty, _require


@dataclass(frozen=True)
class Interval:
    """The one-sided interval on the paired difference ``lean - full``, reported, never deciding."""

    lower: float
    upper: float


@dataclass(frozen=True)
class Counts:
    """A check's usable pairs after the worst-case recount, by what each arm did."""

    both_passed: int
    lean_failed_only: int  # b: full passed, lean failed
    lean_passed_only: int  # c: full failed, lean passed
    both_failed: int

    def __post_init__(self) -> None:
        _require(min(self.both_passed, self.b, self.c, self.both_failed) >= 0, "counts are >= 0")

    @property
    def b(self) -> int:
        return self.lean_failed_only

    @property
    def c(self) -> int:
        return self.lean_passed_only

    @property
    def discordant(self) -> int:
        return self.b + self.c

    @property
    def n(self) -> int:
        return self.both_passed + self.b + self.c + self.both_failed

    @property
    def passes_full(self) -> int:
        return self.both_passed + self.b

    @property
    def passes_lean(self) -> int:
        return self.both_passed + self.c

    @property
    def lean_failures(self) -> int:
        return self.b + self.both_failed


@dataclass(frozen=True)
class NoRegression:
    counts: Counts
    allowance: int


@dataclass(frozen=True)
class Regression:
    counts: Counts
    allowance: int


@dataclass(frozen=True)
class NonInferior:
    counts: Counts
    interval: Interval


@dataclass(frozen=True)
class Inferior:
    counts: Counts
    interval: Interval


CheckVerdict = NoRegression | Regression | NonInferior | Inferior
CLEARING_VERDICTS = (NoRegression, NonInferior)


@dataclass(frozen=True)
class Covered:
    """The flip claim speaks for this check."""


@dataclass(frozen=True)
class NotCovered:
    """The flip claim is silent on this check, and the report says why."""

    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a not-covered reason")


Coverage = Covered | NotCovered


@dataclass(frozen=True)
class Underpowered:
    """Fewer complete pairs than declared: counts only, and no flip verdict by construction."""

    reason: str
    complete_pairs: int
    required_pairs: int

    def __post_init__(self) -> None:
        _non_empty(self.reason, "an underpowered reason")
        _require(self.complete_pairs < self.required_pairs, "an underpowered role is short")


@dataclass(frozen=True)
class Assessed:
    complete_pairs: int
    check_verdicts: Mapping[str, CheckVerdict]
    not_covered: Mapping[str, str]  # check -> why the flip claim is silent on it
    worst_case_lean_failures: Mapping[str, int]

    def __post_init__(self) -> None:
        # A check keeps its arithmetic when only its claim is withheld (an allowance wider than
        # the margin); a failing verdict is evidence the claim cannot withhold.
        _require(
            all(
                isinstance(self.check_verdicts[name], CLEARING_VERDICTS)
                for name in self.not_covered
                if name in self.check_verdicts
            ),
            "a failing verdict is never withheld from the flip claim",
        )
        _frozen(self, "check_verdicts", self.check_verdicts)
        _frozen(self, "not_covered", self.not_covered)
        _frozen(self, "worst_case_lean_failures", self.worst_case_lean_failures)

    def coverage(self, check: str) -> Coverage:
        reason = self.not_covered.get(check)
        return Covered() if reason is None else NotCovered(reason)

    @property
    def flip(self) -> Literal["clear", "not clear"]:
        """Clear only when at least one covered check is scored and every scored check clears."""
        verdicts = self.check_verdicts.values()
        covered = [name for name in self.check_verdicts if name not in self.not_covered]
        return (
            "clear"
            if covered and all(isinstance(v, CLEARING_VERDICTS) for v in verdicts)
            else "not clear"
        )


RoleVerdict = Underpowered | Assessed
