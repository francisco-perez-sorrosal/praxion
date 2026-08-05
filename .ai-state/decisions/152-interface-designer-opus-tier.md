---
id: dec-152
title: '`interface-designer` runs at opus tier (capability floor)'
status: accepted
category: architectural
date: 2026-05-12
summary: Place interface-designer in the H tier (alias `opus`) in agent-model-routing.md — its value is taste-under-trade-offs across a broad design space, the same rationale as systems-architect and verifier. Capability floor, not a ceiling; the orchestrator may route up via per-spawn override, never below.
tags: [architecture, agent, interface-design, model-routing, agent-model-routing]
made_by: agent
agent_type: systems-architect
branch: worktree-interface-design
pipeline_tier: full
affected_files:
  - rules/swe/agent-model-routing.md
  - agents/interface-designer.md
---

## Context

`agent-model-routing.md` assigns every Praxion subagent a tier (H/M/L → `opus`/`sonnet`/`haiku`) acting as a capability floor: the orchestrator may route up via a per-spawn override, never below. The `interface-designer` agent (see `dec-149`) needs a tier assignment and a Tier Table row. Its `model:` frontmatter must match.

## Decision

`interface-designer` is **H tier (alias `opus`)**. Add a row to the `agent-model-routing.md` Tier Table, placed adjacent to `verifier` and `architect-validator` (the other H-tier quality/structural agents):

```
| `interface-designer` | H | `opus` | Interface-layer design under trade-offs; taste-critical |
```

Its agent-file frontmatter carries `model: opus  # capability floor; orchestrator may route up via per-spawn override, never below. See rules/swe/agent-model-routing.md.` — byte-identical to the floor comment on `systems-architect` and `verifier`.

Rationale: the agent's entire value is **taste across a broad design space under trade-offs** — choosing a UI framework, an API paradigm, an MCP tool decomposition, an error format, a pagination strategy, an interaction model, and sketching the designs that follow — exactly the profile that puts `systems-architect` (trade-offs, ADRs, cross-codebase reasoning) and `verifier` (quality-critical gate, structural reasoning) in H. Downgrading below opus would degrade the design quality the agent exists to produce — and the user explicitly set an extreme quality bar. The agent only runs when an interface surface is in scope, so the opus cost is bounded.

## Considered Options

### Option 1 — M tier (`sonnet`)

Rejected — `sonnet` is the tier for feature-scoped decomposition (`implementation-planner`), single-step execution (`implementer`), and placement/conflict-detection (`context-engineer`); interface design is broader-judgment work than any of those. The quality-cliff guards in `agent-model-routing.md` reserve opus for "deep reasoning" and "trade-off resolution" — interface design is both.

### Option 2 — H tier (`opus`) (chosen)

Matches `systems-architect` and `verifier`; a capability floor, not a ceiling.

- **Pro**: the design quality the agent exists for; consistency with the other taste/structural agents.
- **Con**: opus cost — bounded because the agent only runs when an interface surface is in scope.

## Consequences

**Positive:**
- The agent produces design quality commensurate with the user's extreme quality bar.
- Consistency with `systems-architect`/`verifier` — the routing model treats peer taste/structural agents the same.
- The capability-floor semantics mean the orchestrator can route up (e.g., a `CLAUDE_CODE_SUBAGENT_MODEL` override) but never down, protecting the quality cliff.

**Negative / accepted:**
- One more opus-tier agent — accepted; the agent only runs when an interface surface is in scope, and interface design is high-leverage.

This decision is a consequence of `dec-149` (the agent shape) split out because the routing-rule Tier Table row is its own concern. It also re-affirms the routing-model principles in `dec-076`–`dec-080` (the agent-model-routing cohort) — the frontmatter-floor-semantic, the hybrid routing mechanism, the always-loaded-rule placement; named here in prose rather than the single-valued `re_affirms:` frontmatter field. Recorded in `LEARNINGS.md ### Decisions Made` by the implementation-planner.
