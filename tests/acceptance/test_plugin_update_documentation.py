"""The documented update path matches what an update does: no relink for a marketplace install.

The readme's "After plugin updates" paragraph tells a marketplace user that the update command
and a restart are enough. Where it still mentions a relink, it names the case that needs one.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.plugin_update import REPO_ROOT

UPDATE_COMMAND = "claude plugin update praxion@bit-agora"
RELINK = "install.sh --relink"


@pytest.fixture(scope="module")
def paragraph() -> str:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    found = [block for block in readme.split("\n\n") if "After plugin updates" in block]
    assert found, "the readme has no 'After plugin updates' paragraph"
    return found[0]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*/(])", text) if s.strip()]


def test_the_update_paragraph_names_the_update_command(paragraph):
    assert UPDATE_COMMAND in paragraph


def test_the_update_paragraph_says_a_restart_completes_the_update(paragraph):
    assert re.search(r"\brestart", paragraph, re.IGNORECASE), paragraph


def test_the_update_paragraph_mentions_a_relink_only_for_a_named_clone_case(paragraph):
    unconditioned = [s for s in _sentences(paragraph) if RELINK in s and "clone" not in s.lower()]
    assert not unconditioned, f"a relink asked of every user: {unconditioned}"
