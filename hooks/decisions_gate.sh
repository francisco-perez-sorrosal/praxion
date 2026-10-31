#!/bin/sh
# Fast-path gate for the PreToolUse hooks that judge decision records.
# Reads stdin once and starts Python only when the payload could concern the
# decisions tree, so every other Write, Edit and Read pays a grep, not ~200-500ms
# of interpreter startup.
#
# Usage: decisions_gate.sh <write|read>
#   write  Write and Edit: the payload must hold both `.ai-state` and `decisions`
#   read   Read: the payload must hold `DECISIONS_INDEX.md`
#
# The filter is deliberately loose and case-insensitive (the gate's path
# classifier folds case): a false positive just runs Python, which stays
# authoritative. Write mode tests the two words separately, not as one path, so
# every spelling Python normalises into the decisions tree reaches it:
# `.ai-state/./decisions`, `.ai-state/x/../decisions`, `\` separators, and a
# relative `decisions/x.md` under a `cwd` inside `.ai-state`. Any other mode
# exits 0.
#
# Fail-open: this script always exits 0 and is silent apart from the guard's own
# stdout. A guard that is missing, cannot start or crashes lets the call through
# (exit 2 would block it), and the commit gate still holds.
#
# The payload is forwarded with printf, never echo (td-188): /bin/sh on macOS is
# bash in POSIX mode, whose echo interprets backslash escapes, so a payload that
# carries `\n` or `\s` would reach Python as invalid JSON.

holds() {
    printf '%s\n' "$input" | grep -qiE "$1"
}

concerns_decisions() {
    case "$1" in
        write) holds '\.ai-state' && holds 'decisions' ;;
        read) holds 'DECISIONS_INDEX\.md' ;;
        *) return 1 ;;
    esac
}

input=$(cat)

if concerns_decisions "$1"; then
    printf '%s\n' "$input" | python3 "${0%/*}/guard_decision_records.py" 2>/dev/null || exit 0
fi
exit 0
