#!/usr/bin/env bash
# Praxion — Claude Code / Claude Desktop installer
#
# Installs personal config, rules, and the i-am plugin into Claude Code or
# configures MCP servers for Claude Desktop. Invoked by install.sh for code|desktop.
#
# Usage:
#   ./install_claude.sh code|desktop [--check] [--dry-run] [--uninstall] [--help]

set -eo pipefail

# =============================================================================
# Constants
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_CONFIG_DIR="${SCRIPT_DIR}/claude/config"
PLUGIN_NAME="i-am"
MARKETPLACE_NAME="bit-agora"
MARKETPLACE_SOURCE="francisco-perez-sorrosal/bit-agora"
PLUGIN_CACHE_DIR="${HOME}/.claude/plugins/cache/${MARKETPLACE_NAME}/${PLUGIN_NAME}"

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
# Personal config + rules
# =============================================================================

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
}

install_personal_config() {
    local src_dir="$CLAUDE_CONFIG_DIR"
    local dest_dir="${HOME}/.claude"
    mkdir -p "${dest_dir}"

    header "Step 1 — Personal config"

    clean_stale_symlinks

    local list_file="${CLAUDE_CONFIG_DIR}/config_items.txt"
    if [ ! -f "$list_file" ]; then
        fail "Claude config list not found: $list_file"
    fi
    while IFS= read -r item || [ -n "$item" ]; do
        [ -z "$item" ] && continue
        if [ -e "$src_dir/$item" ]; then
            link_item "$src_dir/$item" "$dest_dir/$item" "$item → ~/.claude/"
        fi
    done < "$list_file"
}

