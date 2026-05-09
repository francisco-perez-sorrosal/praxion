#!/usr/bin/env bash
# Install AGENTS.md-facing Praxion guidance into a target project.
# Repo remains source of truth; this script writes a small marked adapter block.
#
# Usage (from this repo root, or via install.sh):
#   ./install_codex.sh /path/to/project              # Install/update AGENTS.md
#   ./install_codex.sh /path/to/project --compat-only # Only install AGENTS.md
#   ./install_codex.sh /path/to/project --dry-run   # Show what would change
#   ./install_codex.sh /path/to/project --check     # Verify adapter block
#   ./install_codex.sh /path/to/project --uninstall # Remove adapter block

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_MARKER="<!-- PRAXION:AGENTS_ADAPTER:START -->"
END_MARKER="<!-- PRAXION:AGENTS_ADAPTER:END -->"

if [ -t 1 ]; then
    B=$'\033[1m' D=$'\033[2m' R=$'\033[0m'
else
    B='' D='' R=''
fi

info() { printf "  ✓ %s\n" "$*"; }
warn() { printf "  ⚠ %s\n" "$*"; }
fail() { printf "  ✗ %s\n" "$*" >&2; exit 1; }
header() { printf "\n${B}%s${R}\n" "$*"; }
step() { printf "  %s\n" "$*"; }

show_usage() {
    cat <<EOF
Usage: $(basename "$0") PATH [--check] [--dry-run] [--uninstall] [--help]

  PATH         Target project directory. Required.
  --native     Also install Codex-native adapter files under PATH/.codex/.
               This is the default; the flag is accepted for readability.
  --compat-only
               Only install the AGENTS.md compatibility pointer. Intended for
               non-Codex AGENTS.md-aware tools or debugging the bootstrap layer.
  --check      Verify PATH/AGENTS.md contains the Praxion adapter block.
  --dry-run    Show what would be installed, without writing files.
  --uninstall  Remove the Praxion adapter block from PATH/AGENTS.md.
  --help       Show this help.
EOF
    exit 0
}

TARGET_PATH=""
DO_CHECK=false
DO_DRY_RUN=false
DO_UNINSTALL=false
DO_NATIVE=true

while [ $# -gt 0 ]; do
    case "$1" in
        --native) DO_NATIVE=true ;;
        --compat-only) DO_NATIVE=false ;;
        --check) DO_CHECK=true ;;
        --dry-run|--status) DO_DRY_RUN=true ;;
        --uninstall) DO_UNINSTALL=true ;;
        -h|--help) show_usage ;;
        *)
            if [ -z "$TARGET_PATH" ]; then
                TARGET_PATH="$1"
            elif [[ "$1" == --* ]]; then
                fail "Unknown option: $1. Use --help for usage."
            else
                fail "Unexpected argument: $1. Use --help for usage."
            fi
            ;;
    esac
    shift
done

[ -n "$TARGET_PATH" ] || fail "PATH is required. Use: ./install.sh codex /path/to/project"
[ -d "$TARGET_PATH" ] || fail "Target is not a directory: $TARGET_PATH"

TARGET_ROOT="$(cd "$TARGET_PATH" && pwd)"
AGENTS_FILE="$TARGET_ROOT/AGENTS.md"
CODEX_DIR="$TARGET_ROOT/.codex"
CODEX_AGENTS_DIR="$CODEX_DIR/agents"
AGENT_SKILLS_DIR="$TARGET_ROOT/.agents/skills"
PRAXION_ROOT="$SCRIPT_DIR"

