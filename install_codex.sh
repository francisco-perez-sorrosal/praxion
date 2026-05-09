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

print_codex_hook_review_note() {
    warn "Codex may require one-time review for the Praxion rules bridge hooks."
    step "If Codex reports '3 hooks need review', open /hooks and approve the Praxion PreToolUse, SessionStart, and UserPromptSubmit hooks."
    step "This is a Codex security gate for project-local commands; install.sh cannot pre-approve it."
}

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
CODEX_HOOKS_DIR="$CODEX_DIR/hooks"
CODEX_PRAXION_DIR="$CODEX_DIR/praxion"
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
    prune_stale_native_codex
    python3 "$PRAXION_ROOT/codex/config/export-codex-agents.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$CODEX_AGENTS_DIR" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/export-codex-skills.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$AGENT_SKILLS_DIR" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/export-codex-command-skills.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$AGENT_SKILLS_DIR" >/dev/null
    install_codex_rules_bridge
}

is_generated_agent_wrapper() {
    [ -f "$1" ] && grep -qF "# Generated by Praxion Codex exporter." "$1"
}

is_generated_skill_wrapper() {
    [ -f "$1" ] && {
        grep -qF "This is a Codex skill wrapper for Praxion." "$1" ||
        grep -qF "This is a Codex command-skill wrapper for a Praxion slash command." "$1"
    }
}

export_expected_native_codex() {
    local expected_root="$1"
    python3 "$PRAXION_ROOT/codex/config/export-codex-agents.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$expected_root/agents" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/export-codex-skills.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$expected_root/skills" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/export-codex-command-skills.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$expected_root/skills" >/dev/null
}

export_expected_rules_bridge() {
    local expected_root="$1"
    python3 "$PRAXION_ROOT/codex/config/export-codex-rules-bridge.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$expected_root" >/dev/null
}

install_codex_rules_bridge() {
    python3 "$PRAXION_ROOT/codex/config/export-codex-rules-bridge.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$CODEX_DIR" >/dev/null
    python3 "$PRAXION_ROOT/codex/config/manage-codex-rules-bridge.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode install >/dev/null
}

prune_stale_native_codex() {
    local expected_root existing_file rel_path
    expected_root="$(mktemp -d)"
    export_expected_native_codex "$expected_root"
    export_expected_rules_bridge "$expected_root/rules_bridge"

    if [ -d "$CODEX_AGENTS_DIR" ]; then
        while IFS= read -r existing_file; do
            [ -n "$existing_file" ] || continue
            rel_path="$(basename "$existing_file")"
            if is_generated_agent_wrapper "$existing_file" &&
               [ ! -f "$expected_root/agents/$rel_path" ]; then
                rm -f "$existing_file"
            fi
        done < <(find "$CODEX_AGENTS_DIR" -maxdepth 1 -name '*.toml' -type f | sort)
    fi

    if [ -d "$AGENT_SKILLS_DIR" ]; then
        while IFS= read -r existing_file; do
            [ -n "$existing_file" ] || continue
            rel_path="${existing_file#"$AGENT_SKILLS_DIR"/}"
            if is_generated_skill_wrapper "$existing_file" &&
               [ ! -f "$expected_root/skills/$rel_path" ]; then
                rm -f "$existing_file"
                rmdir "$(dirname "$existing_file")" 2>/dev/null || true
            fi
        done < <(find "$AGENT_SKILLS_DIR" -mindepth 2 -maxdepth 2 -path '*/SKILL.md' -type f | sort)
    fi

    if [ -d "$CODEX_HOOKS_DIR" ]; then
        while IFS= read -r existing_file; do
            [ -n "$existing_file" ] || continue
            rel_path="${existing_file#"$CODEX_DIR"/}"
            rel_path="${rel_path#/}"
            if [[ "$(basename "$existing_file")" == praxion-* ]] &&
               [ ! -f "$expected_root/rules_bridge/$rel_path" ]; then
                rm -f "$existing_file"
            fi
        done < <(find "$CODEX_HOOKS_DIR" -maxdepth 1 -name 'praxion-*' -type f | sort)
    fi

    if [ -d "$CODEX_PRAXION_DIR" ]; then
        while IFS= read -r existing_file; do
            [ -n "$existing_file" ] || continue
            rel_path="${existing_file#"$CODEX_DIR"/}"
            rel_path="${rel_path#/}"
            case "$(basename "$existing_file")" in
                rules_manifest.json|rules_lookup.py|hook_registrations.json|config_state.json)
                    if [ ! -f "$expected_root/rules_bridge/$rel_path" ] &&
                       [ "$(basename "$existing_file")" != "config_state.json" ]; then
                        rm -f "$existing_file"
                    fi
                    ;;
            esac
        done < <(find "$CODEX_PRAXION_DIR" -maxdepth 1 -type f | sort)
    fi

    rmdir "$CODEX_AGENTS_DIR" 2>/dev/null || true
    rmdir "$AGENT_SKILLS_DIR" 2>/dev/null || true
    rmdir "$CODEX_HOOKS_DIR" 2>/dev/null || true
    rmdir "$CODEX_PRAXION_DIR" 2>/dev/null || true
    rm -rf "$expected_root"
}

