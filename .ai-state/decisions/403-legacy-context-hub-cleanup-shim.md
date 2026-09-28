---
id: dec-403
draft_id: dec-draft-218ce4c9
title: One-release, consent-gated legacy context-hub cleanup shim in each installer
status: accepted
category: behavioral
date: 2026-09-24
summary: "Each installer detects only the context-hub (chub) state that its own past code wrote. install.sh handles the global @aisuite/chub npm package and ~/.chub/, install_claude.sh handles mcpServers.chub/context-hub in ~/.claude.json and the legacy ~/.claude/settings.json, and install_cursor.sh handles the chub key in mcp.json. A closed report|offer mode drives it. --check and --dry-run report without writing and never flip health. Install, --complete-install, --uninstall and --complete-uninstall offer per-remnant removal on a TTY only, ~/.chub/ defaults to keep, non-TTY runs remove nothing and print manual commands, and a clean machine prints nothing. The shim carries the LEGACY-CHUB-CLEANUP marker and a tech-debt row for bounded removal. The SessionStart auto-complete hook never calls it."
tags: [context-hub, installer, legacy-cleanup, consent, uninstall, tech-debt, transitional]
made_by: agent
agent_type: systems-architect
branch: worktree-remove-chub
pipeline_tier: standard
affected_files:
  - install.sh
  - install_claude.sh
  - install_cursor.sh
  - commands/praxion-complete-install.md
  - commands/praxion-complete-uninstall.md
affected_reqs: [REQ-06, REQ-07, REQ-08, REQ-09, REQ-10]
dissent: "An ~80-line transitional shim across three installers adds branching to already-long scripts for a remnant that is inert once the upstream stops working; a CHANGELOG paragraph with three manual commands would reach the same users at zero code cost."
---

## Context

dec-404 removes context-hub from Praxion. Earlier Praxion installers wrote state outside the repo:

- a global npm package (`@aisuite/chub`)
- `~/.chub/config.yaml`
- `mcpServers.chub` in `~/.claude.json`, migrated from a legacy `~/.claude/settings.json` entry
- a `chub` server in Cursor's `mcp.json`

`~/.chub/` can also hold data that belongs to the user, not Praxion: annotations, private doc sources, and a client id. Today `--uninstall` removes the MCP entries silently. `--complete-uninstall` misroutes through `install.sh`'s shared *install* branch.

## Decision

Each installer gains one function, marked `LEGACY-CHUB-CLEANUP`, that handles only the remnant kinds its own past code wrote. The function takes a closed `report | offer` mode:

- **`report`** (used by `--check` and `--dry-run`): one warning per remnant, plus the manual removal command. It makes no writes, shows no prompts, and leaves the health result unchanged.
- **`offer`** (used by install, `--complete-install`, `--uninstall` and `--complete-uninstall`):
  - Nothing present: it prints nothing.
  - On a TTY: it lists the remnants and asks once per kind. The default is Remove, except for `~/.chub/`, which defaults to **Keep**. That prompt is offered before the npm package, so the `chub annotate --list` export tip still works.
  - On a non-TTY: it removes nothing and prints the manual commands.
- **Cursor**: `mcp.json` is already rewritten wholesale from the template (pre-existing ownership), so the install path only announces the dropped entry, and `--check` warns.

The SessionStart auto-complete hook never invokes the shim.

`install.sh` gains an explicit `--complete-uninstall` branch (`delegate`, then cleanup) so that uninstalling no longer runs the shared installers.

**Lifetime.** Remove the shim once both hold:

- at least one further minor release has shipped after the removal release
- 90 days have passed since the removal release

This is tracked by a tech-debt row whose `dedup_key` names the marker. Code comments carry the marker only, never ADR ids: finalize does not rewrite code, so an id cited there would dangle.

## Considered Options

### Option 1: Remove everything and document manual cleanup in the CHANGELOG/release notes

- (+) No code cost.
- (−) Users who never read release notes keep a dangling MCP server, which fails once the upstream breaks, plus a global package they may not know Praxion installed.
- (−) Praxion wrote this state and should offer to reverse it.

### Option 2: Silently remove remnants on the next install

- (+) Zero friction.
- (−) It can destroy user annotations and private sources in `~/.chub/`.
- (−) It uninstalls a global package that the user may use independently.
- (−) It violates consent for writes outside the repo.

### Option 3: Consent-gated shim, one function per installer, TTY-gated (chosen)

- (+) It reaches every user on their next routine installer run.
- (+) There is no silent data loss, and automated runs stay non-mutating.
- (−) It adds about 80 lines of transitional Bash that must actually be deleted later.

## Consequences

**Positive**
- Existing installs converge on a chub-free state with explicit consent.
- The `--complete-uninstall` misroute is fixed.
- `--uninstall` stops silently editing `~/.claude.json`.

**Negative**
- `--uninstall` becomes interactive when remnants exist; a non-TTY run degrades to printing the commands.
- The removal commitment depends on the tech-debt row being acted on.
- Cursor users' `mcp.json` was already clobbered on reinstall (pre-existing); this decision neither worsens nor fixes that.
