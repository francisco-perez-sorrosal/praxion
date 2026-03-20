"""Spec amendment generation via Anthropic API tool-use (structured output).

Given approved decisions and the current REQ text, proposes amendments
that keep the behavioral specification in sync with implementation decisions.
"""

from __future__ import annotations

from typing import Any

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from decision_tracker.extractor import MODEL, _create_client
from decision_tracker.spec import ParsedReq

MAX_TOKENS = 4096

AMENDMENT_TOOL: dict[str, Any] = {
    "name": "propose_amendments",
    "description": "Propose amendments to behavioral specification requirements",
    "input_schema": {
        "type": "object",
        "properties": {
            "amendments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "req_id": {
                            "type": "string",
                            "description": "The REQ ID being amended (e.g. REQ-01)",
                        },
                        "proposed_title": {
                            "type": "string",
                            "description": "Updated title for the requirement",
                        },
                        "proposed_body": {
                            "type": "string",
                            "description": (
                                "Full requirement body in When/and/the system/so that format "
                                "with **bold** markers on each clause keyword"
                            ),
                        },
                        "change_summary": {
                            "type": "string",
                            "description": "One-sentence explanation of what changed and why",
                        },
                    },
                    "required": [
                        "req_id",
                        "proposed_title",
                        "proposed_body",
                        "change_summary",
                    ],
                },
            },
        },
        "required": ["amendments"],
    },
}

AMENDMENT_SYSTEM_PROMPT = """\
You are a specification amendment assistant. Given approved decisions and the \
current text of affected behavioral requirements, propose updated requirement text.

Rules:
1. Preserve the When/and/the system/so that format exactly, with **bold** markers \
on each clause keyword (**When**, **and**, **the system**, **so that**).
2. Only modify what the decision changes — minimize edits to other parts of the requirement.
3. Keep the requirement's intent coherent after the amendment.
4. If a decision does not actually require changing a requirement, omit it from the \
amendments array — do not propose a no-op amendment.
5. The proposed_body must be the full body text (everything after the heading), \
including all clause lines.\
"""

AMENDMENT_USER_PROMPT = """\
Here are the approved decisions from the current development session:

<decisions>
{decisions_text}
</decisions>

Here are the current behavioral requirements that these decisions affect:

<requirements>
{requirements_text}
</requirements>

Propose amendments to any requirements that need updating based on these decisions.\
"""


class SpecAmendment(BaseModel):
    """A proposed amendment to a single requirement."""

    model_config = ConfigDict(extra="forbid")

    req_id: str
    current_title: str
    proposed_title: str
    current_text: str
    proposed_text: str
    change_summary: str


def generate_amendments(
    decisions: list[dict],
    affected_reqs: list[ParsedReq],
    client: anthropic.Anthropic | None = None,
) -> list[SpecAmendment]:
    """Generate spec amendments for affected requirements based on approved decisions.

    Makes a single Haiku call with all decisions and affected REQs.
    Returns validated ``SpecAmendment`` objects; invalid items are skipped.
    """
    if not decisions or not affected_reqs:
        return []

    if client is None:
        client = _create_client()

    decisions_text = _format_decisions(decisions)
    requirements_text = _format_requirements(affected_reqs)
    user_message = AMENDMENT_USER_PROMPT.format(
        decisions_text=decisions_text,
        requirements_text=requirements_text,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=AMENDMENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[AMENDMENT_TOOL],
        tool_choice={"type": "tool", "name": "propose_amendments"},
    )

    return _parse_response(response, affected_reqs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_decisions(decisions: list[dict]) -> str:
    """Format decisions for the prompt."""
    lines: list[str] = []
    for i, d in enumerate(decisions, 1):
        lines.append(f"Decision {i}: {d.get('decision', '')}")
        if d.get("rationale"):
            lines.append(f"  Rationale: {d['rationale']}")
        if d.get("affected_reqs"):
            lines.append(f"  Affects: {', '.join(d['affected_reqs'])}")
    return "\n".join(lines)


def _format_requirements(reqs: list[ParsedReq]) -> str:
    """Format parsed requirements for the prompt."""
    return "\n\n".join(req.full_text for req in reqs)


def _parse_response(
    response: anthropic.types.Message,
    affected_reqs: list[ParsedReq],
) -> list[SpecAmendment]:
    """Extract validated amendments from the API response."""
    req_map = {req.req_id: req for req in affected_reqs}

    for block in response.content:
        if block.type == "tool_use" and block.name == "propose_amendments":
            raw_amendments = block.input.get("amendments", [])
            return _validate_amendments(raw_amendments, req_map)
    return []


def _validate_amendments(
    raw_items: list[dict[str, Any]],
    req_map: dict[str, ParsedReq],
) -> list[SpecAmendment]:
    """Validate raw amendment dicts and enrich with current text."""
    results: list[SpecAmendment] = []
    for item in raw_items:
        req_id = item.get("req_id", "")
        current_req = req_map.get(req_id)
        if current_req is None:
            continue

        proposed_title = item.get("proposed_title", "")
        proposed_body = item.get("proposed_body", "")
        proposed_text = f"### {req_id}: {proposed_title}\n\n{proposed_body}"

        try:
            results.append(
                SpecAmendment(
                    req_id=req_id,
                    current_title=current_req.title,
                    proposed_title=proposed_title,
                    current_text=current_req.full_text,
                    proposed_text=proposed_text,
                    change_summary=item.get("change_summary", ""),
                )
            )
        except ValidationError:
            continue
    return results
