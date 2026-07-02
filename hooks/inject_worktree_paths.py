#!/usr/bin/env python3
"""PreToolUse(Agent) hook: brief spawned subagents with absolute worktree paths.

Fires when the ORCHESTRATOR's own session is running inside a *linked* git
worktree (not the main checkout) and prepends a single-line reminder to
every spawned subagent's prompt: the absolute session worktree root, plus
an instruction to use absolute paths under that root for every file write.

This resolves the residual exposure left in td-034 after the hook-inheritance
question was settled (subagents DO inherit PreToolUse hooks; worktree_guard.py
fires correctly on absolute-path targets). Two gaps remained -- both mitigated
only by prompt discipline (REACTIVE), not by a deterministic layer:

  1. worktree_guard.py deliberately ignores RELATIVE file_path targets (see
     dec-180's tested `test_ignores_relative_path` contract) -- a relative
     path a subagent emits is invisible to the guard by design.
  2. Subagent cwd-bifurcation: a spawned subagent's own cwd can resolve to
     the canonical checkout even while it was briefed to work in a worktree,
     so a relative path from that subagent lands in the wrong tree.

Neither gap is closeable by tightening worktree_guard.py itself -- that
would contradict its tested, ADR-backed contract (dec-180) and would need
its own ADR. This hook is the deterministic mitigation for both gaps: it
makes the absolute worktree root and the "use absolute paths" instruction
PART OF THE SUBAGENT'S OWN PROMPT, delivered mechanically -- not left to
orchestrator prompt discipline.

Fast-skip conditions (exit 0, no stdout, strictly empty):
  (a) tool_name is not "Agent"
  (b) the session's cwd is NOT inside a linked git worktree (main checkout,
      or not a git repo at all) -- nothing to brief
  (c) PRAXION_DISABLE_WORKTREE_PATH_BRIEFING=1 is set

Applies to ALL subagent types -- i-am:* and host-native alike. Unlike
inject_subagent_context.py's gate (d), there is no i-am:* skip here: i-am
agents are exactly the common case in worktree pipelines (EnterWorktree is
a Standard/Full-tier requirement per swe-agent-coordination-protocol.md), so
excluding them would leave the most frequent spawn path unmitigated.

Composition note: this hook and inject_subagent_context.py both register on
PreToolUse(Agent) and both use updatedInput to modify tool_input.prompt. Each
reads and rewrites whatever prompt is CURRENTLY on tool_input at the moment
it runs, so the two injections compose correctly if Claude Code applies
updatedInput cumulatively across chained PreToolUse hooks for the same
matcher -- the harness contract this hook assumes but has not live-verified
(see LEARNINGS_td034.md). If the harness instead keeps only the last hook's
updatedInput, one injection is dropped; that is a platform-level open
question, not a defect specific to either hook.

Synchronous hook. Exit 0 unconditionally -- must never block subagent creation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants -----------------------------------------------------------------

_DISABLE_FLAG = "PRAXION_DISABLE_WORKTREE_PATH_BRIEFING"
_SUBPROCESS_TIMEOUT_SECONDS = 3


# -- Helper functions ----------------------------------------------------------


def _git(cwd: Path, *args: str) -> str | None:
    """Run ``git -C cwd <args>`` and return stripped stdout; None on any failure."""
    try:
        result = subprocess.run(
            ("git", "-C", str(cwd), *args),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _linked_worktree_root(cwd: Path) -> Path | None:
    """Return the session's worktree root iff it is a *linked* (non-main) worktree.

    Mirrors worktree_guard.py's / inject_worktree_banner.py's detection: compares
    the resolved ``--git-dir`` against ``--git-common-dir``. Equal means the main
    worktree (nothing to brief); different means a linked worktree. Returns None
    on any git-detection failure (non-git cwd, missing cwd, subprocess error) --
    the fail-open default is "do not brief."
    """
    git_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir is None or common_dir is None:
        return None
    if Path(git_dir).resolve() == Path(common_dir).resolve():
        return None  # main worktree -- no boundary to brief
    toplevel = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(toplevel).resolve() if toplevel else None


def _briefing_line(worktree_root: Path) -> str:
    return (
        f"[Worktree session] Your session worktree root is `{worktree_root}`. "
        "Use absolute paths under this root for all file writes; never relative paths."
    )


def _emit_updated_input(tool_input: dict, prompt: str, briefing: str) -> None:
    """Emit the updatedInput JSON response to stdout.

    Preserves every field of the original tool_input (subagent_type,
    description, model, run_in_background, isolation, …) and prepends the
    briefing line to whatever prompt is currently set.

    Harness contract: updatedInput's value IS the replacement tool-input params
    object directly -- never wrapped in an envelope key. The harness validates it
    directly against the tool's schema; a wrapper makes every required param
    "missing" (see the identical contract note in inject_subagent_context.py,
    fixed 2026-07-01 after a live breakage).
    """
    updated = dict(tool_input)
    updated["prompt"] = f"{briefing}\n\n{prompt}"
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated,
        }
    }
    print(json.dumps(output))


# -- Main entry point ----------------------------------------------------------


def main() -> None:
    """Read stdin, apply skip gates, and inject the briefing when appropriate."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception:
        # Malformed or empty stdin -- exit 0 silently
        return

    try:
        _process(payload)
    except Exception:
        # Internal error -- exit 0 unconditionally
        return


def _process(payload: dict) -> None:
    """Apply skip gates and emit updatedInput when a worktree briefing is warranted."""
    # Gate (c) checked first: disable flag takes precedence over all other logic
    if is_disabled(_DISABLE_FLAG):
        return

    tool_name = payload.get("tool_name", "")
    if tool_name != "Agent":
        return

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return

    cwd = payload.get("cwd", "")
    if not cwd:
        return

    # Gate (b): session must be inside a linked worktree
    worktree_root = _linked_worktree_root(Path(cwd))
    if worktree_root is None:
        return

    prompt = tool_input.get("prompt", "")
    _emit_updated_input(tool_input, prompt, _briefing_line(worktree_root))


if __name__ == "__main__":
    main()
