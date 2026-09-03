#!/usr/bin/env bash
# scripts/finalize_chain.sh — shared library for the .ai-state/ finalize chain.
#
# Sourced by git-finalize-hook.sh (the multiplexed dispatcher symlinked to
# .git/hooks/{post-merge,post-commit,post-checkout}). Single source of truth for:
#
#   - Path resolution (works for both cp-installed and symlink-installed hooks)
#   - Repo-state predicates (on_main, drafts_present, state_was_touched)
#   - Composition of the finalize chain (broken-Block-D hook repair, ADR
#     drafts -> dec-NNN, ledger dedup, reconcile, squash-safety diagnostic)
#
# Public entry points (called from hooks):
#
#   finalize_chain_post_merge       — reconcile + state-driven finalize + squash-safety
#   finalize_chain_post_commit      — state-driven finalize on main (ADR promotion sub-gated on drafts)
#   finalize_chain_post_checkout    — state-driven finalize on branch switch to main, plus an
#                                     unconditional (branch-independent) sidecar `link` under
#                                     sidecar placement -- the primary channel that materializes
#                                     a new project worktree's state mount
#   finalize_chain_run_on_main      — on-main composition (adr -> ledger -> manifest) for
#                                     non-hook callers (e.g. CI); resolves repo_root from the
#                                     argument or the current working tree. Honors
#                                     FINALIZE_CHAIN_STRICT (unset = non-blocking hook
#                                     semantics; set = fail-loud, for server-side callers).
#
# Sidecar placement (ARCH_WT_RULING.md). Every entry point resolves which git
# repository owns .ai-state/ exactly ONCE (see "Placement resolution" below)
# into a handful of _FC_* shell variables every later branch in that same
# call reads. Under sidecar placement: the project-side reconcile_ai_state.py
# / check_squash_safety.py calls stay in place unmodified -- both already
# self-detect SidecarOwned and report why they no-op; the on-main
# composition runs `praxion-sidecar merge-back --auto` before ADR-draft
# promotion (channel 1 of three idempotent convergence channels, ARCH_WT_RULING.md
# § 13.3) so a plain `git merge` or a GitHub squash-merge-then-pull promotes a
# worktree's drafts in the SAME finalize run; finalize_adrs.py is pointed at
# the state mount via --state-root; and the mount gets exactly one
# `praxion-sidecar commit` once composition finishes mutating it. Under
# in-repo placement every one of the above is a no-op and the chain's
# behavior is byte-identical to before sidecar placement existed.
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

# -- Hook environment scrubbing ------------------------------------------------
#
# git exports repository-scoping variables to the hooks it runs, and exports
# GIT_INDEX_FILE / GIT_DIR *relative* (`.git/index`, `.git`). Any git call this
# chain makes against a different repository -- the sidecar state mount, whose
# `.git` is a worktree pointer *file* -- then resolves `.git/index` under that
# mount and dies with `fatal: .git/index: index file open failed: Not a
# directory`. That failure is what broke the post-commit convergence channel:
# merge-back reported it as a merge conflict and finalize_adrs declined to
# promote, both non-blockingly, so the squash-merge shape silently did nothing.
#
# The runner every python sibling uses (`scripts/_git_runner.py`) scrubs these
# for itself. This wrapper is the defence in depth for the steps the chain
# spawns as executables (praxion-sidecar) and for any `git` it runs directly:
# it runs the command in a subshell with the variables unset, so the hook's own
# environment -- which the rest of the hook may still need -- is untouched.
_FINALIZE_CHAIN_GIT_SCOPE_VARS=(
    GIT_INDEX_FILE
    GIT_DIR
    GIT_WORK_TREE
    GIT_COMMON_DIR
    GIT_OBJECT_DIRECTORY
    GIT_ALTERNATE_OBJECT_DIRECTORIES
    GIT_PREFIX
    GIT_NAMESPACE
)

_finalize_chain_unscoped() {
    ( unset "${_FINALIZE_CHAIN_GIT_SCOPE_VARS[@]}"; "$@" )
}

# -- Script invocation --------------------------------------------------------

