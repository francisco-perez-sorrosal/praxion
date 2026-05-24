#!/usr/bin/env bash
# scripts/finalize_chain.sh — shared library for the .ai-state/ finalize chain.
#
# Sourced by git-finalize-hook.sh (the multiplexed dispatcher symlinked to
# .git/hooks/{post-merge,post-commit,post-checkout}). Single source of truth for:
#
#   - Path resolution (works for both cp-installed and symlink-installed hooks)
#   - Repo-state predicates (on_main, drafts_present, state_was_touched)
#   - Composition of the finalize chain (ADR drafts -> dec-NNN, ledger dedup,
#     reconcile, squash-safety diagnostic)
#
# Public entry points (called from hooks):
#
#   finalize_chain_post_merge       — reconcile + state-driven finalize + squash-safety
#   finalize_chain_post_commit      — state-driven finalize on main (ADR promotion sub-gated on drafts)
#   finalize_chain_post_checkout    — state-driven finalize on branch switch to main
#
# Design rules:
#
#   - State-triggered, not event-triggered. Each finalizer gates on its OWN
#     state: ADR-draft promotion fires when drafts are present on main; tech-debt
#     ledger reconciliation fires on any on-main commit (byte-equivalent no-op
#     when idle). So any path landing work on main (ff merge, direct commit,
#     rebase, squash, fresh clone, branch reset) eventually triggers the
#     relevant finalizer. Rationale: the original `--merged` event-detection
#     silently skipped non-merge paths, and bundling tech-debt finalize behind
#     the drafts gate stranded resolutions committed without a concurrent ADR draft.
#
#   - Non-blocking. A failed step warns; a missing script is skipped. Hooks
#     cannot abort an already-completed git operation, so the exit code is
#     always 0.
#
#   - Idempotent. The python scripts hold an advisory file lock and no-op when
#     there is nothing to do, so multiple triggers firing on the same state
#     (e.g., post-commit + post-merge on a non-ff merge) are safe.

# -- Path resolution ----------------------------------------------------------
#
# FINALIZE_CHAIN_DIR is the absolute path to the directory holding this
# library and its sibling python scripts. Resolved by following ${BASH_SOURCE[0]}
# through any symlinks (user-project hooks symlink into the plugin's scripts/).

