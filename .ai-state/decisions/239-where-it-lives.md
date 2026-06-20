---
id: dec-draft-3ffc5719
title: Spec-drift detection lives in a shared module with two consumers — sentinel check + pipeline checkpoint, NOT a git hook
status: proposed
category: architectural
date: 2026-06-19
summary: Place proactive spec↔artifact drift detection in one side-effect-free detector module consumed by (A) a new sentinel SH07 check over archived specs and (B) the orchestrator's pre-verification checkpoint over in-flight traceability.yml — rejecting a git/PreToolUse hook because drift is a pipeline-state question that a commit-time gate gets wrong (partial-commit false positives) and that a checkpoint already answers correctly.
tags: [drift, spec-driven, sentinel, traceability, hooks, checkpoint, quality, competitive]
made_by: agent
agent_type: systems-architect
branch: feat-spec-drift-detection
pipeline_tier: standard
re_affirms: dec-draft-1b2387cf
affected_files:
  - scripts/spec_drift.py
  - agents/sentinel.md
  - skills/spec-driven-development/references/sentinel-spec-checks.md
  - skills/software-planning/references/coordination-details.md
affected_reqs: []
dissent: "If in-flight drift is rare and the sentinel's post-hoc SH backstop already catches it acceptably, the in-flight checkpoint consumer is ceremony — a single sentinel dimension would suffice."
---

## Context

`dec-draft-1b2387cf` ratified that Praxion adds proactive spec↔artifact drift detection, scoped to **detect-and-surface, not regenerate**. It left ONE architectural fork open: *where does detection live* — (1) a new sentinel dimension, (2) a git-commit / PreToolUse hook, or (3) both via a shared module.

The drift that today's surfaces catch *late* is intra-pipeline: a `SPEC_*`/REQ or design artifact changes while the dependent tests/impl/docs in `.ai-work/<task-slug>/traceability.yml` are not correspondingly touched. The sentinel only ever sees *archived* specs (post-pipeline); the verifier catches it at end-of-pipeline. The genuine gap is **in-flight, before the verifier**. The decision lens is quality / reliability / leanness per unit effort.

## Decision

Detection lives in **one side-effect-free detector module** (`scripts/spec_drift.py`) with **two thin consumers**:

- **Consumer A — sentinel check `SH07`**: runs the module over archived `.ai-state/specs/SPEC_*.md`; periodic post-hoc backstop, conditional-activation (TT-idiom) when no specs exist.
- **Consumer B — orchestrator pre-verification checkpoint**: runs the module over the live `traceability.yml` + in-flight `SYSTEMS_PLAN.md`/`SPEC_DELTA.md`, surfacing a `### Spec Drift` subsection in the curated digest **before** the verifier is spawned. Advisory; never blocks.

A **git-commit / PreToolUse hook is explicitly rejected.**

## Considered Options

### Option 1 — Sentinel dimension only
Lean and read-only, but post-hoc: the sentinel sees only archived specs, so it cannot catch the in-flight drift that is the actual gap. Insufficient alone.

### Option 2 — git-commit / PreToolUse hook (rejected)
Earliest possible trigger, but the **wrong granularity**. Drift is meaningful only relative to a *declared-complete pipeline phase*; commits inside a pipeline are intentionally partial (spec lands in one commit, tests in the next), so a commit-time gate fires on legitimate work-in-progress → false positives → desensitization. It also imposes per-commit cost and opt-out plumbing on every managed project, including those with no `traceability.yml` at all. Heavy and noisy — the opposite of lean.

### Option 3 — Shared module + two consumers (chosen)
One detector module; sentinel and the orchestrator are thin callers. Gets the *earliness* of a hook (Consumer B fires at the pre-verification checkpoint, before the verifier) WITHOUT the partial-commit false-positive tax, because the checkpoint is reached only when a phase is declared complete — a pipeline-state-aware moment a hook cannot know. The sentinel consumer is a near-free periodic backstop sharing the same logic. Single source of truth prevents the two surfaces from drifting apart.

## Consequences

**Positive.** Closes the in-flight drift gap strictly earlier than the verifier; reuses existing traceability edges + the existing checkpoint + `TEST_BASELINE.md` base SHA; zero new always-loaded surface; one logic site; fully unit-testable (pure module). Moat-aligned: detection at a governed decision point, not autonomous gating.

**Negative / accepted.** Two call sites to maintain instead of one. Residual false-positive risk on pure refactors, mitigated by clause-level diffing, WIP-step sequencing suppression, and advisory-only severity. Detection still requires a human/planner to act on the flag (inherited from `dec-draft-1b2387cf`'s scope).

## Disconfirmation

- **Falsifier:** if in-flight drift incidents are near-zero in pipeline history, Consumer B is unjustified overhead and Option 1 (sentinel-only) would have sufficed.
- **Steelmanned runner-up:** Option 1 alone — the sentinel's existing SH dimension is already the home of spec-health checks; adding SH07 there and *nothing else* is maximally lean, and if the post-hoc catch is "good enough" the in-flight checkpoint wiring is pure ceremony. The chosen design bets that *earlier-than-verifier* is worth two call sites; if that bet is wrong, drop Consumer B and keep SH07.
- **Reversal trigger:** if Consumer B's in-flight findings prove to be a strict subset of what the verifier already surfaces moments later (no drift caught meaningfully earlier across several pipelines), retire Consumer B and run detection sentinel-only.
