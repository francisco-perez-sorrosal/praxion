---
id: dec-draft-1989de75
title: "Every agent reaps its background work before its final message, through the universal return-contract block"
status: proposed
category: behavioral
date: 2026-10-22
summary: "One sentence added to claude/kernels/src/return-contract.md and regenerated into every definition and kernel: stop or await every background job before the final message, bound every watcher, a process-name watcher must exclude shells"
tags: [agents, kernels, return-contract, background-jobs]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - claude/kernels/src/return-contract.md
  - claude/kernels/core-blocks.md
  - claude/kernels/core.md
  - claude/kernels/index.json
  - agents/implementer.md
  - agents/test-engineer.md
  - skills/software-planning/references/agent-pipeline-details.md
affected_reqs: [REQ-20]
---

# Every agent reaps its background work before its final message, through the universal return-contract block

## Context

td-465. An implementer wrote its final message with its own background runs and an unbounded watcher alive, marking its return possibly interim (td-464); one watcher looped for hours, another matched another session's watcher by process name.

## Decision

Add the context review's sentence to the universal return-contract source and regenerate: every definition and every role kernel carry it identically, enforced by the shared-block gate and the kernel generator's check. A one-line pointer in the agent-pipeline reference names the block as the obligation's home. The switched researcher's kernel gains the sentence: one added core sentence, not a flip or a hold, so its recorded adherence evidence is not re-run. No rule changes (always-loaded budget unchanged).

## Considered Options

### Universal return-contract block (chosen)

Reaches every agent without a roster; gated.

### Edit the two named definitions

Rejected: a roster, two copies, a third agent uncovered.

### A rule or a role-kernel-only text

Rejected: the budget is at 24,800 of 25,000, and kernel-only text reaches only adopted roles.

## Consequences

- Positive: every agent carries the obligation; one source.
- Negative: about 59 tokens per spawn; a prompt instruction, so compliance is not proven by a gate (the step-loop skill's marker rule remains the orchestrator-side backstop).
