"""The Ralph-lite recipe is found at tier selection and says what the mode is and is not.

The coordination protocol's Lightweight row names Ralph-lite, on the same line as a link to
the recipe's section, as an execution mode and not a tier; its sentence on execution modes
names Automated and Ralph-lite as orthogonal to the tier; and the tier table still lists
five tiers. The recipe section describes the mode (its skill, its two forms, a fresh
context per iteration with state on disk, the gate deciding, the driver as the one
committer, its bounds, its exits to a person, the documents it writes, what it is not for)
with `/goal` in one line only, as the fallback outside Praxion, and the safety profile an
unattended loop runs under. The live eval runner's launch policy covers a Ralph-lite run.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.ralph_lite_texts import (
    EVAL_COMMAND,
    NEGATION,
    RALPH_LITE,
    SAFETY_PROFILE,
    TIERS,
    blocks_mentioning,
    lines_with_goal_command,
    recipe_section,
    tier_row,
    tier_rows,
)
from tests.acceptance.drivers.shipped_texts import (
    COORDINATION_PROTOCOL,
    normalize,
    read,
    sentences_matching,
)

# Each statement of the recipe as the patterns one sentence of its section carries together.
RECIPE = {
    "entered-through-the-skill": (r"/praxion:ralph-lite",),
    "in-two-forms-terminal-and-in-session": (r"terminal", r"in-session"),
    "a-fresh-context-every-iteration": (r"fresh", r"context", r"iteration"),
    "state-in-the-plan-progress-record-ledger-and-git": (
        r"progress record",
        r"ledger",
        r"\bgit\b",
    ),
    "the-gate-decides-never-the-workers-claim": (r"\b(gate|check)", NEGATION, r"claim|says"),
    "the-worker-never-commits": (r"\bworker\b", r"never commits?|does not commit"),
    "the-driver-commits-each-progressing-iteration": (r"\bdriver\b", r"\bcommits\b", r"progress"),
    "bounded-by-the-iterations-budget": (r"\bIterations\b", r"budget"),
    "bounded-per-iteration-in-turns-and-dollars": (r"\bturn", r"dollar|\bfuse\b"),
    "stopped-after-two-non-progressing-iterations": (r"\btwo\b|\b2\b", r"non-progressing"),
    "a-blocked-return-reaches-a-person-with-a-handoff": (r"BLOCKED", r"handoff"),
    "the-impossible-verdict-reaches-a-person": (r"impossible", r"\b(person|human|handoff)"),
    "a-stall-reaches-a-person": (r"\bstall", r"\b(person|human|handoff)"),
    "a-goal-run-writes-a-plan-wip-and-test-results": (r"\bWIP\b", r"TEST_RESULTS", r"plan"),
    "although-the-task-is-lightweight-sized": (r"TEST_RESULTS", r"Lightweight"),
    "the-calibration-rows-source-cell-names-the-mode": (r"calibration", r"\bSource\b"),
    "not-for-standard-and-full-step-loops": (r"Standard", r"Full", r"relay|step-loop"),
    "not-for-goals-no-pytest-command-can-check": (r"pytest", NEGATION),
}

LAUNCH_POLICY = {
    "launched-by-a-person": (r"\b(person|user|human|operator)\b",),
    "opt-in": (r"opt-in",),
    "paid": (r"\bpaid\b|\bcosts?\b|credits",),
    "bounded-per-iteration": (r"per[- ]iteration|each iteration",),
    "bounded-per-loop": (r"per[- ]loop|the loop|whole loop|iterations budget",),
    "never-from-a-hook": (NEGATION, r"\bhooks?\b"),
    "never-from-ci": (NEGATION, r"\bCI\b"),
    "never-from-a-pipeline-step": (NEGATION, r"pipeline step"),
}


def test_the_lightweight_row_names_ralph_lite_beside_a_link_to_its_recipe():
    row = normalize(tier_row("Lightweight"))

    assert sentences_matching(row, RALPH_LITE), row
    assert "tier-templates.md#ralph-lite" in row.lower(), row


def test_the_lightweight_row_calls_ralph_lite_an_execution_mode_not_a_tier():
    row = normalize(tier_row("Lightweight"))

    assert sentences_matching(row, RALPH_LITE, r"execution mode"), row


def test_the_execution_mode_sentence_names_automated_and_ralph_lite_orthogonal_to_the_tier():
    protocol = read(COORDINATION_PROTOCOL)

    found = sentences_matching(protocol, r"Automated", RALPH_LITE, r"execution modes?", r"orthog")

    assert found, "no sentence names Automated and Ralph-lite as execution modes"


def test_the_tier_table_still_lists_exactly_five_tiers():
    assert tier_rows() == list(TIERS)


def test_the_tier_selector_still_walks_five_tiers_in_order():
    protocol = normalize(read(COORDINATION_PROTOCOL))

    assert "Spike → Direct → Lightweight → Standard → Full" in protocol


@pytest.mark.parametrize("statement", list(RECIPE))
def test_the_recipe_states(statement):
    found = sentences_matching(recipe_section(), *RECIPE[statement])

    assert found, f"no sentence of the Ralph-lite section states: {statement}"


@pytest.mark.parametrize("element", list(SAFETY_PROFILE))
def test_the_recipe_states_the_safety_profile(element):
    found = sentences_matching(recipe_section(), *SAFETY_PROFILE[element])

    assert found, f"no sentence of the Ralph-lite section states: {element}"


def test_goal_appears_on_one_line_only_labelled_as_the_fallback_without_praxion():
    lines = lines_with_goal_command(recipe_section())

    assert len(lines) == 1, lines
    assert sentences_matching(lines[0], r"fallback", r"without Praxion|no Praxion"), lines


def test_the_goal_fallback_line_says_it_keeps_one_context_and_judges_printed_output():
    lines = lines_with_goal_command(recipe_section())

    assert len(lines) == 1, lines
    assert sentences_matching(lines[0], r"\b(one|single|same)\b[^.]*context"), lines
    assert sentences_matching(lines[0], r"print|output"), lines


@pytest.mark.parametrize("element", list(LAUNCH_POLICY))
def test_the_launch_policy_covers_a_ralph_lite_run(element):
    blocks = blocks_mentioning(read(EVAL_COMMAND), RALPH_LITE)

    assert blocks, f"no paragraph or list item of {EVAL_COMMAND} mentions Ralph-lite"
    assert sentences_matching(" ".join(blocks), *LAUNCH_POLICY[element]), blocks
