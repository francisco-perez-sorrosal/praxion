"""Tests for the shell of the pocket-run module (``scripts/_step_loop_pocket_runs.py``): a pocket's
tests run detached, in a session of their own, and a later call picks the run up again.

Every run here is a real short subprocess. Apart from the launcher's own deadline, nothing waits
on elapsed time: the code under test takes its clock and its sleep as arguments, so a bound passing
is a fake clock moving, and the only real waiting is ``wait_until`` -- polling for a condition the
OS settles on its own (a process written its first line, a killed process gone) with a generous
guard. The launcher keeps real time (its deadline is the bound plus a grace of several seconds),
so the tests of its stop run a one-second bound and wait out that deadline.
"""

from __future__ import annotations

import contextlib
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
SHORT_BOUND = 1.0  # the launcher's stop is real time: a short bound keeps those tests brief
LONG_RUNNING = ("sleep", "600")
PYTHON = sys.executable
# Every POSIX shell a launcher may run under: `sh` is dash on Debian-family CI runners and bash on
# macOS, and they disagree about `kill`, arithmetic and redirection errors.
SHELLS = ["sh", "/bin/dash", "/bin/bash"]


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


def has_exited(pid: int) -> bool:
    """Whether `pid` is gone, collecting it first when it is this process's own child."""
    pocket_runs._reap(pid)
    return not process_exists(pid)


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
    spec = make_spec(
        python_run("print('re' + 'ady', flush=True); import time; time.sleep(600)"),
        bound_seconds=BOUND,
    )
    run_detached(spec, give_up_at=clock(), now=clock, sleep=clock.sleep)
    wait_for_text(spec, "ready")  # a group still being forked can outlive the signal
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

    assert isinstance(run, NotStarted)  # and this very process, in group 0, is still here


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


def test_a_stale_pid_record_naming_a_live_unrelated_group_is_never_killed(make_spec):
    bystander = subprocess.Popen(LONG_RUNNING, start_new_session=True)
    try:
        spec = make_spec(LONG_RUNNING, bound_seconds=BOUND)
        spec.run_dir.mkdir(parents=True)
        spec.start_path.write_text("1000.0\n", encoding="utf-8")
        spec.pid_path.write_text(f"{bystander.pid}\n", encoding="utf-8")
        spec.log_path.write_text("$ sleep 600\n", encoding="utf-8")

        run = read_run(spec, now=FakeClock(1000.0 + BOUND))

        assert isinstance(run, NotStarted)
        assert "without an exit record" in run.reason
        assert bystander.poll() is None
    finally:
        os.killpg(bystander.pid, signal.SIGKILL)
        bystander.wait(timeout=GUARD_SECONDS)


def test_the_launcher_records_its_own_pid_and_leads_the_runs_group(make_spec):
    spec = make_spec(LONG_RUNNING)
    run_detached(spec, give_up_at=0.0)

    wait_until(lambda: has_text(spec.pid_path), "the launcher's pid file")

    pid = int(spec.pid_path.read_text(encoding="utf-8"))
    assert os.getpgid(pid) == pid
    assert pocket_runs._launcher_is_ours(spec)


def test_a_run_started_for_another_command_is_not_adopted_and_is_stopped(make_spec):
    first = make_spec(python_run("import time; time.sleep(600)"))
    run_detached(first, give_up_at=0.0)
    wait_until(lambda: has_text(first.pid_path), "the launcher's pid file")
    leader = int(first.pid_path.read_text(encoding="utf-8"))
    other = make_spec(python_run("print('another')"))

    run = run_detached(other, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, NotStarted)
    assert "another command or bound" in run.reason
    wait_until(lambda: not process_exists(leader), "the old run to be stopped")


def test_a_run_started_under_another_bound_is_not_adopted(make_spec):
    first = make_spec(python_run("print('x')"), bound_seconds=BOUND)
    assert isinstance(run_detached(first, give_up_at=time.time() + GUARD_SECONDS), Finished)
    longer = make_spec(python_run("print('x')"), bound_seconds=BOUND * 2)

    assert isinstance(run_detached(longer, give_up_at=0.0), NotStarted)


def test_the_same_command_and_bound_attach_to_the_run_on_record(make_spec):
    first = make_spec(python_run("print('x')"))
    run_detached(first, give_up_at=time.time() + GUARD_SECONDS)
    again = make_spec(python_run("print('x')"))

    assert isinstance(run_detached(again, give_up_at=time.time() + GUARD_SECONDS), Finished)


