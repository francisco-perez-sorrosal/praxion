#!/usr/bin/env bash
# scripts/upgrade_project_pins.sh — re-point a managed project's version-pinned
# Praxion surfaces to the live plugin install after a plugin upgrade.
#
# Why this exists
# ---------------
# /onboard-project installs git hooks and a merge driver that reference the
# plugin's scripts/ by absolute path (the versioned plugin-cache install path,
# e.g. ~/.claude/plugins/cache/praxion/<version>/scripts/git-finalize-hook.sh).
# When the praxion plugin is upgraded, the cache moves to a new <version>/ path and
# the old one is garbage-collected, leaving the per-project pins dangling. The
# onboard predicates that re-point them are themselves shipped by the plugin, so
# a project onboarded by an *older* Praxion cannot self-heal until the *newer*
# logic runs once. This script IS that newer logic, factored out of the 10-phase
# onboard flow into a deterministic, gate-free, LLM-free reconciler.
#
# It reconciles every onboarding-installed surface that a plugin upgrade (or
# rename) can invalidate:
#   1. The three finalize-hook symlinks (post-merge, post-commit, post-checkout)
#   2. The merge.observations-jsonl.driver git config
#   3. Retired merge drivers + their .gitattributes lines (cross-version cleanup)
#   4. The .ai-state/.praxion-onboard.json manifest version stamp
#   5. (only with --hub-sha <SHA>) The .github/workflows/ ci-autofix.yml +
#      cross-model-review.yml + labels-reconcile.yml reusable-workflow callers,
#      whose version identity is a cross-repo hub git ref (the pinned SHA)
#      rather than a local plugin-cache path. The script never resolves the SHA
#      itself (that would depend on the hub's moving tip and break determinism)
#      — the SHA is resolved in the /upgrade-project command layer and passed
#      in. Without --hub-sha this surface is skipped entirely.
#   6. The .github/labels.yml `baseline:` block, refreshed from the shipped
#      template via refresh_labels_baseline.py (the project's `additional:`
#      block and surrounding comments are preserved). Needs no hub SHA.
#   7. The two AaC-instantiated surfaces (architecture.yml agent-load prompt +
#      pre-commit Block D), delegated to the tested sibling
#      reconcile_aac_surfaces.py: namespace-token re-point plus the structural
#      repair of the broken pre-fix Block D PLUGIN_ROOT resolution. Needs no
#      hub SHA.
# The Phase-4 pre-commit hook body (id-citation gate) resolves the plugin path
# at run time, so it is version-independent and never goes stale — this script
# leaves it be; only its appended Block D fragment (surface 7) can drift.
#
# Usage
# -----
#   scripts/upgrade_project_pins.sh [options]
#
#   --repo-root <path>    Project root (default: git rev-parse --show-toplevel)
#   --plugin-path <path>  Override the live plugin install path (for tests)
#   --hub-sha <SHA>       Re-point the ci-autofix.yml caller's pinned hub SHA to
#                         this 40-hex value and add the cross-model-review.yml
#                         caller if policy-gated on + absent. Resolved by the
#                         command layer; the script never touches the network.
#                         Omit to skip the caller surface (backward compatible).
#   --check               Report drift and exit 1 if any is found; mutate nothing
#   --dry-run             Print what would change; mutate nothing
#   --no-stage            Skip `git add` of touched tracked files
#   -h, --help            Show this help
#
# Exit codes: 0 = reconciled (or no drift); 1 = drift found under --check, or a
# fatal precondition failure (not a git repo, plugin not installed, etc.).
#
# Idempotent: a second run on an already-current project produces no changes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PLUGIN_KEY="praxion@bit-agora"
EXPECTED_DRIVERS=("observations-jsonl")
FINALIZE_HOOKS=("post-merge" "post-commit" "post-checkout")
LEGACY_HOOK_BASENAME="git-post-merge-hook.sh"
PRAXION_HUB="francisco-perez-sorrosal/praxion"

REPO_ROOT=""
PLUGIN_PATH_OVERRIDE=""
HUB_SHA=""     # empty = skip the caller surface (backward compatible)
MODE="apply"   # apply | check | dry-run
STAGE=1

err()  { printf 'upgrade-pins: %s\n' "$*" >&2; }
info() { printf '  %s\n' "$*"; }