install_rules() {
    local rules_src="${SCRIPT_DIR}/rules"
    local rules_dir="${HOME}/.claude/rules"
    mkdir -p "${rules_dir}"

    header "Step 2 — Rules"

    while IFS= read -r rule; do
        local rel_path="${rule#"$rules_src"/}"
        local rel_dir
        rel_dir="$(dirname "$rel_path")"
        [[ "$(basename "$rule")" == "README.md" ]] && continue
        [[ "$rel_path" == */references/* ]] && continue
        [ "$rel_dir" != "." ] && mkdir -p "${rules_dir}/${rel_dir}"
        link_item "$rule" "${rules_dir}/${rel_path}" "${rel_path}"
    done < <(find "$rules_src" -name '*.md' -type f | sort)
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

# =============================================================================
# CLI scripts (~/.local/bin/)
# =============================================================================

install_scripts() {
    local scripts_src="${SCRIPT_DIR}/scripts"
    local bin_dir="${HOME}/.local/bin"

    header "Step 5 — CLI Scripts"

    if [ ! -d "$scripts_src" ] || [ -z "$(ls -A "$scripts_src" 2>/dev/null)" ]; then
        step "No scripts to install"
        return
    fi

    mkdir -p "$bin_dir"

    for script in "$scripts_src"/*; do
        [ -f "$script" ] || continue
        local name
        name="$(basename "$script")"
        link_item "$script" "${bin_dir}/${name}" "${name} → ~/.local/bin/"
    done

    # Check PATH
    if [[ ":$PATH:" != *":${bin_dir}:"* ]]; then
        warn "~/.local/bin is not in PATH"
        step "Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
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
# Task Chronograph hooks
# =============================================================================

prompt_hooks_install() {
    local hooks_dir="${SCRIPT_DIR}/.claude-plugin/hooks"
    local send_event="${hooks_dir}/send_event.py"
    if [ ! -f "$send_event" ]; then
        warn "Hook script not found: ${send_event} — skipping hooks"
        return
    fi

    header "Step 4 — Hooks (Observability + Code Quality)"
    cat <<EOF

  ${B}[1] Install hooks (recommended)${R}
      ${D}Observability: agent lifecycle tracking via Task Chronograph.${R}
      ${D}Code quality: auto-format Python on Write/Edit, lint gate on commit.${R}
      ${D}Modifies ~/.claude/settings.json.${R}

  ${B}[2] Skip hooks${R}
      ${D}No observability or automatic code quality enforcement.${R}
      ${D}Install later by re-running: ./install.sh code${R}
EOF
    ask 1 2

    if [ "$REPLY" -eq 2 ]; then
        step "Hooks skipped"
        return
    fi

    local settings_file="${HOME}/.claude/settings.json"
    step "Installing hooks into settings.json..."

    python3 - "$settings_file" "$hooks_dir" << 'PYEOF'
import json, sys

settings_path, hooks_dir = sys.argv[1], sys.argv[2]

try:
    with open(settings_path) as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}

def hook(script, matcher="", timeout=10, is_async=True):
    return {
        "matcher": matcher,
        "hooks": [{
            "type": "command",
            "command": f"python3 {hooks_dir}/{script}",
            "timeout": timeout,
            "async": is_async,
        }],
    }

settings["hooks"] = {
    # Observability (async, fire-and-forget)
    "SubagentStart": [hook("send_event.py")],
    "SubagentStop": [hook("send_event.py")],
    "PostToolUse": [
        hook("send_event.py", "Write|Edit"),
        hook("format_python.py", "Write|Edit", is_async=False),
    ],
    # Code quality gate (sync, blocks on violations)
    "PreToolUse": [{
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": f"python3 {hooks_dir}/check_code_quality.py",
                "timeout": 30,
                "async": False,
            },
        ],
    }],
}

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF

    info "Hooks installed:"
    info "  Observability: SubagentStart, SubagentStop, PostToolUse (send_event)"
    info "  Code quality:  PostToolUse (format_python), PreToolUse (check_code_quality)"
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
    header "Step 6 — Claude Desktop"
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
        [ -f "$script" ] || continue
        local name
        name="$(basename "$script")"
        if [ -L "${bin_dir}/${name}" ] && [ "$(readlink "${bin_dir}/${name}")" = "$script" ]; then
            info "${name} linked"
        else
            warn "${name} not linked to ~/.local/bin/"
            healthy=false
        fi
    done

    printf "\n  ${B}Hooks:${R}\n"
    local settings_file="${HOME}/.claude/settings.json"
    if [ -f "$settings_file" ] && python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
hooks = s.get('hooks', {})
sys.exit(0 if 'SubagentStart' in hooks and 'SubagentStop' in hooks else 1)
" "$settings_file" 2>/dev/null; then
        info "Task Chronograph hooks configured"
    else
        warn "Task Chronograph hooks not configured"
        healthy=false
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

    # Remove scripts
    local bin_dir="${HOME}/.local/bin"
    for script in "${SCRIPT_DIR}/scripts"/*; do
        [ -f "$script" ] || continue
        local name
        name="$(basename "$script")"
        if [ -L "${bin_dir}/${name}" ] && [ "$(readlink "${bin_dir}/${name}")" = "$script" ]; then
            rm "${bin_dir}/${name}"
            info "Removed ${name} from ~/.local/bin/"
        fi
    done

    # Remove hooks
    local settings_file="${HOME}/.claude/settings.json"
    if [ -f "$settings_file" ]; then
        python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    s = json.load(f)
if 'hooks' in s:
    del s['hooks']
    with open(sys.argv[1], 'w') as f:
        json.dump(s, f, indent=2)
        f.write('\n')
" "$settings_file" 2>/dev/null && info "Hooks removed" || true
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
    install_personal_config
    install_rules

    if prompt_plugin_install; then
        prompt_hooks_install
    fi

    install_scripts
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
Usage: $(basename "$0") code|desktop [--check] [--dry-run] [--uninstall] [--help]

  code         Install for Claude Code
  desktop      Install for Claude Desktop
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

MODE=""
CHECK=false
DRY_RUN=false
UNINSTALL=false

while [ $# -gt 0 ]; do
    case "$1" in
        code|desktop) MODE="$1" ;;
        --check)      CHECK=true ;;
        --dry-run)    DRY_RUN=true ;;
        --uninstall)  UNINSTALL=true ;;
        -h|--help)    show_usage ;;
        *)            fail "Unknown argument: $1. Use --help for usage." ;;
    esac
    shift
done

if [ -z "$MODE" ]; then
    fail "Missing mode. Use code or desktop. See --help."
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
