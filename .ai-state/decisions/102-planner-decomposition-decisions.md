---
id: dec-102
title: AaC+DaC v1 implementation decomposition — two-worktree split at Phase 3/4 boundary
status: accepted
category: implementation
date: 2026-04-30
summary: 'Decompose 20-step AaC+DaC v1 plan (Ideas 1, 2, 4, 5) into two follow-up worktrees: Worktree 1 for Phases 0–3 (foundation through architect-validator agent), Worktree 2 for Phases 4–5 (agent boundary updates + verification). Split at the dependency cut where Phase 4 requires the agent file to exist on main before boundary-table references can be reviewed.'
tags: [aac, dac, implementation-planning, worktree, decomposition]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - agents/architect-validator.md
---

## Context

The AaC+DaC v1 implementation plan has 20 steps across 5 phases. The plan must be executed in follow-up worktrees (current worktree is planning-only). A critical sequencing dependency exists: Phase 4 (agent boundary updates to 4 agents + 3 rules) all reference `agents/architect-validator.md` by name. These references are only meaningful — and their PRs reviewable — once the agent file exists on main. Similarly, the coordination protocol's boundary-discipline table (Step 4.1) refers to the agent's charter details, which should be a merge-ready PR before reviewers see the table.

## Decision

Split into **two follow-up worktrees**:

**Worktree 1 (Phases 0 + 1 + 2 + 3, Steps 0.1–3.3):** Prerequisites (library versions, MCP confirmation, third-writer rule edit) → philosophy clauses + fence substrate → fitness infrastructure → architect-validator agent creation + registration.

**Worktree 2 (Phases 4 + 5, Steps 4.1–5.3):** Agent boundary updates to existing agents and rules (4 agents: systems-architect, doc-engineer, implementer, verifier; 3 rules: swe-agent-coordination-protocol, agent-model-routing, agent-intermediate-documents) + final verification and token-budget check.

The dependency cut: Worktree 2 starts only after Worktree 1 merges to main.

## Considered Options

### Option 1 — One big worktree (all 20 steps serial)

**Pros:** Simplest process; no handoff between worktrees.

**Cons:** Large PR (~20 files changed, ~350 lines net new code + markdown). Harder to review atomically. If one step requires rework, the entire PR is blocked.

### Option 2 — Two worktrees at Phase 3/4 boundary (chosen)

**Pros:** Clear dependency cut. Worktree 1 PR is reviewable without Worktree 2. Worktree 2 is a coherent "wire the new agent into the ecosystem" batch. Each PR is 10–12 files, manageable review load.

**Cons:** Requires two PR/merge cycles. Minor overhead.

### Option 3 — Three or more worktrees (e.g., P0+P1, P2, P3, P4+P5)

**Pros:** Smaller PRs.

**Cons:** Over-fragmented. P1 and P2 have forward references (fence rule in Step 1.2 is cited by fitness skill in Step 2.1; validator in Step 1.6 is used by architect-validator in Step 3.1). Splitting at P1/P2 or P2/P3 boundaries creates worktrees that can't independently integrate. Rejected.

## Consequences

**Positive:**

- Manageable PR sizes (~10–12 files each).
- Worktree 1 ships the three foundational layers independently; Worktree 2 wires them into the agent ecosystem.
- Integration checkpoints (Steps 1.8, 2.4, 3.3, 4.9) within each worktree verify intermediate state before advancing.

**Negative:**

- Two merge cycles. If Worktree 1 requires post-merge fixes that affect Phase 4 assumptions, Worktree 2 needs to rebase.

**Operational:**

- The main agent should spawn Worktree 1 first, await merge, then spawn Worktree 2.
- Both worktrees operate under the same task slug `aac-dac-philosophy` — they share `.ai-work/aac-dac-philosophy/` for planning docs.
