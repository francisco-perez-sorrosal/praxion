---
id: dec-211
title: New agentic-transactions-architect is a shadow + on-demand sub-architect (interface-designer-shaped), emitting TRANSACTIONS_DESIGN.md with a challenge loop
status: accepted
category: architectural
date: 2026-06-02
summary: The new domain-expert agent is a peer sub-architect modeled on interface-designer — it shadows researcher+systems-architect when transactions are in scope, owns mandate/finality/ToS/HITL domain expertise, emits a forward-only TRANSACTIONS_DESIGN.md, and registers objections via an orchestrator-mediated Architecture Challenges loop. One skill (agentic-transactions), not a multi-skill family.
tags: [agentic-transactions, agent, pipeline-placement, sub-architect, shadow-agent, challenge-loop, skill-design]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: full
affected_files:
  - agents/agentic-transactions-architect.md
  - skills/agentic-transactions/SKILL.md
  - plugin.json
  - agents/README.md
  - rules/swe/agent-model-routing.md
affected_reqs: [REQ-01, REQ-02, REQ-03]
---

## Context

The agentic-transactions capability needs domain expertise the generalist `systems-architect` lacks: mandate models, settlement finality, broker ToS/regulatory boundaries, and HITL spend-gating. The question is *what kind of pipeline citizen* this domain expert is — a forward-pipeline stage, a shadow sub-architect, or an on-demand consultant — and how the domain knowledge is packaged as skills. Praxion already has a validated precedent: `interface-designer` is a peer sub-architect that shadows the researcher + systems-architect stages, owns its design domain with decision authority, emits `INTERFACE_DESIGN.md`, and challenges the architect via an orchestrator-mediated `## Architecture Challenges` loop.

## Decision

Create **one new agent**, `agentic-transactions-architect`, shaped on `interface-designer`:

- **Placement:** shadow + on-demand sub-architect (not a mandatory forward stage). It shadows researcher + systems-architect when a managed-project task involves agentic payments/trading; runs standalone for a transactions design review.
- **Authority & boundary:** owns the transaction *domain* semantics (mandate models, settlement finality, broker ToS/regulatory boundaries, HITL spend-gating). The `systems-architect` owns *that* a transaction boundary exists and its place in the system; the transactions-architect owns *what the transaction semantics are*. Does NOT write production code.
- **Artifact:** emits a forward-only `TRANSACTIONS_DESIGN.md` consumed by implementation-planner / implementer / verifier, with an `## Architecture Challenges` section the orchestrator routes back to systems-architect for one mediated round.
- **Model tier:** `opus` (H) per `agent-model-routing.md` — quality judgment across a regulated, high-stakes, fast-moving domain, like systems-architect / interface-designer / verifier.
- **Skill packaging:** **one** skill, `agentic-transactions`, with the conceptual contract + two-space rubric in the body and per-provider/per-space specifics in `references/` — NOT a multi-skill family (the two spaces share one contract; splitting would duplicate it).

## Considered Options

### Option 1 — Shadow + on-demand sub-architect, interface-designer-shaped, one skill (chosen)
- Pros: reuses proven shadowing + challenge-loop machinery; clean boundary with systems-architect; gated on transactions being in scope; single cohesive skill avoids contract duplication.
- Cons: a new ephemeral artifact name and one more peer-architect to document.

### Option 2 — Mandatory forward-pipeline stage
- Pros: never missed when transactions are in scope.
- Cons: fires even when not needed; heavier than the shadow pattern; no precedent for a domain-specific mandatory stage.

### Option 3 — Fold the expertise into systems-architect as a skill only (no new agent)
- Pros: no new agent; smallest footprint.
- Cons: the generalist architect lacks the focused context window and advocacy standing to catch finality/HITL leaks; loses the challenge-loop objection channel; mandate/ToS/regulatory reasoning competes for attention with general architecture.

### Option 4 — Multi-skill family (agentic-payments + agentic-trading)
- Pros: independent activation per space.
- Cons: the two spaces share one Provider contract; splitting duplicates it or forces a cross-skill dependency (contrast `dec-150`, where the four interface hats were genuinely independent domains).

## Consequences

- **Positive:** the orchestrator routes to a focused domain expert with its own context window and objection channel (REQ-01, REQ-02); the challenge loop catches settlement-finality and spend-gating leaks before the plan freezes; one skill is the single source of truth for the contract (REQ-03).
- **Negative / accepted:** one more `.ai-work/` artifact (`TRANSACTIONS_DESIGN.md`) and one more agent in the catalog — bounded, follows the interface-designer convention exactly. If the two spaces later diverge past the shared core, the skill splits cleanly (references are already per-space).
