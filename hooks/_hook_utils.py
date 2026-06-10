"""Shared utilities for Praxion hooks.

Provides the per-project opt-out check (``is_disabled``) and the observability
kill-switch flag consumed by the capture/telemetry hooks (``capture_memory``,
``capture_session``, ``send_event``, ``measure_context_surface``,
``notify_bg_session_state``).
"""

from __future__ import annotations

import os

# -- Per-project opt-out flag --------------------------------------------------
# Read from Claude Code's per-project settings.json `env` block. Set to "1",
# "true", or "yes" (case-insensitive) to disable the observability hooks for
# the project. Absence of the flag preserves default behavior.

DISABLE_OBSERVABILITY = "PRAXION_DISABLE_OBSERVABILITY"

_TRUTHY = frozenset({"1", "true", "yes"})


def is_disabled(flag_name: str) -> bool:
    """Return True if the named opt-out env var is set to a truthy value."""
    return os.environ.get(flag_name, "").strip().lower() in _TRUTHY
