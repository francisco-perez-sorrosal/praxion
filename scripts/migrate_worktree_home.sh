#!/usr/bin/env bash
# migrate_worktree_home.sh — emit copy-paste-ready commands to migrate
# legacy `.trees/<name>/` worktrees to the unified home `.claude/worktrees/<name>/`.
#
# Behavior:
#   - Enumerates live git worktrees via `git worktree list --porcelain`.
#   - For each worktree whose path matches `.trees/<name>/`, prints a human-readable
#     block with a `git worktree move` command the user can review and run.
#   - Performs NO automatic move. The user is responsible for running the emitted
#     commands after reviewing them (per dec-057 / SYSTEMS_PLAN C2).
#
# Usage:
#   scripts/migrate_worktree_home.sh         # print migration commands
#   scripts/migrate_worktree_home.sh --help  # show help and exit
#
# Exit codes:
#   0 — success (commands printed, or no legacy worktrees found)
#   1 — usage error or git invocation failure

set -euo pipefail

# --- Helpers ----------------------------------------------------------------

_info()  { printf "%s\n" "$*"; }
_warn()  { printf "warn: %s\n" "$*" >&2; }
_error() { printf "error: %s\n" "$*" >&2; }
_die()   { _error "$*"; exit 1; }

show_usage() {
    cat <<'EOF'
Usage: migrate_worktree_home.sh [--help]

Emit copy-paste-ready `git worktree move` commands for any live worktree
rooted at `.trees/<name>/`, migrating it to `.claude/worktrees/<name>/`.

No automatic move is performed. Review each emitted command before running it.

Options:
  --help    Show this help and exit

Exit codes:
  0   commands emitted, or no legacy `.trees/` worktrees found
  1   usage error or git invocation failure

See:
  - .ai-state/decisions/drafts/*-unified-worktree-home.md
  - SYSTEMS_PLAN.md Component C2
EOF
}

# --- Argument parsing -------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            _error "Unknown argument: $1"
            show_usage >&2
            exit 1
            ;;
    esac
done

# --- Preflight --------------------------------------------------------------

command -v git >/dev/null 2>&1 || _die "git not found on PATH"

# Locate the repo root for a stable `cd` target in emitted commands.
if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    _die "not inside a git repository"
fi

# --- Discover legacy worktrees ----------------------------------------------

# Collect worktree paths (one per line). `--porcelain` emits `worktree <path>` lines.
mapfile -t ALL_WORKTREES < <(git -C "$REPO_ROOT" worktree list --porcelain \
    | awk '/^worktree /{ sub(/^worktree /, ""); print }')

# Filter to those rooted at `<repo-root>/.trees/<name>`.
LEGACY=()
for wt in "${ALL_WORKTREES[@]}"; do
    # Strip the repo-root prefix (if present) to get a relative path.
    rel="${wt#"$REPO_ROOT"/}"
    case "$rel" in
        .trees/*)
            # Require exactly `.trees/<name>` — skip deeper nested paths.
            name="${rel#.trees/}"
            if [[ -n "$name" && "$name" != */* ]]; then
                LEGACY+=("$wt")
            fi
            ;;
    esac
done

# --- Emit migration plan ----------------------------------------------------

if [ ${#LEGACY[@]} -eq 0 ]; then
    _info "No .trees/ worktrees found — nothing to migrate."
    exit 0
fi

_info "# Migration plan: move legacy .trees/ worktrees to .claude/worktrees/"
_info "# Repo root: $REPO_ROOT"
_info "# Worktrees to migrate: ${#LEGACY[@]}"
_info ""

for wt in "${LEGACY[@]}"; do
    name="$(basename "$wt")"
    dest="$REPO_ROOT/.claude/worktrees/$name"
    _info "# Worktree: $wt"
    if [ -e "$dest" ]; then
        _warn "destination already exists: $dest — SKIP this entry or resolve manually"
        _info "# (destination exists; DO NOT run blindly — inspect $dest first)"
    fi
    _info "git -C \"$REPO_ROOT\" worktree move \".trees/$name\" \".claude/worktrees/$name\""
    _info ""
done

_info "# Review each command above, then run them manually."
_info "# No automatic move was performed. After moving, confirm with:"
_info "#   git -C \"$REPO_ROOT\" worktree list"
exit 0
