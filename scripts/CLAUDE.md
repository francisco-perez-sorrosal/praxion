# Scripts

Utility and operational scripts for the Praxion ecosystem.

## Available Scripts

- `ccwt` — Claude Code Worktrees: opens a tmux session with one pane per git worktree, each running Claude Code
- `chronograph-ctl` — Development helper for the Task Chronograph MCP server (start/stop/restart/status/logs from source)
- `phoenix-ctl` — Manage the Phoenix observability daemon (install/start/stop/restart/status/uninstall via launchd)
- `reconcile_ai_state.py` — Post-merge reconciliation for `.ai-state/` artifacts: semantic memory.json merge, observations.jsonl dedup, ADR renumbering, index regeneration. Called by `/merge-worktree`
- `regenerate_adr_index.py` — Regenerate `.ai-state/decisions/DECISIONS_INDEX.md` from ADR file frontmatter

## Conventions

- Shell scripts (bash), `set -euo pipefail` (except `ccwt` which uses `set -eo pipefail`)
- Each script is self-contained with usage documentation in header comments
- `chronograph-ctl` and `phoenix-ctl` are development/operations tools — in production, MCP servers run via plugin.json

## Installer Filter

`install_claude.sh` links scripts under `~/.local/bin/` only when they are `-f && -x` AND do not match `merge_driver_*` or `git-*-hook.sh`. User-facing tools must be executable (`chmod +x`); merge drivers and git hooks are invoked by git, not by PATH, so they are intentionally skipped. Orphaned symlinks (from renamed/removed scripts) are cleaned on upgrade by `clean_stale_symlinks`. See dec-042.
