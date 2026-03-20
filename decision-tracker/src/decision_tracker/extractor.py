"""Decision extraction via Anthropic API tool-use (structured output)."""

from __future__ import annotations

import os
from typing import Any

import anthropic
from pydantic import ValidationError

from decision_tracker.schema import ExtractedDecision

MODEL = "claude-haiku-4-5-20250514"
MAX_TOKENS = 4096

EXTRACTION_TOOL: dict[str, Any] = {
    "name": "record_decisions",
    "description": "Record decisions identified in the development session",
    "input_schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "What was being decided",
                        },
                        "decision": {
                            "type": "string",
                            "description": "The choice that was made",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this choice was made",
                        },
                        "alternatives": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "What else was considered",
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "architectural",
                                "behavioral",
                                "implementation",
                                "configuration",
                                "calibration",
                            ],
                        },
                        "made_by": {
                            "type": "string",
                            "enum": ["user", "agent"],
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0.0-1.0 extraction confidence",
                        },
                        "affected_files": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "affected_reqs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "REQ IDs (e.g. REQ-01, REQ-03) from the behavioral "
                                "specification that this decision affects. Only include "
                                "IDs explicitly mentioned in the transcript or diff."
                            ),
                        },
                        "spec_relevant": {
                            "type": "boolean",
                            "description": "Whether this decision affects the spec",
                        },
                    },
                    "required": ["decision", "category", "made_by", "confidence"],
                },
            },
        },
        "required": ["decisions"],
    },
}

SYSTEM_PROMPT = """\
You are a decision extraction assistant. Analyze the development session \
transcript and/or diff to identify decisions that were made.

A decision is a CHOICE — something picked over an alternative. Apply these rules:

1. Diagnoses, observations, and findings are NOT decisions.
2. Process actions (approve, commit, push, merge) are NOT decisions unless they \
reflect a deliberate choice with alternatives.
3. Git/workflow and tooling/environment decisions are NOT spec-relevant.
4. When in doubt, include it — false positives are better than missed decisions.
5. When the transcript or diff references REQ IDs (REQ-01, REQ-02, etc.) from a \
behavioral specification, include them in affected_reqs. Only include IDs that \
appear explicitly — do not guess.

For each decision, assess your confidence (0.0-1.0) in whether it truly \
represents a deliberate choice that was made during this session.\
"""

USER_PROMPT_FULL = """\
Here is the development session transcript:

<transcript>
{transcript}
</transcript>

Here is the diff from this session:

<diff>
{diff}
</diff>

Extract all decisions made during this session.\
"""

USER_PROMPT_DIFF_ONLY = """\
Here is the diff from a development session (no transcript available):

<diff>
{diff}
</diff>

Extract any decisions that can be inferred from the code changes.\
"""


def extract_decisions(
    transcript: str,
    diff: str,
    client: anthropic.Anthropic | None = None,
) -> list[ExtractedDecision]:
    """Extract decisions from a transcript and/or diff using the Anthropic API.

    When *client* is None, creates one from the ``ANTHROPIC_API_KEY`` env var.
    Raises ``ValueError`` when the key is missing and no client is provided.
    """
    if client is None:
        client = _create_client()

    user_message = _build_user_message(transcript, diff)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_decisions"},
    )

    return _parse_response(response)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_client() -> anthropic.Anthropic:
    """Create an Anthropic client, raising ``ValueError`` when the key is unset."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic()


def _build_user_message(transcript: str, diff: str) -> str:
    """Build the user message from transcript and diff content."""
    if transcript.strip():
        return USER_PROMPT_FULL.format(transcript=transcript, diff=diff)
    return USER_PROMPT_DIFF_ONLY.format(diff=diff)


def _parse_response(response: anthropic.types.Message) -> list[ExtractedDecision]:
    """Extract validated ``ExtractedDecision`` objects from the API response.

    Skips individual items that fail Pydantic validation rather than failing
    the entire extraction.
    """
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_decisions":
            raw_decisions = block.input.get("decisions", [])
            return _validate_decisions(raw_decisions)
    return []


def _validate_decisions(raw_items: list[dict[str, Any]]) -> list[ExtractedDecision]:
    """Validate raw decision dicts into ``ExtractedDecision`` models.

    Invalid items are silently skipped — the caller receives only valid decisions.
    """
    results: list[ExtractedDecision] = []
    for item in raw_items:
        try:
            results.append(ExtractedDecision.model_validate(item))
        except ValidationError:
            continue
    return results
