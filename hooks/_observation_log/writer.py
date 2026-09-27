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
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from . import registry
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

    Fail-open: any exception degrades to "not written" rather than
    propagating. Returns whether the row was actually appended.
    """
    try:
        mode, _source = resolve_mode(env)
        if not registry.records(event_class, mode):
            return False
        append_observation(ai_state_dir / LOG_FILENAME, row)
        return True
    except Exception:
        return False


def _classify(row: dict) -> EventClass:
    """Coarse tool-call classification.

    Skill calls and file-changing tool calls are already distinguishable and
    the registry records them identically to every other tool call for now
    (`full` and `standard` both record every class), so this coarseness has
    no observable effect yet. The first-of-subagent distinction needs the
    per-subagent first-call marker file, which `standard` mode introduces.
    """
    if row.get("tool_name") == "Skill":
        return EventClass.SKILL_ACTIVATION
    if row.get("tool_name") in FILE_CHANGING_TOOLS:
        return EventClass.TOOL_FILE_CHANGE
    return EventClass.TOOL_OTHER


def record_tool_call(
    ai_state_dir: Path,
    row: dict,
    *,
    is_subagent: bool,
    env: Mapping[str, str] = os.environ,
) -> bool:
    """Classify one tool-call row and record it if the registry allows it.

    ``is_subagent`` is accepted now to match the stable call signature but is
    not yet consulted -- the first-of-subagent marker and its classification
    branch land in a later step, once `standard` narrows what it keeps.
    """
    return record(ai_state_dir, _classify(row), row, env=env)


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
    hook payload carrying one. Resolves the target project's `.ai-state/` the
    way every ambient-invoked hook in this codebase falls back when no parsed
    payload `cwd` is in scope: the process's own working directory. A caller
    that already resolved the repo root passes ``project_dir``.
    """
    try:
        ai_state_dir = (project_dir or Path(os.getcwd())) / ".ai-state"
        if not ai_state_dir.exists():
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
        record(ai_state_dir, EventClass.GATE_FIRE, observation)
    except Exception:
        pass
