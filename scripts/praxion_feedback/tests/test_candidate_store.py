"""Behavioral tests for the PENDING.md candidate store.

Covers append/dedup/list/mark-filed against the `### <fp8>` candidate-block
schema (SYSTEMS_PLAN.md § Interfaces). Every store path lives under pytest's
`tmp_path` -- never a committed or gitignored fixture path -- so each test
starts from a pristine, isolated file and the framework's own cleanup
guarantees no cross-test state leaks.

Assumption flagged for the paired implementer: `fields` carries raw
category/artifact_path/error keys and `append_candidate` computes the
fingerprint internally via `fingerprint.compute_fingerprint` -- the plan's
"computes/accepts a fingerprint" phrasing leaves this open, and this is the
more self-contained reading (the module owns the full dedup contract, not
just the file I/O around a caller-supplied hash). If the implementation
instead expects a pre-computed `fingerprint` key in `fields`, only
`_candidate_fields` and the `expected = compute_fingerprint(...)` call sites
below need updating.
"""

from __future__ import annotations

from pathlib import Path

from scripts.praxion_feedback.candidate_store import (
    append_candidate,
    list_pending,
    mark_filed,
)
from scripts.praxion_feedback.fingerprint import compute_fingerprint


def _candidate_fields(**overrides: object) -> dict:
    """Minimal, complete candidate fields dict -- the input to `append_candidate`.

    Field names mirror the `capture` CLI flags in SYSTEMS_PLAN.md (Components
    item 2): category/artifact_path/error drive the fingerprint; the rest are
    the §5.2 body fields carried straight through to the stored block.
    """
    fields: dict[str, object] = {
        "category": "scripts",
        "artifact_path": "scripts/praxion_feedback/fingerprint.py",
        "error": "AttributeError: 'NoneType' object has no attribute 'foo'",
        "detected_by": "sentinel",
        "detection_point": "post-implementation audit",
        "confidence": "high",
        "expected": "normalize_error strips volatile tokens",
        "observed": "raises AttributeError on a None error string",
        "reproduction_command": (
            "python3 -m pytest scripts/praxion_feedback/tests/test_fingerprint.py"
        ),
        "environment": "macOS, Python 3.11",
        "regression_status": "new",
    }
    fields.update(overrides)
    return fields


class TestAppendCandidateWritesAWellFormedBlock:
    def test_first_append_returns_the_computed_fingerprint(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()

        fingerprint = append_candidate(pending, upstream, fields)

        expected = compute_fingerprint(fields["category"], fields["artifact_path"], fields["error"])
        assert fingerprint == expected

    def test_first_append_writes_a_block_keyed_by_the_short_fingerprint(
        self, tmp_path: Path
    ) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()

        fingerprint = append_candidate(pending, upstream, fields)

        content = pending.read_text()
        assert f"### {fingerprint[:8]}" in content
        assert "status: pending" in content


class TestAppendCandidateDedupesByFingerprint:
    def test_second_identical_append_is_a_no_op(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()

        append_candidate(pending, upstream, fields)
        result = append_candidate(pending, upstream, fields)

        assert result is None

    def test_second_identical_append_does_not_duplicate_the_block(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()

        fingerprint = append_candidate(pending, upstream, fields)
        append_candidate(pending, upstream, fields)

        content = pending.read_text()
        assert content.count(f"### {fingerprint[:8]}") == 1

    def test_append_with_fingerprint_already_present_in_upstream_issues_is_a_no_op(
        self, tmp_path: Path
    ) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()
        expected = compute_fingerprint(fields["category"], fields["artifact_path"], fields["error"])
        upstream.write_text(f"| {expected} | francisco-perez-sorrosal/praxion#42 | filed |\n")

        result = append_candidate(pending, upstream, fields)

        assert result is None
        assert not pending.exists() or f"### {expected[:8]}" not in pending.read_text()

    def test_a_genuinely_different_defect_still_appends_after_a_prior_dedup_hit(
        self, tmp_path: Path
    ) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        first = _candidate_fields()
        second = _candidate_fields(
            artifact_path="scripts/praxion_feedback/render.py", error="KeyError: 'bar'"
        )

        append_candidate(pending, upstream, first)
        second_fingerprint = append_candidate(pending, upstream, second)

        assert second_fingerprint is not None
        content = pending.read_text()
        assert f"### {second_fingerprint[:8]}" in content


class TestListPendingExcludesResolvedCandidates:
    def test_lists_only_the_still_pending_candidate(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        still_pending = _candidate_fields()
        will_be_filed = _candidate_fields(
            artifact_path="scripts/praxion_feedback/render.py", error="KeyError: 'bar'"
        )
        append_candidate(pending, upstream, still_pending)
        filed_fingerprint = append_candidate(pending, upstream, will_be_filed)
        mark_filed(
            pending,
            filed_fingerprint,
            "https://github.com/francisco-perez-sorrosal/praxion/issues/42",
        )

        pending_candidates = list_pending(pending)

        assert len(pending_candidates) == 1
        assert pending_candidates[0]["artifact_path"] == still_pending["artifact_path"]

    def test_a_store_with_no_candidates_returns_an_empty_list(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        assert list_pending(pending) == []


class TestMarkFiledFlipsStatusWithoutDisturbingSiblings:
    def test_marks_the_target_candidate_filed_with_its_issue_url(self, tmp_path: Path) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        fields = _candidate_fields()
        fingerprint = append_candidate(pending, upstream, fields)

        mark_filed(
            pending, fingerprint, "https://github.com/francisco-perez-sorrosal/praxion/issues/7"
        )

        content = pending.read_text()
        assert "status: filed" in content
        assert "https://github.com/francisco-perez-sorrosal/praxion/issues/7" in content
        assert list_pending(pending) == []

    def test_marking_one_candidate_filed_leaves_a_sibling_candidate_pending(
        self, tmp_path: Path
    ) -> None:
        pending = tmp_path / "PENDING.md"
        upstream = tmp_path / "UPSTREAM_ISSUES.md"
        target = _candidate_fields()
        sibling = _candidate_fields(
            artifact_path="scripts/praxion_feedback/render.py", error="KeyError: 'bar'"
        )
        target_fingerprint = append_candidate(pending, upstream, target)
        append_candidate(pending, upstream, sibling)

        mark_filed(
            pending,
            target_fingerprint,
            "https://github.com/francisco-perez-sorrosal/praxion/issues/7",
        )

        remaining = list_pending(pending)
        assert len(remaining) == 1
        assert remaining[0]["artifact_path"] == sibling["artifact_path"]
