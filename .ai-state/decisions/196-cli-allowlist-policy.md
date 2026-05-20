---
id: dec-196
title: Obsidian CLI agent allowlist — enforced via .claude/settings.json tool-permission denies + prose policy in CLAUDE.md
status: accepted
category: behavioral
date: 2026-05-19
summary: Agents may invoke documented file/search/links/properties/tags/outline/base:query commands; `eval`, plugin lifecycle, theme:set, and `delete --permanent` are denied. Enforcement is mechanical via .claude/settings.json `tool_permissions` deny rules (primary); canonical CLAUDE.md prose block describes the policy so agents see it in-context (secondary). Decision amended at planner stage per user override at the architect→planner phase-transition checkpoint.
tags: [obsidian, security, allowlist, cli, agent-policy, shape-b, settings-json]
made_by: agent
agent_type: implementation-planner
branch: worktree-obsidian-shape-b-onboarding
pipeline_tier: standard
affected_files:
  - claude/canonical-blocks/obsidian-integration.md
  - commands/onboard-project.md
  - commands/new-project.md
  - commands/onboard-project-obsidian.md
  - docs/obsidian-shape-b.md
---

## Context

The Obsidian official CLI (shipped in Obsidian 1.12, Feb 2026) exposes ~115 commands across 26+ categories. Research findings (`RESEARCH_FINDINGS-cli.md` §2.8) identify `obsidian eval '<javascript>'` as the named security risk — it executes arbitrary JavaScript inside Obsidian's renderer process with full app access, equivalent to `child_process.exec` from a community plugin. Plugin-lifecycle commands (`plugin:install`, `plugin:enable`, `plugin:disable`, `plugin:uninstall`) expose the same OS-permission attack surface. `theme:set` and `theme:install` allow theme code to run with full app privileges. `delete --permanent` bypasses Obsidian's trash and is unrecoverable.

