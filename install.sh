#!/usr/bin/env bash
# Praxion Installer — Entry point
#
# Routes to install_claude.sh (Claude Code / Claude Desktop),
# install_cursor.sh (Cursor), or install_codex.sh (AGENTS.md-aware agents).
# See --help for usage.
#
#   ./install.sh [code|desktop|cursor [path]|codex path] [--native|--compat-only] [--check] [--dry-run] [--uninstall] [--help]

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
# Shared — Optional Metrics Tool (scc for /project-metrics SLOC counts)
# =============================================================================

install_scc_cli() {
    header "Shared — Optional Metrics Tool (scc)"

    if command -v scc &>/dev/null; then
        info "scc already installed ($(scc --version 2>/dev/null | head -1 || echo '?'))"
        return
    fi

    cat <<EOF

  ${B}[1] Install scc (recommended if you will run /project-metrics)${R}
      ${D}scc is a fast source-lines-of-code counter used by the${R}
      ${D}/project-metrics command to produce accurate SLOC and${R}
      ${D}per-language breakdowns. Without it, the metrics report${R}
      ${D}falls back to a stdlib counter that misses language-specific${R}
      ${D}detail.${R}

  ${B}[2] Skip${R}
      ${D}No scc. /project-metrics will degrade gracefully and note${R}
      ${D}the missing tool in its report. Install later via:${R}
      ${D}  brew install scc            (macOS, preferred)${R}
      ${D}  go install github.com/boyter/scc/v3@latest${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "scc skipped"
        return
    fi

    # Prefer brew on macOS; fall back to go install; otherwise warn + instruct.
    if command -v brew &>/dev/null; then
        step "Installing scc via Homebrew..."
        if brew install scc 2>&1 | tail -1; then
            info "scc installed ($(scc --version 2>/dev/null | head -1 || echo '?'))"
            return
        fi
        warn "brew install scc failed; trying 'go install' as fallback"
    fi

    if command -v go &>/dev/null; then
        step "Installing scc via 'go install'..."
        if go install github.com/boyter/scc/v3@latest 2>&1 | tail -1; then
            info "scc installed ($(scc --version 2>/dev/null | head -1 || echo 'check PATH'))"
            step "Ensure \$(go env GOPATH)/bin is on PATH for scc to be discoverable"
        else
            warn "go install scc failed; install manually: https://github.com/boyter/scc"
        fi
        return
    fi

    warn "Neither brew nor go found on PATH"
    step "Install manually: https://github.com/boyter/scc"
}

check_scc_cli() {
    printf "\n  ${B}Optional Metrics Tool (scc):${R}\n"
    if command -v scc &>/dev/null; then
        info "scc installed ($(scc --version 2>/dev/null | head -1 || echo '?'))"
    else
        warn "scc not installed (optional — /project-metrics degrades gracefully)"
    fi
}

uninstall_scc_cli() {
    if ! command -v scc &>/dev/null; then
        return
    fi
    step "Removing scc..."
    if command -v brew &>/dev/null && brew list scc &>/dev/null; then
        brew uninstall scc 2>/dev/null \
            && info "scc removed (brew)" \
            || warn "scc removal via brew failed"
    else
        warn "scc was likely installed via 'go install'; remove manually from \$(go env GOPATH)/bin"
    fi
}

# =============================================================================
# Shared — Python Tooling for Praxion (uv + PEP 735 dev group)
# =============================================================================

install_python_tooling() {
    header "Shared — Python Tooling for Praxion"

    local has_uv=false
    local has_venv_deps=false

    command -v uv &>/dev/null && has_uv=true
    if [ -d "${SCRIPT_DIR}/.venv" ] && \
       "${SCRIPT_DIR}/.venv/bin/python3" -c "import pytest_cov" &>/dev/null; then
        has_venv_deps=true
    fi

    if $has_uv && $has_venv_deps; then
        info "uv installed ($(uv --version 2>/dev/null))"
        info "Praxion .venv present with pytest-cov importable"
        return
    fi

    cat <<EOF

  ${B}[1] Install Python tooling for Praxion (recommended)${R}
      ${D}(a) Installs uv if missing — Python package manager used by${R}
      ${D}    the metrics collectors (complexipy/lizard/pydeps via uvx)${R}
      ${D}    and as Praxion's own env manager.${R}
      ${D}(b) Runs 'uv sync --group dev' at the repo root to install${R}
      ${D}    Praxion's PEP 735 dev group (pytest + pytest-cov) into${R}
      ${D}    .venv/ (gitignored). Produces uv.lock at root — commit${R}
      ${D}    it once so the dev env is reproducible across machines.${R}
      ${D}Required for 'pytest' and '/project-metrics --refresh-coverage'${R}
      ${D}to work against Praxion itself.${R}

  ${B}[2] Skip${R}
      ${D}No Python-level setup. /project-metrics still runs but the${R}
      ${D}Tier 1 collectors will downgrade (skip markers in the report)${R}
      ${D}and --refresh-coverage will warn and continue. Install later:${R}
      ${D}  curl -LsSf https://astral.sh/uv/install.sh | sh${R}
      ${D}  cd praxion && uv sync --group dev${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "Python tooling skipped"
        return
    fi

    # (a) Install uv if missing
    if ! $has_uv; then
        step "Installing uv via Astral installer..."
        step "(running: curl -LsSf https://astral.sh/uv/install.sh | sh)"
        if curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1 | tail -3; then
            # uv typically lands in ~/.local/bin; ensure it's on PATH this session
            export PATH="${HOME}/.local/bin:${PATH}"
            if command -v uv &>/dev/null; then
                info "uv installed ($(uv --version 2>/dev/null))"
                has_uv=true
            else
                warn "uv installed but not yet on PATH — restart your shell and re-run install.sh"
                return
            fi
        else
            warn "uv install failed — install manually: https://docs.astral.sh/uv/"
            return
        fi
    fi

    # (b) Sync dev group
    step "Syncing Praxion dev dependencies (uv sync --group dev)..."
    if (cd "$SCRIPT_DIR" && uv sync --group dev 2>&1 | tail -5); then
        info "Praxion .venv ready under ${SCRIPT_DIR}/.venv"
        if [ -f "${SCRIPT_DIR}/uv.lock" ]; then
            step "uv.lock generated at repo root — run 'git add uv.lock && git commit' once to lock versions"
        fi
    else
        warn "uv sync failed; run manually: cd $SCRIPT_DIR && uv sync --group dev"
    fi
}

check_python_tooling() {
    printf "\n  ${B}Python Tooling for Praxion:${R}\n"
    if command -v uv &>/dev/null; then
        info "uv installed ($(uv --version 2>/dev/null))"
    else
        warn "uv not installed (optional — Tier 1 metrics + dev-group sync)"
    fi
    if [ -d "${SCRIPT_DIR}/.venv" ] && \
       "${SCRIPT_DIR}/.venv/bin/python3" -c "import pytest_cov" &>/dev/null; then
        info "Praxion .venv present with pytest-cov"
    else
        warn "Praxion .venv missing or pytest-cov not installed — run install.sh"
    fi
}

uninstall_python_tooling() {
    if [ -d "${SCRIPT_DIR}/.venv" ]; then
        step "Removing Praxion .venv..."
        rm -rf "${SCRIPT_DIR}/.venv" \
            && info "Praxion .venv removed" \
            || warn ".venv removal failed"
    fi
    if command -v uv &>/dev/null; then
        step "uv is a user-wide tool (not auto-removing). Remove manually if desired:"
        step "  rm -rf ~/.local/bin/uv ~/.local/share/uv ~/.cache/uv"
    fi
}

# =============================================================================
# Overview banner
# =============================================================================

show_overview() {
    local mode=$1
    printf "\n${B}Praxion Installer${R}\n"

    if [ "$mode" != "codex" ]; then
        cat <<EOF

  Shared:
    • External API docs (chub CLI — curated docs for 600+ libraries)
    • Optional metrics tool (scc — SLOC counter used by /project-metrics)
    • Python tooling (uv + pytest/pytest-cov for Praxion's own tests and coverage)
EOF
    fi

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
        codex)
            cat <<EOF

  Target: ${B}AGENTS.md-aware agents${R}

  Components:
    • Project-local AGENTS.md managed preamble  (Praxion Codex philosophy + adapter)
    • Project-local Codex config merge  (<path>/.codex/config.toml for hooks, MCP, and CLAUDE.md fallback)
    • Project-local skill and agent wrappers  (<path>/.agents/, <path>/.codex/agents/)
    • Pointers to Praxion source artifacts (no copied canonical rules/skills/agents)
    • Compatibility map for direct reuse vs adapter-required surfaces
EOF
            ;;
    esac
}

# =============================================================================
# Usage
# =============================================================================

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [code|desktop|cursor [path]|codex path] [--check] [--dry-run] [--uninstall] [--help]

  code         Install for Claude Code (default)
  desktop      Install for Claude Desktop
  cursor       Install for Cursor: user profile ~/.cursor/ (default)
  cursor PATH  Install for Cursor: per-project at PATH/.cursor/
  codex PATH   Install a project-local AGENTS.md managed preamble for Codex and other
               AGENTS.md-aware coding agents plus project-local .codex/.agents
               adapter surfaces
  --native     With 'codex', export Codex-native Praxion agent wrappers and the
               project-local .codex/.agents adapter surfaces
               (default; accepted for readability)
  --compat-only
               With 'codex', only install the AGENTS.md compatibility pointer
  --check      Verify installation health
  --dry-run    Show what would be installed (no writes)
  --uninstall  Remove installation
  --relink     Re-symlink config, rules, and scripts (no prompts)
  --complete-install
               Marketplace-only users: finish a 'claude plugin install
               i-am@bit-agora' by symlinking rules, CLI scripts, and
               (optionally) context-hub MCP — the surfaces the plugin
               mechanism does not cover natively. Prompts before each
               system-level change. Reachable via /praxion-complete-install
               inside a Claude Code session. Only valid with 'code'.
  --complete-uninstall
               Reverse of --complete-install: remove the rule/script
               symlinks that point at the plugin cache, and optionally
               remove context-hub MCP. Plugin body is preserved — run
               'claude plugin uninstall i-am' separately to remove it.
               Only valid with 'code'.
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
COMPLETE_INSTALL=false
COMPLETE_UNINSTALL=false
NATIVE=false
COMPAT_ONLY=false
CURSOR_TARGET=""
CODEX_TARGET=""

while [ $# -gt 0 ]; do
    case "$1" in
        code|desktop) MODE="$1" ;;
        cursor)       MODE="cursor"
                      if [ -n "$2" ] && [[ "$2" != --* ]]; then CURSOR_TARGET="$2"; shift; fi ;;
        codex)        MODE="codex"
                      if [ -n "$2" ] && [[ "$2" != --* ]]; then CODEX_TARGET="$2"; shift; fi ;;
        --native)     NATIVE=true ;;
        --compat-only) COMPAT_ONLY=true ;;
        --check)      CHECK=true ;;
        --dry-run)    DRY_RUN=true ;;
        --uninstall)  UNINSTALL=true ;;
        --relink)     RELINK=true ;;
        --complete-install)   COMPLETE_INSTALL=true ;;
        --complete-uninstall) COMPLETE_UNINSTALL=true ;;
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
        $CHECK              && delegate_args+=(--check)
        $DRY_RUN            && delegate_args+=(--dry-run)
        $UNINSTALL          && delegate_args+=(--uninstall)
        $RELINK             && delegate_args+=(--relink)
        $COMPLETE_INSTALL   && delegate_args+=(--complete-install)
        $COMPLETE_UNINSTALL && delegate_args+=(--complete-uninstall)
        ;;
    cursor)
        [ -n "$CURSOR_TARGET" ] && delegate_args+=("$CURSOR_TARGET")
        $CHECK     && delegate_args+=(--check)
        $DRY_RUN   && delegate_args+=(--dry-run)
        $UNINSTALL && delegate_args+=(--uninstall)
        $RELINK    && delegate_args+=(--relink)
        ;;
    codex)
        [ -n "$CODEX_TARGET" ] && delegate_args+=("$CODEX_TARGET")
        $NATIVE       && delegate_args+=(--native)
        $COMPAT_ONLY && delegate_args+=(--compat-only)
        $CHECK     && delegate_args+=(--check)
        $DRY_RUN   && delegate_args+=(--dry-run)
        $UNINSTALL && delegate_args+=(--uninstall)
        ;;
