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
substantial share of stops: the WAL holds 257 `agent_start` rows against 3,031
`agent_stop` rows, and 2,812 stops have no `agent_start` for their `agent_id`
anywhere in the file.

Those 2,812 are not one population. 2,770 of them carry `agent_type: unknown`,
`agent_type_source: unresolved`, and **no row of any kind** -- no start, no
`tool_use` -- for their `agent_id` anywhere in the tail: these are the
harness's own unannounced internal helper agents (see Known WAL anomalies
below), firing roughly once every 30s of session time, not lost starts. The
remaining 14 carry `tool_use` rows and no `agent_start`: their agent
demonstrably ran while its `SubagentStart` capture produced nothing, which is
the real delivery-loss population this hook exists to name. Lumping both
under one verdict hid that only the second class is a defect this fleet
should chase, so the emitter's verdict now distinguishes them:

    paired            -- an `agent_start` row for this agent_id was observed
    unobserved-start  -- no start row observed, but a `tool_use` row proves
                         the agent ran: delivery loss, or rotation
    unobserved-agent  -- no row of any kind observed for this agent_id: an
                         unannounced harness-internal helper, not a lost start
    not-applicable    -- a start row or a session row: nothing to pair with

The verdict is scoped to the same bounded tail window the backfill reads, so
``unobserved-start`` and ``unobserved-agent`` both assert **non-observation,
not non-existence** -- which is precisely the distinction a reader needs and
could not previously make.

Known WAL anomalies (diagnosed 2026-08-30, sentinel P03; refined 2026-09-05)
-----------------------------------------------------------------------------
* 2026-08-25 only: 30 lifecycle rows are near-duplicates (same agent_id +
  event_type, ms apart, one row old-style empty ``agent_type`` and one
  new-style ``unknown``) -- two installed copies of this hook (stale plugin
  cache + refreshed copy) raced during that day's plugin update. Not
  reproducing since 2026-08-26; no dedup logic is warranted for a
  one-day install-transition artifact.
* Six `agent_start` rows emitted `tool_use` and never got an `agent_stop`:
  ``a045b98b6`` (2026-08-13, i-am:implementer), ``a74850d89`` (2026-08-25,
  praxion:context-engineer), ``a92a8a243`` (2026-08-31, praxion:implementer),
  ``aa309b3f8`` (2026-09-02, praxion:implementer), ``a30a946aa`` (2026-09-02,
  praxion:systems-architect), ``a07f58e1f`` (2026-09-05, praxion:implementer).
  Cause, verified against the harness transcripts for the two most recent ids
  and consistent (hours-long continuing sessions, no corresponding stop) for
  the other four: the harness suspends a background subagent at its turn
  limit and reports the suspension to the MAIN agent as a
  `<task-notification>` in the main transcript instead of firing
  `SubagentStop`. The notification's `<summary>` reads ``Agent "<name>"
  stopped at its N-turn limit (partial result; SendMessage to task-id to
  continue)`` and carries a `<task-id>` equal to the WAL `agent_id`; a second
  shape, ``Agent "<name>" was stopped by Claude`` (3 occurrences across
  transcripts), covers an orchestrator-initiated stop. A normal completion
  (``Agent "<name>" finished``, 446 occurrences) *does* fire `SubagentStop` --
  verified against a background sentinel agent this session. `main()` now
  reads the Stop payload's own `transcript_path` for exactly these two shapes
  and backfills the missing `agent_stop` (`stop_source:
  "transcript-notification"`) whenever the matching `agent_start` is still in
  the tail window -- see `find_suspended_tasks`/`build_suspension_stop` below.
* 2,770 of the 2,812 unpaired stops carry no row of any kind for their
  `agent_id` -- the harness's own unannounced internal helper agents (not a
  hook defect), reported as `unobserved-agent`. See "Why the start
  correlation below exists" above.
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
import re
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
CORRELATION_UNOBSERVED_AGENT = "unobserved-agent"
CORRELATION_NOT_APPLICABLE = "not-applicable"

# Provenance of an agent_stop row: a regular hook delivery, or one
# reconstructed from a transcript task-notification (see
# find_suspended_tasks / build_suspension_stop). Only agent_stop rows carry
# this field -- start rows and session rows have nothing to attribute.
STOP_SOURCE_HOOK = "hook"
STOP_SOURCE_TRANSCRIPT_NOTIFICATION = "transcript-notification"

