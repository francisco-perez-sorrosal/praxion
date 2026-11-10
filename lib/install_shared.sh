#!/usr/bin/env bash
# Shared helper functions for Praxion installers.
#
# Sourced by install_claude.sh and install_cursor.sh. Must not be executed directly.
# Contains linking logic shared across assistant-specific installers (Claude Code,
# Cursor, etc.) to avoid duplication.
#
# Each function takes explicit parameters — no reliance on caller's variables.

# Guard against direct execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: this script must be sourced, not executed directly." >&2
    exit 1
fi

# =============================================================================
# Rules manifest reading
# =============================================================================

# Emit the rules-dir-relative path of every manifest rule whose `install:`
# value equals $2, one per line.
#
# Implemented in awk rather than Python-plus-PyYAML on purpose. The installer
# runs on whatever `python3` a user happens to have first on PATH, and that
# interpreter frequently lacks PyYAML (a pyenv shim, a bare system python, a
# fresh machine). Both callers below previously degraded *silently* on the
# resulting ImportError, and their fallbacks compounded rather than cancelled:
# link_rules fell back to "link every rule" while sweep_stale_rule_symlinks
# fell back to "remove nothing", so a hook-deliver rule got symlinked into
# ~/.claude/rules/ and then never swept — loading unconditionally in every
# session and defeating the per-project blacklist. awk is POSIX, present
# everywhere a shell installer can run, and needs no packages.
#
# _manifest.yaml is machine-generated (scripts/regenerate_rules_manifest.py)
# with a fixed flat schema: a `rules:` sequence of mappings holding plain
# scalars. This parser covers exactly that shape, at any indentation level.
# tests/test_install_filter.sh drives it against the real manifest and
# cross-checks the result with an independent grep, so generator schema drift
# fails there rather than as a silently short whitelist at install time.
#
# A record whose `project_scope` is `managed` is never selected for `symlink`:
# managed rules reach only managed projects through the injection hook, so a
# user-scope link would load them everywhere. The generator refuses that
# combination; the reader holds the line for a hand-edited manifest, and the
# sweep then removes a link already there.
#
# Arguments:
#   $1 — manifest_file: absolute path to rules/_manifest.yaml
#   $2 — install_type:  the `install:` value to select (symlink | hook-deliver)
#
# Returns non-zero (emitting nothing) when the manifest is absent.
manifest_rule_paths() {
    local manifest_file="$1" install_type="$2"
    [ -f "$manifest_file" ] || return 1

    awk -v want="$install_type" '
        function _value(line) {
            sub(/^[^:]*:[[:space:]]*/, "", line)
            gsub(/^["\047]|["\047]$/, "", line)
            sub(/[[:space:]]+$/, "", line)
            return line
        }
        function _flush() {
            managed_symlink = (want == "symlink" && scope == "managed")
            if (path ~ /^rules\// && install == want && !managed_symlink) print substr(path, 7)
            path = ""; install = ""; scope = ""
        }
        /^[[:space:]]*rules:[[:space:]]*$/ { in_rules = 1; next }
        in_rules && /^[^[:space:]#-]/ { _flush(); in_rules = 0 }
        !in_rules { next }
        /^[[:space:]]*-[[:space:]]/ { _flush(); sub(/^[[:space:]]*-[[:space:]]*/, "") }
        /^[[:space:]]*path:[[:space:]]/ { path = _value($0); next }
        /^[[:space:]]*install:[[:space:]]/ { install = _value($0); next }
        /^[[:space:]]*project_scope:[[:space:]]/ { scope = _value($0); next }
        END { _flush() }
    ' "$manifest_file"
}

# =============================================================================
# Rules linking
# =============================================================================

# Symlink rule files from the repo's rules/ directory into a target rules directory.
#
# Both Claude Code and Cursor use the same rules source with the same filtering
# (the manifest's install:symlink set), but link into different destinations:
#   - Claude Code: ~/.claude/rules/
#   - Cursor:      ~/.cursor/rules/ or <project>/.cursor/rules/
#
# This function is the single source of truth for which rule files get linked
# and how the directory structure is preserved.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
#
# Output:
#   Prints nothing on success. Returns the count via the LINK_RULES_COUNT variable.
#   Creates target subdirectories as needed.
link_rules() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"

    if [ ! -d "$rules_source_dir" ]; then
        echo "Error: rules source directory not found: $rules_source_dir" >&2
        return 1
    fi

    mkdir -p "$rules_target_dir"

    # Idempotent reconciliation: remove stale symlinks left by prior installs
    # before re-linking. Handles the upgrade path when a rule's install type
    # flipped from `symlink` to `hook-deliver`, or when a rule was renamed or
    # dropped from the manifest. Without this, Claude Code keeps loading the
    # dangling links as user-scope memory files even when the YAML blacklist
    # filters them at hook time. Fail-safe: bails out if the manifest cannot
    # be parsed, so a transient parse error never deletes live links.
    sweep_stale_rule_symlinks "$rules_source_dir" "$rules_target_dir"

    # The manifest's install:symlink set is what gets linked — the same set
    # sweep_stale_rule_symlinks keeps, so a file the manifest leaves out (a
    # hook-deliver rule, or a directory guide such as rules/CLAUDE.md) is never
    # swept above and re-linked here. Hook-deliver rules are injected at session
    # start by hooks/inject_rules.py; symlinking them too would load them
    # unconditionally and defeat the per-project blacklist mechanism.
    local symlink_paths=""
    local manifest_file="${rules_source_dir}/_manifest.yaml"
    # `|| symlink_paths=""` bypasses `set -e` when the manifest is absent or
    # unreadable — falling back to "link every rule file" is the documented safe
    # default; without it the script terminates silently because `var=$(cmd)`
    # propagates the failure under set -e.
    symlink_paths=$(manifest_rule_paths "$manifest_file" symlink) \
        || symlink_paths=""

    LINK_RULES_COUNT=0
    while IFS= read -r rule_file; do
        local rel_path="${rule_file#"$rules_source_dir"/}"
        local rel_dir
        rel_dir="$(dirname "$rel_path")"

        if [ -n "$symlink_paths" ]; then
            echo "$symlink_paths" | grep -qxF "$rel_path" || continue
        else
            # Fallback without a readable manifest: skip the files that live
            # alongside rules without being rules — catalog READMEs, directory
            # guides (CLAUDE.md, loaded on demand as a nested CLAUDE.md) and
            # reference material.
            case "$(basename "$rule_file")" in README.md|CLAUDE.md) continue ;; esac
            [[ "$rel_path" == */references/* ]] && continue
        fi

        [ "$rel_dir" != "." ] && mkdir -p "${rules_target_dir}/${rel_dir}"
        ln -sf "$rule_file" "${rules_target_dir}/${rel_path}"
        LINK_RULES_COUNT=$((LINK_RULES_COUNT + 1))
    done < <(find "$rules_source_dir" -name '*.md' -type f | sort)
}

# The manifest's `install: symlink` set: the rules a rules directory should
# link, one rules-dir-relative path per line.
#
# Fail-safe: returns non-zero (emitting nothing) when the manifest is absent or
# yields an empty set. An empty result means the manifest was unreadable,
# truncated, or its schema drifted — all indistinguishable from "no rule is
# install:symlink", a state that never occurs in a healthy manifest — and an
# empty keep set would judge every Praxion-managed link stale.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
_rule_symlink_keep_set() {
    local keep_paths="" rc=0
    # `|| rc=$?` is the canonical set-e-safe pattern: a plain `var=$(cmd)`
    # would terminate the script before `rc=$?` could capture the exit code.
    keep_paths=$(manifest_rule_paths "${1}/_manifest.yaml" symlink) || rc=$?
    if [ "$rc" -ne 0 ] || [ -z "$keep_paths" ]; then
        return 1
    fi
    printf '%s\n' "$keep_paths"
}

# Print the rules-dir-relative path a Praxion-managed rule link targets, or
# return non-zero for a link Praxion does not manage. Praxion manages a link
# into <rules_source_dir>, and a link into any version of the praxion plugin's
# cached rules (`.../plugins/cache/<marketplace>/praxion/<version>/rules/`):
# an install made from one version's cache leaves links into that version's
# directory, which Claude Code keeps after an update, so judging only the
# current source would read them as external and never sweep them.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
#   $2 — target: the link's target, as readlink prints it
_managed_rule_rel_path() {
    local rules_source_dir="$1" target="$2" rest
    case "$target" in
        "$rules_source_dir"/*)
            printf '%s\n' "${target#"$rules_source_dir"/}" ;;
        */plugins/cache/*/praxion/*/rules/*)
            rest="${target#*/plugins/cache/*/praxion/}"
            printf '%s\n' "${rest#*/rules/}" ;;
        *)
            return 1 ;;
    esac
}

