#!/usr/bin/env bash
# Tests for scripts/diagram-regen-hook.sh, the pre-commit entry of the `diagram-regen`
# hook, which wraps `scripts/regenerate_diagrams.py --staged`.
#
# Observable behaviors:
#   T1: no staged *.c4 → exit 0
#   T2: likec4 not on PATH → exit 0 + "likec4 not installed" warning
#   T3: d2 not on PATH → exit 0 + "d2 not installed" warning
#   T4: a model that records no element → commit aborted with the no-views FAIL message [toolchain]
#   T5: a valid model → exit 0, .d2 + .svg renders written and staged                 [toolchain]
#   T6: a declared view that draws nothing → commit aborted naming that view           [toolchain]
#   T7: a toolchain binary that fails → commit aborted carrying that binary's stderr
#   T8: toolchain absent → the commit proceeds even when python3 itself is broken
#   T9: a tool off its pinned version → warning naming the pins, exit 0, nothing staged
#
# Fixtures are staged in the repository's real diagram layout:
# docs/diagrams/<name>/src/<name>.c4 in, docs/diagrams/<name>/rendered/ out.
#
# Plain bash with pass/fail helpers, like the other tests/*.sh suites (bats is not
# installed here). [toolchain] cases need likec4 and d2 at the versions the command
# pins and are skipped otherwise; every other case runs everywhere, using stubs.
#
# Run from repo root:
#   bash tests/test_diagram_regen_hook.sh
#
# Exits 0 on full pass (skips included), 1 on any failure. Portable to macOS + Linux.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_SCRIPT="${REPO_ROOT}/scripts/diagram-regen-hook.sh"
COMMAND_SCRIPT="${REPO_ROOT}/scripts/regenerate_diagrams.py"
FIXTURES_DIR="${REPO_ROOT}/tests/fixtures"
BASH_BIN="$(command -v bash)"
SYSTEM_PATH="/usr/bin:/bin"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
WORK_ROOT="$(mktemp -d)"

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() { rm -rf "${WORK_ROOT}"; }
trap cleanup EXIT

pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '[PASS] %s\n' "$1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '[FAIL] %s\n' "$1" >&2; }
skip() { SKIP_COUNT=$((SKIP_COUNT + 1)); printf '[SKIP] %s\n' "$1"; }

# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------

# Build an isolated git repo with HEAD, optionally staging one model source at
# docs/diagrams/<name>/src/<name>.c4 (the layout the command discovers roots in).
#
# Usage: make_sandbox [<path_to_c4_file_to_stage>]
# Globals set: SANDBOX, SANDBOX_WORKTREE, SANDBOX_RENDER_DIR
make_sandbox() {
    local staged_c4="${1:-}"
    SANDBOX="$(mktemp -d "${WORK_ROOT}/sandbox.XXXXXX")"
    SANDBOX_WORKTREE="${SANDBOX}/repo"
    SANDBOX_RENDER_DIR=""

    mkdir -p "${SANDBOX_WORKTREE}/docs/diagrams"
    git -C "${SANDBOX_WORKTREE}" init -q
    git -C "${SANDBOX_WORKTREE}" config user.email "test@test.com"
    git -C "${SANDBOX_WORKTREE}" config user.name "Test"
    touch "${SANDBOX_WORKTREE}/.gitkeep"
    git -C "${SANDBOX_WORKTREE}" add .gitkeep
    git -C "${SANDBOX_WORKTREE}" commit -q -m "init"

    if [ -n "${staged_c4}" ]; then
        local name
        name="$(basename "${staged_c4}" .c4)"
        local diagram_dir="${SANDBOX_WORKTREE}/docs/diagrams/${name}"
        SANDBOX_RENDER_DIR="${diagram_dir}/rendered"
        mkdir -p "${diagram_dir}/src"
        cp "${staged_c4}" "${diagram_dir}/src/${name}.c4"
        git -C "${SANDBOX_WORKTREE}" add "${diagram_dir}/src/${name}.c4"
    fi
}

# Write a model source under WORK_ROOT and print its path.
# Usage: write_model <name> <content>
write_model() {
    local path="${WORK_ROOT}/$1.c4"
    printf '%s\n' "$2" > "${path}"
    printf '%s' "${path}"
}

# Run the hook from inside the sandbox repo, the way pre-commit runs a
# `language: system` hook, with PATH = <extra>:/usr/bin:/bin.
# Globals set: LAST_ERR, LAST_EXIT
run_hook() {
    local extra_path="${1:-}"
    local effective_path="${SYSTEM_PATH}"
    [ -n "${extra_path}" ] && effective_path="${extra_path}:${SYSTEM_PATH}"
    LAST_ERR="${SANDBOX}/stderr"
    ( cd "${SANDBOX_WORKTREE}" && \
        PATH="${effective_path}" "${BASH_BIN}" "${HOOK_SCRIPT}" \
        >"${SANDBOX}/stdout" 2>"${LAST_ERR}" )
    LAST_EXIT=$?
}

