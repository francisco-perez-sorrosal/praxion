#!/usr/bin/env bash
# scripts/onboard_placement.sh — sidecar-placement surface for onboard-project.
#
# Sourced by scripts/onboard-project only; not chmod +x, not a standalone
# entry point. Every function here reads globals onboard-project's
# parse_args populates (PLACEMENT, PLACEMENT_SET, SHADOW_PATHS[],
# SHARE_PATHS[], YES_FLAG, QUIET, JSON_MODE) and the EXIT_* constants it
# declares.
#
# Public entry point: resolve_sidecar_placement TARGET MODE — called once
# from main(), before any detection side effect. The placement x mode
# legality gate, the shadow/share composition rules (INTERFACE_DESIGN.md sec. 5.1),
# the confirmation block (sec. 5.3 -- reworded here for the state-mount
# architecture ARCH_WT_RULING.md introduced after that mockup was drafted:
# the sidecar is not purely external, it is projected into the checkout at
# `.praxion-state`), and delegation to `praxion-sidecar init` all live here.
#
# Validation is deliberately NOT duplicated: which paths are shadowable
# (D8's allowlist), the same-path-to-both-flags check, and the `.claude`
# shadow safety refusal are all enforced once, inside
# `_sidecar_init.validate_placement_flags` -- this file calls
# `praxion-sidecar init` for real and lets its exit code and message pass
# straight through. Only the checks `praxion-sidecar init` never sees (no
# --placement sidecar given at all; the in-repo/sidecar mode legality;
# re-onboarding a project that already picked sidecar) live here.

readonly _PLACEMENT_UNAVAILABLE_CI="CI workflows are GitHub-visible by construction"

# ---- Composition rules (pure CLI-flag checks; INTERFACE_DESIGN.md sec 5.1) --

_placement_validate_composition() {
    if [ "$PLACEMENT" != "sidecar" ]; then
        if [ "${#SHADOW_PATHS[@]}" -gt 0 ]; then
            printf 'Usage error: --shadow has no meaning under in-repo placement (everything is in the repo). Add --placement sidecar.\n' >&2
            exit "$EXIT_USAGE"
        fi
        if [ "${#SHARE_PATHS[@]}" -gt 0 ]; then
            printf 'Usage error: --share has no meaning under in-repo placement (everything is in the repo). Add --placement sidecar.\n' >&2
            exit "$EXIT_USAGE"
        fi
    fi
    case "$PLACEMENT" in
        in-repo|sidecar) : ;;
        *)
            printf 'Usage error: --placement %s is not recognized. Use in-repo or sidecar.\n' "$PLACEMENT" >&2
            exit "$EXIT_USAGE" ;;
    esac
    local shadowed shared
    for shadowed in "${SHADOW_PATHS[@]}"; do
        for shared in "${SHARE_PATHS[@]}"; do
            if [ "$shadowed" = "$shared" ]; then
                printf 'Usage error: %s was passed to both --shadow and --share. Each path has exactly one intent.\n' "$shadowed" >&2
                exit "$EXIT_USAGE"
            fi
        done
    done
}

# `--placement sidecar` is legal only when the resolved mode is
# `existing` -- every other mode exits usage, naming the legal combination.
_placement_validate_mode() {
    local mode="$1"
    [ "$mode" = "existing" ] && return 0
    printf 'Usage error: --placement sidecar is legal only when the resolved mode is existing (got: %s). Onboard the project first with a plain run, then re-run with --placement sidecar.\n' "$mode" >&2
    exit "$EXIT_USAGE"
}

# ---- Re-onboard: read placement from the manifest, never re-ask ------------

# Cheapest possible check first: a project that never touched sidecar
# placement has no `.ai-state` symlink at all, so the subprocess below only
# runs when there is something to actually resolve.
_placement_existing_for() {
    local target="$1" line
    line="$(python3 "$(dirname "$0")/_state_repo.py" --print "$target" 2>/dev/null | head -n1)"
    printf '%s' "${line#placement=}"
}

# ---- Path-intent classification (mirrors _sidecar_init.build_manifest) -----

