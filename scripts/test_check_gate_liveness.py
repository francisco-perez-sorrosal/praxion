"""Canary for the Gate Liveness detector (GL02 forbidden-pattern-contradiction).

Cites: rules/swe/gate-liveness.md — a CODE gate ships a canary proving it fails on
a known-bad input, not merely passes on the current good state. These tests feed
the detector deliberately bad fixtures and assert it flags them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import check_gate_liveness as gl  # noqa: E402


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_flags_dead_grep_contradiction(tmp_path: Path) -> None:
    """A canary: an instruction greps test files for a forbidden REQ test-name."""
    _write(
        tmp_path,
        "agents/planner.md",
        "At checkpoints, scan test files for req33_ patterns to find untested REQs.",
    )
    findings = gl.check_forbidden_pattern(tmp_path)
    assert findings, "GL02 must flag a grep for a pattern forbidden in test files"
    assert findings[0]["check"] == "forbidden-pattern"


def test_accepts_traceability_read_instead_of_grep(tmp_path: Path) -> None:
    """Happy path: reading the traceability file (not grepping code) is fine."""
    _write(
        tmp_path,
        "agents/planner.md",
        "At checkpoints, read traceability.yml to find REQs with empty tests lists.",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


def test_forbidden_pattern_respects_ignore_escape(tmp_path: Path) -> None:
    """A line marked gate-liveness:ignore is a deliberate reference, not a gate."""
    _write(
        tmp_path,
        "agents/doc.md",
        "Detectors may scan test code for req10_ shapes. gate-liveness:ignore",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


def test_excludes_pattern_defining_files(tmp_path: Path) -> None:
    """The defining rules describe the forbidden patterns; they are not dead gates."""
    _write(
        tmp_path,
        "rules/swe/id-citation-discipline.md",
        "Never scan test files for req33_ — this rule forbids it.",
    )
    assert gl.check_forbidden_pattern(tmp_path) == []


def test_cli_exits_nonzero_on_findings(tmp_path: Path) -> None:
    """A canary for the exit-code gate contract: bad input → exit 1."""
    _write(tmp_path, "agents/planner.md", "scan test files for req33_ patterns.")
    assert gl.main(["--root", str(tmp_path), "--check", "forbidden-pattern"]) == 1


def test_cli_exits_zero_when_clean(tmp_path: Path) -> None:
    """Happy path: a clean corpus exits 0."""
    _write(tmp_path, "agents/planner.md", "Read traceability.yml for coverage.")
    assert gl.main(["--root", str(tmp_path), "--check", "all"]) == 0
