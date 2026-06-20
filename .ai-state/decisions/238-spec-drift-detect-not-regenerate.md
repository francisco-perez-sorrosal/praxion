---
id: dec-draft-1b2387cf
title: Proactive spec↔artifact drift — detect-and-surface, NOT auto-regenerate
status: proposed
category: architectural
date: 2026-06-19
summary: Adopt Kiro-style proactive spec-change awareness as Praxion's FIRST competitive improvement, but scoped to detect-and-surface drift (reusing traceability edges + sentinel), explicitly excluding Kiro's automatic downstream regeneration to avoid cascade loops and silently-wrong generated artifacts.
tags: [drift, spec-driven, sentinel, traceability, hooks, quality, competitive]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - .ai-work/<slug>/traceability.yml
  - .ai-state/specs/
  - agents/sentinel.md
dissent: "If drift is rare in practice and verifier/sentinel already catch it acceptably, even a detection-only check is ceremony for change that won't come."
---

## Context

Continuous Improvement Signal B (Kiro Agent Hooks) suggests event-driven hooks that
*regenerate* dependent tasks/tests/docs when a spec/design changes. Praxion already detects
spec↔artifact drift but *after the fact*, via verifier/sentinel late in the pipeline. The
user's lens prioritizes quality/process-completeness/reliability per unit effort and
explicitly excludes feature-count chasing. This is the FIRST item in the triage roadmap.

## Decision

Adopt the *proactive-drift-awareness* idea but **scope it to detect-and-surface, not
regenerate.** When a `SPEC_*`/REQ or design artifact changes without its dependent
tasks/tests/docs being touched, a check (a new sentinel dimension and/or a commit-time
guard) **flags the stale dependents with a pointer** and lets a human or the planner
decide. Reuse the dependency edges already encoded in `traceability.yml` (REQ→test/impl)
and the archived `SPEC_*` corpus. **Kiro's automatic regeneration cascade is explicitly
out of scope.**

## Considered Options

### Full Kiro-style cascade: auto-regenerate downstream artifacts on spec edit
Rejected. Auto-generation introduces cascade-loop risk and silently-wrong generated
tests/docs — it trades reliability for automation, the wrong trade under the quality lens.
It also fights Praxion's moat (governed/audited decisions, not autonomous mutation).

### Do nothing — rely on existing verifier/sentinel after-the-fact catch
Rejected (modulo the dissent). Late catch is the dominant silent-correctness failure mode
in spec-driven pipelines; moving detection earlier is the highest quality-per-effort move
available with no external dependency.

### Detect-and-surface using existing traceability + sentinel (chosen)
Lowest risk (read-only), no new dependency, reuses existing dependency edges, and is itself
testable against existing traceability fixtures. Moat-aligned: governance/auditing.

## Consequences

**Positive.** Closes the after-the-fact drift gap; raises process completeness and
reliability; small blast radius (extends sentinel + existing traceability); no external
dependency; testable.

**Negative / accepted.** Detection still requires a human/planner to act on the flag — it
does not auto-fix. Adds one more check to maintain.

## Disconfirmation

- **Falsifier:** measured drift incidents are near-zero in Praxion's pipeline history,
  making even detection-only overhead unjustified.
- **Steelmanned runner-up:** the full Kiro cascade, *with* a loop-guard and human approval
  gate, would save the human the regeneration step entirely — higher automation payoff if
  the loop risk can be contained.
- **Reversal trigger:** detection-only proves consistently followed by tedious manual
  regeneration with low error rate — then a *gated* auto-regeneration step earns its place.
