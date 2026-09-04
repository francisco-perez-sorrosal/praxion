#!/usr/bin/env python3
"""Stop hook: autocommit a dirty sidecar mount when policy allows it.

Fast-exits on one `lstat` when `.ai-state` is not a symlink -- the
overwhelming majority of sessions -- with zero subprocess calls. On a
symlinked (potentially `SidecarOwned`) project it reads `praxion-sidecar
status --json`'s `sidecar.dirty_files` and `autocommit` fields (the same
public JSON contract `inject_sidecar_banner.py` consumes -- git plumbing
stays behind the CLI boundary) and, when the mount is dirty and policy is
`on-finalize-and-stop`, calls `praxion-sidecar commit --quiet`.

Behavior contract:
- **Fast-exit, no subprocess**: a plain (non-symlink) `.ai-state/` costs one
  `lstat` and nothing else.
- **Fail-open, always exits 0**: a Stop hook must never fail the session --
  the commit call's own exit code is ignored.
- **Opt-out**: ``PRAXION_DISABLE_SIDECAR_AUTOCOMMIT=1`` disables the hook
  entirely (mirrors the ``PRAXION_DISABLE_*`` convention).
- **CLI resolution + invocation**: shared with ``inject_sidecar_banner.py``
  via ``_sidecar_hook_common`` -- ``CLAUDE_PLUGIN_ROOT`` env var, else this
  hook's own plugin root, then ``<plugin_root>/scripts/praxion-sidecar``, run
  with this process's own interpreter against the *payload's* cwd. No ``PATH`` fallback.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _hook_utils import is_disabled
from _sidecar_hook_common import resolve_cli, resolve_plugin_root, run_cli

DISABLE_FLAG = "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT"
STATUS_TIMEOUT_SECONDS = 3
COMMIT_TIMEOUT_SECONDS = 10
STATE_DIR_NAME = ".ai-state"
AUTOCOMMIT_POLICY_ON_STOP = "on-finalize-and-stop"


def _is_symlinked_state_dir(cwd: Path) -> bool:
    """One `lstat`, zero subprocess calls -- the whole fast-exit gate."""
    try:
        return (cwd / STATE_DIR_NAME).is_symlink()
    except OSError:
        return False


def main() -> None:
    # Drain stdin even though we may not need it -- the hook framework can
    # SIGPIPE on its write end if the pipe is left unread.
    raw = sys.stdin.read()
    if is_disabled(DISABLE_FLAG):
        return
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())

    if not _is_symlinked_state_dir(cwd):
        return  # fast-exit: not a candidate for sidecar autocommit

    cli_path = resolve_cli(resolve_plugin_root(__file__))
    if cli_path is None:
        return  # unresolvable CLI -- silent, not an error

    status_result = run_cli(cli_path, ["status", "--json"], cwd=cwd, timeout=STATUS_TIMEOUT_SECONDS)
    if status_result is None or status_result.returncode != 0:
        return
    try:
        status = json.loads(status_result.stdout)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(status, dict):
        return
    if status.get("placement") != "sidecar":
        return  # a re-derived status disagreeing with the fast-exit gate above

    sidecar = status.get("sidecar") or {}
    dirty_files = sidecar.get("dirty_files", 0)
    autocommit = status.get("autocommit")
    if autocommit != AUTOCOMMIT_POLICY_ON_STOP or not dirty_files:
        return

    # Fire-and-forget: a commit refusal or failure must never fail the
    # session -- the exit code is deliberately unread beyond this call.
    run_cli(cli_path, ["commit", "--quiet"], cwd=cwd, timeout=COMMIT_TIMEOUT_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block session end
