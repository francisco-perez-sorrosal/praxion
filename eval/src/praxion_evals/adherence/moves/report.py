"""The report of a move run: what the paired run could see, in bounded wording.

``render`` reads a typed ``Measurement`` and states, per governed check: the final-state
failures of each arm, the history outcomes, the arrival timing by channel with trigger failures
(the text never arrived) counted apart from failures with arrival, the floor's failures out of
the floor sessions that scored the check, the sensitivity line beside the check's allowance in
pairs and points beside the declared margin, and whether the clearance claim covers the check.
Per-kind counts sit beside the pooled verdict, and a one-kind restriction is named.

The wording claims bounded non-regression within the margin and nothing about one channel
beating another. History and arrival timing are shown and gate nothing.

Every figure is also printed on a line ``figure | <subject> | <topic> | <values...>``, which is
how a reader of the report (a test, a script) takes it back without parsing prose. The subject
is a governed check, or ``run``.

Pure: a measurement in, a string out.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, assert_never

from praxion_evals.adherence.model import ARMS, Counts, Failed
from praxion_evals.adherence.moves.model import (
    Arrival,
    Arrived,
    Channel,
    FixtureKind,
    NeverArrived,
    Unknown,
)
from praxion_evals.adherence.moves.verdict import (
    SHOWN_DECIMALS,
    FloorTally,
    Measurement,
    MovePair,
    MoveVerdict,
    Sensitivity,
    Side,
    move_verdict,
    sensitivity,
)

PERCENT = 100
NONE = "none"
REGRESSION = "regression"
NO_USABLE_PAIR = "no complete pair scored the check"
NO_FLOOR_SESSION = "no floor session scored the check"
UNDER_ALLOWANCE = "the sensitivity figure does not exceed the check's allowance"
FIGURE = "figure"

ArrivalClass = Literal["trigger failure", "arrived", "unknown"]

READING_NOTES = (
    "How to read this report",
    "- The claim is bounded non-regression on final state within the declared margin, over the"
    " pairs shown. It says nothing about one channel beating another: arrival timing is shown"
    " per channel and never compared across channels.",
    "- History outcomes and arrival timing are shown beside the verdict and enter no verdict.",
    "- A trigger failure is a failed check whose governing text never arrived through any"
    " channel; it is counted apart from failures with arrival and from failures whose arrival"
    " the record could not tell.",
    "- Floor sessions enter no pair and no allowance. The sensitivity line is the target pairs"
    " times the floor's failure rate less the full arm's; it changes no verdict. A check whose"
    " figure does not exceed its allowance is not covered by the clearance claim.",
)


@dataclass(frozen=True)
class _CheckView:
    """What the report states about one governed check, computed once and shown twice."""

    name: str
    counts: Counts | None  # None: no complete pair scored the check
    allowance: int | None
    floor: FloorTally
    sensitivity: Sensitivity | None
    uncovered: str | None  # why the clearance claim is silent on the check; None: covered


def render(measurement: Measurement) -> str:
    verdict = move_verdict(measurement)
    views = [_view(name, measurement, verdict) for name in measurement.checks]
    complete = [pair for pair in measurement.pairs if pair.full and pair.lean]
    sections = [
        _headline(measurement, verdict, views),
        "\n".join(READING_NOTES),
        *(_check_section(view, verdict, complete) for view in views),
        _kind_section(measurement, complete, verdict),
    ]
    return "\n\n".join(sections) + "\n"


# -- What is known about each check -------------------------------------------------------------


def _view(name: str, measurement: Measurement, verdict: MoveVerdict) -> _CheckView:
    counts = verdict.counts.get(name)
    allowance = verdict.allowances.get(name)
    floor = measurement.floor_tally(name)
    seen = (
        None
        if counts is None or allowance is None
        else sensitivity(counts, floor, measurement.target_pairs, allowance)
    )
    return _CheckView(name, counts, allowance, floor, seen, _uncovered(name, verdict, seen, counts))


def _uncovered(
    name: str, verdict: MoveVerdict, seen: Sensitivity | None, counts: Counts | None
) -> str | None:
    if name in verdict.not_covered:
        return verdict.not_covered[name]
    if counts is None:
        return NO_USABLE_PAIR
    if seen is None:
        return NO_FLOOR_SESSION
    return None if seen.exceeds_allowance else UNDER_ALLOWANCE


# -- The headline: the bounded claim ------------------------------------------------------------


def _headline(measurement: Measurement, verdict: MoveVerdict, views: Sequence[_CheckView]) -> str:
    claim = _clearance_claim(measurement, verdict, views)
    lines = [
        "Move run report",
        f"Margin: {_one_decimal(measurement.margin_pp)} points on final state.",
        f"Complete pairs: {verdict.complete_pairs} (target {measurement.target_pairs}).",
        _restriction_sentence(measurement.kind_restriction),
        claim,
        _figure("run", "margin", _one_decimal(measurement.margin_pp)),
        _figure("run", "restriction", measurement.kind_restriction or NONE),
        _figure("run", "clearance", claim),
    ]
    return "\n".join(lines)


def _restriction_sentence(restriction: FixtureKind | None) -> str:
    if restriction is None:
        return "Fixture kinds: managed and unmanaged, pooled."
    return f"Restricted to {restriction} fixtures only: the run says nothing about the other kind."


def _clearance_claim(
    measurement: Measurement, verdict: MoveVerdict, views: Sequence[_CheckView]
) -> str:
    regressed = [n for n, label in verdict.check_verdicts.items() if label == REGRESSION]
    silent = [f"{view.name} ({view.uncovered})" for view in views if view.uncovered]
    parts = [_claim_head(measurement, verdict, regressed)]
    if silent:
        parts.append(f"Not covered, so the claim is silent on: {'; '.join(silent)}.")
    return " ".join(parts)


def _claim_head(measurement: Measurement, verdict: MoveVerdict, regressed: list[str]) -> str:
    margin = _one_decimal(measurement.margin_pp)
    if regressed:
        return f"Regression on final state in {', '.join(regressed)}: no non-regression claim."
    if verdict.cleared is None:
        return (
            f"No clearance claim yet: {verdict.complete_pairs} of the"
            f" {measurement.target_pairs} complete pairs the target needs have run."
        )
    if not verdict.cleared:
        return "No clearance claim: no governed check is covered."
    return f"Non-regression within the margin of {margin} points on the covered checks."


# -- One governed check -------------------------------------------------------------------------


def _check_section(view: _CheckView, verdict: MoveVerdict, complete: Sequence[MovePair]) -> str:
    sides = {arm: _sides(complete, arm) for arm in ARMS}
    lines = [
        view.name,
        _figure(view.name, "verdict", verdict.check_verdicts.get(view.name, NONE)),
        _figure(view.name, "floor", view.floor.failures, view.floor.scored),
        *_final_lines(view, sides),
        *_history_lines(view.name, sides),
        *_timing_lines(view.name, sides),
        *_trigger_lines(view.name, sides),
        *_allowance_lines(view),
    ]
    return "\n".join(lines)


def _sides(complete: Sequence[MovePair], arm: str) -> list[Side]:
    sides = [pair.full if arm == "full" else pair.lean for pair in complete]
    return [side for side in sides if side is not None]


def _final_lines(view: _CheckView, sides: dict[str, list[Side]]) -> list[str]:
    return [
        _figure(view.name, "final", arm, _final_failures(view.name, arm_sides))
        for arm, arm_sides in sides.items()
    ]


def _final_failures(check: str, sides: Iterable[Side]) -> int:
    return sum(isinstance(side.final.get(check), Failed) for side in sides)


def _history_lines(check: str, sides: dict[str, list[Side]]) -> list[str]:
    lines = []
    for arm, arm_sides in sides.items():
        seen = Counter(side.history[check] for side in arm_sides if check in side.history)
        lines += [_figure(check, "history", arm, word, n) for word, n in sorted(seen.items())]
    return lines


def _timing_lines(check: str, sides: dict[str, list[Side]]) -> list[str]:
    lines = []
    for arm, arm_sides in sides.items():
        seen: Counter[tuple[Channel, str]] = Counter(
            (channel, _timing_word(arrival))
            for side in arm_sides
            for channel, arrival in side.arrivals.get(check, {}).items()
        )
        lines += [
            _figure(check, "timing", arm, c, word, n) for (c, word), n in sorted(seen.items())
        ]
    return lines


def _timing_word(arrival: Arrival) -> str:
    match arrival:
        case Arrived(timing):
            return timing
        case NeverArrived():
            return "never"
        case Unknown():
            return "unknown"
        case _:
            assert_never(arrival)


def _trigger_lines(check: str, sides: dict[str, list[Side]]) -> list[str]:
    lines = []
    for arm, arm_sides in sides.items():
        seen = Counter(
            _arrival_class(side.arrivals.get(check, {}))
            for side in arm_sides
            if isinstance(side.final.get(check), Failed)
        )
        lines.append(
            _figure(
                check, "trigger", arm, seen["trigger failure"], seen["arrived"], seen["unknown"]
            )
        )
    return lines


def _arrival_class(arrivals: Mapping[Channel, Arrival]) -> ArrivalClass:
    """A failure's arrival: any channel that carried the text, else whether the record could tell."""
    if any(isinstance(a, Arrived) for a in arrivals.values()):
        return "arrived"
    if arrivals and all(isinstance(a, NeverArrived) for a in arrivals.values()):
        return "trigger failure"
    return "unknown"


