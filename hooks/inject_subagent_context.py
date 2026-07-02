"""PreToolUse(Agent) hook: the single updatedInput emitter for subagent spawns.

Fires at PreToolUse for any Agent tool invocation and composes up to three
prompt additions ahead of the original prompt, emitting at most ONE
updatedInput per spawn (dec-266, resolving td-049 and td-051):

  1. Praxion preamble -- prepended for host-native agents (Explore, Plan,
     general-purpose) launched from a Praxion-managed project; i-am:* agents
     are skipped by default (gate (d) below applies to the preamble ONLY).
  2. Session-worktree line -- when the spawning session's `--git-dir` differs
     from `--git-common-dir` (a linked worktree), for ALL agent types. This
     is the td-034 direction: the session itself is inside a worktree.
  3. Briefed-root line -- when the outgoing PROMPT names an absolute
     `.claude/worktrees/<name>` path that is not the session's own cwd (or a
     subdirectory of it), for ALL agent types. This is the td-051 direction:
     a canonical-checkout session briefing an agent INTO a worktree via the
     prompt text, with no deterministic reinforcement of that boundary.
     Detected by a conservative regex on the prompt text only -- no
     filesystem walk, no git call for this specific check.

Previously this concern was split across two separate PreToolUse(Agent) hooks
that could each emit updatedInput for the same spawn -- whether the harness
chains multiple updatedInput emissions across matching hooks (vs. dropping
all but one) was an unverified assumption (td-049). Consolidating into a
single emitter makes that question structurally moot.

When none of the three conditions hold (e.g. an i-am agent with no worktree
context, a canonical session with no worktree-naming prompt), the hook emits
nothing -- preserving the original gate contract of each concern.

Fast-skip conditions (exit 0, no stdout, strictly empty):
  (a) tool_name is not "Agent"
  (b) tool_input is not a JSON object
  (c) [preamble only] cwd has no .ai-state/ directory (non-Praxion project)
  (d) [preamble only] subagent_type matches i-am:* AND
      PRAXION_INJECT_NATIVE_SUBAGENTS is not set
  (e) [preamble only] PRAXION_DISABLE_SUBAGENT_INJECT=1 is set
  (f) [worktree lines only] PRAXION_DISABLE_WORKTREE_PATH_BRIEFING=1 is set
  (g) [worktree lines only] cwd is empty

Caching: .ai-state/ presence is cached per session_id to avoid per-spawn
filesystem stats on dense fan-out pipelines.

Synchronous hook. Exit 0 unconditionally — must never block subagent creation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants -----------------------------------------------------------------

_DISABLE_PREAMBLE_FLAG = "PRAXION_DISABLE_SUBAGENT_INJECT"
_INJECT_NATIVE_FLAG = "PRAXION_INJECT_NATIVE_SUBAGENTS"
_DISABLE_WORKTREE_FLAG = "PRAXION_DISABLE_WORKTREE_PATH_BRIEFING"
_SUBPROCESS_TIMEOUT_SECONDS = 3

# Preamble content (chars ≤300 incl. separator — enforced by test).
# Structural keywords required by test contract:
#   "Surface Assumptions", "Register Objection", "Stay Surgical", "Simplicity First"
# Plus tier-selector, delegation-back, and return-contract references.
# ~292 chars / 3.6 ≈ 81 tokens — paid in the subagent prompt, not orchestrator context.
# The return clause reaches host-native agents (Explore/Plan/general-purpose) that have
# no `## Output` block and do not load the always-on coordination rule.
_PREAMBLE = (
    "[Praxion process active] "
    "Apply the behavioral contract: "
    "Surface Assumptions, Register Objection, Stay Surgical, Simplicity First. "
    "Use the tier selector; carry this contract into every delegation. "
    "Return a pointer, not a payload: a summary plus your .ai-work/ "
    "artifact path, not the full report."
)

# Conservative match for an absolute path naming a `.claude/worktrees/<name>`
# root inside prompt text. Non-greedy prefix keeps the captured group anchored
# to the leftmost valid absolute path; the name class stops at the next `/`
# or whitespace so trailing path segments (e.g. a file under the worktree)
# are not swept into the captured root.
_WORKTREE_PATH_RE = re.compile(r"(/\S*?\.claude/worktrees/[A-Za-z0-9_.-]+)")

# Per-session-id cache: maps session_id → bool (True = .ai-state/ present)
_session_cache: dict[str, bool] = {}


# -- Preamble gates --------------------------------------------------------------


def _has_ai_state(cwd: str, session_id: str) -> bool:
    """Return True if cwd contains a .ai-state/ subdirectory.

    Caches the result per session_id to avoid repeated filesystem stats
    on multi-agent fan-out from the same session.
    """
    if session_id in _session_cache:
        return _session_cache[session_id]
    result = Path(cwd, ".ai-state").is_dir()
    _session_cache[session_id] = result
    return result


def _is_praxion_native(subagent_type: str) -> bool:
    """Return True for Praxion-native agents (i-am:* prefix)."""
    return subagent_type.startswith("i-am:")


def _preamble_segment(subagent_type: str, cwd: str, session_id: str) -> str:
    """Return the Praxion preamble text, or "" if any preamble gate suppresses it.

    Every gate here is scoped to the preamble ONLY — the worktree lines
    computed by _worktree_segments have their own, independent gates.
    """
    if is_disabled(_DISABLE_PREAMBLE_FLAG):
        return ""
    if not cwd or not _has_ai_state(cwd, session_id):
        return ""
    if _is_praxion_native(subagent_type):
        inject_native = os.environ.get(_INJECT_NATIVE_FLAG, "").strip()
        if inject_native.lower() not in ("1", "true", "yes"):
            return ""
    return _PREAMBLE


# -- Worktree-line gates ----------------------------------------------------------


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

    Compares the resolved ``--git-dir`` against ``--git-common-dir``. Equal
    means the main worktree (nothing to brief); different means a linked
    worktree. Returns None on any git-detection failure (non-git cwd, missing
    cwd, subprocess error) — the fail-open default is "do not brief."
    """
    git_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir is None or common_dir is None:
        return None
    if Path(git_dir).resolve() == Path(common_dir).resolve():
        return None  # main worktree -- no boundary to brief
    toplevel = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(toplevel).resolve() if toplevel else None


