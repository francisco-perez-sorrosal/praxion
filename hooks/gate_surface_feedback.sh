#!/bin/sh
# SessionStart pre-check: skip surface_praxion_feedback.py's interpreter start
# when its own fast path already reports nothing to do.
#
# Mirrors the hook's documented early return (surface_praxion_feedback.py
# module docstring, "Fail-safe" bullet): an absent ledger yields "a silent
# exit-0 no-op." The ledger is `<project-root>/.ai-state/praxion_feedback/PENDING.md`;
# its absence is the common case (most projects have never filed a Praxion
# ecosystem-defect candidate), so this is the dominant skip on most sessions.
# Presence of the file does not guarantee a `status: pending` row inside it --
# that finer check stays in Python (list_pending's own markdown-block parser),
# so a present-but-empty ledger still starts the interpreter. Safe by
# construction: the shell condition can only under-skip (run Python when it
# would have no-op'd anyway), never over-skip (suppress a real advisory).
#
# The disable-flag comparison mirrors `_hook_utils.is_disabled`'s truthy set
# ({1, true, yes}, case-insensitive).
#
# Usage: gate_surface_feedback.sh <interpreter> <hook-script> [args...]

set -e

input=$(cat)

cwd=$(printf '%s\n' "$input" | sed -n 's/.*"cwd" *: *"\([^"]*\)".*/\1/p' | head -n 1)
[ -n "$cwd" ] || cwd="$PWD"

flag=$(printf '%s' "${PRAXION_DISABLE_FEEDBACK_SURFACING:-}" | tr '[:upper:]' '[:lower:]')
case "$flag" in
    1 | true | yes) exit 0 ;;
esac

if [ ! -f "$cwd/.ai-state/praxion_feedback/PENDING.md" ]; then
    exit 0
fi

interpreter="$1"
shift
printf '%s\n' "$input" | "$interpreter" "$@"
