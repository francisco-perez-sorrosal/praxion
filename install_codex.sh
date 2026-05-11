#!/usr/bin/env bash
# Install AGENTS.md-facing Praxion guidance into a target project.
# Repo remains source of truth; this script writes a marked managed block.
#
# Usage (from this repo root, or via install.sh):
#   ./install_codex.sh /path/to/project              # Install/update AGENTS.md
#   ./install_codex.sh /path/to/project --compat-only # Only install AGENTS.md
#   ./install_codex.sh /path/to/project --dry-run   # Show what would change
#   ./install_codex.sh /path/to/project --check     # Verify managed block
#   ./install_codex.sh /path/to/project --uninstall # Remove managed block

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_MARKER="<!-- PRAXION:AGENTS_ADAPTER:START -->"
END_MARKER="<!-- PRAXION:AGENTS_ADAPTER:END -->"
PROJECT_BASELINE_TEMPLATE="${SCRIPT_DIR}/codex/config/AGENTS.md.tmpl"
PROJECT_BASELINE_START="<!-- PRAXION:PROJECT_BASELINE:START -->"
PROJECT_BASELINE_END="<!-- PRAXION:PROJECT_BASELINE:END -->"
CLAUDE_PERSONAL_INFO_ENV_DEFAULT="${SCRIPT_DIR}/claude/config/.personal_info.env"
CLAUDE_PERSONAL_INFO_ENV="${PRAXION_PERSONAL_INFO_ENV:-$CLAUDE_PERSONAL_INFO_ENV_DEFAULT}"

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
    warn "Codex may require one-time review for the Praxion project-local hooks."
    step "If Codex reports hooks need review, open /hooks and approve the Praxion SessionStart, Stop, UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart, SubagentStop, and PreCompact hooks."
    step "This is a Codex security gate for project-local commands; install.sh cannot pre-approve it."
}