# Bound on the transcript scan for suspended-subagent task-notifications. The
# Stop payload's transcript can grow long over a session; a just-suspended
# subagent's notification is always among the most recent turns, so a
# bounded tail read is enough and keeps this hot hook path cheap. Mirrors
# BACKFILL_TAIL_BYTES's rationale below.
TRANSCRIPT_TAIL_BYTES = 1024 * 1024  # 1 MiB

# Outcomes a synthetic suspension stop can carry in its `outcome` field.
OUTCOME_TURN_LIMIT = "turn-limit"
OUTCOME_STOPPED = "stopped"

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


def lookup_prior_agent(obs_path: Path | None, agent_id: str) -> tuple[str, bool, bool]:
    """Return ``(recovered_agent_type, start_row_seen, any_row_seen)`` for ``agent_id``.

    One newest-first pass over the WAL tail answers all three questions the
    stop path asks, so recording the correlation costs no extra read. The
    recovered type is the most recent usable one ("" when the agent has no
    earlier row -- the measured reality for the orphaned-stop class, reported
    rather than papered over); ``start_row_seen`` is True only for an actual
    ``agent_start`` row, never for a ``tool_use`` row that merely names the
    same agent; ``any_row_seen`` is True for *any* row naming this agent_id,
    which is what separates a genuinely unannounced agent (nothing at all)
    from a start that was merely dropped (a ``tool_use`` row survives it).

    The scan ends early once a start row settles all three answers.
    """
    if not agent_id or obs_path is None:
        return "", False, False
    recovered = ""
    any_row_seen = False
    for line in reversed(_tail_lines(obs_path)):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue  # a torn tail line from a concurrent append
        if not isinstance(row, dict) or row.get("agent_id") != agent_id:
            continue
        any_row_seen = True
        if not recovered:
            recorded = str(row.get("agent_type") or "").strip()
            if recorded and recorded != UNKNOWN_AGENT_TYPE:
                recovered = recorded
        if row.get("event_type") == "agent_start":
            return recovered, True, True
    return recovered, False, any_row_seen


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


def resolve_start_correlation(event_type: str, start_row_seen: bool, any_row_seen: bool) -> str:
    """Return the start/stop pairing verdict recorded on the row.

    Only a stop can pair: a start row *is* the start and a session row has no
    spawn, so both are ``not-applicable`` rather than a misleading "unpaired".
    A stop with no start splits further: a surviving ``tool_use`` row proves
    the agent ran (``unobserved-start`` -- delivery loss), while no row at all
    means the harness never announced this agent in the first place
    (``unobserved-agent`` -- an unannounced helper, not a defect here).
    """
    if event_type != "agent_stop":
        return CORRELATION_NOT_APPLICABLE
    if start_row_seen:
        return CORRELATION_PAIRED
    return CORRELATION_UNOBSERVED_START if any_row_seen else CORRELATION_UNOBSERVED_AGENT


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
    backfilled, start_row_seen, any_row_seen = (
        lookup_prior_agent(obs_path, harness_agent_id)
        if _needs_wal_lookup(payload, event_type)
        else ("", False, False)
    )
    agent_type, agent_type_source = resolve_agent_type(payload, event_type, backfilled)
    cwd = payload.get("cwd", ".")
    row = {
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
        "start_correlation": resolve_start_correlation(event_type, start_row_seen, any_row_seen),
    }
    if event_type == "agent_stop":
        row["stop_source"] = STOP_SOURCE_HOOK
    return row


def _read_transcript_tail(transcript_path: str, max_bytes: int = TRANSCRIPT_TAIL_BYTES) -> str:
    """Return the last ``max_bytes`` of ``transcript_path`` as text.

    Any OSError (missing file, unreadable path) degrades to "" -- the caller
    then backfills nothing rather than raising or delaying the Stop hook.
    """
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, max_bytes)
            handle.seek(size - window)
            chunk = handle.read(window)
    except OSError:
        return ""
    return chunk.decode("utf-8", errors="replace")


# A suspended-subagent notification, bounded by its own tags so a scan never
# crosses into a sibling block. `<task-id>` and `<summary>` are pulled out of
# the matched block rather than the whole text, for the same reason.
_TASK_NOTIFICATION_RE = re.compile(r"<task-notification>.*?</task-notification>", re.DOTALL)
_TASK_ID_RE = re.compile(r"<task-id>([^<]+)</task-id>")
_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)

# The two verified suspension shapes (see the module docstring's Known WAL
# anomalies section). A normal completion ("... finished") matches neither.
_TURN_LIMIT_RE = re.compile(r"stopped at its \d+-turn limit")
_STOPPED_BY_CLAUDE_RE = re.compile(r"was stopped by Claude")


