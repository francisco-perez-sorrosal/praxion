"""The pocket-run module of the step-loop gate: how long a pocket's tests may run, and what one
run of them left behind.

This part is pure. A pocket (a directory with a runner configuration of its own, as the resolver
finds them) is allowed a **bound**, `PocketBound`, read from the first of three sources that
yields a usable value:

1. the environment variable `PRAXION_STEP_LOOP_POCKET_TIMEOUTS`, `<pocket root>=<seconds>`
   entries joined by commas (the last entry for a pocket wins), the root pocket being `.`;
2. the pocket's own `pyproject.toml`, `[tool.praxion.step-loop] gate-timeout-seconds`;
3. the driver default, 540 seconds.

A source that is present but unusable (an entry with no `=`, a value that is not a positive
finite number, a file that is not TOML) is skipped with a warning and the next source applies, so
a typo can never remove a bound: a pocket always has one, and `PocketBound` cannot be built
without a positive finite one. The warnings travel in the `BoundReading`; printing them is the
caller's.

A run of a pocket's tests leaves one `PocketRun`: `Finished` (it exited by itself), `CutOff` (it
outlived its bound; the failures its log showed before the cut are kept) or `NotStarted` (it never
ran). Which of the three a run is does not depend on who looked when: the shell reads the run's
recorded start and finish against its bound.

The shell, `run_detached`, starts one invocation in a session of its own and returns to it on
every later call, so a `record` call cut off at its ceiling loses nothing. A run lives in five
files under its request's directory (`<n>` is the invocation's number):

* `<n>.log` -- the command on its first line, then both output streams;
* `<n>.start` -- the start time, the command and the bound, written once, before the process
  starts: its existence is what makes a later call attach instead of start, and a call that asks
  for another command or bound never adopts the run on record;
* `<n>.pid` -- the launcher's process id, which leads the run's process group, written by the
  launcher itself as its first act, so a live run is never without a reference;
* `<n>.exit` -- `<return code> <finish time>`, written by the launcher when the command exits;
* `<n>.cut` -- empty, written when the run was stopped for outliving its bound, so a later look
  reads the same verdict.

The launcher stops its own run. It is given the bound as an argument when it starts and computes
its deadline once from it (the bound and five seconds of grace), so nothing later re-reads the
environment or the pocket's file. A watchdog it starts watches that deadline; with no exit file at
the deadline it writes the cut file first, then sends SIGTERM to the group (the watchdog ignores the
signal itself), and after two seconds SIGKILL to what survives: the whole stop lands inside 30
seconds of the bound, with no call of ours to make it. It needs only what macOS and Linux ship
(`date`, `sleep`, `mv`, `printf`). The command itself runs in the launcher's foreground, with the
signal dispositions it would have anywhere else.

The attach-time check is the second line of defence, for a launcher the operating system killed:
a run with no exit file past its bound is killed with its whole group, once the pid on record is
confirmed to be a live launcher of this run (its command line holds the run's log path); a run
whose launcher is gone and left no cut file is read as not started. A launcher that cannot record
its pid exits before the command runs. A run that exited later than its start plus its bound is cut
off too, though nothing stopped it: the verdict follows the recorded times, not the moment somebody
looked.

Stdlib-only and 3.9-safe at runtime. `tomllib` is guarded: on an interpreter without it a
declaration cannot be read, which is a skipped source like any other.
"""

from __future__ import annotations

import contextlib
import math
import os
import posixpath
import re
import shlex
import signal
import subprocess
import time
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    tomllib = None  # type: ignore[assignment]

POCKET_TIMEOUTS_VARIABLE = "PRAXION_STEP_LOOP_POCKET_TIMEOUTS"
DECLARATION_KEY = "gate-timeout-seconds"
DEFAULT_BOUND_SECONDS = 540.0
_PYPROJECT = "pyproject.toml"
_ROOT_POCKET = "."

BoundSource = Literal["override", "declared", "default"]
_BOUND_SOURCES = ("override", "declared", "default")


