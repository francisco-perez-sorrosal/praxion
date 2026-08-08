#!/usr/bin/env bash
# Tests for new_project.sh greenfield onboarding script.
#
# Validates the bash-observable behaviors of the scaffold:
# T1: no args -> usage on stderr, exit 2
# T2: security -- invalid project name -> exit 2, no mkdir
# T3: missing claude -> exit 3, message mentions claude
# T4: missing praxion plugin record -> exit 4
# T5: missing git -> exit 5
# T6: target exists & non-empty -> exit 6, no mutation
# T7: happy path -- scaffold + pre-flight + exec claude
# T8: --hackathon flag -> '# Hackathon mode: true' trailer in seed prompt
# T9: no --hackathon -> '# Hackathon mode: false' trailer (opt-in default)
# T10: PRAXION_NEW_PROJECT_HACKATHON=1 -> '# Hackathon mode: true' trailer
#
# Run from repo root:
#   bash tests/new_project_test.sh
#
# Exits 0 on full pass, 1 on any failure. Portable to macOS (BSD) + Linux.

set -u

SCRIPT_UNDER_TEST="$(cd "$(dirname "$0")/.." && pwd)/new_project.sh"

PASS_COUNT=0
FAIL_COUNT=0
WORK_ROOT="$(mktemp -d)"

# Resolve absolute path of bash so the runner does not depend on its own
# sandboxed PATH leaking it back to the child invocation.
BASH_BIN="$(command -v bash)"

# Build an "essentials" PATH dir that excludes claude/git so we can compose
# per-test PATHs without leaking the host's binaries. We symlink only the
# external commands the script + stub need; shell builtins are not listed.
ESSENTIALS="$WORK_ROOT/essentials"
mkdir -p "$ESSENTIALS"
for tool in bash sh env basename dirname mkdir ls cat grep printf rm chmod readlink uname find pwd head awk; do
    p="$(command -v "$tool" 2>/dev/null || true)"
    [ -n "$p" ] && ln -sf "$p" "$ESSENTIALS/$tool"
done

cleanup() { rm -rf "$WORK_ROOT"; }
trap cleanup EXIT

pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '[PASS] %s\n' "$1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '[FAIL] %s\n' "$1" >&2; }

# Build a per-test sandbox: stub-bin holding `claude` (and optionally `git`)
# plus a plugins file claiming praxion is installed. Returns sandbox dir on stdout.
make_sandbox() {
    local sandbox stub_log
    sandbox="$(mktemp -d "$WORK_ROOT/sandbox.XXXXXX")"
    mkdir -p "$sandbox/bin" "$sandbox/home/.claude/plugins" "$sandbox/target"
    stub_log="$sandbox/stub.log"
    cat > "$sandbox/bin/claude" <<EOF
#!/usr/bin/env bash
# Stub: capture cwd + args, succeed -- but reject leading-dash args that the
# real CLI would treat as unknown options. This catches the historical bug
# where the seed prompt began with YAML frontmatter ('---description: ...')
# and aborted the real claude with 'unknown option'.
{
  printf 'cwd=%s\n' "\$(pwd)"
  for a in "\$@"; do printf 'arg=%s\n' "\$a"; done
} > "$stub_log"
positional=0
for a in "\$@"; do
    if [ "\$a" = "--" ]; then positional=1; continue; fi
    if [ "\$positional" -eq 1 ]; then continue; fi
    case "\$a" in
        --permission-mode|acceptEdits|--allowedTools) ;;
        --*) printf "stub-claude: unknown option '%s'\n" "\$a" >&2; exit 7 ;;
    esac
done
exit 0
EOF
    chmod +x "$sandbox/bin/claude"
    # Symlink real git so the script's `command -v git` succeeds.
    if command -v git >/dev/null 2>&1; then
        ln -s "$(command -v git)" "$sandbox/bin/git"
    fi
    printf '{"praxion@bit-agora": {"version": "test"}}\n' \
        > "$sandbox/home/.claude/plugins/installed_plugins.json"
    printf '%s\n' "$sandbox"
}

