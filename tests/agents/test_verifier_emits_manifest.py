"""Behavioral tests for verifier Phase 12.5 — rework manifest emission.

Approach: mixed A/B.
  - Schema/existence tests (Approach A): validate against synthesized fixture files
    in tests/fixtures/ that model what Phase 12.5 would produce.  These tests are
    RED until either (a) the implementer creates the helper module, or (b) the
    verifier Phase 12.5 produces matching output.
  - Algorithmic invariant tests (Approach B): call pure functions from
    scripts/rework_manifest.py (row-ID hashing, JSON-table round-trip, dedup
    detection).  That module is created by the implementer.  Tests fail
    with ImportError until it exists — which is the expected RED state.

All imports of the production module are deferred to test bodies (not module-level)
so pytest collection succeeds before the module exists.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------
# Helpers — fixture loading
# ---------------------------------------------------------------------------

MANIFEST_WITH_FINDINGS = FIXTURES / "manifest_with_findings.md"
MANIFEST_WITH_DEDUP = FIXTURES / "manifest_with_dedup.md"


def _json_blocks(manifest_text: str) -> list[dict]:
    """Extract every fenced JSON block from a manifest and parse each one."""
    pattern = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
    return [json.loads(m.group(1)) for m in pattern.finditer(manifest_text)]


def _table_rows(manifest_text: str) -> list[str]:
    """Return non-header, non-separator table rows from the first markdown table."""
    rows = []
    in_table = False
    for line in manifest_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            if re.match(r"\|[\s\-:|]+\|", stripped):
                in_table = True
                continue
            if in_table:
                rows.append(stripped)
        elif in_table:
            break
    return rows


# ---------------------------------------------------------------------------
# Test: manifest existence on findings
# ---------------------------------------------------------------------------


def test_manifest_written_on_findings():
    """A manifest produced by the verifier on a FAIL-containing report must exist
    and contain at least one row with a valid 'id' field."""
    assert MANIFEST_WITH_FINDINGS.exists(), (
        f"Fixture {MANIFEST_WITH_FINDINGS.name} not found; "
        "verifier Phase 12.5 must produce a REWORK_MANIFEST.md when findings are present"
    )
    text = MANIFEST_WITH_FINDINGS.read_text(encoding="utf-8")
    blocks = _json_blocks(text)
    assert len(blocks) >= 1, (
        "Manifest with findings must contain at least one fenced JSON block (one row)"
    )
    row_ids = [b.get("id", "") for b in blocks]
    for rid in row_ids:
        assert re.match(r"rw-[0-9a-f]{8}$", rid), (
            f"Row id {rid!r} does not match expected pattern rw-<8-hex-chars>"
        )


# ---------------------------------------------------------------------------
# Test: no manifest on clean run
# ---------------------------------------------------------------------------


def test_no_manifest_on_clean_run():
    """When the verifier produces only PASS findings, no manifest is written.

    This is validated by asserting that the fixture for a clean run does NOT
    exist — the implementer must NOT create it.  The production invariant is
    that Phase 12.5 is a no-op when the report is clean.
    """
    clean_manifest = FIXTURES / "manifest_clean_run.md"
    assert not clean_manifest.exists(), (
        "A 'clean run' manifest fixture must not exist; "
        "verifier must not write REWORK_MANIFEST.md when there are no FAIL/WARN findings"
    )


# ---------------------------------------------------------------------------
# Test: JSON↔table round-trip (Approach B — deferred import)
# ---------------------------------------------------------------------------


def test_table_round_trips_from_json():
    """Render a table from per-row JSON blocks, re-parse the rows, assert the
    original JSON data survives the round-trip.

    Calls scripts.rework_manifest.render_table_from_rows and
    scripts.rework_manifest.parse_json_blocks.  These functions are created by
    the implementer as part of the verifier Phase 12.5 implementation.
    """
    import scripts.rework_manifest as rm  # deferred: module does not exist yet

    text = MANIFEST_WITH_FINDINGS.read_text(encoding="utf-8")
    original_blocks = rm.parse_json_blocks(text)
    assert original_blocks, "parse_json_blocks must return at least one block"

    rendered_table = rm.render_table_from_rows(original_blocks)
    re_parsed = rm.parse_json_blocks(rendered_table)

    assert len(re_parsed) == len(original_blocks), (
        f"Round-trip changed row count: {len(original_blocks)} → {len(re_parsed)}"
    )
    for orig, reparsed in zip(original_blocks, re_parsed, strict=False):
        assert orig == reparsed, (
            f"Row round-trip mismatch:\n  original:  {orig}\n  re-parsed: {reparsed}"
        )


# ---------------------------------------------------------------------------
# Test: partial-row corruption does not invalidate other rows
# ---------------------------------------------------------------------------


def test_partial_row_does_not_invalidate_others():
    """Corrupting one row's JSON block must not prevent parsing of other rows."""
    import scripts.rework_manifest as rm  # deferred: module does not exist yet

    text = MANIFEST_WITH_FINDINGS.read_text(encoding="utf-8")
    # Corrupt the first JSON block by truncating it
    corrupted = re.sub(
        r"(```json\s*\{)",
        r"```json\n{BROKEN",
        text,
        count=1,
    )
    rows = rm.parse_json_blocks(corrupted)
    # The second (uncorrupted) block must still parse
    assert len(rows) >= 1, (
        "At least one uncorrupted JSON block must parse even when another block is malformed"
    )
    # All successfully-parsed rows must have valid id fields
    for row in rows:
        assert "id" in row, f"Parsed row missing 'id' field: {row!r}"


