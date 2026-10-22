"""The Stop guard's work per Stop is bounded, and it costs nothing outside a loop.

A stale request, issued long before the session's other agents and never recorded, can
neither make every Stop read every transcript of the session nor run the guard into the
harness's timeout: the guard reads a bounded number of transcripts within a deadline of its
own and lets the stop through when a bound is reached. Outside a loop it imports nothing
beyond its own file and reads no transcript. A recent ended, unrecorded agent is still held
once with its record call, and a task named with exactly 64 characters is read while one of
65 is not.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from tests.acceptance.drivers import step_loop, stop_guard
from tests.acceptance.drivers.step_loop import Step, Work, agent_transcript_path, attempt
from tests.acceptance.drivers.stop_guard import (
    END_SHAPES,
    REPO_ROOT,
    fire_stop,
    issue,
    leave_ended_agent,
    loop,
)

OTHER_AGENTS = 2000
LONG_AGO_SECONDS = 30 * 24 * 3600
SLUG_64 = "loop-" + "x" * 59
SLUG_65 = SLUG_64 + "y"


def _other_agents_of_the_session(task, count: int) -> None:
    """Ended agents of this session that answer requests of no task in the checkout."""
    for n in range(count):
        request = {"agent_call": {"prompt": f"Task slug: elsewhere\nSpawn request: e{n}-a1\n"}}
        step_loop.leave_agent_transcript(
            task, request, f"b{n:015d}", requests=2, final_text="Done.\n[COMPLETE]", ended=True
        )


def _age_the_task(task) -> None:
    stamp = time.time() - LONG_AGO_SECONDS
    for path in task.task_dir.rglob("*"):
        os.utime(path, (stamp, stamp))


def _stale_request_in_a_busy_session(tmp_path):
    task = loop(tmp_path, Step("1"))
    issue(task)
    _age_the_task(task)
    _other_agents_of_the_session(task, OTHER_AGENTS)
    return task


def _transcripts_read(outcome) -> set[Path]:
    subagents = agent_transcript_path(outcome.task, "probe").parent
    return {p for p in outcome.transcripts_read() if p.parent == subagents.resolve()}


def test_a_stale_request_in_a_busy_session_reads_a_bounded_number_of_transcripts(tmp_path):
    task = _stale_request_in_a_busy_session(tmp_path)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    read = _transcripts_read(outcome)
    assert len(read) < OTHER_AGENTS, f"one Stop read {len(read)} of {OTHER_AGENTS} transcripts"


def test_a_stale_request_in_a_busy_session_lets_the_stop_through_well_inside_the_timeout(
    tmp_path,
):
    task = _stale_request_in_a_busy_session(tmp_path)
    timeout = stop_guard.guard_registration().timeout or 10

    started = time.monotonic()
    outcome = fire_stop(task)
    seconds = time.monotonic() - started

    assert outcome.let_through_silently, outcome.describe()
    assert seconds < timeout / 2, f"the guard took {seconds:.1f} s of its {timeout} s"


def test_a_recent_ended_agent_in_a_busy_session_is_still_held_with_its_record_call(tmp_path):
    task = loop(tmp_path, Step("1"))
    _other_agents_of_the_session(task, OTHER_AGENTS)
    request = issue(task)
    ended = leave_ended_agent(task, request, END_SHAPES[0])

    outcome = fire_stop(task)

    assert outcome.held, outcome.describe()
    assert stop_guard.record_command(task, request, ended) in outcome.message


# -- Outside a loop the guard imports nothing ------------------------------------------------


def _plugin_code_opened(outcome) -> list[Path]:
    guard = (REPO_ROOT / "hooks" / "guard_step_loop_stop.py").resolve()
    code = [REPO_ROOT / "hooks", REPO_ROOT / "scripts"]
    return [p for p in outcome.probe.opened_under(*code) if p != guard]


def test_with_no_step_loop_the_guard_imports_nothing_beyond_its_own_file(tmp_path):
    task = loop(tmp_path, Step("1"))
    stop_guard.remove_pipeline_directory(task)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    assert _plugin_code_opened(outcome) == []
    assert outcome.transcripts_read() == []


def test_with_every_request_recorded_the_guard_imports_nothing_beyond_its_own_file(tmp_path):
    task = loop(tmp_path, Step("1"))
    attempt(task, Work())

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    assert _plugin_code_opened(outcome) == []
    assert outcome.transcripts_read() == []


# -- The 64-character task name, from both sides ---------------------------------------------


def _ended_request_of_a_task_named(tmp_path, slug: str):
    first = loop(tmp_path, Step("1"))
    named = stop_guard.second_task(first, slug, Step("8"))
    request = issue(named)
    ended = leave_ended_agent(named, request, END_SHAPES[0])
    return first, named, request, ended


def test_a_task_named_with_exactly_64_characters_has_its_ended_request_held(tmp_path):
    first, named, request, ended = _ended_request_of_a_task_named(tmp_path, SLUG_64)

    outcome = fire_stop(first)

    assert outcome.held, outcome.describe()
    assert stop_guard.record_command(named, request, ended) in outcome.message


def test_a_directory_named_with_65_characters_is_not_read_as_a_task(tmp_path):
    first, named, _, _ = _ended_request_of_a_task_named(tmp_path, SLUG_64)
    named.task_dir.rename(named.task_dir.with_name(SLUG_65))

    outcome = fire_stop(first)

    assert outcome.let_through_silently, outcome.describe()
