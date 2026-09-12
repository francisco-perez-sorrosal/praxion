"""Tests for check_state_corpus.py -- DL01/DL02/SH01/SH02/CA01 gate-liveness canary.

Each test builds the minimal `.ai-state/` substrate a check needs under
`tmp_path`. One test per check id, plus DL01's dedicated three-arm-plus-
failing-case set.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_state_corpus import CHECK_IDS, classify  # noqa: E402

_ADR_FRONTMATTER = """---
id: dec-001
title: Example decision
status: accepted
category: architectural
date: 2026-01-01
summary: A summary sentence.
tags: [example]
made_by: agent
---

## Context
"""


def _write_finalized_adr(
    decisions_dir: Path, name: str, frontmatter: str = _ADR_FRONTMATTER
) -> Path:
    decisions_dir.mkdir(parents=True, exist_ok=True)
    path = decisions_dir / name
    path.write_text(frontmatter, encoding="utf-8")
    return path


def _write_spec(specs_dir: Path, name: str, body: str) -> Path:
    specs_dir.mkdir(parents=True, exist_ok=True)
    path = specs_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def test_check_ids_declares_the_five_corpus_checks() -> None:
    assert CHECK_IDS == ("DL01", "DL02", "SH01", "SH02", "CA01")


def test_no_decisions_dir_skips_dl01_and_dl02(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["DL01"]["reason"] == "substrate-absent"
    assert report["skipped"]["DL02"]["reason"] == "substrate-absent"


def test_no_specs_dir_skips_sh01_and_sh02(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["SH01"]["reason"] == "substrate-absent"
    assert report["skipped"]["SH02"]["reason"] == "substrate-absent"


def test_no_calibration_log_skips_ca01(tmp_path: Path) -> None:
    report = classify(tmp_path)
    assert report["skipped"]["CA01"]["reason"] == "substrate-absent"


# -- DL01: three-way OR -----------------------------------------------------


def test_dl01_arm3_no_archived_specs_is_vacuously_clean(tmp_path: Path) -> None:
    """Arm 3: no archived specs at all -- DL01 has nothing to reconcile."""
    (tmp_path / ".ai-state" / "decisions").mkdir(parents=True)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "DL01"] == []


def test_dl01_arm1_finalized_adr_present_is_clean(tmp_path: Path) -> None:
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_x_2026-01-01.md", "# SPEC\n")
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "DL01"] == []


def test_dl01_arm2_draft_fragment_present_is_clean(tmp_path: Path) -> None:
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_x_2026-01-01.md", "# SPEC\n")
    drafts = tmp_path / ".ai-state" / "decisions" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "20260101-1200-alice-main-example-slug.md").write_text(
        _ADR_FRONTMATTER, encoding="utf-8"
    )
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "DL01"] == []


def test_dl01_failing_case_specs_exist_no_adrs_at_all(tmp_path: Path) -> None:
    """Neither arm holds: archived specs exist, .ai-state/decisions/ is empty."""
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_x_2026-01-01.md", "# SPEC\n")
    (tmp_path / ".ai-state" / "decisions").mkdir(parents=True)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "DL01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "warn"


# -- DL02: 8-field non-empty sweep -------------------------------------------


def test_dl02_well_formed_adr_is_clean(tmp_path: Path) -> None:
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "DL02"] == []


def test_dl02_golden_bad_case_empty_summary_field(tmp_path: Path) -> None:
    """Golden bad-case: all 8 keys present, `summary:` is empty."""
    frontmatter = _ADR_FRONTMATTER.replace("summary: A summary sentence.", "summary:")
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md", frontmatter)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "DL02"]
    assert len(findings) == 1
    assert "summary" in findings[0]["message"]


def test_dl02_empty_tags_list_counts_as_absent(tmp_path: Path) -> None:
    frontmatter = _ADR_FRONTMATTER.replace("tags: [example]", "tags: []")
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md", frontmatter)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "DL02"]
    assert len(findings) == 1
    assert "tags" in findings[0]["message"]


def test_dl02_block_style_tags_list_is_not_a_false_positive(tmp_path: Path) -> None:
    """A multi-line YAML block list for `tags:` must not read as empty."""
    frontmatter = _ADR_FRONTMATTER.replace("tags: [example]", "tags:\n  - a\n  - b")
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md", frontmatter)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "DL02"] == []


def test_dl02_no_frontmatter_block_is_flagged(tmp_path: Path) -> None:
    _write_finalized_adr(tmp_path / ".ai-state" / "decisions", "001-example.md", "# Not an ADR\n")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "DL02"]
    assert len(findings) == 1
    assert "no YAML frontmatter" in findings[0]["message"]


# -- SH01: path-column convention --------------------------------------------


_SPEC_HEADER = "# SPEC: Example\n\n## Feature Summary\n\nBody.\n\n"


def test_sh01_conforming_path_column_is_clean(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_state_corpus.py").write_text("", encoding="utf-8")
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | `scripts/check_state_corpus.py` | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "SH01"] == []


def test_sh01_dangling_reference_fails(tmp_path: Path) -> None:
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | `scripts/does_not_exist.py` | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "SH01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "fail"


def test_sh01_non_backtick_cell_is_non_conforming(tmp_path: Path) -> None:
    """Golden bad-case: a path-column cell with no backtick token at all."""
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | see the check script | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "SH01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "warn"


def test_sh01_double_colon_pointer_in_path_column_is_non_conforming(tmp_path: Path) -> None:
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | `scripts/test_x.py::test_y` | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "SH01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "warn"


def test_sh01_double_colon_pointer_in_test_column_is_not_scanned(tmp_path: Path) -> None:
    """`::` pointers are fine in a column that is not the path column."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_state_corpus.py").write_text("", encoding="utf-8")
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Test(s) | Implementation |\n|---|---|---|\n"
        + "| R1 | `scripts/test_x.py::test_y` | `scripts/check_state_corpus.py` |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "SH01"] == []


