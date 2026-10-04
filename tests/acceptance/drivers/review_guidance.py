"""Driver that reads the review checks Praxion's diagramming guidance names.

The checks live in one file, `skills/likec4-diagramming/references/review-checks.md`,
as the Markdown table under its `## Review checks` heading, with the columns
`| Id | Check | Evidence | Pass condition |`. The driver turns each row into a
`ReviewCheck`; the scenarios then judge the checks against the specification. A file
or table that is not there yet is a failed assertion naming where it is expected, so
a scenario reports the missing guidance rather than a driver error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONVENTIONS_ENTRY_POINT = REPO_ROOT / "rules" / "writing" / "diagram-conventions.md"
REVIEW_CHECKS_FILE = REPO_ROOT / "skills" / "likec4-diagramming" / "references" / "review-checks.md"

_SECTION_HEADING = "## Review checks"
_COLUMNS = ["Id", "Check", "Evidence", "Pass condition"]
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


@dataclass(frozen=True)
class ReviewCheck:
    name: str
    evidence: str
    pass_condition: str
    source: Path  # the file the check is stated in

    @property
    def text(self) -> str:
        return f"{self.name} {self.evidence} {self.pass_condition}"


def _cells(row: str) -> list[str]:
    inner = row.strip().removeprefix("|").removesuffix("|")
    return [cell.strip().replace("\\|", "|") for cell in _UNESCAPED_PIPE.split(inner)]


def _table_rows_under_heading(text: str) -> list[list[str]]:
    """The cell lists of the first table after the section heading (header and rule included)."""
    lines = iter(text.splitlines())
    for line in lines:
        if line.strip() == _SECTION_HEADING:
            break
    rows: list[list[str]] = []
    for line in lines:
        if line.startswith("#"):
            break
        if line.lstrip().startswith("|"):
            rows.append(_cells(line))
        elif rows:
            break
    return rows


def review_checks() -> list[ReviewCheck]:
    """The checks of the guidance's review-check table; raises AssertionError when absent."""
    where = REVIEW_CHECKS_FILE.relative_to(REPO_ROOT).as_posix()
    expected = f"{where} with a '{_SECTION_HEADING}' table of columns {' | '.join(_COLUMNS)}"
    assert REVIEW_CHECKS_FILE.is_file(), f"the guidance names no review checks: expected {expected}"
    rows = _table_rows_under_heading(REVIEW_CHECKS_FILE.read_text(encoding="utf-8"))
    header = rows[0] if rows else []
    assert header == _COLUMNS, f"{where} has no review-check table: expected {expected}"
    return [
        ReviewCheck(
            name=f"{ident} {check}",
            evidence=evidence,
            pass_condition=pass_condition,
            source=REVIEW_CHECKS_FILE,
        )
        for ident, check, evidence, pass_condition in (
            row for row in rows[2:] if len(row) == len(_COLUMNS)
        )
    ]