# --- A pocket's bound ---


@dataclass(frozen=True)
class PocketBound:
    """The seconds a pocket's run is allowed, and which source said so."""

    pocket: str
    seconds: float
    source: BoundSource

    def __post_init__(self) -> None:
        if not _is_positive_finite(self.seconds):
            raise ValueError(f"a bound is a positive finite number of seconds, not {self.seconds}")
        if self.source not in _BOUND_SOURCES:
            raise ValueError(f"a bound's source is one of {_BOUND_SOURCES}, not {self.source!r}")


@dataclass(frozen=True)
class BoundReading:
    """A pocket's bound and the sources that were skipped to reach it."""

    bound: PocketBound
    warnings: tuple[str, ...]


def pocket_bound(repo: Path, pocket: str, environ: Mapping[str, str]) -> BoundReading:
    """Read the bound of `pocket` for the checkout at `repo`: the environment, then the
    pocket's own `pyproject.toml`, then the default. The one place this module reads a file."""
    declaration, read_warnings = _read_declaration(repo / pocket / _PYPROJECT)
    reading = resolve_bound(pocket, environ.get(POCKET_TIMEOUTS_VARIABLE, ""), declaration)
    return BoundReading(reading.bound, read_warnings + reading.warnings)


def resolve_bound(pocket: str, override_text: str, declaration_text: str | None) -> BoundReading:
    """The bound of `pocket` from the override's text and the text of its `pyproject.toml`
    (None when it has none). The declaration is read only when no override applies."""
    pocket = _normalise_pocket(pocket)
    seconds, skipped = _override_seconds(pocket, override_text)
    if seconds is not None:
        return BoundReading(PocketBound(pocket, seconds, "override"), skipped)
    if declaration_text is not None:
        seconds, declaration_skipped = _declared_seconds(declaration_text)
        skipped += declaration_skipped
        if seconds is not None:
            return BoundReading(PocketBound(pocket, seconds, "declared"), skipped)
    return BoundReading(PocketBound(pocket, DEFAULT_BOUND_SECONDS, "default"), skipped)


def _override_seconds(pocket: str, text: str) -> tuple[float | None, tuple[str, ...]]:
    """The last usable entry naming `pocket`. An entry whose shape is unreadable could name any
    pocket and warns for all; one that names another pocket is that pocket's business."""
    seconds: float | None = None
    skipped: list[str] = []
    for entry in (part.strip() for part in text.split(",")):
        if not entry:
            continue
        name, separator, value = entry.partition("=")
        if not separator or not name.strip():
            skipped.append(_skipped(entry, "expected <pocket root>=<seconds>"))
        elif _normalise_pocket(name) == pocket:
            parsed = _seconds_from_text(value)
            if parsed is None:
                skipped.append(_skipped(entry, "seconds must be a positive finite number"))
            else:
                seconds = parsed
    return seconds, tuple(skipped)


def _skipped(entry: str, why: str) -> str:
    return f"{POCKET_TIMEOUTS_VARIABLE} entry {entry!r} skipped: {why}"


def _declared_seconds(text: str) -> tuple[float | None, tuple[str, ...]]:
    if tomllib is None:
        return None, (f"{_PYPROJECT} not read: this interpreter has no tomllib",)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return None, (f"{_PYPROJECT} skipped: not TOML ({exc})",)
    table = data
    for key in ("tool", "praxion", "step-loop"):
        table = table.get(key, {}) if isinstance(table, dict) else {}
    if not isinstance(table, dict) or DECLARATION_KEY not in table:
        return None, ()
    value = table[DECLARATION_KEY]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if _is_positive_finite(value):
            return float(value), ()
    return None, (f"{DECLARATION_KEY} skipped: {value!r} is not a positive finite number",)


def _read_declaration(path: Path) -> tuple[str | None, tuple[str, ...]]:
    try:
        return path.read_text(encoding="utf-8"), ()
    except FileNotFoundError:
        return None, ()
    except (OSError, UnicodeDecodeError) as exc:
        return None, (f"{path} skipped: cannot be read ({exc})",)


