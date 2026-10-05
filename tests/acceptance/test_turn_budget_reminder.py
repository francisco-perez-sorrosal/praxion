"""A subagent learns it is near its turn cap while it can still stop in a committable state.

The reminder counts the distinct API requests in the calling agent's own transcript
against the cap its definition declares, and injects one line at 60 percent and one at
80 percent of that cap -- once per agent and threshold. It never fires for the main
session or for an agent with no declared cap, and on any failure it stays silent and
lets the tool call proceed. The plugin registers it for every tool call.
"""

from __future__ import annotations

from tests.acceptance.drivers.turn_budget_reminder import (
    IMPLEMENTER_AGENT_TYPE,
    IMPLEMENTER_DEFINITION,
    UNCAPPED_AGENT_TYPE,
    declared_max_turns,
    grow_agent_transcript,
    main_session_payload,
    matches_every_tool,
    new_agent_id,
    new_session,
    parse_line,
    pre_tool_use_registrations,
    reminder_script,
    run_reminder,
    subagent_payload,
)

CAP = declared_max_turns(IMPLEMENTER_DEFINITION)
BELOW_SIXTY = int(CAP * 0.59)
PAST_SIXTY = int(CAP * 0.65)
STILL_BELOW_EIGHTY = int(CAP * 0.75)
PAST_EIGHTY = int(CAP * 0.85)
NEAR_THE_CAP = int(CAP * 0.95)


def _implementer_at(tmp_path, requests: int):
    """A session with one implementer whose own transcript holds `requests` distinct requests."""
    session = new_session(tmp_path)
    agent_id = new_agent_id()
    grow_agent_transcript(session, agent_id, requests)
    return session, agent_id


def _call(session, agent_id):
    return run_reminder(
        subagent_payload(session, agent_id, IMPLEMENTER_AGENT_TYPE), cwd=session.cwd
    )


def test_an_agent_below_sixty_percent_of_its_cap_gets_no_reminder(tmp_path):
    session, agent_id = _implementer_at(tmp_path, BELOW_SIXTY)

    run = _call(session, agent_id)

    assert run.exit_code == 0
    assert run.reminders() == []


def test_crossing_sixty_percent_injects_one_reminder_stating_turns_used_of_the_cap(tmp_path):
    session, agent_id = _implementer_at(tmp_path, PAST_SIXTY)

    run = _call(session, agent_id)

    assert run.exit_code == 0
    assert len(run.reminders()) == 1
    used, cap, _ = parse_line(run.reminders()[0])
    assert (used, cap) == (PAST_SIXTY, CAP)


def test_the_sixty_percent_reminder_fires_once_per_agent(tmp_path):
    session, agent_id = _implementer_at(tmp_path, PAST_SIXTY)
    _call(session, agent_id)
    grow_agent_transcript(session, agent_id, STILL_BELOW_EIGHTY)

    run = _call(session, agent_id)

    assert run.reminders() == []


def test_crossing_eighty_percent_tells_the_agent_to_stop_in_a_committable_state(tmp_path):
    session, agent_id = _implementer_at(tmp_path, PAST_SIXTY)
    _call(session, agent_id)
    grow_agent_transcript(session, agent_id, PAST_EIGHTY)

    run = _call(session, agent_id)

    assert len(run.reminders()) == 1
    used, cap, action = parse_line(run.reminders()[0])
    assert (used, cap) == (PAST_EIGHTY, CAP)
    assert "committable" in action.lower(), action


def test_the_eighty_percent_reminder_fires_once_per_agent(tmp_path):
    session, agent_id = _implementer_at(tmp_path, PAST_SIXTY)
    _call(session, agent_id)
    grow_agent_transcript(session, agent_id, PAST_EIGHTY)
    _call(session, agent_id)
    grow_agent_transcript(session, agent_id, NEAR_THE_CAP)

    run = _call(session, agent_id)

    assert run.reminders() == []


def test_each_agent_gets_its_own_reminder(tmp_path):
    session, first = _implementer_at(tmp_path, PAST_SIXTY)
    _call(session, first)
    second = new_agent_id()
    grow_agent_transcript(session, second, PAST_SIXTY)

    run = _call(session, second)

    assert len(run.reminders()) == 1


def test_the_main_session_never_gets_a_reminder(tmp_path):
    session = new_session(tmp_path, main_requests=NEAR_THE_CAP)

    run = run_reminder(main_session_payload(session), cwd=session.cwd)

    assert run.exit_code == 0
    assert run.reminders() == []


def test_an_agent_with_no_declared_cap_never_gets_a_reminder(tmp_path):
    session = new_session(tmp_path)
    agent_id = new_agent_id()
    grow_agent_transcript(session, agent_id, NEAR_THE_CAP)

    run = run_reminder(subagent_payload(session, agent_id, UNCAPPED_AGENT_TYPE), cwd=session.cwd)

    assert run.exit_code == 0
    assert run.reminders() == []


def test_an_unparseable_payload_fails_open_silently(tmp_path):
    session = new_session(tmp_path)

    run = run_reminder("{not json", cwd=session.cwd)

    assert run.exit_code == 0
    assert run.stdout.strip() == ""


def test_a_missing_agent_transcript_fails_open_silently(tmp_path):
    session = new_session(tmp_path)

    run = _call(session, new_agent_id())

    assert run.exit_code == 0
    assert run.stdout.strip() == ""


def test_an_agent_whose_definition_cannot_be_read_fails_open_silently(tmp_path):
    session = new_session(tmp_path)
    agent_id = new_agent_id()
    grow_agent_transcript(session, agent_id, PAST_EIGHTY)

    run = run_reminder(
        subagent_payload(session, agent_id, "praxion:no-such-agent"), cwd=session.cwd
    )

    assert run.exit_code == 0
    assert run.stdout.strip() == ""


def test_the_plugin_registers_the_reminder_for_every_tool_call():
    name = reminder_script().name
    matchers = [m for m, command in pre_tool_use_registrations() if name in command]

    assert matchers, f"no PreToolUse registration runs {name}"
    assert any(matches_every_tool(m) for m in matchers), matchers
