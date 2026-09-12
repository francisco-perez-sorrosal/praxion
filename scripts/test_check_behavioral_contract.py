"""Tests for check_behavioral_contract.py -- BC01/BC03/BC04 canary.

Each test builds a minimal substrate tree under `tmp_path` (rules/swe/,
agents/, skills/code-review/references/) rather than pointing at the live
repo -- the golden bad-cases construct the exact drifted shapes each check
exists to detect.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_behavioral_contract import CHECK_IDS, classify  # noqa: E402

_RULE_TEXT = (
    "## Agent Behavioral Contract\n\n"
    "Four non-negotiable behaviors: Surface Assumptions, Register Objection, "
    "Stay Surgical, Simplicity First.\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_ids_declares_all_three() -> None:
    assert CHECK_IDS == ("BC01", "BC03", "BC04")


# -- BC01 -----------------------------------------------------------------------


def test_bc01_flags_paths_frontmatter_and_missing_behavior(tmp_path: Path) -> None:
    """A `paths:`-scoped rule that also drops one behavior should be caught
    by both clauses at once."""
    _write(
        tmp_path / "rules" / "swe" / "agent-behavioral-contract.md",
        "---\npaths: '*.py'\n---\n\n## Contract\n\nSurface Assumptions, "
        "Register Objection, Stay Surgical.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC01"]
    assert any("paths:" in f["message"] for f in findings)
    assert any("Simplicity First" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_bc01_detects_missing_rule_file(tmp_path: Path) -> None:
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC01"]
    assert any("does not exist" in f["message"] for f in findings)


# -- BC03 -----------------------------------------------------------------------


def test_bc03_flags_missing_and_extra_citer(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "agent-behavioral-contract.md", _RULE_TEXT)
    _write(
        tmp_path / "agents" / "researcher.md",
        "See `rules/swe/agent-behavioral-contract.md` for the contract.\n",
    )
    # "verifier" is contract-bound but does not cite the rule -- missing.
    _write(tmp_path / "agents" / "verifier.md", "No citation here.\n")
    # "promethean" is not contract-bound but cites the rule anyway -- extra.
    _write(
        tmp_path / "agents" / "promethean.md",
        "See `rules/swe/agent-behavioral-contract.md` for the contract.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC03"]
    entities = {f["entity"] for f in findings}
    assert "verifier" in entities
    assert "promethean" in entities
    assert all(f["severity"] == "fail" for f in findings)


# -- BC04 -----------------------------------------------------------------------


def test_bc04_flags_missing_tag_in_subsection(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "code-review" / "references" / "report-template.md",
        "## Report\n\n"
        "### Behavioral Contract Findings\n\n"
        "Tags: [UNSURFACED-ASSUMPTION], [MISSING-OBJECTION], [NON-SURGICAL], "
        "[SCOPE-CREEP], [BLOAT].\n\n"
        "### Next Section\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC04"]
    assert findings == [
        {
            "check": "BC04",
            "severity": "fail",
            "entity": "[DEAD-CODE-UNREMOVED]",
            "message": "'[DEAD-CODE-UNREMOVED]' missing from the Behavioral Contract "
            "Findings subsection of skills/code-review/references/report-template.md",
        }
    ]


def test_bc04_rejects_missing_heading(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "code-review" / "references" / "report-template.md",
        "## Report\n\nNo such subsection here.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC04"]
    assert any("heading not found" in f["message"] for f in findings)
