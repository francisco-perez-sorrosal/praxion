#!/usr/bin/env bash
# Praxion — Claude Code / Claude Desktop installer
#
# Installs personal config, rules, and the i-am plugin into Claude Code or
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
PLUGIN_NAME="i-am"
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

    # Python handles the substitution: sed would need escape gymnastics for
    # URLs and @ characters. str.replace is safe regardless of content.
    python3 - "$CLAUDE_MD_TEMPLATE" "$CLAUDE_MD_RENDERED" \
        "$PRAXION_USERNAME" "$PRAXION_EMAIL" "$PRAXION_GITHUB_URL" <<'PYEOF'
import sys
src, dst, username, email, github_url = sys.argv[1:6]
with open(src) as f:
    content = f.read()
content = (content
    .replace("{{USERNAME}}", username)
    .replace("{{EMAIL}}", email)
    .replace("{{GITHUB_URL}}", github_url))
with open(dst, "w") as f:
    f.write(content)
PYEOF

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

    # 4. new-project entry (parked at repo root, not scripts/)
    if [ -f "${SCRIPT_DIR}/new_project.sh" ] && [ -x "${SCRIPT_DIR}/new_project.sh" ]; then
        mkdir -p "$bin_dir"
        link_item "${SCRIPT_DIR}/new_project.sh" "${bin_dir}/new-project" "new-project (greenfield project entry)"
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
    git -C "$repo_root" config merge.memory-json.name "Semantic memory.json merge"
    git -C "$repo_root" config merge.memory-json.driver "python3 scripts/merge_driver_memory.py %O %A %B"

    git -C "$repo_root" config merge.observations-jsonl.name "Observations JSONL merge"
    git -C "$repo_root" config merge.observations-jsonl.driver "python3 scripts/merge_driver_observations.py %O %A %B"

    info "Merge drivers: memory-json, observations-jsonl"

    # Install post-merge hook for ADR renumbering + index regeneration.
    # The hook only fires when .ai-state/ files were involved in the merge.
    local hook_src="${SCRIPT_DIR}/scripts/git-post-merge-hook.sh"
    local hook_dst="${repo_root}/.git/hooks/post-merge"

    if [ -f "$hook_src" ]; then
        # Preserve existing post-merge hook if present
        if [ -f "$hook_dst" ] && ! grep -q "reconcile_ai_state" "$hook_dst" 2>/dev/null; then
            warn "Existing post-merge hook found — appending reconciliation"
            printf '\n# Praxion .ai-state/ reconciliation\n' >> "$hook_dst"
            cat "$hook_src" >> "$hook_dst"
        else
            cp "$hook_src" "$hook_dst"
        fi
        chmod +x "$hook_dst"
        info "Post-merge hook: ADR renumbering + index regeneration"
    fi

    # Install pre-commit hook for shipped-artifact isolation check.
    # Blocks commits that leak specific .ai-state/ or .ai-work/ entries
    # into shipped surfaces (rules/, skills/, agents/, commands/,
    # claude/config/). Rationale: rules/swe/shipped-artifact-isolation.md.
    local precommit_src="${SCRIPT_DIR}/scripts/git-pre-commit-hook.sh"
    local precommit_dst="${repo_root}/.git/hooks/pre-commit"

    if [ -f "$precommit_src" ]; then
        # Preserve existing pre-commit hook if present
        if [ -f "$precommit_dst" ] && ! grep -q "check_shipped_artifact_isolation" "$precommit_dst" 2>/dev/null; then
            warn "Existing pre-commit hook found — appending isolation check"
            printf '\n# Praxion shipped-artifact isolation check\n' >> "$precommit_dst"
            cat "$precommit_src" >> "$precommit_dst"
        else
            cp "$precommit_src" "$precommit_dst"
        fi
        chmod +x "$precommit_dst"
        info "Pre-commit hook: shipped-artifact isolation check"
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
    header "Step 3 — i-am Plugin"
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
    printf "  You already ran 'claude plugin install i-am@bit-agora'. That installed\n"
    printf "  the plugin body (skills, commands, agents, hooks, MCP servers). This\n"
    printf "  command adds the surfaces the plugin mechanism does not cover natively:\n"
    printf "    • Rules (auto-loaded by Claude Code — shape agent behavior globally)\n"
    printf "    • CLI scripts on \$PATH (detector, ccwt, chronograph-ctl, etc.)\n"
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
    printf "      ${D}check_id_citation_discipline.py, ccwt (multi-worktree sessions),\n"
    printf "      chronograph-ctl, phoenix-ctl, new-project — runnable from any\n"
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

        # new-project (parked at repo root)
        if [ -f "${SCRIPT_DIR}/new_project.sh" ] && [ -x "${SCRIPT_DIR}/new_project.sh" ]; then
            ln -sf "${SCRIPT_DIR}/new_project.sh" "${bin_dir}/new-project"
            info "new-project: linked"
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
    printf "  'claude plugin uninstall i-am' to remove it separately.\n\n"
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
    step "Plugin body still installed — run 'claude plugin uninstall i-am' to remove it"
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

    # new-project entry (lives at repo root, not scripts/)
    if [ -f "${SCRIPT_DIR}/new_project.sh" ] && [ -x "${SCRIPT_DIR}/new_project.sh" ]; then
        if [ -L "${bin_dir}/new-project" ] && [ "$(readlink "${bin_dir}/new-project")" = "${SCRIPT_DIR}/new_project.sh" ]; then
            info "new-project linked"
        else
            warn "new-project not linked to ~/.local/bin/"
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
        printf "\n  ${B}Plugin:${R} i-am v%s\n\n" "$(jq -r .version "$plugin_json" 2>/dev/null || echo "?")"
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
    if [ -f "${SCRIPT_DIR}/new_project.sh" ]; then
        printf "    new_project.sh -> ~/.local/bin/new-project (greenfield project entry)\n"
    fi
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
Usage: $(basename "$0") code|desktop [--check] [--dry-run] [--uninstall] [--relink] [--reconfigure] [--complete-install] [--complete-uninstall] [--help]

  code           Install for Claude Code
  desktop        Install for Claude Desktop
  --check        Verify installation health
  --dry-run      Show what would be installed (no writes)
  --uninstall    Remove installation
  --relink       Re-symlink config, rules, and scripts (no prompts)
  --reconfigure  Re-prompt for personal identifiers (username/email/github)
                 even if saved values exist in .personal_info.env
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
        -h|--help)            show_usage ;;
        *)                    fail "Unknown argument: $1. Use --help for usage." ;;
    esac
    shift
done

# --complete-install / --complete-uninstall are 'code' mode only.
if ( $COMPLETE_INSTALL || $COMPLETE_UNINSTALL ) && [ "$MODE" != "code" ]; then
    fail "--complete-install / --complete-uninstall are only supported with 'code' mode."
fi

# Dispatch the complete-install/uninstall actions before the generic flow
# so they exit cleanly without triggering the full interactive install.
if $COMPLETE_INSTALL; then
    complete_install_from_plugin
    exit 0
fi
if $COMPLETE_UNINSTALL; then
    complete_uninstall_from_plugin
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
