---
id: dec-236
title: Decline verified merge queue (Gastown Refinery) at Praxion's target operating point
status: accepted
category: architectural
date: 2026-06-19
summary: Decline adopting a Bors-style bisecting verified merge queue; it solves an autonomous-20-30-agent-scale problem Praxion deliberately does not have. finalize-at-merge + worktree isolation + verifier rework loop already gate quality for human-in-the-loop, low-concurrency operation.
tags: [merge-queue, refinery, gastown, scope, simplicity, competitive]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files: []
dissent: "If Praxion ever raises its autonomous-concurrency ceiling well beyond a few human-supervised worktrees, a verified merge queue stops being ceremony and starts paying for itself."
---

## Context

The competitive evaluation surfaces Gastown's Refinery (Bors-style bisecting verified merge
queue) as a softer Continuous Improvement Signal, and Open Question 3 asks whether
verified-merge-queue discipline is in scope given Praxion's finalize-at-merge + worktree
model. The user's lens explicitly excludes feature-count parity.

## Decision

**Decline** adopting a verified merge queue for Praxion's target operating point. Refinery
exists to verify merges from 20–30 *autonomous* agents that cannot push to main. Praxion is
deliberately **human-in-the-loop, 2–3 concurrent worktrees**, and already gates output
quality via finalize-at-merge, worktree isolation, and the verifier rework loop. A bisecting
merge queue would add significant machinery for near-zero quality return at this scale —
ceremony for a change that won't come.

## Considered Options

### Adopt a Bors-style bisecting verified merge queue
Rejected at target scale. High effort; the failure mode it addresses (bad merges from many
uncontrolled autonomous pushers) does not arise when humans supervise a handful of worktrees
and the verifier already gates.

### Decline; rely on existing finalize-at-merge + worktree + verifier (chosen)
The current model is sufficient for the operating point. Declining keeps the system lean and
focuses effort on quality-raising work that is *not* scale-gated (drift detection, memory).

## Consequences

**Positive.** Avoids substantial machinery with no quality payoff at target scale; keeps the
focus on lens-aligned improvements.

**Negative / accepted.** Praxion remains unsuited to massive autonomous-agent concurrency —
an intentional non-goal, not a regression.

## Disconfirmation

- **Falsifier:** bad merges become a measurable quality problem at Praxion's current
  concurrency (i.e. the verifier + worktree gates demonstrably miss merge-level defects).
- **Steelmanned runner-up:** even at low concurrency, a merge queue gives CI-grade,
  auto-bisected merge verification that catches integration breaks the per-worktree verifier
  can't see across branches.
- **Reversal trigger:** Praxion raises its autonomous-concurrency ceiling well beyond a few
  human-supervised worktrees — revisit immediately.
