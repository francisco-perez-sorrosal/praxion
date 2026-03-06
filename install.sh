#!/usr/bin/env bash
# ai-assistants Installer — Entry point
#
# Routes to install_claude.sh (Claude Code / Claude Desktop) or
# install_cursor.sh (Cursor). See --help for usage.
#
#   ./install.sh [code|desktop|cursor [path]] [--check] [--dry-run] [--uninstall] [--help]

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -t 1 ]; then
    B=$'\033[1m' D=$'\033[2m' R=$'\033[0m'
else
    B='' D='' R=''
fi

info()  { printf "  ✓ %s\n" "$*"; }
warn()  { printf "  ⚠ %s\n" "$*"; }
fail()  { printf "  ✗ %s\n" "$*" >&2; exit 1; }
header() { printf "\n${B}%s${R}\n" "$*"; }

# =============================================================================
# Overview banner
# =============================================================================

show_overview() {
    local mode=$1
    printf "\n${B}ai-assistants Installer${R}\n"
    case "$mode" in
        code)
            cat <<EOF

  Target: ${B}Claude Code${R}

  Components:
    • Personal config  (CLAUDE.md, userPreferences.txt)
    • Rules            (auto-loaded by Claude)
    • i-am plugin      (skills, commands, agents)
    • Chronograph hooks (agent lifecycle observability)
    • CLI scripts        (ccwt — multi-worktree Claude sessions)
EOF
            ;;
        desktop)
            cat <<EOF

  Target: ${B}Claude Desktop${R}

  Components:
    • Claude Desktop config  (MCP servers)
EOF
            ;;
        cursor)
            cat <<EOF

  Target: ${B}Cursor${R}

  Default: user profile ~/.cursor/ (all Cursor projects).
  With path: per-project at <path>/.cursor/

  Components:
    • skills/   (symlinks to repo skills/)
    • rules/   (symlinks to repo rules/)
    • commands/ (exported from commands/*.md)
    • mcp.json  (task-chronograph, memory, sub-agents)
EOF
            ;;
    esac
}

# =============================================================================
# Usage
# =============================================================================

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [code|desktop|cursor [path]] [--check] [--dry-run] [--uninstall] [--help]

  code         Install for Claude Code (default)
  desktop      Install for Claude Desktop
  cursor       Install for Cursor: user profile ~/.cursor/ (default)
  cursor PATH  Install for Cursor: per-project at PATH/.cursor/
  --check      Verify installation health
  --dry-run    Show what would be installed (no writes)
  --uninstall  Remove installation
  --help       Show this help
EOF
    exit 0
}

# =============================================================================
# Main
# =============================================================================

MODE="code"
CHECK=false
DRY_RUN=false
UNINSTALL=false
CURSOR_TARGET=""

while [ $# -gt 0 ]; do
    case "$1" in
        code|desktop) MODE="$1" ;;
        cursor)       MODE="cursor"
                      if [ -n "$2" ] && [[ "$2" != --* ]]; then CURSOR_TARGET="$2"; shift; fi ;;
        --check)      CHECK=true ;;
        --dry-run)    DRY_RUN=true ;;
        --uninstall)  UNINSTALL=true ;;
        -h|--help)    show_usage ;;
        *)            fail "Unknown argument: $1. Use --help for usage." ;;
    esac
    shift
done

# At most one of --check, --dry-run, --uninstall (first wins)
if $CHECK && ( $DRY_RUN || $UNINSTALL ); then
    warn "Multiple actions requested; using --check only."
    DRY_RUN=false
    UNINSTALL=false
elif $DRY_RUN && $UNINSTALL; then
    warn "Multiple actions requested; using --dry-run only."
    UNINSTALL=false
fi

show_overview "$MODE"

# Build delegate args as array
delegate_args=()

case "$MODE" in
    code|desktop)
        delegate_args+=("$MODE")
        $CHECK     && delegate_args+=(--check)
        $DRY_RUN   && delegate_args+=(--dry-run)
        $UNINSTALL && delegate_args+=(--uninstall)
        exec "$SCRIPT_DIR/install_claude.sh" "${delegate_args[@]}"
        ;;
    cursor)
        [ -n "$CURSOR_TARGET" ] && delegate_args+=("$CURSOR_TARGET")
        $CHECK     && delegate_args+=(--check)
        $DRY_RUN   && delegate_args+=(--dry-run)
        $UNINSTALL && delegate_args+=(--uninstall)
        exec "$SCRIPT_DIR/install_cursor.sh" "${delegate_args[@]}"
        ;;
esac
