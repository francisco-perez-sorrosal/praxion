"""Tests for check_sentinel_self_audit.py -- V01/V02/V03/V04 gate-liveness canary.

Each test builds a minimal substrate tree under `tmp_path` (plugin.json /
coordination-details.md / README.md / sentinel.md) rather than pointing at the live
repo -- the golden bad-cases construct the exact hollow shapes each check exists to
catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_sentinel_self_audit import CHECK_IDS, classify  # noqa: E402


def _write_plugin_json(tmp_path: Path, agents: list[str]) -> None:
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps({"agents": agents}), encoding="utf-8")


def _write_roster(tmp_path: Path, include_sentinel: bool) -> None:
    roster_dir = tmp_path / "skills" / "software-planning" / "references"
    roster_dir.mkdir(parents=True, exist_ok=True)
    rows = "| `researcher` | ... | Yes |\n"
    if include_sentinel:
        rows += "| `sentinel` | ... | Yes |\n"
    text = f"## Agent Roster\n\n| Agent | Output | Bg Safe |\n|---|---|---|\n{rows}\n## Next\n"
    (roster_dir / "coordination-details.md").write_text(text, encoding="utf-8")


def _write_readme(tmp_path: Path, include_sentinel: bool) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    rows = "| `researcher` | Explores codebases | - |\n"
    if include_sentinel:
        rows += "| `sentinel` | Read-only auditor | - |\n"
    text = f"| Agent | Description | Skills |\n|---|---|---|\n{rows}"
    (agents_dir / "README.md").write_text(text, encoding="utf-8")


def _write_sentinel_md(tmp_path: Path, body: str) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "sentinel.md").write_text(body, encoding="utf-8")


_POPULATED_CATALOG = """\
## Check Catalog

### Completeness (C)

| ID | Tp | Rule | Pass |
|----|----|------|------|
| C01 | A | Rule text | Pass text |

### Self-Verification (V)

| ID | Tp | Rule | Pass |
|----|----|------|------|
| V01 | A | Rule text | Pass text |

## Process
"""


def _full_tree(tmp_path: Path, *, sentinel_body: str = _POPULATED_CATALOG) -> None:
    _write_plugin_json(tmp_path, ["./agents/sentinel.md"])
    _write_roster(tmp_path, include_sentinel=True)
    _write_readme(tmp_path, include_sentinel=True)
    _write_sentinel_md(tmp_path, sentinel_body)


def test_check_ids_declares_v01_through_v04() -> None:
    assert CHECK_IDS == ("V01", "V02", "V03", "V04")


# -- V01 ------------------------------------------------------------------------


def test_v01_passes_when_sentinel_in_plugin_agents_array(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "V01"] == []


def test_v01_flags_missing_sentinel_from_plugin_agents_array(tmp_path: Path) -> None:
    """Golden bad-case: plugin.json exists but omits the sentinel agent entry."""
    _full_tree(tmp_path)
    _write_plugin_json(tmp_path, ["./agents/researcher.md"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_v01_skips_when_plugin_json_absent(tmp_path: Path) -> None:
    _write_roster(tmp_path, include_sentinel=True)
    _write_readme(tmp_path, include_sentinel=True)
    _write_sentinel_md(tmp_path, _POPULATED_CATALOG)
    report = classify(tmp_path)
    assert report["skipped"]["V01"]["reason"] == "substrate-absent"


# -- V02 ------------------------------------------------------------------------


def test_v02_passes_when_roster_has_sentinel_row(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "V02"] == []


def test_v02_flags_missing_sentinel_row_in_roster(tmp_path: Path) -> None:
    """Golden bad-case: the roster table exists but has no sentinel row."""
    _full_tree(tmp_path)
    _write_roster(tmp_path, include_sentinel=False)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V02"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_v02_skips_when_roster_file_absent(tmp_path: Path) -> None:
    _write_plugin_json(tmp_path, ["./agents/sentinel.md"])
    _write_readme(tmp_path, include_sentinel=True)
    _write_sentinel_md(tmp_path, _POPULATED_CATALOG)
    report = classify(tmp_path)
    assert report["skipped"]["V02"]["reason"] == "substrate-absent"


# -- V03 ------------------------------------------------------------------------


def test_v03_passes_when_readme_has_sentinel_row(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "V03"] == []


def test_v03_flags_missing_sentinel_row_in_readme(tmp_path: Path) -> None:
    """Golden bad-case: agents/README.md's table has no sentinel row."""
    _full_tree(tmp_path)
    _write_readme(tmp_path, include_sentinel=False)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V03"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_v03_skips_when_readme_absent(tmp_path: Path) -> None:
    _write_plugin_json(tmp_path, ["./agents/sentinel.md"])
    _write_roster(tmp_path, include_sentinel=True)
    _write_sentinel_md(tmp_path, _POPULATED_CATALOG)
    report = classify(tmp_path)
    assert report["skipped"]["V03"]["reason"] == "substrate-absent"


# -- V04 ------------------------------------------------------------------------


def test_v04_passes_when_catalog_populated_across_all_dimensions(tmp_path: Path) -> None:
    _full_tree(tmp_path)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "V04"] == []


def test_v04_flags_missing_check_catalog_heading(tmp_path: Path) -> None:
    """Golden bad-case: the sentinel definition has no '## Check Catalog' heading at all."""
    _full_tree(tmp_path, sentinel_body="## Process\n\nNo catalog here.\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V04"]
    assert len(findings) == 1
    assert "not found" in findings[0]["message"]


def test_v04_flags_dimension_heading_left_standing_with_no_rows(tmp_path: Path) -> None:
    """Golden bad-case: a dimension heading survives mid-edit after its rows were cut --
    the catalog still lists the dimension, and nothing under it ever runs."""
    hollow_catalog = """\
## Check Catalog

### Completeness (C)

| ID | Tp | Rule | Pass |
|----|----|------|------|
| C01 | A | Rule text | Pass text |

### Self-Verification (V)

## Process
"""
    _full_tree(tmp_path, sentinel_body=hollow_catalog)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V04"]
    assert len(findings) == 1
    assert "Self-Verification (V)" in findings[0]["message"]


def test_v04_flags_catalog_heading_present_with_no_rows_beneath_it(tmp_path: Path) -> None:
    """Golden bad-case: presence-only pass on a hollow catalog -- an auditor auditing
    nothing."""
    _full_tree(
        tmp_path, sentinel_body="## Check Catalog\n\nNo dimensions, no rows.\n\n## Process\n"
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "V04"]
    assert len(findings) == 1
    assert "no check-ID rows" in findings[0]["message"]


def test_v04_skips_when_sentinel_md_absent(tmp_path: Path) -> None:
    _write_plugin_json(tmp_path, ["./agents/sentinel.md"])
    _write_roster(tmp_path, include_sentinel=True)
    _write_readme(tmp_path, include_sentinel=True)
    report = classify(tmp_path)
    assert report["skipped"]["V04"]["reason"] == "substrate-absent"