def test_a_missing_ps_never_makes_a_live_run_read_as_ended(make_spec, monkeypatch):
    spec = make_spec(LONG_RUNNING)
    run_detached(spec, give_up_at=0.0)
    wait_until(lambda: has_text(spec.pid_path), "the launcher's pid file")

    def no_ps(*_args, **_kwargs):
        raise FileNotFoundError("ps")

    monkeypatch.setattr(pocket_runs.subprocess, "run", no_ps)

    assert isinstance(read_run(spec), StillRunning)


def test_a_launcher_that_cannot_write_its_pid_runs_nothing(make_spec, tmp_path):
    clock = FakeClock(1000.0)
    marker = tmp_path / "ran"
    spec = make_spec(python_run(f"open({str(marker)!r}, 'w').write('x')"), bound_seconds=BOUND)
    spec.run_dir.mkdir(parents=True)
    spec.pid_path.with_name("1.pid.tmp").mkdir()  # the launcher cannot write its pid there

    run = run_detached(spec, give_up_at=1000.0 + BOUND + 1, now=clock, sleep=clock.sleep)

    assert isinstance(run, NotStarted)
    assert not marker.exists()


# --- The launcher stops its own run at the bound it was started with ---


def hangs_with_a_child(child_pid_file: Path) -> tuple[str, ...]:
    return ("sh", "-c", f"sleep 600 & echo $! > {child_pid_file}; wait")


def stop_was_recorded(spec: RunSpec) -> bool:
    return spec.cut_path.exists()


def test_a_run_that_outlives_its_bound_is_stopped_by_its_launcher_with_its_child(
    make_spec, tmp_path
):
    child_pid_file = tmp_path / "child.pid"
    spec = make_spec(hangs_with_a_child(child_pid_file), bound_seconds=SHORT_BOUND)
    run_detached(spec, give_up_at=0.0)
    wait_until(lambda: has_text(child_pid_file), "the child to record its pid")
    child = int(child_pid_file.read_text(encoding="utf-8"))
    leader = int(spec.pid_path.read_text(encoding="utf-8"))

    wait_until(lambda: has_exited(child), "the launcher to stop the child")

    wait_until(lambda: has_exited(leader), "the launcher to be gone")
    assert isinstance(read_run(spec), CutOff)


def test_a_run_that_exits_inside_its_bound_is_untouched_and_its_watchdog_ends_with_it(make_spec):
    spec = make_spec(python_run("print('done')"), bound_seconds=BOUND)

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    wait_until(lambda: not pocket_runs._group_is_alive(spec), "the run's group, watchdog included")
    assert not spec.cut_path.exists()


def test_the_bound_the_launcher_is_handed_is_the_one_the_run_was_started_with(make_spec):
    spec = make_spec(LONG_RUNNING, bound_seconds=2.4)

    command = pocket_runs._launcher_command(spec)

    assert command[-len(spec.argv) - 1] == "3"  # whole seconds, rounded up, just before the command


def test_a_bound_too_large_for_the_shells_arithmetic_is_capped_before_it_reaches_the_shell(
    make_spec,
):
    spec = make_spec(LONG_RUNNING, bound_seconds=1e19)

    command = pocket_runs._launcher_command(spec)

    assert command[-len(spec.argv) - 1] == str(pocket_runs._MAX_LAUNCHER_BOUND_SECONDS)


def test_a_command_run_through_the_launcher_keeps_the_default_interrupt_and_terminate_handling(
    make_spec,
):
    spec = make_spec(
        python_run(
            "import signal; print(signal.getsignal(signal.SIGINT) is signal.default_int_handler,"
            " signal.getsignal(signal.SIGTERM) == signal.SIG_DFL)"
        ),
        bound_seconds=BOUND,
    )

    run = run_detached(spec, give_up_at=time.time() + GUARD_SECONDS)

    assert isinstance(run, Finished)
    assert run.output.splitlines()[-1] == "True True"


# --- The stop itself: every shell, the second signal, the order, the leader ---


@pytest.fixture
def launched():
    """Start launcher processes by hand; at teardown whatever they lead or share is killed."""
    started: list[subprocess.Popen] = []

    def start(command, **popen_kwargs) -> subprocess.Popen:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **popen_kwargs,
        )  # fmt: skip
        started.append(process)
        return process

    yield start
    for process in started:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(process.pid, signal.SIGKILL)
    for process in started:
        process.wait(timeout=GUARD_SECONDS)


