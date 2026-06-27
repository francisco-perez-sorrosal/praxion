"""Shared utilities for Praxion hooks.

Provides the per-project opt-out check (``is_disabled``) and the observability
kill-switch flag consumed by the capture/telemetry hooks (``capture_memory``,
``capture_session``, ``send_event``, ``measure_context_surface``,
``notify_bg_session_state``).

Also provides the shared ``append_observation`` helper (with best-effort
rotation at ``OBSERVATIONS_MAX_BYTES``) used by all capture hooks.
"""

from __future__ import annotations

import fcntl
import json
import os
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
