#!/usr/bin/env bash
# Tests for scripts/finalize_chain.sh + scripts/git-finalize-hook.sh.
#
# Behavioral tests for the state-driven finalize chain:
#
#   1. Path resolution: the library's FINALIZE_CHAIN_DIR resolves to the real
#      scripts/ directory both when sourced directly and when invoked through
#      a symlink (the user-project install path).
#   2. Gate predicates: _finalize_chain_on_main, _finalize_chain_drafts_present,
#      and _finalize_chain_state_was_touched return correct exit codes for
#      a synthetic git repo.
#   3. Dispatcher: git-finalize-hook.sh dispatches to the correct entry point
#      based on basename($0). Direct invocation prints a usage notice.
#   4. Non-blocking: missing python scripts and bad commands cause warnings,
#      never non-zero exits — the hook contract.
#   5. Hook integration: a temp git repo with a synthetic draft, hooks
#      symlinked to git-finalize-hook.sh, and a commit on main triggers
#      post-commit. The mocked finalize_adrs.py records the invocation.
#
# Run from repo root:
#   bash tests/test_finalize_chain.sh
#
# Exits 0 on success, 1 on first failure (after printing diagnostics).

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB_PATH="${REPO_ROOT}/scripts/finalize_chain.sh"
DISPATCHER_PATH="${REPO_ROOT}/scripts/git-finalize-hook.sh"

# Counters live in a shared file so subshell-scoped tests still aggregate.
# Format: "<pass> <fail>" on a single line.
COUNTER_FILE="$(mktemp -t finalize_chain_test_counter.XXXXXX)"
trap 'rm -f "$COUNTER_FILE" 2>/dev/null' EXIT
echo "0 0" > "$COUNTER_FILE"
CURRENT_TEST=""

_increment_counter() {
    local index="$1"  # 1=pass, 2=fail
    local p f
    read -r p f < "$COUNTER_FILE"
    if [ "$index" = "1" ]; then
        p=$((p + 1))
    else
        f=$((f + 1))
    fi
    echo "$p $f" > "$COUNTER_FILE"
}

pass() {
    _increment_counter 1
    printf "  [PASS] %s\n" "$1"
}

fail() {
    _increment_counter 2
    printf "  [FAIL] %s: %s\n" "${CURRENT_TEST}" "$1" >&2
}

start_test() {
    CURRENT_TEST="$1"
    printf "\n=== %s ===\n" "$1"
}

# Create a clean temp git repo wired to a stub scripts/ directory holding
# mock python scripts that record their invocation. Returns the repo path
# in the global TMP_REPO. The stub finalize scripts write a single line to
# tmp/<script-name>.invocation per call so tests can assert on invocation.
make_temp_repo() {
    TMP_REPO="$(mktemp -d -t finalize_chain_test.XXXXXX)"
    git -C "$TMP_REPO" init --quiet --initial-branch=main
    git -C "$TMP_REPO" config user.email "test@example.com"
    git -C "$TMP_REPO" config user.name "Test User"
    git -C "$TMP_REPO" config commit.gpgsign false

    mkdir -p "$TMP_REPO/scripts"
    mkdir -p "$TMP_REPO/.ai-state/decisions/drafts"
    mkdir -p "$TMP_REPO/tmp"

    # Real library + dispatcher copied in.
    cp "$LIB_PATH" "$TMP_REPO/scripts/finalize_chain.sh"
    cp "$DISPATCHER_PATH" "$TMP_REPO/scripts/git-finalize-hook.sh"
    chmod +x "$TMP_REPO/scripts/git-finalize-hook.sh"

    # Mock python scripts that record invocation.
    for script in finalize_adrs.py finalize_tech_debt_ledger.py reconcile_ai_state.py check_squash_safety.py; do
        cat > "$TMP_REPO/scripts/$script" <<EOF
#!/usr/bin/env python3
import sys, pathlib
record = pathlib.Path(__file__).resolve().parent.parent / "tmp" / "${script}.invocation"
record.write_text(" ".join(sys.argv[1:]) + "\n")
sys.exit(0)
EOF
        chmod +x "$TMP_REPO/scripts/$script"
    done

    # Initial commit so HEAD exists for git-state predicates.
    : > "$TMP_REPO/seed.txt"
    git -C "$TMP_REPO" add seed.txt
    git -C "$TMP_REPO" commit --quiet -m "seed"
}

cleanup_temp_repo() {
    [ -n "${TMP_REPO:-}" ] && [ -d "$TMP_REPO" ] && rm -rf "$TMP_REPO"
    TMP_REPO=""
}

# -- Test 1: library sources cleanly and exposes its public API --------------

