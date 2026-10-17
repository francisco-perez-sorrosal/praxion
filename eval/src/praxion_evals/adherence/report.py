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

from praxion_evals.adherence.lineage import (
    Closed,
    Finished,
    InfraStopped,
    Interrupted,
    Legacy,
    RunEnding,
    SpendRefused,
    continuable,
    ending_of,
)
from praxion_evals.adherence.model import (
    ARMS,
    OWN_DISCORDANCE_EXACT,
    Assessed,
    CheckErrored,
    CheckOutcome,
    CheckVerdict,
    DeclaredSettings,
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
from praxion_evals.adherence.model_verdict import NotCovered
from praxion_evals.adherence.results import (
    CatalogEntry,
    KernelDelivery,
    RunResults,
    kernel_deliveries,
    measured_sessions,
    pairs_of,
    role_verdicts,
)
from praxion_evals.adherence.verdict import tally

PERCENT = 100
REASON_WIDTH = 160
INDENT = "  "
EMPTY_TAIL = "(empty)"

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
    "- A token saving appears only as a startup-probe reading: the median of first-request"
    " tokens beside each arm. No verdict here claims a saving; a verdict bounds non-regression"
    " within the declared margin and nothing more.",
    "- Kernel delivery evidence lists, per role, the marker records of the lean sessions the"
    " verdict relies on. An adherence sandbox writes no observation row, so the marker in the"
    " spawned role's transcript is the record a flip can cite.",
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
    state = (
        "complete" if run.complete else f"incomplete ({len(run.refused_launches)} refused launches)"
    )
    allowances = _allowances_declared(settings)
    return "\n".join(
        [
            f"Adherence report for run {run.id}",
            f"Model {run.model}; Claude Code {run.claude_code_version}; the run is {state}.",
            *_ending_lines(ending_of(results)),
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


def _allowances_declared(settings: DeclaredSettings) -> str:
    if settings.allowance_method == OWN_DISCORDANCE_EXACT:
        return "none declared; each check's is the exact one-sided quantile of its own discordant count"
    if settings.allowance_source:
        pairs = ", ".join(f"{name} {n}" for name, n in sorted(settings.allowances.items()))
        return f"from {settings.allowance_source}: {pairs}"
    return "none, so every allowance is zero"


def _ending_lines(ending: RunEnding) -> list[str]:
    """How a run that did not finish ended; nothing for one that ran to the end of its plan or
    was recorded before endings existed."""
    match ending:
        case Finished() | Legacy():
            return []
        case InfraStopped(reason=reason):
            return [
                f"The run stopped itself: {len(reason.sessions)} {reason.arm} sessions in a row"
                f" ended in {reason.kind} with the same evidence {_one_line(reason.masked_tail)};"
                f" {_continuability(ending)}."
            ]
        case SpendRefused(tasks=tasks):
            refused = f" (tasks {', '.join(tasks)})" if tasks else ""
            return [f"The spend cap refused launches{refused}; {_continuability(ending)}."]
        case Interrupted():
            return [f"The operator interrupted the run; {_continuability(ending)}."]
        case Closed(reason=reason, at=at):
            return [f"The run was closed on {at} without being continued: {reason}."]
        case _:
            assert_never(ending)


def _continuability(ending: RunEnding) -> str:
    return "continuable" if continuable(ending) else "not continuable"


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
    calibration = bool(results.run.extra.get("calibration"))
    for entry in entries:
        lines += _check_lines(entry, complete, verdict, results.settings, calibration)
    lines += _kernel_delivery_lines(kernel_deliveries(results, role))
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
    return lines + _errored_tail_lines(results, role)


def _errored_tail_lines(results: RunResults, role: str) -> list[str]:
    """Each errored session's recorded tails, under its arm and task; none for a record
    written before the tails existed."""
    lines = []
    for record in results.sessions:
        status = record.status
        if record.setup.role != role or not isinstance(status, Errored) or status.tails is None:
            continue
        lines += [
            f"{INDENT * 2}{record.setup.arm} {record.setup.task_id} ({status.kind}):",
            f"{INDENT * 3}error tail: {_one_line(status.tails.error_tail)}",
            f"{INDENT * 3}result tail: {_one_line(status.tails.result_tail)}",
        ]
    return lines


def _one_line(tail: str) -> str:
    return " ".join(tail.split()) or EMPTY_TAIL


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


def _kernel_delivery_lines(deliveries: Iterable[KernelDelivery]) -> list[str]:
    lines = [
        f"{INDENT * 2}{d.task_id}: session {d.session_id or 'not recorded'},"
        f" kernel {d.kernel_version}, slot {'not recorded' if d.slot is None else d.slot}"
        for d in deliveries
    ]
    heading = f"{INDENT}Kernel delivery evidence (lean sessions the verdict relies on):"
    return [heading, *lines] if lines else []


def _earlier_runs_line(results: RunResults, role: str) -> str:
    earlier = results.run.earlier_runs.get(role, ())
    if not earlier:
        return f"{INDENT}Earlier runs of this role on this checkout: none."
    listed = "; ".join(f"{run.run_id}: flip {run.flip}" for run in earlier)
    return f"{INDENT}Earlier runs of this role on this checkout: {listed}."


# ---------------------------------------------------------------------------
# One check
# ---------------------------------------------------------------------------


def _check_lines(
    entry: CatalogEntry,
    complete: list[Pair],
    verdict: RoleVerdict,
    settings: DeclaredSettings,
    calibration: bool,
) -> list[str]:
    lines = [
        f"{INDENT * 2}{entry.name} ({entry.kind}) enforces {entry.rule.file}, section"
        f" '{entry.rule.section}'"
    ]
    for arm in ARMS:
        lines += _arm_outcome_lines(entry.name, arm, [getattr(pair, arm) for pair in complete])
    if calibration:
        return [*lines, _slot_order_line(entry.name, complete)]
    lines += _allowance_lines(entry.name, verdict, settings)
    lines.append(f"{INDENT * 3}verdict: {_check_verdict(entry.name, verdict)}")
    return lines


def _slot_order_line(check: str, complete: list[Pair]) -> str:
    """A same-arm run's net discordance on a check: how far the second run's slot moved the
    result. A diagnostic only; it sizes no allowance and decides no verdict."""
    counts = tally(check, complete)
    return (
        f"{INDENT * 3}slot-order check: b - c = {counts.b - counts.c}"
        f" (b {counts.b}, c {counts.c}, n {counts.n}); no allowance"
    )


def _allowance_lines(check: str, verdict: RoleVerdict, settings: DeclaredSettings) -> list[str]:
    """A mechanical check's discordance and allowance beside the margin; none for a file whose
    allowances were declared rather than sized by the run's own discordance."""
    if settings.allowance_method != OWN_DISCORDANCE_EXACT or not isinstance(verdict, Assessed):
        return []
    match verdict.check_verdicts.get(check):
        case (
            NoRegression(counts=counts, allowance=allowance)
            | Regression(counts=counts, allowance=allowance)
        ):
            return [
                f"{INDENT * 3}allowance: {allowance} pairs ({PERCENT * allowance / counts.n:.1f} pp)"
                f" at {counts.discordant} discordant pairs; declared margin"
                f" {settings.margin_pp:g} pp"
            ]
        case _:
            return []


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
        case Assessed(check_verdicts=scored):
            coverage = verdict.coverage(check)
            if isinstance(coverage, NotCovered):
                return f"not covered by the flip verdict ({coverage.reason})"
            if check in scored:
                return _scored_verdict(scored[check])
            return "not covered by the flip verdict (not scored)"
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