usage() { sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; s/^#$//' | sed '$d'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --repo-root)   REPO_ROOT="$2"; shift 2 ;;
        --plugin-path) PLUGIN_PATH_OVERRIDE="$2"; shift 2 ;;
        --hub-sha)     HUB_SHA="$2"; shift 2 ;;
        --check)       MODE="check"; shift ;;
        --dry-run)     MODE="dry-run"; shift ;;
        --no-stage)    STAGE=0; shift ;;
        -h|--help)     usage; exit 0 ;;
        *) err "unknown option: $1"; exit 1 ;;
    esac
done

# --hub-sha is a boundary input: it must be a bare 40-hex commit SHA, never a
# tag/branch/placeholder (the script writes it verbatim into a `uses:` ref).
if [ -n "$HUB_SHA" ] && ! printf '%s' "$HUB_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
    err "--hub-sha must be a 40-hex commit SHA (got: '$HUB_SHA')"
    exit 1
fi

# ---- preconditions ---------------------------------------------------------

if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        err "not inside a git repository (pass --repo-root to override)"; exit 1; }
fi
[ -d "$REPO_ROOT/.git" ] || [ -f "$REPO_ROOT/.git" ] || {
    err "no .git at $REPO_ROOT"; exit 1; }

if ! [ -d "$REPO_ROOT/.ai-state" ] && ! [ -f "$REPO_ROOT/.ai-state/.praxion-onboard.json" ]; then
    err "$REPO_ROOT has no .ai-state/ — not a Praxion-onboarded project. Run /onboard-project first."
    exit 1
fi

MANIFEST="$REPO_ROOT/.ai-state/.praxion-onboard.json"
GITATTR="$REPO_ROOT/.gitattributes"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

# ---- resolve the live plugin install path ----------------------------------

