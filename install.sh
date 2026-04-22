#!/usr/bin/env bash
# Praxion Installer — Entry point
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
step()  { printf "    %s\n" "$*"; }

# Prompt for a numbered choice. Sets REPLY to the chosen number.
ask() {
    local default=$1 max=$2
    printf "\n"
    read -rp "  Choice [$default]: " choice
    choice="${choice:-$default}"
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "$max" ]; then
        fail "Invalid choice: $choice"
    fi
    REPLY="$choice"
}

# =============================================================================
# Shared — External API Docs (context-hub CLI + telemetry config)
# =============================================================================

install_chub_cli() {
    header "Shared — External API Docs (context-hub)"

    if ! command -v npm &>/dev/null; then
        step "Node.js not found — skipping context-hub setup"
        step "Install Node.js 18+ and re-run to enable external API docs"
        return
    fi

    cat <<EOF

  ${B}[1] Install context-hub CLI (recommended)${R}
      ${D}Installs chub globally (npm install -g). Curated API docs for${R}
      ${D}600+ libraries (Stripe, OpenAI, AWS, etc.). Used by skills as${R}
      ${D}a fallback and available to all users on this machine.${R}
      ${D}Telemetry disabled by default.${R}

  ${B}[2] Skip${R}
      ${D}No chub CLI. Install later by re-running: ./install.sh${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "context-hub CLI skipped"
        return
    fi

    step "Installing chub CLI globally..."
    if npm install -g @aisuite/chub 2>&1 | tail -1; then
        info "chub CLI installed ($(chub --cli-version 2>/dev/null || echo '?'))"
    else
        warn "Global install failed — re-run or install manually: npm install -g @aisuite/chub"
    fi

    # Disable telemetry persistently
    local chub_config_dir="${HOME}/.chub"
    if [ ! -f "${chub_config_dir}/config.yaml" ]; then
        mkdir -p "$chub_config_dir"
        cat > "${chub_config_dir}/config.yaml" << 'YAML'
telemetry: false
feedback: false
YAML
        info "Telemetry disabled in ~/.chub/config.yaml"
    fi
}

check_chub_cli() {
    printf "\n  ${B}External API Docs (shared):${R}\n"
    if command -v chub &>/dev/null; then
        info "chub CLI installed ($(chub --cli-version 2>/dev/null || echo '?'))"
    else
        warn "chub CLI not installed globally"
    fi
}

uninstall_chub_cli() {
    if command -v chub &>/dev/null; then
        step "Removing chub CLI..."
        npm uninstall -g @aisuite/chub 2>/dev/null \
            && info "chub CLI removed" \
            || warn "chub CLI removal failed"
    fi
}

# =============================================================================
# Overview banner
# =============================================================================

show_overview() {
    local mode=$1
    printf "\n${B}Praxion Installer${R}\n"

    cat <<EOF

  Shared:
    • External API docs (chub CLI — curated docs for 600+ libraries)
EOF

    case "$mode" in
        code)
            cat <<EOF

  Target: ${B}Claude Code${R}

  Components:
    • Personal config  (CLAUDE.md, userPreferences.txt)
    • Rules            (auto-loaded by Claude)
    • i-am plugin      (skills, commands, agents)
    • Chronograph hooks (agent lifecycle observability)
    • CLI scripts       (ccwt — multi-worktree Claude sessions)
    • context-hub MCP   (chub-mcp — native agent tool access)
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
Usage: $(basename "$0") [code|desktop|cursor [path]] [--check] [--dry-run] [--uninstall] [--from-local] [--help]

  code         Install for Claude Code (default)
  desktop      Install for Claude Desktop
  cursor       Install for Cursor: user profile ~/.cursor/ (default)
  cursor PATH  Install for Cursor: per-project at PATH/.cursor/
  --check      Verify installation health
  --dry-run    Show what would be installed (no writes)
  --uninstall  Remove installation
  --relink     Re-symlink config, rules, and scripts (no prompts)
  --from-local Dev mode: install plugin body from local working tree via
               symlink (bypasses the marketplace). Rules/scripts already
               symlink live; this extends uniform local state to the
               plugin body so edits to skills/commands/agents are
               immediate. Only valid with 'code'.
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
RELINK=false
FROM_LOCAL=false
CURSOR_TARGET=""

while [ $# -gt 0 ]; do
    case "$1" in
        code|desktop) MODE="$1" ;;
        cursor)       MODE="cursor"
                      if [ -n "$2" ] && [[ "$2" != --* ]]; then CURSOR_TARGET="$2"; shift; fi ;;
        --check)      CHECK=true ;;
        --dry-run)    DRY_RUN=true ;;
        --uninstall)  UNINSTALL=true ;;
        --relink)     RELINK=true ;;
        --from-local) FROM_LOCAL=true ;;
        -h|--help)    show_usage ;;
        *)            fail "Unknown argument: $1. Use --help for usage." ;;
    esac
    shift
done

# At most one of --check, --dry-run, --uninstall, --relink (first wins)
if $RELINK && ( $CHECK || $DRY_RUN || $UNINSTALL ); then
    warn "Multiple actions requested; using --relink only."
    CHECK=false
    DRY_RUN=false
    UNINSTALL=false
elif $CHECK && ( $DRY_RUN || $UNINSTALL ); then
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
        $CHECK      && delegate_args+=(--check)
        $DRY_RUN    && delegate_args+=(--dry-run)
        $UNINSTALL  && delegate_args+=(--uninstall)
        $RELINK     && delegate_args+=(--relink)
        $FROM_LOCAL && delegate_args+=(--from-local)
        ;;
    cursor)
        [ -n "$CURSOR_TARGET" ] && delegate_args+=("$CURSOR_TARGET")
        $CHECK     && delegate_args+=(--check)
        $DRY_RUN   && delegate_args+=(--dry-run)
        $UNINSTALL && delegate_args+=(--uninstall)
        $RELINK    && delegate_args+=(--relink)
        ;;
esac

# Dispatch to tool-specific script (capture exit code — don't let set -e kill shared steps)
delegate() {
    local rc=0
    case "$MODE" in
        code|desktop) "$SCRIPT_DIR/install_claude.sh" "${delegate_args[@]}" || rc=$? ;;
        cursor)       "$SCRIPT_DIR/install_cursor.sh" "${delegate_args[@]}" || rc=$? ;;
    esac
    return $rc
}

if $RELINK; then
    delegate
elif $CHECK; then
    delegate_rc=0
    delegate || delegate_rc=$?
    check_chub_cli
    exit $delegate_rc
elif $UNINSTALL; then
    delegate
    uninstall_chub_cli
elif $DRY_RUN; then
    check_chub_cli
    delegate
else
    # Install: shared CLI first, then tool-specific
    install_chub_cli
    delegate
fi
