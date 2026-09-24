#!/usr/bin/env bash
# Temp-HOME round-trip tests for the legacy context-hub (chub) cleanup shim
# in install.sh / install_claude.sh / install_cursor.sh. Every scenario
# describes the shim's contract: a clean machine sees nothing chub-related,
# report modes never write, removal needs per-item consent on a TTY, and
# non-interactive runs change nothing.
#
# Hermeticity guarantees:
#   - Every scenario runs against its own `mktemp -d` HOME (and, for the
#     Cursor scenario, its own `mktemp -d` install target). Nothing here
#     ever touches the real ~/.claude.json, ~/.chub, ~/.claude/settings.json,
#     or global npm.
#   - `npm`, `chub`, and `claude` are stub executables (generated per
#     scenario into a throwaway bin dir) that log their invocation to a file
#     instead of acting, and are put FIRST on PATH so `command -v`/`npm ls`
#     resolve them instead of any real binary. The `claude` stub exists
#     because scripts/install-obsidian-deps.sh --check shells out to the
#     real CLI regardless of chub state, and the real CLI does first-run
#     bootstrap on whatever $HOME it sees — silently rewriting .claude.json
#     even when nothing under test touched it, which would pollute the
#     "did X write to .claude.json" assertions below if left unstubbed.
#   - Single-remnant scenarios (only one of chub-home/npm-global/
#     claude-json-mcp/settings-json-mcp present) exercise a distinct code
#     path from the full-remnants scenarios above: bash's `set -e` only
#     aborts a function on a *tail-position* `$bool && cmd` whose `$bool`
#     is false (non-tail occurrences of the same pattern are exempt — the
#     shell only checks the exit status of the pipeline's last command).
#     Seeding all four kinds at once makes every such guard true, so it
#     never hits the tail-abort branch. The single-remnant scenarios below
#     plant exactly one kind so each of report/non-TTY-offer/TTY-offer's
#     tail guards gets exercised with a false condition at least once.
#   - `pty_scripted_run.py` accepts a repeatable `--answer VALUE` flag (in
#     addition to the older `--answers N` blank-Enter count) so a scenario
#     can script a specific sequence of prompt choices — e.g. `--answer 2
#     --answer 2` to explicitly decline two prompts in a row — not just
#     accept every default with Enter.
#   - `install.sh --uninstall` (plain, not --complete-uninstall) is
#     deliberately never invoked here: it calls uninstall_python_tooling(),
#     which `rm -rf`s "${SCRIPT_DIR}/.venv" — the REAL repo's virtualenv,
#     not anything under the scenario's temp HOME (SCRIPT_DIR is resolved
#     from the script's own path, independent of $HOME). Every interactive/
#     removal scenario below drives `--complete-uninstall` instead, whose
#     dispatch (install_claude.sh's complete_uninstall_from_plugin) never
#     reaches that code path.
#
# Run from repo root:
#   bash tests/test_legacy_chub_cleanup.sh
#
# Exits 0 on success, 1 on first failure (after printing diagnostics for
# every scenario — does not stop at the first failing scenario).

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SH="${REPO_ROOT}/install.sh"
INSTALL_CLAUDE_SH="${REPO_ROOT}/install_claude.sh"
INSTALL_CURSOR_SH="${REPO_ROOT}/install_cursor.sh"
PTY_RUNNER="${REPO_ROOT}/tests/support/pty_scripted_run.py"

SUITE_TMP="$(mktemp -d)"
trap 'rm -rf "$SUITE_TMP"' EXIT

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

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

# Recording npm/chub stubs on a throwaway PATH prefix. Both log every
# invocation to $STUB_LOG (must be exported by the caller) instead of acting.
# `npm ls -g --depth=0 @aisuite/chub` answers via $STUB_NPM_HAS_CHUB
# ("1" = simulate globally installed, default = not installed).
make_stub_bin_dir() {
    local bindir="$1"
    mkdir -p "$bindir"

    cat > "${bindir}/npm" <<'STUBEOF'
#!/bin/sh
printf 'npm %s\n' "$*" >> "$STUB_LOG"
if [ "$1" = "ls" ]; then
    if [ "${STUB_NPM_HAS_CHUB:-0}" = "1" ]; then exit 0; else exit 1; fi
fi
exit 0
STUBEOF
    chmod +x "${bindir}/npm"

    cat > "${bindir}/chub" <<'STUBEOF'
#!/bin/sh
printf 'chub %s\n' "$*" >> "$STUB_LOG"
case "$1" in
    --cli-version) echo "9.9.9" ;;
esac
exit 0
STUBEOF
    chmod +x "${bindir}/chub"

    # scripts/install-obsidian-deps.sh --check/--uninstall shells out to the
    # REAL `claude` CLI (`claude plugin list`) regardless of what flag
    # install.sh itself was given — an unrelated, pre-existing side effect
    # that is NOT hermetic on its own: the real `claude` binary performs
    # first-run bootstrap on whatever $HOME it sees, silently rewriting
    # .claude.json (merging in machineID/firstStartTime/etc.) even though
    # nothing in install.sh's own chub-cleanup code touched the file. Stub
    # it too so every scenario's "did X write to .claude.json" assertion
    # measures only the code under test.
    cat > "${bindir}/claude" <<'STUBEOF'
