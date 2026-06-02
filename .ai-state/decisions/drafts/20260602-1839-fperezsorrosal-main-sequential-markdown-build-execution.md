---
id: dec-draft-01896314
title: Sequential execution for Markdown artifact family build (agentic-transactions)
status: proposed
category: implementation
date: 2026-06-02
summary: Steps 1-4 of the agentic-transactions plan execute sequentially rather than in parallel groups because cross-reference consistency in the agent/skill/reference family requires name contracts to be established before dependent artifacts are authored.
tags: [agentic-transactions, implementation-plan, step-ordering, parallel-execution, cross-reference-consistency]
made_by: agent
agent_type: implementation-planner
branch: main
pipeline_tier: full
affected_files:
  - agents/agentic-transactions-architect.md
  - skills/agentic-transactions/SKILL.md
  - skills/agentic-transactions/references/provider-contract.md
  - skills/agentic-transactions/references/robinhood.md
  - skills/agentic-transactions/references/_provider-template.md
affected_reqs: []
re_affirms: dec-draft-b7686136
---

## Context

The implementation plan for the agentic-transactions capability (AC1–AC8) produces five new Markdown artifacts that cross-reference each other: the agent cites the skill name in its `skills:` frontmatter; the skill body lists the satellite reference file names; the reference files back-link to `../SKILL.md`. The implementation-planner must choose between sequential and parallel step execution for the authoring steps (Steps 1-4).

## Decision

Execute Steps 1-4 **sequentially**: agent definition first, then skill body, then contract reference, then provider references. Do NOT parallelize these four steps into concurrent agent spawns.

## Considered Options

### Option 1 — Sequential execution (chosen)

- Pros: agent definition establishes the skill name (`agentic-transactions`) before the skill body is authored; skill body establishes the reference file names before references are authored; no terminological drift between concurrent agents; a single implementer context window holds all name contracts.
- Cons: slightly longer wall-clock time (~4 steps vs ~2 parallel batches).

### Option 2 — Two parallel groups (agent+skill body | references)

- Pros: potentially faster if agents are spawned concurrently.
- Cons: agent and skill body share an implicit name contract (`skills: [agentic-transactions]` in the agent frontmatter must match the skill directory name). If spawned simultaneously, implementer A names the skill one way and implementer B's skill body uses a different variation — the conflict surfaces only at Step 5 wiring, where the plugin.json glob and agents/README.md must agree on the canonical name. For a small 7-step plan, the coordination overhead of a parallel merge exceeds the benefit.

### Option 3 — Full parallel (all authoring steps concurrent)

- Rejected: the references (Steps 3-4) must know the SKILL.md body's satellite-listing contract to avoid duplicating content that belongs in the body vs the reference.

## Consequences

- **Positive:** The integrated artifact family is consistent on first authoring pass; the Step 7 integration checkpoint runs against a coherent set.
- **Negative / accepted:** Wall-clock is slightly longer than a two-group parallel plan; acceptable given the small step count (7 total).
- **Note:** This decision is specific to the nascent domain artifact family build. Future extensions (adding a second provider) are single-file additions that can run as standalone steps without sequencing concerns.