def shell_or_skip(shell: str) -> str:
    if os.path.isabs(shell) and not os.path.exists(shell):
        pytest.skip(f"{shell} is not installed on this host")
    return shell


def pid_in(path: Path) -> int:
    return int(path.read_text(encoding="utf-8"))


def command_that_records_its_pid(pid_file: Path, then: str) -> tuple[str, ...]:
    return ("sh", "-c", f"echo $$ > {pid_file}; {then}")


@pytest.mark.parametrize("shell", SHELLS)
def test_the_cut_marker_exists_before_the_launcher_signals_the_run_whatever_the_shell(
    make_spec, launched, tmp_path, shell
):
    command_pid = tmp_path / "command.pid"
    spec = make_spec(
        command_that_records_its_pid(command_pid, "exec sleep 600"), bound_seconds=SHORT_BOUND
    )
    spec.run_dir.mkdir(parents=True)
    os.mkfifo(spec.cut_path)  # writing the marker blocks until somebody reads it
    launcher = launched(
        pocket_runs._launcher_command(spec, shell_or_skip(shell)), start_new_session=True
    )
    wait_until(lambda: has_text(command_pid), "the run to record its pid")
    time.sleep(SHORT_BOUND + pocket_runs._GRACE_SECONDS + 2 * pocket_runs._WATCH_TICK_SECONDS)

    still_alive_with_the_marker_unwritten = process_exists(pid_in(command_pid))
    reader = os.open(spec.cut_path, os.O_RDONLY)  # lets the watchdog's write through
    os.close(reader)

    assert still_alive_with_the_marker_unwritten
    wait_until(lambda: has_exited(pid_in(command_pid)), "the stop to land on the run")
    wait_until(lambda: has_exited(launcher.pid), "the launcher to be gone")


@pytest.mark.parametrize("shell", SHELLS)
def test_a_cut_marker_that_cannot_be_written_means_no_signal_whatever_the_shell(
    make_spec, launched, tmp_path, shell
):
    command_pid = tmp_path / "command.pid"
    spec = make_spec(
        command_that_records_its_pid(command_pid, "exec sleep 600"), bound_seconds=SHORT_BOUND
    )
    spec.run_dir.mkdir(parents=True)
    spec.cut_path.mkdir()  # a directory where the marker goes: writing it fails
    launched(pocket_runs._launcher_command(spec, shell_or_skip(shell)), start_new_session=True)
    wait_until(lambda: has_text(command_pid), "the run to record its pid")
    time.sleep(SHORT_BOUND + pocket_runs._GRACE_SECONDS + 2 * pocket_runs._WATCH_TICK_SECONDS)

    assert process_exists(pid_in(command_pid))


def test_a_run_and_its_child_that_both_ignore_sigterm_are_still_gone_after_the_second_signal(
    make_spec, tmp_path
):
    command_pid, child_pid = tmp_path / "command.pid", tmp_path / "child.pid"
    script = (
        f"trap '' TERM; echo $$ > {command_pid}; sleep 600 & echo $! > {child_pid};"
        " while :; do sleep 1; done"
    )
    spec = make_spec(("sh", "-c", script), bound_seconds=SHORT_BOUND)
    run_detached(spec, give_up_at=0.0)
    wait_until(lambda: has_text(command_pid) and has_text(child_pid), "the run to record its pids")

    wait_until(lambda: has_exited(pid_in(child_pid)), "the child to be killed")
    wait_until(lambda: has_exited(pid_in(command_pid)), "the command to be killed")

    assert isinstance(read_run(spec), CutOff)


def test_a_launcher_that_does_not_lead_its_group_signals_no_sibling(make_spec, launched, tmp_path):
    command_pid = tmp_path / "command.pid"
    spec = make_spec(
        command_that_records_its_pid(command_pid, "exec sleep 600"), bound_seconds=SHORT_BOUND
    )
    spec.run_dir.mkdir(parents=True)
    sibling = launched(LONG_RUNNING, preexec_fn=os.setpgrp)  # leads a group that is not ours
    launched(
        pocket_runs._launcher_command(spec),
        preexec_fn=lambda: os.setpgid(0, sibling.pid),  # joins it without leading it
    )

    wait_until(lambda: stop_was_recorded(spec), "the watchdog to reach its deadline")
    time.sleep(pocket_runs._KILL_WAIT_SECONDS + 1)  # past the second signal too

    assert sibling.poll() is None
    assert process_exists(pid_in(command_pid))
