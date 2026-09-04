"""Shared CLI-resolution + subprocess plumbing for the sidecar hooks.

`inject_sidecar_banner.py` and `sidecar_autocommit.py` both shell out to the
`praxion-sidecar` CLI and both need the exact same three steps to do it
honestly: find the plugin root, find the CLI inside it, and run it against
the *payload's* cwd -- not the hook process's own cwd, which can differ from
the session's project when Claude Code launches hooks from an unrelated
working directory (the observed symptom: a banner naming the wrong
project's sidecar path). Folded into one module so the two hooks cannot
drift on this contract.

Also resolves the interpreter to run the CLI with: `sys.executable` (the
interpreter that is running the *hook* itself) rather than a bare
`[str(cli_path), *args]` relying on the CLI's own `#!/usr/bin/env python3`
shebang, which is a different interpreter whenever the shebang's `python3`
lacks PyYAML -- the hook always has a working interpreter, since it
is running right now.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

CLI_NAME = "praxion-sidecar"


def resolve_plugin_root(hook_file: str) -> Path:
    """``CLAUDE_PLUGIN_ROOT`` env var, else the calling hook's own plugin
    root (``hook_file``'s grandparent -- ``hooks/<this file>`` -> plugin root)."""
    plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root_str:
        return Path(plugin_root_str)
    return Path(hook_file).resolve().parent.parent


def resolve_cli(plugin_root: Path) -> Path | None:
    cli_path = plugin_root / "scripts" / CLI_NAME
    return cli_path if cli_path.is_file() else None


def run_cli(
    cli_path: Path, args: list[str], *, cwd: Path, timeout: float
) -> subprocess.CompletedProcess | None:
    """Run the sidecar CLI against `cwd` with this process's own interpreter;
    None on timeout or launch failure (fail-open)."""
    try:
        return subprocess.run(
            [sys.executable, str(cli_path), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
