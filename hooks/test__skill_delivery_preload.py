"""Tests for the preload state ``hooks/_skill_delivery.py`` reads from an agent definition.

The state decides whether a marked delegation is served the refactoring skill's body: a definition
that already preloads the skill must not be served a second copy, and a definition that cannot be
read must be told apart from one that does not preload.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402

ROLE = "implementer"


def definition_with(skills_lines: str) -> str:
    """A definition whose frontmatter carries the given lines in place of its `skills:` entry."""
    return f"---\nname: {ROLE}\ntools: Read, Write\n{skills_lines}model: sonnet\n---\n\nBody.\n"


def state_of(tmp_path: Path, text: str) -> delivery.PreloadState:
    (tmp_path / "agents").mkdir(exist_ok=True)
    (tmp_path / "agents" / f"{ROLE}.md").write_text(text, encoding="utf-8")
    return delivery.preload_state(tmp_path, ROLE)


@pytest.mark.skipif(
    not (PLUGIN_ROOT / "agents").is_dir(),
    reason="a mutation sensor's copy of hooks/ sits beside no agents/ directory",
)
@pytest.mark.parametrize("role", ["implementer", "test-engineer"])
def test_live_definitions_leave_the_skill_to_the_delivery(role):
    assert delivery.preload_state(PLUGIN_ROOT, role) == delivery.NotPreloaded()


@pytest.mark.parametrize(
    "skills_lines",
    [
        "skills: [software-planning, code-review, refactoring]\n",
        "skills: [refactoring]\n",
        "skills: [ software-planning ,  refactoring ]\n",
        "skills: ['refactoring', \"code-review\"]\n",
        "skills: [software-planning, refactoring]  # the preload\n",
        "skills: software-planning, refactoring\n",
        "skills:\n  - software-planning\n  - refactoring\n",
        "skills:\n  - software-planning\n\n  # a comment\n  - 'refactoring'  # last\n",
        "skills:\n- software-planning\n- refactoring\n",
    ],
)
def test_a_definition_listing_the_skill_is_preloaded(tmp_path, skills_lines):
    assert state_of(tmp_path, definition_with(skills_lines)) == delivery.Preloaded()


@pytest.mark.parametrize(
    "skills_lines",
    [
        "skills: [software-planning, code-review]\n",
        "skills: [refactoring-extra, my-refactoring, Refactoring]\n",
        "skills:\n  - software-planning\n  - refactoring-extra\n",
        "skills: []\n",
        "skills:\n",
        "",
        "# skills: [refactoring]\n",
        "tool-skills: [refactoring]\n",
        "  skills: [refactoring]\n",
    ],
)
def test_a_definition_without_the_skill_is_not_preloaded(tmp_path, skills_lines):
    assert state_of(tmp_path, definition_with(skills_lines)) == delivery.NotPreloaded()


def test_the_first_skills_key_decides(tmp_path):
    text = definition_with("skills: [code-review]\nskills: [refactoring]\n")
    assert state_of(tmp_path, text) == delivery.NotPreloaded()


def test_a_block_list_ends_at_the_next_key(tmp_path):
    text = definition_with("skills:\n  - code-review\nbackground:\n  - refactoring\n")
    assert state_of(tmp_path, text) == delivery.NotPreloaded()


def test_a_missing_definition_is_unreadable(tmp_path):
    assert delivery.preload_state(tmp_path, ROLE) == delivery.DefinitionUnreadable(
        "definition-unreadable"
    )


def test_a_definition_that_is_not_text_is_unreadable(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / f"{ROLE}.md").write_bytes(b"---\n\xff\xfe\n---\n")
    assert delivery.preload_state(tmp_path, ROLE) == delivery.DefinitionUnreadable(
        "definition-unreadable"
    )


@pytest.mark.parametrize(
    "text",
    [
        "name: implementer\nskills: [refactoring]\n",
        "---\nname: implementer\nskills: [refactoring]\n",
        "",
        "\n---\nskills: [refactoring]\n---\n",
    ],
)
def test_a_definition_without_frontmatter_is_unreadable(tmp_path, text):
    assert state_of(tmp_path, text) == delivery.DefinitionUnreadable("frontmatter-missing")


@pytest.mark.parametrize(
    "skills_lines",
    [
        "skills: [software-planning,\n  refactoring]\n",
        "skills: [refactoring\n",
        "skills: >\n  refactoring\n",
        "skills: |\n  refactoring\n",
        "skills: {refactoring: true}\n",
        "skills:\n  refactoring\n",
        "skills:\n  - code-review\n  stray: refactoring\n",
        "skills:\n - code-review\n stray: refactoring\n",
    ],
)
def test_an_unparseable_skills_entry_is_unreadable_never_a_guess(tmp_path, skills_lines):
    assert state_of(tmp_path, definition_with(skills_lines)) == delivery.DefinitionUnreadable(
        "skills-unparseable"
    )


def test_only_the_given_plugin_roots_definition_is_read(tmp_path):
    plugin = tmp_path / "plugin"
    project = tmp_path / "project"
    for root, skills in ((plugin, "[code-review]"), (project, "[refactoring]")):
        (root / "agents").mkdir(parents=True)
        (root / "agents" / f"{ROLE}.md").write_text(
            definition_with(f"skills: {skills}\n"), encoding="utf-8"
        )
    assert delivery.preload_state(plugin, ROLE) == delivery.NotPreloaded()