# Run the script under test inside an isolated env. Captures stdout/stderr/exit.
# Globals set: LAST_OUT, LAST_ERR, LAST_EXIT. Never enables `set -e` -- the
# whole runner relies on explicit exit-code checks, not abort-on-error.
# PATH = sandbox/bin + ESSENTIALS so claude/git visibility is per-test only.
run_script() {
    local sandbox="$1"; shift
    LAST_OUT="$sandbox/stdout"
    LAST_ERR="$sandbox/stderr"
    HOME="$sandbox/home" PATH="$sandbox/bin:$ESSENTIALS" \
        "$BASH_BIN" "$SCRIPT_UNDER_TEST" "$@" \
        >"$LAST_OUT" 2>"$LAST_ERR"
    LAST_EXIT=$?
}

t1_no_args_usage_exit_2() {
    local s; s="$(make_sandbox)"
    run_script "$s"
    if [ "$LAST_EXIT" -eq 2 ] && grep -q 'Usage:' "$LAST_ERR"; then
        pass "T1: no args prints Usage on stderr and exits 2"
    else
        fail "T1: expected exit=2 + 'Usage:' on stderr; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t2_invalid_name_exit_2_no_mkdir() {
    local s before_count after_count name
    s="$(make_sandbox)"
    before_count="$(find "$s/target" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
    for name in '../x' 'x y' '.hidden'; do
        run_script "$s" "$name" "$s/target"
        if [ "$LAST_EXIT" -ne 2 ]; then
            fail "T2: name '$name' expected exit=2; got exit=$LAST_EXIT"
            return
        fi
    done
    after_count="$(find "$s/target" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
    if [ "$before_count" = "$after_count" ]; then
        pass "T2: invalid names ('../x','x y','.hidden') exit 2 with no mkdir"
    else
        fail "T2: target dir mutated (before=$before_count after=$after_count)"
    fi
}

t3_missing_claude_exit_3() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/bin/claude"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 3 ] && grep -qi 'claude' "$LAST_ERR"; then
        pass "T3: missing claude exits 3 with claude-mentioning stderr"
    else
        fail "T3: expected exit=3 + 'claude' in stderr; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t4_missing_plugin_exit_4() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/home/.claude/plugins/installed_plugins.json"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 4 ]; then
        pass "T4: missing praxion plugin record exits 4"
    else
        fail "T4: expected exit=4; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t5_missing_git_exit_5() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/bin/git"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 5 ]; then
        pass "T5: missing git exits 5"
    else
        fail "T5: expected exit=5; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t6_target_exists_nonempty_exit_6() {
    local s before_listing after_listing
    s="$(make_sandbox)"
    mkdir -p "$s/target/my-app"
    : > "$s/target/my-app/preexisting.txt"
    before_listing="$(ls -1 "$s/target/my-app")"
    run_script "$s" my-app "$s/target"
    after_listing="$(ls -1 "$s/target/my-app")"
    if [ "$LAST_EXIT" -eq 6 ] && [ "$before_listing" = "$after_listing" ]; then
        pass "T6: non-empty target exits 6 with no mutation"
    else
        fail "T6: expected exit=6 + identical listing; got exit=$LAST_EXIT, before=[$before_listing] after=[$after_listing]"
    fi
}

