#!/bin/sh
# Fast-path gate for PreToolUse hooks that only apply to git commit commands.
# Reads stdin, checks for "git commit" with grep (< 1ms), and only invokes
# the Python hook if the payload looks like a commit. Avoids ~200-500ms of
# Python startup overhead on every non-commit Bash call.
#
# Usage: commit_gate.sh <python-hook-script>

set -e

input=$(cat)

# Quick text check — the JSON payload contains "git commit" in the command field.
# False positives (rare) just run the Python hook unnecessarily — same as before.
if echo "$input" | grep -q 'git.*commit'; then
    echo "$input" | python3 "$1"
else
    exit 0
fi
