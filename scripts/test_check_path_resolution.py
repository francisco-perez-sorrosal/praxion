"""Tests for check_path_resolution.py -- F01/F02/F05/X03/X09 canary.

Each test builds a minimal substrate tree under `tmp_path` (skills/ / agents/ /
commands/ / rules/ / CLAUDE.md / .ai-state/SYSTEM_DEPLOYMENT.md /
.ai-state/decisions/) rather than pointing at the live repo -- the golden
bad-cases construct the exact drifted shapes each check exists to detect.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_path_resolution import CHECK_IDS, classify  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_ids_declares_all_five() -> None:
    assert CHECK_IDS == ("F01", "F02", "F05", "X03", "X09")


# -- F01 ----------------------------------------------------------------------


def test_f01_passes_when_referenced_files_exist(tmp_path: Path) -> None:
    _write(tmp_path / "scripts" / "check_x.py", "# x\n")
    _write(tmp_path / "skills" / "widget" / "SKILL.md", "See `scripts/check_x.py` for details.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F01"] == []


def test_f01_flags_missing_referenced_file(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md", "See `scripts/check_ghost.py` for details.\n"
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F01"]
    assert any("check_ghost.py" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_f01_ignores_bare_references_tokens(tmp_path: Path) -> None:
    """Bare `references/...` mentions are F02's scope, not F01's -- they are
    relative to the citing skill's own directory, not the repo root."""
    _write(tmp_path / "skills" / "widget" / "SKILL.md", "See `references/ghost.md` for details.\n")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F01"] == []


def test_f01_skips_when_no_surface_present(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["F01"]["reason"] == "substrate-absent"


# -- F02 ----------------------------------------------------------------------


def test_f02_passes_when_own_reference_exists(tmp_path: Path) -> None:
    _write(tmp_path / "skills" / "widget" / "references" / "detail.md", "content\n")
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md",
        "- [references/detail.md](references/detail.md) -- detail\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F02"] == []


def test_f02_flags_missing_own_reference(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md",
        "- [references/ghost.md](references/ghost.md) -- ghost\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F02"]
    assert any("ghost.md" in f["entity"] for f in findings)
    assert all(f["severity"] == "warn" for f in findings)


def test_f02_ignores_a_bare_mention_of_another_skills_leaf(tmp_path: Path) -> None:
    """Light-review E2, F-2: a bare `references/x.md` that exists under another skill is a
    cross-skill mention, not a missing own-leaf; the same mention with no home anywhere
    is still flagged (declared residual)."""
    _write(tmp_path / "skills" / "other" / "references" / "leaf.md", "# leaf\n")
    _write(tmp_path / "skills" / "other" / "SKILL.md", "# other\n")
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md",
        "see `references/leaf.md` and `references/nowhere.md`\n",
    )
    findings = [f for f in classify(tmp_path)["findings"] if f["check"] == "F02"]
    assert [f["entity"] for f in findings] == ["skills/widget:references/nowhere.md"]


def test_f02_ignores_cross_skill_href(tmp_path: Path) -> None:
    """A markdown link's href, not its text, decides own-skill-vs-not: a
    `../other-skill/references/x.md` href is cross-skill even if the link
    text reads like a bare same-skill mention."""
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md",
        "see [`references/ghost.md`](../other-skill/references/ghost.md)\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F02"] == []


def test_f02_ignores_arrow_table_convention(tmp_path: Path) -> None:
    """`` `skill` → `references/x.md` `` names *that* skill's file, not this one's."""
    _write(
        tmp_path / "skills" / "widget" / "SKILL.md",
        "| `other-skill` → `references/ghost.md` | some capability |\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F02"] == []


def test_f02_skips_when_skills_dir_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["F02"]["reason"] == "substrate-absent"


# -- F05 ----------------------------------------------------------------------


def test_f05_passes_when_deployment_doc_paths_resolve(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "runbook.md", "content\n")
    _write(
        tmp_path / ".ai-state" / "SYSTEM_DEPLOYMENT.md",
        "See `docs/runbook.md` for the runbook.\n",
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "F05"] == []


def test_f05_flags_missing_deployment_doc_path(tmp_path: Path) -> None:
    _write(
        tmp_path / ".ai-state" / "SYSTEM_DEPLOYMENT.md",
        "See `docs/ghost.md` for the runbook.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F05"]
    assert any("ghost.md" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_f05_skips_when_deployment_doc_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["F05"]["reason"] == "substrate-absent"


# -- X03 ------------------------------------------------------------------------


def _write_claude_md(tmp_path: Path, heading: str, rows: list[str]) -> None:
    table_rows = "".join(f"| `{r}` | purpose |\n" for r in rows)
    text = f"# Project\n\n{heading}\n\n| Path | Purpose |\n|---|---|\n{table_rows}\n## Next\n"
    _write(tmp_path / "CLAUDE.md", text)


def test_x03_passes_when_structure_dirs_exist(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    _write_claude_md(tmp_path, "## Structure", ["src/"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X03"] == []


def test_x03_flags_missing_structure_dir(tmp_path: Path) -> None:
    _write_claude_md(tmp_path, "## Structure", ["ghost/"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X03"]
    assert any(f["entity"] == "ghost/" for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_x03_accepts_repository_layout_heading(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    _write_claude_md(tmp_path, "## Repository layout", ["src/"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X03"] == []


def test_x03_skips_when_no_structure_section(tmp_path: Path) -> None:
    _write(tmp_path / "CLAUDE.md", "# Project\n\n## Something Else\n\ncontent\n")
    report = classify(tmp_path)
    assert report["skipped"]["X03"]["reason"] == "no-structure-section"


def test_x03_skips_when_claude_md_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["X03"]["reason"] == "substrate-absent"


# -- X09 ------------------------------------------------------------------------


def _write_deployment_doc(tmp_path: Path, dec_ids: list[str]) -> None:
    rows = "".join(f"| [dec-{i}](decisions/{i}-x.md) | decision {i} | impact |\n" for i in dec_ids)
    text = f"## 9. Decisions\n\n| ADR | Decision | Impact |\n|---|---|---|\n{rows}\n## 10. Next\n"
    _write(tmp_path / ".ai-state" / "SYSTEM_DEPLOYMENT.md", text)


def test_x09_passes_when_referenced_decisions_exist(tmp_path: Path) -> None:
    _write(tmp_path / ".ai-state" / "decisions" / "001-widget.md", "content\n")
    _write_deployment_doc(tmp_path, ["001"])
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "X09"] == []


def test_x09_flags_missing_referenced_decision(tmp_path: Path) -> None:
    _write_deployment_doc(tmp_path, ["999"])
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "X09"]
    assert any(f["entity"] == "dec-999" for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_x09_skips_when_no_decisions_section(tmp_path: Path) -> None:
    _write(tmp_path / ".ai-state" / "SYSTEM_DEPLOYMENT.md", "## 1. Overview\n\ncontent\n")
    report = classify(tmp_path)
    assert report["skipped"]["X09"]["reason"] == "no-decisions-section"


def test_x09_skips_when_deployment_doc_absent(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["X09"]["reason"] == "substrate-absent"
