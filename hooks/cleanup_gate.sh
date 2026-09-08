#!/bin/sh
# Fast-path gate for PreToolUse hooks that only apply to .ai-work/ cleanup.
# Reads stdin, checks for cleanup patterns with grep (<1ms), and only invokes
# the Python hook if the payload looks like a cleanup. Avoids ~200-500ms of
# Python startup overhead on every non-cleanup Bash call.
#
# Source of truth for patterns: hooks/promote_learnings.py CLEANUP_PATTERNS.
# Shell regex escapes \. for correctness. The shell filter is intentionally
# loose — ambiguous payloads fall through to the Python hook, which remains
# authoritative. False positives (rare) just run Python unnecessarily — same
# as before. Known false-negatives (accepted for v1): `rmdir`, `trash`.
#
# Usage: cleanup_gate.sh <python-hook-script>

set -e

input=$(cat)

# The payload is forwarded with printf, never echo: /bin/sh on macOS is bash in
# POSIX mode, whose builtin echo interprets backslash escapes, so a command that
# contains `\|`, `\s` or `\n` (any grep pattern) arrives as invalid JSON and
# every Python hook's json.loads fails silently -- td-188.
if printf '%s\n' "$input" | grep -qE 'rm[[:space:]]+.*\.ai-work|find[[:space:]]+.*\.ai-work.*-delete|clean\.work|clean-work'; then
    printf '%s\n' "$input" | python3 "$1"
else
    exit 0
fi
