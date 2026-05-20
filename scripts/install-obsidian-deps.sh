#!/usr/bin/env bash
# Praxion — Obsidian integration dependencies installer.
#
# Provisions the kepano/obsidian-skills checkout and writes a marker file so
# the onboarding chain can locate it via KEPANO_SKILLS_ROOT.
#
# Usage (called from install.sh wrapper functions):
#   install-obsidian-deps.sh               # install
#   install-obsidian-deps.sh --check       # report health
#   install-obsidian-deps.sh --uninstall   # prompt + remove
#   install-obsidian-deps.sh --relink      # git pull --ff-only
#
# This script NEVER exits 1 on external failures (network down, Obsidian
# Desktop absent) — it warns and returns 0. Exit 1 is reserved for
# programming errors (unexpected script bugs). Callers rely on this guarantee.

set -eo pipefail

TARGET_DIR="${KEPANO_SKILLS_ROOT:-${HOME}/.local/share/praxion/kepano-skills}"
MARKER_FILE="${HOME}/.config/praxion/obsidian-skills.path"
KEPANO_REPO="https://github.com/kepano/obsidian-skills"

# ---------------------------------------------------------------------------
# Output helpers — match the style used in install.sh
# ---------------------------------------------------------------------------

if [ -t 1 ]; then
    B=$'\033[1m' D=$'\033[2m' R=$'\033[0m'
else
    B='' D='' R=''
fi

info()  { printf "  ✓ %s\n" "$*"; }
warn()  { printf "  ⚠ %s\n" "$*"; }
step()  { printf "    %s\n" "$*"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Soft-check helpers
# ---------------------------------------------------------------------------

_has_git() {
    command -v git &>/dev/null
}

_kepano_installed() {
    test -d "${TARGET_DIR}/.git"
}

_obsidian_present() {
    command -v obsidian &>/dev/null
}

_kepano_revision() {
    # Print the short HEAD revision of the installed checkout, or "?" on failure.
    git -C "${TARGET_DIR}" rev-parse --short HEAD 2>/dev/null || printf '?'
}

# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------

_run_check() {
    printf "\n  ${B}Obsidian integration:${R}\n"

    if _kepano_installed; then
        info "kepano-skills present at ${TARGET_DIR} (rev $(_kepano_revision))"
    else
        warn "kepano-skills not installed (run ./install.sh code to install)"
    fi

    if _obsidian_present; then
        info "Obsidian CLI found on PATH"
    else
        warn "Obsidian CLI not found (optional — Obsidian integration activates when Obsidian 1.12+ is installed)"
    fi
}

# ---------------------------------------------------------------------------
# --uninstall mode
# ---------------------------------------------------------------------------

_run_uninstall() {
    printf "\n  ${B}Uninstall Obsidian integration${R}\n"

    if ! _kepano_installed && [ ! -f "${MARKER_FILE}" ]; then
        step "Nothing to uninstall (kepano-skills not present)"
        return
    fi

    cat <<EOF

  ${B}[1] Remove kepano-skills checkout and marker file${R}
      ${D}Deletes ${TARGET_DIR}${R}
      ${D}and marker file ${MARKER_FILE}${R}

  ${B}[2] Skip${R}
      ${D}Leave kepano-skills in place.${R}
EOF
    printf "\n"
    read -rp "  Choice [2]: " choice
    choice="${choice:-2}"

    case "$choice" in
        1)
            if _kepano_installed || [ -d "${TARGET_DIR}" ]; then
                step "Removing ${TARGET_DIR} ..."
                rm -rf "${TARGET_DIR}" \
                    && info "kepano-skills removed" \
                    || warn "removal failed (check permissions)"
            fi
            if [ -f "${MARKER_FILE}" ]; then
                rm -f "${MARKER_FILE}" \
                    && info "marker file removed" \
                    || warn "marker file removal failed"
            fi
            ;;
        2)
            step "Skipping uninstall"
            ;;
        *)
            warn "Invalid choice '${choice}' — skipping uninstall"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# --relink mode
# ---------------------------------------------------------------------------

_run_relink() {
    if ! _kepano_installed; then
        warn "kepano-skills not installed; running install instead of relink"
        _run_install
        return
    fi

    step "Refreshing kepano-skills (git pull --ff-only)..."
    if git -C "${TARGET_DIR}" pull --ff-only 2>&1; then
        info "kepano-skills refreshed (rev $(_kepano_revision))"
    else
        warn "git pull --ff-only failed (diverged commits or network issue); skipping"
        warn "To force-refresh: rm -rf ${TARGET_DIR} && ./install.sh code"
    fi
}

# ---------------------------------------------------------------------------
# Install mode (no flag)
# ---------------------------------------------------------------------------

_run_install() {
    # Soft-check Obsidian Desktop — warn-only, never block.
    if ! _obsidian_present; then
        warn "Obsidian CLI not found — Obsidian integration will activate when you install Obsidian 1.12+"
        warn "and run './install.sh code --relink'"
    fi

    # Idempotency check.
    if _kepano_installed; then
        step "kepano-skills already installed at ${TARGET_DIR} — skipping clone"
        step "(use --relink to refresh)"
        return
    fi

    if ! _has_git; then
        warn "git not found on PATH — cannot clone kepano/obsidian-skills"
        warn "Install git and re-run: ./install.sh code"
        return
    fi

    step "Cloning kepano/obsidian-skills to ${TARGET_DIR} ..."
    if git clone --depth 1 "${KEPANO_REPO}" "${TARGET_DIR}" 2>&1; then
        info "kepano-skills installed (rev $(_kepano_revision))"
        _write_marker
    else
        warn "git clone failed (network unavailable or repo unreachable)"
        warn "Re-run ./install.sh code once the network is available"
        # Never exit 1 on network failure — caller continues.
        return
    fi
}

_write_marker() {
    mkdir -p "${HOME}/.config/praxion"
    printf '%s\n' "${TARGET_DIR}" > "${MARKER_FILE}"
    info "marker written to ${MARKER_FILE}"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if $CHECK; then
    _run_check
elif $UNINSTALL; then
    _run_uninstall
elif $RELINK; then
    _run_relink
else
    _run_install
fi
