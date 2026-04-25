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
FINALIZE_SCRIPT="$REPO_ROOT/scripts/finalize_adrs.py"
FINALIZE_TD_LEDGER_SCRIPT="$REPO_ROOT/scripts/finalize_tech_debt_ledger.py"
SQUASH_CHECK_SCRIPT="$REPO_ROOT/scripts/check_squash_safety.py"
if [ ! -f "$RECONCILE_SCRIPT" ]; then
    exit 0
fi

# Post-merge ordering (load-bearing):
#   1. reconcile_ai_state.py --post-merge        — settles memory.json / observations.jsonl / legacy ADR NNN collisions
#   2. finalize_adrs.py --merged                  — promotes draft ADRs to stable NNN, rewrites cross-references
#   3. finalize_tech_debt_ledger.py --merged      — collapses duplicate rows in .ai-state/TECH_DEBT_LEDGER.md by dedup_key
#   4. check_squash_safety.py                     — diagnostic: warns if squash erased .ai-state/ (non-blocking)
# Rationale: reconcile settles orthogonal file conflicts first; finalize_adrs rewrites ADR cross-refs on a settled tree;
# finalize_tech_debt_ledger dedupes ledger rows (orthogonal to ADRs, but runs after so an ADR-finalize-driven worktree
# merge sees the ledger stable); diagnostic checks run last on a fully-reconciled tree.

# Only run if .ai-state/decisions/ was involved in the merge
MERGED_FILES="$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
if echo "$MERGED_FILES" | grep -q "^\.ai-state/"; then
    python3 "$RECONCILE_SCRIPT" --post-merge 2>/dev/null || true
fi

# 2. finalize_adrs.py --merged — promote drafts to stable NNN after reconcile has settled.
# Non-blocking: the hook cannot abort an already-completed merge, so we log warnings
# loudly rather than swallowing silently.
if [ -f "$FINALIZE_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
    python3 "$FINALIZE_SCRIPT" --merged 2>&1 || \
        echo "post-merge: finalize_adrs warned (non-blocking) — inspect output above"
fi

# 3. finalize_tech_debt_ledger.py --merged — collapse duplicate ledger rows by dedup_key.
# Non-blocking: the hook cannot abort an already-completed merge; a malformed row surfaces
# via non-zero exit but the `|| echo ...` idiom keeps the rest of the chain running.
if [ -f "$FINALIZE_TD_LEDGER_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
    python3 "$FINALIZE_TD_LEDGER_SCRIPT" --merged 2>&1 || \
        echo "post-merge: finalize_tech_debt_ledger warned (non-blocking) — inspect output above"
fi

# 4. check_squash_safety.py — diagnostic: warn loudly if squash-merge erased .ai-state/.
# Non-blocking: the hook cannot abort a completed merge; the script always exits 0.
# Multi-parent merges are skipped internally.
if [ -x "$SQUASH_CHECK_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
    python3 "$SQUASH_CHECK_SCRIPT" 2>&1 || \
        echo "post-merge: check_squash_safety warning emitted (non-blocking)"
fi
