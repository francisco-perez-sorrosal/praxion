---
id: dec-193
title: Test-topology M2 — behavioral agent wiring plus advisory growth trigger
status: re-affirmation
category: architectural
date: 2026-05-19
summary: "Ship M2 of the test-topology protocol — wire all pipeline agents to author and honor TEST_TOPOLOGY.md and the per-step Tests field, add an advisory growth trigger in the sentinel and the systems-architect, and ship the /refresh-topology command. Re-affirms dec-090 (no automatic per-pipeline regeneration); dec-087's pilot deferral remains in force, unchanged by this decision."
tags: [test-topology, m2, agent-wiring, growth-trigger, behavioral-activation, re-affirmation]
made_by: agent
agent_type: systems-architect
branch: worktree-test-topology-activation
pipeline_tier: full
re_affirms: dec-090
affected_files:
  - agents/sentinel.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - skills/testing-strategy/references/test-topology.md
  - skills/testing-strategy/SKILL.md
  - commands/refresh-topology.md
  - claude/config/CLAUDE.md
  - rules/swe/agent-intermediate-documents.md
affected_reqs: [REQ-01, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-16, REQ-17]
---

## Context

The test-topology protocol shipped trunk-only at M1: the schema, the sentinel TT01–TT05 checks, the `topology-drift` ledger class, the `Tests:` field document conventions. M1 deliberately deferred the "behavioral pilot" to the first consumer project — but that deferral *assumed the shipped agents were already capable of group selection*. They are not. M1 never updated any agent definition to read or write `TEST_TOPOLOGY.md` or to consume the `Tests:` step field. A consumer project (`francisco`) hand-built a 17-group topology inside an explicit re-architecture pipeline — nothing in Praxion triggered it, and the project's pipeline agents could not use it.

Two confirmed gaps: **GAP A** — no growth trigger; nothing watches project growth and proposes adopting a topology. **GAP B** — agents not wired; the `Tests:` field is documented but consumed by no agent, and the three section-ownership assignments in `rules/swe/agent-intermediate-documents.md` point at agents whose definitions never mention the file (a live coherence break).

This decision closes the M1 implementation gap. It does not reverse the pilot deferral and does not introduce automatic regeneration.

## Decision

Ship M2 of the test-topology protocol as a single coordinated change:

1. **Behavioral agent wiring.** Add conditional clauses to six agent definitions, each gated on "the project has a populated `.ai-state/TEST_TOPOLOGY.md`":
   - `systems-architect` — authors the `## Subsystems` cross-reference table; performs the in-pipeline growth-readiness check in Phase 2.
   - `implementation-planner` — authors `Tests:` step fields and maintains the per-group `integration_boundaries` it owns.
   - `implementer` — translates a step's `Tests:` field into a scoped runner invocation via the project's language leaf.
   - `test-engineer` — authors the per-group YAML blocks it owns.
   - `verifier` — checks that declared `Tests:` tiers were consistent with the breadth of subsystems each step touched.
   - `sentinel` — adds the periodic advisory growth trigger.
2. **Advisory growth trigger** — sentinel (periodic, project-wide) and systems-architect Phase 2 (in-pipeline, actionable). Both *propose* `/refresh-topology --init`; neither auto-creates a topology. Advisory only.
3. **`/refresh-topology` command** — `--init` mode creates a topology from scratch (spawns architect + test-engineer); default mode performs the drift-response refresh (spawns the implementation-planner in topology-only mode).
4. **Language-agnosticism preserved** — agents reference the trunk (`test-topology.md`) for the schema and `Tests:` contract, and load the per-language leaf (`references/<lang>-testing.md`) for concrete invocation. Where no leaf exists for a project's language, the agent Registers Objection rather than silently running the full suite or inventing a selector.

**dec-087 (pilot deferral) remains in force.** Praxion itself still does not populate its own `.ai-state/TEST_TOPOLOGY.md`. M2 makes the protocol *usable* by any consumer project; it does not make Praxion a pilot. The pilot deferral is unchanged by this decision — see `## Prior Decision`.

