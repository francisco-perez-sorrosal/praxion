"""Tests for decision_tracker.extractor — Anthropic API extraction with mocked client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from decision_tracker.extractor import EXTRACTION_TOOL, extract_decisions
from decision_tracker.schema import ExtractedDecision


def _mock_response(decisions_data: list[dict]) -> MagicMock:
    """Build a mock Anthropic response with tool_use content."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "record_decisions"
    tool_block.input = {"decisions": decisions_data}

    response = MagicMock()
    response.content = [tool_block]
    return response


VALID_DECISION = {
    "question": "What cache to use?",
    "decision": "Use Redis with 5-min TTL",
    "rationale": "Low latency",
    "alternatives": ["Memcached"],
    "category": "architectural",
    "made_by": "user",
    "confidence": 0.92,
    "affected_files": ["src/cache.py"],
    "spec_relevant": True,
}

MINIMAL_DECISION = {
    "decision": "Use dataclasses",
    "category": "implementation",
    "made_by": "agent",
    "confidence": 0.75,
}


class TestExtractDecisions:
    def test_extract_with_transcript_and_diff(self):
        client = MagicMock()
        client.messages.create.return_value = _mock_response([VALID_DECISION, MINIMAL_DECISION])

        results = extract_decisions(
            transcript="User: Let's use Redis\nAssistant: Good choice",
            diff="+ redis_client = Redis()",
            client=client,
        )

        assert len(results) == 2
        assert all(isinstance(r, ExtractedDecision) for r in results)
        assert results[0].decision == "Use Redis with 5-min TTL"
        assert results[0].category == "architectural"
        assert results[1].decision == "Use dataclasses"

        # Verify the API was called with expected parameters
        client.messages.create.assert_called_once()
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20250514"
        assert "transcript" in call_kwargs["messages"][0]["content"]

    def test_extract_diff_only(self):
        client = MagicMock()
        client.messages.create.return_value = _mock_response([MINIMAL_DECISION])

        results = extract_decisions(transcript="", diff="+ new_function()", client=client)

        assert len(results) == 1
        assert results[0].decision == "Use dataclasses"

        # Verify diff-only prompt variant was used (no transcript tag)
        call_kwargs = client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "<transcript>" not in user_content
        assert "<diff>" in user_content

    def test_empty_decisions_returns_empty_list(self):
        client = MagicMock()
        client.messages.create.return_value = _mock_response([])

        results = extract_decisions(transcript="Hello", diff="", client=client)

        assert results == []

    def test_invalid_decision_skipped(self):
        invalid_decision = {
            "decision": "Missing required fields",
            # missing: category, made_by, confidence
        }
        client = MagicMock()
        client.messages.create.return_value = _mock_response([invalid_decision, VALID_DECISION])

        results = extract_decisions(transcript="test", diff="test", client=client)

        assert len(results) == 1
        assert results[0].decision == "Use Redis with 5-min TTL"

    def test_invalid_category_skipped(self):
        bad_category = {
            "decision": "Something",
            "category": "nonexistent",
            "made_by": "agent",
            "confidence": 0.5,
        }
        client = MagicMock()
        client.messages.create.return_value = _mock_response([bad_category, MINIMAL_DECISION])

        results = extract_decisions(transcript="test", diff="test", client=client)

        assert len(results) == 1
        assert results[0].decision == "Use dataclasses"


class TestAffectedReqsExtraction:
    def test_affected_reqs_extracted(self):
        decision_with_reqs = {
            **VALID_DECISION,
            "affected_reqs": ["REQ-01", "REQ-03"],
        }
        client = MagicMock()
        client.messages.create.return_value = _mock_response([decision_with_reqs])

        results = extract_decisions(transcript="test", diff="test", client=client)

        assert len(results) == 1
        assert results[0].affected_reqs == ["REQ-01", "REQ-03"]

    def test_affected_reqs_absent_when_not_provided(self):
        client = MagicMock()
        client.messages.create.return_value = _mock_response([MINIMAL_DECISION])

        results = extract_decisions(transcript="test", diff="test", client=client)

        assert len(results) == 1
        assert results[0].affected_reqs is None


class TestClientCreation:
    def test_no_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
                extract_decisions(transcript="test", diff="test", client=None)

    def test_api_error_propagates(self):
        client = MagicMock()
        client.messages.create.side_effect = Exception("API connection failed")

        with pytest.raises(Exception, match="API connection failed"):
            extract_decisions(transcript="test", diff="test", client=client)


class TestToolSchema:
    def test_tool_name(self):
        assert EXTRACTION_TOOL["name"] == "record_decisions"

    def test_input_schema_has_decisions_array(self):
        schema = EXTRACTION_TOOL["input_schema"]
        assert schema["type"] == "object"
        assert "decisions" in schema["properties"]
        assert schema["properties"]["decisions"]["type"] == "array"

    def test_required_fields_in_item_schema(self):
        item_schema = EXTRACTION_TOOL["input_schema"]["properties"]["decisions"]["items"]
        assert set(item_schema["required"]) == {"decision", "category", "made_by", "confidence"}

    def test_category_enum_matches_schema(self):
        item_props = EXTRACTION_TOOL["input_schema"]["properties"]["decisions"]["items"][
            "properties"
        ]
        expected = ["architectural", "behavioral", "implementation", "configuration", "calibration"]
        assert item_props["category"]["enum"] == expected

    def test_made_by_enum_matches_schema(self):
        item_props = EXTRACTION_TOOL["input_schema"]["properties"]["decisions"]["items"][
            "properties"
        ]
        assert item_props["made_by"]["enum"] == ["user", "agent"]

    def test_affected_reqs_in_item_schema(self):
        item_props = EXTRACTION_TOOL["input_schema"]["properties"]["decisions"]["items"][
            "properties"
        ]
        assert "affected_reqs" in item_props
        assert item_props["affected_reqs"]["type"] == "array"

    def test_decisions_is_required_top_level(self):
        assert "decisions" in EXTRACTION_TOOL["input_schema"]["required"]
