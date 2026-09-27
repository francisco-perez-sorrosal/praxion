"""Shared utilities for Praxion hooks.

Provides the per-project opt-out check (``is_disabled``) and the observability
kill-switch flag consumed by the capture/telemetry hooks (``capture_observations``,
``capture_session``, ``send_event``, ``measure_context_surface``,
``notify_bg_session_state``).

Also provides ``record_gate_fire`` -- a thin forwarding wrapper for
commit-gate scripts recording their own pass/warn/block verdict. The row
shape, mode gating, and the append/rotate/lock machinery now live in
``hooks/_observation_log/writer.py``; this module keeps the same public
name and signature so no gate call site needs to change.
"""

from __future__ import annotations

import os
from pathlib import Path

# -- Per-project opt-out flag --------------------------------------------------
# Read from Claude Code's per-project settings.json `env` block. Set to "1",
# "true", or "yes" (case-insensitive) to disable the observability hooks for
# the project. Absence of the flag preserves default behavior.

DISABLE_OBSERVABILITY = "PRAXION_DISABLE_OBSERVABILITY"

# Narrower: silences only send_event.py's chronograph POSTs while the local
# observations log keeps being written -- what an isolated sandbox needs when a
# hook under test reads that log.
DISABLE_EVENT_POSTING = "PRAXION_DISABLE_EVENT_POSTING"

_TRUTHY = frozenset({"1", "true", "yes"})


def is_disabled(flag_name: str) -> bool:
    """Return True if the named opt-out env var is set to a truthy value."""
    return os.environ.get(flag_name, "").strip().lower() in _TRUTHY


def record_gate_fire(
    hook: str,
    decision: str,
    reason: str = "",
    *,
    session_id: str = "",
    project_dir: Path | None = None,
) -> None:
    """Forward one commit-gate verdict to the observation-log writer.

    See ``hooks/_observation_log/writer.py::record_gate_fire`` for the row
    shape and mode gating -- this wrapper exists only so gate call sites
    (``from _hook_utils import record_gate_fire``) never need to change.
    The writer is imported *inside* this function, not at module level, so a
    bare importer of this module (``send_event.py``, which only needs
    ``is_disabled``) never eagerly loads the observation-log package.

    Fail-open, mirroring the writer: any exception here (including the
    import itself) is swallowed so a gate's own instrumentation can never
    affect the gate's exit code or its stdout/stderr output.
    """
    try:
        from _observation_log import writer

        writer.record_gate_fire(
            hook, decision, reason, session_id=session_id, project_dir=project_dir
        )
    except Exception:
        pass
