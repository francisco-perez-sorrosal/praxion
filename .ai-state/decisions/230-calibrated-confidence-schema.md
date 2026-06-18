---
id: dec-230
title: Calibrated-confidence schema uses verbal tiers anchored to numeric ranges plus GRADE downgrade factors
status: accepted
category: behavioral
date: 2026-06-18
summary: Confidence is expressed as high (>80%) / med (40-80%) / low (<40%) with GRADE-style downgrade basis, defined once in the multi-perspective-analysis skill and applied to verifier findings and per-claim researcher annotations.
tags: [confidence, calibration, grade, sherman-kent, verifier, researcher, storm-integration]
made_by: agent
agent_type: systems-architect
branch: worktree-storm-integration
pipeline_tier: full
affected_files:
  - skills/multi-perspective-analysis/references/calibrated-confidence.md
  - agents/verifier.md
  - agents/researcher.md
affected_reqs: [REQ-06]
---

## Context

Praxion expresses confidence verbally (`high|medium|low`) in the verifier finding schema, and the researcher has no per-claim certainty annotation at all. Sherman Kent's Words-of-Estimative-Probability evidence (DECISION §5) shows pure verbal terms produce ~40-percentage-point inter-reader variance ("probable" = 50% to one reader, 90% to another). GRADE (EVIDENCE §1) provides a validated five-factor downgrade scheme reusable for software evidence.

## Decision

Define a single calibrated-confidence schema in `skills/multi-perspective-analysis/references/calibrated-confidence.md`: verbal tiers anchored to numeric ranges — `high (>80%)`, `med (40–80%)`, `low (<40%)` — plus GRADE-recast downgrade factors (risk-of-bias→source-tier, inconsistency, indirectness, imprecision, publication-bias). Apply it to (a) the verifier `confidence` finding field (anchors added, keyword back-compatible) and (b) a new researcher per-claim `[certainty: …]` annotation scoped to comparative/divergent claims. Forward-compatible with plain-numeric when a resolution loop exists.

## Considered Options

### Option 1 — Keep pure-verbal `high|med|low`
- Con: ~40-point inter-reader variance (Kent); unbounded miscommunication in high-stakes hand-offs.

### Option 2 — Verbal anchored to numeric + GRADE downgrade factors (CHOSEN)
- Pro: matches Kent's original proposal; bounds communication variance; low authoring cost; forward-compatible.

### Option 3 — Pure-numeric probability + Brier calibration loop
- Con: pseudo-precision without resolved-outcome feedback (Superforecasting requires resolution); Praxion lacks an ADR-outcome scoring loop today.

## Consequences

- Positive: bounded inter-reader variance; one source of truth cited by verifier + researcher; clean upgrade path to numeric calibration later.
- Negative: anchors are self-assessed (no oracle) — bounds *communication* variance, not calibration accuracy; acceptable because communication variance is the proven, present problem.

**Activation:** no — single plausible path on the evidence (verbal+numeric anchor is the unambiguous DECISION/EVIDENCE recommendation); category behavioral, low blast radius. Recorded as an ADR because it changes two agent contracts and defines a reused schema.
