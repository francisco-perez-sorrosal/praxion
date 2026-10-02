"""What a liveness run as a whole guarantees, whichever of its checks fail.

Every check runs even when another fails; any failing check turns the run red
and the run names each failing gate with what it expected and what it saw. A
run, passing or failing, local or inside an assistant session, leaves the
repository's tracked files as they were and writes no row to the project's own
observation log: its simulated spawns land only in its scratch checkout.

The selection audit runs the whole suite and is exercised under `tests/e2e/`;
these scenarios run the three quick checks.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.drivers import dead_gates
from tests.acceptance.drivers.gate_liveness import (
    PROJECT_LOG,
    PROJECT_LOG_ARCHIVE,
    QUICK_GATES,
    Gate,
    RepoCopy,
    make_copy,
    run_liveness,
)

_PROJECT_ROW = json.dumps(
    {
        "event_type": "session_start",
        "session_id": "liveness-acceptance-project-session",
        "timestamp": "2026-10-01T00:00:00Z",
    }
)


@pytest.mark.liveness
def test_every_check_reports_and_the_run_fails_when_two_gates_are_dead(tmp_path):
    copy = make_copy(tmp_path)
    dead_gates.mutation_sensor_parallel_inheritance_failure(copy)
    dead_gates.spawn_counter_attributes_by_checkout_name(copy)
    copy.commit("two dead gates")

    run = run_liveness(copy, QUICK_GATES)

    assert run.exit_code not in (0, None), run.describe()
    assert not run.verdict(Gate.MUTATION_SENSOR).passed, run.describe()
    assert not run.verdict(Gate.SPAWN_COUNT).passed, run.describe()
    assert run.verdict(Gate.OBSERVATION_HOOKS).passed, (
        f"the live hooks should still pass beside two dead gates\n{run.describe()}"
    )


@pytest.mark.liveness
def test_each_failing_check_says_what_it_expected_and_what_it_observed(tmp_path):
    copy = make_copy(tmp_path)
    dead_gates.mutation_sensor_reports_success_without_running(copy)
    dead_gates.spawn_counter_attributes_by_checkout_name(copy)
    copy.commit("two dead gates")

    run = run_liveness(copy, QUICK_GATES)

    failing_reasons = {
        gate: run.verdict(gate).reason.strip() for gate in (Gate.MUTATION_SENSOR, Gate.SPAWN_COUNT)
    }
    assert all(failing_reasons.values()), (
        f"each failing gate needs its expected-against-observed reason: "
        f"{failing_reasons}\n{run.describe()}"
    )


def _all_gates_live(copy: RepoCopy) -> dict[str, str]:
    return {}


def _mutation_sensor_dead(copy: RepoCopy) -> dict[str, str]:
    dead_gates.mutation_sensor_parallel_inheritance_failure(copy)
    return {}


def _inside_an_assistant_session(copy: RepoCopy) -> dict[str, str]:
    """The variables a session in this project exports to the commands it runs."""
    return {
        "CLAUDE_PROJECT_DIR": str(copy.root),
        "CLAUDE_PLUGIN_ROOT": str(copy.root),
        "CLAUDECODE": "1",
    }


@pytest.mark.parametrize(
    "prepare",
    [_all_gates_live, _mutation_sensor_dead, _inside_an_assistant_session],
    ids=["passing-run", "failing-run", "run-inside-a-session"],
)
def test_a_run_leaves_tracked_files_and_the_project_log_unchanged(
    tmp_path, prepare: Callable[[RepoCopy], dict[str, str]]
):
    copy = make_copy(tmp_path)
    session_env = prepare(copy)
    copy.commit("liveness run under test")
    log_before = copy.seed_project_log([_PROJECT_ROW])

    run_liveness(copy, QUICK_GATES, extra_env=session_env)

    assert copy.status() == "", f"the run changed the repository:\n{copy.status()}"
    assert copy.path(PROJECT_LOG).read_bytes() == log_before, (
        "the run wrote to the project's own observation log"
    )
    assert not copy.path(PROJECT_LOG_ARCHIVE).exists(), (
        "the run rotated the project's own observation log"
    )


def test_a_run_creates_no_project_log_where_there_was_none(tmp_path: Path):
    copy = make_copy(tmp_path)

    run_liveness(copy, QUICK_GATES)

    assert not copy.path(PROJECT_LOG).exists(), (
        "the run's simulated spawns reached the project's own observation log"
    )
    assert copy.status() == "", f"the run changed the repository:\n{copy.status()}"
