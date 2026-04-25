---
id: dec-draft-8cbfa312
title: Hybrid routing — central rule table with sparing per-spawn overrides
status: accepted
category: architectural
date: 2026-04-25
summary: Per-agent model routing uses a central rule table as the authority, layer-2 per-spawn overrides only for named exceptions (researcher mode, implementer step-level hint)
tags: [model-routing, agent-pipeline, cost, architecture, claude-code]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/agent-model-routing.md
  - rules/swe/swe-agent-coordination-protocol.md
  - agents/systems-architect.md
  - agents/promethean.md
  - agents/roadmap-cartographer.md
affected_reqs:
  - AC1
  - AC3
  - AC4
---

## Context

Praxion's 13 pipeline agents currently resolve their model via a mix of three frontmatter pins (`systems-architect`, `promethean`, `roadmap-cartographer` → `model: opus`) and ten implicit `inherit`s (session default). Research verified that Claude Code's documented 4-layer resolution chain supports dynamic per-spawn routing via the Agent tool's `model` parameter (layer-2, beats frontmatter). The cost spread is meaningful — Opus↔Haiku ≈ 5×, Sonnet↔Haiku ≈ 3× — and Anthropic explicitly endorses multi-Haiku parallel fan-out, matching Praxion's researcher-fan-out pattern. A routing policy is feasible; the open question is how to encode it.

## Decision

Adopt a **hybrid** routing mechanism:

- A central always-loaded rule `rules/swe/agent-model-routing.md` is the authoritative tier table. All 13 agents appear with an H/M/L tier and a one-line rationale.
- The 3 existing `model: opus` frontmatter pins are retained as **capability floors** (see `dec-draft-3f54371e`).
- The main orchestrator passes layer-2 `model: <alias>` on every Agent-tool spawn for the 10 non-pinned agents, using the rule table as the source of truth.
- Layer-2 overrides on *top of* the rule table are sanctioned for exactly two cases: (a) researcher mode selection (lookup vs comparative vs contested-evidence), (b) implementer step-level `tier:` hint from the planner. Any third case requires reopening this ADR.

## Considered Options

### Option 1 — Frontmatter pins only

- Pros: Declarative, greppable, local intent visible.
- Cons: No single source of truth for tiers across agents; drift between any policy doc and frontmatter is inevitable; no way to express task-sensitive routing (researcher lookup vs comparative).

### Option 2 — Per-spawn overrides only (no rule table)

- Pros: Maximally flexible; every spawn is explicit.
- Cons: No declarative policy; the orchestrator must encode tier logic in prose every pipeline cycle; no audit trail across agents.

### Option 3 — Hybrid (selected)

- Pros: Rule table is the single authority for tiers (audit-friendly); frontmatter floors preserve local intent for the 3 strategic agents; layer-2 overrides handle the two known task-sensitive cases without creating runtime ambiguity.
- Cons: A maintainer must know to check *both* frontmatter (for floors) and the rule table (for tiers). Mitigated by cross-references between the two.

## Consequences

**Positive:**

- Cost savings: **directional estimate, unmeasured** — pipeline cost should drop 30–50% on multi-agent runs based on a back-of-envelope calculation with 4H / 8M / 1L distribution and researcher-lookup L-mode. This is a hypothesis to be validated by post-ship telemetry; it is not evidence of a measured result. A revisit trigger fires one month from ship per the telemetry-deferral ADR.
- Declarative clarity for authors: rule table is one source of truth for tier questions.
- Task-sensitive flexibility where it matters: researcher and implementer handle variable workload.

**Negative:**

- Two lookup surfaces (floor vs rule table) for anyone debugging a tier assignment. Mitigated by rule's header and the `agent-crafting` reference note.
- Layer-2 overrides not mechanically enforced — a future agent could add a third exception without updating the ADR. Mitigated by naming the two sanctioned cases in the rule and requiring reopening.

**Risks accepted:**

- Exceptions proliferate. Boundary: exactly two sanctioned layer-2 cases.
- Main orchestrator forgets to pass the layer-2 override → agent inherits session default instead of rule tier. Mitigated by the rule's standing instruction and the floor semantic (floor catches the worst case).
