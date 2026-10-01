"""The footprint-criteria reference teaches a table pair; its worked example must parse clean.

The failure mode this closes: the reference's example drifting out of the grammar
(a renamed column, a new required cell), so the architect copies a table that the
check then rejects. The example is the first fenced block of the reference; it is
read through the shipped `parse_spec_tables`, wrapped in the `## Acceptance
Criteria` section the grammar requires. The canary blanks one cell of the same
example and expects a finding, which shows this test can fail.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _footprint_grammar as fg  # noqa: E402

REFERENCE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "spec-driven-development"
    / "references"
    / "footprint-criteria.md"
)
SPEC_PREAMBLE = "# Plan\n\n## Acceptance Criteria\n\n- [ ] The change behaves\n\n"
FENCE = re.compile(r"^```[a-z]*\n(.*?)^```$", re.DOTALL | re.MULTILINE)
LIMIT_COLUMN = 5  # position of the Limit cell in a criteria row, counting the leading pipe


def worked_example() -> str:
    match = FENCE.search(REFERENCE.read_text(encoding="utf-8"))
    assert match, "the reference holds no fenced worked example"
    return match.group(1)


def as_spec(example: str) -> str:
    return SPEC_PREAMBLE + example


def blank_limit_of_first_criterion(example: str) -> str:
    lines = example.split("\n")
    row = next(i for i, line in enumerate(lines) if line.startswith("| FC-"))
    cells = lines[row].split(" | ")
    cells[LIMIT_COLUMN - 1] = ""
    lines[row] = " | ".join(cells)
    return "\n".join(lines)


def test_example_parses_with_no_finding_and_carries_both_tables():
    parsed = fg.parse_spec_tables(as_spec(worked_example()))

    assert parsed.findings == (), [f.message for f in parsed.findings]
    assert len(parsed.criteria) >= 2, "the example should show a baseline and a reference row"
    assert {type(c.against) for c in parsed.criteria} == {fg.Baseline, fg.Reference}
    assert parsed.not_measured, "the example should show a declared not-measured footprint"


def test_canary_blanking_one_cell_of_the_example_draws_a_finding():
    broken = blank_limit_of_first_criterion(worked_example())

    parsed = fg.parse_spec_tables(as_spec(broken))

    assert [f.reason for f in parsed.findings] == ["missing-cell"]


def test_reference_points_to_the_normative_docstrings_and_not_to_a_copy():
    text = REFERENCE.read_text(encoding="utf-8")

    assert "scripts/_footprint_grammar.py" in text
    assert "scripts/check_footprint_criteria.py" in text