def _allowance_lines(view: _CheckView) -> list[str]:
    if view.counts is None or view.allowance is None:
        allowance, in_points = NONE, NONE
    else:
        allowance = f"{view.allowance} pairs"
        in_points = _one_decimal(PERCENT * view.allowance / view.counts.n)
    shown = view.sensitivity.shown if view.sensitivity else NONE
    return [
        f"allowance: {allowance} ({in_points} points)",
        f"sensitivity: {shown} pairs the floor's failure rate leaves the paired run to see",
        "coverage: " + (view.uncovered and f"not covered, {view.uncovered}" or "covered"),
        _figure(view.name, "allowance", in_points),
        _figure(view.name, "sensitivity", shown),
        _figure(view.name, "coverage", "not covered" if view.uncovered else "covered"),
    ]


# -- Fixture kinds beside the pooled verdict ----------------------------------------------------


def _kind_section(
    measurement: Measurement, complete: Sequence[MovePair], verdict: MoveVerdict
) -> str:
    pooled = ", ".join(f"{n}: {label}" for n, label in verdict.check_verdicts.items()) or NONE
    kinds = sorted({pair.fixture_kind for pair in complete})
    lines = ["Fixture kinds beside the pooled verdict", f"Pooled verdict: {pooled}."]
    for kind in kinds:
        pairs = [pair for pair in complete if pair.fixture_kind == kind]
        lines += [f"{kind}: {len(pairs)} complete pairs", _figure("run", "kind", kind, len(pairs))]
    return "\n".join(lines)


# -- Figures ------------------------------------------------------------------------------------


def _figure(subject: str, topic: str, *values: object) -> str:
    return " | ".join([FIGURE, subject, topic, *(str(value) for value in values)])


def _one_decimal(value: float) -> str:
    return f"{value:.{SHOWN_DECIMALS}f}"