# Usage: make_stub_binary <dir> <name> <exit_code> [<stderr_msg>]
make_stub_binary() {
    local dir="$1" name="$2" exit_code="$3" msg="${4:-}"
    mkdir -p "${dir}"
    {
        printf '#!/bin/sh\n'
        [ -n "${msg}" ] && printf "echo '%s' >&2\n" "${msg}"
        printf 'exit %s\n' "${exit_code}"
    } > "${dir}/${name}"
    chmod +x "${dir}/${name}"
}

# ---------------------------------------------------------------------------
# Pinned toolchain
# ---------------------------------------------------------------------------

# The version the command pins for <constant>, read from its single statement.
pinned_version() {
    sed -n "s/^$1 = \"\\(.*\\)\"$/\\1/p" "${COMMAND_SCRIPT}"
}

installed_version() {
    "$1" --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | tail -n 1
}

# TOOLCHAIN_PATH holds the directories of likec4, d2 and node when the installed
# likec4 and d2 match the pins, and stays empty otherwise.
TOOLCHAIN_PATH=""
detect_pinned_toolchain() {
    command -v likec4 >/dev/null 2>&1 && command -v d2 >/dev/null 2>&1 || return 0
    [ "$(installed_version likec4)" = "$(pinned_version LIKEC4_VERSION)" ] || return 0
    [ "$(installed_version d2)" = "$(pinned_version D2_VERSION)" ] || return 0
    TOOLCHAIN_PATH="$(dirname "$(command -v likec4)"):$(dirname "$(command -v d2)")"
    if command -v node >/dev/null 2>&1; then
        TOOLCHAIN_PATH="${TOOLCHAIN_PATH}:$(dirname "$(command -v node)")"
    fi
}

# Usage: needs_toolchain <case label> || return
needs_toolchain() {
    [ -n "${TOOLCHAIN_PATH}" ] && return 0
    skip "$1: likec4 $(pinned_version LIKEC4_VERSION) and d2 $(pinned_version D2_VERSION) not on PATH"
    return 1
}

# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

