"""Driver that authors a spec for a change that moves a measurable footprint.

Where a spec carries a quantitative criterion, and where it carries a
declaration that a footprint is not measured, is decided in design. This
driver is the one place the scenarios learn that answer: it returns the full
`SYSTEMS_PLAN.md` text of a footprint-moving change, with one plain
requirement and each given criterion and declaration written at its designed
place, every given value copied verbatim.

Criteria are written to the `### Footprint Criteria` table and declarations to
the `### Footprints Not Measured` table, both under `## Acceptance Criteria`;
each criterion's command is also listed on `### Observable Surface`.
"""

from __future__ import annotations

from dataclasses import dataclass

_CRITERIA_HEADER = ("Id", "Footprint", "Metric", "Comparator", "Limit", "Against", "Command")
_DECLARATION_HEADER = ("Footprint", "Reason")


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
    acceptance = ["## Acceptance Criteria", "", "- [ ] The change behaves as described", ""]
    if criteria:
        rows = [
            (
                f"FC-{number:02d}",
                f"footprint-{number}",
                criterion.metric,
                criterion.comparator,
                criterion.limit,
                f"baseline: {criterion.baseline}",
                f"`{criterion.command}`",
            )
            for number, criterion in enumerate(criteria, start=1)
        ]
        acceptance += ["### Footprint Criteria", "", *_table(_CRITERIA_HEADER, rows), ""]
    if declarations:
        rows = [(declaration.footprint, declaration.reason) for declaration in declarations]
        acceptance += ["### Footprints Not Measured", "", *_table(_DECLARATION_HEADER, rows), ""]

    surface = [f"- `{criterion.command}`" for criterion in criteria] or ["- the change's behavior"]
    lines = [
        "# Footprint-moving change",
        "",
        "## Goal",
        "",
        "Ship a change that moves a measurable footprint.",
        "",
        *acceptance,
        "## Behavioral Specification",
        "",
        "### REQ-01",  # id-citation-discipline:ignore -- spec format requires a requirement heading
        "",
        "The change behaves as described.",
        "",
        "### Observable Surface",
        "",
        *surface,
        "",
    ]
    return "\n".join(lines)


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    def row(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"

    return [row(header), "|" + "---|" * len(header), *(row(cells) for cells in rows)]
