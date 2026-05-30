#!/usr/bin/env bash
# Tests for install_claude.sh scripts filter (dec-042).
#
# Validates the predicate contract:
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
# Test 1: regenerate_adr_index.py is executable in source
# -----------------------------------------------------------------------------
start_test "test_regenerate_adr_index_is_executable"
TARGET="${REPO_ROOT}/scripts/regenerate_adr_index.py"
if [ -x "$TARGET" ]; then
    pass "scripts/regenerate_adr_index.py has +x bit"
else
    fail "scripts/regenerate_adr_index.py is missing executable bit"
fi

# -----------------------------------------------------------------------------
# Test 2: predicate rejects non-executable, accepts executable
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
# Test 3: predicate excludes internal helpers by name
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
# Test 4: predicate rejects CLAUDE.md, test files
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
# Test 5: scripts/ predicate respects its inclusion/exclusion contract
# -----------------------------------------------------------------------------
# Rather than pinning an exact inventory (which grows stale every time a
# script is added — see prior FAIL where the list was 6 entries while
# scripts/ had 15), this test pins the *contract* of script_is_user_facing:
#   - It MUST include known user-facing tools (positive cases).
#   - It MUST NOT include internal helpers (negative cases: merge_driver_*,
#     git-*-hook.sh) regardless of their executable bits.
# That way, adding a new user-facing script doesn't break the test, but a
# regression that lets internal helpers slip into ~/.local/bin/ does.
start_test "test_repo_scripts_yield_expected_inventory"

