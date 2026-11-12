"""The install skill tells the person the command finishes the instructions too.

The skill's body, its description and its row in `skills/README.md` each say that the command
it hands over brings `~/.claude/CLAUDE.md` to the installed version as well as linking the rules
and the scripts, and that it may ask for the person's personal values.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import hand_path_skill as hp

TEXTS = {
    "body": lambda: hp.frontmatter_and_body("install")[1],
    "description": lambda: hp.description("install"),
    "catalog-row": lambda: hp.catalog_row("install"),
}


@pytest.mark.parametrize("where", TEXTS)
def test_the_text_says_the_command_brings_the_global_instructions_along(where):
    text = TEXTS[where]()

    assert "CLAUDE.md" in text, f"the {where} never names CLAUDE.md: {text[:300]!r}"
    assert re.search(r"\brules?\b", text, re.I), f"the {where} no longer names the rules"
    assert re.search(r"\bscripts?\b", text, re.I), f"the {where} no longer names the scripts"


@pytest.mark.parametrize("where", TEXTS)
def test_the_text_says_the_command_may_ask_for_personal_values(where):
    text = TEXTS[where]()

    assert re.search(r"personal values?", text, re.I), (
        f"the {where} never says the command may ask for personal values: {text[:300]!r}"
    )
