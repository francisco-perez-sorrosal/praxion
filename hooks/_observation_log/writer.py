"""Append-only, fail-open, mode-gated writer for the observation log.

Every function here is fail-open and never raises; each returns whether a row
was actually written. ``record``/``record_tool_call`` resolve the recording
mode from ``env`` and consult ``registry.records()`` live -- through the
``registry`` module object, not a locally bound copy of the function -- so a
test (or a future caller) that reconfigures the registry is always honored,
never shadowed by a stale reference. This is the fix for the standing
``record_gate_fire`` bug: the old per-writer switch check has no equivalent
here, because there is no per-writer check left to get wrong.

Hot-path import constraint: this module (and everything it imports) sits on
``capture_observations.py``'s per-tool-call path, so it must never import
``dataclasses``, runtime ``typing``, ``inspect``, ``tempfile``, ``subprocess``,
or ``urllib``.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from . import registry
from .location import locate
from .modes import resolve_mode
from .reader import LOG_FILENAME
from .registry import FILE_CHANGING_TOOLS, EventClass

# When the active observations.jsonl reaches this size, `append_observation`
# renames it to observations.jsonl.1 before writing the new row. Best-effort:
# OSError during rename is swallowed so the append always completes. Moved
# verbatim from `hooks/_hook_utils.py` -- tests monkeypatch it here now.
OBSERVATIONS_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

# Decision values a commit-gate script may report. Kept as a plain tuple (not
# an enum) because the six call sites are independent scripts translating
# their own pass/fail/return-code convention into this shared vocabulary.
GATE_FIRE_DECISIONS = ("pass", "warn", "block")


def _rotate_if_needed(obs_path: Path) -> None:
    """Rename obs_path to obs_path.1 when it exceeds OBSERVATIONS_MAX_BYTES.

    Must be called inside the fcntl-locked section of append_observation so
    concurrent hook invocations cannot double-rotate. Best-effort: any
    OSError is silently swallowed -- the subsequent append still runs.
    """
    try:
        if obs_path.exists() and obs_path.stat().st_size >= OBSERVATIONS_MAX_BYTES:
            os.replace(obs_path, Path(str(obs_path) + ".1"))
    except OSError:
        pass


def append_observation(obs_path: Path, observation: dict) -> None:
    """Append a single observation to the JSONL file with exclusive locking.

    Acquires the fcntl lock at obs_path.parent / "observations.lock", calls
    _rotate_if_needed inside the lock, then appends the serialized JSONL line
    and flushes. Never raises -- callers already wrap main() in except Exception.
    """
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = obs_path.parent / "observations.lock"
    lock_path.touch(exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            _rotate_if_needed(obs_path)
            with open(obs_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(observation, separators=(",", ":")) + "\n")
                f.flush()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def record(
    ai_state_dir: Path,
    event_class: EventClass,
    row: dict,
    *,
    env: Mapping[str, str] = os.environ,
) -> bool:
    """Append ``row`` under ``event_class`` when the resolved mode allows it.

    Every appended row is stamped with ``log_mode``; a ``SESSION_START`` row
    additionally carries ``log_mode_source``, so a reader can tell "the
    fleet default" apart from "this project opted in explicitly" apart from
    "a typo fell back to full" for the one row per session that needs to say
    so. ``row`` itself is never mutated -- the stamped copy is what gets
    appended.

    Fail-open: any exception degrades to "not written" rather than
    propagating. Returns whether the row was actually appended.
    """
    try:
        mode, source = resolve_mode(env)
        if not registry.records(event_class, mode):
            return False
        stamped = {**row, "log_mode": mode.value}
        if event_class is EventClass.SESSION_START:
            stamped["log_mode_source"] = source.value
        append_observation(ai_state_dir / LOG_FILENAME, stamped)
        return True
    except Exception:
        return False


def _classify(row: dict, *, marker_present: bool) -> EventClass:
    """Pure tool-call classification: (row, marker_present) -> EventClass.

    A ``Skill`` call is always ``SKILL_ACTIVATION``; a file-changing tool is
    always ``TOOL_FILE_CHANGE``, regardless of the marker. Otherwise,
    ``marker_present`` being False means this is the first recorded call for
    this (log, subagent) pair -- ``TOOL_FIRST_OF_SUBAGENT`` -- and every
    later call from that same subagent, or any main-agent call that is
    neither Skill nor file-changing, is ``TOOL_OTHER``. The main agent is
    never "first of a subagent" -- its caller passes ``marker_present=True``
    unconditionally, since that concept does not apply to it.
    """
    if row.get("tool_name") == "Skill":
        return EventClass.SKILL_ACTIVATION
    if row.get("tool_name") in FILE_CHANGING_TOOLS:
        return EventClass.TOOL_FILE_CHANGE
    if not marker_present:
        return EventClass.TOOL_FIRST_OF_SUBAGENT
    return EventClass.TOOL_OTHER


# Prefix for the first-call marker's filename -- an empty file per (log
# directory identity, agent_id), see `_first_call_marker_path`.
_MARKER_PREFIX = "praxion-observation-log-first-call-"

# The classes whose row is a `tool_use` row -- the only rows that may set the
# first-call marker.
_MARKER_CONSUMING_CLASSES = frozenset(
    {EventClass.TOOL_FIRST_OF_SUBAGENT, EventClass.TOOL_FILE_CHANGE}
)


def _marker_dir(env: Mapping[str, str]) -> Path:
    """The user temp directory, resolved without importing ``tempfile`` --
    this module sits on the per-tool-call hot path, which must not import it.
    """
    for key in ("TMPDIR", "TEMP", "TMP"):
        value = env.get(key)
        if value:
            return Path(value)
    return Path("/tmp")


def _first_call_marker_path(ai_state_dir: Path, agent_id: str, env: Mapping[str, str]) -> Path:
    """The marker file for one (log directory, subagent) pair.

    Keyed by the log directory's device+inode, not its path, so two
    worktrees -- or the same project moved or renamed -- never collide or
    alias onto the same marker.
    """
    stat = ai_state_dir.stat()
    key = f"{stat.st_dev}:{stat.st_ino}:{agent_id}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return _marker_dir(env) / f"{_MARKER_PREFIX}{digest}"


def _first_call_marker_present(
    ai_state_dir: Path, agent_id: str, env: Mapping[str, str]
) -> tuple[bool, Path | None]:
    """Whether this subagent's first-call marker already exists, and the
    path to create it at.

    Any failure to resolve or read the marker -- an unresolvable temp
    directory, a ``.ai-state`` directory ``stat`` cannot reach -- degrades to
    "not present, no path": biased toward the more-inclusive
    ``TOOL_FIRST_OF_SUBAGENT`` classification (recorded in every mode) over
    the pickier ``TOOL_OTHER`` (dropped in `standard`), so an agent that did
    something is never read as one that did nothing.
    """
    try:
        marker_path = _first_call_marker_path(ai_state_dir, agent_id, env)
        return marker_path.exists(), marker_path
    except OSError:
        return False, None


def _create_first_call_marker(marker_path: Path) -> None:
    """Create the marker, ignoring a losing race and any other OSError.

    Called only after the row it marks has already been appended
    (append-then-mark): a crash, a race between two "first" calls for the
    same subagent, or an unwritable marker directory can only ever cost a
    duplicate ``TOOL_FIRST_OF_SUBAGENT`` classification on this subagent's
    next call, never a missing row.
    """
    try:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(str(marker_path), os.O_CREAT | os.O_EXCL, 0o600))
    except OSError:
        pass


def record_tool_call(
    ai_state_dir: Path,
    row: dict,
    *,
    is_subagent: bool,
    env: Mapping[str, str] = os.environ,
) -> bool:
    """Classify one tool-call row and record it if the registry allows it.

    A subagent's marker is checked before the row is classified, and created
    -- only if this call turned out to be the first -- after the row is
    appended, never before. That ordering is what makes the marker an
    at-least-once signal: whatever goes wrong with the marker, the row it
    would have gated is already written.

    Fail-open like every other function here: any exception degrades to
    "not written" rather than propagating.
    """
    try:
        if is_subagent:
            marker_present, marker_path = _first_call_marker_present(
                ai_state_dir, str(row.get("agent_id", "")), env
            )
        else:
            marker_present, marker_path = True, None

        event_class = _classify(row, marker_present=marker_present)
        written = record(ai_state_dir, event_class, row, env=env)
        # Only a `tool_use` row may consume the marker: a Skill call writes a
        # `skill_activation` row, which the lifecycle check does not count as
        # evidence that the agent ran a tool.
        if (
            written
            and marker_path is not None
            and not marker_present
            and event_class in _MARKER_CONSUMING_CLASSES
        ):
            _create_first_call_marker(marker_path)
        return written
    except Exception:
        return False


def record_gate_fire(
    hook: str,
    decision: str,
    reason: str = "",
    *,
    session_id: str = "",
    project_dir: Path | None = None,
) -> None:
    """Append a `gate_fire` observation recording one commit-gate's verdict.

    Moved from `hooks/_hook_utils.py`, now mode-gated through `record()`
    instead of calling `append_observation` directly -- this is the fix for
    the standing bug where a gate's row leaked with the kill switch set: the
    old function had no mode check of its own at all.

    ``hook`` names the calling gate script (e.g. "check_token_ratchet"),
    never a path. ``decision`` is one of ``GATE_FIRE_DECISIONS``. The row
    carries the value under both ``hook`` (the field
    `hooks/capture_session.py`'s Stop-time rollup already groups
    `gate_fire` rows by) and ``tool_name`` (the field every other
    observation event carries) -- both keys, one value.

    ``session_id`` is best-effort: pass it when the caller already parsed a
    hook payload carrying one. Resolves the target project through `locate`,
    starting from ``project_dir`` or, when no parsed payload `cwd` is in
    scope, the process's own working directory -- either may sit anywhere
    below the project root. No project serving it means no row.
    """
    try:
        location = locate(str(project_dir or os.getcwd()))
        if location is None:
            return
        observation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event_type": "gate_fire",
            "hook": hook,
            "tool_name": hook,
            # The vocabulary is enforced here, fail-open: an unrecognised
            # decision at a call site is recorded as "pass" with the raw
            # value kept in the reason, never as a novel outcome.
            "outcome": decision if decision in GATE_FIRE_DECISIONS else "pass",
            "reason": (
                reason
                if decision in GATE_FIRE_DECISIONS
                else f"unrecognised decision {decision!r}: {reason}"
            ),
        }
        record(location.state_dir, EventClass.GATE_FIRE, observation)
    except Exception:
        pass
