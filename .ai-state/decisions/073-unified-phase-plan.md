---
id: dec-073
title: Praxion-first-class — unified four-phase implementation plan
status: proposed
category: implementation
date: 2026-04-26
summary: Unified IMPLEMENTATION_PLAN.md covering both workstreams in four named phases; hygiene sequential, hook infrastructure with paired BDD/TDD, canonical block plus docs parallel, wiring and budget measurement sequential.
tags: [praxion-first-class, implementation-plan, phase-organization, bdd-tdd, parallel-execution]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - .ai-work/praxion-first-class/IMPLEMENTATION_PLAN.md
  - hooks/inject_subagent_context.py
  - hooks/inject_process_framing.py
  - hooks/auto_complete_install.py
  - scripts/render_claude_md.py
  - hooks/hooks.json
  - hooks/inject_memory.py
  - commands/onboard-project.md
  - commands/new-project.md
  - skills/hook-crafting/references/output-patterns.md
  - README.md
  - README_DEV.md
  - commands/praxion-complete-install.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16]
re_affirms: dec-075
---

## Context

The systems-architect produced a single unified `SYSTEMS_PLAN.md` for the praxion-first-class feature, covering both Workstream A (principle mechanism: rule-inheritance hooks + canonical L2 block) and Workstream B (install-path completeness: first-session auto-install). The implementation-planner must decide whether to produce one unified plan or split it by workstream, and must determine the step ordering to manage the dependency between the `scripts/render_claude_md.py` extraction (required by `auto_complete_install.py`) and the hook registration ordering (hooks.json wiring must wait for all hooks to be implemented and tested).

The architect flagged five constraints:
1. byte-identical mirror discipline between `onboard-project.md` and `new-project.md`
2. idempotency tests are non-default and must be explicitly planned
3. first-session UX must be tested on clean macOS profile / Docker
4. hooks.json wiring should not activate untested hooks
5. token-budget breach risk at L2 requires post-implementation measurement

## Decision

Produce a unified `IMPLEMENTATION_PLAN.md` with 16 steps organized into four named phases:

- **Phase A (hygiene, steps 1–2, sequential)**: Remove dead SubagentStart code path; correct hook-crafting skill documentation. These are prerequisite hygiene steps that touch hooks.json and skills/ — must complete before any new hooks.json edits in Phase D.
- **Phase B (hook infrastructure, steps 3–10, parallel BDD/TDD pairs)**: Extract render helper (B0), implement PreToolUse hook (B1), implement UserPromptSubmit hook (B2), implement auto-install hook (B3 — depends on B0). Each pair is implementer + test-engineer with the TDD red-handshake protocol.
- **Phase C (canonical block + docs, steps 11–13, parallel with Phase B)**: Add §Praxion Process block to both commands (byte-identical, C1 paired with test-engineer), update READMEs and command docs (C2 doc-engineer parallel to C1). Phase C is independent of Phase B (disjoint file sets).
- **Phase D (wiring + measurement, steps 14–16, sequential)**: Integration checkpoint (all tests green), register new hooks in hooks.json, measure always-loaded token budget.

hooks.json wiring (Step 15) is placed in Phase D **after** the integration gate to prevent activation of untested hooks in the plugin.

## Considered Options

### Option A — Two separate plans (one per workstream)

**Pros**: clear workstream isolation; Workstream A could ship independently.
**Cons**: artificial split — Workstream B's auto-install hook depends on the render helper in Workstream A's dependency chain; the hooks.json wiring step spans both workstreams; managing a shared hooks.json across two plans requires coordination protocol.

### Option B — Unified plan without phase labels

**Pros**: simplicity; fewer organizational concepts.
**Cons**: 16 steps with no phase labels are harder to supervise at checkpoints; the dependency structure (B3 depends on B0; Phase D depends on all) is harder to communicate.

### Option C — Unified plan with four named phases (selected)

**Pros**: organizational clarity matching the two-workstream + hygiene + measurement structure; phase-level supervision checkpoints; parallel group structure visible at a glance.
**Cons**: more overhead in the plan document; reviewers must understand four phase names.

## Consequences

**Positive**:
- Phase boundaries provide natural supervision checkpoints with clear done criteria
- Parallel group structure (B0–B3 + C1 + C2) maximizes concurrency within Safety constraints
- hooks.json wiring gated after integration testing prevents premature activation of untested hooks
- byte-identical mirror Done-when clause on Step 11 provides mechanical verification

**Negative**:
- Phase names add cognitive overhead for a single-pipeline execution
- B3's dependency on B0 means the auto-install hook cannot be started until the render helper is tested — adds a serialization constraint within Phase B

**Traceability**:
- All 16 REQ IDs are threaded into paired test steps via `Testing` fields
- `traceability.yml` initialized at `.ai-work/praxion-first-class/traceability.yml`
