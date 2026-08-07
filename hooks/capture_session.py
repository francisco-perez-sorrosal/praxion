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

Why the start correlation below exists
--------------------------------------
The `agent_id` this hook writes on a stop row is **not** minted here: it is the
harness value, passed through verbatim (`resolve_agent_id`). Measured over the
live WAL, no stop row's id was ever a fallback -- zero fell back to
``session_id``, zero to the sentinel. Pairing nonetheless fails for a
substantial minority of stops, because the *start* side is missing: the WAL
holds 614 `agent_start` rows against 651 `agent_stop` rows, and 154 stops have
no `agent_start` for their `agent_id` anywhere in the file.

Those starts were lost before this hook could record them, and four of the 154
prove the loss is real rather than a phantom agent: their `agent_id` also
carries 2, 6, 11 and 24 `tool_use` rows, so the subagent demonstrably ran while
its `SubagentStart` capture produced nothing. A stop cannot reconstruct a start
that was never delivered, and persisting a mapping *at start* would be absent in
exactly the cases that need it. So the honest repair is to stop making readers
re-derive the pairing, and record the emitter's own verdict in
``start_correlation``:

    paired           -- an `agent_start` row for this agent_id was observed
    unobserved-start -- no such row was observed (delivery loss, or rotation)
    not-applicable   -- a start row or a session row: nothing to pair with

The verdict is scoped to the same bounded tail window the backfill reads, so
``unobserved-start`` asserts **non-observation, not non-existence** -- which is
precisely the distinction a reader needs and could not previously make.
A `tool_use` row deliberately does not satisfy the pairing (it satisfies the
backfill): it names the agent, it does not witness its spawn.

Named consumers: the sentinel's pipeline-dimension pairing check and
`scripts/reconcile_pipeline_state.py`, both of which currently re-derive the
pairing by scanning the whole file and report an unpaired stop as a failure
rather than as an unobserved start.
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

# Start/stop correlation verdict recorded on every row this hook writes.
CORRELATION_PAIRED = "paired"
CORRELATION_UNOBSERVED_START = "unobserved-start"
CORRELATION_NOT_APPLICABLE = "not-applicable"

# Bound on the lookup read. The WAL rotates at 10 MiB (_hook_utils), and this
# hook runs on every subagent boundary, so the lookup reads a tail window rather
# than the whole file. A prior row for the same agent_id that has already
# scrolled past this window is treated as absent -- the fallbacks are
# "unresolved" and "unobserved-start", never a guess. Both fallbacks name a
# non-observation for exactly this reason; neither claims the row is not there.
#
# The lookup deliberately does NOT follow rotation into observations.jsonl.1.
# Reading a 10 MiB predecessor on a hot hook path would buy a case that has not
# been observed: every stop measured across a rotation boundary arrived with its
# agent_type already populated, and the *reader* side already stitches both
# files (scripts/reconcile_pipeline_state.py), so a start stranded in .1 is
# recoverable downstream. This is a stated boundary, not an oversight.
BACKFILL_TAIL_BYTES = 512 * 1024


def _tail_lines(obs_path: Path, max_bytes: int | None = None) -> list[str]:
    """Return the last complete JSONL lines of ``obs_path``.

    Reads at most ``max_bytes`` from the end, defaulting to
    ``BACKFILL_TAIL_BYTES`` resolved at call time so the bound stays a single
    tunable (a signature default would freeze the value at import). When the
    window starts mid-file the first line may be a fragment, so it is
    discarded. Any OSError (missing file, unreadable path) degrades to an empty
    list -- the caller then reports the agent type as unresolved and the start
    as unobserved rather than failing the hook.
    """
    if max_bytes is None:
        max_bytes = BACKFILL_TAIL_BYTES
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


def lookup_prior_agent(obs_path: Path | None, agent_id: str) -> tuple[str, bool]:
    """Return ``(recovered_agent_type, start_row_seen)`` for ``agent_id``.

    One newest-first pass over the WAL tail answers both questions the stop path
    asks, so recording the correlation costs no extra read. The recovered type
    is the most recent usable one ("" when the agent has no earlier row -- the
    measured reality for the orphaned-stop class, reported rather than papered
    over); ``start_row_seen`` is True only for an actual ``agent_start`` row,
    never for a ``tool_use`` row that merely names the same agent.

    The scan ends early once a start row settles both answers.
    """
    if not agent_id or obs_path is None:
        return "", False
    recovered = ""
    for line in reversed(_tail_lines(obs_path)):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue  # a torn tail line from a concurrent append
        if not isinstance(row, dict) or row.get("agent_id") != agent_id:
            continue
        if not recovered:
            recorded = str(row.get("agent_type") or "").strip()
            if recorded and recorded != UNKNOWN_AGENT_TYPE:
                recovered = recorded
        if row.get("event_type") == "agent_start":
            return recovered, True
    return recovered, False


def resolve_agent_type(payload: dict, event_type: str, backfilled: str = "") -> tuple[str, str]:
    """Return ``(agent_type, agent_type_source)`` for one lifecycle payload.

    Pure: ``backfilled`` is whatever ``lookup_prior_agent`` recovered from the
    WAL, or "" when nothing was recovered or no lookup ran. Never returns an
    empty ``agent_type``: an unanswerable case resolves to
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
    if backfilled:
        return backfilled, SOURCE_WAL_BACKFILL
    return UNKNOWN_AGENT_TYPE, SOURCE_UNRESOLVED


def resolve_start_correlation(event_type: str, start_row_seen: bool) -> str:
    """Return the start/stop pairing verdict recorded on the row.

    Only a stop can pair: a start row *is* the start and a session row has no
    spawn, so both are ``not-applicable`` rather than a misleading "unpaired".
    """
    if event_type != "agent_stop":
        return CORRELATION_NOT_APPLICABLE
    return CORRELATION_PAIRED if start_row_seen else CORRELATION_UNOBSERVED_START


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


def _needs_wal_lookup(payload: dict, event_type: str) -> bool:
    """True when this row's resolution depends on an earlier row for the agent.

    Every stop needs it for the pairing verdict; a start needs it only when the
    payload withheld the agent type. Session rows never need it.
    """
    if event_type == "agent_stop":
        return True
    return event_type in AGENT_LIFECYCLE_EVENTS and not str(payload.get("agent_type") or "").strip()


def build_observation(payload: dict, event_type: str, obs_path: Path | None = None) -> dict:
    """Assemble one WAL row from a lifecycle payload.

    ``obs_path`` is read once per row and only when ``_needs_wal_lookup`` says
    an earlier row could answer something; every other path is pure. A failed
    read degrades to "nothing recovered, no start observed" -- never a raise,
    and never a claim the emitter cannot support.
    """
    # Correlate on the harness-supplied id only. resolve_agent_id's fallbacks
    # name the *session*, whose rows belong to the main agent -- keying the
    # lookup on one would backfill a subagent's type as "main" and pair its stop
    # against the session's own history.
    harness_agent_id = str(payload.get("agent_id") or "").strip()
    backfilled, start_row_seen = (
        lookup_prior_agent(obs_path, harness_agent_id)
        if _needs_wal_lookup(payload, event_type)
        else ("", False)
    )
    agent_type, agent_type_source = resolve_agent_type(payload, event_type, backfilled)
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
        "start_correlation": resolve_start_correlation(event_type, start_row_seen),
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
