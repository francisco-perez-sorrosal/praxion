#!/usr/bin/env bash
# Git post-merge hook: reconcile .ai-state/ artifacts after merge.
#
# Handles ADR sequence number conflicts and regenerates DECISIONS_INDEX.md.
# Memory and observations reconciliation is handled by custom merge drivers
# (see .gitattributes), so this hook only covers post-merge-only tasks.
#
# Installed by install_claude.sh into .git/hooks/post-merge.

set -eo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    exit 0
fi

RECONCILE_SCRIPT="$REPO_ROOT/scripts/reconcile_ai_state.py"
if [ ! -f "$RECONCILE_SCRIPT" ]; then
    exit 0
fi

# Only run if .ai-state/decisions/ was involved in the merge
MERGED_FILES="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
if echo "$MERGED_FILES" | grep -q "^\.ai-state/"; then
    python3 "$RECONCILE_SCRIPT" --post-merge 2>/dev/null || true
fi
