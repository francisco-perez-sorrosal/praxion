#!/usr/bin/env python3
"""SessionStart hook: surface un-filed Praxion ecosystem-defect candidates.

When a managed project has captured Praxion-origin ecosystem-defect candidates
in ``.ai-state/praxion_feedback/PENDING.md`` that are still ``status: pending``,
this hook injects a concise advisory naming ``/report-praxion-issue`` so the
operator is reminded to review them. Nothing is ever filed autonomously -- this
is a read-only reminder (the self-healing loop's Agent Discovery Protocol:
document, flag, never file without a human).

Two roots are resolved by deliberately different mechanisms, and the distinction
is load-bearing:

- **Plugin root** (where the reporter package ``scripts/praxion_feedback`` lives)
  is resolved from ``__file__`` -- correct, because that package *ships with this
  hook* inside the plugin and we only need it to import ``list_pending``.
- **Managed-project root** (where ``PENDING.md`` lives) is resolved from ``git``
  at the session cwd, **never** ``__file__`` -- the hook runs from the plugin
  cache, so ``__file__`` would point at the plugin, not the consumer repo.

Behavior contract:
- **Fail-safe**: absent ledger, no pending candidates, a non-git cwd, a partial
  install (reporter package unimportable), or ANY internal error all yield a
  silent exit-0 no-op. A global SessionStart hook must never slow or wedge a
  session with its own faults.
- **Lightweight**: one git subprocess + one file read; the surfaced list is
  capped at ``MAX_SURFACED``. No network, no directory scan.
- **Opt-out**: ``PRAXION_DISABLE_FEEDBACK_SURFACING=1`` suppresses the advisory
  (mirrors the ``PRAXION_DISABLE_*`` convention used by the other hooks).
- **Sync (async: false)**: its stdout ``additionalContext`` becomes session
  context, like ``inject_worktree_banner.py`` -- not a fire-and-forget notify.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _hook_utils import is_disabled

DISABLE_FLAG = "PRAXION_DISABLE_FEEDBACK_SURFACING"
MAX_SURFACED = 5  # cap the inline list -- bounded work on every session start
_SHORT_FP_LEN = 8  # matches candidate_store's short-fingerprint length
_PENDING_REL_PATH = Path(".ai-state") / "praxion_feedback" / "PENDING.md"


def _ensure_plugin_root_on_path() -> None:
    """Put the plugin root (parent of ``hooks/``) on ``sys.path``.

    Uses ``__file__`` deliberately: the reporter package ships alongside this
    hook, so importing it means locating the plugin's own tree. This is the
    plugin root, not the managed-project root (that comes from git below).
    """
    plugin_root = str(Path(__file__).resolve().parent.parent)
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)


def _honor_payload_cwd(raw: str) -> None:
    """Chdir into the session's ``cwd`` from the payload when present.

    Lets the reused ``git_toplevel_from_cwd`` (which reads the process cwd)
    resolve the managed-project root. Guarded and best-effort: this process is
    short-lived, so the chdir has no lasting effect and any failure is ignored.
    """
    try:
        cwd = json.loads(raw).get("cwd") if raw.strip() else None
    except (json.JSONDecodeError, AttributeError, TypeError):
        return
    if cwd and Path(cwd).is_dir():
        try:
            os.chdir(cwd)
        except OSError:
            pass


def _pending_md_path() -> Path | None:
    """Resolve the managed-project's ``PENDING.md`` via git -- never ``__file__``."""
    _ensure_plugin_root_on_path()
    from scripts._repo_root import git_toplevel_from_cwd

    repo_root = git_toplevel_from_cwd()
    if repo_root is None:
        return None
    return repo_root / _PENDING_REL_PATH


def _pending_candidates(pending: Path) -> list[dict]:
    """Return the still-``pending`` candidates via the store's own parser.

    ``list_pending`` returns ``[]`` for an absent or block-free ledger, so the
    caller needs no separate existence check.
    """
    _ensure_plugin_root_on_path()
    from scripts.praxion_feedback.candidate_store import list_pending

    return list_pending(pending)


def _candidate_line(candidate: dict) -> str:
    category = candidate.get("category", "?")
    artifact = candidate.get("artifact_path", "?")
    fingerprint = (candidate.get("fingerprint") or "")[:_SHORT_FP_LEN]
    return f"- {category} — {artifact} ({fingerprint})"


def _build_advisory(candidates: list[dict]) -> str:
    """Render the pending-candidate advisory injected into the agent's context."""
    total = len(candidates)
    shown = candidates[:MAX_SURFACED]
    lines = [
        "## Pending Praxion feedback (auto-injected)",
        "",
        f"{total} ecosystem-defect candidate(s) captured and awaiting review. Run "
        "`/report-praxion-issue` to review and file — nothing is filed autonomously.",
        "",
    ]
    lines.extend(_candidate_line(candidate) for candidate in shown)
    remaining = total - len(shown)
    if remaining > 0:
        lines.append(f"- …and {remaining} more (see `.ai-state/praxion_feedback/PENDING.md`)")
    return "\n".join(lines)


def _emit(context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )


def main() -> None:
    # Always drain stdin -- the hook framework can SIGPIPE on its write end
    # if the pipe is left unread.
    raw = sys.stdin.read()
    if is_disabled(DISABLE_FLAG):
        return
    _honor_payload_cwd(raw)
    pending = _pending_md_path()
    if pending is None:
        return
    candidates = _pending_candidates(pending)
    if candidates:
        _emit(_build_advisory(candidates))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-safe: never block or slow session creation
