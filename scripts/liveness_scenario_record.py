"""Per-scenario record for the liveness jobs: a pytest plugin writes it, a command line reads it.

A scenario job that hits its time limit is killed from outside: GitHub signals the step's
entry process and then kills the tree, so nothing inside pytest gets to print a summary. The
record is therefore a file, written a line at a time while the scenarios run, and read by a
step with `if: always()` that outlives the cut.

    python3 scripts/liveness_scenario_record.py disk
    python -m pytest -p scripts.liveness_scenario_record --liveness-record=PATH ...
    python3 scripts/liveness_scenario_record.py report PATH

Every line is `{"v": 1, "event": ...}`, one of two events:

- `start`: `node`, `at` (epoch seconds), `free` (bytes free on the temp directory's filesystem);
- `end`: `node`, `at`, `outcome`, `seconds` (the phases' durations summed), `no_space`
  (a failed phase's text says the disk is full), `free`.

A scenario with a `start` and no `end` was cut. The report is a record, not a gate: it exits 0
whatever it reads, because the job's own step already carries the verdict. The same holds for
the writer: a record it cannot write is said once on stderr and never stops the scenarios.

Under pytest-xdist the controller alone records (a worker's reports reach it, interleaved by
scenario); a worker leaves the option alone, so no line is written twice.

Stdlib-only and 3.9-safe: the report steps run under the runner's own `python3`, which has
neither pytest nor this repository's environment. Not executable: it is a library and a
module-invoked tool, not something the installer should put on `PATH`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import pytest

SCHEMA_VERSION = 1
OUTCOMES = ("passed", "failed", "skipped")
# What a full disk looks like in a failure's text: the OS message, and its errno.
NO_SPACE_MARKERS = ("No space left on device", "Errno 28")
LOW_DISK_BYTES = 1024**3
OPTION_NAME = "--liveness-record"
_SIZE_UNITS = ("bytes", "KiB", "MiB", "GiB", "TiB")
_BYTES_PER_UNIT = 1024
_EXCERPT_CHARS = 80


# --- The record's lines ---------------------------------------------------


@dataclass(frozen=True)
class Phase:
    """One phase (setup, call or teardown) of a scenario, as pytest reported it."""

    outcome: str
    seconds: float
    text: str  # the failure's text; empty for a phase that did not fail


@dataclass(frozen=True)
class Start:
    EVENT: ClassVar[str] = "start"
    node: str
    at: float
    free: int


@dataclass(frozen=True)
class End:
    EVENT: ClassVar[str] = "end"
    node: str
    at: float
    outcome: str
    seconds: float
    no_space: bool
    free: int


@dataclass(frozen=True)
class Finished:
    node: str
    outcome: str
    seconds: float
    no_space: bool


@dataclass(frozen=True)
class Cut:
    node: str
    ran_for: float  # until the report was run: the scenario never ended


@dataclass(frozen=True)
class Unreadable:
    number: int
    text: str


def end_event(node: str, phases: Sequence[Phase], at: float, free: int) -> End:
    """Fold a scenario's phases into its end line."""
    failure_text = "\n".join(phase.text for phase in phases if phase.outcome == "failed")
    return End(
        node=node,
        at=at,
        outcome=_scenario_outcome(phases),
        seconds=sum(phase.seconds for phase in phases),
        no_space=any(marker in failure_text for marker in NO_SPACE_MARKERS),
        free=free,
    )


def _scenario_outcome(phases: Sequence[Phase]) -> str:
    outcomes = {phase.outcome for phase in phases}
    if "failed" in outcomes:
        return "failed"
    if "skipped" in outcomes:
        return "skipped"
    return "passed"


def to_line(event: Start | End) -> str:
    return json.dumps({"v": SCHEMA_VERSION, "event": event.EVENT, **asdict(event)})


def parse_line(text: str) -> Start | End:
    """Parse one record line once; ValueError, KeyError or TypeError says it is not one."""
    raw = json.loads(text)
    if raw["v"] != SCHEMA_VERSION:
        raise ValueError(f"unknown record version {raw['v']!r}")
    kind = raw["event"]
    if kind == Start.EVENT:
        return Start(
            node=_require(raw["node"], str),
            at=_require(raw["at"], int, float),
            free=_require(raw["free"], int),
        )
    if kind == End.EVENT:
        outcome = _require(raw["outcome"], str)
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        return End(
            node=_require(raw["node"], str),
            at=_require(raw["at"], int, float),
            outcome=outcome,
            seconds=_require(raw["seconds"], int, float),
            no_space=_require(raw["no_space"], bool),
            free=_require(raw["free"], int),
        )
    raise ValueError(f"unknown event {kind!r}")


def _require(value, *kinds: type):
    # bool is an int in Python; a JSON `true` is not a byte count.
    if not isinstance(value, kinds) or (isinstance(value, bool) and bool not in kinds):
        raise TypeError(f"{value!r} is not {'/'.join(kind.__name__ for kind in kinds)}")
    return value


