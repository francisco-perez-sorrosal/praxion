#!/usr/bin/env python3
"""SessionStart hook: orient the agent when this project's state lives in a
sidecar, self-healing the mount on the way.

Fires **only** when the project resolves to `SidecarOwned` or `NotYetLinked`
placement (`_state_repo.resolve_placement`) -- silent, zero-subprocess, for
the overwhelming majority of sessions (in-repo projects). It self-heals the
mount first (`praxion-sidecar link --quiet` -- this also materializes a
missing mount and runs the convergence engine in the main checkout), then
reads `praxion-sidecar status --json` and renders the banner from it.

`NotYetLinked` is a session opened in a worktree created moments ago: it has
no `.ai-state` of its own yet, so the heal is the whole point of the visit.
The placement is re-resolved after `link` and the banner is rendered only if
the checkout is now `SidecarOwned` -- a heal that did not take reports
nothing rather than describing a mount that is not there.

Behavior contract:
- **Fail-open**: any internal error (subprocess failure, JSON decode, path
  resolution) exits 0 with no output -- a SessionStart hook must never wedge
  session creation. This extends to the self-heal call itself: `link`'s own
  exit code stays honest (1 on an aborted merge-back conflict), but this hook
  swallows that non-zero, surfaces the conflict as banner text and a stderr
  log line, and still exits 0 -- a conflict during self-heal must never
  present as a broken session start.
- **Opt-out**: ``PRAXION_DISABLE_SIDECAR_BANNER=1`` disables the hook
  entirely (mirrors the ``PRAXION_DISABLE_*`` convention).
- **CLI resolution mirrors ``heal_hook_chain.py``**: ``CLAUDE_PLUGIN_ROOT``
  env var, else this hook's own plugin root (``Path(__file__).parent.parent``),
  then ``<plugin_root>/scripts/praxion-sidecar``. No ``PATH`` fallback --
  same as ``heal_hook_chain._resolve_plugin_root()``/``_run_heal()``. An
  unresolvable CLI is silent, not an error.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

# Locate the sibling `scripts/` directory to import resolve_placement
# in-process -- plugin-internal code location, unrelated to resolving the
# *consumer* repo root below, which always comes from the hook payload's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _state_repo import NotYetLinked, SidecarOwned, resolve_placement  # noqa: E402

DISABLE_FLAG = "PRAXION_DISABLE_SIDECAR_BANNER"
HEADING = "## Praxion sidecar (auto-injected)"
CLI_NAME = "praxion-sidecar"
LINK_TIMEOUT_SECONDS = 10
STATUS_TIMEOUT_SECONDS = 3

# `status --json`'s `failed_checks` carries one entry per offending row
# (`_sidecar_checks.py`'s `_rows_state_unmerged`/`_rows_state_eligible`), so
# counting occurrences of these two ids is exactly the convergence-line count.
_CONVERGENCE_CHECK_IDS = frozenset({"state-unmerged", "state-eligible"})

_AUTOCOMMIT_PHRASES = {
    "on-finalize-and-stop": "on finalize + stop",
    "on-finalize": "on finalize",
    "manual": "manual",
}


def _resolve_plugin_root() -> Path:
    plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root_str:
        return Path(plugin_root_str)
    return Path(__file__).resolve().parent.parent


def _resolve_cli(plugin_root: Path) -> Path | None:
    cli_path = plugin_root / "scripts" / CLI_NAME
    return cli_path if cli_path.is_file() else None


def _run_cli(
    cli_path: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess | None:
    """Run the sidecar CLI; None on timeout or launch failure (fail-open)."""
    try:
        return subprocess.run(
            [str(cli_path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _tilde_path(raw: str) -> str:
    """Abbreviate `raw` relative to `$HOME` as `~/...`, else return it as-is."""
    if not raw:
        return raw
    home_str = os.environ.get("HOME")
    if not home_str:
        return raw
    path, home = Path(raw), Path(home_str)
    try:
        if path.is_relative_to(home):
            return f"~/{path.relative_to(home)}"
    except (OSError, ValueError):
        pass
    return raw


def _render_banner(status: dict) -> str:
    """Render the 7-line healthy/unhealthy banner body, plus the convergence
    line when `status`'s `failed_checks` names any unmerged/eligible branch."""
    sidecar = status.get("sidecar") or {}
    sidecar_path = _tilde_path(sidecar.get("root", ""))
    autocommit = status.get("autocommit", "manual")
    autocommit_phrase = _AUTOCOMMIT_PHRASES.get(autocommit, autocommit)
    failed_checks = status.get("failed_checks") or []
    healthy = status.get("healthy", True)

    lines = [
        HEADING,
        "",
        "Project intelligence for this repo lives **outside it**, in",
        f"`{sidecar_path}` (git-tracked, autocommit {autocommit_phrase}).",
        "`.ai-state/`, `CLAUDE.local.md` and `.claude/settings.local.json` are symlinks into that",
        "sidecar, excluded via `.git/info/exclude` — **project commits never include them**, and",
    ]
    if healthy:
        lines.append(
            "`git add` through the symlink fails loudly rather than leaking. "
            "`docs/architecture.md` is"
        )
        lines.append(
            "shared in the repo: cite ADRs by **id text** (`dec-355`), never by `.ai-state/` path."
        )
    else:
        lines.append("`git add` through the symlink fails loudly rather than leaking.")
        lines.append(
            f"⚠️ `praxion-sidecar doctor` reports {len(failed_checks)} failed checks — "
            "run it before writing state."
        )

    convergence_count = sum(1 for check_id in failed_checks if check_id in _CONVERGENCE_CHECK_IDS)
    if convergence_count:
        lines.append("")
        lines.append(
            f"{convergence_count} state branch(es) awaiting merge-back — run: praxion-sidecar doctor"
        )

    return "\n".join(lines)


def _conflict_note(stderr_text: str) -> str:
    detail = stderr_text.strip() or "praxion-sidecar link exited nonzero during self-heal"
    return f"⚠️ self-heal: {detail}"


def _emit(context: str) -> None:
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        )
    )


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

    placement = resolve_placement(cwd)
    if not isinstance(placement, (SidecarOwned, NotYetLinked)):
        return  # InRepo/Dangling/Foreign -- no subprocess, no output

    cli_path = _resolve_cli(_resolve_plugin_root())
    if cli_path is None:
        return  # unresolvable CLI -- silent, not an error

    # Self-heal BEFORE reading status (materializes a missing mount, converges
    # unmerged state branches). Its exit code stays honest -- 1 on an aborted
    # conflict -- but that never fails this hook; see module docstring.
    link_result = _run_cli(cli_path, ["link", "--quiet"], timeout=LINK_TIMEOUT_SECONDS)

    if isinstance(placement, NotYetLinked) and not isinstance(resolve_placement(cwd), SidecarOwned):
        return  # the heal did not take -- nothing truthful left to render

    status_result = _run_cli(cli_path, ["status", "--json"], timeout=STATUS_TIMEOUT_SECONDS)
    if status_result is None or status_result.returncode != 0:
        return
    try:
        status = json.loads(status_result.stdout)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(status, dict):
        return

    banner = _render_banner(status)
    if link_result is not None and link_result.returncode != 0:
        note = _conflict_note(link_result.stderr)
        banner = f"{banner}\n\n{note}"
        print(note, file=sys.stderr)  # never swallowed silently -- also logged

    _emit(banner)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block session creation
