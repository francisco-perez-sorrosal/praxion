"""Paired verdicts: the ratified flip rule as pure arithmetic over recorded pairs.

A role's two arms ran the same tasks, so each task yields one pair. The rule:

- a pair whose ``lean`` side alone errored counts as a ``lean`` failure on each
  check its ``full`` side scored (the worst-case recount), so an infrastructure
  error caused by the lean arm cannot hide a regression; an error on the
  ``full`` side or on both leaves the pair incomplete;
- a mechanical check regresses when ``lean`` fails it on more pairs than
  ``full`` does, beyond that check's declared noise allowance (zero when none);
- a judged check is non-inferior when the ``lean`` pass rate is no more than the
  declared margin below the ``full`` one, a point-estimate rule; the one-sided
  Tango score interval on the paired difference is reported beside it and never
  decides;
- a role with fewer complete pairs than declared is underpowered and gets no
  flip verdict; otherwise the flip is clear only when every scored check
  clears, and withheld or not-applicable checks are listed as not covered.

Pure: no I/O, no clock, no randomness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import comb, inf, sqrt
from statistics import NormalDist
from typing import assert_never

from praxion_evals.adherence.model import (
    Assessed,
    CheckErrored,
    CheckKind,
    CheckVerdict,
    Counts,
    DeclaredSettings,
    Errored,
    Inferior,
    Interval,
    Measured,
    NonInferior,
    NoRegression,
    NotApplicable,
    Pair,
    Regression,
    RoleVerdict,
    SessionStatus,
    Underpowered,
    Withheld,
    scored,
)

BISECTION_STEPS = 80
PERCENT = 100
PARAMETER_FLOOR = -1.0  # the paired difference of two proportions lies in [-1, 1]
PARAMETER_CEILING = 1.0


def role_verdict(
    checks: Mapping[str, CheckKind], pairs: Sequence[Pair], settings: DeclaredSettings
) -> RoleVerdict:
    """The flip verdict for one role, from its checks (name -> kind) and its pairs."""
    complete = sum(pair.complete for pair in pairs)
    if complete < settings.required_pairs:
        return Underpowered(
            f"{complete} complete pairs, fewer than the {settings.required_pairs} declared",
            complete,
            settings.required_pairs,
        )
    recounted = [pair for pair in pairs if _countable(pair)]
    verdicts: dict[str, CheckVerdict] = {}
    not_covered: dict[str, str] = {}
    lean_failures: dict[str, int] = {}
    for name, kind in checks.items():
        counts = tally(name, recounted)
        if counts.n == 0:
            not_covered[name] = _why_not_covered(name, recounted)
            continue
        lean_failures[name] = counts.lean_failures
        verdicts[name] = _decide(name, kind, counts, settings)
    return Assessed(complete, verdicts, not_covered, lean_failures)


def tally(check: str, pairs: Sequence[Pair]) -> Counts:
    """A check's usable pairs after the worst-case recount, by what each arm did."""
    both_passed = lean_failed_only = lean_passed_only = both_failed = 0
    for pair in pairs:
        full, lean = _sides(pair, check)
        if full is None or lean is None:
            continue
        both_passed += full and lean
        lean_failed_only += full and not lean
        lean_passed_only += lean and not full
        both_failed += not full and not lean
    return Counts(both_passed, lean_failed_only, lean_passed_only, both_failed)


def _countable(pair: Pair) -> bool:
    """Complete, or lean-errored with a measured full side (the recount's extra pairs)."""
    return pair.complete or (isinstance(pair.full, Measured) and isinstance(pair.lean, Errored))


def _sides(pair: Pair, check: str) -> tuple[bool | None, bool | None]:
    """Whether each arm passed the check; None when that side did not score it."""
    full = _score(pair.full, check)
    if isinstance(pair.lean, Errored):
        return full, (False if full is not None else None)
    return full, _score(pair.lean, check)


def _score(status: SessionStatus, check: str) -> bool | None:
    if not isinstance(status, Measured) or check not in status.outcomes:
        return None
    return scored(status.outcomes[check])


def _why_not_covered(check: str, pairs: Sequence[Pair]) -> str:
    reasons: list[str] = []
    for pair in pairs:
        for status in (pair.full, pair.lean):
            reason = _unscored_reason(status, check)
            if reason is not None and reason not in reasons:
                reasons.append(reason)
    return "; ".join(reasons) or "no pair scored this check"


