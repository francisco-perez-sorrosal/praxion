#!/usr/bin/env bash
# Tests for scripts/diagram-regen-hook.sh pre-commit regeneration hook.
#
# Validates observable behaviors of the hook:
#   T1: No staged *.c4 files → exit 0 (no-op, no output)
#   T2: likec4 not on PATH → exit 0 + stderr contains "likec4 not installed"
#   T3: d2 not on PATH → exit 0 + stderr contains "d2 not installed"
#   T4: likec4 present + DSL invalid → exit 0 (LikeC4 lenient) + ERROR in stderr  [requires likec4+d2]
#   T5: Both binaries present + DSL valid → exit 0, .d2 and .svg staged  [requires likec4+d2]
#
# Test framework: plain bash with pass/fail helpers — matches the project's existing
# test pattern (tests/new_project_test.sh, tests/test_install_filter.sh). Bats is
# not installed in this project's test infrastructure.
#
# Tests T4 and T5 require the likec4 and d2 binaries. If either is absent these
# tests are skipped with an explicit SKIP annotation. Tests T1-T3 always run.
#
# Run from repo root:
#   bash tests/test_diagram_regen_hook.sh
#
# Exits 0 on full pass (or all-skip for binary-dependent tests), 1 on any failure.
# Portable to macOS (BSD) + Linux.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_SCRIPT="${REPO_ROOT}/scripts/diagram-regen-hook.sh"
FIXTURES_DIR="${REPO_ROOT}/tests/fixtures"
BASH_BIN="$(command -v bash)"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
WORK_ROOT="$(mktemp -d)"

cleanup() { rm -rf "${WORK_ROOT}"; }
trap cleanup EXIT

pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '[PASS] %s\n' "$1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '[FAIL] %s\n' "$1" >&2; }
skip() { SKIP_COUNT=$((SKIP_COUNT + 1)); printf '[SKIP] %s\n' "$1"; }

# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------

# Build an isolated sandbox with a minimal git repo + fake staged index.
# Usage: make_sandbox [<path_to_c4_file_to_stage>]
# Globals set: SANDBOX, SANDBOX_GIT_DIR, SANDBOX_WORKTREE
make_sandbox() {
    local staged_c4="${1:-}"
    SANDBOX="$(mktemp -d "${WORK_ROOT}/sandbox.XXXXXX")"
    SANDBOX_WORKTREE="${SANDBOX}/repo"
    SANDBOX_GIT_DIR="${SANDBOX_WORKTREE}/.git"

    mkdir -p "${SANDBOX_WORKTREE}/docs/diagrams"

    # Initialise a real git repo so `git diff --cached` works.
    git -C "${SANDBOX_WORKTREE}" init -q
    git -C "${SANDBOX_WORKTREE}" config user.email "test@test.com"
    git -C "${SANDBOX_WORKTREE}" config user.name "Test"

    # Seed the index with an initial commit so HEAD exists.
    touch "${SANDBOX_WORKTREE}/.gitkeep"
    git -C "${SANDBOX_WORKTREE}" add .gitkeep
    git -C "${SANDBOX_WORKTREE}" commit -q -m "init"

    if [ -n "${staged_c4}" ]; then
        # Place the file at the expected diagrams path and stage it.
        local dest="${SANDBOX_WORKTREE}/docs/diagrams/$(basename "${staged_c4}")"
        cp "${staged_c4}" "${dest}"
        git -C "${SANDBOX_WORKTREE}" add "${dest}"
    fi
}

# Run the hook inside the sandbox.
# Globals consumed: SANDBOX_WORKTREE
# Globals set: LAST_OUT, LAST_ERR, LAST_EXIT
run_hook() {
    local extra_path="${1:-}"
    local effective_path
    if [ -n "${extra_path}" ]; then
        effective_path="${extra_path}:/usr/bin:/bin"
    else
        effective_path="/usr/bin:/bin"
    fi

    LAST_OUT="${SANDBOX}/stdout"
    LAST_ERR="${SANDBOX}/stderr"

    # Run the hook from inside the sandbox git repo so that
    # `git diff --cached` resolves against the right index.
    ( cd "${SANDBOX_WORKTREE}" && \
        PATH="${effective_path}" \
        "${BASH_BIN}" "${HOOK_SCRIPT}" \
        >"${LAST_OUT}" 2>"${LAST_ERR}" )
    LAST_EXIT=$?
}