def test_sh01_em_dash_cell_claims_no_path(tmp_path: Path) -> None:
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | — (no artifact) | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "SH01"] == []


def test_sh01_directory_reference_is_a_valid_path_shape(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation | Notes |\n|---|---|---|\n"
        + "| R1 | `scripts/` | fine |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "SH01"] == []


# -- SH02: traceability matrix presence --------------------------------------


def test_sh02_matrix_with_data_row_is_clean(tmp_path: Path) -> None:
    body = (
        _SPEC_HEADER
        + "## Traceability Matrix\n\n"
        + "| Req | Implementation |\n|---|---|\n| R1 | `scripts/check_state_corpus.py` |\n"
    )
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "SH02"] == []


def test_sh02_golden_bad_case_prose_only_no_matrix(tmp_path: Path) -> None:
    """Golden bad-case: a `## Traceability` section of one sentence, no table."""
    body = _SPEC_HEADER + "## Traceability\n\nCovered elsewhere, no matrix here.\n"
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", body)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "SH02"]
    assert len(findings) == 1


def test_sh02_no_traceability_section_at_all(tmp_path: Path) -> None:
    _write_spec(tmp_path / ".ai-state" / "specs", "SPEC_a_2026-01-01.md", _SPEC_HEADER)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "SH02"]
    assert len(findings) == 1
    assert "no '## Traceability" in findings[0]["message"]


# -- CA01: calibration log format --------------------------------------------


_CALIBRATION_HEADER = (
    "| Timestamp | Task | Signals | Recommended Tier | Actual Tier | Source | Retrospective |\n"
)
_CALIBRATION_SEPARATOR = "|---|---|---|---|---|---|---|\n"


def test_ca01_valid_log_with_data_row_is_clean(tmp_path: Path) -> None:
    log = (
        "# Calibration Log\n\n"
        + _CALIBRATION_HEADER
        + _CALIBRATION_SEPARATOR
        + "| 2026-01-01 | x | y | Standard | Standard | agent | correct |\n"
    )
    (tmp_path / ".ai-state").mkdir(parents=True)
    (tmp_path / ".ai-state" / "calibration_log.md").write_text(log, encoding="utf-8")
    report = classify(tmp_path)
    assert [f for f in report["findings"] if f["check"] == "CA01"] == []


def test_ca01_header_mismatch_fails(tmp_path: Path) -> None:
    log = "# Calibration Log\n\n| Wrong | Columns |\n|---|---|\n| a | b |\n"
    (tmp_path / ".ai-state").mkdir(parents=True)
    (tmp_path / ".ai-state" / "calibration_log.md").write_text(log, encoding="utf-8")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "CA01"]
    assert len(findings) == 1


def test_ca01_no_data_rows_fails(tmp_path: Path) -> None:
    log = "# Calibration Log\n\n" + _CALIBRATION_HEADER + _CALIBRATION_SEPARATOR
    (tmp_path / ".ai-state").mkdir(parents=True)
    (tmp_path / ".ai-state" / "calibration_log.md").write_text(log, encoding="utf-8")
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "CA01"]
    assert len(findings) == 1
