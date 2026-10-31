#!/bin/sh
# Fast-path gate for the PreToolUse hooks that judge decision records.
# Reads stdin once and starts Python only when the payload could concern the
# decisions tree, so every other Write, Edit and Read pays a grep, not ~200-500ms
# of interpreter startup.
#
# Usage: decisions_gate.sh <write|read>
#   write  Write and Edit: the payload must hold `.ai-state/decisions`
#   read   Read: the payload must hold `DECISIONS_INDEX.md`
#
# The filter is deliberately loose and case-insensitive (the gate's path
# classifier folds case): a false positive just runs Python, which stays
# authoritative. The separator class takes `/`, JSON's `\/`, a backslash and a
# `.` so `.ai-state/./decisions` is not a way past it. Any other mode exits 0.
#
# The payload is forwarded with printf, never echo (td-188): /bin/sh on macOS is
# bash in POSIX mode, whose echo interprets backslash escapes, so a payload that
# carries `\n` or `\s` would reach Python as invalid JSON.

set -e

case "$1" in
    write) pattern='\.ai-state[/\\.]+decisions' ;;
    read) pattern='DECISIONS_INDEX\.md' ;;
    *) exit 0 ;;
esac

input=$(cat)

if printf '%s\n' "$input" | grep -qiE "$pattern"; then
    printf '%s\n' "$input" | python3 "${0%/*}/guard_decision_records.py"
else
    exit 0
fi
