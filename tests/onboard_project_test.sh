#!/usr/bin/env bash
# Tests for scripts/onboard-project -- the unified onboarding entry point.
#
# Rewritten from tests/new_project_test.sh (kept as-is until the atomic cut
# deletes it) for the collapsed one-script contract per
# INTERFACE_DESIGN.md §2 and SYSTEMS_PLAN.md §Detection Algorithm.
#
# RED-first (BDD/TDD): scripts/onboard-project does not exist yet as of this
# test's authoring -- every test below is expected to fail with a
# script-not-found SETUP FAIL until the paired implementer step lands it.
# This test is not wired into CI (bash, not pytest) so its RED status is
# recorded manually in TEST_RESULTS.md rather than gated by a marker.
#
# Validates the bash-observable behaviors of the unified entry point:
# T1: missing claude -> exit 3
# T2: missing praxion plugin record -> exit 4
# T3: missing git -> exit 5
# T4: invalid project name (new mode) -> exit 2, no mkdir
# T5: target exists & non-empty (new mode) -> exit 6, no mutation
# T6: empty target -> detects state=empty, mode=new, scaffolds + 4-line trailer
# T7: git repo with no Praxion state -> detects state=git-no-praxion, mode=existing
# T8: .ai-state/ non-empty, no stamp -> detects state=partially-managed
# T9: .praxion-onboard.json present, mode != hackathon -> detects state=fully-managed
# T10: .praxion-onboard.json present, mode == hackathon -> detects state=hackathon-managed
# T11: source files present, no .git/ -> detects state=code-no-git
# T12 (REQUIRED canary): the bash script's detected-state name set equals
#      references/detection.md's enumerated 6-state set -- SYSTEMS_PLAN.md
#      §Detection Algorithm requires these to never drift apart.
# T13 (REQUIRED canary, td-130/dec-344): the scaffolded
#      .claude/settings.json carries the permissions.allow baseline, and its
#      value stays in agreement with phases-core.md § Phase 5's canonical
#      copy -- TD130_MECHANISM_SPEC.md Edit 6's naming ("t12_...") predates
#      T12 above already owning that ordinal; renumbered here, content
#      unchanged.
# T14: the greenfield guard still fires (exit 7) on a re-invocation against a
#      seeded scaffold (settings.json present, nothing else) -- the
#      regression edit 2 of TD130_MECHANISM_SPEC.md exists to prevent, plus
#      the pre-seed (empty .claude/) backward-tolerance case.
#
# Run from repo root:
#   bash tests/onboard_project_test.sh
#
# Exits 0 on full pass, 1 on any failure. Portable to macOS (BSD) + Linux.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/scripts/onboard-project"
DETECTION_DOC="$REPO_ROOT/skills/onboard-project/references/detection.md"
PHASES_CORE_DOC="$REPO_ROOT/skills/onboard-project/references/phases-core.md"

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
# real CLI would treat as unknown options.
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

# Run the script from within a target directory (existing-project entry: no
# positional project name -- "onboard the directory I'm standing in").
run_script_in() {
    local sandbox="$1" cwd="$2"; shift 2
    LAST_OUT="$sandbox/stdout"
    LAST_ERR="$sandbox/stderr"
    (
        cd "$cwd" || exit 99
        HOME="$sandbox/home" PATH="$sandbox/bin:$ESSENTIALS" \
            "$BASH_BIN" "$SCRIPT_UNDER_TEST" "$@" \
            >"$LAST_OUT" 2>"$LAST_ERR"
    )
    LAST_EXIT=$?
}

t1_missing_claude_exit_3() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/bin/claude"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 3 ] && grep -qi 'claude' "$LAST_ERR"; then
        pass "T1: missing claude exits 3 with claude-mentioning stderr"
    else
        fail "T1: expected exit=3 + 'claude' in stderr; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t2_missing_plugin_exit_4() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/home/.claude/plugins/installed_plugins.json"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 4 ]; then
        pass "T2: missing praxion plugin record exits 4"
    else
        fail "T2: expected exit=4; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t3_missing_git_exit_5() {
    local s
    s="$(make_sandbox)"
    rm -f "$s/bin/git"
    run_script "$s" my-app "$s/target"
    if [ "$LAST_EXIT" -eq 5 ]; then
        pass "T3: missing git exits 5"
    else
        fail "T3: expected exit=5; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
    fi
}