resolve_plugin() {
    if [ -n "$PLUGIN_PATH_OVERRIDE" ]; then
        PLUGIN_INSTALL_PATH="$PLUGIN_PATH_OVERRIDE"
        PLUGIN_VERSION="$(basename "$PLUGIN_INSTALL_PATH")"
        return 0
    fi
    local reg="$HOME/.claude/plugins/installed_plugins.json"
    [ -f "$reg" ] || { err "plugin registry not found: $reg"; return 1; }
    command -v jq >/dev/null 2>&1 || { err "jq is required"; return 1; }

    # Prefer a project-scoped entry matching this repo, else first user-scoped,
    # else the first entry. Mirrors /onboard-project pre-flight resolution.
    PLUGIN_INSTALL_PATH="$(jq -r --arg root "$REPO_ROOT" '
        (.plugins["'"$PLUGIN_KEY"'"] // [])
        | (map(select(.scope=="project" and .projectPath==$root)) + map(select(.scope=="user")) + .)
        | (.[0].installPath // empty)' "$reg")"
    PLUGIN_VERSION="$(jq -r --arg root "$REPO_ROOT" '
        (.plugins["'"$PLUGIN_KEY"'"] // [])
        | (map(select(.scope=="project" and .projectPath==$root)) + map(select(.scope=="user")) + .)
        | (.[0].version // empty)' "$reg")"

    [ -n "$PLUGIN_INSTALL_PATH" ] || {
        err "$PLUGIN_KEY is not installed. Run 'claude plugin install $PLUGIN_KEY' or ./install.sh code from a Praxion checkout."
        return 1; }
    [ -n "$PLUGIN_VERSION" ] && [ "$PLUGIN_VERSION" != "null" ] || PLUGIN_VERSION="$(basename "$PLUGIN_INSTALL_PATH")"
    return 0
}

resolve_plugin || exit 1
LIVE_HOOK="$PLUGIN_INSTALL_PATH/scripts/git-finalize-hook.sh"
LIVE_DRIVER="python3 $PLUGIN_INSTALL_PATH/scripts/merge_driver_observations.py %O %A %B"

# ---- placement: under sidecar placement the merge driver that
# matters lives in the sidecar's own .git/config, not the project's --------

PLACEMENT="in-repo"
MOUNT_DIR=""
if [ -f "$SCRIPT_DIR/_state_repo.py" ]; then
    while IFS='=' read -r _upp_key _upp_value; do
        case "$_upp_key" in
            placement) PLACEMENT="$_upp_value" ;;
            mount_dir) MOUNT_DIR="$_upp_value" ;;
        esac
    done < <(python3 "$SCRIPT_DIR/_state_repo.py" --print "$REPO_ROOT" 2>/dev/null || true)
fi

CHANGES=0          # count of surfaces that needed (or, in check/dry-run, would need) change
declare -a STAGED_FILES=()

note_change() { CHANGES=$((CHANGES + 1)); }
mutating()    { [ "$MODE" = "apply" ]; }

# ---- caller-reconcile helpers (only reached when --hub-sha is passed) -------

# Locate a shipped plugin file by repo-relative path: prefer the resolved live
# plugin install (the same tree that provides the finalize hook), fall back to
# the script's own checkout. Never fetched over the network.
find_plugin_file() {
    local rel="$1"
    local c
    for c in "$PLUGIN_INSTALL_PATH/$rel" "$SCRIPT_DIR/../$rel"; do
        [ -f "$c" ] && { printf '%s\n' "$c"; return 0; }
    done
    return 1
}

find_cross_model_template() {
    find_plugin_file "claude/project-baseline/ci-autofix/cross-model-review.yml.tmpl"
}

# Render a caller template to stdout: strip the leading doc-comment header (the
# contiguous run of # lines plus the blank line[s] that follow, up to the first
# YAML line) and fill the two placeholders. GitHub Actions ${{ }} expressions are
# left intact — they are not template placeholders.
render_caller_template() {
    local tmpl="$1"
    awk 'seen {print; next}
         /^[[:space:]]*#/ {next}
         /^[[:space:]]*$/ {next}
         {seen=1; print}' "$tmpl" \
        | sed -e "s|{{PRAXION_HUB}}|$PRAXION_HUB|g" -e "s|{{HUB_SHA}}|$HUB_SHA|g"
}

# Re-point a Praxion-authored, SHA-pinned ci-autofix.yml caller's hub SHA in
# place. Provenance is the uses:-line SHAPE: only a
# francisco-perez-sorrosal/praxion reusable-ci-autofix.yml@<40-hex> ref is
# upgradable. The rewrite edits ONLY the 40-hex token — every other byte
# (comments, permissions, an operator's watched-workflow edits) is preserved. A
# foreign-hub / mutable-ref / self-host ./ / hand-renamed caller does not match
# the shape and is left untouched + reported. Idempotent by construction (no-op
# when the SHA already matches).
reconcile_ci_autofix_caller() {
    local caller="$REPO_ROOT/.github/workflows/ci-autofix.yml"
    [ -f "$caller" ] || { info "ci-autofix.yml: absent → nothing to re-point"; return 0; }

    # Count the shape-matching uses: lines BEFORE extracting. grep -Eq only
    # guarantees ≥1 match; a caller with two matching refs (an operator
    # matrix/canary job — the "operator-edited, never clobber" category) would
    # make the single-value extraction below return a multi-line token and crash
    # the rewrite (sed: unterminated substitute pattern), mid-apply. Branch on
    # the count: 0 → not a Praxion caller (leave alone); 1 → rewrite the token;
    # >1 → ambiguous shape → leave untouched + report (mirrors the foreign-caller
    # path). Never crash.
    local match_re='uses:[[:space:]]*francisco-perez-sorrosal/praxion/\.github/workflows/reusable-ci-autofix\.yml@[0-9a-f]{40}'
    local match_count
    match_count="$(grep -Ec "$match_re" "$caller")" || true
    if [ "$match_count" -eq 0 ]; then
        info "ci-autofix.yml: uses: not a Praxion-pinned reusable-ci-autofix ref → left untouched"
        return 0
    fi
    if [ "$match_count" -gt 1 ]; then
        info "ci-autofix.yml: $match_count Praxion-pinned reusable-ci-autofix refs → ambiguous shape, left untouched"
        return 0
    fi

    # Single-pass extract of the currently pinned token (no pipe → no pipefail
    # SIGPIPE surprise); the count above guarantees exactly one such line.
    local cur_sha
    cur_sha="$(sed -nE 's|.*reusable-ci-autofix\.yml@([0-9a-f]{40}).*|\1|p' "$caller")"
    if [ "$cur_sha" = "$HUB_SHA" ]; then
        info "ci-autofix.yml: already pinned to $HUB_SHA"
        return 0
    fi

    note_change
    info "ci-autofix.yml: re-point hub SHA $cur_sha → $HUB_SHA"
    if mutating; then
        # Token-scoped replace: only reusable-ci-autofix.yml@<old-sha> is
        # rewritten, so a coincidental bare SHA elsewhere is never touched; sed
        # preserves every other byte, including the trailing newline.
        sed "s|reusable-ci-autofix\.yml@$cur_sha|reusable-ci-autofix.yml@$HUB_SHA|g" \
            "$caller" > "$caller.tmp" && mv "$caller.tmp" "$caller"
        STAGED_FILES+=("$caller")
    fi
}

# Re-point a Praxion-authored, SHA-pinned labels-reconcile.yml caller's hub SHA
# in place. Mirrors reconcile_ci_autofix_caller exactly: provenance is the
# uses:-line SHAPE (only a francisco-perez-sorrosal/praxion
# reusable-labels-reconcile.yml@<40-hex> ref is upgradable), the same
# 0/1/>1-match branching (0 → not a Praxion caller, left untouched; 1 →
# rewrite the token; >1 → ambiguous shape, left untouched + reported), and the
# same token-scoped sed rewrite that edits ONLY the 40-hex token — every other
# byte (comments, permissions, an operator's manifest_path edit) is preserved.
# Idempotent by construction (no-op when the SHA already matches).
reconcile_labels_caller() {
    local caller="$REPO_ROOT/.github/workflows/labels-reconcile.yml"
    [ -f "$caller" ] || { info "labels-reconcile.yml: absent → nothing to re-point"; return 0; }

    local match_re='uses:[[:space:]]*francisco-perez-sorrosal/praxion/\.github/workflows/reusable-labels-reconcile\.yml@[0-9a-f]{40}'
    local match_count
    match_count="$(grep -Ec "$match_re" "$caller")" || true
    if [ "$match_count" -eq 0 ]; then
        info "labels-reconcile.yml: uses: not a Praxion-pinned reusable-labels-reconcile ref → left untouched"
        return 0
    fi
    if [ "$match_count" -gt 1 ]; then
        info "labels-reconcile.yml: $match_count Praxion-pinned reusable-labels-reconcile refs → ambiguous shape, left untouched"
        return 0
    fi

    local cur_sha
    cur_sha="$(sed -nE 's|.*reusable-labels-reconcile\.yml@([0-9a-f]{40}).*|\1|p' "$caller")"
    if [ "$cur_sha" = "$HUB_SHA" ]; then
        info "labels-reconcile.yml: already pinned to $HUB_SHA"
        return 0
    fi

    note_change
    info "labels-reconcile.yml: re-point hub SHA $cur_sha → $HUB_SHA"
    if mutating; then
        sed "s|reusable-labels-reconcile\.yml@$cur_sha|reusable-labels-reconcile.yml@$HUB_SHA|g" \
            "$caller" > "$caller.tmp" && mv "$caller.tmp" "$caller"
        STAGED_FILES+=("$caller")
    fi
}

# Install the cross-model-review.yml caller when the ci-autofix policy exists,
# its review.cross_model_gate is not `off`, and the caller is absent. Never
# overwrites an existing caller. Renders the shipped template, aborts loudly on a
# surviving {{placeholder}} (a GitHub ${{ }} is not one), then writes.
reconcile_cross_model_caller() {
    local policy="$REPO_ROOT/.github/autofix-policy.yml"
    local cross="$REPO_ROOT/.github/workflows/cross-model-review.yml"

    [ -f "$policy" ] || { info "cross-model-review.yml: no autofix-policy.yml → skip"; return 0; }
    if [ -f "$cross" ]; then
        info "cross-model-review.yml: already present → skip (never overwrite)"
        return 0
    fi

    # Single-pass extract of the first gate value (no grep|head|sed|tr pipe →
    # no pipefail SIGPIPE surprise, matching the cur_sha idiom above): capture
    # the first non-space/non-# token after the colon, drop any trailing
    # comment, and quit on the first matching line.
    local gate
    gate="$(sed -nE '/^[[:space:]]*cross_model_gate:/{s/^[[:space:]]*cross_model_gate:[[:space:]]*([^[:space:]#]*).*/\1/p;q;}' "$policy")"
    if [ -z "$gate" ] || [ "$gate" = "off" ]; then
        info "cross-model-review.yml: gate '${gate:-unset}' → not installed"
        return 0
    fi

    local tmpl
    tmpl="$(find_cross_model_template)" || {
        err "cross-model-review.yml.tmpl not found under plugin install or script tree"
        exit 1; }

    note_change
    info "cross-model-review.yml: gate '$gate', absent → install"
    if mutating; then
        mkdir -p "$(dirname "$cross")"
        render_caller_template "$tmpl" > "$cross.tmp"
        # Abort loudly if an unfilled {{PLACEHOLDER}} survived; ${{ }} is skipped
        # via the not-preceded-by-$ guard so GitHub expressions never trip it.
        if grep -Eq '(^|[^$])\{\{' "$cross.tmp"; then
            rm -f "$cross.tmp"
            err "cross-model-review.yml: unresolved {{placeholder}} survived render — aborting"
            exit 1
        fi
        mv "$cross.tmp" "$cross"
        STAGED_FILES+=("$cross")
    fi
}

echo "Plugin: $PLUGIN_KEY @ $PLUGIN_VERSION"
echo "Live install path: $PLUGIN_INSTALL_PATH"
echo "Mode: $MODE"
echo

# ---- 1. finalize-hook symlinks ---------------------------------------------
#
# Two orthogonal jobs share this section, kept as two blocks rather than one
# merged pass: the ORIGINAL loop below detects drift ACROSS PLUGIN VERSIONS
# (a stale/dangling/legacy-named symlink from an old cache path, with a
# self-host safety carve-out this script has always owned); the NEW block
# after it detects drift in the P0 hook-CHAINING composition (a
# husky/lefthook-style core.hooksPath the loop above has no notion of at
# all, or an orphaned wrapper directory) via scripts/install_git_hooks.py.
# Both run every invocation -- they answer different questions about the
# same four hook slots and neither subsumes the other.

echo "[1/4] Finalize hooks"
for h in "${FINALIZE_HOOKS[@]}"; do
    hp="$HOOKS_DIR/$h"
    target=""
    [ -L "$hp" ] && target="$(readlink "$hp")"

    action=""
    if [ "$target" = "$LIVE_HOOK" ]; then
        info "$h: ok"
        continue
    elif [ ! -e "$hp" ] && [ ! -L "$hp" ]; then
        action="install"            # absent
    elif [ -L "$hp" ] && [ ! -e "$hp" ]; then
        action="repoint"            # dangling symlink (stale cache GC'd)
    elif [ -n "$target" ] && [ "$(basename "$target")" = "$LEGACY_HOOK_BASENAME" ]; then
        action="repoint"            # legacy single-trigger hook name
    elif [ -n "$target" ] && case "$target" in */plugins/cache/*) true;; *) false;; esac; then
        action="repoint"            # version-pinned to a non-live plugin-cache path
    elif [ -L "$hp" ] && [ "$(basename "$target")" = "git-finalize-hook.sh" ]; then
        # Resolves to a real finalize hook outside the plugin cache — a dev /
        # self-host install (Praxion's own tree). Not stale; leave it. This
        # branch must come BEFORE the broad */praxion/* fallback: a self-host
        # checkout is typically a directory literally named praxion, so the
        # glob alone would misclassify every self-host symlink as stale.
        info "$h: skip (dev/self-host symlink → $target)"
        continue
    elif [ -n "$target" ] && case "$target" in */praxion/*) true;; *) false;; esac; then
        action="repoint"            # non-cache-shaped but praxion-pinned path
    else
        action="backup-install"     # a non-Praxion hook occupies the slot
    fi

    note_change
    case "$action" in
        install)        info "$h: absent → install" ;;
        repoint)        info "$h: stale ($target) → re-point" ;;
        backup-install) info "$h: non-Praxion hook present → back up + install" ;;
    esac
    if mutating; then
        mkdir -p "$HOOKS_DIR"
        if [ "$action" = "backup-install" ]; then
            mv "$hp" "$hp.pre-praxion"
            info "  backed up to $h.pre-praxion"
        fi
        ln -sf "$LIVE_HOOK" "$hp"
    fi
done

# ---- 1b. hook-chain composition (P0) ---------------------------------------

INSTALL_GIT_HOOKS="$(find_plugin_file 'scripts/install_git_hooks.py')" || {
    err "install_git_hooks.py not found under plugin install or script tree"
    exit 1
}
if mutating; then
    # install_git_hooks.py exits non-zero for a legitimate refusal (3) as
    # well as success (0) -- `|| true` keeps that from tripping `set -e`;
    # the JSON payload (parsed below) is the actual source of truth either
    # way. --heal restores a KNOWN wrapper only -- it never newly onboards
    # an Absent/ForeignOccupied slot, which the loop above already owns.
    HEAL_JSON="$(python3 "$INSTALL_GIT_HOOKS" --heal \
        --repo-root "$REPO_ROOT" --plugin-root "$PLUGIN_INSTALL_PATH" --json)" || true
    HEAL_ACTIONABLE="$(printf '%s' "$HEAL_JSON" | python3 -c '
import json, sys
p = json.load(sys.stdin)
print("True" if p.get("changed") or p.get("refused") else "False")
')"
    if [ "$HEAL_ACTIONABLE" = "True" ]; then
        note_change
        info "hook chain:"
        printf '%s' "$HEAL_JSON" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
for m in payload.get("messages") or []:
    print(f"  {m}")
if payload.get("refused"):
    print(f"  refused: {payload.get('reason')}")
'
    fi
else
    # --status is inherently read-only, so no separate --dry-run flag on the
    # installer is needed to keep this script's non-mutating modes so.
    #
    # pre-commit is deliberately excluded from this section's drift count:
    # this script has never owned the pre-commit slot (Phase 4's own inline
    # install / a direct `install_git_hooks.py --install` does), so a
    # standalone pre-commit hook the wrapper mechanism does not (yet) manage
    # is not this section's drift to report.
    STATUS_JSON="$(python3 "$INSTALL_GIT_HOOKS" --status \
        --repo-root "$REPO_ROOT" --plugin-root "$PLUGIN_INSTALL_PATH" --json)" || true
    CANNOT_FIRE="$(printf '%s' "$STATUS_JSON" | python3 -c '
import json, sys
names = [n for n in (json.load(sys.stdin).get("cannot_fire") or []) if n != "pre-commit"]
print(len(names))
')"
    if [ "$CANNOT_FIRE" != "0" ]; then
        note_change
        info "hook chain: drift (not fully composed)"
        printf '%s' "$STATUS_JSON" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
for name in payload.get("cannot_fire") or []:
    if name != "pre-commit":
        print(f"  cannot fire: {name}")
'
    fi
fi
echo

# ---- 2. merge driver registration ------------------------------------------

echo "[2/4] Merge driver (observations-jsonl)"

if [ "$PLACEMENT" = "sidecar" ] && [ -n "$MOUNT_DIR" ]; then
    # Under sidecar placement the driver that matters lives in the sidecar's
    # own .git/config (shared across every worktree of it, including this
    # mount) -- the project repository does not own .ai-state/, so mutating
    # the project's own git config here would reconcile the wrong repo
    # `praxion-sidecar link` is the sole reconciler for the sidecar
    # side (it re-points the driver as part of D2's "re-apply every
    # repo-level invariant" contract); this step never calls `git config`
    # directly against the mount.
    cur_driver="$(git -C "$MOUNT_DIR" config --get merge.observations-jsonl.driver 2>/dev/null || true)"
    if [ "$cur_driver" = "$LIVE_DRIVER" ]; then
        info "ok (sidecar)"
    else
        note_change
        info "sidecar driver stale ('$cur_driver') → reconcile via praxion-sidecar link"
        if mutating; then
            (cd "$REPO_ROOT" && python3 "$PLUGIN_INSTALL_PATH/scripts/praxion-sidecar" link --quiet)
        fi
    fi
    echo
else
    cur_driver="$(git -C "$REPO_ROOT" config --get merge.observations-jsonl.driver 2>/dev/null || true)"
    attr_present=0
    [ -f "$GITATTR" ] && grep -qF '.ai-state/observations.jsonl merge=observations-jsonl' "$GITATTR" && attr_present=1

    if [ "$cur_driver" = "$LIVE_DRIVER" ]; then
        info "ok"
    elif [ -z "$cur_driver" ]; then
        if [ "$attr_present" -eq 1 ]; then
            note_change; info "absent but .gitattributes maps it → register"
            mutating && git -C "$REPO_ROOT" config merge.observations-jsonl.driver "$LIVE_DRIVER"
        else
            info "not registered and no .gitattributes mapping → nothing to do"
        fi
    elif case "$cur_driver" in */plugins/cache/*|*/praxion/*) true;; *) false;; esac; then
        # */plugins/cache/* covers i-am-era registrations too: the old namespace's
        # cache path contains no /praxion/ token, and treating it as "non-Praxion"
        # left every pre-rename project's driver permanently stale.
        note_change; info "stale ($cur_driver) → re-register"
        mutating && git -C "$REPO_ROOT" config merge.observations-jsonl.driver "$LIVE_DRIVER"
    else
        info "set to a non-Praxion value ('$cur_driver') → refusing to overwrite (leave as-is)"
    fi
    echo
fi

# ---- 3. retired merge-driver cleanup (manifest-driven) ---------------------

echo "[3/4] Retired merge drivers"
if [ -f "$MANIFEST" ] && command -v jq >/dev/null 2>&1; then
    prior_drivers="$(jq -r '(.artifacts.merge_drivers // [])[]' "$MANIFEST" 2>/dev/null || true)"
    retired_any=0
    while IFS= read -r d; do
        [ -n "$d" ] || continue
        keep=0
        for e in "${EXPECTED_DRIVERS[@]}"; do [ "$d" = "$e" ] && keep=1; done
        [ "$keep" -eq 1 ] && continue
        # Only remove Praxion-managed drivers: value contains /praxion/ or merge_driver_.
        dval="$(git -C "$REPO_ROOT" config --get "merge.$d.driver" 2>/dev/null || true)"
        case "$dval" in
            */praxion/*|*merge_driver_*) ;;
            "") ;;  # already unset; the .gitattributes line may still need removal
            *) info "$d: driver value not Praxion-managed ('$dval') → skip"; continue ;;
        esac
        line_present=0
        [ -f "$GITATTR" ] && grep -q "merge=$d\$" "$GITATTR" && line_present=1
        # Idempotency guard: a no-op (driver already unset AND line already gone)
        # is not a change — it only lingers in the manifest's artifact list.
        if [ -z "$dval" ] && [ "$line_present" -eq 0 ]; then
            continue
        fi
        retired_any=1; note_change
        info "$d: retired → unset driver + drop .gitattributes line"
        if mutating; then
            git -C "$REPO_ROOT" config --unset "merge.$d.driver" 2>/dev/null || true
            if [ "$line_present" -eq 1 ]; then
                grep -v "merge=$d\$" "$GITATTR" > "$GITATTR.tmp" && mv "$GITATTR.tmp" "$GITATTR"
                STAGED_FILES+=("$GITATTR")
            fi
        fi
    done <<< "$prior_drivers"
    [ "$retired_any" -eq 0 ] && info "none"
else
    info "no manifest → nothing to clean"
fi
echo

# ---- 4. manifest version stamp ---------------------------------------------

echo "[4/4] Onboard manifest"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ -f "$MANIFEST" ] && command -v jq >/dev/null 2>&1; then
    recorded="$(jq -r '.onboarded_with_version // "unknown"' "$MANIFEST")"
    # Canonical CORE artifact inventory after reconciliation: the expected driver
    # set and its sole .gitattributes mapping. Applied as a SHALLOW MERGE
    # (.artifacts + $expected) rather than a wholesale overwrite: the canonical
    # core keys win (so a retired driver is still pruned from merge_drivers /
    # gitattributes), while a conditional caller-set key an onboard recorded
    # (e.g. ci_autofix) is preserved across the upgrade.
    expected_artifacts='{"hooks":["pre-commit","post-merge","post-commit","post-checkout"],"merge_drivers":["observations-jsonl"],"gitattributes":[".ai-state/observations.jsonl merge=observations-jsonl"]}'
    cur_artifacts="$(jq -cS '.artifacts // {}' "$MANIFEST")"
    merged_artifacts="$(jq -cS '(.artifacts // {}) + $a' --argjson a "$expected_artifacts" "$MANIFEST")"

    if [ "$recorded" = "$PLUGIN_VERSION" ] && [ "$cur_artifacts" = "$merged_artifacts" ]; then
        info "version already $PLUGIN_VERSION; artifacts current"
    else
        note_change
        [ "$recorded" = "$PLUGIN_VERSION" ] && info "artifacts inventory refreshed" \
            || info "version $recorded → $PLUGIN_VERSION"
        if mutating; then
            jq --arg v "$PLUGIN_VERSION" --arg t "$now" --argjson a "$expected_artifacts" \
               '.onboarded_with_version=$v | .onboarded_at=$t | .artifacts=((.artifacts // {}) + $a)' \
               "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
            STAGED_FILES+=("$MANIFEST")
        fi
    fi
else
    info "manifest absent — run /onboard-project to create it (skipping stamp)"
fi
echo

# ---- 5. CI-autofix + cross-model + labels-reconcile callers (only with --hub-sha) --
# The cross-repo hub-ref surface. Skipped entirely without --hub-sha so the four
# surfaces above behave exactly as before this op existed.

if [ -n "$HUB_SHA" ]; then
    echo "[caller] CI-autofix + cross-model review + labels-reconcile callers"
    reconcile_ci_autofix_caller
    reconcile_cross_model_caller
    reconcile_labels_caller
    echo
fi

# ---- 6. labels-taxonomy baseline (no hub SHA needed) ------------------------
# Refreshes the Praxion-owned `baseline:` block of .github/labels.yml from the
# shipped template, preserving the project's `additional:` block untouched.
# Mode-aware: the refresh runs against a temp copy first, so --check/--dry-run
# report the diff verdict without mutating the manifest.

echo "[labels] Labels-taxonomy baseline"
reconcile_labels_baseline() {
    local manifest="$REPO_ROOT/.github/labels.yml"
    [ -f "$manifest" ] || { info "labels.yml: absent → nothing to refresh"; return 0; }
    local tmpl refresher tmp
    tmpl="$(find_plugin_file 'claude/project-baseline/labels/labels.yml.tmpl')" || {
        info "labels.yml: shipped template not found → skipping"; return 0; }
    refresher="$(find_plugin_file 'scripts/refresh_labels_baseline.py')" || {
        info "labels.yml: refresh_labels_baseline.py not found → skipping"; return 0; }
    tmp="$(mktemp)"
    cp "$manifest" "$tmp"
    if ! python3 "$refresher" "$tmpl" "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp"
        info "labels.yml: refresh script failed → left untouched (manual review)"
        return 0
    fi
    if cmp -s "$tmp" "$manifest"; then
        rm -f "$tmp"
        info "labels.yml: baseline current"
        return 0
    fi
    note_change
    case "$MODE" in
        check)   info "labels.yml: baseline STALE vs the shipped template"; rm -f "$tmp" ;;
        dry-run) info "labels.yml: baseline would be refreshed from the shipped template"; rm -f "$tmp" ;;
        apply)
            mv "$tmp" "$manifest"
            info "labels.yml: baseline refreshed (project 'additional:' block preserved)"
            STAGED_FILES+=("$manifest")
            ;;
    esac
}
reconcile_labels_baseline
echo

# ---- 7. AaC instantiated surfaces (no hub SHA needed) -----------------------
# architecture.yml + pre-commit Block D: namespace-token re-point and the
# structural repair of the broken pre-fix Block D PLUGIN_ROOT resolution.
# Logic lives in the tested sibling reconcile_aac_surfaces.py; its final
# `aac-changes: N` line is folded into this script's change count.

echo "[aac] AaC instantiated surfaces"
AAC_RECONCILER="$(find_plugin_file 'scripts/reconcile_aac_surfaces.py')" || AAC_RECONCILER=""
if [ -z "$AAC_RECONCILER" ]; then
    info "reconcile_aac_surfaces.py not found → skipping"
else
    AAC_ARGS=(--plugin-root "$PLUGIN_INSTALL_PATH" --repo-root "$REPO_ROOT" --mode "$MODE")
    [ "$STAGE" -eq 0 ] && AAC_ARGS+=(--no-stage)
    AAC_OUT="$(python3 "$AAC_RECONCILER" "${AAC_ARGS[@]}" 2>&1)" || true
    printf '%s\n' "$AAC_OUT" | sed '/^aac-changes: /d; s/^/  /'
    AAC_N="$(printf '%s\n' "$AAC_OUT" | sed -n 's/^aac-changes: //p')"
    if [ -n "$AAC_N" ] && [ "$AAC_N" -gt 0 ] 2>/dev/null; then
        CHANGES=$((CHANGES + AAC_N))
    fi
fi
echo

# ---- staging + summary -----------------------------------------------------

if [ "$MODE" = "check" ]; then
    if [ "$CHANGES" -gt 0 ]; then
        err "drift detected ($CHANGES surface(s) need re-pointing) — run without --check to fix"
        exit 1
    fi
    echo "No drift: all pins current for $PLUGIN_VERSION."
    exit 0
fi

if [ "$MODE" = "dry-run" ]; then
    echo "Dry run: $CHANGES surface(s) would change. Nothing was modified."
    exit 0
fi

if [ "$STAGE" -eq 1 ] && [ "${#STAGED_FILES[@]}" -gt 0 ]; then
    # de-dup
    printf '%s\n' "${STAGED_FILES[@]}" | sort -u | while IFS= read -r f; do
        git -C "$REPO_ROOT" add "$f" 2>/dev/null && echo "staged: ${f#$REPO_ROOT/}"
    done
fi

if [ "$CHANGES" -eq 0 ]; then
    echo "Already current — no changes."
else
    echo "Reconciled $CHANGES surface(s) to $PLUGIN_VERSION. Review staged changes and commit."
fi
