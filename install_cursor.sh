#!/usr/bin/env bash
# Install Cursor-facing artifacts from this repo.
# Repo remains source of truth; this script creates symlinks and generated files.
#
# Usage (from this repo root, or via install.sh):
#   ./install_cursor.sh [path]              # Install (user or path)
#   ./install_cursor.sh [path] --dry-run   # Show what would be installed
#   ./install_cursor.sh [path] --check     # Verify installation health
#   ./install_cursor.sh [path] --uninstall # Message only (remove .cursor/ manually)
#   --dry-run and --status are equivalent (dry-run is canonical).
#
# MCP servers in mcp.json always point at this repo (task-chronograph, agents).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
CURSOR_CONFIG_DIR="$REPO_ROOT/cursor/config"

# Shared linking helpers (rules linking used by both Claude and Cursor installers)
# shellcheck source=lib/install_shared.sh
source "${SCRIPT_DIR}/lib/install_shared.sh"

# Terminal formatting
if [ -t 1 ]; then
    B=$'\033[1m' D=$'\033[2m' R=$'\033[0m'
else
    B='' D='' R=''
fi
info() { printf "  ✓ %s\n" "$*"; }
warn() { printf "  ⚠ %s\n" "$*"; }
header() { printf "\n${B}%s${R}\n" "$*"; }
step() { printf "  %s\n" "$*"; }

show_usage() {
    cat <<EOF
Usage: $(basename "$0") [path] [--check] [--dry-run] [--uninstall] [--help]

  path         Per-project install at path/.cursor/ (default: user profile ~/.cursor/)
  --check      Verify installation health
  --dry-run    Show what would be installed (no writes)
  --uninstall  Print message; remove .cursor/ manually if desired
  --help       Show this help
EOF
    exit 0
}

# Parse args: optional path, then optional flags
CURSOR_PATH=""
DO_CHECK=false
DO_DRY_RUN=false
DO_UNINSTALL=false
while [ $# -gt 0 ]; do
    case "$1" in
        --check)     DO_CHECK=true ;;
        --dry-run|--status) DO_DRY_RUN=true ;;
        --uninstall) DO_UNINSTALL=true ;;
        -h|--help)   show_usage ;;
        *)
            if [ -z "$CURSOR_PATH" ]; then
                if [ -d "$1" ]; then
                    CURSOR_PATH="$1"
                elif [[ "$1" == --* ]]; then
                    echo "Error: unknown option $1" >&2
                    exit 1
                else
                    echo "Error: not a directory: $1" >&2
                    exit 1
                fi
            fi
            ;;
    esac
    shift
done

# Resolve target directory
if [ -n "$CURSOR_PATH" ]; then
    TARGET_ROOT="$(cd "$CURSOR_PATH" && pwd)"
    CURSOR_DIR="$TARGET_ROOT/.cursor"
    INSTALL_MODE="project ($TARGET_ROOT)"
else
    TARGET_ROOT="${HOME}"
    CURSOR_DIR="${HOME}/.cursor"
    INSTALL_MODE="user profile (~/.cursor)"
fi
REPO_ROOT_FOR_MCP="${CURSOR_REPO_ROOT:-$REPO_ROOT}"

# --uninstall: no-op with message (symmetric with code/desktop)
if $DO_UNINSTALL; then
    warn "Cursor mode has no automated uninstall; remove the directory manually if desired:"
    step "  rm -rf \"$CURSOR_DIR\""
    exit 0
fi