For v1 of Shape B, the user pre-decided that `obsidian eval` is denied in any agent-driveable allowlist. The remaining question is **which mechanism** enforces the allowlist: prose in CLAUDE.md (behavioral-contract-style discipline), `.claude/settings.json` permission deny rules (Claude Code's Bash tool can match against a deny pattern), a wrapper script that whitelists subcommands, or some combination.

Praxion already enforces several policies via prose-in-CLAUDE.md (the squash-merge ban, the ID-citation discipline, the canonical-block sync requirement), and these have proven adequate in practice — they're discoverable to agents (the rule is loaded at session start) and aligned with the behavioral contract's "Surface Assumptions" / "Stay Surgical" clauses. They're also lower-friction than tool-permission denylists, which can produce confusing failure modes when an agent's `Bash` call is silently denied with no explanation in-context.

The third option — a wrapper script — adds the most enforcement but the most friction; agents would have to learn `praxion-obsidian` is the right invocation and `obsidian` is denied, which is awkward.

## Decision

> **Amendment (implementation-planner, 2026-05-19):** The architect proposed Option 1 (prose-only, v1). At the architect→planner phase-transition checkpoint, the user explicitly overrode this to Option 2 (`.claude/settings.json` deny block) effective immediately. The Decision section below reflects the user-chosen path. Option 1 is preserved in Considered Options as historical record.

The allowlist is declared in plain prose inside `claude/canonical-blocks/obsidian-integration.md` (the `## Obsidian Integration` block that lands in every onboarded project's CLAUDE.md) AND enforced mechanically via a `tool_permissions` deny block in the project's `.claude/settings.json`. Both layers are required:

- **settings.json** is the load-bearing enforcement layer. Denied patterns use Claude Code's `Bash(obsidian eval*)`, `Bash(obsidian plugin:install*)`, `Bash(obsidian plugin:enable*)`, `Bash(obsidian plugin:disable*)`, `Bash(obsidian plugin:uninstall*)`, `Bash(obsidian theme:set*)`, `Bash(obsidian theme:install*)`, and `Bash(obsidian delete --permanent*)` deny rules (eight entries; verified glob form against the existing `Bash(<command>...)` convention in `~/.claude/settings.json`). These are written by Phase 8d (sub-step 8d.5b) of `/onboard-project` and `/onboard-project-obsidian` into the project's `.claude/settings.json`, merged non-destructively alongside existing keys.
- **CLAUDE.md prose block** explains *which* subcommands are denied and why — so agents hitting a denial see an in-context explanation rather than an opaque permission error. The prose is not the enforcement layer; the settings.json is.

The allowlist table reads:

**Allowed:**

| Category | Subcommands |
|---|---|
| File CRUD (non-destructive) | `read`, `create`, `append`, `prepend`, `move`, `rename` |
| File CRUD (trash, not permanent) | `delete` (with no `--permanent`) |
| Search and navigation | `search`, `search:context`, `backlinks`, `links`, `unresolved`, `orphans`, `deadends`, `outline`, `tags`, `tag`, `properties` |
| Structured queries | `base:query` |
| Notes and templates | `daily`, `daily:read`, `daily:append`, `template:read`, `template:insert`, `unique` |
| Read-only diagnostics | `publish:list`, `publish:status`, `sync:status`, `sync:history`, `sync:read` |

**Denied:**

| Category | Subcommands | Reason |
|---|---|---|
| Code execution | `eval` (any args) | Arbitrary JS in renderer = RCE risk |
| Plugin lifecycle | `plugin:install`, `plugin:enable`, `plugin:disable`, `plugin:uninstall` | OS-permission attack surface |
| Theme lifecycle | `theme:set`, `theme:install` | Theme code runs with app privileges |
| Destructive operations | `delete --permanent` | Bypasses trash; unrecoverable |
| Publish writes | `publish:add`, `publish:remove` | Out-of-scope for v1; git is canonical |
| Sync writes | (none enumerated — sync is operator-owned) | Git is canonical sync layer for Praxion artifacts |

v1.1 (out of scope for this PR): if any incident proves prose-only enforcement insufficient, add a `.claude/settings.json` deny block matching the denied subcommands. The block lands in Phase 5 of `/onboard-project` alongside the existing `PRAXION_DISABLE_*` toggles.

## Considered Options

### Option 1 — Prose-only allowlist in CLAUDE.md (architect's original choice; not chosen)

- **Pros:** Zero friction. Aligns with the four-behavior contract — agents read the policy and follow it. Discoverable (loaded at session start). Easy to update — edit one canonical block. Mirrors Praxion's existing prose-enforced policies (squash-merge ban, ID-citation discipline). No new tool-permission scheme.
- **Cons:** Determined misuse (or model error) is not blocked at the tool-permission layer. Architect registered this as a named risk. User override at the architect→planner seam rejected this as insufficient.

### Option 2 — `.claude/settings.json` deny block + prose description (chosen; user override)

- **Pros:** Hard enforcement at the tool-permission layer. Determined misuse is blocked, not just discouraged. The prose layer (also present) gives agents in-context explanation of *why* a denial fires, preventing confusing silent permission errors.
- **Cons:** Phase 8d adds a sub-step (8d.5b) that merges deny patterns into `.claude/settings.json`. Deny patterns must stay aligned with the prose policy. The pattern shape (`Bash(obsidian eval*)`) matches Claude Code's Bash tool-permission glob syntax for subcommand arguments — implementer verified the no-colon form against existing `~/.claude/settings.json` entries.

### Option 3 — Wrapper script (`praxion-obsidian`) — whitelist only

- **Pros:** Maximum enforcement; agents physically cannot invoke denied subcommands.
- **Cons:** Highest friction. Agents have to learn a non-standard invocation. Wrapper itself becomes a maintenance burden. Misaligns with the kepano-skills pattern (kepano's skills call `obsidian` directly, not a wrapper).

### Option 4 — No allowlist

- **Pros:** Zero work.
- **Cons:** Defeats the pre-decided constraint and the named security risk. Rejected.

## Consequences

**Positive:**

- Denied subcommands (`obsidian eval`, `plugin:install`, `plugin:enable`, `plugin:disable`, `theme:set`, `delete --permanent`) are blocked at the tool-permission layer — not just discouraged by prose. This is the strongest enforcement available in Claude Code without a wrapper script.
- The prose block in CLAUDE.md explains the policy in-context — agents see why a denial fires rather than an opaque error, preserving discoverability and debuggability.
- Easy to evolve — the deny list in settings.json and the prose list in CLAUDE.md can both be updated by editing `claude/canonical-blocks/obsidian-integration.md` plus the Phase 8d settings.json merge sub-step.
- The two-layer design (mechanical + prose) is self-reinforcing: agents that follow the prose will never trigger the mechanical block; the mechanical block catches the remainder.

**Negative:**

- Phase 8d gains a sub-step (8d.5b) to merge deny patterns into `.claude/settings.json` — adds ~10 LOC to the onboarding command and Phase 8d body.
- Deny pattern glob syntax must be verified against Claude Code's Bash tool-permission parser. If the syntax is wrong, the deny rules silently fail — implementer must smoke-test. (See implementer note in Slice 2.)
- The allowlist will drift if kepano-skills grows new subcommand categories — sentinel can add a coverage check later.

## Prior Decision

The architect's original choice (Option 1, prose-only) was proposed in the same ADR draft at systems-architect phase. The user overrode it at the architect→planner phase-transition checkpoint to Option 2 (settings.json-primary). This section records the override; finalize rewrites the id cross-references at merge-to-main.

## Prior Decision

No prior decision; this is a new policy area. References ADR fragment `dec-198` (Shape B default-on) and `dec-197` (kepano shipping mechanism) as the integration context that makes this allowlist necessary.
