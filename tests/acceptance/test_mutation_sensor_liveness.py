"""The mutation check proves the sensor still bites, where a pipeline step runs it.

The check runs `scripts/mutation_sensor.py` over a fixture inside the repository,
so the sensor's test runs see the project's own test configuration. It passes
only when the sensor ran and its result is the one fixed in advance: mutants
killed, mutants surviving, survivors only where the fixture's tests are loose.
Every other report -- a refusal of any kind, no survivor, a survivor somewhere
else, or nothing at all -- fails the check, and it says why.

Each dead sensor below changes only the sensor, in a scratch copy of the
repository, and the check is run exactly as the scheduled run runs it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.drivers import dead_gates
from tests.acceptance.drivers.gate_liveness import (
    Gate,
    LivenessRun,
    RepoCopy,
    Verdict,
    make_copy,
    run_liveness,
)


def _run_mutation_check(copy: RepoCopy) -> tuple[LivenessRun, Verdict]:
    run = run_liveness(copy, [Gate.MUTATION_SENSOR])
    return run, run.verdict(Gate.MUTATION_SENSOR)


def _copy_with_dead_sensor(tmp_path: Path, kill: Callable[[RepoCopy], object]) -> RepoCopy:
    copy = make_copy(tmp_path)
    kill(copy)
    copy.commit("dead mutation sensor")
    return copy


def test_live_sensor_on_the_in_repository_fixture_passes_the_check(tmp_path):
    run, verdict = _run_mutation_check(make_copy(tmp_path))

    assert verdict.passed, run.describe()
    assert run.exit_code == 0, run.describe()


@pytest.mark.liveness
def test_sensor_refusing_because_its_test_runs_inherit_parallel_options_fails_the_check(
    tmp_path,
):
    copy = _copy_with_dead_sensor(tmp_path, dead_gates.mutation_sensor_parallel_inheritance_failure)

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert run.exit_code != 0, run.describe()
    assert "reason=run-failed" in verdict.reason, (
        f"the failure should quote the sensor's refusal line\n{run.describe()}"
    )


@pytest.mark.liveness
def test_sensor_refusing_with_the_layout_reason_still_fails_the_check(tmp_path):
    copy = _copy_with_dead_sensor(
        tmp_path,
        lambda c: dead_gates.mutation_sensor_refuses(
            c, "not-flat-layout", "targets and tests are not in one flat directory"
        ),
    )

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert "not-flat-layout" in verdict.reason, (
        f"the failure should quote the sensor's refusal line\n{run.describe()}"
    )


@pytest.mark.liveness
def test_sensor_reporting_success_without_running_fails_the_check(tmp_path):
    copy = _copy_with_dead_sensor(
        tmp_path, dead_gates.mutation_sensor_reports_success_without_running
    )

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"


@pytest.mark.liveness
def test_sensor_reporting_a_survivor_outside_the_loosely_tested_code_fails_the_check(
    tmp_path,
):
    copy = _copy_with_dead_sensor(
        tmp_path, dead_gates.mutation_sensor_reports_survivor_in_unforeseen_code
    )

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"


@pytest.mark.liveness
def test_sensor_that_prints_nothing_fails_the_check_and_says_why(tmp_path):
    copy = _copy_with_dead_sensor(tmp_path, dead_gates.mutation_sensor_says_nothing)

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"


@pytest.mark.liveness
def test_missing_sensor_fails_the_check_and_says_why(tmp_path):
    copy = _copy_with_dead_sensor(tmp_path, lambda c: c.remove(dead_gates.MUTATION_SENSOR))

    run, verdict = _run_mutation_check(copy)

    assert not verdict.passed, run.describe()
    assert run.exit_code != 0, run.describe()
    assert verdict.reason.strip(), f"a failure with no reason\n{run.describe()}"
