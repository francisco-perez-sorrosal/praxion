---
id: dec-084
title: Integration checkpoint runs the full pipeline-tier suite
status: proposed
category: behavioral
date: 2026-04-28
summary: The final integration-checkpoint step in a Standard/Full-tier pipeline runs the full pipeline-tier suite (every pocket, every group), not the more aggressive "touched-pockets-pipeline-tier" optimization. CI minutes are not the binding constraint at Praxion's scale; the full-suite backstop is the protocol's only hard guarantee against false negatives.
tags: [test-topology, integration-checkpoint, tier, ci, false-negatives]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - agents/verifier.md
---

## Context

Open Question 3 from `RESEARCH_FINDINGS.md` §E.4. The integration-checkpoint step is the final step in a Standard/Full-tier pipeline before the verifier handoff. Today it runs the full test suite per `agents/implementer.md` step 6 ("MANDATE the *full* suite at integration checkpoint, regardless of step scope" — researcher §0). The protocol introduces tier semantics; the question is whether the checkpoint runs:

- **Option X (default in §C.5)**: full pipeline-tier — every pocket, every group, regardless of what the pipeline touched.
- **Option Y (more aggressive)**: "touched-pockets-pipeline-tier" — run pipeline-tier only over the pockets that any step in this pipeline modified, plus their integration_boundaries.

## Decision

**Option X — full pipeline-tier suite.** Match today's behavior. The aggressive variant is rejected as a premature optimization.

## Considered Options

### Option X — Full pipeline-tier (chosen)

Every pocket runs in full at the integration checkpoint, regardless of what the pipeline touched.

**Pros:**
- **Acts as the protocol's hard floor against false negatives.** The researcher's §D.1 enumerates three concrete false-negative vectors (cross-pocket import not declared as `integration_boundaries`, hidden global state, fixture contamination in shared `conftest.py`). The integration checkpoint is the absolute backstop that catches all three. Narrowing it weakens the protocol's safety guarantee.
- Matches today's behavior — no change to the implementer's step 6 mandate. Backward compatible with existing pipelines that have not adopted topology yet.
- Composes cleanly with the topology being incomplete or stale: even if `integration_boundaries` for some group is wrong, the checkpoint's full run catches the resulting regression.
- CI matrix parallelism (the `pytest-xdist` per-pocket parallel + GitHub Actions matrix across pockets) bounds the wall-clock at the slowest pocket (today: task-chronograph-mcp at 17.8 s). The full-suite cost is therefore not the sum, just the slowest path. This makes "savings from narrowing" a small absolute number for projects at Praxion's scale.

**Cons:**
- Larger projects (10K+ tests, 30+ pockets) might find the full-suite checkpoint cost-prohibitive. Acknowledged; the option is reversible per below.

### Option Y — Touched-pockets-pipeline-tier

Run pipeline-tier only over pockets that any step in this pipeline modified, plus their `integration_boundaries` closure.

**Rejected.**

**Pros (to be honest):**
- Faster CI feedback for pipelines that touch only one pocket. At Praxion's scale, ~17 s saved if a pipeline touches only memory-mcp (1.7 s) and not task-chronograph-mcp.
- Aligns with the per-pipeline tiering philosophy of the rest of the protocol.

**Cons (decisive):**
- The first false-negative the protocol fails to catch in production becomes an outage / rollback. The full-suite backstop is the cheapest possible insurance against this.
- "Touched pockets" is computed from the pipeline's step `Files` field — a planner-derived set. If the planner missed a file in step decomposition, the touched-pockets set is wrong, and the integration checkpoint silently narrows.
- The integration_boundaries closure is one-hop per ADR `dec-084`'s sibling decision (in the SYSTEMS_PLAN). Multi-hop coupling that the topology has not yet mapped becomes invisible. The full-suite floor is the only mechanism that catches multi-hop coupling without requiring the topology to be perfect.
- The optimization is reversible — a project that demonstrably suffers from the full-suite cost can adopt Option Y in a future ADR. The reverse (going from "we had Option Y in production" to "we now need Option X because we found false negatives") is harder, since by then the protocol is trusted.
- "Premature optimization" is the dominant axis at Praxion's scale (1,623 tests, 35 s aggregate). Optimizing the integration checkpoint is solving a problem that does not yet exist.

## Consequences

### Positive

- The protocol's safety floor is preserved at full strength.
- No new failure modes introduced at the integration checkpoint.
- The verifier's check ("integration-checkpoint final step recorded `Tier=pipeline`") remains a single, unambiguous validation.
- Backward compatibility with pre-topology pipelines: a pipeline that does not yet declare `Tests:` fields runs the full suite at the checkpoint by default; the protocol's runtime selector treats absent `Tests:` as `tier=pipeline`.

### Negative

- A project with a 30+ pocket layout would pay larger CI minutes than necessary at the checkpoint. Acknowledged; that project's architect can propose a follow-up ADR with measured data.
- The full-suite cost grows linearly with test count, while the touched-pockets cost grows only with pipeline scope. Long-term, very large projects may need to revisit this. Reversible.

### Reversibility

Highly reversible. A future ADR can introduce Option Y additively: a new optional field `integration_checkpoint_scope: <full | touched_pockets>` in the trunk schema's project-level config block, defaulting to `full`. Projects that opt in get the narrower behavior; projects that don't keep today's safety floor.

## Prior Decision

None.