render_block() {
    cat <<EOF
$START_MARKER
## Praxion Adapter

This project uses Praxion guidance through AGENTS.md-compatible tooling.
Praxion's source artifacts are canonical; this block is only a pointer.

Praxion source:

\`\`\`text
$PRAXION_ROOT
\`\`\`

When working in this project:

1. Read \`$PRAXION_ROOT/AGENTS.md\` for the compatibility contract.
2. Read \`$PRAXION_ROOT/CLAUDE.md\` for Praxion baseline context.
3. Load relevant rules from \`$PRAXION_ROOT/rules/\` by reading the files.
4. Load matching skills from \`$PRAXION_ROOT/skills/<name>/SKILL.md\` and
   skill references only when needed.
5. Treat \`$PRAXION_ROOT/commands/*.md\` and \`$PRAXION_ROOT/agents/*.md\` as
   workflow specs unless this agentic framework has a native adapter for them.

Always-on Praxion stance:

- Surface Assumptions.
- Register Objection.
- Stay Surgical.
- Simplicity First.

Task sizing:

- Direct: single-file fix, config, doc, typo.
- Lightweight: 2-3 files, one behavior, clear scope.
- Standard: 4-8 files, 2-4 behaviors, architectural decisions.
- Full: 9+ files, 5+ behaviors, cross-cutting work.
- Spike: exploratory, uncertain outcome.

Praxion agents available through Codex custom-agent wrappers when the native
adapter is installed: promethean, researcher, systems-architect,
implementation-planner, context-engineer, implementer, test-engineer, verifier,
architect-validator, doc-engineer, sentinel, skill-genesis, cicd-engineer, and
roadmap-cartographer.

Praxion skills are exposed to Codex through project-local \`.agents/skills\`
wrapper skills. Load matching skills on demand; canonical skill files remain
the source of truth.

Do not copy Praxion rules, skills, commands, or agents into this file. Keep this
adapter small and update Praxion at the source.
$END_MARKER
EOF
}

has_block() {
    [ -f "$AGENTS_FILE" ] && grep -qF "$START_MARKER" "$AGENTS_FILE"
}

has_complete_block() {
    [ -f "$AGENTS_FILE" ] &&
        grep -qF "$START_MARKER" "$AGENTS_FILE" &&
        grep -qF "$END_MARKER" "$AGENTS_FILE"
}

require_well_formed_block() {
    [ -f "$AGENTS_FILE" ] || return 0
    if grep -qF "$START_MARKER" "$AGENTS_FILE" &&
       ! grep -qF "$END_MARKER" "$AGENTS_FILE"; then
        fail "Malformed Praxion adapter block in $AGENTS_FILE: missing end marker"
    fi
    if grep -qF "$END_MARKER" "$AGENTS_FILE" &&
       ! grep -qF "$START_MARKER" "$AGENTS_FILE"; then
        fail "Malformed Praxion adapter block in $AGENTS_FILE: missing start marker"
    fi
}

install_block() {
    local block_file tmp_file
    require_well_formed_block
    block_file="$(mktemp)"
    tmp_file="$(mktemp)"
    render_block > "$block_file"

    if [ ! -f "$AGENTS_FILE" ]; then
        {
            cat "$block_file"
            printf "\n"
        } > "$AGENTS_FILE"
        rm -f "$block_file" "$tmp_file"
        return
    fi

    if has_block; then
        awk -v start="$START_MARKER" -v end="$END_MARKER" -v block="$block_file" '
            $0 == start {
                while ((getline line < block) > 0) print line
                close(block)
                in_block = 1
                next
            }
            $0 == end {
                in_block = 0
                next
            }
            !in_block { print }
        ' "$AGENTS_FILE" > "$tmp_file"
        mv "$tmp_file" "$AGENTS_FILE"
    else
        {
            cat "$AGENTS_FILE"
            printf "\n\n"
            cat "$block_file"
            printf "\n"
        } > "$tmp_file"
        mv "$tmp_file" "$AGENTS_FILE"
    fi

    rm -f "$block_file" "$tmp_file"
}

uninstall_block() {
    [ -f "$AGENTS_FILE" ] || return 0
    require_well_formed_block
    has_block || return 0

    local tmp_file
    tmp_file="$(mktemp)"
    awk -v start="$START_MARKER" -v end="$END_MARKER" '
        $0 == start { in_block = 1; next }
        $0 == end { in_block = 0; next }
        !in_block { print }
    ' "$AGENTS_FILE" > "$tmp_file"
    mv "$tmp_file" "$AGENTS_FILE"
    if ! grep -q '[^[:space:]]' "$AGENTS_FILE"; then
        rm -f "$AGENTS_FILE"
    fi
}

praxion_agent_names() {
    for agent_file in "$PRAXION_ROOT"/agents/*.md; do
        case "$(basename "$agent_file")" in
            CLAUDE.md|README.md) continue ;;
        esac
        sed -n 's/^name:[[:space:]]*//p' "$agent_file" | head -1
    done
}

praxion_skill_names() {
    for skill_file in "$PRAXION_ROOT"/skills/*/SKILL.md; do
        [ -f "$skill_file" ] || continue
        basename "$(dirname "$skill_file")"
    done
}

install_native_codex() {
    python3 "$PRAXION_ROOT/codex/config/export-codex-agents.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$CODEX_AGENTS_DIR" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/export-codex-skills.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$AGENT_SKILLS_DIR" >/dev/null
}

uninstall_native_codex() {
    [ -d "$CODEX_AGENTS_DIR" ] || return 0
    while IFS= read -r agent_name; do
        [ -n "$agent_name" ] || continue
        rm -f "$CODEX_AGENTS_DIR/$agent_name.toml"
    done < <(praxion_agent_names)
    rmdir "$CODEX_AGENTS_DIR" 2>/dev/null || true
    rmdir "$CODEX_DIR" 2>/dev/null || true
    uninstall_codex_skills
    rmdir "$TARGET_ROOT/.agents" 2>/dev/null || true
}

uninstall_codex_skills() {
    [ -d "$AGENT_SKILLS_DIR" ] || return 0
    local skill_name wrapper_file
    while IFS= read -r skill_name; do
        [ -n "$skill_name" ] || continue
        wrapper_file="$AGENT_SKILLS_DIR/$skill_name/SKILL.md"
        if [ -f "$wrapper_file" ] && grep -qF "This is a Codex skill wrapper for Praxion." "$wrapper_file"; then
            rm -f "$wrapper_file"
            rmdir "$AGENT_SKILLS_DIR/$skill_name" 2>/dev/null || true
        fi
    done < <(praxion_skill_names)
    rmdir "$AGENT_SKILLS_DIR" 2>/dev/null || true
}

check_native_codex() {
    local researcher_file="$CODEX_AGENTS_DIR/researcher.toml"
    local software_planning_skill="$AGENT_SKILLS_DIR/software-planning/SKILL.md"
    if [ ! -f "$researcher_file" ]; then
        warn "Codex native agent missing: $researcher_file"
        return 1
    fi
    if ! grep -qF 'agents/researcher.md' "$researcher_file"; then
        warn "Codex researcher wrapper is stale: $researcher_file"
        return 1
    fi
    if [ ! -f "$software_planning_skill" ]; then
        warn "Codex skill wrapper missing: $software_planning_skill"
        return 1
    fi
    if ! grep -qF '`skills/software-planning/SKILL.md`' "$software_planning_skill"; then
        warn "Codex skill wrapper stale: $software_planning_skill"
        return 1
    fi
    info "Codex native agents present in $CODEX_AGENTS_DIR"
    info "Codex skill wrappers present in $AGENT_SKILLS_DIR"
}

header "Codex / AGENTS.md Adapter"
step "Target: $TARGET_ROOT"
step "Praxion source: $PRAXION_ROOT"

if $DO_DRY_RUN; then
    if [ -f "$AGENTS_FILE" ]; then
        if has_block; then
            step "Would update existing Praxion block in $AGENTS_FILE"
        else
            step "Would append Praxion block to existing $AGENTS_FILE"
        fi
    else
        step "Would create $AGENTS_FILE"
    fi
    if $DO_NATIVE; then
        step "Would export Praxion agents to $CODEX_AGENTS_DIR"
        step "Would export Praxion skill wrappers to $AGENT_SKILLS_DIR"
    fi
    exit 0
fi

if $DO_CHECK; then
    check_rc=0
    if has_complete_block && grep -qF "$PRAXION_ROOT" "$AGENTS_FILE"; then
        info "Praxion adapter block present in $AGENTS_FILE"
    else
        warn "Praxion adapter block missing or stale in $AGENTS_FILE"
        check_rc=1
    fi
    if $DO_NATIVE; then
        check_native_codex || check_rc=1
    fi
    exit "$check_rc"
fi

if $DO_UNINSTALL; then
    if $DO_NATIVE; then
        uninstall_native_codex
        info "Codex native adapter files removed from $CODEX_DIR"
    fi
    uninstall_block
    info "Praxion adapter block removed from $AGENTS_FILE"
    exit 0
fi

install_block
info "Praxion adapter installed in $AGENTS_FILE"
if $DO_NATIVE; then
    install_native_codex
    info "Codex native agents exported to $CODEX_AGENTS_DIR"
    info "Codex skill wrappers exported to $AGENT_SKILLS_DIR"
fi
step "Start a fresh AGENTS.md-aware agent session in the target project to auto-load it."
