"""The step-loop procedure is a skill both the user and the model can start.

`/praxion:step-loop <task-slug>` runs the loop for the task slug it is given: repeat
`next`, execute each spawn request through the Agent tool unchanged, call `record` after
each completion notification. It states the relay rules and forbids the orchestrator,
inside the loop, to compose or read an implementer prompt, commit, or edit an `Attempts:`
line. The coordination protocol's "Plan ready" bullet names it, and no command of that
name exists.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.shipped_texts import (
    COORDINATION_PROTOCOL,
    STEP_LOOP_SKILL,
    body,
    frontmatter,
    lines_containing,
    path_of,
    read,
    sentences_matching,
)

NEGATION = r"\b(never|not|no|don't|do not|must not|mustn't)\b"

# Each rule as the patterns one sentence of the procedure carries together.
RELAY_RULES = {
    "pass-the-spawn-request-unchanged": (
        r"\bagent\b",
        r"\b(unchanged|verbatim|as[- ]is|exactly as|without (any )?(change|edit))",
    ),
    "record-only-after-the-completion-notification": (
        r"\brecord\b",
        r"notif",
        r"\b(after|before|until|once)\b",
    ),
    "relay-the-agent-id-and-the-marker": (
        r"\brecord\b",
        r"\bagent[ _-]?id\b|\bagentid\b",
        r"\bmarker\b",
    ),
    "never-edit-the-rendered-prompt": (
        NEGATION,
        r"\b(edit|change|modify|alter|rewrite)",
        r"\bprompt\b",
    ),
    "never-commit": (NEGATION, r"\bcommit"),
    "never-compose-an-implementer-prompt": (
        NEGATION,
        r"\b(compose|write|author|draft)",
        r"\bprompt\b",
    ),
    "never-read-the-rendered-prompt": (NEGATION, r"\bread\b", r"\bprompt\b"),
    "never-edit-an-attempts-line": (
        NEGATION,
        r"\b(edit|write|change|touch|modify)",
        r"\battempts:",
    ),
}


def _skill_text() -> str:
    return read(STEP_LOOP_SKILL)


def test_the_procedure_is_a_skill_named_step_loop():
    meta = frontmatter(_skill_text())

    assert meta.get("name") == "step-loop", meta


def test_the_skill_can_be_invoked_by_the_user_and_by_the_model():
    meta = frontmatter(_skill_text())

    assert meta.get("disable-model-invocation") is not True, meta
    assert meta.get("user-invocable") is not False, meta


def _argument_substitutions(text: str) -> list[str]:
    """`$ARGUMENTS`, `$0`, and `$<name>` for each argument the frontmatter declares."""
    declared = frontmatter(text).get("arguments") or []
    names = declared.split() if isinstance(declared, str) else [str(n) for n in declared]
    return ["$ARGUMENTS", "$0", *(f"${name}" for name in names)]


def _substitutions_used(text: str) -> list[str]:
    return [token for token in _argument_substitutions(text) if token in body(text)]


def test_the_skill_acts_on_the_task_slug_it_is_given():
    text = _skill_text()

    used = _substitutions_used(text)

    assert used, f"the body uses none of {_argument_substitutions(text)} to take the task slug"


def test_the_skill_runs_the_loop_through_the_drivers_verbs():
    procedure = body(_skill_text())

    assert re.search(r"step_loop\.py", procedure), "the driver's command is never named"
    assert sentences_matching(procedure, r"\bnext\b"), "the `next` verb is never named"
    assert sentences_matching(procedure, r"\brecord\b"), "the `record` verb is never named"


@pytest.mark.parametrize("rule", list(RELAY_RULES))
def test_the_skill_states_the_relay_rule(rule):
    found = sentences_matching(body(_skill_text()), *RELAY_RULES[rule])

    assert found, f"no sentence of the procedure states: {rule}"


def test_the_plan_ready_bullet_names_the_skill():
    bullets = lines_containing(read(COORDINATION_PROTOCOL), r"plan ready")

    assert bullets, "the coordination protocol has no Plan ready bullet"
    assert re.search(r"step-loop", " ".join(bullets)), bullets


def test_no_command_of_that_name_exists():
    assert not path_of("commands/step-loop.md").exists()
