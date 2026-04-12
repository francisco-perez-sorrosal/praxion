---
id: dec-031
title: Roadmap-creation is user-initiated and standalone, not inserted into the promethean→SDD chain
status: accepted
category: architectural
date: 2026-04-12
summary: 'Cartographer invoked on-demand (command, delegation, or semantic intent) like sentinel; not a new tier, not inserted into feature-level pipeline, not currently event-triggered'
tags: [architecture, roadmap, pipeline, placement, standalone]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
---

## Context

Context-engineer Phase 1 identified five placement models for roadmap-creation:

1. **Pre-pipeline** — runs before promethean; promethean ideates against roadmap slots.
2. **Parallel / on-demand** — user invokes any time to audit and produce `ROADMAP.md`.
3. **Own tier** — add a sixth calibration tier above Full for project-level roadmapping.
4. **Event-triggered** — stale-roadmap detector fires the cartographer automatically.
5. **User-initiated only** — simplest; matches SPIRIT's origin (user prompt drove the first ROADMAP.md).

Roadmap-creation operates at *project altitude* (multi-item, cross-cutting audit) while promethean operates at *feature altitude* (single validated idea). Inserting roadmap-creation into the feature-level chain distorts both altitudes. Sentinel provides the canonical precedent for a standalone, read-only audit artifact invoked independently.

## Decision

Roadmap-creation is **user-initiated and standalone**. The `roadmap-cartographer` operates like `sentinel`: independent of the feature-level pipeline, invoked on demand, producing a project-level artifact. Three discovery layers:

1. `/roadmap` slash command (explicit user trigger with mode parsing)
2. Formal entry in the Available Agents table (`swe-agent-coordination-protocol.md`) with a Delegation Checklist
3. Description-based semantic activation when the main coordinator recognizes intent phrases ("spring cleaning", "state of the project", "what should we build next", "roadmap audit")

The cartographer is NOT inserted between promethean and SDD. Downstream handoff is by `ROADMAP.md` content itself — each "Now" item names a downstream agent in a "Next pipeline action" field; the main coordinator optionally invokes that agent.

Event-triggered invocation (e.g., stale-roadmap detection) is deferred: it would require a roadmap-staleness dimension in sentinel, which is follow-up work.

## Considered Options

### Option 1 — Pre-pipeline placement

Cartographer runs before promethean; feature ideation is scoped to roadmap slots.
**Pros:** clear precedence (project-level direction first, then feature-level ideas).
**Cons:** inverts the existing flow (promethean is currently upstream of roadmap-planning, which organizes the ideas promethean generates). Breaking change to the pipeline. Also: not every feature idea needs a pre-existing roadmap slot (27% of agentic work is emergent per the Anthropic 2026 report).

### Option 2 — Parallel / on-demand (chosen)

Cartographer is a standalone capability invoked independently.
**Pros:** matches sentinel's precedent; orthogonal to the feature-level pipeline; matches SPIRIT's origin (user drove the first invocation).
**Cons:** requires clear discovery mechanism so the coordinator finds it without explicit prompting; relies on description-based semantic activation for implicit triggers.

### Option 3 — New calibration tier

Add a sixth tier ("Roadmap") above Full.
**Pros:** formal recognition of project-level planning as distinct from feature-level work.
**Cons:** overengineered for a single workflow; forces rule edits to the calibration table (budget pressure); does not solve any concrete problem the parallel placement leaves open.

### Option 4 — Event-triggered

Sentinel detects stale `ROADMAP.md` and auto-invokes cartographer.
**Pros:** preempts roadmap rot; aligns with agentic-cycle "regenerate at low cost" guidance.
**Cons:** requires a roadmap-staleness dimension in sentinel (doesn't exist yet); premature optimization — ship the basic capability first, add detection later if the friction warrants it.

### Option 5 — User-initiated only (folded into Option 2)

Cartographer runs only when the user types `/roadmap`.
**Pros:** simplest; zero auto-invocation surprise.
**Cons:** misses implicit user intent ("let's do spring cleaning" should trigger without the explicit command). Combined with semantic activation (Option 2), this gap closes.

## Consequences

**Positive:**

- Orthogonal to the feature-level pipeline; no calibration-table changes needed.
- Sentinel's independence precedent is reused; the ecosystem pattern is consistent.
- Main coordinator has three independent discovery paths, increasing the chance the cartographer is invoked when appropriate.
- Event-triggered mode is open as future work without requiring rework of the current design.

**Negative:**

- Discovery relies partly on description-based semantic activation, which is model-dependent. Mitigated by the explicit `/roadmap` command and the formal delegation-table entry.
- No proactive stale-roadmap suggestion until a future sentinel extension is built.

**Operational:**

- Available Agents table (in `swe-agent-coordination-protocol.md`) gains a `roadmap-cartographer` row per dec-034's net-≤0 budget offset.
- Delegation Checklist for the cartographer added alongside existing agent checklists.
- Proactive Agent Usage section gains a bullet describing roadmap-intent recognition.
- No change to existing agents' pipeline placements.
