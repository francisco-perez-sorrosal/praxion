"""Every command the driver prints carries the location options its caller gave.

A caller that gives `--base-ref` (alone, or with `--repo-root` or `--worktree-root`) gets a
`then`, a stop's `resume`, a handoff next-action line and a status table whose printed
commands end with those options exactly as given, so running a printed command verbatim
keeps the caller's base. A bare call prints exactly what it printed before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.loop_repairs import (
    as_pairs,
    call,
    location,
    printed_commands,
    status_table,
    trailing_location,
)
from tests.acceptance.drivers.step_loop import (
    SLUG,
    Step,
    Work,
    attempt,
    build_loop,
    handoff_section,
    next_action,
    record_not_started,
)

# The bare forms the base commit prints (read from its `next` output over a one-step plan).
BARE_THEN = (
    f"python3 scripts/step_loop.py record {SLUG} --request s1-a1-implement "
    "--agent-id <agentId> --marker <complete|blocked|conflict|partial|none>"
)
BARE_RESUME = f"python3 scripts/step_loop.py next {SLUG}"

OPTION_SETS = {
    "base-ref-alone": ("base-ref",),
    "base-ref-and-repo-root": ("repo-root", "base-ref"),
    "all-three": ("repo-root", "worktree-root", "base-ref"),
}


def _exhausted(tmp_path):
    """A one-step plan whose every attempt failed its check: next now stops."""
    task = build_loop(tmp_path, Step("1"))
    cap = next_action(task).request["attempt_cap"]
    for _ in range(cap):
        attempt(task, Work(passes=False))
    return task


@pytest.mark.parametrize("names", list(OPTION_SETS.values()), ids=list(OPTION_SETS))
def test_then_ends_with_the_location_options_the_caller_gave(tmp_path, names):
    task = build_loop(tmp_path, Step("1"))
    given = location(task, *names)

    asked = call(task, "next", options=given)

    assert trailing_location(asked.doc["then"]) == as_pairs(given), asked.doc["then"]


@pytest.mark.parametrize("names", list(OPTION_SETS.values()), ids=list(OPTION_SETS))
def test_a_stops_resume_ends_with_the_location_options_the_caller_gave(tmp_path, names):
    task = _exhausted(tmp_path)
    given = location(task, *names)

    stopped = call(task, "next", options=given)

    assert stopped.stop is not None, stopped.doc
    assert trailing_location(stopped.stop["resume"]) == as_pairs(given), stopped.stop["resume"]


def test_the_handoffs_next_action_command_carries_the_callers_base(tmp_path):
    task = _exhausted(tmp_path)
    given = location(task, "base-ref")

    stopped = call(task, "next", options=given)

    section = handoff_section(
        Path(stopped.stop["handoff"]).read_text(encoding="utf-8"), "§2 Next action"
    )
    commands = printed_commands(section)
    assert commands, section
    assert [trailing_location(c) for c in commands] == [as_pairs(given)] * len(commands), commands


def _withdrawn(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    record_not_started(task, next_action(task).request["id"], "the Agent tool call failed")
    return task


def _before_the_first_request(tmp_path):
    return build_loop(tmp_path, Step("1"))


DUE_AND_NONE_OUT = {
    "before-the-first-request": _before_the_first_request,
    "after-a-withdrawal": _withdrawn,
}


@pytest.mark.parametrize("state", list(DUE_AND_NONE_OUT))
def test_the_status_tables_last_line_names_next_with_the_callers_base(tmp_path, state):
    task = DUE_AND_NONE_OUT[state](tmp_path)
    given = location(task, "base-ref")

    table = status_table(task, given)

    last = table.strip().splitlines()[-1]
    commands = [c for c in printed_commands(last) if f" next {SLUG}" in c]
    assert commands, f"the table's last line names no next command:\n{table}"
    assert trailing_location(commands[0]) == as_pairs(given), table


def test_a_bare_calls_then_is_printed_as_before(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    asked = call(task, "next")

    assert asked.doc["then"] == BARE_THEN


def test_a_bare_calls_resume_is_printed_as_before(tmp_path):
    task = _exhausted(tmp_path)

    stopped = call(task, "next")

    assert stopped.stop["resume"] == BARE_RESUME