t1_no_staged_c4_is_noop() {
    make_sandbox
    run_hook "${TOOLCHAIN_PATH}"
    if [ "${LAST_EXIT}" -eq 0 ]; then
        pass "T1: no staged .c4 files exits 0"
    else
        fail "T1: expected exit=0 with no .c4 staged; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

t2_likec4_missing_graceful_skip() {
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook ""
    if [ "${LAST_EXIT}" -eq 0 ] && grep -qi 'likec4 not installed' "${LAST_ERR}"; then
        pass "T2: likec4 absent → exit 0 + 'likec4 not installed' warning"
    else
        fail "T2: expected exit=0 + 'likec4 not installed'; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

t3_d2_missing_graceful_skip() {
    local stub_dir="${WORK_ROOT}/stubs_t3"
    make_stub_binary "${stub_dir}" "likec4" 0
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook "${stub_dir}"
    if [ "${LAST_EXIT}" -eq 0 ] && grep -qi 'd2 not installed' "${LAST_ERR}"; then
        pass "T3: d2 absent → exit 0 + 'd2 not installed' warning"
    else
        fail "T3: expected exit=0 + 'd2 not installed'; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# likec4 adds an `index` view to a model that declares none, so a model without views
# cannot be written; one that records no element is what leaves no view to draw.
t4_model_without_elements_aborts() {
    needs_toolchain "T4" || return
    make_sandbox "$(write_model empty 'specification {
  element actor
}
model {
}')"
    run_hook "${TOOLCHAIN_PATH}"
    if [ "${LAST_EXIT}" -ne 0 ] && grep -q 'FAIL no-views' "${LAST_ERR}"; then
        pass "T4: a model recording no element → commit aborted with the no-views FAIL message"
    else
        fail "T4: expected non-zero exit + 'FAIL no-views'; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# The expected render directory is derived from the fixture's own name, never read
# back from the hook's output, so a change to where renders land fails here.
t5_happy_path_artifacts_staged() {
    needs_toolchain "T5" || return
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook "${TOOLCHAIN_PATH}"
    if [ "${LAST_EXIT}" -ne 0 ]; then
        fail "T5: expected exit=0 on the happy path; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
        return
    fi
    local staged
    staged="$(git -C "${SANDBOX_WORKTREE}" diff --cached --name-only)"
    if [ -f "${SANDBOX_RENDER_DIR}/index.d2" ] && [ -f "${SANDBOX_RENDER_DIR}/index.svg" ] \
        && echo "${staged}" | grep -q 'rendered/index\.d2$' \
        && echo "${staged}" | grep -q 'rendered/index\.svg$'; then
        pass "T5: happy path → exit 0, index.d2 + index.svg written and staged"
    else
        fail "T5: expected rendered/index.{d2,svg} written and staged; staged=$(echo "${staged}" | tr '\n' ' ')"
    fi
}

t6_empty_view_aborts_naming_it() {
    needs_toolchain "T6" || return
    make_sandbox "$(write_model emptyview "$(cat "${FIXTURES_DIR}/minimal.c4")
views {
  view probe_empty_view {
    title \"Empty Probe View\"
  }
}")"
    run_hook "${TOOLCHAIN_PATH}"
    if [ "${LAST_EXIT}" -ne 0 ] && grep -q 'FAIL view-without-render probe_empty_view' "${LAST_ERR}"; then
        pass "T6: a declared view drawing nothing → commit aborted naming probe_empty_view"
    else
        fail "T6: expected non-zero exit naming probe_empty_view; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

t7_failing_toolchain_aborts_with_its_message() {
    local stub_dir="${WORK_ROOT}/stubs_t7"
    local message="simulated toolchain failure"
    make_stub_binary "${stub_dir}" "likec4" 3 "${message}"
    make_stub_binary "${stub_dir}" "d2" 3 "${message}"
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook "${stub_dir}"
    if [ "${LAST_EXIT}" -ne 0 ] && grep -q "${message}" "${LAST_ERR}" \
        && grep -q 'FAIL toolchain-error' "${LAST_ERR}"; then
        pass "T7: a failing toolchain binary → commit aborted with its stderr"
    else
        fail "T7: expected non-zero exit + toolchain-error carrying '${message}'; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# The toolchain check must run before any python3 call: a stub python3 that fails
# stands in for a broken system shim, and must never be reached.
t8_absent_toolchain_never_reaches_python() {
    local stub_dir="${WORK_ROOT}/stubs_t8"
    make_stub_binary "${stub_dir}" "python3" 69 "python3 was called"
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook "${stub_dir}"
    if [ "${LAST_EXIT}" -eq 0 ] && ! grep -q 'python3 was called' "${LAST_ERR}"; then
        pass "T8: toolchain absent → exit 0 without calling a broken python3"
    else
        fail "T8: expected exit=0 without calling python3; got exit=${LAST_EXIT}, stderr=$(cat "${LAST_ERR}")"
    fi
}

# An off-pin tool is refused, never used: the commit proceeds and CI judges the renders.
t9_off_pin_tool_skips_without_staging() {
    local stub_dir="${WORK_ROOT}/stubs_t9"
    make_stub_binary "${stub_dir}" "likec4" 0 "0.0.1"
    make_stub_binary "${stub_dir}" "d2" 0 "$(pinned_version D2_VERSION)"
    make_sandbox "${FIXTURES_DIR}/minimal.c4"
    run_hook "${stub_dir}"
    local staged
    staged="$(git -C "${SANDBOX_WORKTREE}" diff --cached --name-only)"
    if [ "${LAST_EXIT}" -eq 0 ] \
        && grep -q "likec4 0.0.1 found but $(pinned_version LIKEC4_VERSION) is pinned" "${LAST_ERR}" \
        && ! echo "${staged}" | grep -q 'rendered/' && [ ! -d "${SANDBOX_RENDER_DIR}" ]; then
        pass "T9: likec4 off its pin → warning naming the pin, exit 0, nothing written or staged"
    else
        fail "T9: expected exit=0, the pin named, nothing staged; got exit=${LAST_EXIT}, staged=$(echo "${staged}" | tr '\n' ' '), stderr=$(cat "${LAST_ERR}")"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    local required
    for required in "${HOOK_SCRIPT}" "${COMMAND_SCRIPT}" "${FIXTURES_DIR}/minimal.c4"; do
        if [ ! -f "${required}" ]; then
            printf 'SETUP FAIL: %s not found\n' "${required}" >&2
            exit 1
        fi
    done
    detect_pinned_toolchain

    t1_no_staged_c4_is_noop
    t2_likec4_missing_graceful_skip
    t3_d2_missing_graceful_skip
    t4_model_without_elements_aborts
    t5_happy_path_artifacts_staged
    t6_empty_view_aborts_naming_it
    t7_failing_toolchain_aborts_with_its_message
    t8_absent_toolchain_never_reaches_python
    t9_off_pin_tool_skips_without_staging

    printf '\n--- summary: %d passed, %d failed, %d skipped ---\n' \
        "${PASS_COUNT}" "${FAIL_COUNT}" "${SKIP_COUNT}"
    if [ "${FAIL_COUNT}" -eq 0 ]; then
        printf '=== T1–T9: %d passed, %d skipped ===\n' "${PASS_COUNT}" "${SKIP_COUNT}"
        exit 0
    fi
    printf '=== %d of %d tests failed ===\n' "${FAIL_COUNT}" "$((PASS_COUNT + FAIL_COUNT))" >&2
    exit 1
}

main "$@"
