"""The step-loop skill says a marked return is final even under an "interim" notification.

At its rule on when to call `record`, the skill tells the orchestrator that a terminal
marker with the step record's progress is final even when the harness calls the
notification possibly interim, that a return with no marker is answered the same way
with the marker none, and that `record` is always safe to run because it refuses an
agent that has not ended (`agent-running`), the one signal to wait. The listed
description stays as it was. Whether the prose says this well is the verifier's call;
these scenarios only prove the rule sits in one section with every part present.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import frontmatter, markdown_sections

SKILL = Path(__file__).resolve().parents[2] / "skills" / "step-loop" / "SKILL.md"
BASE_DESCRIPTION = (
    "Run a pipeline's implementer steps through the step-loop driver after the pre-mortem "
    "gate, given a task slug: relay each spawn request to the Agent tool and each return to "
    "the driver."
)
RULE_PARTS = ("interim", "`record`", "`then`", "agent-running", "pending", "none")


def _sections_holding_the_rule() -> list[str]:
    text = SKILL.read_text(encoding="utf-8")
    bodies = [section.body.lower() for section in markdown_sections(text)]
    return [body for body in bodies if all(part.lower() in body for part in RULE_PARTS)]


def test_one_section_states_the_interim_rule_beside_the_record_call():
    assert _sections_holding_the_rule(), (
        f"no section of {SKILL.name} names together: {', '.join(RULE_PARTS)}"
    )


def test_the_skill_description_is_unchanged_byte_for_byte():
    assert frontmatter(SKILL.read_text(encoding="utf-8"))["description"] == BASE_DESCRIPTION