def _unscored_reason(status: SessionStatus, check: str) -> str | None:
    if not isinstance(status, Measured) or check not in status.outcomes:
        return None
    outcome = status.outcomes[check]
    if isinstance(outcome, Withheld | NotApplicable | CheckErrored):
        return outcome.reason
    return None


def _decide(name: str, kind: CheckKind, counts: Counts, settings: DeclaredSettings) -> CheckVerdict:
    match kind:
        case "mechanical":
            allowance = settings.allowance(name)
            if counts.b - counts.c > allowance:
                return Regression(counts, allowance)
            return NoRegression(counts, allowance)
        case "judged":
            interval = tango_interval(counts, settings.confidence)
            shortfall = PERCENT * (counts.passes_lean - counts.passes_full)
            if shortfall >= -settings.margin_pp * counts.n:
                return NonInferior(counts, interval)
            return Inferior(counts, interval)
        case _:
            assert_never(kind)


# ---------------------------------------------------------------------------
# Tango's score interval for a paired difference
# ---------------------------------------------------------------------------


def tango_interval(counts: Counts, confidence: float) -> Interval:
    """One-sided lower bound on ``p_lean - p_full`` at ``confidence``; the upper limit is 1.

    The bound is the difference under which the score statistic, evaluated at
    the restricted maximum-likelihood estimate of the discordant cells, just
    reaches the normal quantile. Unlike the Wald interval it keeps its width at
    zero discordance, where it equals ``-z^2 / (n + z^2)``.
    """
    b, c, n = counts.b, counts.c, counts.n
    point = (c - b) / n
    critical = NormalDist().inv_cdf(confidence)
    below, above = PARAMETER_FLOOR, point
    for _ in range(BISECTION_STEPS):
        middle = (below + above) / 2
        if _score_statistic(b, c, n, middle) > critical:
            below = middle
        else:
            above = middle
    return Interval(lower=(below + above) / 2, upper=PARAMETER_CEILING)


def _score_statistic(b: int, c: int, n: int, delta: float) -> float:
    """Standardised ``(c - b) - n * delta`` under the null of difference ``delta``."""
    shift = (b + c) - delta * (2 * n + b - c)
    root = sqrt(max(shift * shift + 8 * n * b * delta * (1 - delta), 0.0))
    lean_failed_only = (shift + root) / (4 * n)  # restricted MLE of the b cell
    variance_per_pair = 2 * lean_failed_only + delta * (1 - delta)
    excess = c - b - n * delta
    if variance_per_pair <= 0:
        return inf if excess > 0 else 0.0
    return excess / sqrt(n * variance_per_pair)


# ---------------------------------------------------------------------------
# Noise allowances from a same-arm calibration run
# ---------------------------------------------------------------------------


def allowances_from_calibration(pairs: Sequence[Pair], confidence: float) -> dict[str, int]:
    """Each check's allowance: the smallest ``k >= 0`` that same-arm noise stays under.

    ``pairs`` are one arm run twice on the same tasks (the second run in the
    ``lean`` slot). For a check with ``d`` discordant pairs, ``b - c`` is
    ``2 * Binomial(d, 1/2) - d`` when the two runs are exchangeable, and the
    allowance is the smallest ``k`` with ``P(b - c <= k) >= confidence``. A
    check with no discordance gets zero. Only mechanical checks use it; the
    caller keeps those.
    """
    names = sorted({name for pair in pairs for name in _measured_names(pair)})
    discordant = {name: tally(name, [p for p in pairs if p.complete]) for name in names}
    return {
        name: _exact_quantile(counts.b + counts.c, confidence)
        for name, counts in discordant.items()
    }


def _measured_names(pair: Pair) -> set[str]:
    return {
        name
        for status in (pair.full, pair.lean)
        if isinstance(status, Measured)
        for name in status.outcomes
    }


def _exact_quantile(discordant: int, confidence: float) -> int:
    for allowance in range(discordant + 1):
        at_most = (discordant + allowance) // 2
        mass = sum(comb(discordant, i) for i in range(at_most + 1))
        if mass >= confidence * 2**discordant:
            return allowance
    return discordant