#!/bin/sh
printf 'claude %s\n' "$*" >> "$STUB_LOG"
exit 1
STUBEOF
    chmod +x "${bindir}/claude"
}

# Seed a HOME with all four legacy chub remnant kinds: claude-json-mcp,
# settings-json-mcp, npm-global (paired with the stub above via
# STUB_NPM_HAS_CHUB=1), chub-home.
seed_full_remnants() {
    local home="$1"
    mkdir -p "${home}/.claude"

    cat > "${home}/.claude.json" <<'JSON'
{
  "mcpServers": {
    "chub": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "chub-mcp"]
    },
    "task-chronograph": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "task_chronograph_mcp"]
    }
  }
}
JSON

    cat > "${home}/.claude/settings.json" <<'JSON'
{
  "mcpServers": {
    "chub": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "chub-mcp"]
    }
  }
}
JSON

    mkdir -p "${home}/.chub/annotations"
    printf 'telemetry: false\nfeedback: false\n' > "${home}/.chub/config.yaml"
    printf 'stripe/api: some annotated note\n' > "${home}/.chub/annotations/stripe-api.yaml"
}

sha256_of() {
    shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
}

# -----------------------------------------------------------------------------
# Single-remnant seed helpers — plant exactly one of the four remnant kinds,
# leaving the other three genuinely absent (not present-without-chub-key).
# `~/.claude/settings.json` is left unwritten by every helper that doesn't
# itself seed it, so `seed_claude_json_mcp_only` also exercises "settings.json
# absent entirely" — a file that was never created, not an empty object.
# -----------------------------------------------------------------------------

seed_chub_home_only() {
    local home="$1"
    mkdir -p "${home}/.chub/annotations"
    printf 'telemetry: false\nfeedback: false\n' > "${home}/.chub/config.yaml"
    printf 'stripe/api: some annotated note\n' > "${home}/.chub/annotations/stripe-api.yaml"
}

seed_claude_json_mcp_only() {
    local home="$1"
    cat > "${home}/.claude.json" <<'JSON'
{
  "mcpServers": {
    "chub": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "chub-mcp"]
    },
    "task-chronograph": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "task_chronograph_mcp"]
    }
  }
}
JSON
}

seed_settings_json_mcp_only() {
    local home="$1"
    mkdir -p "${home}/.claude"
    cat > "${home}/.claude/settings.json" <<'JSON'
{
  "mcpServers": {
    "chub": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "chub-mcp"]
    }
  }
}
JSON
}

# -----------------------------------------------------------------------------
# Scenario (a): clean machine, --check / --dry-run print nothing chub-related
# and run no mutating npm step.
# -----------------------------------------------------------------------------

assert_clean_home_flag_is_silent_on_chub() {
    local flag="$1"
    local home stublog bindir output

    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    stublog="${SUITE_TMP}/stub-${flag//[^a-z]/}.log"
    : > "$stublog"
    make_stub_bin_dir "$bindir"
    # No `chub` on PATH beyond the npm stub — a genuinely clean machine has
    # never installed the CLI, so `command -v chub` must fail here too.
    rm -f "${bindir}/chub"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_SH" code "$flag" 2>&1)"

    if printf '%s' "$output" | grep -qiE 'chub|context-hub'; then
        fail "'$flag' on a clean HOME still mentions chub/context-hub: $(printf '%s' "$output" | grep -iE 'chub|context-hub' | head -3)"
    else
        pass "'$flag' on a clean HOME prints nothing chub-related"
    fi

    if grep -qE '^npm (install|uninstall)' "$stublog" 2>/dev/null; then
        fail "'$flag' on a clean HOME ran a mutating npm step: $(cat "$stublog")"
    else
        pass "'$flag' on a clean HOME ran no mutating npm step"
    fi
}

start_test "test_clean_home_check_prints_nothing_chub_related"
assert_clean_home_flag_is_silent_on_chub --check

start_test "test_clean_home_dry_run_prints_nothing_chub_related"
assert_clean_home_flag_is_silent_on_chub --dry-run

# -----------------------------------------------------------------------------
# Scenario (b.1): seeded HOME, --check reports every remnant, writes nothing,
# and the health exit code is unaffected by their presence.
# -----------------------------------------------------------------------------

