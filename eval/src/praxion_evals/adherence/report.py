"""The text report of an adherence run: counts and bounds, never improvement.

``render`` reads a loaded results file and states what it recorded, per role and
per arm, with the setup that produced it. Verdicts are recomputed from the stored
sessions through ``verdict.role_verdict``, never read back. The wording claims at
most non-regression on a mechanical check and non-inferiority within the declared
margin on a judged one; it says that judge error attenuates differences and that
a reported interval did not decide; it gives an underpowered role its counts and
no flip verdict. No sentence ranks one arm over the other.

Pure: a results value in, a string out.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from statistics import median
from textwrap import shorten
from typing import assert_never

from praxion_evals.adherence.model import (
    ARMS,
    Assessed,
    CheckErrored,
    CheckOutcome,
    CheckVerdict,
    Errored,
    Failed,
    Inferior,
    Measured,
    NonInferior,
    NoRegression,
    NotApplicable,
    NotMeasured,
    Pair,
    Passed,
    Regression,
    RoleVerdict,
    SessionStatus,
    Underpowered,
    Withheld,
)
from praxion_evals.adherence.results import (
    CatalogEntry,
    RunResults,
    measured_sessions,
    pairs_of,
    role_verdicts,
)

PERCENT = 100
REASON_WIDTH = 160
INDENT = "  "

OUTCOME_LABELS: dict[type, str] = {
    Passed: "passed",
    Failed: "failed",
    Withheld: "withheld",
    NotApplicable: "not applicable",
    CheckErrored: "errored",
}

FLIP_MEANING = {
    "clear": "no regression on any scored mechanical check and every scored judged check"
    " non-inferior within the margin",
    "not clear": "a scored check shows a regression or is inferior, or no check was scored",
}

READING_NOTES = (
    "How to read this report",
    "- Each verdict claims at most non-regression on a mechanical check, and non-inferiority"
    " within the declared margin on a judged check, over the pairs shown. It says nothing"
    " about either arm doing more than the other.",
    "- Judge error attenuates differences between the arms toward zero, so a judged check can"
    " look equal when the arms differ.",
    "- A judged check's interval is reported beside its verdict. The interval did not decide"
    " the verdict, which the margin on the pass rates alone decides.",
    "- b counts pairs where only the full arm passed; c counts pairs where only the lean arm"
    " passed; n is the usable pairs after the worst-case recount.",
    "- Withheld and not-applicable checks enter no rate and no verdict, and are not covered by"
    " a flip verdict; each is listed with its reason.",
)


def render(results: RunResults) -> str:
    verdicts = role_verdicts(results)
    sections = [_run_section(results), "\n".join(READING_NOTES)]
    sections += [
        _role_section(results, role, entries, verdicts[role])
        for role, entries in results.catalog.items()
    ]
    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# The run: its identity and the settings it declared before any session
# ---------------------------------------------------------------------------


def _run_section(results: RunResults) -> str:
    run, settings = results.run, results.settings
    ending = (
        "complete" if run.complete else f"incomplete ({len(run.refused_launches)} refused launches)"
    )
    allowances = (
        f"from {settings.allowance_source}: "
        + ", ".join(f"{name} {pairs}" for name, pairs in sorted(settings.allowances.items()))
        if settings.allowance_source
        else "none, so every allowance is zero"
    )
    return "\n".join(
        [
            f"Adherence report for run {run.id}",
            f"Model {run.model}; Claude Code {run.claude_code_version}; the run is {ending}.",
            f"Declared at {results.declared_at}, before the first session:",
            f"{INDENT}non-inferiority margin {settings.margin_pp:g} pp for judged checks;"
            f" method {settings.method}, {settings.sidedness},"
            f" confidence {settings.confidence:.0%};",
            f"{INDENT}target {settings.required_pairs} complete pairs per role,"
            f" slack {settings.pair_slack}; retry policy: {settings.retry_policy};",
            f"{INDENT}mechanical noise allowances: {allowances}.",
            _judge_error_line(results),
        ]
    )


def _judge_error_line(results: RunResults) -> str:
    recorded = (results.golden_bad_case_verdicts or {}).get("observed_error")
    if recorded is None:
        return "Judge error on the golden cases: not recorded in this run."
    return f"Judge error observed on the golden cases: {recorded:.2f} ({recorded:.0%})."


# ---------------------------------------------------------------------------
# One role
# ---------------------------------------------------------------------------


def _role_section(
    results: RunResults, role: str, entries: Iterable[CatalogEntry], verdict: RoleVerdict
) -> str:
    pairs = pairs_of(results, role)
    complete = [pair for pair in pairs if pair.complete]
    lines = [f"Role {role}: {_role_headline(verdict)}"]
    lines.append(
        f"{INDENT}{len(complete)} complete pairs of {len(pairs)} paired tasks;"
        f" worst-case recount, pairs with a lean-side error and a measured full side counted as"
        f" lean failures: {_lean_errored(pairs)}."
    )
    lines += _session_lines(results, role)
    lines += [f"{INDENT}Checks:"]
    for entry in entries:
        lines += _check_lines(entry, complete, verdict)
    lines.append(_earlier_runs_line(results, role))
    return "\n".join(lines)


def _role_headline(verdict: RoleVerdict) -> str:
    match verdict:
        case Underpowered(reason=reason):
            return f"underpowered, counts only and no flip verdict ({reason})."
        case Assessed():
            return (
                f"flip verdict {verdict.flip}, over {verdict.complete_pairs} complete pairs"
                f" ({FLIP_MEANING[verdict.flip]})."
            )
        case _:
            assert_never(verdict)


def _lean_errored(pairs: Iterable[Pair]) -> int:
    return sum(isinstance(p.full, Measured) and isinstance(p.lean, Errored) for p in pairs)


def _session_lines(results: RunResults, role: str) -> list[str]:
    lines = []
    for arm in ARMS:
        statuses = [
            r.status for r in results.sessions if r.setup.role == role and r.setup.arm == arm
        ]
        built = results.arms.get(role, {}).get(arm, {}).get("built", True)
        if not statuses and built:
            continue
        counts = Counter(type(status) for status in statuses)
        lines.append(
            f"{INDENT}{arm} arm{'' if built else ' (not built)'}: {counts[Measured]} measured,"
            f" {counts[Errored]} errored, {counts[NotMeasured]} not measured;"
            f" first-request tokens, median {_token_median(results, role, arm)}."
        )
        lines += _unmeasured_reasons(statuses)
    return lines


def _token_median(results: RunResults, role: str, arm: str) -> str:
    tokens = [
        session.first_request_tokens
        for session in measured_sessions(results, role, arm)
        if session.first_request_tokens is not None
    ]
    return f"{round(median(tokens)):,} over {len(tokens)} sessions" if tokens else "not recorded"


def _unmeasured_reasons(statuses: Iterable[SessionStatus]) -> list[str]:
    reasons: Counter[str] = Counter()
    for status in statuses:
        if isinstance(status, Errored):
            reasons[f"errored, {status.kind}: {status.detail}"] += 1
        elif isinstance(status, NotMeasured):
            reasons[f"not measured: {status.reason}"] += 1
    return [
        f"{INDENT * 2}{count} x {shorten(reason, REASON_WIDTH)}"
        for reason, count in reasons.items()
    ]


def _earlier_runs_line(results: RunResults, role: str) -> str:
    earlier = results.run.earlier_runs.get(role, ())
    if not earlier:
        return f"{INDENT}Earlier runs of this role on this checkout: none."
    listed = "; ".join(f"{run.run_id}: flip {run.flip}" for run in earlier)
    return f"{INDENT}Earlier runs of this role on this checkout: {listed}."


# ---------------------------------------------------------------------------
# One check
# ---------------------------------------------------------------------------


def _check_lines(entry: CatalogEntry, complete: list[Pair], verdict: RoleVerdict) -> list[str]:
    lines = [
        f"{INDENT * 2}{entry.name} ({entry.kind}) enforces {entry.rule.file}, section"
        f" '{entry.rule.section}'"
    ]
    for arm in ARMS:
        lines += _arm_outcome_lines(entry.name, arm, [getattr(pair, arm) for pair in complete])
    lines.append(f"{INDENT * 3}verdict: {_check_verdict(entry.name, verdict)}")
    return lines


def _arm_outcome_lines(check: str, arm: str, statuses: Iterable[SessionStatus]) -> list[str]:
    outcomes: list[CheckOutcome] = [
        s.outcomes[check] for s in statuses if isinstance(s, Measured) and check in s.outcomes
    ]
    counts = Counter(OUTCOME_LABELS[type(outcome)] for outcome in outcomes)
    scored = counts["passed"] + counts["failed"]
    line = (
        f"{INDENT * 3}{arm}: passed {counts['passed']} of {scored} scored;"
        f" withheld {counts['withheld']}, not applicable {counts['not applicable']},"
        f" errored {counts['errored']}"
    )
    reasons = sorted(
        {
            f"{OUTCOME_LABELS[type(o)]}: {o.reason}"
            for o in outcomes
            if isinstance(o, Withheld | NotApplicable | CheckErrored)
        }
    )
    return [line] + [f"{INDENT * 4}{shorten(reason, REASON_WIDTH)}" for reason in reasons]


def _check_verdict(check: str, verdict: RoleVerdict) -> str:
    match verdict:
        case Underpowered():
            return "none (the role is underpowered)"
        case Assessed(check_verdicts=scored, not_covered=not_covered):
            if check in scored:
                return _scored_verdict(scored[check])
            return f"not covered by the flip verdict ({not_covered.get(check, 'not scored')})"
        case _:
            assert_never(verdict)


def _scored_verdict(check_verdict: CheckVerdict) -> str:
    counts = check_verdict.counts
    tallies = f"b {counts.b}, c {counts.c}, n {counts.n}, lean failures {counts.lean_failures}"
    match check_verdict:
        case NoRegression(allowance=allowance) | Regression(allowance=allowance):
            label = "no regression" if isinstance(check_verdict, NoRegression) else "regression"
            return f"{label} ({tallies}; noise allowance {allowance})"
        case NonInferior(interval=interval) | Inferior(interval=interval):
            label = "non-inferior" if isinstance(check_verdict, NonInferior) else "inferior"
            lower, upper = PERCENT * interval.lower, PERCENT * interval.upper
            return (
                f"{label} (pass rates: lean {counts.passes_lean} of {counts.n},"
                f" full {counts.passes_full} of {counts.n}; {tallies}); one-sided interval on"
                f" lean minus full: lower {lower:+.1f} pp, upper {upper:+.1f} pp,"
                f" width {upper - lower:.1f} pp, reported only"
            )
        case _:
            assert_never(check_verdict)