# --dry-run: show what would be installed
if $DO_DRY_RUN; then
    echo "Target: $CURSOR_DIR ($INSTALL_MODE)"
    n_skills=$(find "$REPO_ROOT/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    n_rules=$(find "$REPO_ROOT/rules" -name '*.md' -type f ! -path '*/references/*' ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')
    n_commands=$(find "$REPO_ROOT/commands" -name '*.md' -type f ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')
    echo "Skills: $n_skills | Rules: $n_rules | Commands: $n_commands"
    echo "MCP: $CURSOR_DIR/mcp.json"
    exit 0
fi

# --check: verify installation health
if $DO_CHECK; then
    healthy=true
    header "Cursor — Health Check"
    printf "\n  ${B}Target:${R} %s\n\n" "$CURSOR_DIR"

    printf "  ${B}Skills:${R}\n"
    if [ -d "$CURSOR_DIR/skills" ]; then
        count=$(ls -1 "$CURSOR_DIR/skills" 2>/dev/null | wc -l | tr -d ' ')
        if [ "${count:-0}" -gt 0 ]; then
            info "${count} skills"
        else
            warn "No skills found"
            healthy=false
        fi
    else
        warn "skills/ not found"
        healthy=false
    fi

    printf "\n  ${B}Rules:${R}\n"
    if [ -d "$CURSOR_DIR/rules" ]; then
        count=$(find "$CURSOR_DIR/rules" -name '*.md' \( -type f -o -type l \) 2>/dev/null | wc -l | tr -d ' ')
        if [ "${count:-0}" -gt 0 ]; then
            info "${count} rules"
        else
            warn "No rules found"
            healthy=false
        fi
    else
        warn "rules/ not found"
        healthy=false
    fi

    printf "\n  ${B}Commands:${R}\n"
    if [ -d "$CURSOR_DIR/commands" ]; then
        count=$(find "$CURSOR_DIR/commands" -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
        if [ "${count:-0}" -gt 0 ]; then
            info "${count} commands"
        else
            warn "No commands found"
            healthy=false
        fi
    else
        warn "commands/ not found"
        healthy=false
    fi

    printf "\n  ${B}MCP:${R}\n"
    if [ -f "$CURSOR_DIR/mcp.json" ]; then
        expected_servers="$CURSOR_CONFIG_DIR/expected-mcp-servers.txt"
        if [ -f "$expected_servers" ]; then
            missing=""
            while IFS= read -r srv || [ -n "$srv" ]; do
                [ -z "$srv" ] && continue
                if ! python3 -c "
import json, sys
j = json.load(open(sys.argv[1]))
servers = j.get('mcpServers') or {}
sys.exit(0 if sys.argv[2] in servers else 1)
" "$CURSOR_DIR/mcp.json" "$srv" 2>/dev/null; then
                    missing="$missing $srv"
                fi
            done < "$expected_servers"
            if [ -z "$missing" ]; then
                info "mcp.json present (task-chronograph, sub-agents, chub)"
            else
                warn "mcp.json missing expected server(s):$missing"
                healthy=false
            fi
        else
            info "mcp.json present"
        fi
    else
        warn "mcp.json not found"
        healthy=false
    fi

    printf "\n"
    if $healthy; then
        info "All checks passed"
    else
        warn "Issues found — re-run: ./install.sh cursor${CURSOR_PATH:+ $CURSOR_PATH}"
    fi
    $healthy && exit 0 || exit 1
fi

# Install (default)

cd "$REPO_ROOT"
step "Target: $INSTALL_MODE"

# 1. Skills: symlink each skills/<name> -> TARGET/skills/<name>
step "Linking skills..."
mkdir -p "$CURSOR_DIR/skills"
for d in skills/*/; do
    name="${d%/}"
    name="${name#skills/}"
    [ -z "$name" ] && continue
    src="$REPO_ROOT/skills/$name"
    target="$CURSOR_DIR/skills/$name"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$src" ]; then
        :
    else
        ln -sf "$src" "$target"
    fi
done
info "Skills linked ($(ls -1 "$CURSOR_DIR/skills" 2>/dev/null | wc -l | tr -d ' ') skills)"

# 2. Rules (shared logic — see lib/install_shared.sh)
step "Linking rules..."
link_rules "$REPO_ROOT/rules" "$CURSOR_DIR/rules"
info "Rules linked ($LINK_RULES_COUNT rules)"

# 3. Commands: export plain .md into TARGET/commands/
step "Exporting commands..."
python3 "$CURSOR_CONFIG_DIR/export-cursor-commands.py" "$REPO_ROOT" "$CURSOR_DIR/commands"
info "Commands exported"

# 4. MCP: write mcp.json from cursor/config template
step "Writing mcp.json..."
MCP_ROOT="$(cd "$REPO_ROOT_FOR_MCP" && pwd)"
AGENTS_DIR_ABS="$MCP_ROOT/agents"
template="$CURSOR_CONFIG_DIR/mcp.json.template"
if [ ! -f "$template" ]; then
    echo "Error: cursor config template not found: $template" >&2
    exit 1
fi
mkdir -p "$CURSOR_DIR"
sed -e "s|{{MCP_ROOT}}|$MCP_ROOT|g" \
    -e "s|{{AGENTS_DIR_ABS}}|$AGENTS_DIR_ABS|g" \
    "$template" > "$CURSOR_DIR/mcp.json"
info "MCP config written to $CURSOR_DIR/mcp.json (servers use repo: $MCP_ROOT)"
info "sub-agents points at $AGENTS_DIR_ABS (requires Node/npx)"
info "chub (context-hub) configured for external API docs (requires Node/npx)"

printf "\n"
info "Cursor install complete."
step "Target: $CURSOR_DIR"
step "MCP: task-chronograph requires \`uv\`; sub-agents and chub require Node/npx."
