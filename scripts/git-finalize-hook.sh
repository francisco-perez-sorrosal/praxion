#!/usr/bin/env bash
# scripts/git-finalize-hook.sh — multiplexed git hook entry point.
#
# A single script handles the four finalize hooks: post-merge, post-commit,
# post-checkout and post-rewrite. Each `.git/hooks/<name>` is a symlink to this
# file; dispatch is by the basename of the invocation path ($0). This collapses
# one near-identical hook script per trigger into one.
#
# Trigger coverage:
#
#   post-merge     — every git merge and pull (ff and non-ff, squash). Runs the
#                    full chain: reconcile + worktree-log merge-in +
#                    finalize-on-main + squash-safety.
#   post-commit    — every commit. Merges in the worktree logs a merge commit
#                    brought in when the merge was finished by `git commit` or
#                    `git merge --continue` (after a conflict or --no-commit);
#                    then runs finalize when on main.
#   post-checkout  — every branch switch (or fresh clone). Runs finalize when
#                    arriving on main; links a worktree's state mount under
#                    sidecar placement.
#   post-rewrite   — after `git commit --amend` and after a rebase. Merges in
#                    the worktree logs a finished rebase brought in
#                    (`git pull --rebase` included); an amend does nothing.
#
# The finalize is state-driven: together these cover every path that lands
# drafts on main. Merge-in is event-relative: each merge-in step judges
# "brought in" against its own operation's before-revision. A squash merge is
# the one merge no hook recognises. All logic lives in finalize_chain.sh.
#
# Installed by install_claude.sh (Praxion self-install), install_git_hooks.py
# (/onboard-project Phase 4) and upgrade_project_pins.sh (/upgrade-project).
# The names are declared once in install_git_hooks.py FINALIZE_HOOK_NAMES; the
# case arms below mirror them (scripts/test_finalize_hook_names.py).

set -eo pipefail

# Resolve the directory containing this script, following any symlinks.
# When invoked via .git/hooks/<name> -> scripts/git-finalize-hook.sh, the
# resolution finds the plugin's scripts/ directory where finalize_chain.sh
# and the python scripts live as siblings.
_resolve_script_dir() {
    local source="$1"
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

# shellcheck source=./finalize_chain.sh
. "$(_resolve_script_dir "${BASH_SOURCE[0]}")/finalize_chain.sh"

# Dispatch by basename of $0. When git invokes .git/hooks/post-merge (a
# symlink to this script), $0 is the symlink path and its basename names
# the hook. This avoids per-hook shim files at the cost of one indirection.
case "$(basename "$0")" in
    post-merge)    finalize_chain_post_merge "$@" ;;
    post-commit)   finalize_chain_post_commit "$@" ;;
    post-checkout) finalize_chain_post_checkout "$@" ;;
    post-rewrite)  finalize_chain_post_rewrite "$@" ;;
    *)
        # Direct invocation (basename = git-finalize-hook.sh) or unknown hook
        # name. Print usage and exit cleanly — git would never invoke us this
        # way, so this only fires from a misconfigured manual run.
        echo "git-finalize-hook.sh: invoked as '$(basename "$0")'; expected" \
             "post-merge / post-commit / post-checkout / post-rewrite. No-op." >&2
        ;;
esac
