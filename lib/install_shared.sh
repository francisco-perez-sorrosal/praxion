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
    if [ -f "$manifest_file" ]; then
        # `|| hook_deliver_paths=""` bypasses `set -e` when python exits
        # non-zero (e.g. PyYAML missing) — falling back to "link all rules"
        # is the documented safe default; without it the script terminates
        # silently because `var=$(cmd)` propagates the failure under set -e.
        hook_deliver_paths=$(python3 - "$manifest_file" <<'PYEOF' 2>/dev/null
import sys
try:
    import yaml
    with open(sys.argv[1]) as f:
        m = yaml.safe_load(f)
    for r in m.get("rules", []):
        if r.get("install") == "hook-deliver":
            print(r["path"])
except Exception as e:
    sys.stderr.write(f"[link_rules] manifest parse failed: {e}; linking all rules\n")
PYEOF
        ) || hook_deliver_paths=""
    fi

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
        if [ -n "$hook_deliver_paths" ]; then
            local rule_repo_path="rules/${rel_path}"
            if echo "$hook_deliver_paths" | grep -qxF "$rule_repo_path"; then
                continue
            fi
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
    keep_paths=$(python3 - "$manifest_file" <<'PYEOF' 2>/dev/null
import sys
try:
    import yaml
    with open(sys.argv[1]) as f:
        m = yaml.safe_load(f) or {}
    for r in m.get("rules", []):
        if r.get("install") == "symlink":
            p = r.get("path", "")
            if p.startswith("rules/"):
                print(p[len("rules/"):])
except Exception:
    sys.exit(1)
PYEOF
) || rc=$?
    # Fail-safe: a parse error must NOT trigger an empty whitelist (which
    # would delete every Praxion-managed symlink). Bail out instead.
    if [ "$rc" -ne 0 ]; then
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
        if [ -n "$keep_paths" ] && echo "$keep_paths" | grep -qxF "$rel_to_source"; then
            continue
        fi
        rm "$link"
        removed=$((removed + 1))
    done < <(find "$rules_target_dir" -type l 2>/dev/null)

    # Tidy up empty subdirs (e.g., vcs/ after both its rules went hook-deliver).
    find "$rules_target_dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true

    SWEEP_STALE_RULE_SYMLINKS_REMOVED="$removed"
}