start_test "test_seeded_check_reports_remnants_and_writes_nothing"
{
    seeded_home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-check.log"
    : > "$stublog"

    # Baseline: run --check on this SAME HOME before any remnant exists, so
    # the later rc comparison isolates "did seeding change the exit code"
    # from any unrelated health-check noise a temp HOME might carry (a
    # comparison across two DIFFERENT homes proves nothing, since each
    # temp HOME's own baseline health-check noise differs).
    clean_rc=0
    env HOME="$seeded_home" PATH="${bindir}:${PATH}" STUB_LOG="${stublog}.clean" \
        "$INSTALL_SH" code --check > /dev/null 2>&1 || clean_rc=$?
    : > "${stublog}.clean"  # not asserted on; only its rc matters here

    seed_full_remnants "$seeded_home"

    claude_json_before="$(sha256_of "${seeded_home}/.claude.json")"
    settings_json_before="$(sha256_of "${seeded_home}/.claude/settings.json")"
    chub_home_listing_before="$(find "${seeded_home}/.chub" | sort)"

    output="$(env HOME="$seeded_home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 "$INSTALL_SH" code --check 2>&1)"
    rc=$?

    # Every remnant location named as a warning — these needles are the
    # shim's own contractual manual-removal strings (what a user would
    # copy-paste to remove each remnant by hand), not a guess at
    # implementation wording.
    for needle in '~/.chub' '@aisuite/chub' '.claude.json' 'settings.json'; do
        if printf '%s' "$output" | grep -qF "$needle"; then
            pass "--check names the '$needle' remnant"
        else
            fail "--check does not mention the '$needle' remnant"
        fi
    done

    if [ "$(sha256_of "${seeded_home}/.claude.json")" = "$claude_json_before" ]; then
        pass "--check leaves .claude.json byte-for-byte unchanged"
    else
        fail "--check modified .claude.json"
    fi
    if [ "$(sha256_of "${seeded_home}/.claude/settings.json")" = "$settings_json_before" ]; then
        pass "--check leaves settings.json byte-for-byte unchanged"
    else
        fail "--check modified settings.json"
    fi
    if [ "$(find "${seeded_home}/.chub" | sort)" = "$chub_home_listing_before" ]; then
        pass "--check leaves ~/.chub untouched"
    else
        fail "--check modified ~/.chub's contents"
    fi

    if grep -qE '^npm (install|uninstall)' "$stublog" 2>/dev/null; then
        fail "--check performed a mutating npm call: $(cat "$stublog")"
    else
        pass "--check performed no mutating npm call"
    fi

    if [ "$rc" -eq "$clean_rc" ]; then
        pass "seeding this HOME with remnants does not change --check's exit code (both: $rc)"
    else
        fail "seeding this SAME HOME with remnants changed --check's exit code (before=$clean_rc, after=$rc)"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (b.2): non-TTY --complete-uninstall removes nothing and prints the
# manual commands instead — also the regression case for the
# pre-existing `ask()`-under-set-e-hits-EOF footgun.
# -----------------------------------------------------------------------------

start_test "test_seeded_non_tty_complete_uninstall_removes_nothing_and_prints_manual_commands"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    seed_full_remnants "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-nontty.log"
    : > "$stublog"

    claude_json_before="$(sha256_of "${home}/.claude.json")"
    settings_json_before="$(sha256_of "${home}/.claude/settings.json")"
    chub_home_listing_before="$(find "${home}/.chub" | sort)"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 "$INSTALL_SH" code --complete-uninstall < /dev/null 2>&1)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "non-TTY --complete-uninstall exits 0 (does not abort on EOF)"
    else
        fail "non-TTY --complete-uninstall exited $rc instead of completing gracefully: $output"
    fi

    for needle in 'npm uninstall -g @aisuite/chub' '~/.chub'; do
        if printf '%s' "$output" | grep -qF "$needle"; then
            pass "non-TTY run prints the manual command '$needle'"
        else
            fail "non-TTY run does not print the manual command '$needle'"
        fi
    done

    if [ "$(sha256_of "${home}/.claude.json")" = "$claude_json_before" ] \
        && [ "$(sha256_of "${home}/.claude/settings.json")" = "$settings_json_before" ] \
        && [ "$(find "${home}/.chub" | sort)" = "$chub_home_listing_before" ]; then
        pass "non-TTY run wrote nothing to any of the four remnant locations"
    else
        fail "non-TTY run mutated remnant state despite non-interactive stdin"
    fi

    if grep -qE '^npm (install|uninstall)' "$stublog" 2>/dev/null; then
        fail "non-TTY run performed a mutating npm call: $(cat "$stublog")"
    else
        pass "non-TTY run performed no mutating npm call"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (f): single-remnant coverage across --check, --dry-run, non-TTY
# --complete-uninstall and interactive --complete-uninstall (Enter defaults).
# Seeding all four remnant kinds at once (scenarios a/b/c above) never
# exercises a *false* `$bool` at a tail-position `$bool && cmd` guard — bash's
# `set -e` only aborts on the tail occurrence of that pattern, not a non-tail
# one (see the header comment). Planting exactly one kind at a time forces
# each such guard to see `false` at least once, so each of the three modes
# below is proven to still complete (rc=0) no matter which single kind is
# present.
# -----------------------------------------------------------------------------