# Run a python script. Default: non-blocking failure semantics (warn, return 0)
# — hooks cannot abort an already-completed git operation. When
# FINALIZE_CHAIN_STRICT is set (non-empty), propagate the script's exit code
# instead — for server-side callers (e.g. CI) that must fail loud.
# Args: <label> <absolute-script-path> [extra-args...]
# Resolve the interpreter that runs chain scripts.
#
# A bare `python3` is whatever the ambient shell exposes, which is not
# necessarily an interpreter holding the project's declared dependencies. Under
# a pyenv shim it can be an unrelated build entirely, silently stranding any
# chain script that needs a third-party package: observed on Praxion itself,
# where `build_doc_manifest.py` requires PyYAML (declared in pyproject.toml and
# present in .venv) but the shim resolved to a 3.14 alpha without it -- so the
# committed manifest went stale while every commit printed a non-blocking
# warning that read as noise.
#
# Order: explicit override, the project's own virtualenv, then the ambient
# interpreter. The last keeps stdlib-only chain scripts (finalize_adrs,
# finalize_tech_debt_ledger) working in consumer projects that have no venv --
# so this strictly widens what runs and never narrows it.
_finalize_chain_python() {
    local repo_root
    if [ -n "${PRAXION_PYTHON:-}" ] && [ -x "${PRAXION_PYTHON}" ]; then
        printf '%s\n' "${PRAXION_PYTHON}"
        return 0
    fi
    repo_root="$(_finalize_chain_repo_root)"
    if [ -n "$repo_root" ] && [ -x "${repo_root}/.venv/bin/python" ]; then
        printf '%s\n' "${repo_root}/.venv/bin/python"
        return 0
    fi
    command -v python3 2>/dev/null
}

_finalize_chain_run_script() {
    local label="$1"; shift
    local script="$1"; shift
    local python
    [ -f "$script" ] || return 0
    python="$(_finalize_chain_python)"
    [ -n "$python" ] || return 0
    if [ -n "${FINALIZE_CHAIN_STRICT:-}" ]; then
        "$python" "$script" "$@"
        return $?
    fi
    "$python" "$script" "$@" 2>&1 || \
        echo "${label}: warned (non-blocking) — inspect output above"
}

# Run praxion-sidecar directly. Unlike the .py siblings _finalize_chain_run_script
# invokes through a resolved interpreter, praxion-sidecar is a self-contained
# executable carrying its own shebang (and the test fixtures swap it for a
# recording shim or a bash shim, neither of which `python3 <path>` could run)
# -- so it is invoked as itself. Same non-blocking-by-default /
# FINALIZE_CHAIN_STRICT contract as _finalize_chain_run_script.
_finalize_chain_run_sidecar() {
    local label="$1"; shift
    local sidecar="${FINALIZE_CHAIN_DIR}/praxion-sidecar"
    [ -x "$sidecar" ] || return 0
    if [ -n "${FINALIZE_CHAIN_STRICT:-}" ]; then
        _finalize_chain_unscoped "$sidecar" "$@"
        return $?
    fi
    _finalize_chain_unscoped "$sidecar" "$@" 2>&1 \
        || echo "${label}: warned (non-blocking) — inspect output above"
}

# -- Placement resolution ------------------------------------------------------
#
# Which git repository owns .ai-state/? Resolved via _state_repo.py's --print
# CLI, which is contracted to never raise and always exit 0 -- so this call
# needs no failure handling of its own. When the interpreter or the script is
# unavailable, _finalize_chain_load_placement falls back to `in-repo`, which
# reproduces every pre-sidecar chain's behavior exactly.
_finalize_chain_resolve_placement() {
    local repo_root="$1" python
    python="$(_finalize_chain_python)"
    [ -n "$python" ] || return 0
    [ -f "${FINALIZE_CHAIN_DIR}/_state_repo.py" ] || return 0
    "$python" "${FINALIZE_CHAIN_DIR}/_state_repo.py" --print "$repo_root" 2>/dev/null
}

_FC_PLACEMENT=""
_FC_STATE_GIT_ROOT=""
_FC_MOUNT_DIR=""
_FC_SIDECAR_COMMON_DIR=""
_FC_REASON=""