def _seconds_from_text(text: str) -> float | None:
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if _is_positive_finite(value) else None


def _is_positive_finite(value: float) -> bool:
    return math.isfinite(value) and value > 0


def _normalise_pocket(raw: str) -> str:
    """`eval/` and `./eval` name the pocket `eval`; the root pocket is `.`."""
    stripped = raw.strip()
    return posixpath.normpath(stripped) if stripped else _ROOT_POCKET


# --- What one run left behind ---


@dataclass(frozen=True)
class Finished:
    """The run exited by itself, within its bound. `output` is its whole log."""

    pocket: str
    argv: tuple[str, ...]
    returncode: int
    output: str
    log_path: Path


@dataclass(frozen=True)
class CutOff:
    """The run outlived its bound. `failed_seen` holds the failures its log showed, each once, in
    log order; `output` is what it had printed."""

    bound: PocketBound
    argv: tuple[str, ...]
    failed_seen: tuple[str, ...]
    output: str
    log_path: Path

    @property
    def pocket(self) -> str:
        return self.bound.pocket


@dataclass(frozen=True)
class NotStarted:
    """The run never ran, or ended without leaving a record of how."""

    pocket: str
    reason: str
    output: str = ""  # what its log held, when it ended without an exit record


PocketRun = Union[Finished, CutOff, NotStarted]  # noqa: UP007 -- runtime value, 3.9 floor


# --- One run: start it detached, or attach to it ---

POLL_SECONDS = 0.1
_GRACE_SECONDS = 5  # past its bound, a run that is exiting still gets to say so
_KILL_WAIT_SECONDS = 2  # between SIGTERM and SIGKILL for the run's group
# $1 the log, $2 the exit file, $3 the pid file, $4 the cut file, $5 the bound in whole seconds,
# then the command. The shell leads the run's process group (the run starts in a session of its
# own) and records its own pid before anything else, so no live run is ever without a reference;
# the pid and exit files appear whole or not at all. The command runs in the launcher's
# foreground, so it keeps the default signal dispositions: a background job of a non-interactive
# shell starts with SIGINT ignored, and every test run under it would inherit that. The deadline
# is computed once, from the bound this call was given, and watched by a background subshell that
# stops when the exit file appears. Past the deadline (plus the grace that lets a run exiting at its
# bound say so) the watchdog writes the cut file first, then sends SIGTERM to the group -- it
# ignores the signal itself, which only a subshell can do without the command inheriting the
# ignore -- and SIGKILL to what survives. The signals name the group by the launcher's pid, so a
# launcher that does not lead its group (not started in a session of its own) signals nothing;
# the watchdog is in the group and goes with it.
_LAUNCHER = rf"""
log=$1; done=$2; pidfile=$3; cutfile=$4; bound=$5; shift 5
leader=$$
printf '%s\n' "$leader" > "$pidfile.tmp" && mv "$pidfile.tmp" "$pidfile" || exit 70
deadline=$(( $(date +%s) + bound + {_GRACE_SECONDS} ))
(
    trap '' TERM
    while [ ! -e "$done" ]; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
            : > "$cutfile"
            kill -TERM -- "-$leader"
            sleep {_KILL_WAIT_SECONDS}
            kill -KILL -- "-$leader"
        fi
        sleep 0.1 || sleep 1
    done
) &
"$@" >> "$log" 2>&1
code=$?
printf '%s %s\n' "$code" "$(date +%s)" > "$done.tmp" && mv "$done.tmp" "$done"
"""
_PS_TIMEOUT_SECONDS = 10.0
_PID_RECORD_WAIT_SECONDS = 2.0
_PID_RECORD_POLL_SECONDS = 0.01
_PINNED_LINES = 3  # start time, command, bound
_FIRST_SIGNALLABLE_PID = 2  # pid 1 and group 0 (our own) are never signalled
_NO_COLOUR_ENV = {"NO_COLOR": "1", "PY_COLORS": "0"}
_FORCED_COLOUR_VARS = ("FORCE_COLOR", "CLICOLOR_FORCE")
_PYTEST_WORD = "pytest"
# Pytest applies a pocket's ini `addopts` first, so a later `--verbosity=1` sets verbosity to
# exactly one whatever `-q`, `-qq` or `-v` the pocket declares: the per-test outcome lines a
# cut-off reader parses are always printed, and a run cut off part-way still shows its failures.
# `-rfE` is pytest's own default summary: a bare `-rf` would replace an `-ra` in a pocket's
# configuration and drop the lines that name errors.
_OUTCOME_REPORTS = ("--verbosity=1", "-rfE")