# ---------------------------------------------------------------------------
# Stub-binary builder
# ---------------------------------------------------------------------------

# Create a stub binary that behaves like a present-but-failing likec4/d2.
# Usage: make_stub_binary <dir> <name> <exit_code> [<stderr_msg>]
make_stub_binary() {
    local dir="$1" name="$2" exit_code="$3" msg="${4:-}"
    mkdir -p "${dir}"
    cat > "${dir}/${name}" <<EOF
#!/usr/bin/env bash
${msg:+printf '%s\n' "${msg}" >&2}
exit ${exit_code}
EOF
    chmod +x "${dir}/${name}"
}

# ---------------------------------------------------------------------------
# T1: No staged .c4 files → exit 0 (no-op)
# ---------------------------------------------------------------------------

t1_no_staged_c4_is_noop() {
    make_sandbox  # no staged .c4

    run_hook

    if [ "${LAST_EXIT}" -eq 0 ]; then
        pass "T1: no staged .c4 files exits 0 (no-op)"
    else
        fail "T1: expected exit=0 when no .c4 files staged; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# ---------------------------------------------------------------------------
# T2: likec4 not on PATH → exit 0 + stderr contains "likec4 not installed"
# ---------------------------------------------------------------------------

t2_likec4_missing_graceful_skip() {
    make_sandbox "${FIXTURES_DIR}/minimal.c4"

    # PATH has no likec4 or d2 — use a stripped minimal PATH.
    run_hook ""

    if [ "${LAST_EXIT}" -eq 0 ] && grep -qi 'likec4 not installed' "${LAST_ERR}"; then
        pass "T2: likec4 absent → exit 0 + 'likec4 not installed' in stderr"
    else
        fail "T2: expected exit=0 + 'likec4 not installed' in stderr; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# ---------------------------------------------------------------------------
# T3: d2 not on PATH → exit 0 + stderr contains "d2 not installed"
# ---------------------------------------------------------------------------

t3_d2_missing_graceful_skip() {
    local stub_dir="${WORK_ROOT}/stubs_t3"
    make_stub_binary "${stub_dir}" "likec4" 0  # likec4 present, no-op stub
    make_sandbox "${FIXTURES_DIR}/minimal.c4"

    run_hook "${stub_dir}"

    if [ "${LAST_EXIT}" -eq 0 ] && grep -qi 'd2 not installed' "${LAST_ERR}"; then
        pass "T3: d2 absent → exit 0 + 'd2 not installed' in stderr"
    else
        fail "T3: expected exit=0 + 'd2 not installed' in stderr; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# ---------------------------------------------------------------------------
# T4: likec4 present + DSL invalid → hook completes silently (exit 0; no error)
#     Skipped when the real likec4 binary is not installed.
#
# NOTE: LikeC4 v1.56.0 is extremely lenient on parse errors. When called via
# the hook (which passes a workspace directory rather than a single file),
# malformed DSL produces an empty `.d2` rather than any error output. The
# hook then runs `d2` against the empty `.d2` and produces an empty `.svg`,
# reporting "Diagram regeneration complete" — no ERROR signal anywhere.
#
# T4 documents that contract: the hook does NOT raise on bad DSL because
# the underlying tools don't either. If LikeC4 or D2 ever flip to strict
# parse, this test fails and forces a review of the hook's failure-mode
# story (we may then want to add a content-validity check ourselves).
# ---------------------------------------------------------------------------

t4_invalid_dsl_silently_completes() {
    if ! command -v likec4 >/dev/null 2>&1; then
        skip "T4: likec4 not installed — skipping lenient-parse contract test"
        return
    fi
    if ! command -v d2 >/dev/null 2>&1; then
        skip "T4: d2 not installed — skipping lenient-parse contract test"
        return
    fi

    # Write an intentionally malformed .c4 file.
    local bad_fixture="${WORK_ROOT}/bad.c4"
    printf '@@@ this is not valid LikeC4 DSL @@@\n' > "${bad_fixture}"

    make_sandbox "${bad_fixture}"

    # Use the real PATH so both real binaries are invoked.
    local bin_path
    bin_path="$(dirname "$(command -v likec4)"):$(dirname "$(command -v d2)")"
    run_hook "${bin_path}"

    # Lenient-parse contract: hook exits 0, completes its run, no ERROR raised.
    if [ "${LAST_EXIT}" -eq 0 ] && grep -q 'Diagram regeneration complete' "${LAST_ERR}"; then
        pass "T4: invalid DSL → hook completes silently (LikeC4 lenient parse contract)"
    else
        fail "T4: expected exit=0 + 'Diagram regeneration complete' in stderr; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# ---------------------------------------------------------------------------
# T5: Both binaries present + DSL valid → exit 0, artifacts staged
#     Skipped when either likec4 or d2 is not installed.
# ---------------------------------------------------------------------------

t5_happy_path_artifacts_staged() {
    if ! command -v likec4 >/dev/null 2>&1; then
        skip "T5: likec4 not installed — skipping happy-path artifact-staging test"
        return
    fi
    if ! command -v d2 >/dev/null 2>&1; then
        skip "T5: d2 not installed — skipping happy-path artifact-staging test"
        return
    fi

    make_sandbox "${FIXTURES_DIR}/minimal.c4"

    # Inject both real binaries into PATH.
    local bin_path
    bin_path="$(dirname "$(command -v likec4)"):$(dirname "$(command -v d2)")"
    run_hook "${bin_path}"

    if [ "${LAST_EXIT}" -ne 0 ]; then
        fail "T5: expected exit=0 on happy path; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
        return
    fi

    # Verify .d2 and .svg artifacts exist in the output directory.
    local out_dir="${SANDBOX_WORKTREE}/docs/diagrams/minimal"
    local d2_count svg_count
    d2_count="$(find "${out_dir}" -maxdepth 1 -name '*.d2' 2>/dev/null | wc -l | tr -d ' ')"
    svg_count="$(find "${out_dir}" -maxdepth 1 -name '*.svg' 2>/dev/null | wc -l | tr -d ' ')"

    if [ "${d2_count}" -ge 1 ] && [ "${svg_count}" -ge 1 ]; then
        # Verify artifacts are staged in git.
        local staged
        staged="$(git -C "${SANDBOX_WORKTREE}" diff --cached --name-only)"
        if echo "${staged}" | grep -qE '\.d2$' && echo "${staged}" | grep -qE '\.svg$'; then
            pass "T5: happy path → exit 0, .d2 + .svg artifacts present and staged"
        else
            fail "T5: artifacts generated but not staged in git; staged=$(echo "${staged}" | tr '\n' ' ')"
        fi
    else
        fail "T5: expected ≥1 .d2 and ≥1 .svg in ${out_dir}/; got d2=${d2_count} svg=${svg_count}"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    if [ ! -f "${HOOK_SCRIPT}" ]; then
        printf 'SETUP FAIL: hook script not found at %s\n' "${HOOK_SCRIPT}" >&2
        printf 'The implementer must write scripts/diagram-regen-hook.sh before this test can reach GREEN.\n' >&2
        exit 1
    fi

    if [ ! -f "${FIXTURES_DIR}/minimal.c4" ]; then
        printf 'SETUP FAIL: fixture not found at %s\n' "${FIXTURES_DIR}/minimal.c4" >&2
        exit 1
    fi

    t1_no_staged_c4_is_noop
    t2_likec4_missing_graceful_skip
    t3_d2_missing_graceful_skip
    t4_invalid_dsl_silently_completes
    t5_happy_path_artifacts_staged

    printf '\n--- summary: %d passed, %d failed, %d skipped ---\n' \
        "${PASS_COUNT}" "${FAIL_COUNT}" "${SKIP_COUNT}"

    if [ "${FAIL_COUNT}" -eq 0 ]; then
        printf '=== T1–T5: %d passed, %d skipped ===\n' "${PASS_COUNT}" "${SKIP_COUNT}"
        exit 0
    fi
    printf '=== %d of %d tests failed ===\n' "${FAIL_COUNT}" "$((PASS_COUNT + FAIL_COUNT))" >&2
    exit 1
}

main "$@"