ACTUAL_LINKED=""
for f in "${REPO_ROOT}/scripts"/*; do
    [ -f "$f" ] || continue
    if script_is_user_facing "$f"; then
        ACTUAL_LINKED="${ACTUAL_LINKED} $(basename "$f")"
    fi
done
ACTUAL_LINKED="$(printf '%s' "$ACTUAL_LINKED" | tr ' ' '\n' | sort | grep -v '^$' | tr '\n' ' ' | sed 's/ $//')"

# Positive contract: these MUST be present (canonical, stable user tools).
EXPECTED_PRESENT="praxion-parallel chronograph-ctl phoenix-ctl"
missing_present=""
for tool in $EXPECTED_PRESENT; do
    case " $ACTUAL_LINKED " in
        *" $tool "*) : ;;
        *) missing_present="${missing_present} $tool" ;;
    esac
done

# Negative contract: these MUST NOT be present even if executable
# (internal helpers — merge drivers, git hooks).
EXPECTED_ABSENT_PATTERNS="merge_driver_ git-finalize-hook.sh git-pre-commit-hook.sh git-post-merge-hook.sh"
present_negatives=""
for tool in $ACTUAL_LINKED; do
    for bad in $EXPECTED_ABSENT_PATTERNS; do
        case "$tool" in
            *${bad}*) present_negatives="${present_negatives} $tool" ;;
        esac
    done
done

if [ -z "$missing_present" ] && [ -z "$present_negatives" ]; then
    pass "scripts/ predicate respects positive+negative contract"
else
    msg="contract violation:"
    [ -n "$missing_present" ] && msg="${msg} missing user-facing tools:${missing_present};"
    [ -n "$present_negatives" ] && msg="${msg} internal helpers slipped through:${present_negatives};"
    fail "${msg} got '${ACTUAL_LINKED}'"
fi

# -----------------------------------------------------------------------------
# Test 6: stale-symlink sweep removes orphaned links
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
# Test 7: sweep_stale_rule_symlinks prunes stale rule symlinks idempotently
# -----------------------------------------------------------------------------
# Source the production function under test from lib/install_shared.sh —
# the file's guard only fails on direct execution, sourcing is permitted.
# shellcheck source=../lib/install_shared.sh
source "${REPO_ROOT}/lib/install_shared.sh"

start_test "test_sweep_stale_rule_symlinks_prunes_stale_and_preserves_live"

FAKE_RULES_SOURCE="${TMPDIR}/fake_rules_src"
FAKE_RULES_TARGET="${TMPDIR}/fake_rules_tgt"
mkdir -p "${FAKE_RULES_SOURCE}/swe/vcs" "${FAKE_RULES_TARGET}/swe/vcs"

# Real rule files in the source tree.
printf '# claude\n'           > "${FAKE_RULES_SOURCE}/CLAUDE.md"
printf '# coding-style\n'     > "${FAKE_RULES_SOURCE}/swe/coding-style.md"
printf '# memory-protocol\n'  > "${FAKE_RULES_SOURCE}/swe/memory-protocol.md"
printf '# git-conventions\n'  > "${FAKE_RULES_SOURCE}/swe/vcs/git-conventions.md"

# Manifest pinning current install types — memory-protocol and
# vcs/git-conventions are NOW hook-deliver (flipped from symlink).
cat > "${FAKE_RULES_SOURCE}/_manifest.yaml" <<'YAMLEOF'
version: 1
rules:
  - id: CLAUDE
    path: rules/CLAUDE.md
    install: symlink
    core: true
  - id: swe/coding-style
    path: rules/swe/coding-style.md
    install: symlink
    core: false
  - id: swe/memory-protocol
    path: rules/swe/memory-protocol.md
    install: hook-deliver
    core: false
  - id: swe/vcs/git-conventions
    path: rules/swe/vcs/git-conventions.md
    install: hook-deliver
    core: false
YAMLEOF

# Symlink set that mimics the leftover state from prior installs:
#   - core CLAUDE.md (still install:symlink — keep)
#   - swe/coding-style.md (still install:symlink — keep)
#   - swe/memory-protocol.md (now hook-deliver — STALE)
#   - swe/vcs/git-conventions.md (now hook-deliver — STALE)
#   - swe/obsolete.md (target missing, rule absent from manifest — STALE)
#   - swe/my_personal_rule.md (points OUTSIDE the source tree — keep)
ln -sf "${FAKE_RULES_SOURCE}/CLAUDE.md"              "${FAKE_RULES_TARGET}/CLAUDE.md"
ln -sf "${FAKE_RULES_SOURCE}/swe/coding-style.md"    "${FAKE_RULES_TARGET}/swe/coding-style.md"
ln -sf "${FAKE_RULES_SOURCE}/swe/memory-protocol.md" "${FAKE_RULES_TARGET}/swe/memory-protocol.md"
ln -sf "${FAKE_RULES_SOURCE}/swe/vcs/git-conventions.md" \
       "${FAKE_RULES_TARGET}/swe/vcs/git-conventions.md"
ln -sf "${FAKE_RULES_SOURCE}/swe/obsolete.md"        "${FAKE_RULES_TARGET}/swe/obsolete.md"

EXTERNAL_RULE="${TMPDIR}/external_rule.md"
printf '# external\n' > "$EXTERNAL_RULE"
ln -sf "$EXTERNAL_RULE" "${FAKE_RULES_TARGET}/swe/my_personal_rule.md"

# Run the sweep.
sweep_stale_rule_symlinks "$FAKE_RULES_SOURCE" "$FAKE_RULES_TARGET"

# Live symlinks — must be preserved.
if [ -L "${FAKE_RULES_TARGET}/CLAUDE.md" ]; then
    pass "core install:symlink rule kept"
else
    fail "core install:symlink rule was removed"
fi

if [ -L "${FAKE_RULES_TARGET}/swe/coding-style.md" ]; then
    pass "non-core install:symlink rule kept"
else
    fail "non-core install:symlink rule was removed"
fi

# Stale symlinks — must be gone.
for stale_path in \
    "swe/memory-protocol.md" \
    "swe/vcs/git-conventions.md" \
    "swe/obsolete.md"; do
    if [ -L "${FAKE_RULES_TARGET}/${stale_path}" ] || \
       [ -e "${FAKE_RULES_TARGET}/${stale_path}" ]; then
        fail "stale symlink '${stale_path}' was not removed"
    else
        pass "stale symlink '${stale_path}' removed"
    fi
done

# External symlink — must be left alone.
if [ -L "${FAKE_RULES_TARGET}/swe/my_personal_rule.md" ]; then
    pass "external symlink left alone"
else
    fail "external symlink was removed by sweep"
fi

# Empty subdir vcs/ should be pruned after both its rules went hook-deliver.
if [ -d "${FAKE_RULES_TARGET}/swe/vcs" ]; then
    fail "empty subdir 'swe/vcs' was NOT cleaned up"
else
    pass "empty subdir 'swe/vcs' cleaned up"
fi

# -----------------------------------------------------------------------------
# Test 8: idempotency — second sweep is a no-op
# -----------------------------------------------------------------------------
start_test "test_sweep_stale_rule_symlinks_is_idempotent"

# Capture the post-sweep state.
BEFORE_SECOND_SWEEP=$(find "$FAKE_RULES_TARGET" \( -type l -o -type d \) | sort)

sweep_stale_rule_symlinks "$FAKE_RULES_SOURCE" "$FAKE_RULES_TARGET"

AFTER_SECOND_SWEEP=$(find "$FAKE_RULES_TARGET" \( -type l -o -type d \) | sort)

if [ "$BEFORE_SECOND_SWEEP" = "$AFTER_SECOND_SWEEP" ]; then
    pass "second sweep produces identical target tree"
else
    fail "second sweep mutated the tree (before='${BEFORE_SECOND_SWEEP}' after='${AFTER_SECOND_SWEEP}')"
fi

# -----------------------------------------------------------------------------
# Test 9: missing manifest — sweep is a safe no-op (fail-safe)
# -----------------------------------------------------------------------------
start_test "test_sweep_stale_rule_symlinks_bails_on_missing_manifest"

FAKE_NO_MANIFEST_SRC="${TMPDIR}/no_manifest_src"
FAKE_NO_MANIFEST_TGT="${TMPDIR}/no_manifest_tgt"
mkdir -p "$FAKE_NO_MANIFEST_SRC" "$FAKE_NO_MANIFEST_TGT"
printf '# rule\n' > "${FAKE_NO_MANIFEST_SRC}/rule.md"
ln -sf "${FAKE_NO_MANIFEST_SRC}/rule.md" "${FAKE_NO_MANIFEST_TGT}/rule.md"

# Intentionally NO _manifest.yaml.
sweep_stale_rule_symlinks "$FAKE_NO_MANIFEST_SRC" "$FAKE_NO_MANIFEST_TGT"

if [ -L "${FAKE_NO_MANIFEST_TGT}/rule.md" ]; then
    pass "missing manifest → sweep is a no-op (fail-safe)"
else
    fail "missing manifest → sweep deleted live symlinks (fail-open regression)"
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
