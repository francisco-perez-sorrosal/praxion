---
description: "Fan out /resume-rework into all rework worktrees from REWORK_MANIFEST.md. Default mode is background (--bg); pass --terminals for visible windows."
allowed-tools: [Bash(scripts/dispatch-reworks:*)]
argument-hint: "[--bg | --terminals] [--dry-run]"
disable-model-invocation: true
---

## Help

```
/dispatch-reworks — fan out /resume-rework into all rework worktrees

USAGE
  /dispatch-reworks [options]

  Reads REWORK_MANIFEST.md (auto-discovered under the project root),
  then starts one /resume-rework session per row — either as headless
  background sessions (default) or in visible terminal windows.

MODES
  --bg (default)
    Headless background sessions via claude --bg.  Each session is named
    "rework: <name>".  Monitor with claude agents --cwd <project-root>,
    inspect logs with claude logs <id>, stop with claude stop <id>.
    Note: N sessions consume API quota ~N× faster; budget accordingly for N > 3.

  --terminals
    Opens one terminal window per worktree with /resume-rework pre-filled;
    press Enter in each window to start.  Requires the claude-cli:// URI
    handler — run claude interactively at least once to register it.

OPTIONS
  --bg                  Background sessions (default).
  --terminals           Visible terminal windows instead of background sessions.
  --dry-run             Print the dispatch plan; exit 0 without firing.
  --manifest <path>     Explicit path to REWORK_MANIFEST.md (skip auto-discovery).
  --help, -h            Show this help.

EXAMPLES
  # Preview the dispatch plan without firing
  /dispatch-reworks --dry-run

  # Default: fan out as background sessions
  /dispatch-reworks

  # Visible terminal windows instead
  /dispatch-reworks --terminals

EXIT CODES
  0   Success — sessions dispatched (or --dry-run completed cleanly).
  1   General failure.
  2   Misuse — bad flags or ambiguous manifest.
  3   REWORK_MANIFEST.md not found.  Run the verifier first or pass --manifest.
  4   Manifest has no rows.  A clean verifier run; nothing to dispatch.
  5   claude-cli:// handler not registered (--terminals only).
```

## Invocation

Run `scripts/dispatch-reworks $ARGUMENTS` via the Bash tool and surface the output directly to the user. The script's printed output is the user-facing artifact — do not summarize it.
