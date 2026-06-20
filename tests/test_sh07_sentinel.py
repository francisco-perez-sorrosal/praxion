"""Tests for the SH07 sentinel call-site contract in scripts/check_spec_drift.py.

These tests verify the *wiring* of SH07 — the thin wrapper that calls detect_drift
over archived specs and emits sentinel-formatted findings. They do NOT re-test
detector logic (covered by tests/test_spec_drift.py).

# Assumed call-site contract (Step 6 must honor):
#
#   from scripts.check_spec_drift import run_sh07
#
#   def run_sh07(repo_root: Path) -> list[dict]:
#       \"\"\"Run SH07 check over .ai-state/specs/ under repo_root.
#
#       Returns a list of sentinel finding dicts, each with:
#           {
#               "check": "SH07",
#               "severity": "info" | "important" | "suggested",
#               "message": str,
#           }
#       Returns [] (empty list) when .ai-state/specs/ is absent (INFO skip).
#       Orphaned-edge findings from detect_drift are filtered out (deferred to SH01/SH04).
#       \"\"\"
#
# Step 6 implementer must:
#   1. Create scripts/check_spec_drift.py with a run_sh07(repo_root: Path) callable.
#   2. When .ai-state/specs/ is absent, return [] or a single info-severity row.
#   3. For each non-orphaned-edge finding from detect_drift, emit a sentinel row
#      mapping severity: "important" -> "important", "suggested" -> "suggested".
#   4. For orphaned-edge findings, do NOT emit a row (defer to SH01/SH04).
#
# All three imports are deferred into each test body so pytest collection succeeds
# before scripts/check_spec_drift.py exists (required RED handshake in BDD/TDD mode).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Sentinel output shape helpers
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"info", "important", "suggested"}


def _assert_sentinel_row(row: dict) -> None:
    assert "check" in row, f"sentinel row missing 'check' key: {row!r}"
    assert row["check"] == "SH07", f"expected check=SH07, got {row['check']!r}"
    assert "severity" in row, f"sentinel row missing 'severity' key: {row!r}"
    assert row["severity"] in _VALID_SEVERITIES, (
        f"severity must be one of {_VALID_SEVERITIES!r}, got {row['severity']!r}"
    )
    assert "message" in row, f"sentinel row missing 'message' key: {row!r}"
    assert isinstance(row["message"], str) and row["message"], "message must be a non-empty string"


# ---------------------------------------------------------------------------
# Test: SH07 skips cleanly when .ai-state/specs/ is absent
# ---------------------------------------------------------------------------


def test_sh07_skips_when_no_specs_dir(tmp_path: Path) -> None:
    """With no .ai-state/specs/ under repo_root, SH07 produces zero findings.

    The sentinel should not error — it silently skips (INFO-level) when there
    is nothing to scan. The caller receives an empty list or a single info row;
    either way, no important/suggested findings are emitted.
    """
    # Arrange: repo root with no .ai-state/specs/ directory
    (tmp_path / ".ai-state").mkdir()
    # specs/ intentionally absent

    from scripts.check_spec_drift import run_sh07  # deferred import: RED trigger

    # Act
    results = run_sh07(tmp_path)

    # Assert: no important or suggested findings (zero or one info-level skip row)
    important_or_suggested = [r for r in results if r.get("severity") in ("important", "suggested")]
    assert not important_or_suggested, (
        f"Expected zero important/suggested rows when specs/ absent, got: {important_or_suggested!r}"
    )
    # Any emitted rows must still be valid sentinel rows
    for row in results:
        _assert_sentinel_row(row)


# ---------------------------------------------------------------------------
# Test: SH07 renders detector findings as sentinel rows with correct severity
# ---------------------------------------------------------------------------


def test_sh07_surfaces_findings_from_detector(tmp_path: Path) -> None:
    """When detect_drift returns a stale-dependent finding, SH07 renders a sentinel row.

    Verifies the severity mapping: detector 'important' -> sentinel 'important'.
    The test patches detect_drift so only wiring is exercised, not detector logic.
    """
    # Arrange: repo root with a specs/ dir so SH07 doesn't skip
    specs_dir = tmp_path / ".ai-state" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "SPEC_my-feature_2026-01-01.md").write_text("# Spec\n## Traceability\n")

    canned_finding = {
        "kind": "stale-dependent",
        "scope": "archived:SPEC_my-feature_2026-01-01.md",
        "req": "REQ-01",
        "source_changed": "skills/auth.md",
        "stale_dependents": ["tests/test_auth.py"],
        "severity": "important",
        "pointer": ".ai-state/specs/SPEC_my-feature_2026-01-01.md",
        "rationale": "REQ-01 clause changed; tests/test_auth.py not updated",
    }

    from scripts.check_spec_drift import run_sh07  # deferred import: RED trigger

    with patch("scripts.check_spec_drift.detect_drift", return_value=[canned_finding]):
        results = run_sh07(tmp_path)

    # Assert: at least one important sentinel row
    important_rows = [r for r in results if r.get("severity") == "important"]
    assert important_rows, (
        f"Expected at least one important sentinel row from a stale-dependent finding; "
        f"got: {results!r}"
    )
    for row in important_rows:
        _assert_sentinel_row(row)
    # The row must mention the REQ or the finding pointer so the operator can navigate
    combined_messages = " ".join(r["message"] for r in important_rows)
    assert "REQ-01" in combined_messages or "SPEC_my-feature" in combined_messages, (
        f"Sentinel row message should reference the finding's REQ or SPEC pointer; "
        f"got messages: {combined_messages!r}"
    )


# ---------------------------------------------------------------------------
# Test: SH07 defers orphaned-edge findings to SH01/SH04 (does not emit them)
# ---------------------------------------------------------------------------


def test_sh07_defers_orphaned_edge_to_sh01(tmp_path: Path) -> None:
    """Orphaned-edge findings are silently dropped by SH07 — deferred to SH01/SH04.

    This ensures no duplication between SH07 and the existing orphaned-edge
    checks. The detector may return orphaned-edge entries for archived scope,
    but SH07 must filter them before emitting sentinel rows.
    """
    # Arrange: repo root with a specs/ dir
    specs_dir = tmp_path / ".ai-state" / "specs"
    specs_dir.mkdir(parents=True)
    (specs_dir / "SPEC_other-feature_2026-02-01.md").write_text("# Spec\n")

    orphaned_finding = {
        "kind": "orphaned-edge",
        "scope": "archived:SPEC_other-feature_2026-02-01.md",
        "req": "REQ-05",
        "source_changed": "",
        "stale_dependents": ["tests/test_deleted.py"],
        "severity": "important",
        "pointer": ".ai-state/specs/SPEC_other-feature_2026-02-01.md",
        "rationale": "Mapped test path deleted; no longer on disk",
    }

    from scripts.check_spec_drift import run_sh07  # deferred import: RED trigger

    with patch("scripts.check_spec_drift.detect_drift", return_value=[orphaned_finding]):
        results = run_sh07(tmp_path)

    # Assert: zero rows — orphaned-edge is wholly deferred
    non_info = [r for r in results if r.get("severity") != "info"]
    assert not non_info, (
        f"SH07 must not emit rows for orphaned-edge findings (deferred to SH01/SH04); "
        f"got non-info rows: {non_info!r}"
    )
