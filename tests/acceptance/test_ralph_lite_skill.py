"""Ralph-lite is entered through one skill, never a command, and the skill is the procedure.

`/praxion:ralph-lite <goal arguments>` is a skill the user and the model can both start,
whose body receives the typed arguments. It states the procedure whole: scaffold the goal
plan with `goal`, then either the terminal form (`run`, from a scratch worktree, launched
by a person) or the in-session form (the goal plan driven through `/praxion:step-loop`);
the goal must be checkable by a pytest command; a run is opt-in and paid and never started
from a hook, CI or a pipeline step; a stop's handoff is where a person picks the work up;
and the safety profile an unattended loop runs under.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.ralph_lite_texts import (
    NEGATION,
    RALPH_LITE_COMMAND,
    SAFETY_PROFILE,
    argument_substitutions_used,
    skill_text,
)
from tests.acceptance.drivers.shipped_texts import (
    body,
    frontmatter,
    path_of,
    sentences_matching,
)

# Each statement of the procedure as the patterns one sentence of the body carries together.
PROCEDURE = {
    "scaffold-the-goal-plan-with-the-goal-verb": (r"step_loop\.py goal|\bgoal\b verb", r"scaffold"),
    "the-terminal-form-runs-the-run-verb": (r"step_loop\.py run|\brun\b verb", r"terminal"),
    "the-in-session-form-drives-the-step-loop-skill": (r"/praxion:step-loop", r"session"),
    "a-goal-is-checkable-by-a-pytest-command": (r"pytest", r"check"),
    "a-run-is-opt-in": (r"opt-in",),
    "a-run-is-paid": (r"\bpaid\b|\bcosts?\b|credits",),
    "never-started-from-a-hook-ci-or-pipeline-step": (
        NEGATION,
        r"\bhooks?\b",
        r"\bCI\b",
        r"pipeline step",
    ),
    "a-person-launches-the-terminal-form": (r"\b(person|user|human|operator)\b", r"launch|start"),
    "a-stops-handoff-is-where-a-person-picks-up": (r"HANDOFF\.md", r"\b(person|human|pick)"),
}


def test_the_mode_is_a_skill_named_ralph_lite():
    meta = frontmatter(skill_text())

    assert meta.get("name") == "ralph-lite", meta


def test_the_skill_can_be_invoked_by_the_user_and_by_the_model():
    meta = frontmatter(skill_text())

    assert meta.get("disable-model-invocation") is not True, meta
    assert meta.get("user-invocable") is not False, meta


def test_the_skills_body_receives_the_typed_arguments():
    used = argument_substitutions_used(skill_text())

    assert used, "the body takes none of $ARGUMENTS, $0 or a declared argument"


def test_the_skills_description_says_when_the_model_should_start_it():
    description = str(frontmatter(skill_text()).get("description", ""))

    assert sentences_matching(description, r"single[- ]behaviou?r|one behaviou?r|goal"), description
    assert sentences_matching(description, r"test|check|pytest"), description


def test_no_command_of_that_name_exists():
    assert not path_of(RALPH_LITE_COMMAND).exists()


@pytest.mark.parametrize("statement", list(PROCEDURE))
def test_the_skill_states_the_procedure(statement):
    found = sentences_matching(body(skill_text()), *PROCEDURE[statement])

    assert found, f"no sentence of the skill states: {statement}"


@pytest.mark.parametrize("element", list(SAFETY_PROFILE))
def test_the_skill_states_the_safety_profile(element):
    found = sentences_matching(body(skill_text()), *SAFETY_PROFILE[element])

    assert found, f"no sentence of the skill states: {element}"
