"""Tests for decision_tracker.plan — plan impact detection and annotation."""

from __future__ import annotations

from pathlib import Path

from decision_tracker.plan import ANNOTATION_MARKER, annotate_plan, find_plan_impacts

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PLAN = """\
# IMPLEMENTATION_PLAN: Auth Feature

## Acceptance Criteria

- [ ] Users can log in with JWT
- [ ] Sessions expire correctly

## Steps

### Step 1: Set up JWT middleware

**Implementation**: Create JWT validation module
**Testing**: Validates REQ-01, REQ-03
**Done when**: Middleware intercepts all API routes

### Step 2: Implement role-based access control

**Implementation**: Add role checking to endpoints
**Testing**: Validates REQ-02
**Done when**: Role checks pass for all endpoints

### Step 3: Add session expiry handling

**Implementation**: Implement token refresh and expiry logic
**Testing**: Validates REQ-01
**Done when**: Expired tokens are rejected with proper error codes

### Step 4: Write integration tests

**Implementation**: End-to-end auth flow tests
**Testing**: Validates REQ-01, REQ-02, REQ-03
**Done when**: All integration tests pass
"""

PLAN_NO_REQS = """\
# IMPLEMENTATION_PLAN: Simple

## Steps

### Step 1: Do something

**Implementation**: Write code
**Done when**: It works
"""


# ---------------------------------------------------------------------------
# find_plan_impacts tests
# ---------------------------------------------------------------------------


class TestFindPlanImpacts:
    def test_finds_steps_referencing_amended_reqs(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01"})

        # Steps 1, 3, and 4 reference REQ-01
        assert len(impacts) == 3
        headings = [i.step_heading for i in impacts]
        assert "### Step 1: Set up JWT middleware" in headings
        assert "### Step 3: Add session expiry handling" in headings
        assert "### Step 4: Write integration tests" in headings

    def test_multiple_amended_reqs(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01", "REQ-02"})

        # Step 4 references both REQ-01 and REQ-02
        step4 = [i for i in impacts if "Step 4" in i.step_heading]
        assert len(step4) == 1
        assert "REQ-01" in step4[0].affected_reqs
        assert "REQ-02" in step4[0].affected_reqs

    def test_no_matching_reqs(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-99"})
        assert impacts == []

    def test_plan_without_req_references(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(PLAN_NO_REQS, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01"})
        assert impacts == []

    def test_file_not_found(self, tmp_path: Path) -> None:
        impacts = find_plan_impacts(tmp_path / "missing.md", {"REQ-01"})
        assert impacts == []

    def test_empty_amended_ids(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, set())
        assert impacts == []

    def test_line_numbers_are_1_indexed(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-02"})
        assert len(impacts) >= 1
        # Line numbers should be positive
        assert all(i.line_number > 0 for i in impacts)


# ---------------------------------------------------------------------------
# annotate_plan tests
# ---------------------------------------------------------------------------


class TestAnnotatePlan:
    def test_inserts_annotation(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01"})
        summaries = {"REQ-01": "Updated from session tokens to JWT"}

        count = annotate_plan(plan_file, impacts, summaries)
        assert count == 3  # Steps 1, 3, 4

        content = plan_file.read_text(encoding="utf-8")
        assert ANNOTATION_MARKER in content
        assert "Updated from session tokens to JWT" in content

    def test_annotation_appears_before_next_step(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-02"})
        summaries = {"REQ-02": "Role model changed"}

        annotate_plan(plan_file, impacts, summaries)

        content = plan_file.read_text(encoding="utf-8")
        # Annotation for step 2 should appear before step 3
        annotation_pos = content.index(ANNOTATION_MARKER)
        step3_pos = content.index("### Step 3:")
        assert annotation_pos < step3_pos

    def test_no_duplicate_annotations(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01"})
        summaries = {"REQ-01": "Changed"}

        # Annotate twice
        annotate_plan(plan_file, impacts, summaries)
        # Re-scan after first annotation (line numbers changed)
        impacts2 = find_plan_impacts(plan_file, {"REQ-01"})
        count = annotate_plan(plan_file, impacts2, summaries)
        assert count == 0  # No new annotations

    def test_preserves_plan_structure(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01"})
        summaries = {"REQ-01": "Changed"}

        annotate_plan(plan_file, impacts, summaries)

        content = plan_file.read_text(encoding="utf-8")
        # All original steps should still exist
        assert "### Step 1:" in content
        assert "### Step 2:" in content
        assert "### Step 3:" in content
        assert "### Step 4:" in content
        # Acceptance criteria preserved
        assert "## Acceptance Criteria" in content

    def test_multiple_reqs_in_one_annotation(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        impacts = find_plan_impacts(plan_file, {"REQ-01", "REQ-03"})
        summaries = {
            "REQ-01": "Session to JWT",
            "REQ-03": "Rate limit changed",
        }

        annotate_plan(plan_file, impacts, summaries)

        content = plan_file.read_text(encoding="utf-8")
        # Step 1 references both REQ-01 and REQ-03
        assert "REQ-01: Session to JWT" in content
        assert "REQ-03: Rate limit changed" in content

    def test_file_not_found(self, tmp_path: Path) -> None:
        count = annotate_plan(tmp_path / "missing.md", [], {})
        assert count == 0

    def test_empty_impacts(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "IMPLEMENTATION_PLAN.md"
        plan_file.write_text(SAMPLE_PLAN, encoding="utf-8")

        count = annotate_plan(plan_file, [], {})
        assert count == 0