# $1 label, $2 seed function name (empty string = no HOME seeding — used for
# npm-global, which is controlled entirely via $3/STUB_NPM_HAS_CHUB), $3
# STUB_NPM_HAS_CHUB value, $4 flag (--check or --dry-run), $5 a regex a
# landmark output line must match to prove the run continued past the
# legacy-chub block instead of aborting inside it (empty string skips that
# assertion — dry-run's install_claude.sh-side kinds have no such landmark).
#
# Compares this SAME HOME's exit code before vs after the remnant is seeded,
# rather than asserting a flat rc==0: a bare temp HOME's `--check`/`--dry-run`
# is legitimately unhealthy for reasons that have nothing to do with chub
# (e.g. Praxion's own CLI scripts not being linked into ~/.local/bin/ in a
# throwaway HOME) — a flat rc==0 would fail on every single-remnant scenario
# regardless of whether the legacy-chub shim itself works. Same fix as
# scenario (b.1)'s exit-code comparison above.
assert_single_remnant_report_flag_completes() {
    local label="$1" seed_fn="$2" npm_has_chub="$3" flag="$4" landmark="$5"
    local home bindir stublog output rc clean_rc

    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-single-${label}-${flag//[^a-z]/}.log"
    : > "$stublog"

    clean_rc=0
    env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="${stublog}.clean" \
        "$INSTALL_SH" code "$flag" > /dev/null 2>&1 || clean_rc=$?
    : > "${stublog}.clean"  # not asserted on; only its rc matters here

    [ -n "$seed_fn" ] && "$seed_fn" "$home"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB="$npm_has_chub" "$INSTALL_SH" code "$flag" 2>&1)"
    rc=$?

    if [ "$rc" -eq "$clean_rc" ]; then
        pass "$flag with only '$label' present does not change this HOME's exit code (both: $rc)"
    else
        fail "$flag with only '$label' present changed this HOME's exit code (before=$clean_rc, after=$rc): $output"
    fi

    if [ -n "$landmark" ]; then
        if printf '%s' "$output" | grep -qiE "$landmark"; then
            pass "$flag with only '$label' present runs to completion"
        else
            fail "$flag with only '$label' present stopped short of completion: $output"
        fi
    fi
}

start_test "test_single_remnant_check_chub_home_only_completes"
assert_single_remnant_report_flag_completes chub-home seed_chub_home_only 0 --check 'scc (installed|not installed)'

start_test "test_single_remnant_dry_run_chub_home_only_completes"
assert_single_remnant_report_flag_completes chub-home seed_chub_home_only 0 --dry-run 'scc (installed|not installed)'

start_test "test_single_remnant_check_npm_global_only_completes"
assert_single_remnant_report_flag_completes npm-global "" 1 --check 'scc (installed|not installed)'

start_test "test_single_remnant_dry_run_npm_global_only_completes"
assert_single_remnant_report_flag_completes npm-global "" 1 --dry-run 'scc (installed|not installed)'

start_test "test_single_remnant_check_claude_json_mcp_only_completes"
assert_single_remnant_report_flag_completes claude-json-mcp seed_claude_json_mcp_only 0 --check 'All checks passed|Issues found'

start_test "test_single_remnant_dry_run_claude_json_mcp_only_completes"
assert_single_remnant_report_flag_completes claude-json-mcp seed_claude_json_mcp_only 0 --dry-run ""

start_test "test_single_remnant_check_settings_json_mcp_only_completes"
assert_single_remnant_report_flag_completes settings-json-mcp seed_settings_json_mcp_only 0 --check 'All checks passed|Issues found'

start_test "test_single_remnant_dry_run_settings_json_mcp_only_completes"
assert_single_remnant_report_flag_completes settings-json-mcp seed_settings_json_mcp_only 0 --dry-run ""

# $1 label, $2 seed_fn (or empty), $3 STUB_NPM_HAS_CHUB value.
assert_single_remnant_non_tty_complete_uninstall_completes() {
    local label="$1" seed_fn="$2" npm_has_chub="$3"
    local home bindir stublog output rc

    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    [ -n "$seed_fn" ] && "$seed_fn" "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-single-nontty-${label}.log"
    : > "$stublog"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB="$npm_has_chub" "$INSTALL_SH" code --complete-uninstall < /dev/null 2>&1)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "non-TTY --complete-uninstall with only '$label' present exits 0"
    else
        fail "non-TTY --complete-uninstall with only '$label' present exited $rc: $output"
    fi

    if printf '%s' "$output" | grep -qF 'Praxion complete uninstall done'; then
        pass "non-TTY --complete-uninstall with only '$label' present reaches the done banner"
    else
        fail "non-TTY --complete-uninstall with only '$label' present never reached the done banner: $output"
    fi
}

start_test "test_single_remnant_non_tty_chub_home_only_completes"
assert_single_remnant_non_tty_complete_uninstall_completes chub-home seed_chub_home_only 0

start_test "test_single_remnant_non_tty_npm_global_only_completes"
assert_single_remnant_non_tty_complete_uninstall_completes npm-global "" 1

start_test "test_single_remnant_non_tty_claude_json_mcp_only_completes"
assert_single_remnant_non_tty_complete_uninstall_completes claude-json-mcp seed_claude_json_mcp_only 0