def find_suspended_tasks(text: str) -> list[tuple[str, str]]:
    """Scan raw transcript text for suspended-subagent task-notifications.

    Pure: text in, ``(task_id, outcome)`` pairs out -- so the shape stays
    testable and replaceable the moment the harness changes its wording,
    without touching any I/O. A `<task-notification>` block whose `<summary>`
    matches neither known shape (a normal "... finished", or one this scan
    does not yet recognize) contributes nothing: silence is correct here,
    not a raise.
    """
    findings: list[tuple[str, str]] = []
    for block_match in _TASK_NOTIFICATION_RE.finditer(text):
        block = block_match.group(0)
        task_id_match = _TASK_ID_RE.search(block)
        summary_match = _SUMMARY_RE.search(block)
        if not task_id_match or not summary_match:
            continue
        summary = summary_match.group(1)
        if _TURN_LIMIT_RE.search(summary):
            findings.append((task_id_match.group(1), OUTCOME_TURN_LIMIT))
        elif _STOPPED_BY_CLAUDE_RE.search(summary):
            findings.append((task_id_match.group(1), OUTCOME_STOPPED))
    return findings


_SUSPENSION_SUMMARY = {
    OUTCOME_TURN_LIMIT: "Agent suspended at turn limit: {agent_type}",
    OUTCOME_STOPPED: "Agent stopped by orchestrator: {agent_type}",
}


def build_suspension_stop(
    payload: dict, task_id: str, kind: str, agent_type: str, agent_type_source: str
) -> dict:
    """Build the synthetic ``agent_stop`` row for a transcript-observed suspension.

    Reuses the harness Stop payload's own ``session_id``/``cwd`` -- the
    suspension was reported to the main agent in that same session, so the
    row belongs to it. ``start_correlation`` is always ``paired``: the caller
    only reaches here after confirming an `agent_start` row exists for
    ``task_id`` (see ``_record_suspended_subagent_stops``).
    """
    cwd = payload.get("cwd", ".")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": payload.get("session_id", ""),
        "agent_type": agent_type,
        "agent_id": task_id,
        "project": Path(cwd).name,
        "event_type": "agent_stop",
        "tool_name": None,
        "summary": _SUSPENSION_SUMMARY[kind].format(agent_type=agent_type),
        "file_paths": [],
        "outcome": kind,
        "classification": None,
        "agent_type_source": agent_type_source,
        "start_correlation": CORRELATION_PAIRED,
        "stop_source": STOP_SOURCE_TRANSCRIPT_NOTIFICATION,
    }


def _stop_row_exists(obs_path: Path, agent_id: str) -> bool:
    """True if the WAL tail already carries an ``agent_stop`` for ``agent_id``.

    The idempotency check before writing a synthetic suspension stop: a
    second Stop reporting the same still-open notification must not
    double-write once an earlier Stop already recorded it.
    """
    for line in _tail_lines(obs_path):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if (
            isinstance(row, dict)
            and row.get("agent_id") == agent_id
            and row.get("event_type") == "agent_stop"
        ):
            return True
    return False


def _record_suspended_subagent_stops(obs_path: Path, payload: dict) -> None:
    """Backfill ``agent_stop`` rows for subagents the harness suspended silently.

    The harness reports a suspended background subagent to the MAIN agent as
    a `<task-notification>` in its own transcript instead of firing
    `SubagentStop` -- so the WAL would otherwise carry a start with no stop
    forever (see the module docstring's Known WAL anomalies section).
    ``transcript_path`` is read once per Stop, bounded to its tail; any
    failure to find, read, or parse it degrades to "nothing to backfill,"
    never a raise and never a delay beyond that bounded read.
    """
    transcript_path = str(payload.get("transcript_path") or "")
    if not transcript_path:
        return
    text = _read_transcript_tail(transcript_path)
    if not text:
        return
    for task_id, kind in find_suspended_tasks(text):
        agent_type, start_row_seen, _ = lookup_prior_agent(obs_path, task_id)
        if not start_row_seen or _stop_row_exists(obs_path, task_id):
            continue
        resolved_type, source = resolve_agent_type({}, "agent_stop", agent_type)
        append_observation(
            obs_path, build_suspension_stop(payload, task_id, kind, resolved_type, source)
        )


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
    if event_type == "session_stop":
        _record_suspended_subagent_stops(obs_path, payload)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
