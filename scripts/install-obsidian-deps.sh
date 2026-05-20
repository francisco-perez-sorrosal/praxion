#!/usr/bin/env bash
# Praxion — Obsidian integration dependencies installer.
#
# Provisions kepano/obsidian-skills via the Claude Code marketplace so
# SKILL.md files land at the correct discovery depth (~/.claude/plugins/cache/).
#
# Usage (called from install.sh wrapper functions):
#   install-obsidian-deps.sh               # install
#   install-obsidian-deps.sh --check       # report health
#   install-obsidian-deps.sh --uninstall   # remove plugin
#   install-obsidian-deps.sh --relink      # update plugin to latest version
#
# This script NEVER exits 1 on external failures (network down, claude CLI
# absent, Obsidian Desktop absent) — it warns and returns 0.

set -eo pipefail

PLUGIN_ID="obsidian@obsidian-skills"
MARKETPLACE_SOURCE="kepano/obsidian-skills"

if [ -t 1 ]; then
    B=$'\033[1m' R=$'\033[0m'
else
    B='' R=''
fi

info()  { printf "  ✓ %s\n" "$*"; }
warn()  { printf "  ⚠ %s\n" "$*"; }
step()  { printf "    %s\n" "$*"; }

CHECK=false
UNINSTALL=false
RELINK=false

for arg in "$@"; do
    case "$arg" in
        --check)     CHECK=true ;;
        --uninstall) UNINSTALL=true ;;
        --relink)    RELINK=true ;;
    esac
done

_has_claude_cli()   { command -v claude &>/dev/null; }
_obsidian_present() { command -v obsidian &>/dev/null; }
_plugin_installed() { claude plugin list 2>/dev/null | grep -q "${PLUGIN_ID}"; }

_run_check() {
    printf "\n  ${B}Obsidian integration:${R}\n"
    if ! _has_claude_cli; then
        warn "claude CLI not found on PATH — cannot check plugin status"
    elif _plugin_installed; then
        info "${PLUGIN_ID} installed at user scope"
    else
        warn "${PLUGIN_ID} not installed (run ./install.sh code to install)"
    fi
    if _obsidian_present; then
        info "Obsidian CLI found on PATH"
    else
        warn "Obsidian CLI not found (optional — Obsidian integration activates when Obsidian 1.12+ is installed)"
    fi
}

_run_uninstall() {
    printf "\n  ${B}Uninstall Obsidian integration${R}\n"
    if ! _has_claude_cli; then
        warn "claude CLI not found on PATH — cannot uninstall ${PLUGIN_ID}"
        return
    fi
    if ! _plugin_installed; then
        step "Nothing to uninstall (${PLUGIN_ID} not present)"
        return
    fi
    step "Uninstalling ${PLUGIN_ID}..."
    if claude plugin uninstall "${PLUGIN_ID}" --yes 2>&1; then
        info "${PLUGIN_ID} uninstalled"
    else
        warn "Uninstall failed — try manually: claude plugin uninstall ${PLUGIN_ID}"
    fi
}

_run_relink() {
    if ! _has_claude_cli; then
        warn "claude CLI not found on PATH — cannot update ${PLUGIN_ID}"
        return
    fi
    if ! _plugin_installed; then
        warn "${PLUGIN_ID} not installed; running install instead of update"
        _run_install
        return
    fi
    step "Updating ${PLUGIN_ID} to latest version..."
    if claude plugin update "${PLUGIN_ID}" 2>&1; then
        info "${PLUGIN_ID} updated"
    else
        warn "plugin update failed (network unavailable or marketplace unreachable); skipping"
    fi
}

_run_install() {
    if ! _has_claude_cli; then
        warn "claude CLI not found on PATH — install Claude Code first, then re-run ./install.sh code"
        return
    fi
    if ! _obsidian_present; then
        warn "Obsidian CLI not found — Obsidian integration will activate when you install Obsidian 1.12+"
    fi
    if _plugin_installed; then
        step "${PLUGIN_ID} already installed — skipping"
        step "(use --relink to update to the latest version)"
        return
    fi
    step "Adding kepano marketplace (${MARKETPLACE_SOURCE})..."
    if ! claude plugin marketplace add "${MARKETPLACE_SOURCE}" 2>&1; then
        warn "marketplace add failed (network unavailable or marketplace unreachable)"
        warn "Re-run ./install.sh code once the network is available"
        return
    fi
    step "Installing ${PLUGIN_ID}..."
    if claude plugin install "${PLUGIN_ID}" 2>&1; then
        info "${PLUGIN_ID} installed"
    else
        warn "plugin install failed — check output above"
        warn "Re-run ./install.sh code once the issue is resolved"
    fi
}

if $CHECK; then
    _run_check
elif $UNINSTALL; then
    _run_uninstall
elif $RELINK; then
    _run_relink
else
    _run_install
fi