start_test "library sources cleanly with correct FINALIZE_CHAIN_DIR"
(
    # shellcheck source=../scripts/finalize_chain.sh
    . "$LIB_PATH"
    if [ "$FINALIZE_CHAIN_DIR" = "${REPO_ROOT}/scripts" ]; then
        pass "FINALIZE_CHAIN_DIR resolves to scripts/"
    else
        fail "FINALIZE_CHAIN_DIR=$FINALIZE_CHAIN_DIR (expected ${REPO_ROOT}/scripts)"
    fi

    for fn in finalize_chain_post_merge finalize_chain_post_commit finalize_chain_post_checkout finalize_chain_post_rewrite; do
        if declare -F "$fn" >/dev/null; then
            pass "exposes $fn"
        else
            fail "missing entry point: $fn"
        fi
    done
)

# -- Test 2: gate predicates report correct state ----------------------------

start_test "gate predicates"
make_temp_repo
(
    cd "$TMP_REPO" || exit 1
    # shellcheck source=../scripts/finalize_chain.sh
    . "$TMP_REPO/scripts/finalize_chain.sh"

    if _finalize_chain_on_main; then
        pass "_finalize_chain_on_main returns 0 on main"
    else
        fail "_finalize_chain_on_main should return 0 on main"
    fi

    git checkout --quiet -b feature/x
    if ! _finalize_chain_on_main; then
        pass "_finalize_chain_on_main returns non-zero on feature branch"
    else
        fail "_finalize_chain_on_main should be non-zero on feature/x"
    fi
    git checkout --quiet main

    if ! _finalize_chain_drafts_present "$TMP_REPO"; then
        pass "_finalize_chain_drafts_present returns non-zero with empty drafts/"
    else
        fail "_finalize_chain_drafts_present should be non-zero with empty drafts/"
    fi

    : > "$TMP_REPO/.ai-state/decisions/drafts/20260503-1200-test-main-foo.md"
    if _finalize_chain_drafts_present "$TMP_REPO"; then
        pass "_finalize_chain_drafts_present returns 0 with a draft fragment"
    else
        fail "_finalize_chain_drafts_present should detect the fragment"
    fi

    # Guidance files like CLAUDE.md legitimately live in drafts/ but are not
    # fragment ADRs — the predicate must skip them.
    rm -f "$TMP_REPO/.ai-state/decisions/drafts/20260503-1200-test-main-foo.md"
    : > "$TMP_REPO/.ai-state/decisions/drafts/CLAUDE.md"
    : > "$TMP_REPO/.ai-state/decisions/drafts/README.md"
    if ! _finalize_chain_drafts_present "$TMP_REPO"; then
        pass "_finalize_chain_drafts_present ignores non-fragment .md files"
    else
        fail "_finalize_chain_drafts_present should ignore CLAUDE.md / README.md"
    fi
)
cleanup_temp_repo

# -- Test 3: post-commit dispatch invokes finalize when on main with drafts --

start_test "post-commit hook fires finalize on main with drafts"
make_temp_repo
(
    cd "$TMP_REPO" || exit 1

    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/.git/hooks/post-commit"
    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/.git/hooks/post-merge"
    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/.git/hooks/post-checkout"

    # Drop a draft fragment, stage and commit. post-commit fires.
    : > "$TMP_REPO/.ai-state/decisions/drafts/20260503-1200-test-main-add-feature.md"
    git -C "$TMP_REPO" add ".ai-state/decisions/drafts/20260503-1200-test-main-add-feature.md"
    git -C "$TMP_REPO" commit --quiet -m "add draft"

    if [ -f "$TMP_REPO/tmp/finalize_adrs.py.invocation" ]; then
        pass "finalize_adrs.py invoked by post-commit"
        if grep -q -- "--all" "$TMP_REPO/tmp/finalize_adrs.py.invocation"; then
            pass "finalize_adrs.py invoked with --all"
        else
            fail "finalize_adrs.py invoked without --all (got: $(cat "$TMP_REPO/tmp/finalize_adrs.py.invocation"))"
        fi
    else
        fail "finalize_adrs.py was not invoked by post-commit"
    fi

    if [ -f "$TMP_REPO/tmp/finalize_tech_debt_ledger.py.invocation" ]; then
        pass "finalize_tech_debt_ledger.py invoked by post-commit"
    else
        fail "finalize_tech_debt_ledger.py was not invoked"
    fi

    # reconcile and squash-safety belong to post-merge, not post-commit.
    if [ ! -f "$TMP_REPO/tmp/reconcile_ai_state.py.invocation" ]; then
        pass "reconcile_ai_state.py NOT invoked by post-commit"
    else
        fail "reconcile_ai_state.py was wrongly invoked by post-commit"
    fi
    if [ ! -f "$TMP_REPO/tmp/check_squash_safety.py.invocation" ]; then
        pass "check_squash_safety.py NOT invoked by post-commit"
    else
        fail "check_squash_safety.py was wrongly invoked by post-commit"
    fi
)
cleanup_temp_repo