# Resolve placement ONCE per entry point into the _FC_* globals above; every
# later branch in that same entry-point call reads them rather than
# re-resolving. Never fails: an unparseable or empty result leaves placement
# at its safe `in-repo` default.
_finalize_chain_load_placement() {
    local repo_root="$1" key value
    _FC_PLACEMENT="in-repo"
    _FC_STATE_GIT_ROOT="$repo_root"
    _FC_MOUNT_DIR=""
    _FC_SIDECAR_COMMON_DIR=""
    _FC_REASON=""
    while IFS='=' read -r key value; do
        case "$key" in
            placement) _FC_PLACEMENT="$value" ;;
            state_git_root) _FC_STATE_GIT_ROOT="$value" ;;
            mount_dir) _FC_MOUNT_DIR="$value" ;;
            sidecar_common_dir) _FC_SIDECAR_COMMON_DIR="$value" ;;
            reason) _FC_REASON="$value" ;;
        esac
    done < <(_finalize_chain_resolve_placement "$repo_root")
}

# Cheap existence check for at least one sidecar-side wt/* state branch,
# read directly from the sidecar's own common dir rather than by shelling
# out to praxion-sidecar -- a `merge-back --auto` call against a sidecar
# with nothing to converge would still count as one praxion-sidecar
# invocation, and the common case (no worktree in flight) should never pay
# for a Python CLI startup just to hear "Nothing to converge."
_finalize_chain_state_branches_pending() {
    local sidecar_common_dir="$1"
    [ -n "$sidecar_common_dir" ] && [ -d "$sidecar_common_dir" ] || return 1
    local ref
    ref="$(_finalize_chain_unscoped git --git-dir="$sidecar_common_dir" for-each-ref --count=1 \
        --format='%(refname)' refs/heads/wt/ 2>/dev/null)"
    [ -n "$ref" ]
}

# Merge-back convergence (ARCH_WT_RULING.md § 13, channel 1). Runs BEFORE
# drafts_present/finalize_adrs so a plain `git merge`, or a GitHub squash
# merge followed by `git pull`, promotes a worktree's drafts in the SAME
# finalize run. Per-branch outcomes (converged/skipped/aborted) are printed
# by merge-back's own report -- forwarded verbatim via 2>&1, never
# reconstructed here. An aborted branch is a reported, expected outcome for
# THAT branch, not a finalizer crash, so this call never affects the chain's
# exit code, not even under FINALIZE_CHAIN_STRICT (contrast
# _finalize_chain_run_sidecar, whose STRICT mode does propagate failure) --
# and it is never --quiet, since --quiet would suppress exactly the
# converged/skipped/aborted lines this call exists to surface.
_finalize_chain_merge_back_auto() {
    local sidecar="${FINALIZE_CHAIN_DIR}/praxion-sidecar"
    [ -x "$sidecar" ] || return 0
    _finalize_chain_unscoped "$sidecar" merge-back --auto 2>&1 || true
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

    # Caller has already called _finalize_chain_load_placement -- reads
    # _FC_* only, never re-resolves. A dangling or foreign shadow can't be
    # written through safely, so every state-mutating step below is skipped
    # (fail closed for writers); the chain itself stays non-blocking.
    case "$_FC_PLACEMENT" in
        dangling | foreign)
            echo "praxion: .ai-state/ placement is ${_FC_PLACEMENT} (${_FC_REASON}) -- skipping state finalization"
            return 0
            ;;
        not-yet-linked)
            # Defensive: a main checkout is never not-yet-linked (the variant
            # names a linked worktree whose own mount has not been created),
            # so this arm should be unreachable on main. It exists so a future
            # caller reaching it fails closed with a reason instead of writing.
            echo "praxion: .ai-state/ is not materialized in this checkout yet -- skipping state finalization"
            return 0
            ;;
    esac

    # Channel 1 (ARCH_WT_RULING.md § 13.3): converge every eligible wt/*
    # state branch into this checkout's sidecar branch BEFORE draft
    # promotion, so a plain `git merge` or a squash-merge-then-pull promotes
    # a worktree's drafts in this same run. Skipped when the sidecar has no
    # wt/* branches at all -- nothing could converge either way.
    if [ "$_FC_PLACEMENT" = "sidecar" ] \
        && _finalize_chain_state_branches_pending "$_FC_SIDECAR_COMMON_DIR"; then
        _finalize_chain_merge_back_auto
    fi

    # Pass --repo-root explicitly: the python scripts may be executing from a
    # symlinked plugin cache, where their own file location resolves to the
    # plugin rather than this consumer repo. repo_root is the git worktree root
    # resolved above; handing it down is what makes finalize act on the
    # consumer's .ai-state/ instead of the plugin's (empty) one. Under sidecar
    # placement --state-root points the git plumbing at the mount instead of
    # the project checkout, which owns no .ai-state/ of its own.
    if _finalize_chain_drafts_present "$repo_root"; then
        local -a state_root_args=()
        if [ "$_FC_PLACEMENT" = "sidecar" ]; then
            state_root_args=(--state-root "$_FC_STATE_GIT_ROOT")
        fi
        # Unscoped: under sidecar placement finalize_adrs' git plumbing runs
        # against --state-root (the mount), not this repo_root.
        _finalize_chain_unscoped _finalize_chain_run_script "finalize_adrs" \
            "${FINALIZE_CHAIN_DIR}/finalize_adrs.py" --all --repo-root "$repo_root" \
            "${state_root_args[@]}" || return $?
    fi
    _finalize_chain_run_script "finalize_tech_debt_ledger" \
        "${FINALIZE_CHAIN_DIR}/finalize_tech_debt_ledger.py" --all --repo-root "$repo_root" || return $?
    # Refresh the committed doc manifest LAST: it must index the dec-NNN renames
    # finalize_adrs makes and the TECH_DEBT_RESOLVED migrations the ledger makes
    # (a pre-commit gate runs too early to see them). Content-aware write no-ops
    # when nothing durable changed. Gated on the manifest already existing so
    # projects without one are never surprised by a new committed file.
    if [ -f "${repo_root}/.ai-state/doc_manifest.yaml" ]; then
        _finalize_chain_run_script "build_doc_manifest" \
            "${FINALIZE_CHAIN_DIR}/build_doc_manifest.py" --root "$repo_root" || return $?
    fi

    # The only commit in the chain: once composition has finished mutating
    # the mount, commit it. commit's own residue_paths() makes this
    # a clean no-op when nothing changed, so it is safe to call unconditionally.
    if [ "$_FC_PLACEMENT" = "sidecar" ]; then
        _finalize_chain_run_sidecar "praxion-sidecar commit" commit --quiet
    fi
}

