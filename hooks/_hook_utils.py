"""Shared utilities for Praxion hooks.

Provides the per-project opt-out check (``is_disabled``) and the observability
kill-switch flag consumed by the capture/telemetry hooks (``capture_observations``,
``capture_session``, ``send_event``, ``measure_context_surface``,
``notify_bg_session_state``).

Also provides the shared ``append_observation`` helper (with best-effort
rotation at ``OBSERVATIONS_MAX_BYTES``) used by all capture hooks, and
``record_gate_fire`` -- the same append, specialized for commit-gate scripts
recording their own pass/warn/block verdict.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# -- Per-project opt-out flag --------------------------------------------------
# Read from Claude Code's per-project settings.json `env` block. Set to "1",
# "true", or "yes" (case-insensitive) to disable the observability hooks for
# the project. Absence of the flag preserves default behavior.

DISABLE_OBSERVABILITY = "PRAXION_DISABLE_OBSERVABILITY"

_TRUTHY = frozenset({"1", "true", "yes"})

# -- Observability WAL size threshold for rotation ----------------------------
# When the active observations.jsonl reaches this size, append_observation
# renames it to observations.jsonl.1 before writing the new row. Best-effort:
# OSError during rename is swallowed so the append always completes.
# Tests monkeypatch this constant to exercise rotation without real 10 MiB writes.

OBSERVATIONS_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB


def is_disabled(flag_name: str) -> bool:
    """Return True if the named opt-out env var is set to a truthy value."""
    return os.environ.get(flag_name, "").strip().lower() in _TRUTHY


def _rotate_if_needed(obs_path: Path) -> None:
    """Rename obs_path to obs_path.1 when the file exceeds OBSERVATIONS_MAX_BYTES.

    Must be called inside the fcntl-locked section of append_observation so
    concurrent hook invocations cannot double-rotate. Best-effort: any OSError
    (e.g., the destination already exists on a platform that does not support
    atomic replace) is silently swallowed — the subsequent append still runs.
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
    and flushes. Never raises — callers already wrap main() in except Exception.
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


# -- gate_fire observations ----------------------------------------------------
# Decision values a commit-gate script may report. Kept as a plain tuple (not
# an enum) because the six call sites are independent scripts translating
# their own pass/fail/return-code convention into this shared vocabulary --
# see each gate's own comment at its record_gate_fire() call site.
GATE_FIRE_DECISIONS = ("pass", "warn", "block")


def record_gate_fire(
    hook: str,
    decision: str,
    reason: str = "",
    *,
    session_id: str = "",
) -> None:
    """Append a `gate_fire` observation recording one commit-gate's verdict.

    Fail-open, mirroring every other writer in this module: any exception is
    swallowed here so a gate's own instrumentation can never affect the
    gate's exit code or its stdout/stderr output. Callers additionally wrap
    their own call site in try/except (belt-and-suspenders, per the
    behavioral requirement that a helper defect must never reach a gate's
    exit path).

    ``hook`` names the calling gate script (e.g. "check_token_ratchet"),
    never a path. ``decision`` is one of ``GATE_FIRE_DECISIONS``. The row
    carries the value under both ``hook`` (the field
    `hooks/capture_session.py`'s Stop-time rollup already groups
    `gate_fire` rows by) and ``tool_name`` (the field every other
    observation event carries) -- both keys, one value, so this row is
    consistent with the pre-existing rollup contract and the general
    envelope shape at once.

    ``session_id`` is best-effort: pass it when the caller already parsed a
    hook payload carrying one, so the Stop-time per-session summary can
    attribute this row to the session that triggered it. A caller that
    cannot cheaply reach a session id (e.g. a gate invoked without ever
    reading its own stdin payload) still gets its row into the raw WAL --
    just outside that session's rollup.

    Resolves the target project's `.ai-state/` the way every ambient-invoked
    hook in this codebase falls back when no parsed payload `cwd` is in
    scope: the process's own working directory. Gate scripts run with the
    target project as the process cwd (git invokes `PreToolUse` hooks that
    way), so this is not a degraded case here -- it is the normal one.
    """
    try:
        ai_state_dir = Path(os.getcwd()) / ".ai-state"
        if not ai_state_dir.exists():
            return
        observation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event_type": "gate_fire",
            "hook": hook,
            "tool_name": hook,
            "outcome": decision,
            "reason": reason,
        }
        append_observation(ai_state_dir / "observations.jsonl", observation)
    except Exception:
        pass
