"""A plan defect stops the loop on its own cause and never spends an implementer attempt.

A Check that cannot print a pytest summary under the interpreter the driver runs it with is
refused before any request for its step is issued, naming the step, the Check and what its
collection printed. A plan whose Checks collect is driven exactly as before. A step whose
Iterations or Change type value the plan grammar cannot read stops under a cause of its own,
whose evidence names the step and the field and whose handoff says to fix that field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.loop_repairs import EXISTING_STOP_CAUSES, status_json, with_annotation
from tests.acceptance.drivers.step_loop import (
    Step,
    attempt,
    attempts_line,
    build_loop,
    handoff_section,
    ledger_records,
    next_action,
)

ABSENT_PLUGIN = "pytest-absent-acceptance-plugin"
FIRST = "1"
NEEDS_AN_ABSENT_PLUGIN = (
    '[project]\nname = "loop-widget"\nversion = "0.0.0"\n\n'
    "[tool.pytest.ini_options]\n"
    'pythonpath = ["."]\n'
    f'required_plugins = ["{ABSENT_PLUGIN}"]\n'
)


def _uncollectable(tmp_path):
    return build_loop(tmp_path, Step("1"), base_files={"pyproject.toml": NEEDS_AN_ABSENT_PLUGIN})


def test_a_check_that_cannot_print_a_summary_is_refused_before_any_request(tmp_path):
    task = _uncollectable(tmp_path)

    asked = next_action(task)

    assert asked.outcome != "spawn", asked.doc
    assert asked.request is None, asked.doc
    assert attempts_line(task, "1") is None, task.wip_path.read_text(encoding="utf-8")


def test_the_refusal_names_the_step_the_check_and_what_collection_printed(tmp_path):
    task = _uncollectable(tmp_path)

    refused = next_action(task)

    said = refused.text()
    stop_step = str((refused.stop or {}).get("step", "")).removeprefix("Step ")
    assert task.step("1").check_command in said, said
    assert ABSENT_PLUGIN in said, said
    assert stop_step == FIRST or f"Step {FIRST}" in said, said


def test_a_refused_check_spends_no_attempt_and_writes_no_ledger_record(tmp_path):
    task = _uncollectable(tmp_path)
    next_action(task)

    asked_again = next_action(task)
    records, _ = ledger_records(task)

    assert asked_again.request is None, asked_again.doc
    assert records == []
    assert status_json(task)["steps"][0]["attempts"] == 0


def test_a_plan_whose_checks_collect_is_issued_gated_and_recorded_as_before(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    recorded = attempt(task)
    finished = next_action(task)

    assert recorded.doc.get("warnings", []) == [], recorded.doc
    assert recorded.recorded["gate"]["verdict"] == "verified-complete", recorded.doc
    assert finished.outcome == "complete", finished.doc
    assert status_json(task)["steps"][0]["attempts"] == 1


UNREADABLE = {
    "iterations": ("**Iterations**: several, give or take", "Iterations"),
    "change-type": ("**Change type**: a sort of feature, mostly", "Change type"),
}


@pytest.mark.parametrize("case", list(UNREADABLE))
def test_an_unreadable_plan_field_stops_under_a_cause_of_its_own_naming_step_and_field(
    tmp_path, case
):
    line, field = UNREADABLE[case]
    task = build_loop(tmp_path, with_annotation(Step("1"), line))

    stopped = next_action(task)

    assert stopped.stop is not None, stopped.doc
    assert stopped.stop["cause"] not in EXISTING_STOP_CAUSES, stopped.stop
    assert str(stopped.stop["step"]).removeprefix("Step ") == "1", stopped.stop
    assert field in str(stopped.stop["evidence"]), stopped.stop


@pytest.mark.parametrize("case", list(UNREADABLE))
def test_an_unreadable_plan_fields_handoff_says_to_fix_that_field_and_resume(tmp_path, case):
    line, field = UNREADABLE[case]
    task = build_loop(tmp_path, with_annotation(Step("1"), line))

    stopped = next_action(task)

    assert stopped.stop is not None, stopped.doc
    section = handoff_section(
        Path(stopped.stop["handoff"]).read_text(encoding="utf-8"), "§2 Next action"
    )
    assert field in section, section
    assert "step_loop.py next" in section, section
