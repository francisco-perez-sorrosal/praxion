"""Tests for decision_tracker.spec — behavioral specification parsing and amendment."""

from __future__ import annotations

from pathlib import Path

from decision_tracker.spec import apply_amendment, get_req_by_id, parse_spec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SPEC = """\
# SYSTEMS_PLAN: Auth Feature

## Acceptance Criteria

- Users can log in
- Sessions expire correctly

## Behavioral Specification

### REQ-01: Expired session rejected on API request

**When** a client sends an API request with an expired session token
**and** the token has been expired for more than the grace period
**the system** returns a 401 Unauthorized response with a `session_expired` error code
**so that** the client knows to re-authenticate rather than retrying the same request

### REQ-02: Default role assignment on registration

**When** a new user completes registration without selecting a role
**the system** assigns the `viewer` role by default
**so that** the user has minimal permissions until explicitly upgraded

### REQ-03: Rate limit enforced on API calls

**When** a client exceeds 100 requests per minute
**the system** returns a 429 Too Many Requests response with a `Retry-After` header
**so that** the client knows when to retry without overwhelming the service

## Architecture

### Component Overview

The auth service consists of...
"""

SPEC_NO_BEHAVIORAL_SECTION = """\
# SYSTEMS_PLAN: Simple Feature

## Acceptance Criteria

- Something works

## Architecture

Nothing here.
"""

SPEC_SINGLE_REQ = """\
## Behavioral Specification

### REQ-01: Only requirement

**When** something happens
**the system** does something
**so that** an outcome occurs
"""

SPEC_REQ_NO_TRAILING_SECTION = """\
## Behavioral Specification

### REQ-01: First

**When** A
**the system** B
**so that** C

### REQ-02: Second

**When** D
**the system** E
**so that** F
"""


# ---------------------------------------------------------------------------
# parse_spec tests
# ---------------------------------------------------------------------------


class TestParseSpecMultipleReqs:
    def test_parses_all_reqs(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)

        assert result is not None
        assert len(result.requirements) == 3
        assert result.requirements[0].req_id == "REQ-01"
        assert result.requirements[1].req_id == "REQ-02"
        assert result.requirements[2].req_id == "REQ-03"

    def test_extracts_titles(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        assert result.requirements[0].title == "Expired session rejected on API request"
        assert result.requirements[1].title == "Default role assignment on registration"
        assert result.requirements[2].title == "Rate limit enforced on API calls"

    def test_body_contains_when_clause(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        body = result.requirements[0].body
        assert "**When**" in body
        assert "**the system**" in body
        assert "**so that**" in body

    def test_body_contains_and_clause_when_present(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        # REQ-01 has an "and" clause
        assert "**and**" in result.requirements[0].body
        # REQ-02 does not
        assert "**and**" not in result.requirements[1].body

    def test_full_text_includes_heading(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        assert result.requirements[0].full_text.startswith("### REQ-01:")

    def test_section_boundaries(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        # Section should not include ## Architecture content
        last_req = result.requirements[-1]
        assert "Component Overview" not in last_req.full_text


class TestParseSpecEdgeCases:
    def test_file_not_found(self, tmp_path: Path) -> None:
        result = parse_spec(tmp_path / "nonexistent.md")
        assert result is None

    def test_no_behavioral_section(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SPEC_NO_BEHAVIORAL_SECTION, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is None

    def test_single_req(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SPEC_SINGLE_REQ, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        assert len(result.requirements) == 1
        assert result.requirements[0].req_id == "REQ-01"

    def test_spec_ending_without_next_section(self, tmp_path: Path) -> None:
        """Spec where Behavioral Specification is the last section (no ## after it)."""
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SPEC_REQ_NO_TRAILING_SECTION, encoding="utf-8")

        result = parse_spec(spec_file)
        assert result is not None
        assert len(result.requirements) == 2
        assert result.requirements[1].req_id == "REQ-02"
        assert "**so that** F" in result.requirements[1].body


# ---------------------------------------------------------------------------
# get_req_by_id tests
# ---------------------------------------------------------------------------


class TestGetReqById:
    def test_found(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        spec = parse_spec(spec_file)
        assert spec is not None
        req = get_req_by_id(spec, "REQ-02")
        assert req is not None
        assert req.title == "Default role assignment on registration"

    def test_not_found(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        spec = parse_spec(spec_file)
        assert spec is not None
        assert get_req_by_id(spec, "REQ-99") is None


# ---------------------------------------------------------------------------
# apply_amendment tests
# ---------------------------------------------------------------------------


class TestApplyAmendment:
    def test_replaces_req_block(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        new_text = (
            "### REQ-02: JWT-based role assignment on registration\n\n"
            "**When** a new user completes registration with a JWT token\n"
            "**the system** extracts the role from the JWT claims\n"
            "**so that** the user's role is set without a separate database lookup"
        )

        result = apply_amendment(spec_file, "REQ-02", new_text)
        assert result is True

        # Re-parse and verify
        updated_spec = parse_spec(spec_file)
        assert updated_spec is not None
        req = get_req_by_id(updated_spec, "REQ-02")
        assert req is not None
        assert req.title == "JWT-based role assignment on registration"
        assert "JWT claims" in req.body

    def test_preserves_other_reqs(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        new_text = (
            "### REQ-02: Updated title\n\n"
            "**When** something new\n"
            "**the system** does something new\n"
            "**so that** new outcome"
        )

        apply_amendment(spec_file, "REQ-02", new_text)

        updated_spec = parse_spec(spec_file)
        assert updated_spec is not None
        # REQ-01 and REQ-03 should be unchanged
        req01 = get_req_by_id(updated_spec, "REQ-01")
        req03 = get_req_by_id(updated_spec, "REQ-03")
        assert req01 is not None
        assert "expired session token" in req01.body
        assert req03 is not None
        assert "429 Too Many Requests" in req03.body

    def test_preserves_surrounding_sections(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        new_text = (
            "### REQ-01: Updated\n\n"
            "**When** new trigger\n"
            "**the system** new response\n"
            "**so that** new outcome"
        )

        apply_amendment(spec_file, "REQ-01", new_text)

        content = spec_file.read_text(encoding="utf-8")
        # Acceptance Criteria should still exist
        assert "## Acceptance Criteria" in content
        # Architecture should still exist
        assert "## Architecture" in content
        assert "Component Overview" in content

    def test_req_not_found(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SAMPLE_SPEC, encoding="utf-8")

        result = apply_amendment(spec_file, "REQ-99", "### REQ-99: New\n\nbody")
        assert result is False

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = apply_amendment(tmp_path / "missing.md", "REQ-01", "text")
        assert result is False

    def test_no_spec_section(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "SYSTEMS_PLAN.md"
        spec_file.write_text(SPEC_NO_BEHAVIORAL_SECTION, encoding="utf-8")

        result = apply_amendment(spec_file, "REQ-01", "text")
        assert result is False
