"""Behavioral tests for the `description` of `skills/skill-crafting/SKILL.md`.

The description is the only text that decides whether the skill activates, so a rewrite may
change its lead sentence but must keep every trigger noun it had (a dropped noun silently stops
the skill from activating) and add the nouns for the capabilities the skill gained.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILL_MD = REPO_ROOT / "skills" / "skill-crafting" / "SKILL.md"

# The validator's limit (skills/skill-crafting/scripts/validate.py: 1-1024 chars).
MAX_DESCRIPTION_CHARS = 1024

# The nouns of the `Triggers:` clause as it stood before the rewrite.
BASE_TRIGGER_NOUNS = (
    "creating new skills",
    "updating or modernizing existing skills",
    "converting memory files to skills",
    "debugging skill activation",
    "skill architecture and best practices",
    "user-invoked skills",
    "argument-hint",
    "argument substitution",
    "converting command files to skills",
)
NEW_TRIGGER_NOUNS = ("skill evals", "description optimization")


def _description() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    frontmatter = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert frontmatter is not None, f"{SKILL_MD} has no frontmatter"
    return " ".join(yaml.safe_load(frontmatter.group(1))["description"].split())


def test_every_base_trigger_noun_survives_verbatim() -> None:
    description = _description()
    missing = [noun for noun in BASE_TRIGGER_NOUNS if noun not in description]
    assert not missing, f"trigger nouns dropped from the description: {missing}"


def test_the_new_trigger_nouns_are_present() -> None:
    description = _description()
    missing = [noun for noun in NEW_TRIGGER_NOUNS if noun not in description]
    assert not missing, f"new trigger nouns absent from the description: {missing}"


def test_the_description_is_within_the_validator_limit_and_has_no_angle_bracket() -> None:
    description = _description()
    assert 1 <= len(description) <= MAX_DESCRIPTION_CHARS
    assert not re.search(r"[<>]", description)