t7_happy_path_full_scaffold() {
    local s expected_gitignore project_dir stub_log
    s="$(make_sandbox)"
    expected_gitignore="$s/expected.gitignore"
    cat > "$expected_gitignore" <<'EOF'
# AI assistants
.ai-work/
.ai-state/*.lock
.ai-state/**/*.lock
.ai-state/*.backup.json
.ai-state/observations.jsonl.1
.claude/settings.local.json
.claude/worktrees/
.env
.env.*
.env.local
tmp/
EOF
    run_script "$s" test-app "$s/target"
    project_dir="$s/target/test-app"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T7: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    [ -d "$project_dir/.git" ] || { fail "T7: missing .git/ in $project_dir"; return; }
    [ -d "$project_dir/.claude" ] || { fail "T7: missing .claude/ in $project_dir"; return; }
    if [ -n "$(ls -A "$project_dir/.claude")" ]; then
        fail "T7: .claude/ should be empty"; return
    fi
    if ! cmp -s "$expected_gitignore" "$project_dir/.gitignore"; then
        fail "T7: .gitignore byte-mismatch (expected canonical content)"; return
    fi
    if ! grep -qE '(Scaffold|Launching|Claude)' "$LAST_OUT"; then
        fail "T7: pre-flight stdout line missing; stdout=$(cat "$LAST_OUT")"; return
    fi
    [ -f "$stub_log" ] || { fail "T7: claude stub never invoked (no $stub_log)"; return; }
    if ! grep -q "cwd=$project_dir" "$stub_log"; then
        fail "T7: claude stub not invoked from inside $project_dir; log=$(cat "$stub_log")"; return
    fi
    # The bash layer embeds the slash command body as the seed prompt (CLI does
    # not dispatch /-prefixed positional args as slash commands). Verify both the
    # permission flags and that the seed prompt mentions the command — whether
    # as the literal `/new-project` fallback or as a substring inside the
    # embedded markdown body.
    if ! grep -q 'arg=--permission-mode' "$stub_log" || \
       ! grep -q 'arg=acceptEdits' "$stub_log" || \
       ! grep -qF 'new-project' "$stub_log"; then
        fail "T7: claude stub args missing expected flags or seed prompt; log=$(cat "$stub_log")"; return
    fi
    pass "T7: happy path scaffolds .git/.claude/.gitignore and execs claude correctly"
}

# --hackathon is opt-in: the flag must produce a '# Hackathon mode: true'
# trailer in the seed prompt so the seeded /new-project can detect it. The
# claude stub captures every arg (including the multi-line seed prompt) into
# stub.log, so the trailer is grep-able there.
t8_hackathon_flag_sets_trailer_true() {
    local s stub_log
    s="$(make_sandbox)"
    run_script "$s" hk-app "$s/target" --hackathon
    stub_log="$s/stub.log"
    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T8: --hackathon expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Hackathon mode: true' "$stub_log"; then
        pass "T8: --hackathon emits '# Hackathon mode: true' trailer in the seed prompt"
    else
        fail "T8: expected '# Hackathon mode: true' in seed prompt; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

# The default run (no --hackathon) must produce '# Hackathon mode: false' --
# hackathon is opt-in, so a regular project is never silently in hackathon mode.
t9_no_hackathon_flag_sets_trailer_false() {
    local s stub_log
    s="$(make_sandbox)"
    run_script "$s" plain-app "$s/target"
    stub_log="$s/stub.log"
    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T9: default run expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Hackathon mode: false' "$stub_log"; then
        pass "T9: default run emits '# Hackathon mode: false' trailer (hackathon is opt-in)"
    else
        fail "T9: expected '# Hackathon mode: false' in seed prompt; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

# PRAXION_NEW_PROJECT_HACKATHON=1 is the env-var equivalent of the --hackathon
# flag (mirrors PRAXION_NEW_PROJECT_NO_AAC) -- with no flag passed, it must also
# produce the '# Hackathon mode: true' trailer. The env var is unset right after
# the run so it never leaks into later tests.
t10_hackathon_env_var_sets_trailer_true() {
    local s stub_log
    s="$(make_sandbox)"
    export PRAXION_NEW_PROJECT_HACKATHON=1
    run_script "$s" env-app "$s/target"
    unset PRAXION_NEW_PROJECT_HACKATHON
    stub_log="$s/stub.log"
    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T10: PRAXION_NEW_PROJECT_HACKATHON=1 expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Hackathon mode: true' "$stub_log"; then
        pass "T10: PRAXION_NEW_PROJECT_HACKATHON=1 emits '# Hackathon mode: true' trailer (no flag)"
    else
        fail "T10: expected '# Hackathon mode: true' in seed prompt; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

main() {
    if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
        printf 'SETUP FAIL: script under test not found at %s\n' "$SCRIPT_UNDER_TEST" >&2
        exit 1
    fi
    t1_no_args_usage_exit_2
    t2_invalid_name_exit_2_no_mkdir
    t3_missing_claude_exit_3
    t4_missing_plugin_exit_4
    t5_missing_git_exit_5
    t6_target_exists_nonempty_exit_6
    t7_happy_path_full_scaffold
    t8_hackathon_flag_sets_trailer_true
    t9_no_hackathon_flag_sets_trailer_false
    t10_hackathon_env_var_sets_trailer_true

    printf '\n--- summary: %d passed, %d failed ---\n' "$PASS_COUNT" "$FAIL_COUNT"
    if [ "$FAIL_COUNT" -eq 0 ]; then
        printf '=== T1–T10 passed ===\n'
        exit 0
    fi
    printf '=== %d of 10 failed ===\n' "$FAIL_COUNT" >&2
    exit 1
}

main "$@"