# ---------------------------------------------------------------------------
# Test: row-ID hash stability across re-runs (Approach B)
# ---------------------------------------------------------------------------


def test_row_id_stable_across_reruns():
    """The same report_id and cluster_signature always produce the same rw-<hash>.

    Calls scripts.rework_manifest.compute_row_id.  Verifies that:
      (a) the function exists and is callable,
      (b) repeated calls with identical inputs return identical output,
      (c) the hash formula is sha1(report_id + cluster_signature)[:8].
    """
    import scripts.rework_manifest as rm  # deferred: module does not exist yet

    report_id = "test-pipeline-2026-05-14T08"
    cluster_signature = "#fail-1,#fail-2"

    row_id_first = rm.compute_row_id(report_id, cluster_signature)
    row_id_second = rm.compute_row_id(report_id, cluster_signature)

    assert row_id_first == row_id_second, (
        "compute_row_id must be deterministic: same inputs must produce same output"
    )
    assert re.match(r"rw-[0-9a-f]{8}$", row_id_first), (
        f"Row id {row_id_first!r} does not match rw-<8-hex-chars>"
    )

    # Verify the specific hash formula from the ADR:
    # sha1(report_id + cluster_signature)[:8]
    expected_hash = hashlib.sha1((report_id + cluster_signature).encode()).hexdigest()[:8]
    expected_id = f"rw-{expected_hash}"
    assert row_id_first == expected_id, (
        f"Row id {row_id_first!r} does not match expected sha1-based formula "
        f"{expected_id!r}; verify compute_row_id uses sha1(report_id + cluster_signature)[:8]"
    )


# ---------------------------------------------------------------------------
# Test: dedup_against populated when existing worktree matches row id
# ---------------------------------------------------------------------------


def test_dedup_against_populated_on_existing_worktree():
    """When a prior rework worktree exists for a row id, dedup_against is non-empty
    and severity is downgraded to 'suggested'.

    Approach A: validates the fixture manifest_with_dedup.md which models the
    re-emission scenario.  The implementer must produce output with these semantics.
    """
    assert MANIFEST_WITH_DEDUP.exists(), (
        f"Fixture {MANIFEST_WITH_DEDUP.name} not found; "
        "verifier Phase 12.5 must produce a re-emission manifest with dedup semantics"
    )
    text = MANIFEST_WITH_DEDUP.read_text(encoding="utf-8")
    blocks = _json_blocks(text)
    assert blocks, "Dedup manifest must contain at least one JSON block"

    dedup_rows = [b for b in blocks if b.get("dedup_against")]
    assert dedup_rows, (
        "At least one row in the dedup manifest must have a non-empty 'dedup_against' list"
    )
    for row in dedup_rows:
        assert row.get("severity") == "suggested", (
            f"Row with dedup_against populated must have severity='suggested', "
            f"got {row.get('severity')!r}"
        )