start_test "test_single_remnant_non_tty_settings_json_mcp_only_completes"
assert_single_remnant_non_tty_complete_uninstall_completes settings-json-mcp seed_settings_json_mcp_only 0

# $1 label, $2 seed_fn (or empty), $3 STUB_NPM_HAS_CHUB value. Enter-key
# defaults throughout — the explicit-answer ("2") branches are Scenario (g).
assert_single_remnant_interactive_complete_uninstall_completes() {
    local label="$1" seed_fn="$2" npm_has_chub="$3"
    local home bindir stublog output rc

    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    [ -n "$seed_fn" ] && "$seed_fn" "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-single-tty-${label}.log"
    : > "$stublog"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB="$npm_has_chub" python3 "$PTY_RUNNER" --timeout 20 --answers 2 \
        --answer-delay 0.3 -- "$INSTALL_SH" code --complete-uninstall)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "interactive --complete-uninstall with only '$label' present exits 0"
    else
        fail "interactive --complete-uninstall with only '$label' present exited $rc: $output"
    fi

    if printf '%s' "$output" | grep -qF 'Praxion complete uninstall done'; then
        pass "interactive --complete-uninstall with only '$label' present reaches the done banner"
    else
        fail "interactive --complete-uninstall with only '$label' present never reached the done banner: $output"
    fi
}

start_test "test_single_remnant_interactive_chub_home_only_completes"
assert_single_remnant_interactive_complete_uninstall_completes chub-home seed_chub_home_only 0

start_test "test_single_remnant_interactive_npm_global_only_completes"
assert_single_remnant_interactive_complete_uninstall_completes npm-global "" 1

start_test "test_single_remnant_interactive_claude_json_mcp_only_completes"
assert_single_remnant_interactive_complete_uninstall_completes claude-json-mcp seed_claude_json_mcp_only 0

start_test "test_single_remnant_interactive_settings_json_mcp_only_completes"
assert_single_remnant_interactive_complete_uninstall_completes settings-json-mcp seed_settings_json_mcp_only 0

# -----------------------------------------------------------------------------
# Scenario (h): malformed-but-JSON-parseable shapes — `mcpServers: null` and a
# top-level array — must not crash the probe (Python traceback) or its
# caller, and must leave the file byte-for-byte unchanged after `--check`.
# -----------------------------------------------------------------------------

assert_odd_json_shape_does_not_crash_check() {
    local label="$1" json_body="$2"
    local home bindir stublog output rc before after clean_rc

    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-oddjson-${label//[^a-z]/}.log"
    : > "$stublog"

    # Baseline: this SAME HOME, before ~/.claude.json holds the odd shape —
    # isolates "did the odd JSON change the exit code" from unrelated
    # environmental health-check noise a bare temp HOME carries (see
    # assert_single_remnant_report_flag_completes above).
    clean_rc=0
    env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="${stublog}.clean" \
        "$INSTALL_SH" code --check > /dev/null 2>&1 || clean_rc=$?
    : > "${stublog}.clean"

    printf '%s' "$json_body" > "${home}/.claude.json"
    before="$(sha256_of "${home}/.claude.json")"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_SH" code --check 2>&1)"
    rc=$?
    after="$(sha256_of "${home}/.claude.json")"

    if [ "$rc" -eq "$clean_rc" ]; then
        pass "--check on $label ~/.claude.json does not change this HOME's exit code (both: $rc)"
    else
        fail "--check on $label ~/.claude.json changed this HOME's exit code (before=$clean_rc, after=$rc): $output"
    fi

    if printf '%s' "$output" | grep -qiE 'traceback|typeerror|attributeerror'; then
        fail "--check on $label ~/.claude.json printed a Python traceback: $output"
    else
        pass "--check on $label ~/.claude.json produces no traceback"
    fi

    if [ "$before" = "$after" ]; then
        pass "--check on $label ~/.claude.json leaves the file byte-for-byte unchanged"
    else
        fail "--check on $label ~/.claude.json modified the file"
    fi
}

start_test "test_check_mcp_servers_null_does_not_crash"
assert_odd_json_shape_does_not_crash_check 'mcpServers-null' '{"mcpServers": null}'

start_test "test_check_top_level_array_does_not_crash"
assert_odd_json_shape_does_not_crash_check 'top-level-array' '[1, 2, 3]'

# -----------------------------------------------------------------------------
# Scenario (c): `--complete-uninstall` no longer runs the shared scc/Python/
# Obsidian installers — regression test for the --complete-uninstall
# dispatch fix. Uses a clean HOME; this is orthogonal to chub state.
# -----------------------------------------------------------------------------

start_test "test_complete_uninstall_skips_shared_installers"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-regression.log"
    : > "$stublog"

    venv_before="$( [ -d "${REPO_ROOT}/.venv" ] && echo present || echo absent )"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_SH" code --complete-uninstall < /dev/null 2>&1)"
    rc=$?

    venv_after="$( [ -d "${REPO_ROOT}/.venv" ] && echo present || echo absent )"

    if [ "$rc" -eq 0 ]; then
        pass "--complete-uninstall exits 0"
    else
        fail "--complete-uninstall exited $rc: $output"
    fi

    if printf '%s' "$output" | grep -qiE 'Optional Metrics Tool|Obsidian|Python Tooling for Praxion'; then
        fail "--complete-uninstall still ran a shared installer step: $output"
    else
        pass "--complete-uninstall runs no shared installer step (scc/Python/Obsidian)"
    fi

    if [ "$venv_before" = "$venv_after" ]; then
        pass "the real repo's .venv is untouched by --complete-uninstall (still $venv_after)"
    else
        fail "the real repo's .venv changed state ($venv_before -> $venv_after) — .venv deletion landmine"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (b.3): interactive TTY run, Enter-key defaults — chub-home stays
# (default Keep), npm-global and the two MCP entries are removed (default
# Remove), the surviving MCP server and JSON validity are preserved
# Drives a real pty since piped stdin is not a tty.
# -----------------------------------------------------------------------------

start_test "test_interactive_complete_uninstall_enter_defaults"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    seed_full_remnants "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-interactive.log"
    : > "$stublog"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 python3 "$PTY_RUNNER" --timeout 20 --answers 6 --answer-delay 0.3 \
        -- "$INSTALL_SH" code --complete-uninstall)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "interactive --complete-uninstall completes (rc=0)"
    else
        fail "interactive --complete-uninstall did not complete cleanly (rc=$rc): $output"
    fi

    if [ -d "${home}/.chub" ]; then
        pass "chub-home default (Enter) keeps ~/.chub"
    else
        fail "chub-home default (Enter) removed ~/.chub — its default must be Keep"
    fi

    if grep -qF 'npm uninstall -g @aisuite/chub' "$stublog" 2>/dev/null; then
        pass "npm-global default (Enter) calls npm uninstall -g @aisuite/chub"
    else
        fail "npm-global default (Enter) did not call npm uninstall -g @aisuite/chub"
    fi

    if [ -f "${home}/.claude.json" ] && python3 -m json.tool "${home}/.claude.json" > /dev/null 2>&1; then
        pass "~/.claude.json is still valid JSON after cleanup"
        if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