uninstall_native_codex() {
    if [ -d "$CODEX_AGENTS_DIR" ]; then
        while IFS= read -r agent_file; do
            [ -n "$agent_file" ] || continue
            if is_generated_agent_wrapper "$agent_file"; then
                rm -f "$agent_file"
            fi
        done < <(find "$CODEX_AGENTS_DIR" -maxdepth 1 -name '*.toml' -type f | sort)
    fi
    rmdir "$CODEX_AGENTS_DIR" 2>/dev/null || true
    uninstall_codex_rules_bridge
    uninstall_codex_skills
    rmdir "$CODEX_DIR" 2>/dev/null || true
    rmdir "$TARGET_ROOT/.agents" 2>/dev/null || true
}

uninstall_codex_skills() {
    [ -d "$AGENT_SKILLS_DIR" ] || return 0
    local wrapper_file
    while IFS= read -r wrapper_file; do
        [ -n "$wrapper_file" ] || continue
        if is_generated_skill_wrapper "$wrapper_file"; then
            rm -f "$wrapper_file"
            rmdir "$(dirname "$wrapper_file")" 2>/dev/null || true
        fi
    done < <(find "$AGENT_SKILLS_DIR" -mindepth 2 -maxdepth 2 -path '*/SKILL.md' -type f | sort)
    rmdir "$AGENT_SKILLS_DIR" 2>/dev/null || true
}

uninstall_codex_rules_bridge() {
    python3 "$PRAXION_ROOT/codex/config/manage-codex-rules-bridge.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode uninstall >/dev/null

    rm -f "$CODEX_HOOKS_DIR"/praxion-*.py 2>/dev/null || true
    rm -f "$CODEX_PRAXION_DIR"/rules_manifest.json 2>/dev/null || true
    rm -f "$CODEX_PRAXION_DIR"/rules_lookup.py 2>/dev/null || true
    rm -f "$CODEX_PRAXION_DIR"/hook_registrations.json 2>/dev/null || true
    rmdir "$CODEX_HOOKS_DIR" 2>/dev/null || true
    rmdir "$CODEX_PRAXION_DIR" 2>/dev/null || true
}

