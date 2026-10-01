"""A step tagged `mutation: on` cannot complete without a mutation reading.

A tagged step whose recorded runs carry no `Mutation:` line, or carry
`Mutation: unavailable` for any reason other than `not-flat-layout`, is blocked:
it does not complete, the pipeline does not advance past it, and the block
names the step and the refusal reason or the missing line. A later run that
records the sensor ran, or records the `not-flat-layout` refusal, lets it
complete. The `not-flat-layout` refusal and every untagged step behave as they
did before.

Each scenario's step is otherwise done: its files changed, it is checked off,
and its recorded run is green.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.step_gate import (
    STEP,
    STEP_TITLE,
    RecordedRun,
    build_task,
    judge_step,
)

TAGGED = "mutation: on"
SENSOR_RAN = "Mutation: survivors=1 mutants=14 targets=[widget.py] (read_widget: 1)"
LAYOUT_REFUSAL = (
    "Mutation: unavailable reason=not-flat-layout (targets and tests are not in one flat directory)"
)


def _names_the_step(message: str) -> bool:
    return f"Step {STEP}" in message or STEP_TITLE in message


def _refusal(reason: str) -> str:
    return f"Mutation: unavailable reason={reason} (the sensor could not produce a reading)"


@pytest.mark.parametrize(
    "reason",
    [
        "run-failed",
        "toolchain-missing",
        "run-timeout",
        "path-missing",
        "pyproject-present",
        "mutants-dir-present",
        "a-reason-no-one-has-seen-yet",
    ],
)
def test_tagged_step_whose_sensor_refused_is_blocked_naming_the_reason(tmp_path, reason):
    task = build_task(tmp_path, tag=TAGGED, runs=(RecordedRun(_refusal(reason)),))

    judgment = judge_step(task)

    assert not judgment.completes, judgment.message
    assert reason in judgment.message, (
        f"the block should name the refusal reason {reason!r}: {judgment.message!r}"
    )
    assert _names_the_step(judgment.message), (
        f"the block should name the step: {judgment.message!r}"
    )


def test_tagged_step_with_no_mutation_line_is_blocked_naming_the_missing_line(tmp_path):
    task = build_task(tmp_path, tag=TAGGED, runs=(RecordedRun(None),))

    judgment = judge_step(task)

    assert not judgment.completes, judgment.message
    assert "mutation" in judgment.message.lower(), (
        f"the block should name the missing mutation line: {judgment.message!r}"
    )
    assert _names_the_step(judgment.message), (
        f"the block should name the step: {judgment.message!r}"
    )


@pytest.mark.parametrize(
    "later_line",
    [SENSOR_RAN, LAYOUT_REFUSAL],
    ids=["sensor-ran", "layout-refusal"],
)
def test_blocked_tagged_step_completes_once_a_later_run_records_a_reading(tmp_path, later_line):
    task = build_task(
        tmp_path,
        tag=TAGGED,
        runs=(RecordedRun(_refusal("run-failed")), RecordedRun(later_line)),
    )

    judgment = judge_step(task)

    assert judgment.completes, judgment.message


def test_tagged_step_with_no_line_completes_once_a_later_run_records_the_sensor_ran(tmp_path):
    task = build_task(tmp_path, tag=TAGGED, runs=(RecordedRun(None), RecordedRun(SENSOR_RAN)))

    judgment = judge_step(task)

    assert judgment.completes, judgment.message


def test_tagged_step_whose_sensor_ran_completes(tmp_path):
    task = build_task(tmp_path, tag=TAGGED, runs=(RecordedRun(SENSOR_RAN),))

    judgment = judge_step(task)

    assert judgment.completes, judgment.message


def test_tagged_step_with_the_layout_refusal_completes_as_before(tmp_path):
    task = build_task(tmp_path, tag=TAGGED, runs=(RecordedRun(LAYOUT_REFUSAL),))

    judgment = judge_step(task)

    assert judgment.completes, judgment.message


@pytest.mark.parametrize(
    ("tag", "line"),
    [
        (None, None),
        ("mutation: off", None),
        (None, _refusal("run-failed")),
    ],
    ids=["no-tag", "tag-off", "no-tag-with-a-stray-refusal"],
)
def test_untagged_step_completes_without_any_mutation_reading(tmp_path, tag, line):
    task = build_task(tmp_path, tag=tag, runs=(RecordedRun(line),))

    judgment = judge_step(task)

    assert judgment.completes, judgment.message