servers = d.get('mcpServers', {})
sys.exit(0 if 'chub' not in servers and 'task-chronograph' in servers else 1)
" "${home}/.claude.json"; then
            pass "~/.claude.json: chub entry removed, other MCP server survives"
        else
            fail "~/.claude.json: chub entry survived or the other MCP server was dropped too"
        fi
    else
        fail "~/.claude.json missing or invalid JSON after cleanup"
    fi

    if [ -f "${home}/.claude/settings.json" ] && python3 -m json.tool "${home}/.claude/settings.json" > /dev/null 2>&1; then
        if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'chub' not in d.get('mcpServers', {}) else 1)
" "${home}/.claude/settings.json"; then
            pass "settings.json's legacy chub MCP entry is removed"
        else
            fail "settings.json still has a chub MCP entry"
        fi
    else
        pass "settings.json absent or empty after cleanup (also an acceptable outcome for the legacy location)"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (g): TTY decline/explicit-answer branches. Scenario (b.3) above
# only exercises Enter-key defaults; these three script a specific non-default
# answer at one prompt while defaulting every other, through the same
# full-remnants seed. Prompt order is claude-json-mcp, settings-json-mcp,
# chub-home, npm-global — the shim asks per-kind, in that order, and this is
# confirmed by the absence of ~/.claude/rules or ~/.local/bin in these temp
# HOMEs (present, they would add two unrelated prompts ahead of these four).
# -----------------------------------------------------------------------------

start_test "test_interactive_chub_home_explicit_remove"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    seed_full_remnants "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-tty-chub-remove.log"
    : > "$stublog"

    # claude-json-mcp: default (Remove); settings-json-mcp: default (Remove);
    # chub-home: explicit "2" (Remove — its default is [1] Keep); npm-global:
    # default (Remove).
    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 python3 "$PTY_RUNNER" --timeout 20 \
        --answer "" --answer "" --answer 2 --answer "" \
        --answer-delay 0.3 -- "$INSTALL_SH" code --complete-uninstall)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "interactive run with explicit chub-home Remove exits 0"
    else
        fail "interactive run with explicit chub-home Remove exited $rc: $output"
    fi

    if [ -d "${home}/.chub" ]; then
        fail "explicit '2' (Remove) at the chub-home prompt did not remove ~/.chub"
    else
        pass "explicit '2' (Remove) at the chub-home prompt removes ~/.chub"
    fi
}

start_test "test_interactive_npm_global_decline_keeps_package"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    seed_full_remnants "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-tty-npm-decline.log"
    : > "$stublog"

    # claude-json-mcp/settings-json-mcp/chub-home: defaults; npm-global:
    # explicit "2" (Keep — its default is [1] Remove).
    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 python3 "$PTY_RUNNER" --timeout 20 \
        --answer "" --answer "" --answer "" --answer 2 \
        --answer-delay 0.3 -- "$INSTALL_SH" code --complete-uninstall)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "interactive run with npm-global decline exits 0"
    else
        fail "interactive run with npm-global decline exited $rc: $output"
    fi

    if grep -qF 'npm uninstall -g @aisuite/chub' "$stublog" 2>/dev/null; then
        fail "declining ('2') at the npm-global prompt still ran npm uninstall: $(cat "$stublog")"
    else
        pass "declining ('2') at the npm-global prompt does not run npm uninstall"
    fi
}

