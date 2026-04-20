#!/usr/bin/env bash
# new_cc_project.sh — Greenfield Claude-ready project bootstrap.
#
# Validates host prereqs, lays down a minimal scaffold (.git, .gitignore, .claude),
# then exec's an interactive Claude Code session seeded with /new-cc-project.
#
# Usage: new_cc_project.sh <project-name> [target-dir]
# Env vars:
#   PRAXION_NEW_CC_EDITOR  Which editor surface to open the scaffold in.
#                          Values: auto (default; cursor → code), cursor,
#                          code, claude-desktop, none. The claude-desktop
#                          option launches Claude.app and copies the project
#                          path to the clipboard (macOS only) since the
#                          desktop app has no documented CLI/URL hook to
#                          open a folder programmatically.
# Exit codes: 0 ok, 2 usage/invalid name, 3 no claude, 4 no plugin, 5 no git,
#             6 target exists & non-empty.
# See docs/project-onboarding.md for the full flow and troubleshooting matrix.

set -eo pipefail

# Exit codes — named for readability per coding-style "no magic values".
readonly EXIT_USAGE=2
readonly EXIT_NO_CLAUDE=3
readonly EXIT_NO_PLUGIN=4
readonly EXIT_NO_GIT=5
readonly EXIT_TARGET_EXISTS=6

readonly NAME_REGEX='^[A-Za-z0-9][A-Za-z0-9._-]*$'
readonly PLUGIN_FILE="${HOME}/.claude/plugins/installed_plugins.json"
readonly PLUGIN_KEY='i-am@bit-agora'

usage() {
    printf 'Usage: new_cc_project.sh <project-name> [target-dir]\n' >&2
}

# Parse args (REQ-ONBOARD-01).
if [ $# -lt 1 ] || [ -z "${1:-}" ]; then
    usage
    exit "$EXIT_USAGE"
fi
project_name="$1"
target_dir="${2:-$PWD}"

# Validate project name (security lens; SYSTEMS_PLAN §Stakeholder Review).
if ! [[ "$project_name" =~ $NAME_REGEX ]]; then
    printf "Error: invalid project name '%s'.\n" "$project_name" >&2
    printf 'Project name must match %s — letters/digits first, then letters, digits, dot, underscore, or hyphen.\n' "$NAME_REGEX" >&2
    exit "$EXIT_USAGE"
fi

# Prereq: claude binary (REQ-ONBOARD-02).
if ! command -v claude >/dev/null 2>&1; then
    cat >&2 <<EOF
Error: 'claude' binary not found in PATH.
This tool requires Claude Code. Install it from https://claude.com/product/claude-code
and re-run this script.
EOF
    exit "$EXIT_NO_CLAUDE"
fi

# Prereq: i-am plugin recorded in user-scope plugin registry (REQ-ONBOARD-03).
if [ ! -f "$PLUGIN_FILE" ] || ! grep -q "$PLUGIN_KEY" "$PLUGIN_FILE"; then
    cat >&2 <<EOF
Error: the 'i-am' plugin is not installed in your Claude Code user scope.
Run './install.sh code' from the Praxion repo, then re-run this script.
(Checked: ${PLUGIN_FILE} for '${PLUGIN_KEY}'.)
EOF
    exit "$EXIT_NO_PLUGIN"
fi

# Prereq: git binary (REQ-ONBOARD-04).
if ! command -v git >/dev/null 2>&1; then
    cat >&2 <<EOF
Error: 'git' not found in PATH.
Install git (e.g., 'brew install git' on macOS) and re-run.
EOF
    exit "$EXIT_NO_GIT"
fi

# Collision check (REQ-ONBOARD-05) — must precede any mkdir.
project_path="${target_dir%/}/${project_name}"
if [ -e "$project_path" ] && [ -n "$(ls -A "$project_path" 2>/dev/null)" ]; then
    cat >&2 <<EOF
Error: '${project_path}' already exists and is not empty.
Pick a different name or target directory, or remove the existing path.
EOF
    exit "$EXIT_TARGET_EXISTS"
fi

# Scaffold (REQ-ONBOARD-06).
mkdir -p "$project_path"
cd "$project_path"
git init -q
mkdir -p .claude
cat > .gitignore <<'EOF'
# AI assistants
.ai-work/
.env
.env.*
.claude/settings.local.json
EOF

# Open the project in the user's chosen surface so they can watch .ai-work/
# and .ai-state/ appear as the pipeline runs. Selection is driven by the
# PRAXION_NEW_CC_EDITOR env var:
#   unset / auto    → cursor first, then VS Code (legacy behavior)
#   cursor          → Cursor only
#   code            → VS Code only
#   claude-desktop  → Claude.app (the unified Claude Code desktop app); no
#                     CLI flag or URL scheme exists to open a path directly,
#                     so we launch the app + copy the path to the clipboard
#                     and ask the user to paste into "Select folder".
#   none            → no editor launch (pure-terminal environments)
# Absent editors are not an error — onboarding still works without one.
editor_choice="${PRAXION_NEW_CC_EDITOR:-auto}"
editor_launched=""
desktop_path_announce=""

launch_cursor_if_present() {
    if command -v cursor >/dev/null 2>&1; then
        cursor "$project_path" "$project_path/.gitignore" >/dev/null 2>&1 &
        editor_launched="cursor"
        return 0
    fi
    return 1
}

launch_code_if_present() {
    if command -v code >/dev/null 2>&1; then
        code "$project_path" "$project_path/.gitignore" >/dev/null 2>&1 &
        editor_launched="code"
        return 0
    fi
    return 1
}

# Launch Claude.app (bundle id com.anthropic.claudefordesktop). The desktop
# app has no documented way to open a folder from the CLI — we launch it and
# pre-stage the project path on the clipboard so the user only has to click
# "Select folder" + paste. The path is also printed verbatim as a fallback
# for environments without pbcopy.
launch_claude_desktop() {
    if [ "$(uname -s)" != "Darwin" ]; then
        printf '→ PRAXION_NEW_CC_EDITOR=claude-desktop is only wired for macOS today.\n' >&2
        printf '  Open Claude Code desktop manually and select this folder: %s\n' "$project_path" >&2
        return 1
    fi
    if ! open -a "Claude" >/dev/null 2>&1; then
        printf '→ Could not launch Claude.app (is the Claude Code desktop app installed?).\n' >&2
        printf '  Install from https://claude.ai/download, then open it and select: %s\n' "$project_path" >&2
        return 1
    fi
    if command -v pbcopy >/dev/null 2>&1; then
        printf '%s' "$project_path" | pbcopy
        desktop_path_announce="path copied to clipboard — paste into 'Select folder'"
    else
        desktop_path_announce="select this folder manually: $project_path"
    fi
    editor_launched="claude-desktop"
    return 0
}

case "$editor_choice" in
    auto)
        launch_cursor_if_present || launch_code_if_present || true
        ;;
    cursor)
        launch_cursor_if_present || \
            printf '→ PRAXION_NEW_CC_EDITOR=cursor but the cursor CLI is not on PATH.\n' >&2
        ;;
    code)
        launch_code_if_present || \
            printf '→ PRAXION_NEW_CC_EDITOR=code but the code CLI is not on PATH.\n' >&2
        ;;
    claude-desktop)
        launch_claude_desktop || true
        ;;
    none)
        ;;
    *)
        printf '→ PRAXION_NEW_CC_EDITOR=%s is not recognized; valid: auto|cursor|code|claude-desktop|none.\n' \
            "$editor_choice" >&2
        ;;
