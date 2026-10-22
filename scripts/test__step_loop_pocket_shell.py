"""Tests for the shell of the pocket-run module (``scripts/_step_loop_pocket_runs.py``): a pocket's
tests run detached, in a session of their own, and a later call picks the run up again.

Every run here is a real short subprocess. Nothing waits on elapsed time: the code under test
takes its clock and its sleep as arguments, so a bound passing is a fake clock moving, and the
only real waiting is ``wait_until`` -- polling for a condition the OS settles on its own (a
process written its first line, a killed process gone) with a generous guard.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_pocket_runs as pocket_runs  # noqa: E402
from _step_loop_pocket_runs import (  # noqa: E402
    CutOff,
    Finished,
    NotStarted,
    PocketBound,
    RunSpec,
    StillRunning,
    read_run,
    run_detached,
)

GUARD_SECONDS = 30.0
BOUND = 100.0
LONG_RUNNING = ("sleep", "600")
PYTHON = sys.executable


class FakeClock:
    """A clock that moves only when told to, or when the code under test sleeps."""

    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def wait_until(condition, what: str) -> None:
    deadline = time.monotonic() + GUARD_SECONDS
    while not condition():
        assert time.monotonic() < deadline, f"gave up waiting for {what}"
        time.sleep(0.01)


def has_text(path: Path) -> bool:
    return path.exists() and path.read_text(encoding="utf-8").strip() != ""


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def make_spec(tmp_path):
    """Build run specs under tmp_path; whatever is still running at teardown is killed."""
    made: list[RunSpec] = []

    def make(argv, bound_seconds=BOUND, number=1, cwd=None) -> RunSpec:
        spec = RunSpec(
            run_dir=tmp_path / "gate" / "request-1",
            number=number,
            argv=tuple(argv),
            cwd=cwd if cwd is not None else tmp_path,
            bound=PocketBound("eval", bound_seconds, "declared"),
        )
        made.append(spec)
        return spec

    yield make
    for spec in made:
        read_run(spec, now=lambda: float("inf"))  # past every bound: kills what still runs


def python_run(code: str) -> tuple[str, ...]:
    return (PYTHON, "-c", code)


def wait_for_text(spec: RunSpec, text: str) -> None:
    wait_until(lambda: has_text(spec.log_path) and text in spec.log_path.read_text("utf-8"), text)


# --- Start, finish and read ---


def test_a_run_that_exits_is_read_as_finished_with_its_output_and_code(make_spec):
    spec = make_spec(python_run("print('hello from the pocket')"))

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert (run.pocket, run.returncode, run.argv) == ("eval", 0, spec.argv)
    assert "hello from the pocket" in run.output
    assert run.log_path == spec.run_dir / "1.log"


def test_a_failing_exit_code_is_kept(make_spec):
    spec = make_spec(python_run("import sys; sys.exit(3)"))

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert run.returncode == 3


def test_the_first_line_of_the_log_is_the_full_command(make_spec):
    spec = make_spec(python_run("print('x y')"))

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert run.output.splitlines()[0] == "$ " + shlex.join(spec.argv)


def test_output_goes_to_the_log_and_both_streams_are_kept(make_spec):
    spec = make_spec(python_run("import sys; print('out'); print('err', file=sys.stderr)"))

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert "out" in run.output
    assert "err" in run.output


def test_the_run_leads_a_session_of_its_own(make_spec):
    spec = make_spec(python_run("import os; print(os.getsid(0))"))

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    session = int(run.output.splitlines()[-1])
    assert session == int(spec.pid_path.read_text(encoding="utf-8"))
    assert session != os.getsid(0)


def test_colour_is_off_in_the_run_whatever_the_callers_environment_says(make_spec, monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    spec = make_spec(
        python_run("import os; print(os.environ.get('FORCE_COLOR'), os.environ['NO_COLOR'])")
    )

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert run.output.splitlines()[-1] == "None 1"


def test_a_missing_working_directory_is_not_started_and_leaves_nothing_to_adopt(
    make_spec, tmp_path
):
    spec = make_spec(python_run("pass"), cwd=tmp_path / "absent")

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, NotStarted)
    assert "could not start" in run.reason
    assert not spec.start_path.exists()


def test_reading_a_run_that_was_never_started_says_so(make_spec):
    spec = make_spec(python_run("pass"))

    run = read_run(spec)

    assert isinstance(run, NotStarted)
    assert "no run was started" in run.reason


def test_two_invocations_of_one_request_keep_their_own_files(make_spec):
    first = make_spec(python_run("print('one')"), number=1)
    second = make_spec(python_run("print('two')"), number=2)

    run_first = run_detached(first, give_up_at=time.time() + GUARD_SECONDS)
    run_second = run_detached(second, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run_first, Finished)
    assert isinstance(run_second, Finished)
    assert run_first.output.splitlines()[-1] == "one"
    assert run_second.output.splitlines()[-1] == "two"


# --- Attach instead of a second start ---


def test_a_finished_run_is_read_again_never_run_again(make_spec, tmp_path):
    counter = tmp_path / "launches"
    spec = make_spec(python_run(f"open({str(counter)!r}, 'a').write('x\\n')"))

    first = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)
    second = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)
    third = read_run(spec)

    assert first == second == third
    assert counter.read_text(encoding="utf-8") == "x\n"


def test_attaching_to_a_run_in_progress_starts_no_second_process(make_spec, monkeypatch):
    launches: list[object] = []
    real_popen = subprocess.Popen

    def counting_popen(*args, **kwargs):
        launches.append(args)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(pocket_runs.subprocess, "Popen", counting_popen)
    clock = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING)

    first = run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    stamp = spec.start_path.read_text(encoding="utf-8")
    second = run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)

    assert isinstance(first, StillRunning)
    assert isinstance(second, StillRunning)
    assert len(launches) == 1
    assert spec.start_path.read_text(encoding="utf-8") == stamp


def test_a_run_still_inside_its_bound_when_the_caller_gives_up_is_still_running(make_spec):
    clock = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)

    run = run_detached(spec, give_up_at=1000.0 + 10, now=clock, sleep=clock.sleep)

    assert isinstance(run, StillRunning)
    assert (run.pocket, run.bound) == ("eval", spec.bound)
    assert run.elapsed == pytest.approx(10.0, abs=1.0)
    assert clock() >= 1000.0 + 10  # it waited by sleeping, up to the moment it gave up


# --- The bound, from the recorded start ---


def test_a_run_past_its_bound_is_killed_with_its_whole_group_and_read_as_cut_off(
    make_spec, tmp_path
):
    grandchild_pid = tmp_path / "grandchild.pid"
    script = (
        f"sleep 600 & echo $! > {grandchild_pid}; echo 'tests/t.py::test_a FAILED [ 50%]'; wait"
    )
    clock = FakeClock(1000.0)
    spec = make_spec(("sh", "-c", script), bound_seconds=BOUND)
    run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    wait_until(lambda: has_text(grandchild_pid), "the grandchild to record its pid")
    wait_for_text(spec, "test_a FAILED")
    grandchild = int(grandchild_pid.read_text(encoding="utf-8"))
    leader = int(spec.pid_path.read_text(encoding="utf-8"))
    clock.now = 1000.0 + BOUND

    run = read_run(spec, now=clock)

    assert isinstance(run, CutOff)
    assert (run.pocket, run.bound, run.argv) == ("eval", spec.bound, spec.argv)
    assert run.failed_seen == ("tests/t.py::test_a",)
    assert "tests/t.py::test_a FAILED" in run.output
    wait_until(lambda: not process_exists(grandchild), "the grandchild to be gone")
    wait_until(lambda: not process_exists(leader), "the group leader to be gone")


def test_a_cut_off_run_reads_the_same_when_looked_at_again(make_spec):
    clock = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
    run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    clock.now = 1000.0 + BOUND + 5

    first = read_run(spec, now=clock)
    second = read_run(spec, now=clock)

    assert isinstance(first, CutOff)
    assert first == second


def test_the_bound_runs_from_the_recorded_start_not_from_the_call_that_attaches(make_spec):
    start = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
    run_detached(spec, give_up_at=start(), now=start, sleep=start.sleep)

    later_call = FakeClock(1000.0 + BOUND + 50)
    run = run_detached(spec, give_up_at=later_call() + 5, now=later_call, sleep=later_call.sleep)

    assert isinstance(run, CutOff)
    assert later_call() == 1000.0 + BOUND + 50  # cut off on the first look, after no wait


def test_a_run_one_instant_inside_its_bound_is_still_running(make_spec):
    clock = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
    run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    clock.now = 1000.0 + BOUND - 0.5

    assert isinstance(read_run(spec, now=clock), StillRunning)


def test_a_run_that_exited_but_took_longer_than_its_bound_is_cut_off_all_the_same(make_spec):
    spec = make_spec(python_run("print('slow but done')"), bound_seconds=BOUND)
    finished = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)
    assert isinstance(finished, Finished)
    spec.start_path.write_text("1000.0\n", encoding="utf-8")  # as if it had started long before

    run = read_run(spec)

    assert isinstance(run, CutOff)
    assert "slow but done" in run.output


# --- A run that vanished, and a record that cannot be trusted ---


def test_a_run_whose_group_was_killed_from_outside_ends_without_a_record(make_spec):
    clock = FakeClock(1000.0)
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
    run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    wait_until(lambda: has_text(spec.pid_path), "the launcher's pid file")
    os.killpg(int(spec.pid_path.read_text(encoding="utf-8")), signal.SIGKILL)

    wait_until(lambda: isinstance(read_run(spec, now=clock), NotStarted), "the group to be gone")

    run = read_run(spec, now=clock)
    assert isinstance(run, NotStarted)
    assert "without an exit record" in run.reason


@pytest.mark.parametrize("garbage", ["0", "1", "-5", "abc", ""])
def test_a_pid_record_that_names_no_process_of_ours_is_never_signalled(make_spec, garbage):
    spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
    spec.run_dir.mkdir(parents=True)
    spec.start_path.write_text("1000.0\n", encoding="utf-8")
    spec.pid_path.write_text(garbage, encoding="utf-8")
    spec.log_path.write_text("$ sleep 600\n", encoding="utf-8")

    run = read_run(spec, now=FakeClock(1000.0 + BOUND))

    assert isinstance(run, CutOff)  # and this very process, in group 0, is still here


def test_an_unreadable_start_record_is_not_started(make_spec):
    spec = make_spec(LONG_RUNNING)
    spec.run_dir.mkdir(parents=True)
    spec.start_path.write_text("not a time", encoding="utf-8")

    run = read_run(spec)

    assert isinstance(run, NotStarted)
    assert "start record" in run.reason


def test_an_unreadable_exit_record_is_not_started(make_spec):
    spec = make_spec(LONG_RUNNING)
    spec.run_dir.mkdir(parents=True)
    spec.start_path.write_text("1000.0\n", encoding="utf-8")
    spec.exit_path.write_text("done", encoding="utf-8")

    run = read_run(spec, now=FakeClock(1000.0))

    assert isinstance(run, NotStarted)
    assert "exit record" in run.reason