show_usage() {
    cat <<EOF
Usage: $(basename "$0") PATH [--check] [--dry-run] [--uninstall] [--help]

  PATH         Target project directory. Required.
  --native     Also install Codex-native adapter files under PATH/.codex/.
               This is the default; the flag is accepted for readability.
               Native Codex install is project-local by default and updates
               PATH/.codex plus PATH/.agents only.
  --compat-only
               Only install the AGENTS.md compatibility pointer. Intended for
               non-Codex AGENTS.md-aware tools or debugging the bootstrap layer.
  --check      Verify PATH/AGENTS.md contains the Praxion managed block.
  --dry-run    Show what would be installed, without writing files.
  --uninstall  Remove the Praxion managed block from PATH/AGENTS.md.
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

load_render_personal_info_args() {
    if [ -f "$CLAUDE_PERSONAL_INFO_ENV" ]; then
        # shellcheck source=/dev/null
        source "$CLAUDE_PERSONAL_INFO_ENV"
        if [ -n "${PRAXION_USERNAME:-}" ] &&
           [ -n "${PRAXION_EMAIL:-}" ] &&
           [ -n "${PRAXION_GITHUB_URL:-}" ]; then
            printf '%s\n' "$PRAXION_USERNAME" "$PRAXION_EMAIL" "$PRAXION_GITHUB_URL"
            return 0
        fi
    fi
    return 1
}

render_template_file() {
    local template_path="$1"
    local output_path="$2"
    local values

    if values="$(load_render_personal_info_args)"; then
        mapfile -t personal_info < <(printf '%s\n' "$values")
        python3 "$PRAXION_ROOT/scripts/render_claude_md.py" \
            "$template_path" "$output_path" \
            "${personal_info[0]}" "${personal_info[1]}" "${personal_info[2]}" >/dev/null
        return
    fi

    python3 "$PRAXION_ROOT/scripts/render_claude_md.py" \
        "$template_path" "$output_path" >/dev/null
}

render_project_baseline() {
    local rendered_template
    [ -f "$PROJECT_BASELINE_TEMPLATE" ] || fail "Codex AGENTS template not found: $PROJECT_BASELINE_TEMPLATE"
    rendered_template="$(mktemp)"
    render_template_file "$PROJECT_BASELINE_TEMPLATE" "$rendered_template"
    awk -v start="$PROJECT_BASELINE_START" -v end="$PROJECT_BASELINE_END" '
        $0 == start { in_block = 1; next }
        $0 == end { in_block = 0; next }
        in_block { print }
    ' "$rendered_template"
    rm -f "$rendered_template"
}

render_block() {
    cat <<EOF
$START_MARKER
# Development Guidelines for Codex

$(render_project_baseline)

## Project Layering

This managed Praxion block is installed first so Codex sees the shared Praxion
Codex philosophy before any project-specific instructions that may also live in
this project's \`AGENTS.md\`.

Project-specific instructions are expected to appear after this managed block.

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
6. If \`.codex/praxion/pipeline_semantics.json\` exists, read it before task
   sizing or delegation; it is the Codex-native translation of Praxion
   pipeline semantics.
7. If \`.codex/praxion/model_routing.json\` exists, read it before choosing
   model or reasoning settings for Codex agent work; it is the Codex adapter
   for Praxion's Claude-only routing rule.

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
        fail "Malformed Praxion managed block in $AGENTS_FILE: missing end marker"
    fi
    if grep -qF "$END_MARKER" "$AGENTS_FILE" &&
       ! grep -qF "$START_MARKER" "$AGENTS_FILE"; then
        fail "Malformed Praxion managed block in $AGENTS_FILE: missing start marker"
    fi
}

install_block() {
    local block_file remainder_file tmp_file
    require_well_formed_block
    block_file="$(mktemp)"
    remainder_file="$(mktemp)"
    tmp_file="$(mktemp)"
    render_block > "$block_file"

    if [ ! -f "$AGENTS_FILE" ]; then
        {
            cat "$block_file"
            printf "\n"
        } > "$AGENTS_FILE"
        rm -f "$block_file" "$remainder_file" "$tmp_file"
        return
    fi

    awk -v start="$START_MARKER" -v end="$END_MARKER" '
        $0 == start { in_block = 1; next }
        $0 == end { in_block = 0; next }
        !in_block { print }
    ' "$AGENTS_FILE" > "$remainder_file"

    {
        cat "$block_file"
        if grep -q '[^[:space:]]' "$remainder_file"; then
            printf "\n\n"
            cat "$remainder_file"
        else
            printf "\n"
        fi
    } > "$tmp_file"
    mv "$tmp_file" "$AGENTS_FILE"

    rm -f "$block_file" "$remainder_file" "$tmp_file"
}

uninstall_block() {
    [ -f "$AGENTS_FILE" ] || return 0
    require_well_formed_block
    has_block || return 0

    local tmp_file trimmed_file
    tmp_file="$(mktemp)"
    trimmed_file="$(mktemp)"
    awk -v start="$START_MARKER" -v end="$END_MARKER" '
        $0 == start { in_block = 1; next }
        $0 == end { in_block = 0; next }
        !in_block { print }
    ' "$AGENTS_FILE" > "$tmp_file"
    sed '/./,$!d' "$tmp_file" > "$trimmed_file"
    mv "$trimmed_file" "$AGENTS_FILE"
    if ! grep -q '[^[:space:]]' "$AGENTS_FILE"; then
        rm -f "$AGENTS_FILE"
    fi
    rm -f "$tmp_file" "$trimmed_file"
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
    install_codex_pipeline_adapter
    install_codex_mcp
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

export_expected_pipeline_adapter() {
    local expected_root="$1"
    python3 "$PRAXION_ROOT/codex/config/export-codex-pipeline-adapter.py" \
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

install_codex_pipeline_adapter() {
    python3 "$PRAXION_ROOT/codex/config/export-codex-pipeline-adapter.py" \
        --repo-root "$PRAXION_ROOT" \
        --out-dir "$CODEX_DIR" >/dev/null
}

install_codex_mcp() {
    python3 "$PRAXION_ROOT/codex/config/manage-codex-mcp.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode install >/dev/null
}

prune_stale_native_codex() {
    local expected_root existing_file rel_path
    expected_root="$(mktemp -d)"
    export_expected_native_codex "$expected_root"
    export_expected_rules_bridge "$expected_root/rules_bridge"
    export_expected_pipeline_adapter "$expected_root/pipeline_adapter"

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
                rules_manifest.json|rules_lookup.py|hook_runtime.py|hook_registrations.json|pipeline_semantics.json|model_routing.json|config_state.json)
                    if [ ! -f "$expected_root/rules_bridge/$rel_path" ] &&
                       [ ! -f "$expected_root/pipeline_adapter/$rel_path" ] &&
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
    uninstall_codex_pipeline_adapter
    uninstall_codex_mcp
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
    rm -f "$CODEX_PRAXION_DIR"/hook_runtime.py 2>/dev/null || true
    rm -f "$CODEX_PRAXION_DIR"/hook_registrations.json 2>/dev/null || true
    rmdir "$CODEX_HOOKS_DIR" 2>/dev/null || true
    rmdir "$CODEX_PRAXION_DIR" 2>/dev/null || true
}

uninstall_codex_pipeline_adapter() {
    rm -f "$CODEX_PRAXION_DIR"/pipeline_semantics.json 2>/dev/null || true
    rm -f "$CODEX_PRAXION_DIR"/model_routing.json 2>/dev/null || true
    rmdir "$CODEX_PRAXION_DIR" 2>/dev/null || true
}

uninstall_codex_mcp() {
    python3 "$PRAXION_ROOT/codex/config/manage-codex-mcp.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode uninstall >/dev/null
}

check_native_codex() {
    local expected_root expected_file actual_file rel_path check_rc=0
    expected_root="$(mktemp -d)"
    export_expected_native_codex "$expected_root"
    export_expected_rules_bridge "$expected_root/rules_bridge"
    export_expected_pipeline_adapter "$expected_root/pipeline_adapter"

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

    while IFS= read -r expected_file; do
        [ -n "$expected_file" ] || continue
        rel_path="${expected_file#"$expected_root/pipeline_adapter"/}"
        rel_path="${rel_path#/}"
        actual_file="$CODEX_DIR/$rel_path"
        if [ ! -f "$actual_file" ]; then
            warn "Codex pipeline adapter file missing: $actual_file"
            check_rc=1
            continue
        fi
        if ! cmp -s "$expected_file" "$actual_file"; then
            warn "Codex pipeline adapter file is stale: $actual_file"
            check_rc=1
        fi
    done < <(find "$expected_root/pipeline_adapter" -type f | sort)

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

    local mcp_check_output
    mcp_check_output="$(mktemp)"
    python3 "$PRAXION_ROOT/codex/config/manage-codex-mcp.py" \
        --repo-root "$PRAXION_ROOT" \
        --project-root "$TARGET_ROOT" \
        --mode check >"$mcp_check_output" 2>&1 || {
            cat "$mcp_check_output" | while IFS= read -r line; do
                [ -n "$line" ] && warn "$line"
            done
            check_rc=1
        }
    rm -f "$mcp_check_output" 2>/dev/null || true

    rm -rf "$expected_root"

    if [ "$check_rc" -eq 0 ]; then
        info "Codex native agents present in $CODEX_AGENTS_DIR"
        info "Codex skill and command wrappers present in $AGENT_SKILLS_DIR"
        info "Codex rules bridge present in $CODEX_DIR"
        info "Codex pipeline adapter present in $CODEX_PRAXION_DIR"
        info "Codex project MCP config present in $CODEX_DIR/config.toml"
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
        step "Would export Praxion pipeline adapter to $CODEX_PRAXION_DIR"
        step "Would update project Codex config in $CODEX_DIR/config.toml"
    fi
    exit 0
fi

if $DO_CHECK; then
    check_rc=0
    if has_complete_block && grep -qF "$PRAXION_ROOT" "$AGENTS_FILE"; then
        info "Praxion managed block present in $AGENTS_FILE"
    else
        warn "Praxion managed block missing or stale in $AGENTS_FILE"
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
        info "Codex project config updated in $CODEX_DIR/config.toml"
    fi
    uninstall_block
    info "Praxion managed block removed from $AGENTS_FILE"
    exit 0
fi

install_block
info "Praxion adapter installed in $AGENTS_FILE"
if $DO_NATIVE; then
    install_native_codex
    info "Codex native agents exported to $CODEX_AGENTS_DIR"
    info "Codex skill and command wrappers exported to $AGENT_SKILLS_DIR"
    info "Codex rules bridge exported to $CODEX_DIR"
    info "Codex pipeline adapter exported to $CODEX_PRAXION_DIR"
    info "Codex project config updated in $CODEX_DIR/config.toml"
    print_codex_hook_review_note
fi
step "Start a fresh AGENTS.md-aware agent session in the target project to auto-load it."
