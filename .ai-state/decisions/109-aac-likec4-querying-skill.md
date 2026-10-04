---
id: dec-109
title: likec4-querying skill — path-scoped progressive-disclosure rubric for MCP-vs-direct-read decisions
status: accepted
category: architectural
date: 2026-05-01
summary: 'Ship skills/likec4-querying/SKILL.md (≤200 lines, path-scoped to .c4 / ARCHITECTURE.md / docs/architecture.md / docs/diagrams) with a one-table decision rubric covering eight common architecture-authoring tasks, plus a references/mcp-tool-recipes.md catalog with one worked example per likec4 MCP tool.'
tags: [skill, likec4, mcp, progressive-disclosure, aac, dac, architecture, rubric]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/likec4-querying/SKILL.md
  - skills/likec4-querying/references/mcp-tool-recipes.md
  - skills/likec4-querying/README.md
superseded_in_part_by: [dec-draft-971ab11d]
---

## Context

The `likec4` MCP server exposes 11 read-only tools (`list-projects`, `read-project-summary`, `search-element`, `read-element`, `read-deployment`, `read-view`, `find-relationships`, `query-graph`, `query-incomers-graph`, `query-outgoers-graph`, `query-by-metadata`, `query-by-tags`, `find-relationship-paths`). Agents authoring or reviewing architecture content currently choose between calling these MCP tools and reading `.c4` files directly with `Read` — without a documented rubric. The `architect-validator` agent (`dec-100`) has its own internal preference order, but the rubric is buried inside the agent prompt and does not benefit other consumers (systems-architect, doc-engineer, future agents that touch `.c4` files).

Without a shared rubric, three failure modes coexist:
- **Wrong-tool choice**: an agent reads every `.c4` file when one `search-element` call would suffice (token waste).
- **Wrong-tool choice the other way**: an agent calls `read-project-summary` repeatedly when a single `Read` of a 100-line `.c4` file would suffice (latency waste, MCP-server round-trips).
- **Missing capability awareness**: agents don't know `find-relationship-paths` exists and reimplement BFS by hand.

## Decision

Ship a new top-level skill `skills/likec4-querying/`:

```
skills/likec4-querying/
  SKILL.md
  README.md
  references/
    mcp-tool-recipes.md
```

`SKILL.md` is **path-scoped** so it consumes zero always-loaded token budget:

```yaml
---
name: likec4-querying
description: 'Decision rubric and recipes for querying LikeC4 architecture models — when to use the likec4 MCP server''s read tools vs. read .c4 source files directly. Use when authoring or reviewing LikeC4 DSL, when answering structural questions about a system''s architecture, or when an architect-validator-style triangle check needs LikeC4 inputs.'
paths:
  - "**/*.c4"
  - "**/ARCHITECTURE.md"
  - "docs/architecture.md"
  - "docs/diagrams/**"
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---
```

The skill body contains:

1. **Decision rubric** (one canonical table covering eight authoring/reviewing tasks). Each row names a signal (file count, search dimension, recursion depth, edit-vs-read intent) and recommends MCP tool or direct `Read`.
2. **Quick reference** of the MCP tool catalog (one line per tool — name, purpose, when to use).
3. **Pointer** to the recipes reference for full examples.
4. **Common pitfalls** section: 3–5 documented failure modes (e.g., "MCP is read-only — for edits, use Read+Edit and let the next architect-validator pass detect any drift").

The references file `mcp-tool-recipes.md` documents every MCP tool with:
- One-paragraph use case.
- Input shape (the JSON object the tool accepts).
- Worked example with representative output excerpt (10–20 lines, truncated with `...` when long).

The skill adds `staleness_sensitive_sections:` to its frontmatter listing the rubric and tool table, with a 120-day default threshold so the sentinel F08 check catches drift if the MCP tool list evolves.

## Considered Options

### Option 1 — New top-level skill (chosen)

**Pros:** Path-scoped activation hits exactly when the rubric is useful (architecture-authoring surfaces). Zero always-loaded cost. Skill catalog already supports >40 skills with no scaling problems. Progressive disclosure: SKILL.md loads on path match, recipes load on demand.

**Cons:** One more skill directory in `skills/`. Mitigated by clean placement and reuse of existing skill conventions.

### Option 2 — Reference file under `skills/software-planning/references/likec4-mcp.md`

**Pros:** Reuses an existing skill's directory.

**Cons:** `software-planning` activates on broad planning tasks that don't always need LikeC4 detail. Loading the LikeC4 reference from inside software-planning's own activation is fine, but the rubric's *primary* trigger should be architectural-authoring paths, not planning. Forcing the reference under software-planning means architectural-only tasks (no planning) miss the rubric. Rejected.

### Option 3 — Inline in `rules/writing/aac-dac-conventions.md`

**Pros:** Reuses an existing path-scoped rule.

**Cons:** Rules encode declarative constraints; the rubric is procedural (a how-to-choose-tools recipe). Mixing the two violates the rules-vs-skills separation. The rule already encodes the fence convention; adding tool-selection procedure dilutes its purpose. Rejected.

### Option 4 — Embed in `architect-validator` agent prompt only

**Pros:** Co-located with the agent that needs it most.

**Cons:** Other consumers (systems-architect, doc-engineer, future agents) lose access. Re-extracting the rubric for each consumer duplicates content. The agent-validator's prompt is already substantial; embedding the rubric there bloats the prompt.

## Consequences

**Positive:**

- Agents authoring/reviewing architecture get a one-stop rubric for tool selection.
- Path-scoped activation keeps always-loaded surface unchanged.
- The recipes reference is the authoritative example catalog for the LikeC4 MCP — useful for onboarding new agents to the toolset.
- Sentinel F08 will surface drift if the MCP tool list changes.

**Negative:**

- One additional skill catalog entry.
- Skill maintenance: when the LikeC4 MCP server adds tools, the rubric and recipes must update. Mitigated by `staleness_sensitive_sections:` listing the affected sections.

**Operational:**

- Add `skills/likec4-querying/` to the standard skill catalog (already auto-discovered via the directory glob in `.claude-plugin/plugin.json` — no manifest update needed per `skills/CLAUDE.md`).
- After authoring, run `skills/skill-crafting/scripts/validate.py` to verify frontmatter and structure.
- The skill should be referenced by `architect-validator`'s prompt as a soft pointer ("Consult `skills/likec4-querying/` for tool selection") so that consumers running outside the agent's path-scope still benefit; this is a one-line edit, deferred to implementation.
- Library-version verification: the `likec4` CLI is already a project dependency (used by the diagram-regen hook). The MCP server tool list is captured from the system reminder injected at session start (lists 11 tools as of 2026-04-30). The skill should include a "Last verified" marker per the staleness policy.