_placement_claude_md_tracked() {
    [ -n "$(git -C "$1" ls-files -- CLAUDE.md 2>/dev/null)" ]
}

_placement_all_paths() {
    printf '%s\n' .ai-state CLAUDE.md CLAUDE.local.md .claude/settings.local.json \
        docs/architecture.md "${SHADOW_PATHS[@]}" "${SHARE_PATHS[@]}" | sort -u
}

# Echoes shadow|share|untouched for PATH under TARGET, mirroring
# _sidecar_init.build_manifest's own composition order exactly: the manifest's
# defaults, then --share overrides, then --shadow overrides (last write
# wins) -- so this block never claims an intent `praxion-sidecar init`
# would not also produce.
_placement_intent_of() {
    local target="$1" path="$2" intent p
    case "$path" in
        .ai-state|CLAUDE.local.md|.claude/settings.local.json) intent=shadow ;;
        docs/architecture.md) intent=share ;;
        CLAUDE.md)
            if _placement_claude_md_tracked "$target"; then intent=untouched; else intent=shadow; fi ;;
        *) intent=shadow ;;
    esac
    for p in "${SHARE_PATHS[@]}"; do [ "$p" = "$path" ] && intent=share; done
    for p in "${SHADOW_PATHS[@]}"; do [ "$p" = "$path" ] && intent=shadow; done
    printf '%s' "$intent"
}

# ---- Confirmation block (INTERFACE_DESIGN.md sec 5.3) ----------------------

_placement_print_section() {
    local target="$1" want="$2" path intent line
    for path in $(_placement_all_paths "$target"); do
        intent="$(_placement_intent_of "$target" "$path")"
        [ "$intent" = "$want" ] || continue
        line="$path"
        if [ "$path" = "CLAUDE.md" ] && [ "$intent" = "shadow" ]; then
            line="$(printf '%-30s yours — this repo has none; --share CLAUDE.md to commit it instead' "$path")"
        fi
        printf '    %s\n' "$line"
    done
}

_placement_render_block() {
    local target="$1" root
    root="${PRAXION_SIDECAR_ROOT:-$HOME/.praxion/sidecars}"

    printf 'Praxion onboarding · plugin %s\n\n' "$(plugin_version)"
    printf '  Directory   %s\n' "$target"
    printf '  Placement   sidecar\n\n'
    printf '  Project intelligence will live in a state mount (%s/.praxion-state)\n' "$target"
    printf '  backed by %s.\n\n' "$root"
    printf '  Shadowed — symlinked in, excluded via .git/info/exclude, never committed here:\n'
    _placement_print_section "$target" shadow
    printf '\n  Shared — committed in this repository, visible to the team:\n'
    _placement_print_section "$target" share
    printf '\n  Untouched — Praxion writes nothing here:\n'
    _placement_print_section "$target" untouched
    printf '\n  Unavailable under sidecar placement:\n'
    printf '    ci                             %s\n' "$_PLACEMENT_UNAVAILABLE_CI"
    printf '\n  Change the split with --shadow <path> / --share <path>. Reverse it later\n'
    printf '  with `praxion-sidecar publish` (state joins the repo) or `absorb` (state\n'
    printf '  leaves it).\n\n'
}

# Under --quiet, the full block above is suppressed -- but an operator on a
# real TTY about to be asked to confirm still needs to know what "yes" means.
# One line naming the mount path stands in for the block's own "Project
# intelligence will live in..." line.
_placement_print_quiet_summary() {
    printf 'Placement sidecar — %s/.praxion-state (rerun without --quiet to see the full split).\n' "$1"
}

_placement_emit_json() {
    local target="$1" path intent shadow_json="" share_json="" untouched_json=""
    for path in $(_placement_all_paths "$target"); do
        intent="$(_placement_intent_of "$target" "$path")"
        case "$intent" in
            shadow)    shadow_json="${shadow_json}${shadow_json:+,}\"$path\"" ;;
            share)     share_json="${share_json}${share_json:+,}\"$path\"" ;;
            untouched) untouched_json="${untouched_json}${untouched_json:+,}\"$path\"" ;;
        esac
    done
    printf '{"placement":"sidecar","shadow":[%s],"share":[%s],"untouched":[%s],"unavailable":["ci"]}\n' \
        "$shadow_json" "$share_json" "$untouched_json"
}

