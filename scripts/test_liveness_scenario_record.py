"""Tests for `liveness_scenario_record.py` -- the record the liveness jobs keep of their scenarios.

The failure modes this closes: a cut scenario that leaves no trace of how long it ran, and a
full disk that reads as a gate that stopped biting. The plugin half runs a real pytest inside
this one (pytester), the only way to know its hooks are the ones pytest calls, and stays
in-process so the mutation sensor can run the file; the reader half is pure text in, lines
out.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

# Flat import (siblings by bare name), the layout the mutation sensor reads.
MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

import liveness_scenario_record as record  # noqa: E402
from liveness_scenario_record import (  # noqa: E402
    End,
    Phase,
    Start,
    end_event,
    format_size,
    parse_line,
    report_lines,
    to_line,
)

GIB = 1024**3
PLENTY = 50 * GIB
SCENARIOS = """
import pytest


def test_passes():
    pass


def test_fails():
    assert False


def test_skips():
    pytest.skip("on purpose")


def test_runs_out_of_disk():
    raise OSError(28, "No space left on device")
"""
SCENARIO_NODES = (
    "test_scenarios.py::test_passes",
    "test_scenarios.py::test_fails",
    "test_scenarios.py::test_skips",
    "test_scenarios.py::test_runs_out_of_disk",
)


def _run_pytest(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    pytester.makepyfile(test_scenarios=SCENARIOS)
    return pytester.runpytest_inprocess("-p", "liveness_scenario_record", *args)


def _recorded(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _ends(path: Path, field: str) -> dict[str, object]:
    return {entry["node"]: entry[field] for entry in _recorded(path) if entry["event"] == "end"}


# --- The plugin, under a real pytest ---------------------------------------


@pytest.fixture
def recorded_run(pytester):
    path = pytester.path / "out" / "deeper" / "scenarios.jsonl"
    _run_pytest(pytester, f"--liveness-record={path}")
    return path


def test_each_scenario_leaves_one_start_line_then_one_end_line(recorded_run):
    by_node: dict[str, list[str]] = {}
    for entry in _recorded(recorded_run):
        by_node.setdefault(entry["node"], []).append(entry["event"])

    assert by_node == {node: ["start", "end"] for node in SCENARIO_NODES}


def test_every_recorded_line_reads_back_through_the_reader(recorded_run):
    lines = recorded_run.read_text(encoding="utf-8").splitlines()

    assert len([parse_line(line) for line in lines]) == 2 * len(SCENARIO_NODES)


def test_the_end_line_states_the_outcome_of_a_passing_failing_and_skipped_scenario(recorded_run):
    assert _ends(recorded_run, "outcome") == dict(
        zip(SCENARIO_NODES, ["passed", "failed", "skipped", "failed"], strict=True)
    )


def test_only_the_scenario_that_ran_out_of_disk_is_marked_no_space(recorded_run):
    assert _ends(recorded_run, "no_space") == dict(
        zip(SCENARIO_NODES, [False, False, False, True], strict=True)
    )


def test_a_scenarios_start_line_is_on_disk_before_the_scenario_ends(tmp_path):
    scenarios = record.ScenarioRecorder(tmp_path / "scenarios.jsonl")
    scenarios.pytest_sessionstart(session=None)

    scenarios.pytest_runtest_logstart("a::cut", ("a.py", 0, "cut"))

    assert [
        (entry["event"], entry["node"]) for entry in _recorded(tmp_path / "scenarios.jsonl")
    ] == [("start", "a::cut")]


def test_a_session_start_empties_what_an_earlier_job_left_in_the_record(tmp_path):
    path = tmp_path / "scenarios.jsonl"
    path.write_text("left over\n", encoding="utf-8")

    record.ScenarioRecorder(path).pytest_sessionstart(session=None)

    assert path.read_text(encoding="utf-8") == ""


def test_each_line_is_one_newline_terminated_write(tmp_path):
    path = tmp_path / "scenarios.jsonl"
    scenarios = record.ScenarioRecorder(path)
    scenarios.pytest_sessionstart(session=None)

    scenarios.pytest_runtest_logstart("a::cut", ("a.py", 0, "cut"))
    scenarios.pytest_runtest_logstart("a::next", ("a.py", 1, "next"))

    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_the_plugin_writes_nothing_without_its_option(pytester):
    before = {entry.name for entry in pytester.path.iterdir()}

    result = _run_pytest(pytester, "-p", "no:cacheprovider")

    assert (result.ret, {entry.name for entry in pytester.path.iterdir()} - before) == (
        1,
        {"test_scenarios.py", "__pycache__"},
    )


def test_collect_only_writes_nothing_even_with_the_option(pytester):
    path = pytester.path / "scenarios.jsonl"

    result = _run_pytest(pytester, f"--liveness-record={path}", "--collect-only")

    assert (result.ret, path.exists()) == (0, False)


def test_a_new_session_starts_the_record_afresh(pytester):
    path = pytester.path / "scenarios.jsonl"
    path.write_text("left over from an earlier job\n", encoding="utf-8")

    _run_pytest(pytester, f"--liveness-record={path}")

    assert "left over" not in path.read_text(encoding="utf-8")


# --- Folding a scenario's phases into its end line -------------------------


def test_the_end_line_sums_the_durations_of_the_phases():
    phases = [Phase("passed", 0.5, ""), Phase("passed", 2.0, ""), Phase("passed", 0.25, "")]

    assert end_event("n", phases, at=1.0, free=7).seconds == 2.75


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        (("passed", "passed", "passed"), "passed"),
        (("passed", "failed", "passed"), "failed"),
        (("skipped", "passed"), "skipped"),
        (("passed", "failed", "failed"), "failed"),
        (("skipped", "failed"), "failed"),
    ],
)
def test_a_failed_phase_outranks_a_skipped_one_which_outranks_a_passing_one(outcomes, expected):
    phases = [Phase(outcome, 0.0, "") for outcome in outcomes]

    assert end_event("n", phases, at=1.0, free=7).outcome == expected


@pytest.mark.parametrize("marker", ["No space left on device", "OSError: [Errno 28] whatever"])
def test_a_failure_naming_a_full_disk_is_marked_no_space(marker):
    phases = [Phase("passed", 0.0, ""), Phase("failed", 1.0, f"E   {marker}")]

    assert end_event("n", phases, at=1.0, free=7).no_space is True


def test_a_failure_for_any_other_reason_is_not_marked_no_space():
    phases = [Phase("failed", 1.0, "E   AssertionError: the gate did not bite")]

    assert end_event("n", phases, at=1.0, free=7).no_space is False


def test_a_full_disk_named_by_a_passing_phase_is_not_a_failure_for_lack_of_space():
    phases = [Phase("passed", 1.0, "")]

    assert end_event("n", phases, at=1.0, free=7).no_space is False


# --- The record's lines -----------------------------------------------------


def test_lines_round_trip_through_the_reader():
    events = [Start("a", 10.5, 1234), End("a", 12.0, "failed", 1.5, True, 1200)]

    assert [parse_line(to_line(event)) for event in events] == events


def test_whole_second_times_and_durations_are_read_as_numbers():
    line = (
        '{"v": 1, "event": "end", "node": "a", "at": 5, "outcome": "passed",'
        ' "seconds": 2, "no_space": false, "free": 9}'
    )

    assert parse_line(line) == End("a", 5, "passed", 2, False, 9)


def test_a_line_states_its_version_and_event():
    entry = json.loads(to_line(Start("a", 10.5, 1234)))

    assert (entry["v"], entry["event"]) == (1, "start")


@pytest.mark.parametrize(
    "line",
    [
        '{"v": 1, "event": "sta',
        "[1, 2]",
        '{"v": 2, "event": "start", "node": "a", "at": 1, "free": 1}',
        '{"v": 1, "event": "pause", "node": "a", "at": 1, "free": 1}',
        '{"v": 1, "event": "start", "node": "a", "at": 1}',
        '{"v": 1, "event": "start", "node": "a", "at": 1, "free": true}',
        '{"v": 1, "event": "end", "node": "a", "at": 1, "outcome": "exploded",'
        ' "seconds": 1, "no_space": false, "free": 1}',
        '{"v": 1, "event": "end", "node": "a", "at": 1, "outcome": "passed",'
        ' "seconds": 1, "no_space": "no", "free": 1}',
    ],
)
def test_a_line_that_is_not_a_well_formed_event_is_refused(line):
    with pytest.raises((ValueError, KeyError, TypeError)):
        parse_line(line)


# --- The report ----------------------------------------------------------------


def _text(*events) -> str:
    return "".join(to_line(event) + "\n" for event in events)


def test_the_report_states_the_duration_of_a_passing_failing_and_cut_scenario():
    text = _text(
        Start("a::passes", 100.0, PLENTY),
        End("a::passes", 112.0, "passed", 812.4, False, PLENTY),
        Start("a::fails", 113.0, PLENTY),
        End("a::fails", 116.0, "failed", 3.1, False, PLENTY),
        Start("a::cut", 120.0, PLENTY),
    )

    lines = report_lines(text, now=551.0, free_now=PLENTY)

    assert lines[:3] == [
        "a::passes: passed in 812.4 s",
        "a::fails: failed in 3.1 s",
        "a::cut: cut by the step's time limit after 431.0 s",
    ]


def test_a_scenario_that_failed_for_lack_of_space_says_the_disk_not_the_gate():
    text = _text(
        Start("a::fills", 100.0, PLENTY),
        End("a::fills", 103.0, "failed", 3.1, True, PLENTY),
    )

    assert report_lines(text, now=200.0, free_now=PLENTY)[0] == (
        "a::fills: failed in 3.1 s, for lack of disk space: the disk, not the gate"
    )


def test_scenarios_are_reported_in_the_order_they_started():
    text = _text(
        Start("a::first", 1.0, PLENTY),
        Start("a::second", 2.0, PLENTY),
        End("a::second", 3.0, "passed", 1.0, False, PLENTY),
        End("a::first", 4.0, "passed", 3.0, False, PLENTY),
    )

    assert report_lines(text, now=9.0, free_now=PLENTY)[:2] == [
        "a::first: passed in 3.0 s",
        "a::second: passed in 1.0 s",
    ]


def test_a_torn_last_line_is_reported_by_number_and_the_lines_before_it_are_read():
    text = _text(Start("a::runs", 1.0, PLENTY), End("a::runs", 2.0, "passed", 1.0, False, PLENTY))
    torn = text + '{"v": 1, "event": "start", "node": "a::cu'

    lines = report_lines(torn, now=9.0, free_now=PLENTY)

    assert lines[:2] == [
        "a::runs: passed in 1.0 s",
        "record line 3 is torn or malformed, not read: "
        + repr('{"v": 1, "event": "start", "node": "a::cu'),
    ]


def test_blank_lines_are_skipped_and_the_lines_after_them_are_read():
    ended = End("a::x", 2.0, "passed", 1.0, False, PLENTY)
    text = to_line(Start("a::x", 1.0, PLENTY)) + "\n\n" + to_line(ended)

    assert report_lines(text, now=9.0, free_now=PLENTY)[0] == "a::x: passed in 1.0 s"


def test_a_malformed_line_in_the_middle_is_reported_and_never_guessed():
    text = (
        to_line(Start("a::x", 1.0, PLENTY))
        + "\nnot json\n"
        + to_line(End("a::x", 2.0, "passed", 1.0, False, PLENTY))
    )

    lines = report_lines(text, now=9.0, free_now=PLENTY)

    assert lines[:2] == [
        "a::x: passed in 1.0 s",
        "record line 2 is torn or malformed, not read: 'not json'",
    ]


def test_the_report_gives_the_lowest_free_space_seen_and_the_free_space_now():
    text = _text(
        Start("a::x", 1.0, 30 * GIB),
        End("a::x", 2.0, "passed", 1.0, False, 12 * GIB),
    )

    assert report_lines(text, now=9.0, free_now=20 * GIB)[-2:] == [
        "lowest free disk space seen: 12.0 GiB",
        "free disk space now: 20.0 GiB",
    ]


def test_the_report_warns_when_the_lowest_free_space_fell_under_one_gibibyte():
    text = _text(Start("a::x", 1.0, GIB // 2), End("a::x", 2.0, "failed", 1.0, False, GIB // 2))

    lines = report_lines(text, now=9.0, free_now=20 * GIB)

    assert lines[-1].startswith("WARNING: free disk space fell under 1.0 GiB")


def test_the_report_does_not_warn_at_exactly_one_gibibyte():
    text = _text(Start("a::x", 1.0, GIB), End("a::x", 2.0, "passed", 1.0, False, GIB))

    assert not report_lines(text, now=9.0, free_now=GIB)[-1].startswith("WARNING")


def test_a_free_space_now_under_one_gibibyte_also_warns():
    assert report_lines("", now=9.0, free_now=GIB // 4)[-1].startswith("WARNING")


def test_an_empty_record_says_no_scenario_was_recorded_and_still_reports_the_disk():
    assert report_lines("", now=9.0, free_now=20 * GIB) == [
        "no scenario was recorded",
        "lowest free disk space seen: 20.0 GiB",
        "free disk space now: 20.0 GiB",
    ]


def test_a_cut_scenario_never_reads_as_running_for_a_negative_time():
    text = _text(Start("a::cut", 500.0, PLENTY))

    assert report_lines(text, now=100.0, free_now=PLENTY)[0] == (
        "a::cut: cut by the step's time limit after 0.0 s"
    )


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (512, "512.0 bytes"),
        (1024, "1.0 KiB"),
        (5 * 1024**2, "5.0 MiB"),
        (GIB, "1.0 GiB"),
        (int(12.34 * GIB), "12.3 GiB"),
        (3 * 1024**4, "3.0 TiB"),
        (5000 * 1024**4, "5000.0 TiB"),
    ],
)
def test_sizes_read_in_the_largest_unit_they_fill(size, expected):
    assert format_size(size) == expected


# --- The command line -----------------------------------------------------------


def test_disk_prints_the_free_space_before_the_scenarios_as_a_size(capsys):
    code = record.main(["disk"])

    assert code == 0
    assert re.fullmatch(
        r"free disk space before the scenarios: \d+\.\d (bytes|KiB|MiB|GiB|TiB)\n",
        capsys.readouterr().out,
    )


def test_report_prints_each_scenario_and_exits_zero(tmp_path, capsys):
    path = tmp_path / "scenarios.jsonl"
    path.write_text(_text(Start("a::cut", 1.0, PLENTY)), encoding="utf-8")

    code = record.main(["report", str(path)])

    assert (code, "a::cut: cut by the step's time limit after" in capsys.readouterr().out) == (
        0,
        True,
    )


def test_report_prints_one_line_per_finding_in_order(tmp_path, capsys, monkeypatch):
    path = tmp_path / "scenarios.jsonl"
    path.write_text(
        _text(Start("a::x", 1.0, PLENTY), End("a::x", 2.0, "passed", 1.0, False, PLENTY)),
        encoding="utf-8",
    )
    monkeypatch.setattr(record, "free_bytes", lambda: 20 * GIB)

    record.main(["report", str(path)])

    assert capsys.readouterr().out == (
        "a::x: passed in 1.0 s\n"
        "lowest free disk space seen: 20.0 GiB\n"
        "free disk space now: 20.0 GiB\n"
    )


def test_report_exits_zero_whatever_it_reads(tmp_path, capsys):
    path = tmp_path / "scenarios.jsonl"
    path.write_bytes(b"\x00\x01 not a record\n{")

    code = record.main(["report", str(path)])

    assert (code, "record line 1 is torn" in capsys.readouterr().out) == (0, True)


def test_report_on_a_missing_record_says_so_and_still_reports_the_disk(tmp_path, capsys):
    code = record.main(["report", str(tmp_path / "never-written.jsonl")])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("cannot read the record ")
    assert "free disk space now: " in out


@pytest.mark.parametrize("argv", [[], ["report"], ["disk", "extra"], ["watch"]])
def test_a_usage_error_exits_two(argv):
    with pytest.raises(SystemExit) as stopped:
        record.main(argv)

    assert stopped.value.code == 2


def test_the_module_is_not_executable_so_the_installer_leaves_it_off_the_path():
    assert (MODULE_DIR / "liveness_scenario_record.py").stat().st_mode & 0o111 == 0