# -- Test 4: post-commit on feature branch is a no-op ------------------------

start_test "post-commit no-op on feature branch (gate fails)"
make_temp_repo
(
    cd "$TMP_REPO" || exit 1
    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/.git/hooks/post-commit"

    git -C "$TMP_REPO" checkout --quiet -b feature/x
    : > "$TMP_REPO/.ai-state/decisions/drafts/20260503-1201-test-feature-x-thing.md"
    git -C "$TMP_REPO" add ".ai-state/decisions/drafts/20260503-1201-test-feature-x-thing.md"
    git -C "$TMP_REPO" commit --quiet -m "add draft on feature"

    if [ ! -f "$TMP_REPO/tmp/finalize_adrs.py.invocation" ]; then
        pass "finalize_adrs.py NOT invoked on feature branch"
    else
        fail "finalize_adrs.py wrongly invoked on feature branch"
    fi
)
cleanup_temp_repo

# -- Test 5: post-checkout fires only on branch checkout (flag=1) ------------

start_test "post-checkout dispatcher honors branch-checkout-flag"
make_temp_repo
(
    cd "$TMP_REPO" || exit 1
    : > "$TMP_REPO/.ai-state/decisions/drafts/20260503-1202-test-main-co.md"

    # Direct invocation simulating a file checkout (flag=0).
    "$TMP_REPO/.git/../scripts/git-finalize-hook.sh" \
        2>/dev/null || true  # direct invocation is a no-op (basename mismatch)

    # Invoke via symlink shaped as post-checkout, with file-checkout flag.
    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/post-checkout"
    "$TMP_REPO/post-checkout" "$(git -C "$TMP_REPO" rev-parse HEAD)" "$(git -C "$TMP_REPO" rev-parse HEAD)" 0
    if [ ! -f "$TMP_REPO/tmp/finalize_adrs.py.invocation" ]; then
        pass "post-checkout with flag=0 (file checkout) skipped finalize"
    else
        fail "post-checkout with flag=0 wrongly invoked finalize"
    fi

    "$TMP_REPO/post-checkout" "$(git -C "$TMP_REPO" rev-parse HEAD)" "$(git -C "$TMP_REPO" rev-parse HEAD)" 1
    if [ -f "$TMP_REPO/tmp/finalize_adrs.py.invocation" ]; then
        pass "post-checkout with flag=1 (branch checkout) invoked finalize"
    else
        fail "post-checkout with flag=1 should invoke finalize"
    fi
)
cleanup_temp_repo

# -- Test 6: non-blocking when finalize script is missing --------------------

start_test "non-blocking when a python script is missing"
make_temp_repo
(
    cd "$TMP_REPO" || exit 1
    rm -f "$TMP_REPO/scripts/finalize_adrs.py"
    : > "$TMP_REPO/.ai-state/decisions/drafts/20260503-1203-test-main-missing.md"

    ln -sf "$TMP_REPO/scripts/git-finalize-hook.sh" "$TMP_REPO/.git/hooks/post-commit"
    git -C "$TMP_REPO" add ".ai-state/decisions/drafts/20260503-1203-test-main-missing.md"
    if git -C "$TMP_REPO" commit --quiet -m "missing script test"; then
        pass "commit succeeded despite missing finalize_adrs.py"
    else
        fail "commit failed with missing script — should be non-blocking"
    fi
)
cleanup_temp_repo

# -- Test 7: dispatcher direct invocation prints usage and exits 0 -----------

start_test "dispatcher direct invocation is a clean no-op"
out="$("$DISPATCHER_PATH" 2>&1)"
rc=$?
if [ "$rc" -eq 0 ]; then
    pass "direct invocation exits 0"
else
    fail "direct invocation exited $rc (expected 0)"
fi
if echo "$out" | grep -q "expected"; then
    pass "direct invocation prints usage hint to stderr"
else
    fail "direct invocation should print usage hint (got: $out)"
fi

# -- Summary ------------------------------------------------------------------

printf "\n=== Summary ===\n"
read -r PASS_COUNT FAIL_COUNT < "$COUNTER_FILE"
printf "  PASS: %d\n" "$PASS_COUNT"
printf "  FAIL: %d\n" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
