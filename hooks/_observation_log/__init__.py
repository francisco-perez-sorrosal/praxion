"""The observation-log owner package.

This package is the *only* writer and the *only* reader of
``.ai-state/observations.jsonl``: every hook that appends a row, and every
script or hook that reads one back, does so through ``writer.py`` /
``reader.py`` respectively. Outside a short allowlist of whole-file tools
(merge drivers, reconciliation), no module names the log's filename directly,
and every module importing the reader is a declared consumer in
``registry.CONSUMERS`` -- ``hooks/test_observation_log_private_reader.py``
enforces both.

Modules, in dependency order:

- ``modes``      -- ``Mode``/``ModeSource`` and the pure ``resolve_mode(env)``.
- ``registry``   -- ``EventClass``, the class-by-mode recording table, and the
  consumer contract every ``standard``-min reader is checked against.
- ``retention``  -- the retention policy (size cap, archive count, history
  target) and the only builder and parser of an archive's name.
- ``location``   -- ``locate(cwd)``: which ``.ai-state/`` and which ``project`` a
  working directory belongs to; the one answer every writer records under.
- ``reader``     -- stdlib-only (no ``fcntl``): segment discovery across every
  archive, streamed and raw reads, row identity and row time, and the row
  upcaster.
- ``writer``     -- append-only, fail-open, mode-gated. Rotation (the archive
  shift) and locking live here, and so does the batched append a copier uses.
- ``checkouts``  -- a repository's main working tree and linked worktrees, from
  ``git worktree list``. Runs git: never on the hook path.
- ``merge_in``   -- copy a worktree's log rows into the main log, skipping rows
  it already holds. A copy path, not a recording path.

Deliberately no eager imports here -- a bare ``import _observation_log`` (or
``import hooks._observation_log``) must stay cheap; callers import the
specific submodule they need.
"""

from __future__ import annotations
