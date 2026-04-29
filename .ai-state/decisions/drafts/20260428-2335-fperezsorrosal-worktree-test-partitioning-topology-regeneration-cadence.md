---
id: dec-draft-005764a9
title: Topology regeneration is human-initiated or sentinel-triggered, never automatic per-pipeline
status: proposed
category: behavioral
date: 2026-04-28
summary: TEST_TOPOLOGY.md is not regenerated automatically at any pipeline boundary. Refresh is initiated by the user via a future /refresh-topology command, or triggered by the sentinel when 3+ topology-drift ledger rows accumulate. Per-pipeline regeneration would obliterate section ownership and produce a topology diff on every PR.
tags: [test-topology, regeneration, cadence, section-ownership, section-conflict, refresh, sentinel]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - agents/sentinel.md
---

## Context

Open Question 7 from `RESEARCH_FINDINGS.md` §E.4. `TEST_TOPOLOGY.md` is a living document with multi-agent section ownership (systems-architect owns Subsystems table, test-engineer owns per-group definitions, implementation-planner owns per-pipeline integration_boundary additions). The question: should the file be regenerated automatically on some cadence, or only on demand?

Two failure modes:

- **Regenerate per-pipeline**: every PR produces a topology diff; section-ownership semantics are nullified (whoever's process happens to run the regeneration owns the file at that moment); cross-pipeline drift is the norm.
- **Never regenerate**: drift accumulates silently; the topology rots.

## Decision

**No automatic regeneration. Refresh is human-initiated or sentinel-triggered.**

Two refresh mechanisms:

1. **Human-initiated** via a future `/refresh-topology` command (§C.3.2 of `RESEARCH_FINDINGS.md`). The command spawns the implementation-planner in topology-only mode (input: tech-debt-ledger filter `class=topology-drift`, output: revised `TEST_TOPOLOGY.md`). The user invokes this when the drift signal is loud or before a major refactoring pipeline.
2. **Sentinel-triggered** when 3+ `topology-drift` ledger rows accumulate (§C.3.2). The sentinel emits a `### Recommended Actions` line: "Run `/refresh-topology`." This is a recommendation, not an enforcement — the file is not auto-modified.

Routine envelope updates (a single group's `expected_runtime_envelope.p95` changing slightly) do NOT require regeneration. The sentinel TT04 check files a `topology-drift` row for sustained drift; minor noise does not.

Group splits and merges (a `memory-store-core` group becoming `memory-store-core-write` + `memory-store-core-read`) DO require explicit regeneration plus an ADR per the protocol's "topology change is its own decision" rule (§C.3.3).

## Considered Options

### Option A — Auto-regenerate per pipeline

At the start of every Standard/Full-tier pipeline, the planner regenerates `TEST_TOPOLOGY.md` from current filesystem state.

**Rejected.**

**Pros (to be honest):**
- Topology stays in sync with code without human intervention.
- No "is the topology current?" question — it always is.

**Cons (decisive):**
- Section ownership is nullified. The systems-architect's authoritative Subsystems table can be silently rewritten by a planner running on a different concern.
- Every PR includes a topology diff. Reviewers learn to ignore them. The diff signal-to-noise ratio degrades to zero.
- Concurrent pipelines in different worktrees produce conflicting regenerations. Worktree merge becomes painful.
- The schema's optional fields (`expected_runtime_envelope`, `notes`) are human-curated; auto-regeneration would either preserve them (requires an authoritative diff strategy) or wipe them (defeats the purpose).
- The structural risk this creates is large; the structural benefit is small (only catches drift in the simplest cases — file moves, renames — that grep would also catch on every PR).

### Option B — Never regenerate; only manual edits

Topology only changes via manual edits during pipelines.

**Rejected.**

**Pros:**
- Section ownership maximally preserved.

**Cons:**
- Drift accumulates silently. Without a mechanism to surface drift, the topology becomes increasingly out-of-sync with code.
- Human ownership without a forcing function leads to neglect (the well-known maintenance-burden trap from researcher §D.2).

### Option C — Human-initiated + sentinel-triggered (chosen)

**Pros:**
- Preserves section ownership: the file is only changed in the explicit refresh mode (which is itself an implementation-planner pipeline that the user authorizes).
- Drift surfaces via the sentinel, which is the right mechanism for cross-cutting health checks.
- Threshold for triggering (3+ ledger rows) gives the project room to absorb minor drift without ceremony, while preventing rot.
- The `/refresh-topology` command is a user-facing, explicit action — a clean affordance for "the topology needs attention."
- This is the same model as `TECH_DEBT_LEDGER.md` (which is also append-only, with consumer agents updating in place but never auto-regenerating) — an established Praxion precedent.

**Cons:**
- The `/refresh-topology` command must be implemented (in the future M3-or-later pipeline) before the human-initiated path is real. At the moment of this ADR, only the sentinel-triggered surface exists.
- The 3+ row threshold is a number borrowed from intuition; it may need calibration based on observed behavior in consumer projects.

## Consequences

### Positive

- The topology is stable across pipelines unless the user (or a sentinel-surfaced drift) explicitly demands a refresh.
- Section ownership is preserved — the architect's, planner's, and test-engineer's contributions are durable.
- Concurrent pipelines in worktrees do not race on regeneration.
- The refresh-topology workflow has a single, named entry point (the future `/refresh-topology` command) and a single, named trigger (sentinel "3+ drift rows").

### Negative

- Until `/refresh-topology` is implemented, the human-initiated path requires manual editing. Acknowledged; this is acceptable since the protocol's M1 milestone (this pipeline) does not include behavioral activation, so the topology is not yet under heavy maintenance pressure.
- The 3+ threshold is a guess. It might be too lax (drift accumulates uncomfortably) or too strict (the sentinel pesters with every minor envelope change). Calibrate after first M2 lands somewhere.

### Reversibility

The decision is highly reversible per direction:
- Switching to per-pipeline regeneration would require changing the planner's contract; large change but not catastrophic.
- Adjusting the sentinel threshold (3+ rows → 5+, or → 1+) is a one-line change in `agents/sentinel.md`.
- Adding additional triggers (e.g., "any architectural change in `ARCHITECTURE.md` Subsystems table") is additive.

## Prior Decision

None.
