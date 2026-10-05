"""A reader choosing a process for a well-gated single-behaviour task finds a safe goal-loop recipe.

The tier-selection text names the Ralph-lite recipe and where it lives. The recipe
states what makes an unattended goal loop safe: a scratch worktree; `/goal` under auto
mode or with the check command allow-listed, never under `acceptEdits` alone; the
derived test command as the stated check, its raw result printed every turn; a turn
clause; the "impossible" verdict as the exit that needs a human; and what the recipe is
not for.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.ralph_lite_recipe import (
    lines_naming_the_recipe,
    recipe_section,
    selection_text,
)


def test_the_tier_selection_text_names_the_recipe():
    assert lines_naming_the_recipe(selection_text()), "the tier-selection text never names it"


@pytest.mark.parametrize(
    ("element", "pattern"),
    [
        ("a scratch worktree", r"scratch worktree"),
        ("the goal command", r"/goal\b"),
        ("auto mode as a way to run it", r"\bauto mode\b"),
        ("the check command allow-listed as the other way", r"allow-?list"),
        ("acceptEdits alone named as not enough", r"\bacceptEdits\b"),
        ("the derived test command as the stated check", r"resolve_test_scope\.py"),
        ("the raw check result printed every turn", r"\b(every|each) turn\b"),
        ("the impossible verdict as the exit that needs a human", r"\bimpossible\b"),
        ("not for Standard step loops", r"\bStandard\b"),
        ("not for Full step loops", r"\bFull\b"),
        ("not for work that relies on background agents", r"\bbackground\b"),
    ],
)
def test_the_recipe_states_what_makes_an_unattended_goal_loop_safe(element, pattern):
    recipe = recipe_section()

    assert re.search(pattern, recipe, re.IGNORECASE), f"the recipe never states {element}"


def test_the_recipe_bounds_the_run_with_a_turn_clause():
    recipe = recipe_section()

    assert re.search(r"\bturns?\b", recipe, re.IGNORECASE)
    assert re.search(r"\b\d+\s+turns?\b|\bturn (clause|limit|cap|bound)\b", recipe, re.IGNORECASE)
