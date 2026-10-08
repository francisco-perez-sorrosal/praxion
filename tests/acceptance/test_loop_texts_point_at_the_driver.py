"""The texts that run implementer steps, and the budget procedure, agree with the loop.

The spawn-budget procedure is the one place that says how the loop's spawns count: as
iterations bounded by the plan-derived iteration budget, the loop bounded by quality (cap,
then surface; never grind), cost observed and recorded per pipeline, never capped in
dollars. Every other text that speaks of the loop's spawns against a budget points to it.

Inside the loop the driver writes the `Attempts:` line ahead, commits a verified step and
records the return; outside the loop the orchestrator does. The progress template's
`Attempts:` example shows the request the driver names, the resume procedure hands a step
whose `Attempts:` line names a request not yet recorded back to `next`, and the attempt
cap's value is stated only in the completion-handshake procedure.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.shipped_texts import (
    COORDINATION_DETAILS,
    COORDINATION_PROTOCOL,
    DOCUMENT_TEMPLATES,
    IMPLEMENTER_PROMPT,
    PIPELINE_DETAILS,
    RESUME_PIPELINE,
    STEP_LOOP_SKILL,
    lines_containing,
    normalize,
    paragraphs,
    read,
    section,
    sentences_matching,
)

DRIVER = r"step[_-]loop|\bdriver\b"
NEGATION = r"\b(never|not|no)\b"

BUDGET_PROCEDURE_STATES = {
    "loop-spawns-count-as-iterations": (r"iteration", r"\bloop\b|" + DRIVER),
    "bounded-by-the-iteration-budget": (r"iteration budget",),
    "quality-bounds-the-loop-never-grind": (r"\bgrind",),
    "cost-is-never-capped-in-dollars": (r"dollar", NEGATION),
    "cost-is-observed-and-recorded-per-pipeline": (r"\bcost", r"\b(record|observ)\w*"),
}

RUNNING_TEXTS = (PIPELINE_DETAILS, DOCUMENT_TEMPLATES, IMPLEMENTER_PROMPT, RESUME_PIPELINE)

DRIVER_DUTIES = {
    "writes-the-attempts-line": (r"attempts:",),
    "commits-a-verified-step": (r"\bcommit",),
    "records-the-return": (r"\brecord",),
}

NUMERIC_ATTEMPT_CAP = r"\b(two|three|2|3) (fresh )?attempts?\b|\bcap of (two|three|2|3)\b"


def _budget_procedure() -> str:
    return section(read(COORDINATION_DETAILS), r"spawn budget")


@pytest.mark.parametrize("statement", list(BUDGET_PROCEDURE_STATES))
def test_the_budget_procedure_states_how_loop_spawns_count(statement):
    found = sentences_matching(_budget_procedure(), *BUDGET_PROCEDURE_STATES[statement])

    assert found, f"the spawn-budget procedure never states: {statement}"


def test_the_protocols_budget_envelope_points_to_the_budget_procedure():
    pointers = lines_containing(read(COORDINATION_PROTOCOL), r"envelope.*#spawn-budget")

    assert pointers, "the coordination protocol's envelope bullet does not link #spawn-budget"


def _loop_budget_paragraphs_without_a_pointer(relative: str) -> list[str]:
    return [
        p
        for p in paragraphs(read(relative))
        if sentences_matching(p, r"budget", r"iteration|\bloop\b") and "#spawn-budget" not in p
    ]


@pytest.mark.parametrize(
    "text", [COORDINATION_PROTOCOL, STEP_LOOP_SKILL, *RUNNING_TEXTS], ids=lambda t: t
)
def test_every_other_text_on_loop_spawns_and_the_budget_points_to_the_procedure(text):
    assert _loop_budget_paragraphs_without_a_pointer(text) == []


@pytest.mark.parametrize("duty", list(DRIVER_DUTIES))
@pytest.mark.parametrize("text", RUNNING_TEXTS, ids=lambda t: t)
def test_the_text_names_the_driver_as_the_party_that_does_it_inside_the_loop(text, duty):
    found = sentences_matching(read(text), DRIVER, *DRIVER_DUTIES[duty])

    assert found, f"{text} never names the driver as the one that {duty}"


def test_the_completion_handshake_says_the_orchestrator_does_it_outside_the_loop():
    found = sentences_matching(read(PIPELINE_DETAILS), r"outside", r"orchestrator", r"loop")

    assert found, "the completion handshake never says who does it outside the loop"


def test_the_progress_templates_attempts_example_names_the_request():
    examples = lines_containing(normalize(read(DOCUMENT_TEMPLATES)), r"attempts:.*request")

    assert examples, "no `Attempts:` example in the templates names the driver's request"


def test_the_resume_procedure_hands_an_unrecorded_request_back_to_next():
    found = sentences_matching(read(RESUME_PIPELINE), r"attempts", r"\bnext\b", r"record")

    assert found, (
        "the resume procedure never sends a step whose Attempts line names an "
        "unrecorded request back to `next`"
    )


@pytest.mark.parametrize(
    "text",
    [DOCUMENT_TEMPLATES, IMPLEMENTER_PROMPT, RESUME_PIPELINE, STEP_LOOP_SKILL],
    ids=lambda t: t,
)
def test_the_attempt_caps_value_is_not_restated(text):
    assert sentences_matching(read(text), NUMERIC_ATTEMPT_CAP) == []
