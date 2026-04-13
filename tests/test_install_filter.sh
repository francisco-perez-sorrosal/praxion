#!/usr/bin/env bash
# Tests for install_claude.sh scripts filter (dec-042).
#
# Validates REQ-SL-01, REQ-SL-02, REQ-SL-04, REQ-SL-05:
#   - Only executable regular files in scripts/ get linked.
#   - Internal helpers (merge_driver_*, git-*-hook.sh) are excluded even
#     when executable.
#   - scripts/regenerate_adr_index.py has the executable bit set in source.
#   - clean_stale_symlinks() sweeps ~/.local/bin/ for links that no longer
#     pass the filter.
#
# Run from repo root:
#   bash tests/test_install_filter.sh
#
# Exits 0 on success, 1 on first failure (after printing diagnostics).

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SCRIPT="${REPO_ROOT}/install_claude.sh"

FAIL_COUNT=0
PASS_COUNT=0
CURRENT_TEST=""

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    printf "  [PASS] %s\n" "$1"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf "  [FAIL] %s: %s\n" "${CURRENT_TEST}" "$1" >&2
}

start_test() {
    CURRENT_TEST="$1"
    printf "\n=== %s ===\n" "$1"
}

# Source the install script's predicate function. The script has a main
# execution guard, so we extract and eval only the helper.
extract_predicate() {
    # Grab lines from "script_is_user_facing() {" up to the matching "}".
    awk '
        /^script_is_user_facing\(\) \{/ { inside = 1 }
        inside { print }
        inside && /^\}/ { exit }
    ' "$INSTALL_SCRIPT"
}

PREDICATE_BODY="$(extract_predicate)"
if [ -z "$PREDICATE_BODY" ]; then
    printf "SETUP FAIL: could not extract script_is_user_facing from %s\n" "$INSTALL_SCRIPT" >&2
    exit 1
fi

# Define the predicate in this shell.
eval "$PREDICATE_BODY"

# -----------------------------------------------------------------------------
# Test 1: regenerate_adr_index.py is executable in source (REQ-SL-02)
# -----------------------------------------------------------------------------
start_test "test_regenerate_adr_index_is_executable"
TARGET="${REPO_ROOT}/scripts/regenerate_adr_index.py"
if [ -x "$TARGET" ]; then
    pass "scripts/regenerate_adr_index.py has +x bit"
else
    fail "scripts/regenerate_adr_index.py is missing executable bit"
fi

# -----------------------------------------------------------------------------
# Test 2: predicate rejects non-executable, accepts executable (REQ-SL-01)
# -----------------------------------------------------------------------------
start_test "test_predicate_filters_by_executable_bit"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

EXEC_FILE="${TMPDIR}/tool_exec"
NOEXEC_FILE="${TMPDIR}/tool_noexec"
printf '#!/bin/sh\necho hi\n' > "$EXEC_FILE"
printf '# docs only\n' > "$NOEXEC_FILE"
chmod 755 "$EXEC_FILE"
chmod 644 "$NOEXEC_FILE"

if script_is_user_facing "$EXEC_FILE"; then
    pass "executable tool passes predicate"
else
    fail "executable tool rejected by predicate"
fi

if script_is_user_facing "$NOEXEC_FILE"; then
    fail "non-executable tool passed predicate (should be rejected)"
else
    pass "non-executable file rejected"
fi

# -----------------------------------------------------------------------------
# Test 3: predicate excludes internal helpers by name (REQ-SL-04)
# -----------------------------------------------------------------------------
start_test "test_predicate_excludes_internal_helpers"
MERGE_DRIVER="${TMPDIR}/merge_driver_foo.py"
GIT_HOOK="${TMPDIR}/git-post-merge-hook.sh"
printf '#!/usr/bin/env python3\n' > "$MERGE_DRIVER"
printf '#!/bin/sh\n' > "$GIT_HOOK"
chmod 755 "$MERGE_DRIVER" "$GIT_HOOK"

if script_is_user_facing "$MERGE_DRIVER"; then
    fail "merge_driver_foo.py passed predicate (should be excluded)"
else
    pass "merge_driver_* excluded"
fi

if script_is_user_facing "$GIT_HOOK"; then
    fail "git-post-merge-hook.sh passed predicate (should be excluded)"
else
    pass "git-*-hook.sh excluded"
fi

# Internal helpers that are NOT executable must also be rejected.
chmod 644 "$MERGE_DRIVER"
if script_is_user_facing "$MERGE_DRIVER"; then
    fail "non-exec merge_driver passed predicate"
else
    pass "non-exec merge_driver rejected"
fi

# -----------------------------------------------------------------------------
# Test 4: predicate rejects CLAUDE.md, test files (EC-3.6.2)
# -----------------------------------------------------------------------------
start_test "test_predicate_rejects_docs_and_tests"
DOC_FILE="${TMPDIR}/CLAUDE.md"
TEST_FILE="${TMPDIR}/test_reconcile_ai_state.py"
printf '# docs\n' > "$DOC_FILE"
printf '# tests\n' > "$TEST_FILE"
chmod 644 "$DOC_FILE" "$TEST_FILE"

if script_is_user_facing "$DOC_FILE"; then
    fail "CLAUDE.md passed predicate (should be rejected: non-exec)"
