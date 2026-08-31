#!/usr/bin/env bash
# Praxion — Claude Code / Claude Desktop installer
#
# Installs personal config, rules, and the praxion plugin into Claude Code or
# configures MCP servers for Claude Desktop. Invoked by install.sh for code|desktop.
#
# Usage:
#   ./install_claude.sh code|desktop [--check] [--dry-run] [--uninstall] [--relink]
#                                    [--complete-install] [--complete-uninstall] [--help]

set -eo pipefail

# =============================================================================
# Constants
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_CONFIG_DIR="${SCRIPT_DIR}/claude/config"

# Shared linking helpers (rules linking used by both Claude and Cursor installers)
# shellcheck source=lib/install_shared.sh
source "${SCRIPT_DIR}/lib/install_shared.sh"
PLUGIN_NAME="praxion"
MARKETPLACE_NAME="bit-agora"
MARKETPLACE_SOURCE="francisco-perez-sorrosal/bit-agora"
PLUGIN_CACHE_DIR="${HOME}/.claude/plugins/cache/${MARKETPLACE_NAME}/${PLUGIN_NAME}"

# Personal identifiers rendered into claude/config/CLAUDE.md (the Personal Info
# section). Defaults are the original author's — users can accept them as-is
# or customize during the install prompt; saved values persist across re-runs
# in .personal_info.env (gitignored).
DEFAULT_USERNAME="@fperezsorrosal"
DEFAULT_EMAIL="fperezsorrosal@gmail.com"
DEFAULT_GITHUB_URL="https://github.com/francisco-perez-sorrosal"
PERSONAL_INFO_ENV="${CLAUDE_CONFIG_DIR}/.personal_info.env"
CLAUDE_MD_TEMPLATE="${CLAUDE_CONFIG_DIR}/CLAUDE.md.tmpl"
CLAUDE_MD_RENDERED="${CLAUDE_CONFIG_DIR}/CLAUDE.md"

# =============================================================================
# Terminal formatting (disabled when not a TTY)
# =============================================================================

if [ -t 1 ]; then
    B=$'\033[1m' D=$'\033[2m' R=$'\033[0m'
else
    B='' D='' R=''
fi

# =============================================================================
# Helpers
# =============================================================================

info()   { printf "  ✓ %s\n" "$*"; }
warn()   { printf "  ⚠ %s\n" "$*"; }
fail()   { printf "  ✗ %s\n" "$*" >&2; exit 1; }
header() { printf "\n${B}%s${R}\n" "$*"; }
step()   { printf "    %s\n" "$*"; }

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

require_cmd() {
    local cmd=$1 msg=$2
    command -v "$cmd" &>/dev/null || fail "$msg"
}

link_item() {
    local source="$1" target="$2" label="$3"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        info "${label} (already linked)"
        return 0
    fi
    if [ -e "$target" ]; then
        warn "${target} exists and would be overwritten"
        printf "    Replace? [y/N]: "
        read -rn 1 answer
        printf "\n"
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            step "Skipped ${label}"
            return 0
        fi
    fi
    ln -sf "$source" "$target"
    info "${label}"
}

# =============================================================================
# Symlink management — single source of truth for all symlink-based artifacts
# =============================================================================

# Predicate: should scripts/<file> be linked into ~/.local/bin/?
# Returns 0 (true) only for user-facing CLI tools — regular executable files
# whose basename is NOT an internal git helper (merge driver, git-* hook).
# See dec-042 for rationale.
script_is_user_facing() {
    local path="$1"
    [ -f "$path" ] && [ -x "$path" ] || return 1
    local name
    name="$(basename "$path")"
    case "$name" in
        merge_driver_*|git-*-hook.sh) return 1 ;;
    esac
    return 0
}

