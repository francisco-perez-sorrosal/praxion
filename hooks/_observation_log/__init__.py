"""The observation-log owner package.

This package is the *only* writer and the *only* reader of
``.ai-state/observations.jsonl``: every hook that appends a row, and every
script or hook that reads one back, does so through ``writer.py`` /
``reader.py`` respectively. Nothing outside this package should reference the
log's filename directly -- ``hooks/test_observation_log_private_reader.py``
enforces that as a totalising check.

Modules, in dependency order:

- ``modes``    -- ``Mode``/``ModeSource`` and the pure ``resolve_mode(env)``.
- ``registry`` -- ``EventClass``, the class-by-mode recording table, and the
  consumer contract every ``standard``-min reader is checked against.
- ``writer``   -- append-only, fail-open, mode-gated. Rotation and locking
  live here.
- ``reader``   -- stdlib-only (no ``fcntl``): segment discovery, streamed
  reads, and the row upcaster.

Deliberately no eager imports here -- a bare ``import _observation_log`` (or
``import hooks._observation_log``) must stay cheap; callers import the
specific submodule they need.
"""

from __future__ import annotations
