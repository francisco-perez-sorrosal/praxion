---
id: dec-draft-620b4085
title: Raise the per-tier spawn budgets to Standard 16 / Full 32
status: proposed
category: configuration
date: 2026-10-01
summary: "The charged-spawn budgets of the per-tier pipeline envelope double, from Standard ≤ 8 / Full ≤ 16 to Standard ≤ 16 / Full ≤ 32. The counting rule (first start plus heavy resume), the read-before-spawn duty and the never-meet-the-budget-by list are unchanged."
tags: [spawn-budget, process-economy, pipeline, coordination-protocol, calibration]
made_by: user
agent_type: orchestrator
branch: main
pipeline_tier: direct
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
affected_reqs: []
supersedes_in_part: [dec-394]
---

## Context

dec-394 set the charged-spawn budgets from two calibration rows, and named its own reversal trigger: a single Standard plan whose minimum spawn need exceeds the cap. Since then, the acceptance-design stage (dec-409) added one charged spawn to every Standard and Full pipeline, and three pipelines ran against the caps:

- test-refresh-core (Full) and acceptance-independence (Standard, run as Full) both reached 16 of 16, with agents hitting turn caps and resuming.
- selection-gaps-dogfood (Standard) planned exactly 8 of 8 (architect, acceptance designer, planner, four implementers, verifier) with no slack. It fit only because the orchestrator authored three plan steps and two spec amendments itself to avoid charged spawns.

The planned work ahead is more complex than any of these, so the cap now binds before quality concerns do, and it pushes work onto the orchestrator, whose context is the one the envelope exists to protect.

## Decision

Standard ≤ 16 and Full ≤ 32 charged spawns. Everything else in dec-394's budget rule stands: a charged spawn is a first start or a resume into a context of 250k tokens or more; the orchestrator reads the count before each spawn and records the tally in the calibration row; the budget is never met by unpairing a side-effect step or skipping the verifier, and an overrun stops for a re-tier or a split.

## Considered Options

### Standard 12 / Full 24

- Pro: covers the acceptance designer, one fix loop and one rework while keeping a firm brake.
- Con: the dogfood run would have used about 11 without orchestrator authoring, leaving little room for the complex tasks the user plans.

### Standard 10 / Full 20

- Pro: the smallest change that clears the acceptance-stage spawn.
- Con: orchestrator authoring stays a routine budget workaround.

### Standard 16 / Full 32 (chosen)

- Pro: complex pipelines can delegate every step, fix loop and rework without workarounds; Full stays twice Standard.
- Con: a weaker brake on runaway pipelines. The re-tier/split duty and the calibration-row tally remain the brake.

## Consequences

- Positive: steps go to the agents built for them instead of to the orchestrator.
- Negative: a pipeline can now spend twice as many agent contexts before the rule stops it.
- Neutral: the numbers rest on three pipelines and a user decision about upcoming work, not on telemetry. spawn_count.py undercounted in two of those pipelines (missing agent_start rows when the session cwd was a subdirectory), so the measured spawn counts behind this decision come from manual tallies.

## Prior Decision

dec-394 stays accepted. Only its budget numbers (Standard ≤ 8 / Full ≤ 16) are narrowed here; the artifact floor, the spawn-count instrument, the counting rule and the calibration reminder are unchanged.