# -- Block D self-repair backstop ---------------------------------------------
#
# A Block D fragment installed from the pre-fix template resolves PLUGIN_ROOT
# by walking the top level of installed_plugins.json (whose real shape nests
# installs under .plugins[key][N].installPath), so the AaC golden-rule gate
# silently skipped on every commit while printing a green result.
# /upgrade-project repairs it — but only when an operator remembers to run it.
# These finalize hooks are the one channel that executes CURRENT plugin code
# inside every managed project on every merge/commit/checkout, so the repair
# rides here as a backstop: once the operator updates the plugin, the next git
# activity in each project heals its hook with no further action.
#
# Guarded by a cheap two-marker grep (Block D present AND the broken shape's
# unique data.items() literal — the fixed template deliberately avoids that
# string), so healthy projects pay one grep and the repair fires at most once
# ever: repairing removes the marker. Scoped to --surface block-d because a
# git hook must never mutate tracked files — the workflow-namespace re-point
# remains /upgrade-project's. Branch-independent (hooks are not branch-scoped),
# so callers run it BEFORE any on-main gate. Non-blocking like every chain step.
_finalize_chain_repair_broken_block_d() {
    local repo_root="$1"
    local hook="${repo_root}/.git/hooks/pre-commit"
    [ -f "$hook" ] || return 0
    grep -q 'check_aac_golden_rule' "$hook" 2>/dev/null || return 0
    grep -q 'data\.items()' "$hook" 2>/dev/null || return 0
    echo "praxion: .git/hooks/pre-commit carries the broken Block D PLUGIN_ROOT resolution (the AaC gate has been silently skipping) — repairing from the shipped template"
    _finalize_chain_run_script "block-d repair" \
        "${FINALIZE_CHAIN_DIR}/reconcile_aac_surfaces.py" \
        --plugin-root "${FINALIZE_CHAIN_DIR}/.." --repo-root "$repo_root" \
        --mode apply --no-stage --surface block-d
}

