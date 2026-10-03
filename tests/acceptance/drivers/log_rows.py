"""Builders for log rows in the shapes the hooks write (and wrote before modes existed).

Shapes follow the row contract the owner package documents and this repository's
existing tests use: an `agent_start` without `slug_attribution` (attributed by
its `project`), an `agent_stop` carrying transcript-sourced usage (the cost
report's honest population), the slim `helper_stop`, a legacy stop row that
self-reports as a helper call (no start, no usage, `unobserved-agent`), and a
`session_start` carrying `log_mode` and `log_mode_source`.
"""

from __future__ import annotations

from typing import Any

_ABSENT = object()


def agent_start(
    agent_id: str, *, at: str, project: str, session_id: str = "s-main", **extra: Any
) -> dict:
    row = {
        "timestamp": at,
        "session_id": session_id,
        "agent_type": "praxion:implementer",
        "agent_id": agent_id,
        "project": project,
        "event_type": "agent_start",
        "tool_name": None,
        "summary": "Agent started: praxion:implementer",
        "file_paths": [],
        "outcome": None,
        "classification": None,
        "agent_type_source": "payload",
        "start_correlation": "not-applicable",
    }
    row.update(extra)
    return row


def agent_stop(
    agent_id: str, *, at: str, project: str, session_id: str = "s-main", **extra: Any
) -> dict:
    row = {
        "timestamp": at,
        "session_id": session_id,
        "agent_type": "praxion:implementer",
        "agent_id": agent_id,
        "project": project,
        "event_type": "agent_stop",
        "tool_name": None,
        "summary": "Agent completed: praxion:implementer",
        "file_paths": [],
        "outcome": None,
        "classification": None,
        "agent_type_source": "payload",
        "start_correlation": "paired",
    }
    row.update(extra)
    return row


def costed_stop(agent_id: str, *, at: str, project: str, tokens_out: int = 21796) -> dict:
    """An `agent_stop` whose usage came from the agent's own transcript."""
    return agent_stop(
        agent_id,
        at=at,
        project=project,
        session_id="f24cda13-489f-4da1-a37c-b6bacd468135",
        agent_type="praxion:context-engineer",
        stop_source="hook",
        tokens_in=80,
        tokens_out=tokens_out,
        cache_read=3359140,
        cache_create=321135,
        duration_ms=226552,
        model="claude-sonnet-5",
        usage_source="subagent-transcript",
    )


def helper_stop(agent_id: str, *, at: str, project: str) -> dict:
    return {
        "timestamp": at,
        "session_id": "s-main",
        "agent_id": agent_id,
        "project": project,
        "event_type": "helper_stop",
        "log_mode": "standard",
    }


def legacy_helper_stop(agent_id: str, *, at: str, project: str) -> dict:
    """A stop row from before modes that self-reports as a harness helper call."""
    return agent_stop(
        agent_id,
        at=at,
        project=project,
        agent_type="unknown",
        start_correlation="unobserved-agent",
        usage_source=None,
        tokens_in=None,
        tokens_out=None,
        cache_read=None,
        cache_create=None,
    )


def tool_write(
    agent_id: str, path: str, *, at: str, project: str = "pipeline", **extra: Any
) -> dict:
    row = {
        "timestamp": at,
        "session_id": "s-main",
        "agent_type": "praxion:implementer",
        "agent_id": agent_id,
        "project": project,
        "event_type": "tool_use",
        "tool_name": "Write",
        "file_paths": [path],
        "outcome": "success",
    }
    row.update(extra)
    return row


def session_start(session_id: str, *, at: str, project: str, source: object = "default") -> dict:
    """A session start; `source=None` leaves out both mode fields, as rows before modes did."""
    row = {
        "timestamp": at,
        "session_id": session_id,
        "agent_type": "main",
        "agent_id": session_id,
        "project": project,
        "event_type": "session_start",
    }
    if source is not None:
        row["log_mode"] = "full" if source == "invalid-setting" else "standard"
        row["log_mode_source"] = source
    return row
