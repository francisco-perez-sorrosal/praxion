"""Report-writing agents fill each section right after its check, not at the end.

The `verifier` prompt tells the agent to fill a section right after its check,
from the evidence in hand, never at the end from notes, so that a turn-capped
run leaves filled sections on disk rather than bare headings. The
`systems-architect` and `implementation-planner` prompts carry the same
instruction.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.step_checks import REPO_ROOT

INSTRUCTION_PARTS = (
    "right after its check",
    "from the evidence in hand",
    "never at the end from notes",
)


def _prompt_text(agent: str) -> str:
    text = (REPO_ROOT / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text).lower()


@pytest.mark.parametrize("agent", ["verifier", "systems-architect", "implementation-planner"])
@pytest.mark.parametrize("part", INSTRUCTION_PARTS)
def test_report_agent_prompt_tells_it_to_fill_each_section_right_after_its_check(agent, part):
    prompt = _prompt_text(agent)

    assert part in prompt, f"agents/{agent}.md does not carry the fill-as-you-check clause {part!r}"
