---
id: dec-231
title: Defer the agentic eval-lens and the full ACH matrix
status: accepted
category: architectural
date: 2026-06-18
summary: The project_profile.yaml-keyed agentic eval-lens and the full ACH matrix are explicitly out of scope for storm-integration; both are recorded as deferred with the signals that would justify revisiting.
tags: [deferral, eval-lens, ach-matrix, project-profile, agentic, storm-integration]
made_by: agent
agent_type: systems-architect
branch: worktree-storm-integration
pipeline_tier: full
affected_files: []
affected_reqs: [REQ-09]
superseded_by: dec-232
dissent: "A reader could argue the agentic eval-lens should ship now because the coverage gap (no multi-perspective eval-coverage check before plan approval) is real today for any managed agentic project. Held minority view: revisit when a managed agentic project actually runs the pipeline and the project_profile.yaml infrastructure exists."
---

## Context

The storm-integration scope explicitly bounded two items OUT: the full ACH matrix, and the agentic eval-lens keyed off `project_profile.yaml`. Recording the deferral with revisit-signals closes the Continuous-Improvement loop on both (disposition: `defer-with-rationale`).

## Decision

Defer both:

1. **Full ACH matrix** — superseded by the DI + two-tier Disconfirmation scheme (dec-232), which covers the deliberation need at lower cost and with better evidence.
2. **Agentic eval-lens** — a pipeline-integrated step that challenges a plan's behavioral assumptions from multiple evaluator perspectives before implementation, routed by `project_profile.yaml` `archetype: agentic_ai`. Deferred because Praxion has no `project_profile.yaml` of its own (it has never run Phase 8f self-onboarding), and the lens is premature without that profile infrastructure and a managed agentic project to exercise it.

## Considered Options

### Option 1 — Build both now
- Con: ACH is superseded; the eval-lens has no profile infrastructure and no consumer to validate against — speculative scope.

### Option 2 — Defer both with recorded revisit-signals (CHOSEN)
- Pro: keeps scope surgical; preserves the signal so the work is not lost.

## Consequences

- Positive: scope stays tight; deferrals are auditable (a future sentinel/promethean pass can pick them up).
- Negative: the agentic eval-coverage gap (apparatus §8) remains open for any agentic project until revisited.

## Prior Decision

This deferral's ACH clause is superseded by dec-232 (DI + Disconfirmation), which is the chosen replacement mechanism. The eval-lens clause stands as a live deferral.

## Disconfirmation (Tier A)

- **Falsifier**: Wrong (on the eval-lens half) if a managed agentic project ships a plan with a behavioral-assumption defect that a pre-implementation multi-evaluator lens would have caught.
- **Steelmanned runner-up (build the eval-lens now)**: The agentic-specific coverage gap is real and named; building the lens now (even without a profile, gated behind explicit invocation) would establish the pattern before the first agentic project needs it, avoiding a scramble.
- **Reversal trigger**: Build the agentic eval-lens when (a) a `project_profile.yaml` with `archetype: agentic_ai` exists in a managed project, OR (b) the first managed agentic project enters the pipeline; reintroduce ACH per dec-232's own reversal trigger.

**Activation:** no — both deferrals are non-actions with no live alternative to weigh at this time; recorded as an ADR to preserve the revisit-signals, not because a choice was contested.
