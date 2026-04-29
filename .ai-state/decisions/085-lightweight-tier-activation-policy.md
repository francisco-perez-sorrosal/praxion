---
id: dec-085
title: Test-topology protocol does not activate at Lightweight tier; escalation path is the sole exit
status: proposed
category: behavioral
date: 2026-04-28
summary: The test-topology protocol activates at Standard and Full tiers only. Lightweight tier (2-3 files, single behavior, clear scope) does not derive groups, does not consult TEST_TOPOLOGY.md, does not emit per-group results. If a Lightweight task touches more than one group's worth of behavior, the existing escalation-to-Standard rule (no scope creep) is the only exit; the protocol does not silently activate mid-Lightweight.
tags: [test-topology, lightweight-tier, calibration, scope-discipline, ux]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - rules/swe/swe-agent-coordination-protocol.md
---

## Context

Open Question 5 from `RESEARCH_FINDINGS.md` §E.4. Lightweight tier in Praxion's process calibration (per `rules/swe/swe-agent-coordination-protocol.md`) is "2-3 files, single behavior, clear scope" — optional researcher only, acceptance criteria inline, no canonical artifacts beyond what already exists. The tier's identity is "minimal overhead for small changes."

The question: should the test-topology protocol activate when a Lightweight task happens to touch more than one group's worth of files? §C.5 said "manual at Lightweight" but flagged the boundary as fuzzy.

Two failure modes to weigh:

- **Activate at Lightweight**: a Lightweight task that touches a hooks file might activate group derivation, marker validation, and the `Tests:` field protocol — turning a 30-minute fix into a 2-hour exercise. This violates Lightweight's identity.
- **Never activate at Lightweight, even when scope grows**: a Lightweight task that should have been Standard silently runs without test-tier discipline. False negatives could escape into a merged change.

## Decision

**The test-topology protocol does NOT activate at Lightweight tier.**

Specifically:

- The implementation-planner does NOT emit `Tests:` field on Lightweight steps (Lightweight does not produce `IMPLEMENTATION_PLAN.md` at all per current process).
- The implementer/test-engineer at Lightweight uses the project's default test command (e.g., `uv run pytest`) without group selection.
- `TEST_RESULTS.md` is not created at Lightweight (canonical schema applies only when written).
- Sentinel TT01–TT05 do not count Lightweight pipelines toward their statistics.

**The escalation path is the sole exit when scope grows.** This is not a new mechanism — `rules/swe/swe-agent-coordination-protocol.md` already states: "Lightweight scope that grows mid-task beyond 3 files or requires architect/planner input must stop and re-scope to Standard rather than silently expanding; escalation is a controlled transition, not creep."

The architect's contribution here is to confirm that "test-topology engagement" is a Standard-tier capability, not an automatic upgrade trigger from Lightweight. If Lightweight scope grows to N groups in N pockets, that's an escalation to Standard for *all* Standard-tier reasons, not just for the test-topology reason.

## Considered Options

### Option A — Activate at Lightweight when 2+ groups are touched

The planner counts how many groups the touched files map to; if >1, activate group selection.

**Rejected.**

**Pros (to be honest):**
- Captures the false-negative case automatically — a Lightweight task that touches multiple groups gets group-aware testing.

**Cons (decisive):**
- Lightweight identity erodes. The tier's value proposition is "minimal overhead." Silent activation of test-topology mechanics inside Lightweight breaks that contract.
- The 2+-groups detection requires consulting `TEST_TOPOLOGY.md`, which Lightweight tasks otherwise do not touch. New coupling for the Lightweight tier.
- The "escalation to Standard" path already handles the multi-group case at the right level. Adding test-topology-specific escalation duplicates the broader scope-creep discipline.

### Option B — Activate always, but degrade gracefully when topology is absent

The protocol always tries to derive groups; if `TEST_TOPOLOGY.md` doesn't exist, the protocol is a no-op.

**Rejected (for Lightweight).**

This is actually the trunk's general behavior — the protocol degrades to today's behavior when topology data is missing. But for Lightweight specifically, "trying to derive groups" still implies the planner running through derivation logic, which Lightweight doesn't have a planner for. The cleanest answer is that test-topology is a Standard-and-up capability.

### Option C — Off at Lightweight, always; escalation handles scope creep (chosen)

**Pros:**
- Lightweight identity is preserved.
- No new coupling between Lightweight and `TEST_TOPOLOGY.md`.
- Existing escalation discipline carries the burden — a tested mechanism, not a new one.
- The planner agent (which is the only consumer of `TEST_TOPOLOGY.md` at the planning stage) is a Standard-tier agent. Lightweight does not invoke it. So this decision is consistent with the existing tier-agent map.

**Cons:**
- A Lightweight task that touches a cross-pocket bridge file (e.g., `hooks/inject_memory.py`) and that should have been Standard but was incorrectly classified as Lightweight will run without test-topology discipline. The integration checkpoint full-suite at the Lightweight task's CI run still catches the regression — but per current Lightweight conventions, Lightweight tasks may not run a full integration checkpoint. Acknowledged risk.

## Consequences

### Positive

- Lightweight tier identity is preserved.
- No new code, no new schema fields, no new convention to teach for the 80%+ of tasks that pass through Lightweight tier.
- Sentinel TT statistics are clean (Standard-and-up only) — no noise from Lightweight tasks polluting drift signals.

### Negative

- Lightweight tasks that touch cross-pocket bridges run with today's default test command. The test-topology protocol's safety floor (the integration-checkpoint full suite) is not part of Lightweight's process. Mitigation: the calibration log captures tier-selection accuracy; if Lightweight regressions become observable, the calibration system is the right tool to address it.

### Reversibility

Easily reversible. A future ADR could activate test-topology at Lightweight in a watered-down form (e.g., "if the touched files map to a known group, use that group's marker but skip the planner's `Tests:` field derivation"). The change would be additive; M1 artifacts remain valid.

## Prior Decision

None.
