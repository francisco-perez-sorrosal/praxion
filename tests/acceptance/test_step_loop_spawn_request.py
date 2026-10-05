"""The spawn request is ready to execute as it stands, and its prompt carries only its fixed parts.

The orchestrator passes the request's Agent-tool parameters unchanged: the implementer
agent type, the model the step's routing annotation selects, a short description and a
three-line prompt whose first line attributes the spawn to the pipeline. The rendered
prompt it points to holds the step block verbatim, the brief's health guards verbatim,
earlier attempts from the second attempt on and the stop instruction -- and never a
model name, a plan field from outside the step block, or a second `Read-only:` line.
Rendering is reproducible and bounded: an oversized step block is reported, never cut.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.step_loop import (
    GOAL_TEXT,
    HEALTH_GUARD,
    INTENT_TEXT,
    SLUG,
    Step,
    Work,
    attempt,
    build_loop,
    next_action,
    record_not_started,
    step_block,
)

PROMPT_CEILING = 16_000


def _prompt_of(request: dict) -> str:
    return Path(request["prompt_path"]).read_text(encoding="utf-8")


def test_the_request_names_its_step_attempt_and_cap_under_a_deterministic_id(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    request = next_action(task).request

    assert request["id"] == "s7-a1-implement"
    assert request["kind"] == "implement"
    assert request["step"] == "7"
    assert request["attempt"] == 1
    assert request["attempt_cap"] >= 1


def test_the_agent_call_is_the_implementer_with_a_short_description(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    call = next_action(task).request["agent_call"]

    assert call["subagent_type"] == "praxion:implementer"
    assert 0 < len(call["description"]) <= 40


def test_the_agent_call_carries_only_the_agent_tools_parameters_and_no_background_flag(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    call = next_action(task).request["agent_call"]

    assert set(call) == {"subagent_type", "model", "prompt", "description"}, sorted(call)


@pytest.mark.parametrize(
    ("annotations", "model"),
    [
        (("tier: H",), "opus"),
        ((), "sonnet"),
        (("tier: L",), "sonnet"),
    ],
    ids=[
        "high-tier-step-routes-to-opus",
        "unannotated-step-routes-to-sonnet",
        "low-tier-step-never-routes-to-haiku",
    ],
)
def test_the_model_follows_the_step_routing_annotation(tmp_path, annotations, model):
    task = build_loop(tmp_path, Step("1", annotations=annotations))

    call = next_action(task).request["agent_call"]

    assert call["model"] == model


def test_the_agent_prompt_is_three_lines_opening_with_the_task_slug(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    request = next_action(task).request

    lines = request["agent_call"]["prompt"].splitlines()
    assert len(lines) == 3, request["agent_call"]["prompt"]
    assert lines[0] == f"Task slug: {SLUG}"
    assert lines[1] == f"Spawn request: {request['id']}"
    assert request["prompt_path"] in lines[2]


def test_the_envelope_tells_the_orchestrator_which_record_call_follows(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    asked = next_action(task)

    assert asked.doc["then"].startswith(
        f"python3 scripts/step_loop.py record {SLUG} --request {asked.request['id']} --agent-id "
    )


def test_the_rendered_prompt_holds_its_fixed_parts_in_order(tmp_path):
    step = Step("7", read_only=("tests/acceptance/test_widget.py::test_widget_returns_its_id",))
    task = build_loop(tmp_path, step)
    request = next_action(task).request

    prompt = _prompt_of(request)

    first, second = prompt.splitlines()[:2]
    assert first == f"Task slug: {SLUG}"
    assert second == f"Spawn request: {request['id']}"
    block_at = prompt.find(step_block(step).rstrip())
    guards_at = prompt.find(HEALTH_GUARD)
    finish_at = prompt.find("<finish>")
    assert block_at != -1, "the step block is not in the prompt verbatim"
    assert guards_at != -1, "the brief's health guards are not in the prompt verbatim"
    assert 0 < block_at < guards_at < finish_at, (block_at, guards_at, finish_at)


def test_the_rendered_prompt_tells_the_agent_to_stop_committable_and_never_commit(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    prompt = _prompt_of(next_action(task).request).lower()

    assert "committable" in prompt
    assert "never commit" in prompt


def test_the_rendered_prompt_binds_the_results_and_progress_files_for_the_step(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    prompt = _prompt_of(next_action(task).request)

    finish = prompt[prompt.find("<finish>") :]
    assert "TEST_RESULTS.md" in finish
    assert "WIP.md" in finish


def test_nothing_from_outside_the_step_block_leaks_into_the_prompt(tmp_path):
    step = Step("7", read_only=("tests/acceptance/test_widget.py::test_widget_returns_its_id",))
    neighbour = Step("8", implementation="Wire the neighbouring widget (neighbour text 61).")
    task = build_loop(tmp_path, step, neighbour)

    prompt = _prompt_of(next_action(task).request)

    assert GOAL_TEXT not in prompt
    assert INTENT_TEXT not in prompt
    assert "neighbour text 61" not in prompt
    assert len(re.findall(r"^\W*Read-only\W*:", prompt, re.MULTILINE)) == 1


@pytest.mark.parametrize("model_name", ["opus", "sonnet", "haiku"])
def test_the_prompt_carries_no_model_name(tmp_path, model_name):
    task = build_loop(tmp_path, Step("7", annotations=("tier: H",)))

    prompt = _prompt_of(next_action(task).request).lower()

    assert model_name not in prompt


def test_a_first_attempt_prompt_has_no_earlier_attempts_and_a_second_names_the_first(tmp_path):
    task = build_loop(tmp_path, Step("7"))
    first_request = next_action(task).request
    first_prompt = _prompt_of(first_request)
    record_not_started(task, first_request["id"], "the Agent tool call failed before launch")
    failed = attempt(task, Work(passes=False))

    second_prompt = _prompt_of(next_action(task).request)

    assert "<previous-attempts>" not in first_prompt
    assert "<previous-attempts>" in second_prompt
    assert failed.recorded["agent_id"] in second_prompt


def test_rendering_the_same_step_and_attempt_again_gives_byte_identical_prompts(tmp_path):
    task = build_loop(tmp_path, Step("7"))
    first = next_action(task).request
    first_bytes = Path(first["prompt_path"]).read_bytes()
    record_not_started(task, first["id"], "the Agent tool call failed before launch")

    again = next_action(task).request

    assert again["id"] == first["id"]
    assert Path(again["prompt_path"]).read_bytes() == first_bytes


def test_an_ordinary_prompt_stays_within_the_size_ceiling(tmp_path):
    task = build_loop(tmp_path, Step("7"))

    prompt = _prompt_of(next_action(task).request)

    assert len(prompt) <= PROMPT_CEILING


def test_an_oversized_step_block_is_reported_and_carried_whole_never_truncated(tmp_path):
    long_text = " ".join(f"clause-{n}" for n in range(3_000))
    step = Step("7", implementation=long_text)
    task = build_loop(tmp_path, step)

    asked = next_action(task)

    assert "step-block-oversize" in asked.warning_codes
    assert step_block(step).rstrip() in _prompt_of(asked.request)
