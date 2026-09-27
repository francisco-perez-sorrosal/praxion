"""Legacy helper stops are presented as `helper_stop`; every agent is not.

A harness helper call left an `agent_stop` row with no start, no prior row
and no usage. The reader presents those as the slim `helper_stop` row the
stop path now writes directly. A real agent must never be relabelled --
including one recorded before `usage_source` existed, whose row carries
token counts with no source label.
"""

from __future__ import annotations

from hooks._observation_log.reader import upcast


def _stop(**fields: object) -> dict:
    row = {
        "timestamp": "2026-09-20T00:00:00+00:00",
        "session_id": "s1",
        "agent_id": "a1",
        "agent_type": "unknown",
        "project": "repo",
        "event_type": "agent_stop",
        "start_correlation": "unobserved-agent",
        "usage_source": None,
        "tokens_in": None,
        "tokens_out": None,
        "cache_read": None,
        "cache_create": None,
    }
    row.update(fields)
    return row


def test_a_legacy_helper_stop_becomes_a_slim_helper_stop_row() -> None:
    assert upcast(_stop()) == {
        "timestamp": "2026-09-20T00:00:00+00:00",
        "session_id": "s1",
        "agent_id": "a1",
        "project": "repo",
        "event_type": "helper_stop",
    }


def test_a_pre_usage_source_agent_with_token_counts_is_not_a_helper() -> None:
    row = _stop(tokens_in=998, tokens_out=47518)
    del row["usage_source"]
    assert upcast(row) is row


def test_a_stop_with_transcript_sourced_usage_is_not_a_helper() -> None:
    row = _stop(usage_source="subagent-transcript")
    assert upcast(row) is row


def test_a_paired_stop_is_not_a_helper() -> None:
    row = _stop(start_correlation="paired")
    assert upcast(row) is row


def test_non_stop_rows_pass_through_unchanged() -> None:
    row = {"event_type": "tool_use", "agent_id": "a1", "start_correlation": "unobserved-agent"}
    assert upcast(row) is row
