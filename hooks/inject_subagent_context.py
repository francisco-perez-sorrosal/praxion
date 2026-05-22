"""PreToolUse(Agent) hook: inject Praxion behavioral contract into subagent prompts.

Fires at PreToolUse for any Agent tool invocation. Prepends a compact
Praxion preamble to the subagent's prompt so that host-native agents
(Explore, Plan, general-purpose) receive the behavioral contract that
they otherwise have no mechanism to load.

Fast-skip conditions (exit 0, no stdout, strictly empty):
  (a) tool_name is not "Agent"
  (b) cwd has no .ai-state/ directory (non-Praxion project)
  (c) PRAXION_DISABLE_SUBAGENT_INJECT=1 is set (takes precedence over all)
  (d) subagent_type matches i-am:* AND PRAXION_INJECT_NATIVE_SUBAGENTS not set

Caching: .ai-state/ presence is cached per session_id to avoid per-spawn
filesystem stats on dense fan-out pipelines.

Synchronous hook. Exit 0 unconditionally — must never block subagent creation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants -----------------------------------------------------------------

_DISABLE_FLAG = "PRAXION_DISABLE_SUBAGENT_INJECT"
_INJECT_NATIVE_FLAG = "PRAXION_INJECT_NATIVE_SUBAGENTS"

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

# Per-session-id cache: maps session_id → bool (True = .ai-state/ present)
_session_cache: dict[str, bool] = {}


# -- Helper functions ----------------------------------------------------------


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


def _emit_updated_input(subagent_type: str, prompt: str) -> None:
    """Emit the updatedInput JSON response to stdout."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {
                "tool_input": {
                    "subagent_type": subagent_type,
                    "prompt": f"{_PREAMBLE}\n\n{prompt}",
                }
            },
        }
    }
    print(json.dumps(output))


# -- Main entry point ----------------------------------------------------------


def main() -> None:
    """Read stdin, apply skip gates, and inject preamble when appropriate."""
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
    """Apply skip gates and emit updatedInput when injection is warranted."""
    # Gate (c) checked first: disable flag takes precedence over all other logic
    if is_disabled(_DISABLE_FLAG):
        return

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

    # Gate (b): non-Praxion project
    if not cwd or not _has_ai_state(cwd, session_id):
        return

    # Gate (d): skip Praxion-native agents unless opt-in is set
    if _is_praxion_native(subagent_type):
        inject_native = os.environ.get(_INJECT_NATIVE_FLAG, "").strip()
        if inject_native.lower() not in ("1", "true", "yes"):
            return

    _emit_updated_input(subagent_type, prompt)


if __name__ == "__main__":
    main()