t4_invalid_name_exit_2_no_mkdir() {
    local s before_count after_count name
    s="$(make_sandbox)"
    before_count="$(find "$s/target" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
    for name in '../x' 'x y' '.hidden'; do
        run_script "$s" "$name" "$s/target"
        if [ "$LAST_EXIT" -ne 2 ]; then
            fail "T4: name '$name' expected exit=2; got exit=$LAST_EXIT"
            return
        fi
    done
    after_count="$(find "$s/target" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
    if [ "$before_count" = "$after_count" ]; then
        pass "T4: invalid names ('../x','x y','.hidden') exit 2 with no mkdir"
    else
        fail "T4: target dir mutated (before=$before_count after=$after_count)"
    fi
}

t5_target_exists_nonempty_exit_6() {
    local s before_listing after_listing
    s="$(make_sandbox)"
    mkdir -p "$s/target/my-app"
    : > "$s/target/my-app/preexisting.txt"
    before_listing="$(ls -1 "$s/target/my-app")"
    run_script "$s" my-app "$s/target"
    after_listing="$(ls -1 "$s/target/my-app")"
    if [ "$LAST_EXIT" -eq 6 ] && [ "$before_listing" = "$after_listing" ]; then
        pass "T5: non-empty target exits 6 with no mutation"
    else
        fail "T5: expected exit=6 + identical listing; got exit=$LAST_EXIT, before=[$before_listing] after=[$after_listing]"
    fi
}

t6_empty_target_detects_new_mode_with_4line_trailer() {
    local s project_dir stub_log
    s="$(make_sandbox)"
    run_script "$s" test-app "$s/target"
    project_dir="$s/target/test-app"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T6: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    [ -d "$project_dir/.git" ] || { fail "T6: missing .git/ in $project_dir"; return; }
    [ -d "$project_dir/.claude" ] || { fail "T6: missing .claude/ in $project_dir"; return; }
    [ -f "$project_dir/.claude/settings.json" ] || { fail "T6: missing .claude/settings.json in $project_dir"; return; }
    [ -f "$stub_log" ] || { fail "T6: claude stub never invoked (no $stub_log)"; return; }
    if ! grep -q "cwd=$project_dir" "$stub_log"; then
        fail "T6: claude stub not invoked from inside $project_dir; log=$(cat "$stub_log")"; return
    fi
    if ! grep -q '# Mode: new' "$stub_log" \
        || ! grep -q '# Detected state: empty' "$stub_log" \
        || ! grep -q '# Capabilities:' "$stub_log" \
        || ! grep -q '# Brief:' "$stub_log"; then
        fail "T6: seed-prompt trailer missing one of the required 4 lines (Mode/Detected state/Capabilities/Brief); log=$(cat "$stub_log")"
        return
    fi
    pass "T6: empty target scaffolds + detects state=empty/mode=new + emits 4-line trailer"
}

t7_git_no_praxion_detects_existing_mode() {
    local s dir stub_log
    s="$(make_sandbox)"
    dir="$s/target/plain-repo"
    mkdir -p "$dir"
    (cd "$dir" && git init -q)
    run_script_in "$s" "$dir"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T7: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] \
        && grep -q '# Mode: existing' "$stub_log" \
        && grep -q '# Detected state: git-no-praxion' "$stub_log"; then
        pass "T7: bare git repo detects state=git-no-praxion, mode=existing"
    else
        fail "T7: expected state=git-no-praxion/mode=existing trailer; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