@dataclass(frozen=True)
class RunSpec:
    """One invocation of a request's derived scope: where its record lives, what it runs and the
    bound its pocket allows. `run_dir` is the request's own directory; `number` tells the
    request's invocations apart."""

    run_dir: Path
    number: int
    argv: tuple[str, ...]
    cwd: Path
    bound: PocketBound

    @property
    def pocket(self) -> str:
        return self.bound.pocket

    @property
    def log_path(self) -> Path:
        return self._file("log")

    @property
    def start_path(self) -> Path:
        return self._file("start")

    @property
    def pid_path(self) -> Path:
        return self._file("pid")

    @property
    def exit_path(self) -> Path:
        return self._file("exit")

    @property
    def cut_path(self) -> Path:
        return self._file("cut")

    def _file(self, suffix: str) -> Path:
        return self.run_dir / f"{self.number}.{suffix}"


@dataclass(frozen=True)
class StillRunning:
    """The run is alive and inside its bound; the caller stopped waiting before it ended."""

    pocket: str
    elapsed: float
    bound: PocketBound


Observed = Union[Finished, CutOff, NotStarted, StillRunning]  # noqa: UP007 -- runtime value, 3.9 floor


def run_detached(
    spec: RunSpec,
    give_up_at: float,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> Observed:
    """Start the run unless its start record exists, then wait for it until `give_up_at` (a time
    on `now`'s clock). A run that outlives its bound meanwhile is killed and read as cut off; one
    still inside its bound when the caller gives up comes back as `StillRunning`, and calling
    again attaches to it."""
    refused = _start_once(spec, now)
    if refused is not None:
        return refused
    while True:
        looked = read_run(spec, now)
        if not isinstance(looked, StillRunning) or now() >= give_up_at:
            return looked
        sleep(POLL_SECONDS)


def read_run(spec: RunSpec, now: Callable[[], float] = time.time) -> Observed:
    """One look at a run, which never waits: read its record against its bound, and kill its
    group when it is past it with no exit record."""
    started = _read_start(spec)
    if isinstance(started, NotStarted):
        return started
    elapsed = now() - started
    finish = _read_exit(spec)
    if finish is None and elapsed < spec.bound.seconds:
        if _group_is_alive(spec):
            return StillRunning(spec.pocket, elapsed, spec.bound)
        finish = _read_exit(spec)  # it may have exited between the two looks
        if finish is None:
            return _ended_without_record(spec)
    if isinstance(finish, NotStarted):
        return finish
    if finish is None:
        if _launcher_is_ours(spec):
            _kill_group(spec)
            spec.cut_path.touch()  # the cut stays the verdict once the launcher is gone
        elif not spec.cut_path.exists():  # a stale or planted pid record is never signalled
            return _ended_without_record(spec)
        return _cut_off(spec)
    returncode, finished_at = finish
    if finished_at - started > spec.bound.seconds:
        return _cut_off(spec)
    output = _read_log(spec)
    if output is None:
        return NotStarted(spec.pocket, f"the log {spec.log_path} cannot be read")
    return Finished(spec.pocket, spec.argv, returncode, output, spec.log_path)


def _start_once(spec: RunSpec, now: Callable[[], float]) -> NotStarted | None:
    """Record the start and launch, unless a start was recorded already (then: attach)."""
    try:
        spec.run_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(spec.start_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return _refuse_another_run(spec)
    except OSError as exc:
        return NotStarted(spec.pocket, f"could not start: {exc}")
    with os.fdopen(descriptor, "w", encoding="utf-8") as stamp:
        stamp.write(f"{now()!r}\n{shlex.join(spec.argv)}\n{_bound_text(spec)}\n")
    try:
        spec.log_path.write_text(f"$ {shlex.join(spec.argv)}\n", encoding="utf-8")
        _launch(spec)
    except OSError as exc:
        spec.start_path.unlink(missing_ok=True)  # nothing runs: a later call may try again
        return NotStarted(spec.pocket, f"could not start: {exc}")
    return None


def _bound_text(spec: RunSpec) -> str:
    return repr(float(spec.bound.seconds))


def _refuse_another_run(spec: RunSpec) -> NotStarted | None:
    """On attach, the run on record must be the one this call asks for: the command and the
    bound are pinned in its start record. A run started for another is never adopted -- it is
    stopped, and this request's run reads as not started. A record not yet whole (the starting
    call is still writing it) is adopted."""
    try:
        lines = spec.start_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < _PINNED_LINES or lines[1:3] == [shlex.join(spec.argv), _bound_text(spec)]:
        return None
    _kill_group(spec)
    return NotStarted(spec.pocket, "the run on record was started for another command or bound")


def _launch(spec: RunSpec) -> None:
    """Start the launcher in a session of its own; its pid, which it records, leads the group."""
    files = (str(spec.log_path), str(spec.exit_path), str(spec.pid_path), str(spec.cut_path))
    bound = str(math.ceil(spec.bound.seconds))
    command = ["sh", "-c", _LAUNCHER, "sh", *files, bound, *spec.argv]
    process = subprocess.Popen(
        command, cwd=spec.cwd, env=no_colour_environment(os.environ),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )  # fmt: skip
    with warnings.catch_warnings():
        # Detached on purpose: the run outlives this call and is found again through its files.
        warnings.simplefilter("ignore", ResourceWarning)
        del process


def no_colour_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` for a child whose output is read by a program: no colour asked for, none forced."""
    kept = {name: value for name, value in environ.items() if name not in _FORCED_COLOUR_VARS}
    return {**kept, **_NO_COLOUR_ENV}


def with_outcome_reports(argv: tuple[str, ...]) -> tuple[str, ...]:
    """`argv` with the flags that make a pytest run report each outcome; another runner's
    invocation comes back as it is. The flags follow the first `pytest` word, the runner's own."""
    if _PYTEST_WORD not in argv:
        return argv
    at = argv.index(_PYTEST_WORD) + 1
    return (*argv[:at], *_OUTCOME_REPORTS, *argv[at:])


def _read_start(spec: RunSpec) -> float | NotStarted:
    try:
        return float(spec.start_path.read_text(encoding="utf-8").splitlines()[0])
    except FileNotFoundError:
        return NotStarted(spec.pocket, "no run was started")
    except (OSError, ValueError, IndexError):
        return NotStarted(spec.pocket, f"the start record {spec.start_path} cannot be read")


def _read_exit(spec: RunSpec) -> tuple[int, float] | NotStarted | None:
    """The code and the finish time of an exited run; None while no exit record exists."""
    try:
        code, finished_at = spec.exit_path.read_text(encoding="utf-8").split()
        return int(code), float(finished_at)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return NotStarted(spec.pocket, f"the exit record {spec.exit_path} cannot be read")


def _read_log(spec: RunSpec) -> str | None:
    try:
        return spec.log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _ended_without_record(spec: RunSpec) -> NotStarted:
    return NotStarted(spec.pocket, "the run ended without an exit record", _read_log(spec) or "")


def _cut_off(spec: RunSpec) -> CutOff:
    output = _read_log(spec) or ""  # a cut-off run is red whether or not its log can be read
    return CutOff(spec.bound, spec.argv, failed_node_ids(output), output, spec.log_path)


# --- The run's process group ---


def _leader_pid(spec: RunSpec) -> int | None:
    """The launcher's pid when its record names a process that can be ours to signal."""
    try:
        pid = int(spec.pid_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return pid if pid >= _FIRST_SIGNALLABLE_PID else None


def _await_pid_record(spec: RunSpec) -> int | None:
    """The recorded pid, waiting a moment for a launcher that has only just started to write it."""
    give_up = time.monotonic() + _PID_RECORD_WAIT_SECONDS
    while not spec.pid_path.exists() and time.monotonic() < give_up:
        time.sleep(_PID_RECORD_POLL_SECONDS)
    return _leader_pid(spec)


def _launcher_is_ours(spec: RunSpec) -> bool:
    """Whether the recorded pid is a live launcher of this very run: its command line holds the
    run's log path, which no other process has. The pid file is only a claim; it may be stale
    (the pid reused after a reboot) or written by someone else."""
    pid = _await_pid_record(spec)
    if pid is None:
        return False
    _reap(pid)
    try:
        done = subprocess.run(
            ["ps", "-ww", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=_PS_TIMEOUT_SECONDS, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return False
    return str(spec.log_path) in done.stdout


def _group_is_alive(spec: RunSpec) -> bool:
    """Whether the run's group still has a member. A launcher not recorded yet is starting. The
    `ps` check of `_launcher_is_ours` only authorises a kill: a missing or slow `ps` must never
    make a live run read as ended."""
    pid = _leader_pid(spec)
    if pid is None:
        return True
    _reap(pid)
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # a group exists that is not ours: not the run that ended
        return True
    return True


def _kill_group(spec: RunSpec) -> None:
    pid = _leader_pid(spec)
    if pid is None or not _launcher_is_ours(spec):
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
    _reap(pid, wait=True)  # SIGKILL cannot be ignored: the wait is short


def _reap(pid: int, wait: bool = False) -> None:
    """Collect the launcher if it is our child, so a dead one does not read as alive; a launcher
    started by an earlier process is not our child and needs nothing."""
    with contextlib.suppress(ChildProcessError):
        os.waitpid(pid, 0 if wait else os.WNOHANG)


# --- The failures a log shows ---
#
# `pytest -v` streams one outcome per test as it finishes, so a run killed part-way still
# shows the failures before the cut. The short summary that names them again comes last and is the
# gate's to read: a killed run never prints it.

_STREAMED_OUTCOME = r"(?:FAILED|ERROR)"
_PLAIN_OUTCOME_RE = re.compile(
    rf"^(?P<id>\S+::\S.*?) {_STREAMED_OUTCOME}(?:\s+\[\s*\d+%\])?\s*$"
)  # path::test FAILED   [ 50%]
_XDIST_OUTCOME_RE = re.compile(
    rf"^\[gw\d+\] \[\s*\d+%\] {_STREAMED_OUTCOME} (?P<id>\S.*?)\s*$"
)  # [gw1] [ 50%] FAILED path::test


def failed_node_ids(log: str) -> tuple[str, ...]:
    """The node ids a `-v` log shows as failed or errored, each once, in log order."""
    matches = (
        _PLAIN_OUTCOME_RE.match(line) or _XDIST_OUTCOME_RE.match(line) for line in log.splitlines()
    )
    return tuple(dict.fromkeys(match["id"] for match in matches if match))


_ANY_OUTCOME = r"(?:PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)"
_SEEN_FILE_RES = (
    re.compile(rf"^(?P<file>[^\s:]+)::\S.* {_ANY_OUTCOME}\b"),  # path::test PASSED   [ 50%]
    re.compile(
        rf"^\[gw\d+\] \[\s*\d+%\] {_ANY_OUTCOME} (?P<file>[^\s:]+)::"
    ),  # [gw1] PASSED path::test
)


def files_with_outcomes(log: str) -> int:
    """How many distinct test files a `-v` log shows an outcome for."""
    matches = (regex.match(line) for line in log.splitlines() for regex in _SEEN_FILE_RES)
    return len({match["file"] for match in matches if match})