esac

# Pre-flight announcement (REQ-ONBOARD-07).
if [ "$editor_launched" = "claude-desktop" ]; then
    printf '→ Launched Claude Code desktop app — %s.\n' "$desktop_path_announce"
elif [ -n "$editor_launched" ]; then
    printf '→ Opened project in %s (file tree will refresh as Praxion writes files).\n' \
        "$editor_launched"
fi
printf '→ Scaffolded %s at %s. Launching Claude Code...\n' \
    "$project_name" "$project_path"

# Locate the /new-cc-project command body so we can embed it as the seed prompt.
# Claude Code's CLI does NOT dispatch slash commands from positional args — they
# are treated as literal user messages. Embedding the command body keeps the
# handoff deterministic regardless of slash-command plumbing.
cmd_body_file="$(find "$HOME/.claude/plugins" -maxdepth 6 -name new-cc-project.md -type f -print 2>/dev/null | head -n 1 || true)"
if [ -z "$cmd_body_file" ]; then
    # Dev fallback: invoked directly from a Praxion checkout.
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$script_dir/commands/new-cc-project.md" ]; then
        cmd_body_file="$script_dir/commands/new-cc-project.md"
    fi
fi

# Strip YAML frontmatter (the leading `---`...`---` block) before embedding the
# command body. The frontmatter is metadata for Claude Code's slash dispatcher;
# when embedded inline as a positional arg it is dead weight AND a parser
# hazard — `claude` reads a leading `---description:` as an unknown long option
# and aborts. Strip with awk: skip the first `---` line, then everything until
# the closing `---`, then print the rest verbatim.
strip_frontmatter() {
    awk 'BEGIN{state=0} state==0 && /^---[[:space:]]*$/ {state=1; next}
         state==1 && /^---[[:space:]]*$/ {state=2; next}
         state==2 {print}' "$1"
}

if [ -n "$cmd_body_file" ] && [ -f "$cmd_body_file" ]; then
    seed_prompt="$(strip_frontmatter "$cmd_body_file")

---

The text above is the body of the /new-cc-project slash command. The bash bootstrap embeds it here because Claude Code's CLI does not dispatch slash commands from positional arguments. You are now inside a freshly scaffolded Praxion greenfield project. Execute those instructions in order, starting from the §Guard check. Do not ask me to invoke anything — begin now."
else
    seed_prompt="You are inside a freshly scaffolded Praxion greenfield project. Invoke the /new-cc-project slash command now to onboard it. If the slash command is not registered, locate its body under ~/.claude/plugins/ (Markdown file named new-cc-project.md) and follow its instructions."
fi

# Pre-allow the tools the seed pipeline relies on so the user is not paged
# for every chub fetch / Bash probe during the headline pipeline run.
# Onboarding is a teaching moment — broader-than-strict by design. The
# `mcp__chub__*` glob covers chub MCP additions without future churn here.
ALLOWED_TOOLS="mcp__chub__*,WebFetch,WebSearch,Bash(uv:*),Bash(git:*),Bash(grep:*),Bash(pytest:*),Bash(test:*)"

# Hand off (REQ-ONBOARD-08). `--` stops `claude` from interpreting any leading
# dash in the seed prompt as a flag.
exec claude --permission-mode acceptEdits --allowedTools "$ALLOWED_TOOLS" -- "$seed_prompt"
