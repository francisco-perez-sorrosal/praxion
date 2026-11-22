"""The weekly liveness workflow's header no longer says any of its jobs is red by design.

Once the selection audit passes on a commit whose every dependency is selected, a red audit job,
or a red audit-gated scenario, is news like any other job's red. The workflow's header comment,
which a reader of the weekly run consults first, says nothing that expects a job to be red.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "gate-liveness.yml"
_RED = re.compile(r"\bred\b", re.IGNORECASE)
_EXPECTED = re.compile(r"\bby design\b|\bevery week\b", re.IGNORECASE)
_CLAUSE_END = re.compile(r"(?<=[.;:])\s+")


def header_clauses() -> list[str]:
    """The workflow's leading comment block, as one text split into clauses."""
    lines = []
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line.lstrip("#").strip())
    return [clause for clause in _CLAUSE_END.split(" ".join(lines)) if clause]


def test_the_header_expects_no_job_to_be_red():
    expecting_red = [c for c in header_clauses() if _RED.search(c) and _EXPECTED.search(c)]

    assert expecting_red == [], f"the header still expects a red job: {expecting_red}"