# --- The writer: the pytest plugin ----------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        OPTION_NAME,
        dest="liveness_record",
        metavar="PATH",
        default=None,
        help="append a start and an end line per scenario to PATH (JSON lines)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Record only when asked to, and never while merely collecting."""
    path = config.getoption("liveness_record")
    if path is None or config.getoption("collectonly") or hasattr(config, "workerinput"):
        return
    config.pluginmanager.register(ScenarioRecorder(Path(path)), "liveness-scenario-recorder")


class ScenarioRecorder:
    """Writes each line as the scenario reaches it, so a kill loses at most the running one."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._phases: dict[str, list[Phase]] = {}  # by node: xdist interleaves scenarios
        self._said_unwritable = False

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self._write("", "w")

    def pytest_runtest_logstart(self, nodeid: str, location: object) -> None:
        self._append(Start(node=nodeid, at=time.time(), free=free_bytes()))

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        text = str(report.longrepr) if report.failed else ""
        phase = Phase(report.outcome, report.duration, text)
        self._phases.setdefault(report.nodeid, []).append(phase)
        if report.when == "teardown":
            phases = self._phases.pop(report.nodeid)
            self._append(end_event(report.nodeid, phases, time.time(), free_bytes()))

    def _append(self, event: Start | End) -> None:
        self._write(to_line(event) + "\n", "a")

    def _write(self, text: str, mode: str) -> None:
        # The record is an observer: when the disk is the very thing that is wrong, losing
        # the record is better than ending the run it watches.
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Open and close per line: the close is the flush, and a line is one write.
            with self._path.open(mode, encoding="utf-8") as record:
                record.write(text)
        except OSError as error:
            if not self._said_unwritable:
                self._said_unwritable = True
                print(f"liveness record: cannot write {self._path}: {error}", file=sys.stderr)


def free_bytes() -> int:
    return shutil.disk_usage(tempfile.gettempdir()).free


# --- The reader: the report -----------------------------------------------


def report_lines(text: str, now: float, free_now: int) -> list[str]:
    """What the job's log says about a record: durations, torn lines, free disk."""
    events, unreadable = read_events(text)
    lines = [describe(scenario) for scenario in fold(events, now)]
    lines = lines or ["no scenario was recorded"]
    lines += [
        f"record line {line.number} is torn or malformed, not read: {line.text[:_EXCERPT_CHARS]!r}"
        for line in unreadable
    ]
    lowest = min([free_now, *(event.free for event in events)])
    lines.append(f"lowest free disk space seen: {format_size(lowest)}")
    lines.append(f"free disk space now: {format_size(free_now)}")
    if lowest < LOW_DISK_BYTES:
        lines.append(
            f"WARNING: free disk space fell under {format_size(LOW_DISK_BYTES)}; "
            "a scenario that failed in this run may have failed for the disk, not the gate"
        )
    return lines


def read_events(text: str) -> tuple[list[Start | End], list[Unreadable]]:
    events: list[Start | End] = []
    unreadable: list[Unreadable] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(parse_line(line))
        except (ValueError, KeyError, TypeError):
            unreadable.append(Unreadable(number, line))
    return events, unreadable


def fold(events: Sequence[Start | End], now: float) -> list[Finished | Cut]:
    """One entry per scenario, in the order it started; a start with no end is cut."""
    latest: dict[str, Start | Finished] = {}
    for event in events:
        if isinstance(event, Start):
            latest[event.node] = event
        else:
            latest[event.node] = Finished(event.node, event.outcome, event.seconds, event.no_space)
    return [
        Cut(entry.node, max(0.0, now - entry.at)) if isinstance(entry, Start) else entry
        for entry in latest.values()
    ]


def describe(scenario: Finished | Cut) -> str:
    if isinstance(scenario, Cut):
        return f"{scenario.node}: cut by the step's time limit after {scenario.ran_for:.1f} s"
    line = f"{scenario.node}: {scenario.outcome} in {scenario.seconds:.1f} s"
    if scenario.no_space:
        line += ", for lack of disk space: the disk, not the gate"
    return line


def format_size(size: int) -> str:
    value = float(size)
    unit = 0
    while value >= _BYTES_PER_UNIT and unit < len(_SIZE_UNITS) - 1:
        value /= _BYTES_PER_UNIT
        unit += 1
    return f"{value:.1f} {_SIZE_UNITS[unit]}"


# --- The command line -----------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "disk":
        print(f"free disk space before the scenarios: {format_size(free_bytes())}")
        return 0
    try:
        # Bytes that are not UTF-8 become a malformed line, reported by number.
        text = args.path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        print(f"cannot read the record {args.path}: {error}")
        text = ""
    print("\n".join(report_lines(text, time.time(), free_bytes())))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report what the liveness scenarios did.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("disk", help="print the free disk space before the scenarios")
    report = commands.add_parser("report", help="print each scenario's duration and the disk")
    report.add_argument("path", type=Path, help="the record the plugin wrote")
    return parser


if __name__ == "__main__":
    sys.exit(main())