check_native_codex() {
    local expected_root expected_file actual_file rel_path check_rc=0
    expected_root="$(mktemp -d)"
    export_expected_native_codex "$expected_root"
    export_expected_rules_bridge "$expected_root/rules_bridge"

    while IFS= read -r expected_file; do
        [ -n "$expected_file" ] || continue
        rel_path="$(basename "$expected_file")"
        actual_file="$CODEX_AGENTS_DIR/$rel_path"
        if [ ! -f "$actual_file" ]; then
            warn "Codex native agent missing: $actual_file"
            check_rc=1
            continue
        fi
        if ! cmp -s "$expected_file" "$actual_file"; then
            warn "Codex native agent is stale: $actual_file"
            check_rc=1
        fi
    done < <(find "$expected_root/agents" -maxdepth 1 -name '*.toml' -type f | sort)

    if [ -d "$CODEX_AGENTS_DIR" ]; then
        while IFS= read -r actual_file; do
            [ -n "$actual_file" ] || continue
            rel_path="$(basename "$actual_file")"
            if is_generated_agent_wrapper "$actual_file" &&
               [ ! -f "$expected_root/agents/$rel_path" ]; then
                warn "Unexpected stale Praxion agent wrapper: $actual_file"
                check_rc=1
            fi
        done < <(find "$CODEX_AGENTS_DIR" -maxdepth 1 -name '*.toml' -type f | sort)
    fi

    while IFS= read -r expected_file; do
        [ -n "$expected_file" ] || continue
        rel_path="${expected_file#"$expected_root/skills"/}"
        rel_path="${rel_path#/}"
        actual_file="$AGENT_SKILLS_DIR/$rel_path"
        if [ ! -f "$actual_file" ]; then
            warn "Codex skill wrapper missing: $actual_file"
            check_rc=1
            continue
        fi
        if ! cmp -s "$expected_file" "$actual_file"; then
            warn "Codex skill wrapper is stale: $actual_file"
            check_rc=1
        fi
    done < <(find "$expected_root/skills" -mindepth 2 -maxdepth 2 -path '*/SKILL.md' -type f | sort)

    if [ -d "$AGENT_SKILLS_DIR" ]; then
        while IFS= read -r actual_file; do
            [ -n "$actual_file" ] || continue
            rel_path="${actual_file#"$AGENT_SKILLS_DIR"/}"
            rel_path="${rel_path#/}"
            if is_generated_skill_wrapper "$actual_file" &&
               [ ! -f "$expected_root/skills/$rel_path" ]; then
                warn "Unexpected stale Praxion skill wrapper: $actual_file"
                check_rc=1
            fi
        done < <(find "$AGENT_SKILLS_DIR" -mindepth 2 -maxdepth 2 -path '*/SKILL.md' -type f | sort)
    fi

    while IFS= read -r expected_file; do
        [ -n "$expected_file" ] || continue
        rel_path="${expected_file#"$expected_root/rules_bridge"/}"
        rel_path="${rel_path#/}"
        actual_file="$CODEX_DIR/$rel_path"
        if [ ! -f "$actual_file" ]; then
            warn "Codex rules bridge file missing: $actual_file"
            check_rc=1
            continue
        fi
        if ! cmp -s "$expected_file" "$actual_file"; then
            warn "Codex rules bridge file is stale: $actual_file"
            check_rc=1
        fi
    done < <(find "$expected_root/rules_bridge" -type f ! -name 'config_state.json' | sort)

    local rules_bridge_check_output
    rules_bridge_check_output="$(mktemp)"
    python3 "$PRAXION_ROOT/codex/config/manage-codex-rules-bridge.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode check >"$rules_bridge_check_output" 2>&1 || {
            cat "$rules_bridge_check_output" | while IFS= read -r line; do
                [ -n "$line" ] && warn "$line"
            done
            check_rc=1
        }
    rm -f "$rules_bridge_check_output" 2>/dev/null || true

    rm -rf "$expected_root"

    if [ "$check_rc" -eq 0 ]; then
        info "Codex native agents present in $CODEX_AGENTS_DIR"
        info "Codex skill and command wrappers present in $AGENT_SKILLS_DIR"
        info "Codex rules bridge present in $CODEX_DIR"
    fi
    return "$check_rc"
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
        step "Would export Praxion skill and command wrappers to $AGENT_SKILLS_DIR"
        step "Would export Praxion rules bridge to $CODEX_DIR"
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
        if [ "$check_rc" -eq 0 ]; then
            print_codex_hook_review_note
        fi
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
    info "Codex skill and command wrappers exported to $AGENT_SKILLS_DIR"
    info "Codex rules bridge exported to $CODEX_DIR"
    print_codex_hook_review_note
fi
step "Start a fresh AGENTS.md-aware agent session in the target project to auto-load it."
