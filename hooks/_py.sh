#!/bin/sh
# Resolve a non-shim python3 interpreter once per machine, then exec it with
# this script's own argv and stdin forwarded unmodified.
#
# Why: on machines where `python3` on PATH is a pyenv (or similar) shim, every
# hook invocation pays the shim's own dispatch cost on top of the real
# interpreter's startup -- and hooks.json invokes `python3` once per
# SessionStart hook, every session. The shim's target interpreter does not
# change within a machine's active pyenv version, so resolving it once and
# caching the result to a per-user tmp file amortizes that cost across every
# hook call instead of paying it on each one.
#
# Usage: _py.sh <script.py> [args...]   -- stdin, argv, and the child's exit
# code are all forwarded as-is.
#
# Override: set PRAXION_PYTHON=/path/to/python3 to skip resolution entirely
# (e.g. a project's settings.json `env` block pinning a specific interpreter).
# Takes precedence over both the cache and the PATH lookup.
#
# Cache: ${TMPDIR:-/tmp}/praxion-py-<uid> stores the resolved absolute path on
# one line. Re-resolved (cache overwritten) whenever the cached path no longer
# exists on disk -- the only staleness signal available without invoking the
# shim itself to ask again. A stale cache pointing at a *different* still-valid
# interpreter (e.g. after a pyenv global version change) is not detected -- an
# accepted trade-off for a same-machine, same-session cache.
#
# Resolution mirrors `sys.executable`, not `readlink`: pyenv shims are wrapper
# scripts, not symlinks, so following symlinks would still land on the shim.
# Asking the shim to report its own `sys.executable` is the one reliable way
# to name the interpreter underneath it, and this is the sole python process
# started per cache miss.

set -e

if [ -n "$PRAXION_PYTHON" ]; then
    exec "$PRAXION_PYTHON" "$@"
fi

cache_file="${TMPDIR:-/tmp}/praxion-py-$(id -u)"

resolved=""
if [ -f "$cache_file" ]; then
    resolved=$(cat "$cache_file" 2>/dev/null || true)
    if [ -n "$resolved" ] && [ ! -x "$resolved" ]; then
        resolved=""
    fi
fi

if [ -z "$resolved" ]; then
    shim=$(command -v python3 2>/dev/null || true)
    if [ -z "$shim" ]; then
        echo "_py.sh: python3 not found on PATH" >&2
        exit 127
    fi
    resolved=$("$shim" -c 'import sys; print(sys.executable)' 2>/dev/null || true)
    if [ -z "$resolved" ] || [ ! -x "$resolved" ]; then
        resolved="$shim"
    fi
    printf '%s\n' "$resolved" > "$cache_file" 2>/dev/null || true
fi

exec "$resolved" "$@"
