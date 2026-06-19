"""Shared repo-root resolution for the finalize-chain scripts.

Consumer git hooks symlink into the installed-plugin cache, so a script's own
`Path(__file__).resolve()` follows the symlink to the *plugin*, not the
consumer repo. These helpers resolve the consumer root from an explicit
`--repo-root` or a cwd-based `git rev-parse --show-toplevel`, and detect the
plugin-cache path so writers can refuse to mutate shared plugin state.

Imported (not executed) by `finalize_adrs.py`, `finalize_tech_debt_ledger.py`,
`reconcile_ai_state.py`, `regenerate_adr_index.py`, and `check_squash_safety.py`
as a sibling module — `scripts/` is on `sys.path[0]` when any of them runs.
Each caller keeps its own one-line wrapper binding its `SCRIPT_DIR` and logger,
plus an `apply_repo_root` that rebinds its own module-level path constants.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


def git_toplevel_from_cwd() -> Path | None:
    """Return the repo root from the process CWD via git, or None.

    Runs `git rev-parse --show-toplevel` with NO `cwd` override. Git invokes
    the post-merge/post-commit/post-checkout hooks with the working directory
    at the consumer's worktree root, so this returns the consumer repo even
    when the calling script lives in a symlinked plugin cache.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return Path(out) if out else None


def resolve_repo_root(
    cli_repo_root: str | None,
    *,
    script_dir: Path,
    on_fallback: Callable[[Path], None] | None = None,
) -> Path:
    """Resolve the repo root: explicit `--repo-root` > git-root > script-relative.

    `script_dir` is the caller's `SCRIPT_DIR`; the script-relative fallback
    (`script_dir.parent`) is correct only when the script runs from a real
    checkout (e.g. Praxion self-hosting). For symlinked plugin hooks it resolves
    to the plugin, not the consumer -- the divergence that silently stranded
    draft ADRs -- so it is the last resort. `on_fallback` is invoked with that
    path when the fallback is used, letting the caller log via its own
    logger/print.
    """
    if cli_repo_root:
        return Path(cli_repo_root).resolve()
    git_root = git_toplevel_from_cwd()
    if git_root is not None:
        return git_root.resolve()
    fallback = script_dir.parent
    if on_fallback is not None:
        on_fallback(fallback)
    return fallback


def is_plugin_cache_path(root: Path) -> bool:
    """True if `root` looks like an installed-plugin cache location.

    Claude Code installs plugins under `.../plugins/cache/<owner>/<plugin>/<ver>`.
    The finalize writers must never operate there -- it would corrupt shared
    plugin state for every onboarded project (and hard-fail on a read-only
    cache). Resolving correctly (explicit `--repo-root` or git-root) never lands
    here; only the buggy script-relative fallback could, so this is a hard
    backstop.
    """
    posix = root.as_posix()
    return "/plugins/cache/" in posix or posix.endswith("/plugins/cache")