# -- Public entry points ------------------------------------------------------

# Public wrapper around the on-main composition, for callers that source this
# library directly instead of going through a git hook (e.g. a CI workflow).
# repo_root defaults to the current working tree's root when omitted. Honors
# FINALIZE_CHAIN_STRICT the same way _finalize_chain_run_script does — this
# function adds no error-handling policy of its own, it only resolves repo_root.
finalize_chain_run_on_main() {
    local repo_root="${1:-$(_finalize_chain_repo_root)}"
    [ -n "$repo_root" ] || return 0
    _finalize_chain_load_placement "$repo_root"
    _finalize_chain_run_on_main "$repo_root"
}

# State-driven finalize on main. Shared body for post-commit (and, when
# already on main, post-checkout's tail). Inlined into both for clarity (the
# entry name is part of the hook's contract).
_finalize_chain_state_driven() {
    local repo_root
    repo_root="$(_finalize_chain_repo_root)"
    [ -n "$repo_root" ] || return 0
    # Hook repair is branch-independent — run before the on-main gate.
    _finalize_chain_repair_broken_block_d "$repo_root"
    _finalize_chain_on_main || return 0
    # Placement is resolved only once we know the composition will actually
    # run — the common case (an ordinary commit on a feature branch) never
    # pays for it.
    _finalize_chain_load_placement "$repo_root"
    _finalize_chain_run_on_main "$repo_root"
}

# Post-merge entry point.
#
# Sequence (load-bearing):
#   0. broken-Block-D hook repair               — branch-independent backstop
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

    _finalize_chain_repair_broken_block_d "$repo_root"
    _finalize_chain_load_placement "$repo_root"

    if _finalize_chain_state_was_touched "$repo_root"; then
        _finalize_chain_run_script "post-merge: reconcile_ai_state" \
            "${FINALIZE_CHAIN_DIR}/reconcile_ai_state.py" --post-merge \
            --repo-root "$repo_root"
    fi

    if _finalize_chain_on_main; then
        _finalize_chain_run_on_main "$repo_root"
    fi

    _finalize_chain_run_script "post-merge: check_squash_safety" \
        "${FINALIZE_CHAIN_DIR}/check_squash_safety.py" --repo-root "$repo_root"
}

# Post-commit entry point. Catches paths that create commits on main without
# a merge event: direct commits, non-ff merges (creates merge commit), rebases
# (each replayed commit), cherry-picks.
finalize_chain_post_commit() {
    _finalize_chain_state_driven
}

# Post-checkout entry point. Catches paths that arrive on main without a
# local commit: branch switch, fresh clone, reset to main. Under sidecar
# placement it is also the PRIMARY channel that materializes a new project
# worktree's own state mount -- confirmed to fire on `git worktree add`,
# with the SessionStart heal as the idempotent backstop.
#
# Git invokes post-checkout with three args: prev-head, new-head, branch-flag.
# branch-flag is "1" for branch checkout, "0" for file checkout. We act only
# on branch checkouts; file checkouts cannot land drafts on main and cannot
# be a new worktree either.
finalize_chain_post_checkout() {
    local branch_flag="${3:-0}"
    [ "$branch_flag" = "1" ] || return 0
    local repo_root
    repo_root="$(_finalize_chain_repo_root)"
    [ -n "$repo_root" ] || return 0

    _finalize_chain_repair_broken_block_d "$repo_root"
    # Resolved before the on_main gate: the link call below must fire on
    # EVERY branch checkout (a new worktree checks out its own feature
    # branch, never main), not only when the checkout lands on main.
    _finalize_chain_load_placement "$repo_root"

    # `not-yet-linked` is the shape a brand-new worktree actually has: `git
    # worktree add` copies no `.ai-state`, so gating on `sidecar` alone made
    # this call unreachable in exactly the case it exists to serve.
    case "$_FC_PLACEMENT" in
        sidecar | not-yet-linked)
            _finalize_chain_run_sidecar "praxion-sidecar link" link --quiet
            ;;
    esac

    _finalize_chain_on_main || return 0
    _finalize_chain_run_on_main "$repo_root"
}