esac

# Dispatch to tool-specific script (capture exit code — don't let set -e kill shared steps)
delegate() {
    local rc=0
    case "$MODE" in
        code|desktop) "$SCRIPT_DIR/install_claude.sh" "${delegate_args[@]}" || rc=$? ;;
        cursor)       "$SCRIPT_DIR/install_cursor.sh" "${delegate_args[@]}" || rc=$? ;;
        codex)        "$SCRIPT_DIR/install_codex.sh" "${delegate_args[@]}" || rc=$? ;;
    esac
    return $rc
}

if [ "$MODE" = "codex" ]; then
    if $RELINK; then
        warn "--relink does not apply to codex; using regular install/check/dry-run flags."
    fi
    delegate
elif $RELINK; then
    delegate
elif $CHECK; then
    delegate_rc=0
    delegate || delegate_rc=$?
    check_chub_cli
    check_scc_cli
    check_python_tooling
    exit $delegate_rc
elif $UNINSTALL; then
    delegate
    uninstall_chub_cli
    uninstall_scc_cli
    uninstall_python_tooling
elif $DRY_RUN; then
    check_chub_cli
    check_scc_cli
    check_python_tooling
    delegate
else
    # Install: shared CLIs first, then tool-specific
    install_chub_cli
    install_scc_cli
    install_python_tooling
    delegate
fi
