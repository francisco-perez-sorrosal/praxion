"""Lifecycle hook: capture session and agent events into the observations WAL.

Fires on SessionStart, Stop, SubagentStart, SubagentStop.
Async hook (async: true) -- never blocks.
Exit 0 unconditionally.

Why the agent_type resolution below exists
------------------------------------------
`.ai-state/observations.jsonl` is the recovery write-ahead log designated by
dec-248, and its job is to *localize* a truncated pipeline step: which agent
stopped, and where it last wrote. A row that cannot name its agent cannot
localize anything.

Measured against the live WAL, `SubagentStop` payloads split into two classes:

* Terminations that also produced a `SubagentStart` row and `tool_use` rows
  carry a populated `agent_type` -- these were always recorded correctly.
* A second class arrives with `agent_type` **present but empty**, no
  `SubagentStart`, and zero `tool_use` rows anywhere in the WAL for that
  `agent_id`. (Present-but-empty rather than absent is decidable from the old
  code: it wrote ``payload.get("agent_type", "main")``, so an absent key would
  have produced ``"main"``, and no row ever said ``main`` for a subagent.)

For that second class the agent type is genuinely **not knowable at this hook**
-- the harness does not supply it and the WAL holds no earlier record to carry
forward from. Writing ``""`` made an unanswerable case indistinguishable from a
recorded one. So resolution is explicit and its provenance is recorded in
``agent_type_source``:

    payload         -- the harness supplied it
    wal-backfill    -- recovered from an earlier row for the same agent_id
    session-default -- a session-level row, where "main" is the known answer
    unresolved      -- genuinely unavailable; agent_type is "unknown"

`wal-backfill` is what repairs a *dropped* `SubagentStart` (this hook is async
and can be killed): every real subagent in the measured WAL emitted 2-76
`tool_use` rows carrying the correct `agent_type`, so one earlier row for the
same `agent_id` is enough to recover the name.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _hook_utils import DISABLE_OBSERVABILITY, append_observation, is_disabled

EVENT_MAP = {
    "SessionStart": "session_start",
    "Stop": "session_stop",
    "SubagentStart": "agent_start",
    "SubagentStop": "agent_stop",
}

# Lifecycle events that describe a *subagent* rather than the session itself.
# Only these are eligible for WAL backfill; a session row's agent is "main".
AGENT_LIFECYCLE_EVENTS = frozenset({"agent_start", "agent_stop"})

MAIN_AGENT_TYPE = "main"
UNKNOWN_AGENT_TYPE = "unknown"
UNKNOWN_AGENT_ID = "unknown-agent"

SOURCE_PAYLOAD = "payload"
SOURCE_WAL_BACKFILL = "wal-backfill"
SOURCE_SESSION_DEFAULT = "session-default"
SOURCE_UNRESOLVED = "unresolved"

# Bound on the backfill read. The WAL rotates at 10 MiB (_hook_utils), and this
# hook runs on every subagent boundary, so the lookup reads a tail window rather
# than the whole file. A prior row for the same agent_id that has already
# scrolled past this window is treated as absent -- the fallback is "unresolved",
# never a guess.
#
# The lookup deliberately does NOT follow rotation into observations.jsonl.1.
# Reading a 10 MiB predecessor on a hot hook path would buy a case that has not
# been observed: every stop measured across a rotation boundary arrived with its
# agent_type already populated, and the *reader* side already stitches both
# files (scripts/reconcile_pipeline_state.py), so a start stranded in .1 is
# recoverable downstream. This is a stated boundary, not an oversight.
BACKFILL_TAIL_BYTES = 512 * 1024


def _tail_lines(obs_path: Path, max_bytes: int = BACKFILL_TAIL_BYTES) -> list[str]:
    """Return the last complete JSONL lines of ``obs_path``.

    Reads at most ``max_bytes`` from the end. When the window starts mid-file
    the first line may be a fragment, so it is discarded. Any OSError (missing
    file, unreadable path) degrades to an empty list -- the caller then reports
    the agent type as unresolved rather than failing the hook.
    """
    try:
        with open(obs_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, max_bytes)
            handle.seek(size - window)
            chunk = handle.read(window)
    except OSError:
        return []
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if window < size and lines:
        lines = lines[1:]  # drop the fragment the window cut in half
    return lines


def lookup_agent_type(obs_path: Path | None, agent_id: str) -> str:
    """Return the most recent non-empty ``agent_type`` recorded for ``agent_id``.

    Scans the WAL tail newest-first and stops at the first match. Returns ""
    when the agent has no earlier row -- which is the measured reality for the
    orphaned-stop class, and is reported as such rather than papered over.
    """
    if not agent_id or obs_path is None:
        return ""
    for line in reversed(_tail_lines(obs_path)):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue  # a torn tail line from a concurrent append
        if not isinstance(row, dict) or row.get("agent_id") != agent_id:
            continue
        recorded = str(row.get("agent_type") or "").strip()
        if recorded and recorded != UNKNOWN_AGENT_TYPE:
            return recorded
    return ""


def resolve_agent_type(
    payload: dict, event_type: str, obs_path: Path | None = None
) -> tuple[str, str]:
    """Return ``(agent_type, agent_type_source)`` for one lifecycle payload.

    Never returns an empty ``agent_type``: an unanswerable case resolves to
    ``UNKNOWN_AGENT_TYPE`` with source ``unresolved``, so a reader can tell
    "not knowable here" apart from "recorded".
    """
    declared = str(payload.get("agent_type") or "").strip()
    if declared:
        return declared, SOURCE_PAYLOAD
    if event_type not in AGENT_LIFECYCLE_EVENTS:
        # SessionStart/Stop carry no agent_type at all; "main" is the known
        # answer for a session row, not a guess.
        return MAIN_AGENT_TYPE, SOURCE_SESSION_DEFAULT
    backfilled = lookup_agent_type(obs_path, str(payload.get("agent_id") or ""))
    if backfilled:
        return backfilled, SOURCE_WAL_BACKFILL
    return UNKNOWN_AGENT_TYPE, SOURCE_UNRESOLVED


def resolve_agent_id(payload: dict) -> str:
    """Return a non-empty agent identifier for the row.

    Falls back to ``session_id`` (the main agent's own identifier, matching the
    PostToolUse writer) and finally to an explicit sentinel, so no lifecycle row
    is ever written with an unusable empty id.
    """
    agent_id = str(payload.get("agent_id") or "").strip()
    if agent_id:
        return agent_id
    session_id = str(payload.get("session_id") or "").strip()
    return session_id or UNKNOWN_AGENT_ID


def build_summary(event_type: str, payload: dict, agent_type: str) -> str:
    """Build a human-readable summary for lifecycle events."""
    if event_type == "session_start":
        return "Session started"
    if event_type == "session_stop":
        return "Session ended"
    label = str(payload.get("description") or "") or agent_type
    if event_type == "agent_start":
        return f"Agent started: {label[:150]}"
    if event_type == "agent_stop":
        return f"Agent completed: {label[:150]}"
    return event_type


def build_observation(payload: dict, event_type: str, obs_path: Path | None = None) -> dict:
    """Assemble one WAL row from a lifecycle payload.

    ``obs_path`` is read only when the payload omits ``agent_type`` on a
    subagent lifecycle event; every other path is pure.
    """
    agent_type, agent_type_source = resolve_agent_type(payload, event_type, obs_path)
    cwd = payload.get("cwd", ".")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": payload.get("session_id", ""),
        "agent_type": agent_type,
        "agent_id": resolve_agent_id(payload),
        "project": Path(cwd).name,
        "event_type": event_type,
        "tool_name": None,
        "summary": build_summary(event_type, payload, agent_type),
        "file_paths": [],
        "outcome": None,
        "classification": None,
        "agent_type_source": agent_type_source,
    }


def main() -> None:
    if is_disabled(DISABLE_OBSERVABILITY):
        return

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(payload, dict):
        return

    event_type = EVENT_MAP.get(payload.get("hook_event_name", ""))
    if event_type is None:
        return

    cwd = payload.get("cwd", ".")
    ai_state_dir = Path(cwd) / ".ai-state"
    if not ai_state_dir.exists():
        return  # graceful degradation

    obs_path = ai_state_dir / "observations.jsonl"
    append_observation(obs_path, build_observation(payload, event_type, obs_path))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
