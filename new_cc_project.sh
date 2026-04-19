#!/usr/bin/env bash
# new_cc_project.sh — Greenfield Claude-ready project bootstrap.
#
# Validates host prereqs, lays down a minimal scaffold (.git, .gitignore, .claude),
# then exec's an interactive Claude Code session seeded with /new-cc-project.
#
# Usage: new_cc_project.sh <project-name> [target-dir]
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

# Pre-flight announcement (REQ-ONBOARD-07).
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

# Hand off (REQ-ONBOARD-08). `--` stops `claude` from interpreting any leading
# dash in the seed prompt as a flag.
exec claude --permission-mode acceptEdits -- "$seed_prompt"
