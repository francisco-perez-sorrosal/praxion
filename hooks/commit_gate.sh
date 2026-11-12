#!/bin/sh
# Fast-path gate for PreToolUse hooks that only apply to git commit commands.
# Reads stdin, checks for "git commit" with grep (< 1ms), and only invokes
# the Python hook if the payload looks like a commit. Avoids ~200-500ms of
# Python startup overhead on every non-commit Bash call.
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

# Led with, not appended: a refusal's stderr may be clipped, and the way out is
# the part the session cannot do without. A refused call is refused whole, and
# the check read the tree before the call began, so a fix made inside the
# refused call is not seen.
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
                printf 'commit gate: %s more line(s) not shown; to see them all, run the check by hand: python3 %s\n' \
                    "$((total - FINDINGS_LINE_CAP))" "$1"
            fi
        fi
    } >&2 || :
}

blocking=0
if [ "$1" = "--blocking" ]; then
    blocking=1
    shift
fi

input=$(cat)

# Quick text check — the JSON payload contains "git commit" in the command field.
# False positives (rare) just run the Python hook unnecessarily — same as before.
# The payload is forwarded with printf, never echo: /bin/sh on macOS is bash in
# POSIX mode, whose builtin echo interprets backslash escapes, so a command that
# contains `\|`, `\s` or `\n` (any grep pattern) arrives as invalid JSON and
# every Python hook's json.loads fails silently -- td-188.
if printf '%s\n' "$input" | grep -q 'git.*commit'; then
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
else
    exit 0
fi