t8_ai_state_nonempty_no_stamp_detects_partially_managed() {
    local s dir stub_log
    s="$(make_sandbox)"
    dir="$s/target/partial-repo"
    mkdir -p "$dir/.ai-state"
    (cd "$dir" && git init -q)
    : > "$dir/.ai-state/DESIGN.md"
    run_script_in "$s" "$dir"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T8: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Detected state: partially-managed' "$stub_log"; then
        pass "T8: non-empty .ai-state/ with no stamp detects state=partially-managed"
    else
        fail "T8: expected state=partially-managed trailer; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

t9_stamp_present_full_mode_detects_fully_managed() {
    local s dir stub_log
    s="$(make_sandbox)"
    dir="$s/target/managed-repo"
    mkdir -p "$dir/.ai-state"
    (cd "$dir" && git init -q)
    printf '{"onboarded_with_version": "test", "mode": "full"}\n' > "$dir/.ai-state/.praxion-onboard.json"
    run_script_in "$s" "$dir"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T9: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Detected state: fully-managed' "$stub_log"; then
        pass "T9: stamp with mode=full detects state=fully-managed"
    else
        fail "T9: expected state=fully-managed trailer; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

t10_stamp_present_hackathon_mode_detects_hackathon_managed() {
    local s dir stub_log
    s="$(make_sandbox)"
    dir="$s/target/hackathon-repo"
    mkdir -p "$dir/.ai-state"
    (cd "$dir" && git init -q)
    printf '{"onboarded_with_version": "test", "mode": "hackathon"}\n' > "$dir/.ai-state/.praxion-onboard.json"
    run_script_in "$s" "$dir"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T10: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Detected state: hackathon-managed' "$stub_log"; then
        pass "T10: stamp with mode=hackathon detects state=hackathon-managed"
    else
        fail "T10: expected state=hackathon-managed trailer; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

t11_source_no_git_detects_code_no_git() {
    local s dir stub_log
    s="$(make_sandbox)"
    dir="$s/target/code-only"
    mkdir -p "$dir"
    printf 'print("hi")\n' > "$dir/main.py"
    run_script_in "$s" "$dir"
    stub_log="$s/stub.log"

    if [ "$LAST_EXIT" -ne 0 ]; then
        fail "T11: expected exit=0; got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    if [ -f "$stub_log" ] && grep -q '# Detected state: code-no-git' "$stub_log"; then
        pass "T11: source files with no .git/ detects state=code-no-git"
    else
        fail "T11: expected state=code-no-git trailer; log=$(cat "$stub_log" 2>/dev/null)"
    fi
}

# REQUIRED canary (risk-table item #3): the bash script's detected-state name
# set must equal references/detection.md's enumerated 6-state set. A silent
# drift here means the launcher's classification (passed in the seed trailer)
# and Phase 0's re-detection can disagree on a state name that exists on one
# side and not the other -- the exact failure the bash/skill split depends on
# never happening (SYSTEMS_PLAN.md §Detection Algorithm).
t12_bash_state_names_agree_with_detection_md() {
    local expected_states="code-no-git empty fully-managed git-no-praxion hackathon-managed partially-managed"

    if [ ! -f "$DETECTION_DOC" ]; then
        fail "T12: $DETECTION_DOC not found -- cannot verify state-name agreement"
        return
    fi
    if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
        fail "T12: $SCRIPT_UNDER_TEST not found -- cannot verify state-name agreement"
        return
    fi

    local doc_states script_states missing_in_script missing_in_doc
    doc_states="$(grep -oE '\`(empty|hackathon-managed|fully-managed|partially-managed|git-no-praxion|code-no-git)\`' "$DETECTION_DOC" \
        | tr -d '\`' | sort -u | tr '\n' ' ' | sed 's/ $//')"
    script_states="$(grep -oE '(empty|hackathon-managed|fully-managed|partially-managed|git-no-praxion|code-no-git)' "$SCRIPT_UNDER_TEST" \
        | sort -u | tr '\n' ' ' | sed 's/ $//')"

    missing_in_script=""
    for state in $expected_states; do
        case " $script_states " in
            *" $state "*) ;;
            *) missing_in_script="$missing_in_script $state" ;;
        esac
    done
    missing_in_doc=""
    for state in $expected_states; do
        case " $doc_states " in
            *" $state "*) ;;
            *) missing_in_doc="$missing_in_doc $state" ;;
        esac
    done

    if [ -z "$missing_in_script" ] && [ -z "$missing_in_doc" ]; then
        pass "T12: bash script's state-name set agrees with detection.md's enumerated set"
    else
        fail "T12: state-name disagreement -- missing in script:[$missing_in_script] missing in detection.md:[$missing_in_doc]"
    fi
}