def _session_worktree_line(worktree_root: Path) -> str:
    return (
        f"[Worktree session] Your session worktree root is `{worktree_root}`. "
        "Use absolute paths under this root for all file writes; never relative paths."
    )


def _briefed_worktree_root(prompt: str, cwd: str) -> str | None:
    """Return the worktree root named in `prompt`, iff it differs from `cwd`.

    Conservative regex on the prompt TEXT only — no filesystem walk, no git
    call. Detects the canonical-session-briefing-a-worktree direction: the
    outgoing prompt names an absolute `.claude/worktrees/<name>` path that is
    not the session's own cwd (or a subdirectory of it). Returns None when no
    such path is named, or when the named root is the session's own root
    (already covered, if applicable, by the session-worktree line above).
    """
    match = _WORKTREE_PATH_RE.search(prompt)
    if match is None:
        return None
    named_root = match.group(1).rstrip("/")
    cwd_norm = cwd.rstrip("/")
    if cwd_norm == named_root or cwd_norm.startswith(named_root + "/"):
        return None  # session is already inside the named worktree
    return named_root


def _briefed_root_line(worktree_root: str) -> str:
    return (
        f"[Worktree briefing] This prompt names `{worktree_root}` as the target "
        "worktree root. Use absolute paths under that root for every file write; "
        "never relative paths, and verify your cwd resolves there before writing."
    )


def _worktree_segments(cwd: str, prompt: str) -> list[str]:
    """Return 0-2 worktree briefing lines: session-worktree, briefed-root."""
    if is_disabled(_DISABLE_WORKTREE_FLAG):
        return []
    if not cwd:
        return []

    segments: list[str] = []
    linked_root = _linked_worktree_root(Path(cwd))
    if linked_root is not None:
        segments.append(_session_worktree_line(linked_root))

    briefed_root = _briefed_worktree_root(prompt, cwd)
    if briefed_root is not None:
        segments.append(_briefed_root_line(briefed_root))

    return segments


# -- Emission ---------------------------------------------------------------------


def _emit_updated_input(tool_input: dict, prompt: str, segments: list[str]) -> None:
    """Emit the updatedInput JSON response to stdout.

    Preserves every field of the original tool_input (subagent_type,
    description, model, run_in_background, isolation, …) and overrides only
    the prompt: each composed segment on its own paragraph, ahead of the
    original prompt. Reconstructing tool_input from scratch would drop the
    Agent tool's required `description` field, causing host-native spawns
    (Explore/Plan/general-purpose) to fail schema validation.
    """
    updated = dict(tool_input)
    updated["prompt"] = "\n\n".join([*segments, prompt])
    # Harness contract: updatedInput's value IS the replacement tool-input params
    # object — never wrap it in an envelope key. The harness validates it directly
    # against the tool's schema; a wrapper makes every required param "missing".
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
    """Read stdin, apply skip gates, and inject composed segments when warranted."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception:
        # Malformed or empty stdin — exit 0 silently
        return

    try:
        _process(payload)
    except Exception:
        # Internal error — exit 0 unconditionally
        return


def _process(payload: dict) -> None:
    """Compose the preamble and worktree segments and emit updatedInput when
    at least one applies."""
    tool_name = payload.get("tool_name", "")
    if tool_name != "Agent":
        return

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return

    subagent_type = tool_input.get("subagent_type", "")
    prompt = tool_input.get("prompt", "")
    cwd = payload.get("cwd", "")
    session_id = payload.get("session_id", "")

    segments: list[str] = []
    preamble = _preamble_segment(subagent_type, cwd, session_id)
    if preamble:
        segments.append(preamble)
    segments.extend(_worktree_segments(cwd, prompt))

    if not segments:
        return

    _emit_updated_input(tool_input, prompt, segments)


if __name__ == "__main__":
    main()