**Re-affirmation of dec-090 (no automatic per-pipeline regeneration).** The growth trigger is advisory; `/refresh-topology` is the only mutation path. No agent regenerates `TEST_TOPOLOGY.md` at a pipeline boundary. The three-way section ownership the regeneration-cadence decision protects is honored by every agent clause. The `--init` path *extends* the regeneration model with an initial-creation operation the cadence decision did not cover — initial creation (create the sections) is genuinely distinct from drift-response refresh (reconcile existing sections) — but it does not contradict it: `--init` is only ever human-initiated.

## Considered Options

### Option 1 — Wire only the implementer and planner (partial)

Wire the two agents that run and schedule tests; leave the architect, test-engineer, and verifier untouched.

- Pro: smaller change.
- Con: the four pipeline agents form one handoff chain — architect authors the Subsystems table → planner authors `Tests:` fields and `integration_boundaries` → implementer/test-engineer run scoped invocations and author groups. A partial wiring ships a half-working protocol: the planner would author `Tests:` fields against a Subsystems table no agent maintains. Rejected.

### Option 2 — Full M2 in one pass (chosen)

Wire all six agents, add the growth trigger, ship `/refresh-topology`, in one coordinated change.

- Pro: the protocol becomes coherently usable end-to-end; the section-ownership coherence break is closed.
- Con: larger change surface — but every edit is an additive conditional clause; non-topology projects see zero behavior change.

### Option 3 — Pilot in Praxion to force the wiring (reverse dec-087)

Populate Praxion's own `TEST_TOPOLOGY.md` and let the pipeline exercise the wiring.

- Pro: real integration test of the wiring.
- Con: Praxion's full test fleet runs in ~35 s — scoped invocation saves nothing here, and the topology groups would recapitulate the whole repo rather than map to real subsystems (the anti-pattern dec-087's Option-3 analysis rejected). Rejected; pilot deferral re-affirmed.

## Consequences

**Positive:**
- The test-topology protocol is behaviorally complete and usable by any consumer project that grows past the adoption thresholds.
- The `rules/swe/agent-intermediate-documents.md` section-ownership coherence break is closed — the three named agents now reference the file.
- Purely additive: every clause is gated on a populated topology, so non-topology projects (including Praxion) are unchanged. Rollback is reverting Markdown edits.

**Negative:**
- Six agent definitions grow by a conditional clause each — a small, bounded increase in agent-prompt size.
- The protocol's behavior is now spread across six agents plus a command; the single-source-of-truth discipline (the `Tests:` schema lives only in the trunk reference) is load-bearing — drift between agent clauses would break the handoff chain.

**Neutral:**
- Praxion still does not dogfood the protocol; the first real integration test happens in a consumer project. This is the deliberate, re-affirmed pilot posture.

## Prior Decision

**dec-087 (pilot strategy — trunk-only, defer behavioral pilot)** remains in force — unchanged by this decision, and not formally re-affirmed: dec-087 was not re-opened or challenged here, only its scope boundary restated. dec-087 deferred the behavioral pilot to "the first consumer project." This task builds the *capability* that deferral presupposed — it does not start a Praxion pilot. Praxion still ships no populated `TEST_TOPOLOGY.md`. The evidence that would justify revisiting the pilot deferral: a Praxion-internal subsystem set whose isolated test runtime grew past the adoption thresholds — not the case today (~35 s fleet).

**dec-090 (topology regeneration is human-initiated or sentinel-triggered, never automatic per-pipeline)** is re-affirmed, not superseded. The M2 growth trigger is advisory and the `/refresh-topology` command is the sole mutation path; no per-pipeline auto-regeneration is introduced. The `--init` mode is an *addition* to the regeneration model (an initial-creation path the cadence decision did not enumerate), consistent with its core principle that section ownership must never be obliterated by an automatic regenerator. The evidence that would justify a future supersession: a demonstrated need for automatic per-pipeline regeneration that does not destroy section ownership — no such mechanism exists or is proposed.
