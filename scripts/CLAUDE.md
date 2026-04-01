# Scripts

Utility and operational scripts for the Praxion ecosystem.

## Available Scripts

- `ccwt` — Claude Code Worktrees: opens a tmux session with one pane per git worktree, each running Claude Code
- `chronograph-ctl` — Development helper for the Task Chronograph MCP server (start/stop/restart/status/logs from source)
- `phoenix-ctl` — Manage the Phoenix observability daemon (install/start/stop/restart/status/uninstall via launchd)

## Conventions

- Shell scripts (bash), `set -euo pipefail` (except `ccwt` which uses `set -eo pipefail`)
- Each script is self-contained with usage documentation in header comments
- `chronograph-ctl` and `phoenix-ctl` are development/operations tools — in production, MCP servers run via plugin.json
