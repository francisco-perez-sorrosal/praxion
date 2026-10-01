"""The hook check proves a spawn from a subdirectory still lands in the checkout's log.

The check replays a spawn -- the spawned agent's start and the completed spawn
call whose prompt names a task slug -- to the commands the hook registration
lists, in a scratch checkout, with the session's working directory set below the
checkout root. It passes only when the checkout's own log holds the agent-start
row and the spawn row and no log appeared in the subdirectory.

Each dead hook set below changes only the commands `hooks/hooks.json` registers,
in a scratch copy of the repository.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tests.acceptance.drivers import dead_gates
from tests.acceptance.drivers.gate_liveness import (
    Gate,
    LivenessRun,
    RepoCopy,
    Verdict,
    make_copy,
    run_liveness,
)


def _run_hook_check(copy: RepoCopy) -> tuple[LivenessRun, Verdict]:
    run = run_liveness(copy, [Gate.OBSERVATION_HOOKS])
    return run, run.verdict(Gate.OBSERVATION_HOOKS)


def _copy_with_dead_hooks(tmp_path: Path, kill: Callable[[RepoCopy], None]) -> RepoCopy:
    copy = make_copy(tmp_path)
    kill(copy)
    copy.commit("dead observation hooks")
    return copy


def test_registered_hooks_record_a_spawn_from_a_subdirectory_and_pass_the_check(tmp_path):
    run, verdict = _run_hook_check(make_copy(tmp_path))

    assert verdict.passed, run.describe()
    assert run.exit_code == 0, run.describe()


def test_hooks_that_write_nothing_fail_the_check_naming_the_missing_row(tmp_path):
    copy = _copy_with_dead_hooks(tmp_path, dead_gates.hooks_do_nothing)

    run, verdict = _run_hook_check(copy)

    assert not verdict.passed, run.describe()
    assert run.exit_code != 0, run.describe()
    assert verdict.reason.strip(), f"a failure that names no row\n{run.describe()}"


def test_hooks_logging_beside_the_session_directory_fail_the_check(tmp_path):
    copy = _copy_with_dead_hooks(tmp_path, dead_gates.hooks_log_beside_session_directory)

    run, verdict = _run_hook_check(copy)

    assert not verdict.passed, run.describe()
    assert verdict.reason.strip(), f"a failure that names no row\n{run.describe()}"