# Emit each stale rule symlink under <rules_target_dir>, one path per line: a
# Praxion-managed link (see _managed_rule_rel_path) at a rule the manifest does
# not list as `install: symlink`. External symlinks are never stale. This is
# the one predicate both the sweep (which removes these links) and the install
# check (which reports them) apply, so the two can never disagree about what a
# stale link is.
#
# Returns non-zero (emitting nothing) when the manifest cannot give a keep set.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
stale_rule_symlinks() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"
    local keep_paths
    keep_paths=$(_rule_symlink_keep_set "$rules_source_dir") || return 1
    [ -d "$rules_target_dir" ] || return 0

    local link rel_path
    while IFS= read -r link; do
        rel_path=$(_managed_rule_rel_path "$rules_source_dir" "$(readlink "$link")") \
            || continue
        echo "$keep_paths" | grep -qxF "$rel_path" || printf '%s\n' "$link"
    done < <(find "$rules_target_dir" -type l 2>/dev/null)
}

# Emit each manifest `install: symlink` rule that has no working link under
# <rules_target_dir>, one rules-dir-relative path per line: no symlink at its
# place, or a symlink that no longer resolves.
#
# Returns non-zero (emitting nothing) when the manifest cannot give a keep set.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
missing_rule_symlinks() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"
    local keep_paths
    keep_paths=$(_rule_symlink_keep_set "$rules_source_dir") || return 1

    local rel_path link
    while IFS= read -r rel_path; do
        link="${rules_target_dir}/${rel_path}"
        if [ ! -L "$link" ] || [ ! -e "$link" ]; then
            printf '%s\n' "$rel_path"
        fi
    done <<< "$keep_paths"
}

