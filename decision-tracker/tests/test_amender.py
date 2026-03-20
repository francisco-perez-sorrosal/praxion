"""Tests for decision_tracker.amender — spec amendment generation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from decision_tracker.amender import (
    SpecAmendment,
    _format_decisions,
    _format_requirements,
    _validate_amendments,
    generate_amendments,
)
from decision_tracker.spec import ParsedReq

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_parsed_req(
    req_id: str = "REQ-01",
    title: str = "Expired session rejected",
    body: str = "**When** client sends expired token\n**the system** returns 401\n**so that** client re-authenticates",
) -> ParsedReq:
    full_text = f"### {req_id}: {title}\n\n{body}"
    return ParsedReq(
        req_id=req_id,
        title=title,
        full_text=full_text,
        body=body,
        start_offset=0,
        end_offset=len(full_text),
    )


def _make_tool_response(amendments: list[dict]) -> MagicMock:
    """Create a mock Anthropic API response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "propose_amendments"
    tool_block.input = {"amendments": amendments}

    response = MagicMock()
    response.content = [tool_block]
    return response


# ---------------------------------------------------------------------------
# _validate_amendments tests
# ---------------------------------------------------------------------------


class TestValidateAmendments:
    def test_valid_amendment(self) -> None:
        req = _make_parsed_req()
        req_map = {req.req_id: req}

        raw = [
            {
                "req_id": "REQ-01",
                "proposed_title": "Expired JWT rejected",
                "proposed_body": "**When** client sends expired JWT\n**the system** returns 401\n**so that** client re-authenticates",
                "change_summary": "Changed from session token to JWT",
            }
        ]

        results = _validate_amendments(raw, req_map)
        assert len(results) == 1
        assert results[0].req_id == "REQ-01"
        assert results[0].current_title == "Expired session rejected"
        assert results[0].proposed_title == "Expired JWT rejected"
        assert "### REQ-01: Expired JWT rejected" in results[0].proposed_text
        assert results[0].change_summary == "Changed from session token to JWT"

    def test_unknown_req_id_skipped(self) -> None:
        req_map = {"REQ-01": _make_parsed_req()}

        raw = [
            {
                "req_id": "REQ-99",
                "proposed_title": "Nonexistent",
                "proposed_body": "body",
                "change_summary": "summary",
            }
        ]

        results = _validate_amendments(raw, req_map)
        assert len(results) == 0

    def test_missing_req_id_skipped(self) -> None:
        req_map = {"REQ-01": _make_parsed_req()}

        # Missing req_id entirely
        raw = [
            {
                "proposed_title": "Title",
                "proposed_body": "body",
                "change_summary": "summary",
            }
        ]

        results = _validate_amendments(raw, req_map)
        assert len(results) == 0

    def test_current_text_populated_from_parsed_req(self) -> None:
        req = _make_parsed_req()
        req_map = {req.req_id: req}

        raw = [
            {
                "req_id": "REQ-01",
                "proposed_title": "New title",
                "proposed_body": "**When** new\n**the system** new\n**so that** new",
                "change_summary": "Updated",
            }
        ]

        results = _validate_amendments(raw, req_map)
        assert len(results) == 1
        assert results[0].current_text == req.full_text


# ---------------------------------------------------------------------------
# _format_decisions tests
# ---------------------------------------------------------------------------


class TestFormatDecisions:
    def test_formats_with_rationale_and_reqs(self) -> None:
        decisions = [
            {
                "decision": "Use JWT for auth",
                "rationale": "Stateless scaling",
                "affected_reqs": ["REQ-01", "REQ-02"],
            }
        ]

        result = _format_decisions(decisions)
        assert "Decision 1: Use JWT for auth" in result
        assert "Rationale: Stateless scaling" in result
        assert "Affects: REQ-01, REQ-02" in result

    def test_formats_minimal_decision(self) -> None:
        decisions = [{"decision": "Simple choice"}]

        result = _format_decisions(decisions)
        assert "Decision 1: Simple choice" in result
        assert "Rationale" not in result


# ---------------------------------------------------------------------------
# _format_requirements tests
# ---------------------------------------------------------------------------


class TestFormatRequirements:
    def test_formats_multiple_reqs(self) -> None:
        reqs = [
            _make_parsed_req("REQ-01", "First"),
            _make_parsed_req("REQ-02", "Second"),
        ]

        result = _format_requirements(reqs)
        assert "### REQ-01: First" in result
        assert "### REQ-02: Second" in result


# ---------------------------------------------------------------------------
# generate_amendments tests (mocked LLM)
# ---------------------------------------------------------------------------


class TestGenerateAmendments:
    @patch("decision_tracker.amender._create_client")
    def test_returns_valid_amendments(self, mock_create_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_response(
            [
                {
                    "req_id": "REQ-01",
                    "proposed_title": "Expired JWT rejected",
                    "proposed_body": "**When** JWT expires\n**the system** returns 401\n**so that** re-auth",
                    "change_summary": "Session to JWT",
                }
            ]
        )

        req = _make_parsed_req()
        decisions = [{"decision": "Use JWT", "affected_reqs": ["REQ-01"]}]

        results = generate_amendments(decisions, [req])
        assert len(results) == 1
        assert results[0].req_id == "REQ-01"
        assert isinstance(results[0], SpecAmendment)

    @patch("decision_tracker.amender._create_client")
    def test_empty_when_no_changes_needed(self, mock_create_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_response([])

        req = _make_parsed_req()
        decisions = [{"decision": "Minor refactor", "affected_reqs": ["REQ-01"]}]

        results = generate_amendments(decisions, [req])
        assert len(results) == 0

    def test_empty_decisions_returns_empty(self) -> None:
        results = generate_amendments([], [_make_parsed_req()])
        assert results == []

    def test_empty_reqs_returns_empty(self) -> None:
        results = generate_amendments([{"decision": "test"}], [])
        assert results == []

    @patch("decision_tracker.amender._create_client")
    def test_invalid_items_skipped(self, mock_create_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        mock_client.messages.create.return_value = _make_tool_response(
            [
                # Valid
                {
                    "req_id": "REQ-01",
                    "proposed_title": "Updated",
                    "proposed_body": "**When** new\n**the system** new\n**so that** new",
                    "change_summary": "Updated",
                },
                # Invalid — unknown REQ ID
                {
                    "req_id": "REQ-99",
                    "proposed_title": "Ghost",
                    "proposed_body": "body",
                    "change_summary": "summary",
                },
            ]
        )

        req = _make_parsed_req()
        decisions = [{"decision": "test", "affected_reqs": ["REQ-01"]}]

        results = generate_amendments(decisions, [req])
        assert len(results) == 1
        assert results[0].req_id == "REQ-01"
