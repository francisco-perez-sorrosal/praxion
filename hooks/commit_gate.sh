#!/bin/sh
# Fast-path gate for PreToolUse hooks that only apply to git commit commands.
# Reads stdin and starts the Python hook only for a command that may record a
# commit, deciding as much as it can before any interpreter starts (a Python
# start costs 20 to 500 ms, and the gate runs on every Bash call):
#
#   1. two `case`s over the whole payload, one word each: no `commit`, or no
#      `git`, anywhere, exit 0 (each a linear scan; macOS /bin/sh backtracks
#      quadratically over the one two-word pattern `*git*commit*`);
#   2. one sed cuts out the command field's value: no `commit` in it (the words
#      were only in the description or a path), exit 0;
#   3. a `case` reads a value that is plainly one `git <read-only built-in>`
#      command (`git log --grep=commit`), exit 0;
#   4. the stdlib reader `_commit_command.py` reads the command as a shell
#      would split it: `not-a-commit` (`git -C . log --grep=commit`), exit 0;
#   5. anything else starts the hook: a commit, a form the reader cannot read
#      with certainty, or a reader that failed for any reason.
#
# Each skip is decided on the command alone, and every doubt runs the hook: a
# real commit no checker judged is the worse failure.
#
# Usage: commit_gate.sh [--blocking] <python-hook-script>
#
# --blocking translates a findings exit (1) into Claude Code's PreToolUse block
# code (2), and is the adapter between two conventions that genuinely disagree.
# Praxion's check_* scripts follow the POSIX-natural "0 clean / 1 findings /
# 2 script error"; PreToolUse treats *only* exit 2 as "block this tool call",
# and every other non-zero as a non-blocking error the model never sees. Without
# a translation, a gate can detect a violation perfectly and have its verdict
# silently discarded -- exactly what check_id_citation_discipline.py did while
# the rule it enforces called it "the primary enforcement layer".
#
# The translation lives here, in the adapter, rather than in each script: the
# scripts are also run from CI, from git hooks, and by hand, where 1-on-findings
# is the correct and expected contract. Only this wrapper knows it is speaking
# to PreToolUse.
#
# Reminders are deliberately invoked WITHOUT --blocking. A reminder that crashes
# must not block a commit, and a Python traceback exits 1 -- the same code a
# gate uses for findings, which is precisely why this is opt-in per invocation
# rather than applied to everything the wrapper runs.

set -e

# The gate leads its own replay of a checker's stdout findings with this hint:
# a refusal's stderr may be clipped, and the way out is the part the session
# cannot do without. A checker that exits 2 by itself has already streamed its
# own stderr before the gate prints anything, so the hint follows it there. A
# refused call is refused whole, and the check read the tree before the call
# began, so a fix made inside the refused call is not seen.
REFUSAL_HINT="commit gate: refused; no command of that call ran. The check judged the files as they stood before the call began, so a fix made in the same call is not seen. Fix the findings, then stage in one call and commit in a separate call."

# How many lines of a checker's findings a refusal replays. Enough for a dozen
# multi-line findings, small enough that the hint, the findings and the pointer
# to the rest stay in one readable block however much the checker printed.
FINDINGS_LINE_CAP=40

# Write the refusal on stderr, the stream a refused session reads: the way out
# first, then at most FINDINGS_LINE_CAP lines of the findings in $out, then how
# to see the rest. $1 is the checker, named so it can be run by hand.
refuse() {
    {
        printf '%s\n' "$REFUSAL_HINT"
        if [ -n "$out" ]; then
            printf '%s' "$out" | sed -n "1,${FINDINGS_LINE_CAP}p"
            total=$(printf '%s' "$out" | sed -n '$=')
            if [ "$total" -gt "$FINDINGS_LINE_CAP" ]; then
                printf 'commit gate: %s more line(s) not shown; to see them all, run the check by hand, scoped to the staged files where it takes --files (a bare run can scan more than the commit): python3 %s\n' \
                    "$((total - FINDINGS_LINE_CAP))" "$1"
            fi
        fi
    } >&2 || :
}

