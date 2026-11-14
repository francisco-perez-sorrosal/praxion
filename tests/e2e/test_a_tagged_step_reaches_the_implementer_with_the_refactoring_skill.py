"""A step-loop spawn request for a tagged step yields an implementer spawn that holds the
refactoring skill; a request for an untagged step, or the verifier reviewing a tagged one, does not.

The journey crosses two boundaries: the step-loop command renders the request from a plan, and the
orchestrator passes that request's Agent-tool parameters unchanged to a spawn, whose hooks run
against a copy of the plugin in which no definition preloads the refactoring skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers.refactoring_delivery import MARKER, ROLES, Installation
from tests.acceptance.drivers.step_loop import Step, Work, attempt, build_loop, next_action

TAGGED_TITLE = f"{MARKER} Extract the widget's value into its own module"


@pytest.fixture
def end_state(tmp_path: Path) -> Installation:
    installation = rd.new_installation(tmp_path / "plugin")
    for role in ROLES:
        rd.without_preload(installation, role)
    return installation


def _spawn_for(installation: Installation, project: Path, request: dict) -> rd.Spawn:
    call = request["agent_call"]
    return rd.spawn(installation, project, call["subagent_type"], call["prompt"])


@pytest.mark.parametrize(
    "title",
    [TAGGED_TITLE, "[phase:refactoring] Extract the widget's value into its own module"],
    ids=["as-written", "other-case-and-spacing"],
)
def test_the_request_for_a_tagged_step_yields_an_implementer_holding_the_skill(
    tmp_path: Path, end_state: Installation, title: str
) -> None:
    task = build_loop(tmp_path / "loop", Step("1", title=title))
    request = next_action(task).request

    spawned = _spawn_for(end_state, task.root, request)

    assert spawned.agent_type == "praxion:implementer"
    assert rd.copies_held(spawned) == rd.Copies(whole=1, most=1), (
        "the implementer spawned for a tagged step does not hold one whole copy of the skill"
    )


def test_the_request_for_an_untagged_step_that_mentions_the_marker_yields_no_skill(
    tmp_path: Path, end_state: Installation
) -> None:
    step = Step(
        "1",
        implementation=f"Keep `value()` as it is; a later {MARKER} step restructures the module.",
    )
    task = build_loop(tmp_path / "loop", step)
    request = next_action(task).request

    spawned = _spawn_for(end_state, task.root, request)

    assert rd.copies_held(spawned).most == 0, "an untagged step pulled the skill"


def test_the_verifier_reviewing_a_tagged_step_receives_no_skill(
    tmp_path: Path, end_state: Installation
) -> None:
    task = build_loop(
        tmp_path / "loop", Step("1", title=TAGGED_TITLE, annotations=("**review**: force",))
    )
    attempt(task, Work())
    review = next_action(task).request

    spawned = _spawn_for(end_state, task.root, review)

    assert spawned.agent_type == "praxion:verifier"
    assert rd.copies_held(spawned).most == 0, "the reviewing verifier received the skill"
