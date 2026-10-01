"""Driver that authors a spec for a change that moves a measurable footprint.

Where a spec carries a quantitative criterion, and where it carries a
declaration that a footprint is not measured, is decided in design. This
driver is the one place the scenarios learn that answer: it returns the full
`SYSTEMS_PLAN.md` text of a footprint-moving change, with one plain
requirement and each given criterion and declaration written at its designed
place, every given value copied verbatim.

Unbound until a binding step writes `spec_carrying` against the design.
"""

from __future__ import annotations

from dataclasses import dataclass

UNBOUND = (
    "unbound: the place a spec carries a quantitative criterion (metric, "
    "comparator, limit, baseline or reference, and the command that measures "
    "it) and a not-measured declaration (footprint and reason) is decided in "
    "design; bind this driver to that place"
)


@dataclass(frozen=True)
class QuantitativeCriterion:
    metric: str
    comparator: str
    limit: str
    baseline: str
    command: str


@dataclass(frozen=True)
class NotMeasured:
    footprint: str
    reason: str


def spec_carrying(
    criteria: tuple[QuantitativeCriterion, ...] = (),
    declarations: tuple[NotMeasured, ...] = (),
) -> str:
    """The plan text of a footprint-moving change carrying `criteria` and `declarations`.

    The text holds every section a spec phase writes (goal, acceptance
    criteria, behavioral specification with its observable surface and one
    plain requirement) and is free of design vocabulary outside the given
    values, so the spec lint judges only how the criteria are carried.
    """
    raise NotImplementedError(UNBOUND)