# ---- Delegation --------------------------------------------------------

_placement_delegate_init() {
    local target="$1" sidecar_cli rc=0
    sidecar_cli="$(dirname "$0")/praxion-sidecar"
    local -a init_args=(init)
    local p
    for p in "${SHADOW_PATHS[@]}"; do init_args+=(--shadow "$p"); done
    for p in "${SHARE_PATHS[@]}"; do init_args+=(--share "$p"); done
    [ "$QUIET" -eq 1 ] && init_args+=(--quiet)
    (cd "$target" && "$sidecar_cli" "${init_args[@]}") || rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
}

# Shared by both the --check preview and the real confirm-and-delegate path
# below: the block (or --json plan), --quiet summary included.
_placement_print_preview() {
    local target="$1"

    if [ "$JSON_MODE" -eq 1 ]; then
        _placement_emit_json "$target"
    elif [ "$QUIET" -eq 0 ]; then
        _placement_render_block "$target"
    else
        _placement_print_quiet_summary "$target"
    fi
}

# Renders the block (or the --json object) BEFORE calling praxion-sidecar,
# so the operator sees what was about to happen even when delegation
# refuses -- and only actually blocks on a read when stdin is a real,
# interactive TTY and neither --yes nor --json (which implies --yes) was
# given, so a piped/closed stdin never hangs.
_placement_confirm_and_delegate() {
    local target="$1" answer=""

    _placement_print_preview "$target"

    # The prompt line itself is printed here, unconditionally within this
    # guard, rather than as part of _placement_render_block above -- so
    # `--quiet` suppresses the descriptive block but never the prompt an
    # interactive operator is about to be blocked on (INTERFACE_DESIGN.md
    # sec 5.3: "--quiet suppresses the block but not the prompt").
    if [ "$YES_FLAG" -eq 0 ] && [ "$JSON_MODE" -eq 0 ] && [ -t 0 ]; then
        printf 'Proceed? [y/N] '
        read -r answer || answer=""
        case "$answer" in
            y|Y) : ;;
            *)
                printf 'Aborted — nothing was written.\n' >&2
                exit "$EXIT_SIDECAR_REFUSED" ;;
        esac
    fi

    _placement_delegate_init "$target"
}

# ---- Entry point --------------------------------------------------------

resolve_sidecar_placement() {
    local target="$1" mode="$2" existing

    _placement_validate_composition

    if [ ! -L "$target/.ai-state" ] && [ "$PLACEMENT" != "sidecar" ]; then
        return 0
    fi

    if [ -L "$target/.ai-state" ]; then
        existing="$(_placement_existing_for "$target")"
        if [ "$existing" = "sidecar" ]; then
            if [ "$PLACEMENT_SET" -eq 1 ] && [ "$PLACEMENT" != "sidecar" ]; then
                printf 'Usage error: this project already has --placement sidecar established; --placement %s contradicts it.\n' "$PLACEMENT" >&2
                printf 'To change placement, run:  praxion-sidecar publish   (state joins the repo)\n' >&2
                printf '                       or:  praxion-sidecar absorb    (state leaves it)\n' >&2
                exit "$EXIT_SIDECAR_REFUSED"
            fi
            return 0
        fi
        # dangling/foreign: fall through as "not yet sidecar" -- a
        # --placement sidecar retry surfaces praxion-sidecar init's own
        # (already-correct) refusal for the occupied slot.
    fi

    [ "$PLACEMENT" = "sidecar" ] || return 0

    _placement_validate_mode "$mode"

    # `--check` (and `--check --json`) is a dry-run by contract (see
    # onboard-project's own `--check` help text): print what would happen,
    # never delegate to `praxion-sidecar init` -- no sidecar directory, no
    # `.git/info/exclude` edit, `git status` unchanged.
    if [ "$CHECK_ONLY" -eq 1 ]; then
        _placement_print_preview "$target"
        return 0
    fi

    _placement_confirm_and_delegate "$target"
}
