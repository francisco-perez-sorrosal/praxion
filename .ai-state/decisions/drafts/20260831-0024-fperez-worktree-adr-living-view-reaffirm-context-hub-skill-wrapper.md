---
id: dec-draft-b169b522
title: Skill wrapper remains the primary context-hub integration — re-affirmed against doc drift
status: re-affirmation
category: architectural
date: 2026-08-31
summary: The 2026-08-30 still-current audit challenged dec-001 because skill text asserts an MCP-primary posture; code inspection shows the decision holds — re-affirmed, with the skill's false installer claim fixed as a doc bug
tags: [context-hub, skills, integration, re-affirmation, audit]
made_by: agent
agent_type: orchestrator
branch: worktree-adr-living-view
pipeline_tier: lightweight
re_affirms: dec-001
affected_files: ["skills/external-api-docs/SKILL.md", ".claude-plugin/plugin.json"]
dissent: "If the ecosystem's MCP posture has genuinely shifted toward native tool integration, re-affirming a 2026-03 skill-wrapper decision may preserve an outdated integration style instead of prompting the re-evaluation the doc drift was symptomatically requesting."
---

## Context

The 2026-08-30 still-current audit (adr-read-path, 30-record sample) flagged dec-001 as a re-affirm candidate: `skills/external-api-docs/SKILL.md` described MCP tools as "preferred, native" and claimed "the Praxion installer configures the MCP server via `npx`" — asserting an MCP-primary posture that dec-001 rejected. This is exactly the challenge-and-re-examine trigger the re-affirmation protocol exists for.

## Decision

Re-affirm dec-001. Code is the ground truth and it agrees with the decision, not the doc: `.claude-plugin/plugin.json` registers no `chub` MCP server (only `task-chronograph` and `likec4`), and `install.sh` installs the CLI globally (`npm install -g @aisuite/chub`) and writes `~/.chub/config.yaml` — it configures no MCP server. The skill wrapper remains the primary integration: opt-in, zero context cost when not loaded, no hard runtime dependency in the plugin manifest.

The contradicting sentence in `skills/external-api-docs/SKILL.md` is a **doc bug**, fixed alongside this record (installer claim corrected to what `install.sh` actually does), not evidence the decision changed.

## Considered Options

### A — Re-affirm (chosen)
The decision's rationale (opt-in loading, no hard Node.js runtime dependency in `plugin.json`, consistency with the skill ecosystem) is intact and the code implements it. The challenge came from prose drift, not from a changed constraint.

### B — Supersede toward MCP-primary
Would require actually registering the server in `plugin.json`, accepting a hard runtime dependency and always-on tool surface. No new evidence supports paying that cost; the drifted doc sentence was aspiration, not implementation.

## Consequences

Positive: status vocabulary now records that this decision was challenged and survived — future auditors see `re_affirmed_by` instead of re-litigating. The skill's installer description matches reality.

Negative: none material; the doc fix is one sentence.

## Disconfirmation

- **Falsifier**: `chub` (or a successor) appearing in `plugin.json` `mcpServers`, or the installer actually configuring an MCP server, would invalidate the re-affirmation immediately.
- **Steelmanned runner-up**: MCP-primary offers native tool ergonomics and provider-side schema discovery; if agents demonstrably underuse the skill wrapper while needing external docs, that is the cost of opt-in made visible.
- **Reversal trigger**: telemetry showing repeated external-API doc failures in sessions where the skill was never activated — evidence the opt-in boundary, not the doc, is the problem.

## Prior Decision

dec-001 (2026-03-31) chose a skill wrapper over bundling an MCP server in `plugin.json`. A future supersession would require: a demonstrated activation-failure pattern of the opt-in skill, or an ecosystem shift making MCP registration cost-free (lazy server startup in the host), or context-hub dropping its CLI surface.
