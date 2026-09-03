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
- **CLI resolution + invocation**: shared with ``sidecar_autocommit.py`` via
  ``_sidecar_hook_common`` -- ``CLAUDE_PLUGIN_ROOT`` env var, else this
  hook's own plugin root, then ``<plugin_root>/scripts/praxion-sidecar``, run
  with this process's own interpreter against the *payload's* cwd (IF-09/
  IF-17). No ``PATH`` fallback. An unresolvable CLI is silent, not an error.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _hook_utils import is_disabled
from _sidecar_hook_common import resolve_cli, resolve_plugin_root, run_cli

# Locate the sibling `scripts/` directory to import resolve_placement
# in-process -- plugin-internal code location, unrelated to resolving the
# *consumer* repo root below, which always comes from the hook payload's cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _state_repo import NotYetLinked, SidecarOwned, resolve_placement  # noqa: E402

DISABLE_FLAG = "PRAXION_DISABLE_SIDECAR_BANNER"
HEADING = "## Praxion sidecar (auto-injected)"
LINK_TIMEOUT_SECONDS = 10
STATUS_TIMEOUT_SECONDS = 3

# `status --json`'s `failed_checks` carries one entry per offending row
# (`_sidecar_checks.py`'s `_rows_state_unmerged`/`_rows_state_eligible`), each
# suffixed `:<branch>` by `_sidecar_inputs._failed_check_ids` -- e.g.
# `"state-unmerged:wt/x"` -- so the branch name is recoverable without a
# second `doctor` call.
_CONVERGENCE_CHECK_IDS = frozenset({"state-unmerged", "state-eligible"})
_MAX_NAMED_BRANCHES = 3

_AUTOCOMMIT_PHRASES = {
    "on-finalize-and-stop": "on finalize + stop",
    "on-finalize": "on finalize",
    "manual": "manual",
}


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


def _doctor_summary_phrase(counts: dict) -> str:
    """`{N} failed, {M} warnings` -- omits either half when it is zero, so a
    warnings-only report never claims a phantom failure (F-4)."""
    failed = int(counts.get("fail", 0))
    warnings = int(counts.get("warn", 0))
    parts = [f"{failed} failed"] if failed else []
    if warnings:
        parts.append(f"{warnings} warnings")
    return ", ".join(parts) if parts else "0 failed"


def _convergence_branches(failed_checks: list[str]) -> list[str]:
    """Branch names from `state-unmerged:<branch>` / `state-eligible:<branch>`
    entries, in `failed_checks` order (F-3 -- name the branches, not just a count)."""
    branches = []
    for check_id in failed_checks:
        check_type, sep, branch = check_id.partition(":")
        if sep and check_type in _CONVERGENCE_CHECK_IDS:
            branches.append(branch)
    return branches


def _convergence_line(branches: list[str]) -> str:
    shown = branches[:_MAX_NAMED_BRANCHES]
    remainder = len(branches) - len(shown)
    names = ", ".join(shown)
    if remainder:
        names = f"{names}, and {remainder} more"
    return f"State branch(es) awaiting merge-back: {names}"


def _has_share_row(paths: list) -> bool:
    """True iff `status`'s `paths[]` names at least one `intent: share` row --
    only then does the `docs/architecture.md` sentence describe this project."""
    return any(isinstance(row, dict) and row.get("intent") == "share" for row in paths)


def _render_banner(status: dict) -> str:
    """Render the healthy/unhealthy banner body, plus the convergence
    line when `status`'s `failed_checks` names any unmerged/eligible branch."""
    sidecar = status.get("sidecar") or {}
    sidecar_path = _tilde_path(sidecar.get("root", ""))
    autocommit = status.get("autocommit", "manual")
    autocommit_phrase = _AUTOCOMMIT_PHRASES.get(autocommit, autocommit)
    failed_checks = status.get("failed_checks") or []
    counts = status.get("counts") or {}
    healthy = status.get("healthy", True)

    lines = [
        HEADING,
        "",
        "Project intelligence for this repo lives **outside it**, in",
        f"`{sidecar_path}` (git-tracked, autocommit {autocommit_phrase}).",
        "`.ai-state/`, `CLAUDE.local.md` and `.claude/settings.local.json` are symlinks into that",
        "sidecar, excluded via `.git/info/exclude` — **project commits never include them**.",
    ]
    if healthy:
        if _has_share_row(status.get("paths") or []):
            lines.append(
                "`docs/architecture.md` is shared in the repo: cite ADRs by **id text** "
                "(`dec-NNN`), never by `.ai-state/` path."
            )
    else:
        lines.append(
            f"⚠️ `praxion-sidecar doctor` reports {_doctor_summary_phrase(counts)} — "
            "run it before writing state."
        )

    lines.append(
        "File shadows (`CLAUDE.local.md`, a shadowed `CLAUDE.md`, `.claude/settings.local.json`) load "
        "through their links, but `Write`/`Edit` must target the mount path — `.praxion/<name>`. Writes "
        "under `.ai-state/` work in place."
    )

    branches = _convergence_branches(failed_checks)
    if branches:
        lines.append("")
        lines.append(_convergence_line(branches))

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

    cli_path = resolve_cli(resolve_plugin_root(__file__))
    if cli_path is None:
        return  # unresolvable CLI -- silent, not an error

    # Self-heal BEFORE reading status (materializes a missing mount, converges
    # unmerged state branches). Its exit code stays honest -- 1 on an aborted
    # conflict -- but that never fails this hook; see module docstring.
    link_result = run_cli(cli_path, ["link", "--quiet"], cwd=cwd, timeout=LINK_TIMEOUT_SECONDS)

    if isinstance(placement, NotYetLinked) and not isinstance(resolve_placement(cwd), SidecarOwned):
        return  # the heal did not take -- nothing truthful left to render

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
        return  # a re-derived status disagreeing with `placement` above -- render nothing rather than guess

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