_finalize_chain_resolve_self() {
    local source="$1"
    [ -n "$source" ] || { echo "/" ; return ; }
    while [ -L "$source" ]; do
        local target
        target="$(readlink "$source")"
        case "$target" in
            /*) source="$target" ;;
            *) source="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)/$target" ;;
        esac
    done
    (cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)
}

FINALIZE_CHAIN_DIR="$(_finalize_chain_resolve_self "${BASH_SOURCE[0]}")"

# -- Repo-state predicates ----------------------------------------------------

# Print the repo root, or empty string if not inside a working tree.
_finalize_chain_repo_root() {
    git rev-parse --show-toplevel 2>/dev/null
}

# Return 0 if HEAD is on main (or master, for older projects).
_finalize_chain_on_main() {
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [ "$branch" = "main" ] || [ "$branch" = "master" ]
}

# Return 0 if .ai-state/decisions/drafts/ contains at least one fragment ADR.
# Fragments are timestamp-prefixed (`<YYYYMMDD-HHMM>-...md`), so we match
# digit-prefixed filenames. This skips guidance files like `CLAUDE.md` that
# legitimately live in the same directory. Cheap (single find with -print -quit),
# safe to call from per-commit hooks.
_finalize_chain_drafts_present() {
    local repo_root="$1"
    local drafts_dir="${repo_root}/.ai-state/decisions/drafts"
    [ -d "$drafts_dir" ] || return 1
    [ -n "$(find "$drafts_dir" -maxdepth 1 -name '[0-9]*-*.md' -print -quit 2>/dev/null)" ]
}

# Return 0 if the most recent commit touched any path under .ai-state/.
# Used by post-merge to decide whether reconcile_ai_state.py is worth running.
_finalize_chain_state_was_touched() {
    local repo_root="$1"
    local merged_files
    merged_files="$(git -C "$repo_root" diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true)"
    echo "$merged_files" | grep -q "^\.ai-state/"
}

# -- Script invocation --------------------------------------------------------

# Run a python script with non-blocking failure semantics.
# Args: <label> <absolute-script-path> [extra-args...]
_finalize_chain_run_script() {
    local label="$1"; shift
    local script="$1"; shift
    [ -f "$script" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    python3 "$script" "$@" 2>&1 || \
        echo "${label}: warned (non-blocking) — inspect output above"
}

# Run the on-main finalize steps. Caller has already gated on `on_main`; each
# finalizer is then gated on its OWN input rather than a shared condition:
#   - ADR-draft promotion runs only when draft fragments are present.
#   - Tech-debt ledger reconciliation runs unconditionally. Its work (migrating
#     terminal rows to RESOLVED, re-opening on cross-file dedup_key matches) is
#     independent of ADR drafts, and the script is a byte-equivalent no-op that
#     skips the write entirely when there is nothing to migrate — so running it
#     on every on-main commit costs one cheap read and never churns the tree.
#     Bundling it behind drafts_present (the prior behavior) stranded tech-debt
#     resolutions committed without a concurrent ADR draft.
_finalize_chain_run_on_main() {
    local repo_root="$1"
    if _finalize_chain_drafts_present "$repo_root"; then
        _finalize_chain_run_script "finalize_adrs" \
            "${FINALIZE_CHAIN_DIR}/finalize_adrs.py" --all
    fi
    _finalize_chain_run_script "finalize_tech_debt_ledger" \
        "${FINALIZE_CHAIN_DIR}/finalize_tech_debt_ledger.py" --all
}

# -- Public entry points ------------------------------------------------------

# State-driven finalize on main. Shared body for post-commit and post-checkout
# entry points. Inlined into both for clarity (the entry name is part of the
# hook's contract).
_finalize_chain_state_driven() {
    local repo_root
    repo_root="$(_finalize_chain_repo_root)"
    [ -n "$repo_root" ] || return 0
    _finalize_chain_on_main || return 0
    _finalize_chain_run_on_main "$repo_root"
}

# Post-merge entry point.
#
# Sequence (load-bearing):
#   1. reconcile_ai_state.py --post-merge      — only if .ai-state/ was touched
#   2. finalize on main (ADR if drafts; ledger always) — only on main
#   3. check_squash_safety.py                   — diagnostic, always runs
#
# Rationale: reconcile settles orthogonal file conflicts first; finalize
# rewrites cross-references on a settled tree; the squash-safety diagnostic
# runs last on a fully-reconciled tree.
finalize_chain_post_merge() {
    local repo_root
    repo_root="$(_finalize_chain_repo_root)"
    [ -n "$repo_root" ] || return 0

    if _finalize_chain_state_was_touched "$repo_root"; then
        _finalize_chain_run_script "post-merge: reconcile_ai_state" \
            "${FINALIZE_CHAIN_DIR}/reconcile_ai_state.py" --post-merge
    fi

    if _finalize_chain_on_main; then
        _finalize_chain_run_on_main "$repo_root"
    fi

    _finalize_chain_run_script "post-merge: check_squash_safety" \
        "${FINALIZE_CHAIN_DIR}/check_squash_safety.py"
}

# Post-commit entry point. Catches paths that create commits on main without
# a merge event: direct commits, non-ff merges (creates merge commit), rebases
# (each replayed commit), cherry-picks.
finalize_chain_post_commit() {
    _finalize_chain_state_driven
}

# Post-checkout entry point. Catches paths that arrive on main without a
# local commit: branch switch, fresh clone, reset to main.
#
# Git invokes post-checkout with three args: prev-head, new-head, branch-flag.
# branch-flag is "1" for branch checkout, "0" for file checkout. We act only
# on branch checkouts; file checkouts cannot land drafts on main.
finalize_chain_post_checkout() {
    local branch_flag="${3:-0}"
    [ "$branch_flag" = "1" ] || return 0
    _finalize_chain_state_driven
}
