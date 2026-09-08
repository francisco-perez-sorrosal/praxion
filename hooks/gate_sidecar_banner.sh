#!/bin/sh
# SessionStart pre-check: skip inject_sidecar_banner.py's interpreter start
# when the project is plainly `InRepo` (owns its own `.ai-state/`) -- the
# overwhelming majority of sessions per the hook's own module docstring.
#
# Mirrors `_state_repo.resolve_placement`'s InRepo branch exactly: when
# `.ai-state` is not a symlink AND it exists, resolution returns InRepo
# unconditionally (no other code path can produce a different placement for
# that shape -- see resolve_placement's `if not slot.is_symlink(): if not
# slot.exists(): ... ; return InRepo(...)`). The only shape this check must
# NOT skip is "`.ai-state` absent" -- that can still resolve to `NotYetLinked`
# (a fresh worktree of a sidecar-owned project), which is exactly the case
# this hook exists to heal, so absence always falls through to Python.
#
# The disable-flag comparison mirrors `_hook_utils.is_disabled`'s truthy set
# ({1, true, yes}, case-insensitive).
#
# Usage: gate_sidecar_banner.sh <interpreter> <hook-script> [args...]

set -e

input=$(cat)

cwd=$(printf '%s\n' "$input" | sed -n 's/.*"cwd" *: *"\([^"]*\)".*/\1/p' | head -n 1)
[ -n "$cwd" ] || cwd="$PWD"

flag=$(printf '%s' "${PRAXION_DISABLE_SIDECAR_BANNER:-}" | tr '[:upper:]' '[:lower:]')
case "$flag" in
    1 | true | yes) exit 0 ;;
esac

if [ -e "$cwd/.ai-state" ] && [ ! -L "$cwd/.ai-state" ]; then
    exit 0
fi

interpreter="$1"
shift
printf '%s\n' "$input" | "$interpreter" "$@"
