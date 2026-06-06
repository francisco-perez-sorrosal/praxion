---
id: dec-218
title: Reconcile the ML experiment-storage convention onto the unified out-of-tree model
status: accepted
category: architectural
date: 2026-06-05
summary: Migrate the in-tree ML experiment conventions onto the out-of-tree storage model so one storage model serves all experiment/eval-bearing projects (user-approved 2026-06-05); migration runs as its own pre-refactor sub-pipeline.
tags: [storage, ml-training, reconciliation, migration, pre-refactor, run-store, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - rules/ml/experiment-tracking-conventions.md
  - rules/ml/experiment-commit-conventions.md
  - commands/onboard-project.md
  - skills/experiment-tracking/SKILL.md
related: [dec-221]
---

## Context

The unified out-of-tree storage model (`dec-221`) defaults operational artifacts out
of the repo tree. The existing ML scaffold diverges on two layers (verified against current
conventions):

- Heavy operational (`runs/`, `checkpoints/`, `mlruns/`) → in working tree, gitignored
  (Phase 8c.2).
- Per-run trace (`experiments/<run-tag>/config.yaml`, `metrics.jsonl`) → in working tree,
  **committed** (`experiment-tracking-conventions.md` + `experiment-commit-conventions.md`).
- Already aligned: `TRAINING_RESULTS.md` (committed summary), `.ai-state/experiments/` +
  `gpu_budget.yaml` (committed config).

Two storage models for one artifact class (experiment/eval runs) is a structural inconsistency.

## Decision

**DECISION: migrate (Option A) — APPROVED by user 2026-06-05.** Unify both branches on the out-of-tree default — heavy
artifacts *and* per-step traces (`metrics.jsonl`) move to `$HOME/.<project-name>/` or a tracker;
commit only the curated summary (`TRAINING_RESULTS.md`) + config. This converges the ML and
agentic-eval branches to a single storage model.

**Objection on record (per task brief, Register Objection):** maintaining two storage models for
the same artifact class is worse than one. Divergence (Option B) is acceptable *only* with an
explicit stated rationale — it must not be the default outcome.

**Blast radius (assessed):** touches 4+ shipped surfaces — `experiment-tracking-conventions.md`,
`experiment-commit-conventions.md`, onboarding Phase 8c.1/8c.2, and the `experiment-tracking`
skill. Existing managed ML projects rely on the in-tree committed-trace convention, so a
behavior-preservation concern exists (committed `experiments/<run-tag>/` traces must keep
resolving, or a documented one-time migration step is provided).

**`PRE_REFACTOR_PLAN.md` flag:** because the migration is multi-file with real
behavioral-preservation risk and is a distinct architectural concern from the additive P1–P6 work,
a `PRE_REFACTOR_PLAN.md` is **likely warranted** when this decision is greenlit. Per the
design-pass guardrails it is **flagged, not produced** here. The migration must run as its own
sub-pipeline (characterization tests first), not bundled into the additive program.

## Considered Options

### A — Migrate ML conventions onto the out-of-tree model (RECOMMENDED)
- Pros: one storage model for all experiment/eval-bearing projects; out-of-tree default is
  strictly better than committing per-run traces in-tree.
- Cons: changes shipped conventions; real blast radius; needs back-compat for existing projects.

### B — Keep ML divergent, document the rationale
- Pros: zero blast radius on shipped ML conventions; no migration risk.
- Cons: two storage models persist; future readers and the archetype scaffold must understand
  both; the inconsistency is permanent. Requires a stated reason on record.

## Consequences

- **If A (migrate):** the storage-model ADR (`dec-221`) supersedes the in-tree
  committed-trace convention; `experiment-commit-conventions.md` and Phase 8c.1/8c.2 are rewritten;
  a one-time migration note ships for existing managed ML projects.
- **If B (diverge):** `dec-221` is scoped to agentic-eval only and explicitly carves
  out ML; this ADR records the divergence rationale.
- **RESOLVED — user approved migrate (2026-06-05).** `dec-221` (unified storage model)
  therefore **supersedes** the in-tree committed-trace convention (it should be tightened from
  conditional "if A/if B" scoping to the migrate outcome when the program enters implementation).
  The ML migration is gated on a `PRE_REFACTOR_PLAN.md` and runs as its own pre-refactor
  sub-pipeline (characterization tests first), not bundled into the additive P1–P6 work.
