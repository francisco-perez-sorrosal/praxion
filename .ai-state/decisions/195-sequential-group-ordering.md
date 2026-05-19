---
id: dec-195
title: "Sequential group ordering for test-topology activation: trunk-first, then agents in parallel"
status: accepted
category: implementation
date: "2026-05-19"
summary: "S7 (test-topology.md trunk) must land before all agent edits; S11 (agent-intermediate-documents rule) is parallel-safe with S7; agents S1-S6 can parallelize after S7."
tags: [test-topology, implementation-ordering, context-artifact, parallel-groups]
made_by: agent
agent_type: implementation-planner
branch: worktree-test-topology-activation
pipeline_tier: full
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - agents/sentinel.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - skills/testing-strategy/SKILL.md
  - commands/refresh-topology.md
  - claude/config/CLAUDE.md.tmpl
  - rules/swe/agent-intermediate-documents.md
---

## Context

The test-topology activation task modifies 11 surfaces: a trunk skill reference (S7), a rule (S11), six
agent definitions (S1–S6), a skill pointer (S8), a new command (S9), and the orchestrator config template
(S10). The CONTEXT_REVIEW F4 finding establishes that S7 is load-bearing: all six agent clauses reference
`skills/testing-strategy/references/test-topology.md` for the `## Growth-Trigger Policy` section and the
`Tests:` field schema. The commands/S8/S10 also reference the trunk. S11 only replaces static milestone
wording with no inbound dependencies.

The decomposition question is: what ordering and parallelism structure minimizes wall-clock time while
preserving reference integrity at each commit boundary?

## Decision

Use three sequential parallel groups:

- **Group A** (parallel): S7 (trunk additions) ∥ S11 (rule amendment). S11 has no inbound dependency; S7
  and S11 touch disjoint files. Both context-engineer assignees.
- **Group B** (parallel, depends on A): S8 (SKILL.md pointer) ∥ S9 (new command) ∥ S1–S6 (six agent edits).
  All reference the trunk section S7 created; all have disjoint files. S8 and S9 each touch one file;
  each of S1–S6 touches one file. Seven concurrent context-engineer tasks.
- **Group C** (sequential, depends on B): S10 (CLAUDE.md.tmpl addition). References the testing-strategy
  skill (S8) and topology protocol (S7). Single file; one context-engineer.
- **Integration checkpoint** (depends on C): run validators, `wc -c`, verify REQ coverage by inspection.

## Considered Options

### Option 1: Fully sequential (one step per surface, S7→S8→S9→S1→S2→S3→S4→S5→S6→S10→S11)

- Pro: Simple, no coordination overhead.
- Con: 11 sequential steps with no wall-clock savings from independent file disjointness.

### Option 2: Two groups (S7+S11 first, then everything else in parallel)

- Pro: Maximum parallelism — all remaining 9 surfaces run concurrently.
- Con: S10 depends on S8 being correct (the SKILL.md pointer update defines what S10 references). Running S10
  concurrently with S8 risks a forward reference in S10 before S8's content is stable. The risk is small
  (S10 just names the skill, not a specific section title that could drift), but the cleaner decomposition
  puts S10 after Group B.

### Option 3 (chosen): Three sequential groups (S7+S11 → all agents+S8+S9 → S10 → checkpoint)

- Pro: S7 lands first (F4 satisfied); agents and command parallelize (disjoint files, F4 dependency met);
  S10 follows once the skill pointer (S8) is stable. Right-sizes concurrency to real dependencies.
- Con: S10 is forced sequential after Group B even though its only actual dependency is S7. Accepted —
  the wall-clock cost is one extra sequential step, and the decomposition is easier to supervise.

## Consequences

- **Positive:** Reference integrity at every commit boundary — no agent clause can precede the trunk section
  it references, because Group A lands S7 before Group B spawns.
- **Positive:** Maximum legal parallelism — seven concurrent tasks in Group B, disjoint file sets verified.
- **Negative:** S10 is blocked until all of Group B completes, even though only S7 and S8 are its real
  prerequisites. Acceptable — the delay is at most the longest Group B task minus the S8 duration.
- **Risk accepted:** If one Group B agent reports `[BLOCKED]` or `[CONFLICT]`, the others continue; the
  planner handles the failure at the coherence review step (after all Group B tasks report).