# Whether $1, the command value as stage 2 cut it, is plainly one simple command
# `git <built-in> ...` that the reader would read `not-a-commit`: no backslash
# (stage 2 marks a value it dropped escapes from with one), no character that
# could end the simple command or change its words, `git` and one space first,
# and no later word the reader would follow as another invocation (`git`, or a
# shell's name: each of them holds `sh`). Builtins only, so it costs no process.
# When in doubt it answers no and the reader decides.
is_plainly_read_only_git() {
    case "$1" in
        *[\\\;\&\|\(\)\<\>\`\$\'\"\#]*) return 1 ;;
        '=git '*) ;;
        *) return 1 ;;
    esac
    words=${1#=git }
    subcommand=${words%% *}
    case "${words#"$subcommand"}" in
        *git* | *sh*) return 1 ;;
    esac
    # A subset of GIT_BUILTINS in _commit_command.py; test_commit_command.py holds it there.
    case "$subcommand" in
        log | show | diff | status | branch | blame | grep | rev-parse | rev-list | ls-files) return 0 ;;
    esac
    return 1
}

blocking=0
if [ "$1" = "--blocking" ]; then
    blocking=1
    shift
fi

input=$(cat)

# Quick text checks over the whole payload, the only stage most calls reach. Their
# false positives (the words in the description, a path or a `git log --grep`)
# are what the later stages settle before the hook starts. `case`s, not a pipe
# into grep: a forked producer that dies under load (seen with dash) leaves grep
# reading nothing, and a real commit would pass unjudged. Two one-word patterns,
# not `*git*commit*`, which macOS /bin/sh matches in time quadratic in the
# payload (minutes for a megabyte of `git ` words); `commit` first, since most
# payloads that hold either word hold only `git`. Together they match the words
# in either order and on different lines, a superset of the old line-wise grep,
# so they only send more payloads on to the exact stages.
# The payload is forwarded with printf, never echo: /bin/sh on macOS is bash in
# POSIX mode, whose builtin echo interprets backslash escapes, so a command that
# contains `\|`, `\s` or `\n` (any grep pattern) arrives as invalid JSON and
# every Python hook's json.loads fails silently.
case "$input" in *commit*) ;; *) exit 0 ;; esac
case "$input" in *git*) ;; *) exit 0 ;; esac

# The command field's value, cut out exactly: the field's opening quote, then
# unescaped characters and whole escapes, then the closing quote. The first
# `"command":` is cut at a newline (no JSON text holds a raw one), and the `=`
# before the value tells an empty command from no field at all; no field, or
# a sed that failed, goes on. A value that holds a backslash gains one in front
# of its `=`, so stage 3 can tell; then every `\\` and every `\"` is dropped.
# Dropping can only join letters into the word, never part them, so it errs
# towards the reader; a `\u` escape could spell the word, so it goes on to the
# reader too. LC_ALL=C reads the payload as bytes, so no multibyte character
# can stop sed. No subshell beyond the pipe: this stage is paid again on the
# way to the reader.
command_value=$(printf '%s\n' "$input" | LC_ALL=C sed -n \
    -e 's/"command"[[:space:]]*:[[:space:]]*"\([^"\\]*\(\\.[^"\\]*\)*\)".*/\
=\1/' -e 's/\(\n\)=\(.*\\\)/\1\\=\2/' \
    -e 's/\\\\//g' -e 's/\\"//g' -e 's/^.*\n//p') || command_value=
case "$command_value" in
    '' | *commit* | *'\u'*) ;;
    *) exit 0 ;;
esac
if is_plainly_read_only_git "$command_value"; then
    exit 0
fi

# The reader's interpreter, in the finalize chain's order: a real interpreter
# starts the reader in 20 to 30 ms, a version-manager shim on PATH in 200 ms or
# more. `-I -S` keeps any of them to the standard library. A reader that cannot
# start, crashes or prints anything but `not-a-commit` leaves the hook to run.
if [ -n "${PRAXION_PYTHON:-}" ] && [ -x "$PRAXION_PYTHON" ]; then
    py=$PRAXION_PYTHON
elif [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -x "$CLAUDE_PROJECT_DIR/.venv/bin/python" ]; then
    py=$CLAUDE_PROJECT_DIR/.venv/bin/python
else
    py=python3
fi
verdict=$(printf '%s\n' "$input" | "$py" -I -S "${0%/*}/_commit_command.py" 2>/dev/null) || verdict=
if [ "$verdict" = not-a-commit ]; then
    exit 0
fi

# PRAXION_COMMIT_PAYLOAD tells a payload-aware checker that stdin carries a
# hook payload deterministically, rather than sniffing stdin readiness with
# a timed probe that can lose the race under load (a false "no payload" then
# runs a whole-repo scan and blocks the commit). Harmless to checkers that
# ignore it. The `printf | python3` pipe always reaches EOF, so a blocking
# read is safe here.
#
# The checker's stdout is captured, not streamed: checkers print findings
# there (so a hand, pre-commit or CI run is unchanged), but on exit 2 the
# harness shows the session only stderr, so a refusal re-routes them. The
# capture ends in a sentinel and the checker's status, because a bare $(...)
# strips trailing newlines and a pass must replay stdout byte for byte. The
# substitution turns `set -e` off so the checker's non-zero status reaches
# the sentinel instead of ending the substitution early.
captured=$(set +e; printf '%s\n' "$input" | PRAXION_COMMIT_PAYLOAD=1 python3 "$1"; printf 'x%s' "$?")
rc=${captured##*x}
out=${captured%x*}
# From here on, a write to a closed or broken stream must not change the
# verdict: SIGPIPE would end the shell with another status, and a failed
# write under `set -e` would turn a block into a non-blocking error. So the
# signal is ignored and every write ends `|| :`. Set only after the checker
# ran, so it is not inherited by it.
trap '' PIPE
if [ "$blocking" -eq 1 ] && [ "$rc" -eq 1 ]; then
    rc=2
fi
if [ "$rc" -eq 2 ]; then
    refuse "$1"
else
    printf '%s' "$out" || :
fi
exit "$rc"