# REQUIRED canary (td-130 / dec-344): the bash-scaffolded
# .claude/settings.json's permissions.allow baseline must agree with the
# canonical value in phases-core.md § Phase 5, sub-step 5b -- a change to
# either site without the other must fail loudly.
t13_scaffold_seeds_permissions_baseline() {
    local s project_dir

    if [ ! -f "$PHASES_CORE_DOC" ]; then
        fail "T13: $PHASES_CORE_DOC not found -- cannot verify permissions-baseline agreement"
        return
    fi

    s="$(make_sandbox)"
    run_script "$s" test-app "$s/target"
    project_dir="$s/target/test-app"

    if [ ! -f "$project_dir/.claude/settings.json" ]; then
        fail "T13: $project_dir/.claude/settings.json was not scaffolded"
        return
    fi

    if command -v jq >/dev/null 2>&1; then
        if ! jq -e '.permissions.allow' "$project_dir/.claude/settings.json" >/dev/null 2>&1; then
            fail "T13: $project_dir/.claude/settings.json does not parse as JSON with .permissions.allow"
            return
        fi
        if ! jq -e '.permissions.allow | index("Write(.ai-work/**)")' "$project_dir/.claude/settings.json" >/dev/null 2>&1; then
            fail "T13: .permissions.allow is missing the required entry Write(.ai-work/**)"
            return
        fi
    fi

    # Grep-based agreement half runs unconditionally (no jq dependency).
    if ! grep -qF 'Write(.ai-work/**)' "$PHASES_CORE_DOC"; then
        fail "T13: phases-core.md's § Phase 5 no longer states the canonical Write(.ai-work/**) value"
        return
    fi
    if ! grep -qF 'Write(.ai-work/**)' "$project_dir/.claude/settings.json"; then
        fail "T13: scaffolded settings.json does not carry the canonical Write(.ai-work/**) value"
        return
    fi

    pass "T13: scaffold seeds the permissions.allow baseline in agreement with phases-core.md"
}

# REQUIRED canary (td-130 / dec-344): the greenfield guard must
# still fire on a re-invocation against a seeded scaffold -- this is the
# regression edit 2 of TD130_MECHANISM_SPEC.md exists to prevent.
t14_greenfield_guard_fires_on_seeded_scaffold() {
    local s project_dir

    s="$(make_sandbox)"
    run_script "$s" test-app "$s/target"
    project_dir="$s/target/test-app"

    if [ ! -d "$project_dir/.claude" ]; then
        fail "T14: setup: expected $project_dir/.claude to exist after scaffold"
        return
    fi

    run_script_in "$s" "$project_dir"
    if [ "$LAST_EXIT" -ne 7 ]; then
        fail "T14: seeded-scaffold re-invocation expected exit=7 (EXIT_REFUSED); got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    pass "T14: greenfield guard fires (exit 7) on a re-invocation against a seeded scaffold"

    # Backward-tolerance case: a pre-seed scaffold (empty .claude/) also matches.
    rm -f "$project_dir/.claude/settings.json"
    run_script_in "$s" "$project_dir"
    if [ "$LAST_EXIT" -ne 7 ]; then
        fail "T14: pre-seed (empty .claude/) re-invocation expected exit=7 (EXIT_REFUSED); got exit=$LAST_EXIT, stderr=$(cat "$LAST_ERR")"
        return
    fi
    pass "T14: greenfield guard remains backward-tolerant of a pre-seed empty .claude/"
}

main() {
    if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
        printf 'SETUP FAIL: script under test not found at %s\n' "$SCRIPT_UNDER_TEST" >&2
        printf 'This is expected RED-first, pre-implementation: scripts/onboard-project has not landed yet.\n' >&2
        exit 1
    fi
    t1_missing_claude_exit_3
    t2_missing_plugin_exit_4
    t3_missing_git_exit_5
    t4_invalid_name_exit_2_no_mkdir
    t5_target_exists_nonempty_exit_6
    t6_empty_target_detects_new_mode_with_4line_trailer
    t7_git_no_praxion_detects_existing_mode
    t8_ai_state_nonempty_no_stamp_detects_partially_managed
    t9_stamp_present_full_mode_detects_fully_managed
    t10_stamp_present_hackathon_mode_detects_hackathon_managed
    t11_source_no_git_detects_code_no_git
    t12_bash_state_names_agree_with_detection_md
    t13_scaffold_seeds_permissions_baseline
    t14_greenfield_guard_fires_on_seeded_scaffold

    printf '\n--- summary: %d passed, %d failed ---\n' "$PASS_COUNT" "$FAIL_COUNT"
    if [ "$FAIL_COUNT" -eq 0 ]; then
        printf '=== T1-T14 passed ===\n'
        exit 0
    fi
    printf '=== %d of 14 failed ===\n' "$FAIL_COUNT" >&2
    exit 1
}

main "$@"
