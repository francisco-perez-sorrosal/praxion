"""IMPLEMENTATION_PLAN.md impact detection and annotation.

Scans plan steps for references to amended REQ IDs and annotates
affected steps with a visible warning that the spec has changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STEP_HEADING_RE = re.compile(r"^### Step \d+", re.MULTILINE)
REQ_REF_RE = re.compile(r"REQ-\d+")

# Path is task-scoped: .ai-work/<task-slug>/IMPLEMENTATION_PLAN.md
# Callers pass the resolved path; this constant is for documentation.
IMPLEMENTATION_PLAN_PATH = ".ai-work/IMPLEMENTATION_PLAN.md"
ANNOTATION_MARKER = "[SPEC AMENDED]"


@dataclass(frozen=True)
class PlanImpact:
    """A plan step that references an amended REQ ID."""

    step_heading: str
    line_number: int
    affected_reqs: list[str]


def find_plan_impacts(
    plan_path: Path,
    amended_req_ids: set[str],
) -> list[PlanImpact]:
    """Find plan steps that reference any of the amended REQ IDs.

    Returns one ``PlanImpact`` per affected step, listing which
    amended REQs that step references.
    """
    if not plan_path.is_file() or not amended_req_ids:
        return []

    content = plan_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Build a map: step heading -> (line_number, step_text_range)
    steps = _parse_step_boundaries(lines)

    impacts: list[PlanImpact] = []
    for heading, start_line, end_line in steps:
        step_text = "\n".join(lines[start_line:end_line])
        refs_in_step = set(REQ_REF_RE.findall(step_text))
        matched = sorted(refs_in_step & amended_req_ids)
        if matched:
            impacts.append(
                PlanImpact(
                    step_heading=heading,
                    line_number=start_line + 1,  # 1-indexed
                    affected_reqs=matched,
                )
            )

    return impacts


def annotate_plan(
    plan_path: Path,
    impacts: list[PlanImpact],
    summaries: dict[str, str],
) -> int:
    """Insert annotation blockquotes into affected plan steps.

    For each impacted step, appends a ``[SPEC AMENDED]`` annotation
    after the step's content block (before the next step heading).

    *summaries* maps REQ IDs to their change summary text.

    Returns the number of annotations inserted. Skips steps that
    already have the annotation marker to avoid duplicates.
    """
    if not plan_path.is_file() or not impacts:
        return 0

    content = plan_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Work backwards to preserve line numbers during insertion
    sorted_impacts = sorted(impacts, key=lambda i: i.line_number, reverse=True)
    inserted = 0

    step_boundaries = _parse_step_boundaries(lines)
    # Build a quick lookup: start_line -> end_line
    boundary_map = {start: end for _, start, end in step_boundaries}

    for impact in sorted_impacts:
        start_line = impact.line_number - 1  # Convert to 0-indexed
        end_line = boundary_map.get(start_line)
        if end_line is None:
            continue

        # Check if annotation already exists in this step
        step_text = "\n".join(lines[start_line:end_line])
        if ANNOTATION_MARKER in step_text:
            continue

        # Build annotation lines
        annotation_lines = _build_annotation(impact.affected_reqs, summaries)

        # Insert before the end of the step (before the next heading or EOF)
        insert_at = end_line
        lines[insert_at:insert_at] = annotation_lines
        inserted += 1

    plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return inserted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_step_boundaries(
    lines: list[str],
) -> list[tuple[str, int, int]]:
    """Parse step headings and their line boundaries.

    Returns a list of (heading_text, start_line, end_line) tuples
    where start_line is the heading line and end_line is the line
    before the next step heading (or the last line of the file).
    """
    steps: list[tuple[str, int]] = []
    for i, line in enumerate(lines):
        if STEP_HEADING_RE.match(line):
            steps.append((line.strip(), i))

    boundaries: list[tuple[str, int, int]] = []
    for idx, (heading, start) in enumerate(steps):
        if idx + 1 < len(steps):
            end = steps[idx + 1][1]
        else:
            end = len(lines)
        boundaries.append((heading, start, end))

    return boundaries


def _build_annotation(
    req_ids: list[str],
    summaries: dict[str, str],
) -> list[str]:
    """Build the annotation blockquote lines for a step."""
    parts: list[str] = []
    for req_id in req_ids:
        summary = summaries.get(req_id, "behavior updated")
        parts.append(f"{req_id}: {summary}")

    annotation_text = "; ".join(parts)
    return [
        "",
        f"> **{ANNOTATION_MARKER}** {annotation_text}. See SYSTEMS_PLAN.md for current requirement text.",
        "",
    ]
