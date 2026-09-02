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

blocking=0
if [ "$1" = "--blocking" ]; then
    blocking=1
    shift
fi

input=$(cat)

# Quick text check — the JSON payload contains "git commit" in the command field.
# False positives (rare) just run the Python hook unnecessarily — same as before.
if echo "$input" | grep -q 'git.*commit'; then
    rc=0
    # PRAXION_COMMIT_PAYLOAD tells a payload-aware checker that stdin carries a
    # hook payload deterministically, rather than sniffing stdin readiness with
    # a timed probe that can lose the race under load (a false "no payload" then
    # runs a whole-repo scan and blocks the commit). Harmless to checkers that
    # ignore it. The `echo | python3` pipe always reaches EOF, so a blocking
    # read is safe here.
    echo "$input" | PRAXION_COMMIT_PAYLOAD=1 python3 "$1" || rc=$?
    if [ "$blocking" -eq 1 ] && [ "$rc" -eq 1 ]; then
        exit 2
    fi
    exit "$rc"
else
    exit 0
fi