start_test "test_interactive_claude_json_mcp_decline_keeps_entry"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    seed_full_remnants "$home"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-tty-claude-decline.log"
    : > "$stublog"

    # claude-json-mcp: explicit "2" (Keep — its default is [1] Remove);
    # settings-json-mcp/chub-home/npm-global: defaults.
    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        STUB_NPM_HAS_CHUB=1 python3 "$PTY_RUNNER" --timeout 20 \
        --answer 2 --answer "" --answer "" --answer "" \
        --answer-delay 0.3 -- "$INSTALL_SH" code --complete-uninstall)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "interactive run with claude-json-mcp decline exits 0"
    else
        fail "interactive run with claude-json-mcp decline exited $rc: $output"
    fi

    if [ -f "${home}/.claude.json" ] && python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'chub' in d.get('mcpServers', {}) else 1)
" "${home}/.claude.json"; then
        pass "declining ('2') at the ~/.claude.json prompt keeps the chub entry"
    else
        fail "declining ('2') at the ~/.claude.json prompt removed the chub entry anyway"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (d): install_claude.sh's code-mode banners number 0..5 with no
# gap and no stray 6/7 — removing the context-hub MCP step renumbered the
# Phoenix and Claude Desktop banners. Source-based: dry_run_claude_code()
# prints a different, unnumbered summary, so the header calls in the
# source are the meaningful surface.
# -----------------------------------------------------------------------------

start_test "test_install_claude_step_headers_number_contiguously"
{
    # install_claude_desktop() (desktop MODE) has its own independent
    # "Claude Desktop config" banner numbered independently of code-mode's
    # 0..5 sequence — excluded by its unique header text, since the number
    # alone cannot tell the two modes' banners apart.
    numbers="$(grep -n 'header "Step [0-9]' "$INSTALL_CLAUDE_SH" \
        | grep -v 'Claude Desktop config' \
        | grep -oE 'Step [0-9]+' | awk '{print $2}' | sort -un | tr '\n' ' ')"

    if [ "$numbers" = "0 1 2 3 4 5 " ]; then
        pass "code-mode Step banners are exactly 0 1 2 3 4 5 (got: $numbers)"
    else
        fail "code-mode Step banners are not contiguous 0..5 (got: $numbers)"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (e): a Cursor install sweeps a dangling `.cursor/skills/` symlink,
# drops the chub MCP entry with a notice, and a second run's --check is
# clean. The dangling symlink's name is a fabricated one no
# shipped skill uses (`zz-removed-skill-fixture`) — NOT `external-api-docs`.
# Naming it after a still-shipped skill would make the scenario silently
# depend on that skill eventually being deleted from the repo: the sweep
# would remove the dangling link correctly, but the pre-existing per-skill
# reconcile loop that runs immediately after would re-create a link of the
# same *name*, because it would legitimately find a live
# `skills/external-api-docs/` directory to point it at — so the "was swept
# and stays swept" assertion below would be unsatisfiable regardless of the
# sweep's own correctness. A name with no currently-shipped counterpart
# isolates the sweep mechanism from that unrelated reconcile loop.
#
# Drives install_cursor.sh DIRECTLY rather than `install.sh cursor <path>`:
# install.sh's default (no --check/--dry-run/--uninstall) flow runs
# install_chub_cli/install_scc_cli/install_python_tooling/
# install_obsidian_deps FOR EVERY MODE, cursor included, before it even
# delegates — each an interactive `ask()` prompt (or, for Obsidian, a
# network-touching plugin operation) wholly unrelated to the Cursor sweep
# behavior under test. install_cursor.sh itself has no prompts and no
# shared-installer side effects, so it is the actually-hermetic,
# narrowly-scoped entry point for that behavior.
# -----------------------------------------------------------------------------

start_test "test_cursor_round_trip_sweeps_dangling_symlink_and_converges_clean"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    target="$(mktemp -d "${SUITE_TMP}/cursor.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-cursor.log"
    : > "$stublog"
    mkdir -p "${target}/.cursor/skills"
    ln -sfn "${REPO_ROOT}/skills/zz-removed-skill-fixture" \
        "${target}/.cursor/skills/zz-removed-skill-fixture"

    first_output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_CURSOR_SH" "$target" 2>&1)"
    first_rc=$?

    if [ "$first_rc" -eq 0 ]; then
        pass "first cursor install run exits 0"
    else
        fail "first cursor install run exited $first_rc: $first_output"
    fi

    if [ -L "${target}/.cursor/skills/zz-removed-skill-fixture" ] || [ -e "${target}/.cursor/skills/zz-removed-skill-fixture" ]; then
        fail "dangling .cursor/skills/zz-removed-skill-fixture symlink was not swept"
    else
        pass "dangling .cursor/skills/zz-removed-skill-fixture symlink was swept"
    fi

    if printf '%s' "$first_output" | grep -qi 'stale skill link'; then
        pass "sweep announces the removal"
    else
        fail "sweep produced no announcement in the run's output"
    fi

    mcp_json="${target}/.cursor/mcp.json"
    if [ -f "$mcp_json" ] && python3 -m json.tool "$mcp_json" > /dev/null 2>&1; then
        pass "mcp.json is valid JSON after install"
        if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'chub' not in d.get('mcpServers', {}) else 1)