else
    pass "CLAUDE.md rejected"
fi

if script_is_user_facing "$TEST_FILE"; then
    fail "test_*.py passed predicate (should be rejected: non-exec)"
else
    pass "test_*.py rejected"
fi

# -----------------------------------------------------------------------------
# Test 5: full scripts/ directory yields the expected 6-file inventory
#         (EC-3.6.1, EC-3.6.2)
# -----------------------------------------------------------------------------
start_test "test_repo_scripts_yield_expected_inventory"
EXPECTED_LINKED="ccwt chronograph-ctl phoenix-ctl reconcile_ai_state.py regenerate_adr_index.py validate_adr_references.py"

ACTUAL_LINKED=""
for f in "${REPO_ROOT}/scripts"/*; do
    [ -f "$f" ] || continue
    if script_is_user_facing "$f"; then
        ACTUAL_LINKED="${ACTUAL_LINKED} $(basename "$f")"
    fi
done
ACTUAL_LINKED="$(printf '%s' "$ACTUAL_LINKED" | tr ' ' '\n' | sort | grep -v '^$' | tr '\n' ' ' | sed 's/ $//')"
EXPECTED_SORTED="$(printf '%s' "$EXPECTED_LINKED" | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')"

if [ "$ACTUAL_LINKED" = "$EXPECTED_SORTED" ]; then
    pass "scripts/ predicate yields exactly the 6 expected user-facing tools"
else
    fail "inventory mismatch: expected '${EXPECTED_SORTED}' got '${ACTUAL_LINKED}'"
fi

# -----------------------------------------------------------------------------
# Test 6: stale-symlink sweep removes orphaned links (REQ-SL-05)
# -----------------------------------------------------------------------------
start_test "test_stale_symlink_sweep_removes_orphans"

# Build a fake "scripts" tree and fake bin directory.
FAKE_SCRIPTS="${TMPDIR}/fake_scripts"
FAKE_BIN="${TMPDIR}/fake_bin"
mkdir -p "$FAKE_SCRIPTS" "$FAKE_BIN"

# User-facing tool that must survive the sweep.
GOOD_TOOL="${FAKE_SCRIPTS}/good_tool"
printf '#!/bin/sh\n' > "$GOOD_TOOL"
chmod 755 "$GOOD_TOOL"
ln -sf "$GOOD_TOOL" "${FAKE_BIN}/good_tool"

# Stale link pointing to a file that no longer exists.
STALE_MISSING="${FAKE_SCRIPTS}/ghost.sh"
ln -sf "$STALE_MISSING" "${FAKE_BIN}/ghost.sh"

# Stale link pointing to a merge driver (exec but internal helper).
BAD_DRIVER="${FAKE_SCRIPTS}/merge_driver_memory.py"
printf '#!/usr/bin/env python3\n' > "$BAD_DRIVER"
chmod 755 "$BAD_DRIVER"
ln -sf "$BAD_DRIVER" "${FAKE_BIN}/merge_driver_memory.py"

# Stale link pointing to a non-executable doc.
BAD_DOC="${FAKE_SCRIPTS}/CLAUDE.md"
printf '# doc\n' > "$BAD_DOC"
ln -sf "$BAD_DOC" "${FAKE_BIN}/CLAUDE.md"

# Link to a file OUTSIDE our scripts_src — must be left alone.
EXTERNAL_TARGET="${TMPDIR}/external_tool"
printf '#!/bin/sh\n' > "$EXTERNAL_TARGET"
chmod 755 "$EXTERNAL_TARGET"
ln -sf "$EXTERNAL_TARGET" "${FAKE_BIN}/external_tool"

# Execute the sweep logic — inline copy of the block from clean_stale_symlinks
# that sweeps bin_dir. This keeps the test hermetic (does not touch $HOME).
(
    scripts_src="$FAKE_SCRIPTS"
    bin_dir="$FAKE_BIN"
    if [ -d "$bin_dir" ] && [ -d "$scripts_src" ]; then
        for link in "$bin_dir"/*; do
            [ -L "$link" ] || continue
            target="$(readlink "$link")"
            case "$target" in
                "$scripts_src"/*) ;;
                *) continue ;;
            esac
            if ! script_is_user_facing "$target"; then
                rm "$link"
            fi
        done
    fi
)

# good_tool must still be linked.
if [ -L "${FAKE_BIN}/good_tool" ]; then
    pass "user-facing tool kept"
else
    fail "user-facing tool was removed by sweep"
fi

# Stale links must be gone.
for stale in ghost.sh merge_driver_memory.py CLAUDE.md; do
    if [ -e "${FAKE_BIN}/${stale}" ] || [ -L "${FAKE_BIN}/${stale}" ]; then
        fail "stale symlink '${stale}' was not removed"
    else
        pass "stale symlink '${stale}' removed"
    fi
done

# External link (not pointing into scripts_src) must be untouched.
if [ -L "${FAKE_BIN}/external_tool" ]; then
    pass "external symlink untouched (not in scripts_src)"
else
    fail "external symlink was removed by sweep"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
printf "\n---\n"
printf "Passed: %d\n" "$PASS_COUNT"
printf "Failed: %d\n" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
