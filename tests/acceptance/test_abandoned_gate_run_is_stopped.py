"""A detached gate run that outlives its pocket's bound is stopped even when nobody comes back.

The step-loop driver starts each gate run detached, so a `record` call cut off by its
caller loses nothing. A run still going past its bound plus the stop allowance is stopped,
with every process it started, with no later `record` call; a later `record` that does
attach reads it as cut off, red, keeping the failures it showed before the stop, and never
as not started. A run that finishes inside its bound is never stopped, a process number that
now belongs to something else is never signalled, the bound in force is the one recorded
when the run started, and the stop needs no tool the systems do not ship and no hook.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.acceptance.drivers import abandoned_gate_run as abandoned
from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.abandoned_gate_run import BOUND_SECONDS, SLOW_POCKET, SLOW_TESTS
from tests.acceptance.drivers.pocket_gate import gate_block, prompt_of
from tests.acceptance.drivers.step_loop import LoopTask, Step, build_loop, next_action, record

FAILURES = ("test_first_slow_failure", "test_second_slow_failure")


@pytest.fixture
def pids_file(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "slow-run-pids.txt"
    yield path
    abandoned.reap(path)


def _loop(tmp_path: Path, *, declared_bound: int | None = None) -> LoopTask:
    task = build_loop(
        tmp_path,
        Step("1", more_files=(SLOW_TESTS,)),
        base_files={
            f"{SLOW_POCKET}/pyproject.toml": abandoned.slow_pocket_config(
                bound_seconds=declared_bound
            )
        },
    )
    if declared_bound is None:
        pocket_gate.bound_pocket_run(task, SLOW_POCKET, BOUND_SECONDS)
    return task


def test_an_abandoned_run_past_its_bound_is_stopped_with_every_process_it_started(
    tmp_path: Path, pids_file: Path
) -> None:
    task = _loop(tmp_path)
    _, _, pids = abandoned.abandon_a_gate_run(task, abandoned.hanging_tests(pids_file), pids_file)
    assert all(abandoned.is_alive(pid) for pid in pids), "the run did not outlive the cut call"

    left = abandoned.still_running_after_the_allowance(pids, BOUND_SECONDS)

    assert left == [], f"processes of the abandoned run still alive past its bound: {left}"


def test_a_later_record_reads_the_stopped_run_as_cut_off_with_its_earlier_failures(
    tmp_path: Path, pids_file: Path
) -> None:
    task = _loop(tmp_path)
    request_id, agent_id, pids = abandoned.abandon_a_gate_run(
        task, abandoned.hanging_tests(pids_file), pids_file
    )
    left = abandoned.still_running_after_the_allowance(pids, BOUND_SECONDS)
    assert left == [], f"the abandoned run was not stopped before any call: {left}"

    returned = record(task, request_id, agent_id=agent_id, marker="complete")

    assert returned.recorded is not None, returned.doc
    assert returned.recorded["gate"]["verdict"] != "verified-complete", returned.doc
    block = gate_block(task, request_id)
    assert SLOW_POCKET in block, block
    assert re.search(rf"\b{BOUND_SECONDS}(\.0+)?\s*s", block), block
    assert [name for name in FAILURES if name not in block] == [], block
    starts = pids_file.read_text(encoding="utf-8").splitlines()
    assert len(starts) == 1, f"the stopped run was read as not started and run again: {starts}"
    prompt = prompt_of(next_action(task))
    failed = [line for line in prompt.splitlines() if line.startswith("Failed:")]
    assert [n for n in FAILURES if not any(n in line for line in failed)] == [], prompt


def test_a_run_that_finishes_inside_its_bound_is_never_stopped(
    tmp_path: Path, pids_file: Path
) -> None:
    done = tmp_path / "slow-run-finished"
    task = _loop(tmp_path)
    text = abandoned.hanging_tests(pids_file, failures=False, finish_after=6, done_file=done)
    request_id, agent_id, _ = abandoned.abandon_a_gate_run(task, text, pids_file)
    finished = abandoned.appears_within(done, BOUND_SECONDS)

    returned = record(task, request_id, agent_id=agent_id, marker="complete")

    assert finished, "the run was stopped before it finished inside its bound"
    assert returned.recorded is not None, returned.doc
    assert returned.recorded["gate"]["verdict"] == "verified-complete", returned.doc


def test_the_bound_in_force_is_the_one_recorded_when_the_run_started(
    tmp_path: Path, pids_file: Path
) -> None:
    task = _loop(tmp_path, declared_bound=BOUND_SECONDS)
    _, _, pids = abandoned.abandon_a_gate_run(task, abandoned.hanging_tests(pids_file), pids_file)
    (task.root / SLOW_POCKET / "pyproject.toml").write_text(
        abandoned.slow_pocket_config(bound_seconds=900), encoding="utf-8"
    )

    left = abandoned.still_running_after_the_allowance(pids, BOUND_SECONDS)

    assert left == [], f"the run was held to the later declaration, not its own bound: {left}"


def test_a_process_number_that_now_belongs_to_something_else_is_never_signalled(
    tmp_path: Path, pids_file: Path
) -> None:
    task = _loop(tmp_path)
    request_id, agent_id, _ = abandoned.abandon_a_gate_run(
        task, abandoned.hanging_tests(pids_file), pids_file
    )
    pid_file = abandoned.slow_run_pid_file(task)
    launcher = int(pid_file.read_text(encoding="utf-8").split()[0])
    innocent = subprocess.Popen(["sleep", "600"], start_new_session=True)
    try:
        abandoned.reap(pids_file)
        subprocess.run(["kill", "-9", str(launcher)], check=False)
        pid_file.write_text(f"{innocent.pid}\n", encoding="utf-8")

        abandoned.wait_past_the_allowance(BOUND_SECONDS)
        record(task, request_id, agent_id=agent_id, marker="complete")

        assert innocent.poll() is None, "a process that is not the run's own was signalled"
    finally:
        innocent.kill()
        innocent.wait(timeout=30)


def test_the_stop_needs_no_tool_beyond_the_systems_own_and_no_hook(
    tmp_path: Path, pids_file: Path
) -> None:
    task = _loop(tmp_path)
    abandoned.systems_own_tools_only(task, tmp_path / "bare-host")
    _, _, pids = abandoned.abandon_a_gate_run(task, abandoned.hanging_tests(pids_file), pids_file)

    left = abandoned.still_running_after_the_allowance(pids, BOUND_SECONDS)

    assert left == [], f"on a bare host the abandoned run was not stopped: {left}"
