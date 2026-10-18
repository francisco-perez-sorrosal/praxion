"""The text report of an adherence run: counts and bounds, never improvement.

``render`` reads a loaded results file and states what it recorded, per role and
per arm, with the setup that produced it. Verdicts are recomputed from the stored
sessions through ``verdict.role_verdict``, never read back. The wording claims at
most non-regression on a mechanical check and non-inferiority within the declared
margin on a judged one; it says that judge error attenuates differences and that
a reported interval did not decide; it gives an underpowered role its counts and
no flip verdict. No sentence ranks one arm over the other.

A continued run is one run: ``render`` takes the latest part and the parts before it and states
one verdict over the sessions of all of them, under what the first part declared, naming each part.

Pure: results values in, a string out.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from statistics import median
from textwrap import shorten
from typing import Any, assert_never

from praxion_evals.adherence.lineage import (
    LAUNCH_REFUSED,
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
    SessionRecord,
    SessionStatus,
    Underpowered,
    Withheld,
)
from praxion_evals.adherence.model_verdict import NotCovered
from praxion_evals.adherence.results import (
    CatalogEntry,
    KernelDelivery,
    RunInfo,
    RunResults,
    earlier_listed,
    kernel_deliveries,
    measured_sessions,
    merged,
    pairs_of,
    role_verdicts,
    skipped_files,
)
from praxion_evals.adherence.run_ending import stop_summary
from praxion_evals.adherence.transcript import EndedOnItsOwn, StoppedAtCap
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


def render(results: RunResults, continued_from: Sequence[RunResults] = ()) -> str:
    """The report of ``results``; ``continued_from`` is the parts of its lineage before it, oldest
    first, so the report reads the whole run and not just the part that happened to end it."""
    parts = [*continued_from, results]
    whole = merged(parts)
    verdicts = role_verdicts(whole)
    sections = [_run_section(whole, parts), "\n".join(READING_NOTES)]
    sections += [
        _role_section(whole, role, entries, verdicts[role])
        for role, entries in whole.catalog.items()
    ]
    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# The run: its identity and the settings it declared before any session
# ---------------------------------------------------------------------------


def _run_section(results: RunResults, parts: Sequence[RunResults]) -> str:
    run, settings = results.run, results.settings
    state = (
        "complete" if run.complete else f"incomplete ({len(run.refused_launches)} refused launches)"
    )
    allowances = _allowances_declared(settings)
    return "\n".join(
        [
            f"Adherence report for run {run.id}",
            f"Model {run.model}; Claude Code {run.claude_code_version}; the run is {state}.",
            *_continued_lines(parts),
            *_ending_lines(ending_of(results)),
            *_skipped_lines(results),
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


def _continued_lines(parts: Sequence[RunResults]) -> list[str]:
    """A continued run says so and names every part, oldest first, with what it cost and how it
    ended; nothing for a run that continues no other."""
    if len(parts) < 2:
        return []
    lines = [
        f"Continued run: part {len(parts)} of {len(parts)}; one verdict over the sessions of every"
        " part, judged under what part 1 declared."
    ]
    for number, part in enumerate(parts, start=1):
        launched = sum(not _refused(record) for record in part.sessions)
        spent = sum(record.cost_usd for record in part.sessions)
        started = part.run.extra.get("started_at", "not recorded")
        lines.append(
            f"{INDENT}part {number}: {part.run.id} (started {started};"
            f" Claude Code {part.run.claude_code_version}; {launched} sessions launched;"
            f" ${spent:.2f} spent; {stop_summary(ending_of(part))})"
        )
    return lines


def _refused(record: SessionRecord) -> bool:
    return isinstance(record.status, Errored) and record.status.kind == LAUNCH_REFUSED


def _skipped_lines(results: RunResults) -> list[str]:
    skipped = skipped_files(results.run)
    if not skipped:
        return []
    return [f"Skipped, not adherence results files, beside this run's: {', '.join(skipped)}."]


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
    lines += _run_out_lines(results, role)
    lines += [f"{INDENT}Checks:"]
    calibration = bool(results.run.extra.get("calibration"))
    for entry in entries:
        lines += _check_lines(entry, complete, verdict, results.settings, calibration)
    lines += _kernel_delivery_lines(kernel_deliveries(results, role))
    lines += _earlier_runs_lines(results, role)
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


def _run_out_lines(results: RunResults, role: str) -> list[str]:
    """How the role's forced-stop sessions ended, per arm, and the gap between the arms.

    Counted over every measured session that recorded an ending, paired or not; a session whose
    record could not tell is in neither count. Reported and never decisive: nothing here enters
    a verdict. None for a run with no forced-stop session, or one recorded before endings were.
    """
    counts = {arm: _run_out_counts(measured_sessions(results, role, arm)) for arm in ARMS}
    if not any(any(arm_counts) for arm_counts in counts.values()):
        return []
    lines = [
        f"{INDENT}forced-stop sessions, {arm} arm: {ran_out} ran out of turns,"
        f" {ended_early} ended before their cap"
        for arm, (ran_out, ended_early) in counts.items()
    ]
    lines.append(
        f"{INDENT}differential run-out rate (lean minus full): {_differential_run_out(counts)}"
    )
    return lines


def _run_out_counts(sessions: Iterable[Measured]) -> tuple[int, int]:
    endings = Counter(type(session.role_ending) for session in sessions)
    return endings[StoppedAtCap], endings[EndedOnItsOwn]


def _differential_run_out(counts: dict[str, tuple[int, int]]) -> str:
    """Lean's share of forced-stop sessions that ran out of turns, minus full's, in points."""
    shares = {
        arm: ran_out / (ran_out + ended_early)
        for arm, (ran_out, ended_early) in counts.items()
        if ran_out + ended_early
    }
    if len(shares) < len(ARMS):
        return "not defined, an arm has no forced-stop session that ended in a known way"
    return f"{PERCENT * (shares['lean'] - shares['full']):.1f} pp"


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


def _earlier_runs_lines(results: RunResults, role: str) -> list[str]:
    listed = earlier_listed(results.run, role)
    if listed is None:  # a file written before runs were listed by what they measured
        earlier = results.run.earlier_runs.get(role, ())
        runs = "; ".join(f"{run.run_id}: flip {run.flip}" for run in earlier) or "none"
        return [f"{INDENT}Earlier runs of this role on this checkout: {runs}."]
    own = _own_run_ids(results.run)  # the parts a run continues were listed beside it, not before
    shown = [d for d in listed.draws if own.isdisjoint(d.run_ids)]
    draws = "; ".join(f"{' + '.join(d.run_ids)}: flip {d.flip}" for d in shown) or "none"
    lines = [f"{INDENT}Earlier runs of this role on the same definition and kernel: {draws}."]
    if listed.apart:
        lines.append(f"{INDENT}Earlier runs of this role set apart, with how they differ:")
        lines += [f"{INDENT * 2}{run_id}: {how}" for run_id, how in listed.apart.items()]
    if listed.calibration:
        calibration = ", ".join(listed.calibration)
        lines.append(f"{INDENT}Calibration runs of this role, never a draw: {calibration}.")
    return lines


def _own_run_ids(run: RunInfo) -> frozenset[str]:
    lineage: Sequence[dict[str, Any]] = run.extra.get("lineage") or ()
    return frozenset({run.id, *(part["run_id"] for part in lineage)})


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
