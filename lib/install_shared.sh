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
            if (path ~ /^rules\// && install == want) print substr(path, 7)
            path = ""; install = ""
        }
        /^[[:space:]]*rules:[[:space:]]*$/ { in_rules = 1; next }
        in_rules && /^[^[:space:]#-]/ { _flush(); in_rules = 0 }
        !in_rules { next }
        /^[[:space:]]*-[[:space:]]/ { _flush(); sub(/^[[:space:]]*-[[:space:]]*/, "") }
        /^[[:space:]]*path:[[:space:]]/ { path = _value($0); next }
        /^[[:space:]]*install:[[:space:]]/ { install = _value($0); next }
        END { _flush() }
    ' "$manifest_file"
}

# =============================================================================
# Rules linking
# =============================================================================

# Symlink rule files from the repo's rules/ directory into a target rules directory.
#
# Both Claude Code and Cursor use the same rules source with the same filtering
# (skip README.md, skip references/), but link into different destinations:
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

    # Build the set of rule paths to skip during symlinking.
    # Rules with install: hook-deliver are NOT symlinked — they are injected
    # at session start by hooks/inject_rules.py, which reads the same manifest
    # and emits them as additionalContext. Symlinking them in addition would
    # load them unconditionally and defeat the per-project blacklist mechanism.
    local hook_deliver_paths=""
    local manifest_file="${rules_source_dir}/_manifest.yaml"
    # `|| hook_deliver_paths=""` bypasses `set -e` when the manifest is absent —
    # falling back to "link all rules" is the documented safe default; without
    # it the script terminates silently because `var=$(cmd)` propagates the
    # failure under set -e.
    hook_deliver_paths=$(manifest_rule_paths "$manifest_file" hook-deliver) \
        || hook_deliver_paths=""

    LINK_RULES_COUNT=0
    while IFS= read -r rule_file; do
        local rel_path="${rule_file#"$rules_source_dir"/}"
        local rel_dir
        rel_dir="$(dirname "$rel_path")"

        # Skip non-rule files that live alongside rules
        [[ "$(basename "$rule_file")" == "README.md" ]] && continue
        # Reference files are skill/rule support material, not rules themselves
        [[ "$rel_path" == */references/* ]] && continue
        # Skip hook-deliver rules — delivered by inject_rules.py at session start
        if [ -n "$hook_deliver_paths" ] && \
           echo "$hook_deliver_paths" | grep -qxF "$rel_path"; then
            continue
        fi

        [ "$rel_dir" != "." ] && mkdir -p "${rules_target_dir}/${rel_dir}"
        ln -sf "$rule_file" "${rules_target_dir}/${rel_path}"
        LINK_RULES_COUNT=$((LINK_RULES_COUNT + 1))
    done < <(find "$rules_source_dir" -name '*.md' -type f | sort)
}

# Sweep <rules_target_dir> for symlinks that:
#   - point into <rules_source_dir> (Praxion-managed), AND
#   - are NOT in the current manifest as `install: symlink`.
#
# Removes them and prunes empty subdirectories left behind. External symlinks
# (target outside <rules_source_dir>) are left untouched — mirror of
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

    local manifest_file="${rules_source_dir}/_manifest.yaml"
    [ -f "$manifest_file" ] || return 0

    local keep_paths="" rc=0
    # `|| rc=$?` is the canonical set-e-safe pattern: a plain `var=$(cmd)`
    # would terminate the script before `rc=$?` could capture the exit
    # code, defeating the fail-safe bail-out a few lines below.
    keep_paths=$(manifest_rule_paths "$manifest_file" symlink) || rc=$?
    # Fail-safe: never derive an empty whitelist from a manifest we could not
    # read, because an empty whitelist deletes every Praxion-managed symlink.
    # An empty result means the manifest was unreadable, truncated, or its
    # schema drifted — all indistinguishable from "no rule is install:symlink",
    # a state that never occurs in a healthy manifest. Bail out either way.
    if [ "$rc" -ne 0 ] || [ -z "$keep_paths" ]; then
        return 0
    fi

    local link target rel_to_source removed=0
    while IFS= read -r link; do
        [ -L "$link" ] || continue
        target="$(readlink "$link")"
        # Only consider absolute symlinks pointing into the source rules dir;
        # leave external links alone.
        case "$target" in
            "$rules_source_dir"/*) rel_to_source="${target#"$rules_source_dir"/}" ;;
            *) continue ;;
        esac
        # Keep if the rule is still in the manifest as install: symlink.
        # keep_paths is guaranteed non-empty — the bail-out above returned
        # already if it were.
        if echo "$keep_paths" | grep -qxF "$rel_to_source"; then
            continue
        fi
        rm "$link"
        removed=$((removed + 1))
    done < <(find "$rules_target_dir" -type l 2>/dev/null)

    # Tidy up empty subdirs (e.g., vcs/ after both its rules went hook-deliver).
    find "$rules_target_dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true

    SWEEP_STALE_RULE_SYMLINKS_REMOVED="$removed"
}
