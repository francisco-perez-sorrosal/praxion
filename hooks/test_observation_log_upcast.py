"""Legacy helper stops are presented as `helper_stop`; nothing else is.

A harness helper call left an `agent_stop` row with no start, no prior row
and no usage. The reader presents those legacy rows as the slim
`helper_stop` row the stop path now writes directly. A row the owner writer
appended carries `log_mode` and was classified at write time, so it always
reads back as written. A legacy row carrying token counts with no source
label stays `agent_stop`: those are helpers contaminated with the parent
session's usage, indistinguishable by content from a real agent, so the
rule stays conservative.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hooks._observation_log import reader, writer
from hooks._observation_log.reader import upcast
from hooks._observation_log.registry import EventClass


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


def test_a_parent_contaminated_helper_row_is_left_as_agent_stop() -> None:
    """Pre-`usage_source` helper rows carry the parent session's usage; the
    content cannot tell them from a real agent, so they are not relabelled."""
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


@pytest.mark.parametrize("log_mode", ["standard", "full"])
def test_a_log_mode_stamped_agent_stop_with_no_usage_passes_through_unchanged(
    log_mode: str,
) -> None:
    row = _stop(agent_type="praxion:implementer", log_mode=log_mode)
    assert upcast(row) is row


def test_an_agent_stop_the_owner_writer_keeps_reads_back_unchanged(tmp_path: Path) -> None:
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    row = _stop(agent_type="praxion:implementer")

    written = writer.record(ai_state_dir, EventClass.AGENT_STOP, row, env={})

    assert written is True
    assert reader.read_rows(ai_state_dir) == [{**row, "log_mode": "standard"}]
