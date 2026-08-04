---
id: dec-128
title: Pipeline Dashboard process model — bash ctl + macOS launchd, not MCP-bound
status: accepted
category: architectural
date: 2026-05-07
summary: Streamlit dashboard runs as a standalone bash-managed daemon mirroring phoenix-ctl, not as an MCP server tied to Claude Code session lifecycle.
tags: [dashboard, streamlit, daemon, lifecycle, phoenix-ctl]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - scripts/praxion-dashboard
  - .claude-plugin/plugin.json
affected_reqs: [REQ-01, REQ-12]
---

## Context

Praxion's pipeline dashboard must be reachable while a project is being worked on, including across multiple Claude Code sessions, multiple worktrees, and even when no Claude Code session is open (the human inspecting the project asynchronously). The dashboard's core value proposition is "visual entry point at any time." This pulls against three existing lifecycle patterns in the repo:

1. MCP servers in `plugin.json` (`task-chronograph`, `memory`) — die when Claude Code exits.
2. Phoenix observability (`scripts/phoenix-ctl`) — long-running daemon managed by macOS launchd, lives independent of Claude Code.
3. Ad-hoc HTTP server (`metrics-viewer.html.tmpl` launched via `python -m http.server`) — no lifecycle management at all.

The dashboard cannot accept the MCP-bound lifecycle: a user closes their terminal, the Streamlit server dies, the dashboard URL goes 404. This is the wrong default. The dashboard must outlive Claude Code sessions.

## Decision

The dashboard uses a **standalone bash ctl script (`scripts/praxion-dashboard`) with macOS launchd plist persistence**, modeled exactly on `scripts/phoenix-ctl`. Subcommands: `install`, `start`, `stop`, `restart`, `status`, `uninstall`. The launcher is a thin Python wrapper invoked by ctl `start` that resolves the project root, derives the port, and `subprocess.run`s `streamlit run app.py`.

The slash command `/dashboard` in `commands/dashboard.md` shells to `praxion-dashboard start` via the Bash tool — same pattern as `/eval` and `/project-metrics`. The slash command is the convenient entry point; the ctl is the authoritative lifecycle surface.

## Considered Options

### Option A — Plugin-bundled MCP server (lifecycle tied to Claude Code)

**Pros**: Zero new install machinery; `plugin.json` already manages MCP servers; auto-start when Claude Code launches.

**Cons**: Server dies when Claude Code exits — wrong semantics for a dashboard that must persist. Claude Code is not the only consumer; the human-in-the-loop visiting the dashboard asynchronously is a primary use case. Multi-session ergonomics break (every session would race to start its own).

### Option B — Standalone bash ctl + launchd (chosen)

**Pros**: Proven pattern (phoenix-ctl precedent works in production); decouples dashboard lifecycle from Claude Code; user controls start/stop explicitly; idempotent `install` lets onboarding wire it once. Logs are persistent across sessions for debugging. `praxion-dashboard status` gives a deterministic answer.

**Cons**: Adds a new ctl script and a new launchd plist to Praxion's surface. macOS-only without explicit Linux work (see ADR draft on cross-platform). Users must remember to `start` if they want the daemon running.

### Option C — On-demand subprocess with no daemon (closest to current metrics viewer)

**Pros**: Simplest; nothing to install; just `streamlit run` from a slash command.

**Cons**: Each invocation starts fresh — slow first paint, no persistence of port, no obvious "is it running?" signal, port collisions when multiple sessions try to start. Loses every property that makes Phoenix usable as a daemon.

## Consequences

**Positive**: Lifecycle parity with Phoenix; multi-session and multi-worktree scenarios work because the daemon outlives any single Claude Code session; the `/dashboard` slash command becomes a convenient front door without owning lifecycle. The bash ctl is shell-only — no Python startup cost on `status`.

**Negative**: New `scripts/praxion-dashboard` to maintain alongside phoenix-ctl; mac-only without further work (deferred to ADR draft 3); first-time UX has an `install` step (mitigation: `/dashboard` slash command auto-runs `install` if `~/Library/LaunchAgents/com.praxion.dashboard.plist` is absent).

**Risks accepted**: Two daemons (Phoenix + Dashboard) on a developer machine — judged acceptable because both are observability tools and both are opt-in.