" "$mcp_json"; then
            pass "mcp.json carries no chub server entry"
        else
            fail "mcp.json still carries a chub server entry"
        fi
    else
        fail "mcp.json missing or invalid JSON after install"
    fi

    second_output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_CURSOR_SH" "$target" --check 2>&1)"
    second_rc=$?

    if [ "$second_rc" -eq 0 ]; then
        pass "second run's --check exits 0 (converged clean)"
    else
        fail "second run's --check exited $second_rc: $second_output"
    fi
    if printf '%s' "$second_output" | grep -qi 'chub'; then
        fail "second run's --check still mentions chub: $second_output"
    else
        pass "second run's --check mentions no chub server"
    fi
}

# -----------------------------------------------------------------------------
# Scenario (i): the install path's drop notice and --check's positive warning
# both key off the SAME mcp_json_has_chub() probe against a pre-existing
# mcp.json, but they run at different points in the lifecycle — install
# rewrites mcp.json wholesale right after warning, --check only reads it — so
# each needs its own seeded mcp.json to exercise.
# -----------------------------------------------------------------------------

start_test "test_cursor_install_announces_dropping_a_preexisting_chub_entry"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    target="$(mktemp -d "${SUITE_TMP}/cursor.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-cursor-drop.log"
    : > "$stublog"

    # Seed a pre-removal mcp.json (chub entry present) before install ever
    # runs, so the drop-notice branch — which reads mcp.json BEFORE the
    # install path's wholesale rewrite — sees a chub entry to report.
    mkdir -p "${target}/.cursor"
    cat > "${target}/.cursor/mcp.json" <<'JSON'
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "mcp"]
    }
  }
}
JSON

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_CURSOR_SH" "$target" 2>&1)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "install with a pre-existing chub entry exits 0"
    else
        fail "install with a pre-existing chub entry exited $rc: $output"
    fi

    if printf '%s' "$output" | grep -qi "dropping legacy 'chub'"; then
        pass "install announces dropping the legacy chub entry"
    else
        fail "install did not announce dropping the legacy chub entry: $output"
    fi

    mcp_json="${target}/.cursor/mcp.json"
    if python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
sys.exit(0 if 'chub' not in d.get('mcpServers', {}) else 1)
" "$mcp_json"; then
        pass "mcp.json no longer carries the chub entry after install"
    else
        fail "mcp.json still carries the chub entry after install"
    fi
}

start_test "test_cursor_check_warns_on_legacy_chub_entry_without_failing_health"
{
    home="$(mktemp -d "${SUITE_TMP}/home.XXXXXX")"
    target="$(mktemp -d "${SUITE_TMP}/cursor.XXXXXX")"
    bindir="$(mktemp -d "${SUITE_TMP}/bin.XXXXXX")"
    make_stub_bin_dir "$bindir"
    stublog="${SUITE_TMP}/stub-cursor-check-warn.log"
    : > "$stublog"

    # A clean install first, so every OTHER --check condition (skills,
    # rules, commands, expected MCP servers) is genuinely healthy — this
    # isolates the chub warning from unrelated health-check noise.
    env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_CURSOR_SH" "$target" > /dev/null 2>&1

    # Inject a chub entry directly into the now-clean mcp.json (not via
    # install, which would just drop it again) so --check sees one to warn
    # about, without touching any of the other health-check inputs above.
    mcp_json="${target}/.cursor/mcp.json"
    python3 -c "
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d.setdefault('mcpServers', {})['chub'] = {'command': 'npx', 'args': ['-y', '@aisuite/chub', 'mcp']}
json.dump(d, open(p, 'w'), indent=2)
" "$mcp_json"

    output="$(env HOME="$home" PATH="${bindir}:${PATH}" STUB_LOG="$stublog" \
        "$INSTALL_CURSOR_SH" "$target" --check 2>&1)"
    rc=$?

    if [ "$rc" -eq 0 ]; then
        pass "--check with a legacy chub entry still exits 0 (warning, not failure)"
    else
        fail "--check with a legacy chub entry exited $rc: $output"
    fi

    if printf '%s' "$output" | grep -qi "still has a legacy 'chub'"; then
        pass "--check names the legacy chub entry as a warning"
    else
        fail "--check did not warn about the legacy chub entry: $output"
    fi

    if printf '%s' "$output" | grep -qi 'All checks passed'; then
        pass "--check still reports overall health as passed"
    else
        fail "--check did not report overall health as passed: $output"
    fi
}

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