# Sweep ~/.local/bin/ for symlinks pointing into this repo's scripts/
# directory that no longer pass the install filter (dec-042). Covers the
# upgrade path from older installers that linked CLAUDE.md, merge drivers,
# test files, or scripts that have since been renamed/removed.
sweep_stale_script_symlinks() {
    local scripts_src="${SCRIPT_DIR}/scripts"
    local bin_dir="${HOME}/.local/bin"
    [ -d "$bin_dir" ] && [ -d "$scripts_src" ] || return 0
    for link in "$bin_dir"/*; do
        [ -L "$link" ] || continue
        local target
        target="$(readlink "$link")"
        case "$target" in
            "$scripts_src"/*) ;;
            *) continue ;;
        esac
        if ! script_is_user_facing "$target"; then
            step "Removing stale symlink: ${link}"
            rm "$link"
        fi
    done
}

clean_stale_symlinks() {
    local dest_dir="${HOME}/.claude"
    local list_file="${CLAUDE_CONFIG_DIR}/stale_symlinks.txt"
    if [ -f "$list_file" ]; then
        while IFS= read -r item || [ -n "$item" ]; do
            [ -z "$item" ] && continue
            local target="$dest_dir/$item"
            if [ -L "$target" ]; then
                step "Removing stale symlink: ${target}"
                rm "$target"
            fi
        done < "$list_file"
    fi
    for subdir in skills commands; do
        local dest_subdir="$dest_dir/$subdir"
        if [ -d "$dest_subdir" ]; then
            for item in "$dest_subdir"/*; do
                if [ -L "$item" ]; then
                    step "Removing stale symlink: ${item}"
                    rm "$item"
                fi
            done
            rmdir "$dest_subdir" 2>/dev/null || true
        fi
    done
    sweep_stale_script_symlinks
}

# =============================================================================
# Personal identifiers — render CLAUDE.md from template
# =============================================================================
#
# ${CLAUDE_CONFIG_DIR}/CLAUDE.md.tmpl contains {{USERNAME}}, {{EMAIL}},
# {{GITHUB_URL}} placeholders that get substituted into the rendered
# CLAUDE.md (gitignored) at install time. The rendered file is what the
# symlink points at, so the user's global Claude prompt always reflects
# their own identifiers, not the original author's.

prompt_personal_info() {
    # If saved values exist and --reconfigure was not requested, reuse silently.
    if [ -f "$PERSONAL_INFO_ENV" ] && ! $RECONFIGURE; then
        # shellcheck source=/dev/null
        source "$PERSONAL_INFO_ENV"
        info "Personal info loaded from $(basename "$PERSONAL_INFO_ENV")"
        return
    fi

    header "Step 0 — Personal identifiers"
    cat <<EOF

  These values fill the 'Personal Info' section of your global Claude
  prompt (~/.claude/CLAUDE.md). Press Enter to accept the defaults and
  continue, or type [n] to customize each value.

  username:  ${B}${DEFAULT_USERNAME}${R}
  email:     ${B}${DEFAULT_EMAIL}${R}
  github:    ${B}${DEFAULT_GITHUB_URL}${R}

EOF
    printf "  Use defaults? [Y/n]: "
    read -r answer

    if [[ "$answer" =~ ^[Nn]$ ]]; then
        read -rp "  Username (e.g. @alice) [${DEFAULT_USERNAME}]: " input
        PRAXION_USERNAME="${input:-$DEFAULT_USERNAME}"
        read -rp "  Email [${DEFAULT_EMAIL}]: " input
        PRAXION_EMAIL="${input:-$DEFAULT_EMAIL}"
        read -rp "  GitHub URL [${DEFAULT_GITHUB_URL}]: " input
        PRAXION_GITHUB_URL="${input:-$DEFAULT_GITHUB_URL}"
    else
        PRAXION_USERNAME="$DEFAULT_USERNAME"
        PRAXION_EMAIL="$DEFAULT_EMAIL"
        PRAXION_GITHUB_URL="$DEFAULT_GITHUB_URL"
    fi

    # Persist so re-runs (plugin updates, --relink) don't re-prompt.
    # Use printf %q to quote values safely for shell sourcing.
    {
        printf 'PRAXION_USERNAME=%q\n' "$PRAXION_USERNAME"
        printf 'PRAXION_EMAIL=%q\n' "$PRAXION_EMAIL"
        printf 'PRAXION_GITHUB_URL=%q\n' "$PRAXION_GITHUB_URL"
    } > "$PERSONAL_INFO_ENV"
    info "Saved to $(basename "$PERSONAL_INFO_ENV") (gitignored)"
}

render_claude_md() {
    if [ ! -f "$CLAUDE_MD_TEMPLATE" ]; then
        fail "Template not found: $CLAUDE_MD_TEMPLATE"
    fi

    # Delegate substitution to the extracted Python helper.  The script handles
    # {{USERNAME}}, {{EMAIL}}, {{GITHUB_URL}} and logs residual placeholders to
    # stderr without failing — matching the warn path below.
    python3 "${SCRIPT_DIR}/scripts/render_claude_md.py" \
        "$CLAUDE_MD_TEMPLATE" "$CLAUDE_MD_RENDERED" \
        "$PRAXION_USERNAME" "$PRAXION_EMAIL" "$PRAXION_GITHUB_URL"

    # Guard against forgotten placeholders (e.g., a new {{FOO}} added to the
    # template but not to render_claude_md) — surface it loudly.
    if grep -q '{{[A-Z_]\+}}' "$CLAUDE_MD_RENDERED" 2>/dev/null; then
        warn "Rendered CLAUDE.md still contains unsubstituted placeholders"
        grep -n '{{[A-Z_]\+}}' "$CLAUDE_MD_RENDERED" | sed 's/^/    /'
    else
        info "Rendered CLAUDE.md (${PRAXION_USERNAME})"
    fi
}

relink_all() {
    # 1. Personal config
    local src_dir="$CLAUDE_CONFIG_DIR"
    local dest_dir="${HOME}/.claude"
    local list_file="${CLAUDE_CONFIG_DIR}/config_items.txt"
    mkdir -p "${dest_dir}"

    if [ ! -f "$list_file" ]; then
        fail "Claude config list not found: $list_file"
    fi
    local config_count=0
    while IFS= read -r item || [ -n "$item" ]; do
        [ -z "$item" ] && continue
        if [ -e "$src_dir/$item" ]; then
            ln -sf "$src_dir/$item" "$dest_dir/$item"
            config_count=$((config_count + 1))
        fi
    done < "$list_file"
    info "Config: ${config_count} items linked"

    # 2. Rules (shared logic — see lib/install_shared.sh)
    link_rules "${SCRIPT_DIR}/rules" "${HOME}/.claude/rules"
    info "Rules: ${LINK_RULES_COUNT} files linked"

    # 3. CLI scripts
    local scripts_src="${SCRIPT_DIR}/scripts"
    local bin_dir="${HOME}/.local/bin"

    if [ -d "$scripts_src" ] && [ -n "$(ls -A "$scripts_src" 2>/dev/null)" ]; then
        mkdir -p "$bin_dir"
        local scripts_count=0
        for script in "$scripts_src"/*; do
            # Combined predicate (dec-042): user-facing scripts are regular
            # files with the executable bit set. Internal helpers invoked by
            # git (merge drivers, git-* hooks) must stay out of $PATH even
            # though they are executable.
            [ -f "$script" ] && [ -x "$script" ] || continue
            local name
            name="$(basename "$script")"
            case "$name" in
                merge_driver_*|git-*-hook.sh) continue ;;
            esac
            ln -sf "$script" "${bin_dir}/${name}"
            scripts_count=$((scripts_count + 1))
        done
        info "Scripts: ${scripts_count} files linked"
    fi

    # 4. onboard-project entry (also linked by the generic scripts/ loop above;
    # kept explicit for clarity since it is the single onboarding entry point)
    if [ -f "${SCRIPT_DIR}/scripts/onboard-project" ] && [ -x "${SCRIPT_DIR}/scripts/onboard-project" ]; then
        mkdir -p "$bin_dir"
        link_item "${SCRIPT_DIR}/scripts/onboard-project" "${bin_dir}/onboard-project" "onboard-project (project onboarding entry)"
    fi

    # PATH check for scripts
    if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
        warn "~/.local/bin is not in PATH"
        step "Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

# =============================================================================
# Git merge drivers and hooks for .ai-state/ reconciliation
# =============================================================================

# Install one finalize git hook as a symlink to the multiplexed dispatcher.
# Idempotent: a correctly-pointing symlink is a no-op. Legacy Praxion copies
# (pre-refactor cp-installed hooks containing finalize_adrs / reconcile_ai_state)
# are replaced silently. Non-Praxion hooks are backed up to <name>.pre-praxion.
#
# Args: <repo-root> <dispatcher-target> <hook-name>
install_finalize_hook() {
    local repo_root="$1"
    local target="$2"
    local hook_name="$3"
    local dst="${repo_root}/.git/hooks/${hook_name}"

    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$target" ]; then
        info "${hook_name} hook: already linked"
        return 0
    fi

    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        if grep -qE "finalize_adrs|reconcile_ai_state|finalize_chain" "$dst" 2>/dev/null; then
            : # Legacy Praxion-managed hook — safe to replace.
        else
            warn "Existing ${hook_name} hook is non-Praxion — backing up to ${hook_name}.pre-praxion"
            mv "$dst" "${dst}.pre-praxion"
        fi
    fi

    ln -sf "$target" "$dst"
    info "${hook_name} hook → scripts/git-finalize-hook.sh"
}

install_git_merge_infra() {
    # Custom merge drivers for structured .ai-state/ files.
    # These are invoked by git during merge when .gitattributes routes files
    # to them, preventing line-based merge from corrupting JSON/JSONL data.
    # Drivers are per-repo config (not global) — safe for multi-repo setups.

    header "Step 2 — Git merge infrastructure"

    local repo_root
    repo_root="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"
    if [ -z "$repo_root" ]; then
        warn "Not a git repository — skipping merge drivers"
        return
    fi

    # Register merge drivers (references scripts/ in the repo)
    git -C "$repo_root" config merge.observations-jsonl.name "Observations JSONL merge"
    git -C "$repo_root" config merge.observations-jsonl.driver "python3 scripts/merge_driver_observations.py %O %A %B"

    info "Merge driver: observations-jsonl"

    # Install three git hooks (post-merge, post-commit, post-checkout) as
    # symlinks pointing at the multiplexed dispatcher scripts/git-finalize-hook.sh.
    # State-driven finalization: any path landing drafts on main (ff merge,
    # direct commit, rebase, fresh clone, branch reset) eventually triggers
    # one of these and finalizes. The dispatcher reads basename($0) to
    # determine which trigger fired; gate logic lives in finalize_chain.sh.
    local finalize_hook_target="${SCRIPT_DIR}/scripts/git-finalize-hook.sh"

    if [ -f "$finalize_hook_target" ]; then
        install_finalize_hook "$repo_root" "$finalize_hook_target" post-merge
        install_finalize_hook "$repo_root" "$finalize_hook_target" post-commit
        install_finalize_hook "$repo_root" "$finalize_hook_target" post-checkout
    fi

    # Activate Praxion's commit gate via the pre-commit framework. The five
    # author gates (shipped-artifact isolation, canonical-block sync, diagram
    # regen, AaC golden-rule, rules-manifest drift) plus ruff + gitleaks live in
    # .pre-commit-config.yaml (repo:local + standard hooks); `pre-commit install`
    # writes the framework dispatcher into .git/hooks/pre-commit. This is
    # Praxion's own author repo — user projects get a tailored inline hook from
    # /onboard-project Phase 4 instead. Rationale: rules/swe/coding-style.md
    # (Baseline Configuration) + rules/swe/shipped-artifact-isolation.md.
    install_praxion_pre_commit "$repo_root"
}

install_praxion_pre_commit() {
    local repo_root="$1"
    local config="${repo_root}/.pre-commit-config.yaml"
    local precommit_dst="${repo_root}/.git/hooks/pre-commit"

    [ -f "$config" ] || return 0

    if $CHECK || $DRY_RUN; then
        if [ -f "$precommit_dst" ] && grep -q "pre-commit" "$precommit_dst" 2>/dev/null; then
            info "Pre-commit hook: pre-commit framework dispatcher present"
        else
            info "Pre-commit hook: would run 'pre-commit install' to activate the commit gate"
        fi
        return 0
    fi

    # Resolve the pre-commit CLI — direct, else via the repo's uv dev env.
    local pc=""
    if command -v pre-commit >/dev/null 2>&1; then
        pc="pre-commit"
    elif command -v uv >/dev/null 2>&1; then
        pc="uv run pre-commit"
    fi
    if [ -z "$pc" ]; then
        warn "pre-commit not available — activate the commit gate manually:"
        warn "    uv sync --group dev && uv run pre-commit install"
        return 0
    fi

    # Back up a genuinely foreign existing hook (neither a pre-commit dispatcher
    # nor a legacy Praxion symlink/copy).
    if [ -e "$precommit_dst" ] && [ ! -L "$precommit_dst" ] \
        && ! grep -qE "pre-commit|check_shipped_artifact_isolation" "$precommit_dst" 2>/dev/null; then
        warn "Existing pre-commit hook is non-Praxion — backing up to pre-commit.pre-praxion"
        mv "$precommit_dst" "${precommit_dst}.pre-praxion"
    fi
    # Remove a dangling/legacy symlink (e.g., to the retired git-pre-commit-hook.sh)
    # so the framework installs cleanly.
    [ -L "$precommit_dst" ] && rm -f "$precommit_dst"

    if ( cd "$repo_root" && $pc install >/dev/null 2>&1 ); then
        info "Pre-commit hook installed via the pre-commit framework"
    else
        warn "pre-commit install failed — run 'uv run pre-commit install' from the repo root"
    fi
}

# =============================================================================
# Plugin installation
# =============================================================================

plugin_is_orphaned() {
    local marker
    marker=$(find "$PLUGIN_CACHE_DIR" -name '.orphaned_at' 2>/dev/null | head -1)
    [ -n "$marker" ]
}

plugin_is_installed() {
    local installed_file="${HOME}/.claude/plugins/installed_plugins.json"
    [ -f "$installed_file" ] && grep -q "${PLUGIN_NAME}@${MARKETPLACE_NAME}" "$installed_file"
}

marketplace_is_registered() {
    local known_file="${HOME}/.claude/plugins/known_marketplaces.json"
    [ -f "$known_file" ] && grep -q "${MARKETPLACE_NAME}" "$known_file"
}

# Returns 0 if plugin was installed, 1 if skipped.
prompt_plugin_install() {
    header "Step 3 — praxion Plugin"
    cat <<EOF

  ${B}[1] Install plugin (recommended)${R}
      ${D}Skills, commands, and agents auto-discovered. Managed package${R}
      ${D}with updates via 'claude plugin update'. Works from any directory.${R}

  ${B}[2] Skip plugin${R}
      ${D}No skills, commands, or agents in this session. Use --plugin-dir${R}
      ${D}for development testing (see README_DEV.md).${R}
      ${D}Install later by re-running: ./install.sh code${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "Plugin skipped"
        return 1
    fi

    require_cmd "claude" "Claude Code CLI not found. Install: https://docs.anthropic.com/en/docs/claude-code"

    # Scope choice
    cat <<EOF

  ${B}Plugin scope:${R}

  ${B}[1] User scope (recommended)${R}
      ${D}Available in every Claude Code session. Install once, use everywhere.${R}

  ${B}[2] Project scope${R}
      ${D}Only in a specific project directory. Useful for testing or isolation.${R}
EOF
    ask 1 2
    local scope
    if [ "$REPLY" -eq 1 ]; then scope="user"; else scope="project"; fi

    # Remove orphan marker if present
    if [ -d "$PLUGIN_CACHE_DIR" ] && plugin_is_orphaned; then
        step "Removing orphan marker from previous installation..."
        find "$PLUGIN_CACHE_DIR" -name '.orphaned_at' -delete 2>/dev/null
        info "Orphan marker removed"
    fi

    # Register marketplace + install
    step "Registering marketplace..."
    claude plugin marketplace add "$MARKETPLACE_SOURCE" 2>/dev/null || true

    step "Installing ${PLUGIN_NAME} (${scope} scope)..."
    if ! claude plugin install "${PLUGIN_NAME}@${MARKETPLACE_NAME}" --scope "$scope" 2>&1; then
        fail "Plugin installation failed"
    fi

    # Verify
    if plugin_is_installed && ! plugin_is_orphaned; then
        info "Plugin installed and verified"
    else
        warn "Plugin installed but verification found issues — run: ./install.sh --check"
    fi

    # Auto-configure permissions (no choice — required for plugin to work)
    install_plugin_permissions

    return 0
}

complete_install_from_plugin() {
    header "Praxion Complete Install"

    printf "\n  This finishes the Praxion setup for marketplace-only installs.\n"
    printf "  You already ran 'claude plugin install praxion@bit-agora'. That installed\n"
    printf "  the plugin body (skills, commands, agents, hooks, MCP servers). This\n"
    printf "  command adds the surfaces the plugin mechanism does not cover natively:\n"
    printf "    • Rules (auto-loaded by Claude Code — shape agent behavior globally)\n"
    printf "    • CLI scripts on \$PATH (detector, praxion-parallel, chronograph-ctl, etc.)\n"
    printf "    • context-hub MCP (curated docs for 600+ libraries)\n\n"
    printf "  You will be prompted before each system-level change. Re-run anytime;\n"
    printf "  the operations are idempotent.\n\n"

    # ---- Rules ----
    printf "  ${B}[1] Symlink rules to ~/.claude/rules/?${R}\n"
    printf "      ${D}Auto-loaded by Claude Code. Shapes agent behavior globally\n"
    printf "      across every project — coding style, coordination protocols,\n"
    printf "      id-citation-discipline, ADR conventions, etc.${R}\n"
    printf "  ${B}[2] Skip rules${R}\n"
    ask 1 2
    if [ "$REPLY" -eq 1 ]; then
        link_rules "${SCRIPT_DIR}/rules" "${HOME}/.claude/rules"
        info "Rules: ${LINK_RULES_COUNT} files linked"
    else
        step "Rules skipped"
    fi

    # ---- CLI scripts ----
    printf "\n  ${B}[1] Symlink CLI scripts to ~/.local/bin/?${R}\n"
    printf "      ${D}check_id_citation_discipline.py, praxion-parallel (multi-session launcher),\n"
    printf "      chronograph-ctl, phoenix-ctl, onboard-project — runnable from any\n"
    printf "      shell. Filters internal helpers (merge drivers, git hooks).${R}\n"
    printf "  ${B}[2] Skip scripts${R}\n"
    ask 1 2
    if [ "$REPLY" -eq 1 ]; then
        local scripts_src="${SCRIPT_DIR}/scripts"
        local bin_dir="${HOME}/.local/bin"
        mkdir -p "$bin_dir"
        local scripts_count=0
        for script in "$scripts_src"/*; do
            [ -f "$script" ] && [ -x "$script" ] || continue
            local name
            name="$(basename "$script")"
            case "$name" in
                merge_driver_*|git-*-hook.sh) continue ;;
            esac
            ln -sf "$script" "${bin_dir}/${name}"
            scripts_count=$((scripts_count + 1))
        done
        info "Scripts: ${scripts_count} files linked"

        # onboard-project (also linked by the generic scripts/ loop above;
        # kept explicit for clarity since it is the single onboarding entry point)
        if [ -f "${SCRIPT_DIR}/scripts/onboard-project" ] && [ -x "${SCRIPT_DIR}/scripts/onboard-project" ]; then
            ln -sf "${SCRIPT_DIR}/scripts/onboard-project" "${bin_dir}/onboard-project"
            info "onboard-project: linked"
        fi

        if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
            warn "~/.local/bin is not in PATH"
            step "Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
    else
        step "Scripts skipped"
    fi

    # ---- context-hub MCP ----
    # prompt_chub_mcp has its own internal [1]/[2] prompt for install/skip,
    # so we just delegate to it.
    printf "\n"
    prompt_chub_mcp

    printf "\n"
    info "Praxion complete install done"
    step "Start a new Claude Code session to pick up the rules"
}

complete_uninstall_from_plugin() {
    header "Praxion Complete Uninstall (symlinks only)"

    printf "\n  This removes the rules and script symlinks installed by\n"
    printf "  '--complete-install'. The plugin body stays installed — use\n"
    printf "  'claude plugin uninstall praxion' to remove it separately.\n\n"
    printf "  You will be prompted before each removal.\n\n"

    # ---- Rules symlinks ----
    local rules_dir="${HOME}/.claude/rules"
    if [ -d "$rules_dir" ]; then
        printf "  ${B}[1] Remove Praxion rule symlinks from ~/.claude/rules/?${R}\n"
        printf "      ${D}Only removes links that target the plugin cache —\n"
        printf "      rules from other sources are left alone.${R}\n"
        printf "  ${B}[2] Skip${R}\n"
        ask 1 2
        if [ "$REPLY" -eq 1 ]; then
            local removed=0
            while IFS= read -r link; do
                local target
                target="$(readlink "$link" 2>/dev/null)" || continue
                if [[ "$target" == "${SCRIPT_DIR}"* ]]; then
                    rm "$link"
                    removed=$((removed + 1))
                fi
            done < <(find "$rules_dir" -type l 2>/dev/null)
            info "Rules: ${removed} symlink(s) removed"
            find "$rules_dir" -type d -empty -delete 2>/dev/null || true
        else
            step "Rules skipped"
        fi
    fi

    # ---- Script symlinks ----
    local bin_dir="${HOME}/.local/bin"
    if [ -d "$bin_dir" ]; then
        printf "\n  ${B}[1] Remove Praxion CLI script symlinks from ~/.local/bin/?${R}\n"
        printf "      ${D}Only removes links that target the plugin cache.${R}\n"
        printf "  ${B}[2] Skip${R}\n"
        ask 1 2
        if [ "$REPLY" -eq 1 ]; then
            local removed=0
            while IFS= read -r link; do
                local target
                target="$(readlink "$link" 2>/dev/null)" || continue
                if [[ "$target" == "${SCRIPT_DIR}"* ]]; then
                    rm "$link"
                    removed=$((removed + 1))
                fi
            done < <(find "$bin_dir" -maxdepth 1 -type l 2>/dev/null)
            info "Scripts: ${removed} symlink(s) removed"
        else
            step "Scripts skipped"
        fi
    fi

    # ---- context-hub MCP ----
    local claude_json="${HOME}/.claude.json"
    if [ -f "$claude_json" ] && grep -q "chub-mcp\|@aisuite/chub" "$claude_json" 2>/dev/null; then
        printf "\n  ${B}[1] Remove context-hub MCP from ~/.claude.json?${R}\n"
        printf "      ${D}Reverses what '/praxion-complete-install' added.${R}\n"
        printf "  ${B}[2] Skip${R}\n"
        ask 1 2
        if [ "$REPLY" -eq 1 ]; then
            python3 - "$claude_json" << 'PYEOF'
import json, sys
p = sys.argv[1]
with open(p) as f:
    data = json.load(f)
servers = data.get("mcpServers", {})
removed = 0
for name in ["context-hub", "chub"]:
    if name in servers:
        del servers[name]
        removed += 1
with open(p, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"removed {removed} MCP entr{'y' if removed == 1 else 'ies'}")
PYEOF
            info "context-hub MCP removed from ~/.claude.json"
        else
            step "MCP skipped"
        fi
    fi

    printf "\n"
    info "Praxion complete uninstall done"
    step "Plugin body still installed — run 'claude plugin uninstall praxion' to remove it"
}

# =============================================================================
# Dev-Link mode — symlink the installed plugin cache back to this working tree
# =============================================================================
#
# `bash install.sh` performs a marketplace fetch (`claude plugin install`),
# which clones a pinned copy into ~/.claude/plugins/cache/<marketplace>/
# <plugin>/<version>/. Local edits to hooks/, scripts/, or commands/ never
# reach that cache, so contributors testing plugin-cache-resolved code paths
# (${CLAUDE_PLUGIN_ROOT}-based hooks, `claude --bg` sessions, etc.) have had
# to manually `cp` files into the cache between iterations — see td-036 in
# .ai-state/TECH_DEBT_LEDGER.md.
#
# `--dev-link` replaces the cache copies of the three plugin-cache-resolved
# runtime surfaces (hooks/, scripts/, commands/ — the directories Claude Code
# actually loads through ${CLAUDE_PLUGIN_ROOT}/<surface>/...) with
# directory-level symlinks back to this repo's own hooks/, scripts/,
# commands/. Edits then take effect immediately, no copy step needed.
# `--dev-link=off` reverses it, restoring the pre-link cache contents from a
# sibling `.pre-dev-link` backup taken at link time — a plain marketplace
# re-fetch is also expected to overwrite the cache wholesale, but that
# overwrite behavior isn't part of Claude Code's documented contract, so the
# explicit backup/restore path is the one this script relies on for
# reversibility.
#
# Test-only override: lets scripts/test_install_dev_link.py point dev-link's
# "source of truth" at a synthetic tree instead of this repo's own hooks/,
# scripts/, commands/. Production runs always resolve to SCRIPT_DIR.
DEV_LINK_SOURCE_DIR="${PRAXION_DEV_LINK_SOURCE_DIR:-$SCRIPT_DIR}"
DEV_LINK_SURFACES=(hooks scripts commands)

# Resolves the pinned praxion install path + version from the plugin registry —
# same registry and lookup shape as scripts/upgrade_project_pins.sh's
# resolve_plugin() (prefers a user-scope entry, falls back to the first
# match). Sets DEV_LINK_INSTALL_PATH and DEV_LINK_VERSION, or fail()s with an
# actionable message. Also refuses (fail()s) if the resolved path escapes
# this plugin's own cache tree — never touch another plugin's cache.
dev_link_resolve_target() {
    local reg="${HOME}/.claude/plugins/installed_plugins.json"
    [ -f "$reg" ] || fail "No plugin registry at ${reg} — install the plugin first ('./install.sh code' or 'claude plugin install ${PLUGIN_NAME}@${MARKETPLACE_NAME}')."
    require_cmd "jq" "jq is required to resolve the pinned plugin version for --dev-link."

    local plugin_key="${PLUGIN_NAME}@${MARKETPLACE_NAME}"
    DEV_LINK_INSTALL_PATH="$(jq -r --arg key "$plugin_key" '
        (.plugins[$key] // [])
        | (map(select(.scope=="user")) + .)
        | (.[0].installPath // empty)' "$reg")"
    DEV_LINK_VERSION="$(jq -r --arg key "$plugin_key" '
        (.plugins[$key] // [])
        | (map(select(.scope=="user")) + .)
        | (.[0].version // empty)' "$reg")"

    [ -n "$DEV_LINK_INSTALL_PATH" ] || fail "${plugin_key} is not installed (no entry in ${reg}). Run './install.sh code' or 'claude plugin install ${plugin_key}' first."
    if [ -z "$DEV_LINK_VERSION" ] || [ "$DEV_LINK_VERSION" = "null" ]; then
        DEV_LINK_VERSION="$(basename "$DEV_LINK_INSTALL_PATH")"
    fi

    case "$DEV_LINK_INSTALL_PATH" in
        "$PLUGIN_CACHE_DIR"/*) ;;
        *) fail "Resolved install path '${DEV_LINK_INSTALL_PATH}' is not under ${PLUGIN_CACHE_DIR}/ — refusing to touch it." ;;
    esac
}

dev_link_install() {
    header "Dev-Link — symlink plugin cache to working tree"
    dev_link_resolve_target

    printf "\n  Plugin:  %s@%s\n  Cache:   %s\n  Source:  %s\n" \
        "$PLUGIN_NAME" "$DEV_LINK_VERSION" "$DEV_LINK_INSTALL_PATH" "$DEV_LINK_SOURCE_DIR"

    local surface target source backup
    for surface in "${DEV_LINK_SURFACES[@]}"; do
        target="${DEV_LINK_INSTALL_PATH}/${surface}"
        source="${DEV_LINK_SOURCE_DIR}/${surface}"
        backup="${target}.pre-dev-link"

        if [ ! -d "$source" ]; then
            warn "${surface}: no such directory in working tree (${source}) — skipping"
            continue
        fi
        if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
            info "${surface}: already dev-linked"
            continue
        fi
        if [ -L "$target" ]; then
            rm "$target"
        elif [ -d "$target" ]; then
            rm -rf "$backup"
            mv "$target" "$backup"
        elif [ -e "$target" ]; then
            fail "${surface}: unexpected non-directory at ${target} — refusing to touch"
        fi
        ln -s "$source" "$target"
        info "${surface}: linked -> ${source}"
    done

    printf "\n"
    info "Dev-link active — edits to hooks/, scripts/, commands/ now take effect immediately"
    step "Restore the fetched copies with: ./install.sh --dev-link=off"
}

dev_link_remove() {
    header "Dev-Link Off — restoring plugin cache"
    dev_link_resolve_target

    local surface target source backup skipped=0
    for surface in "${DEV_LINK_SURFACES[@]}"; do
        target="${DEV_LINK_INSTALL_PATH}/${surface}"
        source="${DEV_LINK_SOURCE_DIR}/${surface}"
        backup="${target}.pre-dev-link"

        if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
            rm "$target"
            if [ -d "$backup" ]; then
                mv "$backup" "$target"
                info "${surface}: restored from backup"
            else
                warn "${surface}: no backup found — re-fetch with 'claude plugin update ${PLUGIN_NAME}' or './install.sh code'"
                skipped=$((skipped + 1))
            fi
        else
            info "${surface}: not dev-linked, nothing to do"
        fi
    done

    printf "\n"
    if [ "$skipped" -eq 0 ]; then
        info "Dev-link removed — plugin cache restored to its fetched copies"
    else
        warn "Dev-link removed for some surfaces; ${skipped} surface(s) need a manual re-fetch (see above)"
    fi
}

install_plugin_permissions() {
    local settings_file="${HOME}/.claude/settings.json"

    step "Configuring plugin directory permissions..."

    python3 - "$settings_file" << 'PYEOF'
import json, sys

settings_path = sys.argv[1]

try:
    with open(settings_path) as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}

perms = settings.setdefault("permissions", {})
dirs = perms.setdefault("additionalDirectories", [])

entry = "~/.claude/plugins/**"
if entry not in dirs:
    dirs.append(entry)

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

    info "Plugin directory access granted (~/.claude/plugins/**)"
}

# =============================================================================
# Hooks: provided by plugin hooks.json (no settings.json registration needed)
# =============================================================================
# Hooks were previously installed into ~/.claude/settings.json by this script.
# Since Claude Code auto-loads hooks from installed plugins, the plugin's
# hooks.json (hooks/hooks.json) is now the single authority.
# The installer only cleans up stale hooks from settings.json if present.

# =============================================================================
# External API Docs (context-hub MCP)
# =============================================================================

prompt_chub_mcp() {
    header "Step 5 — context-hub MCP Server"

    # Prefer globally installed chub-mcp, fall back to npx
    local chub_mcp_cmd chub_mcp_args
    if command -v chub-mcp &>/dev/null; then
        chub_mcp_cmd="chub-mcp"
        chub_mcp_args="[]"
    elif command -v npx &>/dev/null; then
        chub_mcp_cmd="npx"
        chub_mcp_args='["-p", "@aisuite/chub", "chub-mcp"]'
    else
        step "Neither chub-mcp nor npx found — skipping MCP server setup"
        step "Install chub globally (npm install -g @aisuite/chub) and re-run"
        return
    fi

    cat <<EOF

  ${B}[1] Configure context-hub MCP (recommended)${R}
      ${D}Agents get native tool access to curated API docs (chub_search,${R}
      ${D}chub_get). Modifies ~/.claude/settings.json.${R}

  ${B}[2] Skip${R}
      ${D}Agents can still use chub CLI as fallback (if installed globally).${R}
      ${D}MCP gives agents native tool discovery without CLI teaching.${R}
      ${D}Install later by re-running: ./install.sh code${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "context-hub MCP skipped"
        return
    fi

    local claude_json="${HOME}/.claude.json"
    step "Adding context-hub MCP to ~/.claude.json (command: ${chub_mcp_cmd})..."

    python3 - "$claude_json" "$chub_mcp_cmd" "$chub_mcp_args" << 'PYEOF'
import json, sys

claude_json_path = sys.argv[1]
cmd = sys.argv[2]
args = json.loads(sys.argv[3])

try:
    with open(claude_json_path) as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

servers = config.setdefault("mcpServers", {})
servers["chub"] = {
    "type": "stdio",
    "command": cmd,
    "args": args,
    "env": {
        "CHUB_TELEMETRY": "0",
        "CHUB_FEEDBACK": "1"
    }
}

with open(claude_json_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF

    info "context-hub MCP configured (telemetry disabled)"

    # Migrate: remove stale chub entry from settings.json if present
    local settings_file="${HOME}/.claude/settings.json"
    if [ -f "$settings_file" ]; then
        python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
servers = s.get('mcpServers', {})
if 'chub' in servers:
    del servers['chub']
    if not servers:
        del s['mcpServers']
    with open(sys.argv[1], 'w') as f:
        json.dump(s, f, indent=2)
        f.write('\n')
" "$settings_file" 2>/dev/null && step "Cleaned stale chub entry from settings.json" || true
    fi
}

# =============================================================================
# Phoenix Observability Daemon
# =============================================================================

prompt_phoenix_install() {
    header "Step 6 — Phoenix Observability Daemon"

    cat <<EOF

  ${B}[1] Install Phoenix daemon (recommended)${R}
      ${D}Persistent trace backend for agent pipeline observability.${R}
      ${D}Creates a background daemon, UI at http://localhost:6006.${R}
      ${D}Installs in ~/.phoenix/ (~300MB). 90-day trace retention.${R}

  ${B}[2] Skip${R}
      ${D}Hooks still fire and chronograph still works for real-time${R}
      ${D}MCP queries. Traces are not persisted. Install later with:${R}
      ${D}phoenix-ctl install${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "Phoenix daemon skipped"
        return
    fi

    "${SCRIPT_DIR}/scripts/phoenix-ctl" install
}

# =============================================================================
# Claude Desktop config link
# =============================================================================

get_claude_desktop_config_dir() {
    case "$(uname -s)" in
        Darwin) echo "${HOME}/Library/Application Support/Claude" ;;
        Linux)  echo "${HOME}/.config/Claude" ;;
        *)      fail "Unsupported OS: $(uname -s)" ;;
    esac
}

prompt_claude_desktop_link() {
    header "Step 7 — Claude Desktop"
    cat <<EOF

  ${B}[1] Skip${R}
      ${D}Recommended if not using Claude Desktop alongside Claude Code.${R}

  ${B}[2] Link config to Claude Desktop${R}
      ${D}Symlinks claude_desktop_config.json to the official Claude Desktop${R}
      ${D}path. Enables MCP servers (task-chronograph) in Claude Desktop.${R}
      ${D}Install separately with: ./install.sh desktop${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 1 ]; then
        step "Desktop config skipped"
        return
    fi

    install_claude_desktop_link
}

install_claude_desktop_link() {
    local desktop_config_dir
    desktop_config_dir="$(get_claude_desktop_config_dir)"

    local source="${HOME}/.claude/claude_desktop_config.json"
    local target="${desktop_config_dir}/claude_desktop_config.json"

    mkdir -p "$desktop_config_dir"

    if [ ! -e "$source" ] && [ ! -L "$source" ]; then
        warn "Source not found: ${source}"
        step "Run ./install.sh code first to install personal config"
        return 1
    fi

    link_item "$source" "$target" "claude_desktop_config.json → Desktop"
}

# =============================================================================
# Health check
# =============================================================================

check_claude_code() {
    header "Claude Code — Health Check"

    local healthy=true
    local dest_dir="${HOME}/.claude"

    printf "\n  ${B}Config:${R}\n"
    for item in CLAUDE.md userPreferences.txt; do
        if [ -L "$dest_dir/$item" ]; then
            info "$item linked"
        else
            warn "$item not linked"
            healthy=false
        fi
    done

    # Rendered template + saved personal info — unsubstituted {{PLACEHOLDERS}}
    # leaking into the global prompt would be a loud, confusing bug.
    if [ -f "$CLAUDE_MD_RENDERED" ]; then
        if grep -q '{{[A-Z_]\+}}' "$CLAUDE_MD_RENDERED" 2>/dev/null; then
            warn "CLAUDE.md contains unsubstituted placeholders — re-run installer"
            healthy=false
        else
            info "CLAUDE.md rendered from template"
        fi
    else
        warn "CLAUDE.md not rendered (run: ./install.sh code)"
        healthy=false
    fi
    if [ -f "$PERSONAL_INFO_ENV" ]; then
        info "Personal info saved ($(basename "$PERSONAL_INFO_ENV"))"
    else
        warn "No saved personal info — defaults will be re-prompted"
    fi

    printf "\n  ${B}Rules:${R}\n"
    local rules_dir="${dest_dir}/rules"
    if [ -d "$rules_dir" ]; then
        local count
        count=$(find "$rules_dir" -name '*.md' -type l 2>/dev/null | wc -l | tr -d ' ')
        if [ "$count" -gt 0 ]; then
            info "${count} rules linked"
        else
            warn "No rule symlinks found"
            healthy=false
        fi
    else
        warn "Rules directory not found"
        healthy=false
    fi

    printf "\n  ${B}Plugin:${R}\n"
    if marketplace_is_registered; then
        info "Marketplace '${MARKETPLACE_NAME}' registered"
    else
        warn "Marketplace '${MARKETPLACE_NAME}' not registered"
        healthy=false
    fi

    if plugin_is_installed; then
        info "Plugin '${PLUGIN_NAME}' installed"
    else
        warn "Plugin '${PLUGIN_NAME}' not installed"
        healthy=false
    fi

    if [ -d "$PLUGIN_CACHE_DIR" ]; then
        if plugin_is_orphaned; then
            warn "Plugin has .orphaned_at marker (won't load)"
            healthy=false
        else
            info "No orphan marker"
        fi
    else
        warn "Plugin cache directory missing"
        healthy=false
    fi

    printf "\n  ${B}Scripts:${R}\n"
    local bin_dir="${HOME}/.local/bin"
    for script in "${SCRIPT_DIR}/scripts"/*; do
        # Same combined predicate as relink_all() (dec-042) so check only
        # reports on scripts that would actually be linked.
        [ -f "$script" ] && [ -x "$script" ] || continue
        local name
        name="$(basename "$script")"
        case "$name" in
            merge_driver_*|git-*-hook.sh) continue ;;
        esac
        if [ -L "${bin_dir}/${name}" ] && [ "$(readlink "${bin_dir}/${name}")" = "$script" ]; then
            info "${name} linked"
        else
            warn "${name} not linked to ~/.local/bin/"
            healthy=false
        fi
    done

    # onboard-project entry (also covered by the generic scripts/ loop above;
    # kept explicit since it is the single onboarding entry point)
    if [ -f "${SCRIPT_DIR}/scripts/onboard-project" ] && [ -x "${SCRIPT_DIR}/scripts/onboard-project" ]; then
        if [ -L "${bin_dir}/onboard-project" ] && [ "$(readlink "${bin_dir}/onboard-project")" = "${SCRIPT_DIR}/scripts/onboard-project" ]; then
            info "onboard-project linked"
        else
            warn "onboard-project not linked to ~/.local/bin/"
            healthy=false
        fi
    fi

    printf "\n  ${B}Hooks:${R}\n"
    local hooks_json="${SCRIPT_DIR}/hooks/hooks.json"
    if [ -f "$hooks_json" ]; then
        info "Hooks provided by plugin hooks.json"
        # Warn if stale hooks remain in settings.json
        local settings_file="${HOME}/.claude/settings.json"
        if [ -f "$settings_file" ] && python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
sys.exit(0 if 'hooks' in s else 1)
" "$settings_file" 2>/dev/null; then
            warn "Stale hooks in settings.json — remove the 'hooks' key to prevent double-firing"
        fi
    else
        warn "Plugin hooks.json not found at ${hooks_json}"
        healthy=false
    fi

    printf "\n  ${B}Phoenix Observability:${R}\n"
    if [ -f "${HOME}/Library/LaunchAgents/com.praxion.phoenix.plist" ]; then
        info "Phoenix plist installed"
        if curl -sf "http://localhost:${PHOENIX_PORT:-6006}" >/dev/null 2>&1; then
            info "Phoenix UI reachable at http://localhost:${PHOENIX_PORT:-6006}"
        else
            warn "Phoenix UI not reachable (daemon may not be running)"
        fi
    else
        warn "Phoenix not installed (optional — run: phoenix-ctl install)"
    fi

    printf "\n  ${B}context-hub MCP:${R}\n"
    local claude_json="${HOME}/.claude.json"
    if [ -f "$claude_json" ] && python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
servers = s.get('mcpServers', {})
sys.exit(0 if 'chub' in servers else 1)
" "$claude_json" 2>/dev/null; then
        info "context-hub MCP configured"
    else
        warn "context-hub MCP not configured"
    fi

    printf "\n"
    if $healthy; then
        info "All checks passed"
    else
        warn "Issues found — re-run: ./install.sh code"
    fi

    $healthy
}

check_claude_desktop() {
    header "Claude Desktop — Health Check"

    local healthy=true
    local desktop_config_dir
    desktop_config_dir="$(get_claude_desktop_config_dir)"
    local target="${desktop_config_dir}/claude_desktop_config.json"

    if [ -L "$target" ]; then
        info "Claude Desktop config linked"
    elif [ -f "$target" ]; then
        info "Claude Desktop config exists (not managed by installer)"
    else
        warn "Claude Desktop config not found at ${target}"
        healthy=false
    fi

    printf "\n"
    if $healthy; then
        info "All checks passed"
    else
        warn "Issues found — re-run: ./install.sh desktop"
    fi

    $healthy
}

# =============================================================================
# Uninstall
# =============================================================================

uninstall_claude_code() {
    header "Uninstalling Claude Code config"

    local dest_dir="${HOME}/.claude"

    # Remove config symlinks (same list as config_items.txt)
    local list_file="${CLAUDE_CONFIG_DIR}/config_items.txt"
    if [ -f "$list_file" ]; then
        while IFS= read -r item || [ -n "$item" ]; do
            [ -z "$item" ] && continue
            local target="$dest_dir/$item"
            if [ -L "$target" ]; then
                rm "$target"
                info "Removed $item"
            fi
        done < "$list_file"
    fi

    # Remove rendered CLAUDE.md + saved personal info (both gitignored —
    # regenerated cleanly on next install).
    if [ -f "$CLAUDE_MD_RENDERED" ]; then
        rm "$CLAUDE_MD_RENDERED"
        info "Removed rendered CLAUDE.md"
    fi
    if [ -f "$PERSONAL_INFO_ENV" ]; then
        rm "$PERSONAL_INFO_ENV"
        info "Removed $(basename "$PERSONAL_INFO_ENV")"
    fi

    # Remove rule symlinks
    local rules_dir="${dest_dir}/rules"
    if [ -d "$rules_dir" ]; then
        find "$rules_dir" -type l -delete 2>/dev/null
        find "$rules_dir" -type d -empty -delete 2>/dev/null
        info "Removed rule symlinks"
    fi

    # Uninstall plugin
    if command -v claude &>/dev/null && plugin_is_installed; then
        step "Uninstalling plugin..."
        claude plugin uninstall "$PLUGIN_NAME" 2>/dev/null \
            && info "Plugin removed" \
            || warn "Plugin removal failed"
    fi

    # Remove scripts (same combined filter as relink_all — dec-042).
    local bin_dir="${HOME}/.local/bin"
    for script in "${SCRIPT_DIR}/scripts"/*; do
        [ -f "$script" ] && [ -x "$script" ] || continue
        local name
        name="$(basename "$script")"
        case "$name" in
            merge_driver_*|git-*-hook.sh) continue ;;
        esac
        if [ -L "${bin_dir}/${name}" ] && [ "$(readlink "${bin_dir}/${name}")" = "$script" ]; then
            rm "${bin_dir}/${name}"
            info "Removed ${name} from ~/.local/bin/"
        fi
    done

    # Remove new-project entry (lives at repo root, not scripts/)
    if [ -L "${bin_dir}/new-project" ] && [ "$(readlink "${bin_dir}/new-project")" = "${SCRIPT_DIR}/new_project.sh" ]; then
        rm "${bin_dir}/new-project"
        info "Removed new-project from ~/.local/bin/"
    fi

    # Remove hooks from settings.json
    local settings_file="${HOME}/.claude/settings.json"
    if [ -f "$settings_file" ]; then
        python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
changed = False
if 'hooks' in s:
    del s['hooks']
    changed = True
# Clean up stale mcpServers from settings.json (moved to ~/.claude.json)
servers = s.get('mcpServers', {})
if 'chub' in servers:
    del servers['chub']
    changed = True
if not servers and 'mcpServers' in s:
    del s['mcpServers']
    changed = True
if changed:
    with open(sys.argv[1], 'w') as f:
        json.dump(s, f, indent=2)
        f.write('\n')
" "$settings_file" 2>/dev/null && info "Hooks removed from settings.json" || true
    fi

    # Remove chub MCP from ~/.claude.json
    local claude_json="${HOME}/.claude.json"
    if [ -f "$claude_json" ]; then
        python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
servers = s.get('mcpServers', {})
if 'chub' in servers:
    del servers['chub']
    with open(sys.argv[1], 'w') as f:
        json.dump(s, f, indent=2)
        f.write('\n')
" "$claude_json" 2>/dev/null && info "context-hub MCP removed from ~/.claude.json" || true
    fi

    # Uninstall Phoenix daemon
    if [ -f "${HOME}/Library/LaunchAgents/com.praxion.phoenix.plist" ]; then
        "${SCRIPT_DIR}/scripts/phoenix-ctl" uninstall 2>/dev/null || true
    fi

    printf "\n"
    info "Uninstall complete"
}

uninstall_claude_desktop() {
    header "Uninstalling Claude Desktop config"

    local desktop_config_dir
    desktop_config_dir="$(get_claude_desktop_config_dir)"
    local target="${desktop_config_dir}/claude_desktop_config.json"

    if [ -L "$target" ]; then
        rm "$target"
        info "Removed Desktop config symlink"
    elif [ -f "$target" ]; then
        warn "${target} is a regular file (not managed by installer)"
        step "Remove manually if desired"
    else
        step "Nothing to remove"
    fi

    printf "\n"
    info "Uninstall complete"
}

# =============================================================================
# Top-level flows
# =============================================================================

install_claude_code() {
    prompt_personal_info
    render_claude_md

    header "Step 1 — Symlinks (config, rules, scripts)"
    clean_stale_symlinks
    relink_all

    install_git_merge_infra

    prompt_plugin_install

    prompt_chub_mcp
    prompt_phoenix_install
    prompt_claude_desktop_link

    printf "\n"
    info "Installation complete"
}

install_claude_desktop() {
    header "Step 1 — Claude Desktop config"

    install_claude_desktop_link

    printf "\n"
    info "Installation complete"
    step "Skills, commands, and agents require Claude Code"
    step "Run ./install.sh code for the full feature set"
}

# =============================================================================
# Dry-run (show what would be installed, no writes)
# =============================================================================

dry_run_claude_code() {
    header "Claude Code — Dry run"
    local plugin_json="${SCRIPT_DIR}/.claude-plugin/plugin.json"
    if [ -f "$plugin_json" ]; then
        printf "\n  ${B}Plugin:${R} praxion v%s\n\n" "$(jq -r .version "$plugin_json" 2>/dev/null || echo "?")"
    fi
    printf "  ${B}Personal identifiers:${R}\n"
    if [ -f "$PERSONAL_INFO_ENV" ]; then
        printf "    (reuse saved values from %s)\n" "$(basename "$PERSONAL_INFO_ENV")"
    else
        printf "    Defaults: %s / %s / %s\n" "$DEFAULT_USERNAME" "$DEFAULT_EMAIL" "$DEFAULT_GITHUB_URL"
        printf "    (installer will prompt to accept or customize)\n"
    fi
    printf "\n"
    printf "  ${B}Skills:${R}\n"
    find "${SCRIPT_DIR}/skills" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; 2>/dev/null | sed 's/^/    /' || step "(none)"
    printf "\n  ${B}Commands:${R}\n"
    find "${SCRIPT_DIR}/commands" -name '*.md' -type f ! -name 'README.md' 2>/dev/null | while read -r f; do
        printf "    /%s\n" "$(basename "$f" .md)"
    done
    printf "\n  ${B}Agents:${R}\n"
    find "${SCRIPT_DIR}/agents" -name '*.md' -type f ! -name 'README.md' 2>/dev/null | sed 's|.*/||;s|\.md$||' | sed 's/^/    /' || step "(none)"
    printf "\n  ${B}Scripts:${R}\n"
    for script in "${SCRIPT_DIR}/scripts"/*; do
        [ -f "$script" ] && printf "    %s\n" "$(basename "$script")"
    done
    printf "\n"
}

dry_run_claude_desktop() {
    header "Claude Desktop — Dry run"
    local desktop_config_dir
    desktop_config_dir="$(get_claude_desktop_config_dir)"
    printf "\n  Would link claude_desktop_config.json to:\n    %s/claude_desktop_config.json\n\n" "$desktop_config_dir"
}

# =============================================================================
# Usage
# =============================================================================

show_usage() {
    cat <<EOF
Usage: $(basename "$0") code|desktop [--check] [--dry-run] [--uninstall] [--relink] [--reconfigure] [--complete-install] [--complete-uninstall] [--dev-link] [--dev-link=off] [--help]

  code           Install for Claude Code
  desktop        Install for Claude Desktop
  --check        Verify installation health
  --dry-run      Show what would be installed (no writes)
  --uninstall    Remove installation
  --relink       Re-symlink config, rules, and scripts (no prompts)
  --reconfigure  Re-prompt for personal identifiers (username/email/github)
                 even if saved values exist in .personal_info.env
  --dev-link     Symlink the pinned plugin cache's hooks/, scripts/, and
                 commands/ back to this working tree (code mode only)
  --dev-link=off Reverse of --dev-link: restore fetched cache copies
  --help         Show this help
EOF
    exit 0
}

# =============================================================================
# Main
# =============================================================================

MODE=""
CHECK=false
DRY_RUN=false
UNINSTALL=false
RELINK=false
RECONFIGURE=false
COMPLETE_INSTALL=false
COMPLETE_UNINSTALL=false
DEV_LINK=false
DEV_LINK_OFF=false

while [ $# -gt 0 ]; do
    case "$1" in
        code|desktop)         MODE="$1" ;;
        --check)              CHECK=true ;;
        --dry-run)            DRY_RUN=true ;;
        --uninstall)          UNINSTALL=true ;;
        --relink)             RELINK=true ;;
        --reconfigure)        RECONFIGURE=true ;;
        --complete-install)   COMPLETE_INSTALL=true ;;
        --complete-uninstall) COMPLETE_UNINSTALL=true ;;
        --dev-link)           DEV_LINK=true ;;
        --dev-link=off)       DEV_LINK_OFF=true ;;
        -h|--help)            show_usage ;;
        *)                    fail "Unknown argument: $1. Use --help for usage." ;;
    esac
    shift
done

# --complete-install / --complete-uninstall are 'code' mode only.
if ( $COMPLETE_INSTALL || $COMPLETE_UNINSTALL ) && [ "$MODE" != "code" ]; then
    fail "--complete-install / --complete-uninstall are only supported with 'code' mode."
fi

# --dev-link / --dev-link=off are 'code' mode only, and mutually exclusive.
if $DEV_LINK && $DEV_LINK_OFF; then
    fail "--dev-link and --dev-link=off are mutually exclusive."
fi
if ( $DEV_LINK || $DEV_LINK_OFF ) && [ "$MODE" != "code" ]; then
    fail "--dev-link is only supported with 'code' mode."
fi

# Dispatch the complete-install/uninstall/dev-link actions before the
# generic flow so they exit cleanly without triggering the full interactive
# install.
if $COMPLETE_INSTALL; then
    complete_install_from_plugin
    exit 0
fi
if $COMPLETE_UNINSTALL; then
    complete_uninstall_from_plugin
    exit 0
fi
if $DEV_LINK; then
    dev_link_install
    exit 0
fi
if $DEV_LINK_OFF; then
    dev_link_remove
    exit 0
fi

if [ -z "$MODE" ]; then
    fail "Missing mode. Use code or desktop. See --help."
fi

if $RELINK; then
    case "$MODE" in
        code)
            header "Relinking symlink-based artifacts"
            # Re-render too, in case the template changed upstream (git pull).
            # Reuses saved .personal_info.env silently unless --reconfigure set.
            prompt_personal_info
            render_claude_md
            relink_all
            printf "\n"
            info "Relink complete"
            ;;
        desktop) fail "--relink is only supported for code mode" ;;
    esac
    exit $?
fi

if $CHECK; then
    case "$MODE" in
        code)    check_claude_code ;;
        desktop) check_claude_desktop ;;
    esac
    exit $?
fi

if $DRY_RUN; then
    case "$MODE" in
        code)    dry_run_claude_code ;;
        desktop) dry_run_claude_desktop ;;
    esac
    exit 0
fi

if $UNINSTALL; then
    case "$MODE" in
        code)    uninstall_claude_code ;;
        desktop) uninstall_claude_desktop ;;
    esac
    exit 0
fi

case "$MODE" in
    code)    install_claude_code ;;
    desktop) install_claude_desktop ;;
esac