# Sweep <rules_target_dir> for the stale rule symlinks `stale_rule_symlinks`
# names, remove them, and prune empty subdirectories left behind. Mirror of
# sweep_stale_script_symlinks for ~/.local/bin/. Idempotent; safe to call
# every install.
#
# Fail-safe: if the manifest cannot be parsed, this function exits without
# removing anything, so an installer error never deletes live symlinks.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the repo's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
sweep_stale_rule_symlinks() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"
    [ -d "$rules_target_dir" ] || return 0
    [ -d "$rules_source_dir" ] || return 0

    local stale_links="" rc=0
    stale_links=$(stale_rule_symlinks "$rules_source_dir" "$rules_target_dir") || rc=$?
    [ "$rc" -eq 0 ] || return 0

    local link removed=0
    while IFS= read -r link; do
        [ -n "$link" ] || continue
        rm "$link"
        removed=$((removed + 1))
    done <<< "$stale_links"

    # Tidy up empty subdirs (e.g., vcs/ after both its rules went hook-deliver).
    find "$rules_target_dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true

    SWEEP_STALE_RULE_SYMLINKS_REMOVED="$removed"
}

# Bring <rules_target_dir> up to the manifest without taking over any link:
# sweep the stale links `stale_rule_symlinks` names, then link each manifest
# `install: symlink` rule that has no working link. A live link is never
# re-pointed, wherever it points, so a clone install's links into its own
# checkout stay its own, and a regular file at a rule's place is never
# replaced. The plugin's first-session completion runs this after an update.
# Fail-safe like the sweep: a manifest it cannot read changes nothing.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the plugin's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
refresh_rule_symlinks() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"
    [ -d "$rules_source_dir" ] || return 0
    sweep_stale_rule_symlinks "$rules_source_dir" "$rules_target_dir"

    local missing_rules="" rc=0 rel_path link
    missing_rules=$(missing_rule_symlinks "$rules_source_dir" "$rules_target_dir") || rc=$?
    [ "$rc" -eq 0 ] || return 0
    while IFS= read -r rel_path; do
        [ -n "$rel_path" ] || continue
        [ -f "${rules_source_dir}/${rel_path}" ] || continue
        link="${rules_target_dir}/${rel_path}"
        # A regular file at the rule's place is the operator's own.
        if [ -e "$link" ] && [ ! -L "$link" ]; then
            continue
        fi
        mkdir -p "$(dirname "$link")"
        ln -sfn "${rules_source_dir}/${rel_path}" "$link"
    done <<< "$missing_rules"
}

# Re-point each rule link that lies in another version's cached rules to the
# same place under <rules_source_dir>. Only a manifest `install: symlink` rule's
# own place is considered, and only a link there (live or dangling) that
# `_managed_rule_rel_path` reads as a cache link into a version other than
# <rules_source_dir>. A link already into <rules_source_dir>, a live link
# outside the cache (a clone install's), a regular file, and a place outside the
# keep set (the sweep owns it) are never touched. The plugin's first-session
# update path runs this before `refresh_rule_symlinks`; the installer and the
# install check never call it, so a live link elsewhere is still never taken over
# on any other path.
# Fail-safe like the sweep: a manifest it cannot read changes nothing.
#
# Arguments:
#   $1 — rules_source_dir: absolute path to the plugin's rules/ directory
#   $2 — rules_target_dir: absolute path to the destination rules directory
repoint_cached_rule_symlinks() {
    local rules_source_dir="$1"
    local rules_target_dir="$2"
    [ -d "$rules_source_dir" ] || return 0
    [ -d "$rules_target_dir" ] || return 0

    local keep_paths="" rc=0 rel_path link target
    keep_paths=$(_rule_symlink_keep_set "$rules_source_dir") || rc=$?
    [ "$rc" -eq 0 ] || return 0
    while IFS= read -r rel_path; do
        [ -n "$rel_path" ] || continue
        [ -f "${rules_source_dir}/${rel_path}" ] || continue
        link="${rules_target_dir}/${rel_path}"
        [ -L "$link" ] || continue
        target=$(readlink "$link")
        case "$target" in
            "$rules_source_dir"/*) continue ;;
        esac
        _managed_rule_rel_path "$rules_source_dir" "$target" >/dev/null || continue
        ln -sfn "${rules_source_dir}/${rel_path}" "$link"
    done <<< "$keep_paths"
}
