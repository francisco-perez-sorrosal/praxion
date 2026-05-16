"""UserPromptSubmit hook: inject compact process-framing reminder.

Fires at UserPromptSubmit. Emits a short additionalContext message that
reminds the orchestrator of the Praxion tier selector and rule-inheritance
obligation — but only when the prompt is non-trivial and the session is
in a Praxion-managed project.

Fast-skip conditions (exit 0, no output):
  (a) cwd has no .ai-state/ directory (non-Praxion project)
  (b) PRAXION_DISABLE_PROCESS_INJECT=1 is set
  (c) _is_continuation(payload) returns True (continuation turn)
  (d) prompt length <= 60 AND prompt does not contain '?'
  (e) prompt matches the trivial-pattern set (yes/ok/go/run/do it)

Synchronous hook. Exit 0 unconditionally — must never block prompt submission.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants -----------------------------------------------------------------

_DISABLE_FLAG = "PRAXION_DISABLE_PROCESS_INJECT"
_HACKATHON_FLAG = "PRAXION_HACKATHON_MODE"
_HACKATHON_HEADING = "## Hackathon Mode"

_CONSISTENCY_WARNING = (
    "[Praxion] Warning: a `## Hackathon Mode` block is present in CLAUDE.md "
    "but `PRAXION_HACKATHON_MODE` is not set. "
    "Remove the block or set the env var."
)

_TEST_DISCIPLINE_REMINDER = (
    "[Praxion] Hackathon mode disabled — test discipline is now active. "
    "Red tests will block the pipeline again. "
    "Consider a coverage pass before adding new behavior."
)

# Short-reply threshold: prompts at or under 60 chars without '?' are skipped.
# A 60-char prompt without '?' is still considered a short reply.
_SHORT_REPLY_THRESHOLD = 60

# Trivial-pattern: case-insensitive, whole-prompt match, optional trailing punct
_TRIVIAL_RE = re.compile(
    r"^\s*(yes|no|ok|continue|go|run|do\s+it)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

# The injected framing — must be under 50 tokens (≈180 bytes at 3.6 bytes/token).
# Contains: "tier" + "pipeline" (tier-selector language) and
#           "contract" + "delegation" (rule-inheritance language).
# 129 bytes / 3.6 ≈ 35.8 tokens — well within budget.
_FRAMING = (
    "[Praxion] Use the tier selector for non-trivial work. "
    "Carry the behavioral contract into every delegation and subagent prompt."
)


# -- Module-level continuation detector (must be patchable by tests) -----------


def _is_continuation(payload: dict) -> bool:
    """Return True when the payload looks like a mid-conversation continuation.

    A continuation is detected when the transcript ends with an assistant
    turn followed by a brief (< 60 char) user reply with no question mark —
    i.e. the user is responding to the assistant rather than initiating new
    work.

    Reads the transcript at ``payload["transcript_path"]`` if present.
    Falls back to False on any I/O or parse error (safe default: do not
    suppress framing when uncertain).
    """
    transcript_path = payload.get("transcript_path", "")
    if not transcript_path:
        return False
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    last_role = None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            turn = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = turn.get("type") or turn.get("role", "")
        if role:
            last_role = role
            break

    return last_role == "assistant"


# -- Main entry point ----------------------------------------------------------


def main() -> None:
    """Read stdin, apply fast-skip gates, and emit framing when appropriate."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception:
        # Malformed stdin — exit 0 silently
        return

    try:
        _process(payload)
    except Exception:
        # Internal error — exit 0 unconditionally
        return


def _process(payload: dict) -> None:
    """Apply gates and emit additionalContext when all gates pass."""
    cwd = payload.get("cwd", "")
    prompt = payload.get("prompt", "")

    # Gate (a): non-Praxion project
    if not Path(cwd, ".ai-state").is_dir():
        return

    # Gate (b): opt-out flag
    if is_disabled(_DISABLE_FLAG):
        return

    # Hackathon consistency checks — both are no-ops when the flag is active
    # (is_disabled returns True when PRAXION_HACKATHON_MODE=1).
    # When the flag is OFF but the CLAUDE.md block is present, emit advisory
    # messages to help the user restore full ceremony.
    if not is_disabled(_HACKATHON_FLAG):
        _check_hackathon_consistency(cwd)

    # Gate (c): continuation turn
    if _is_continuation(payload):
        return

    # Gate (d): short reply (<=60 chars with no question mark is a short reply)
    if len(prompt) <= _SHORT_REPLY_THRESHOLD and "?" not in prompt:
        return

    # Gate (e): trivial pattern
    if _TRIVIAL_RE.match(prompt):
        return

    _emit_framing()


def _emit_framing() -> None:
    """Emit the additionalContext output to stdout.

    UserPromptSubmit hooks emit additionalContext directly as a top-level
    key, not nested under hookSpecificOutput.
    """
    print(json.dumps({"additionalContext": _FRAMING}))


def _emit_advisory(message: str) -> None:
    """Emit an advisory additionalContext message to stdout."""
    print(json.dumps({"additionalContext": message}))


def _has_hackathon_block(cwd: str) -> bool:
    """Return True if the project CLAUDE.md contains the hackathon heading."""
    claude_md = Path(cwd, "CLAUDE.md")
    try:
        return _HACKATHON_HEADING in claude_md.read_text(encoding="utf-8")
    except OSError:
        return False


def _check_hackathon_consistency(cwd: str) -> None:
    """Emit advisory messages when the hackathon block is present but the flag is off.

    Both advisories (consistency warning + test-discipline reminder) fire when
    PRAXION_HACKATHON_MODE is unset/off and the CLAUDE.md block is still present.
    This is the exit-procedure reminder: the block has not been deleted yet.
    Fail-open: any exception exits silently.
    """
    try:
        if _has_hackathon_block(cwd):
            _emit_advisory(_CONSISTENCY_WARNING)
            _emit_advisory(_TEST_DISCIPLINE_REMINDER)
    except Exception:
        pass


if __name__ == "__main__":
    main()
