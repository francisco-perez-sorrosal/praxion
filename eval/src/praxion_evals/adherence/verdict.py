"""Paired verdicts: the ratified flip rule as pure arithmetic over recorded pairs.

A role's two arms ran the same tasks, so each task yields one pair. The rule:

- a pair whose ``lean`` side alone errored counts as a ``lean`` failure on each
  check its ``full`` side scored (the worst-case recount), so an infrastructure
  error caused by the lean arm cannot hide a regression; an error on the
  ``full`` side or on both leaves the pair incomplete;
- a mechanical check regresses when ``lean`` fails it on more pairs than
  ``full`` does, beyond its noise allowance: the exact one-sided quantile of its own
  discordant count when the settings declare that method, else the declared allowance
  (zero when none);
- a judged check is non-inferior when the ``lean`` pass rate is no more than the
  declared margin below the ``full`` one, a point-estimate rule; the one-sided
  Tango score interval on the paired difference is reported beside it and never
  decides;
- a role with fewer complete pairs than declared is underpowered and gets no
  flip verdict; otherwise the flip is clear only when every scored check
  clears, and withheld or not-applicable checks are listed as not covered;
- under the own-discordance method, a mechanical check whose allowance is wider than the
  margin times its usable pairs cannot state non-regression within the margin, so it is
  listed as not covered too; a regression is never withheld that way;
- under the same method, the forced-stop check C5 clears only on enough evidence it could have
  failed: fewer than five pairs that ran out of turns on both sides list it as not covered.

Pure: no I/O, no clock, no randomness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import comb, inf, sqrt
from statistics import NormalDist
from typing import assert_never

from praxion_evals.adherence.model import (
    OWN_DISCORDANCE_EXACT,
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
from praxion_evals.adherence.transcript import StoppedAtCap

BISECTION_STEPS = 80
PERCENT = 100
OVER_MARGIN = "the allowance exceeds the margin times the usable pairs"
FORCED_STOP_CHECK = "C5"
MIN_RUN_OUT_PAIRS = 5  # the statistician's floor: below it C5 has had too few chances to fail
PARAMETER_FLOOR = -1.0  # the paired difference of two proportions lies in [-1, 1]
PARAMETER_CEILING = 1.0


def role_verdict(
    checks: Mapping[str, CheckKind],
    pairs: Sequence[Pair],
    settings: DeclaredSettings,
    role: str | None = None,
) -> RoleVerdict:
    """The flip verdict for one role, from its checks (name -> kind) and its pairs.

    ``role`` selects the role's own noise allowances; without it the bare check names are read.
    """
    complete = sum(pair.complete for pair in pairs)
    if complete < settings.required_pairs:
        return Underpowered(
            f"{complete} complete pairs, fewer than the {settings.required_pairs} declared",
            complete,
            settings.required_pairs,
        )
    recounted = [pair for pair in pairs if _countable(pair)]
    ran_out = ran_out_on_both_sides(pairs)
    verdicts: dict[str, CheckVerdict] = {}
    not_covered: dict[str, str] = {}
    lean_failures: dict[str, int] = {}
    for name, kind in checks.items():
        counts = tally(name, recounted)
        if counts.n == 0:
            not_covered[name] = _why_not_covered(name, recounted)
            continue
        lean_failures[name] = counts.lean_failures
        verdicts[name] = _decide(name, kind, counts, settings, role)
        silent_because = _why_claim_is_silent(name, verdicts[name], ran_out, settings)
        if silent_because is not None:
            not_covered[name] = silent_because
    return Assessed(complete, verdicts, not_covered, lean_failures)


def ran_out_on_both_sides(pairs: Sequence[Pair]) -> int:
    """Pairs whose two sessions both ended by the harness stopping the role at its turn cap."""
    return sum(_ran_out(pair.full) and _ran_out(pair.lean) for pair in pairs)


def _ran_out(status: SessionStatus) -> bool:
    return isinstance(status, Measured) and isinstance(status.role_ending, StoppedAtCap)


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


def _decide(
    name: str, kind: CheckKind, counts: Counts, settings: DeclaredSettings, role: str | None
) -> CheckVerdict:
    match kind:
        case "mechanical":
            allowance = _mechanical_allowance(name, counts, settings, role)
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


def _why_claim_is_silent(
    name: str, check_verdict: CheckVerdict, ran_out: int, settings: DeclaredSettings
) -> str | None:
    """Why the flip claim says nothing for a scored mechanical check that would clear, if it does.

    A clearing verdict is withheld when it rests on noise wider than the margin it would claim,
    or, for the forced-stop check, on fewer than ``MIN_RUN_OUT_PAIRS`` pairs that ran out of
    turns on both sides. A failing verdict is never withheld. Only the own-discordance method
    is held to either; a file that declares none keeps the verdict it showed.
    """
    if settings.allowance_method != OWN_DISCORDANCE_EXACT or not isinstance(
        check_verdict, NoRegression
    ):
        return None
    if PERCENT * check_verdict.allowance > settings.margin_pp * check_verdict.counts.n:
        return OVER_MARGIN
    if name == FORCED_STOP_CHECK and ran_out < MIN_RUN_OUT_PAIRS:
        return (
            f"{ran_out} pairs ran out of turns on both sides, fewer than the"
            f" {MIN_RUN_OUT_PAIRS} it needs to be scored"
        )
    return None


def _mechanical_allowance(
    name: str, counts: Counts, settings: DeclaredSettings, role: str | None
) -> int:
    """Net discordance a mechanical check may show without regressing.

    Under the own-discordance method the run's own discordant count sizes it, so no
    calibration run's allowance is ever read; a file that declares no method keeps the
    allowances it declared.
    """
    # Exhaustive on purpose: a second method fails type-checking here instead of taking the
    # legacy branch. The case spells OWN_DISCORDANCE_EXACT out because a case cannot take a name.
    method = settings.allowance_method
    match method:
        case "own-discordance-exact":
            return _exact_quantile(counts.discordant, settings.confidence)
        case None:
            return settings.allowance(name, role)
        case _:
            assert_never(method)


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
# The noise allowance: the exact one-sided quantile of a check's own discordant count
# ---------------------------------------------------------------------------


def _exact_quantile(discordant: int, confidence: float) -> int:
    """The smallest net discordance ``b - c`` the exact one-sided test cannot call a regression.

    Of the ``d = b + c`` pairs on which the arms disagree, a lean arm no worse than the full
    arm loses ``b`` of them as a fair coin would, so ``b - c = 2 * Binomial(d, 1/2) - d``.
    Net discordance ``k`` therefore needs ``b <= (d + k) // 2``, and this returns the first
    ``k`` for which that tail holds at least ``confidence`` of the ``2**d`` outcomes. It is the
    allowance itself, sized by the check's own ``d`` at the declared confidence; no calibration
    run's allowance enters.
    """
    for allowance in range(discordant + 1):
        at_most = (discordant + allowance) // 2
        mass = sum(comb(discordant, i) for i in range(at_most + 1))
        if mass >= confidence * 2**discordant:
            return allowance
    return discordant
