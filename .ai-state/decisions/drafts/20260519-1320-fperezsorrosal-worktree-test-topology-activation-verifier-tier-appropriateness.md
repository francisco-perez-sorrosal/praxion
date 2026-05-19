---
id: dec-draft-7ab209cf
title: Verifier validates scoped-test tier-appropriateness as a document cross-check, not a re-run
status: proposed
category: behavioral
date: 2026-05-19
summary: "The verifier checks that each topology-scoped step's declared Tests tier was consistent with the breadth of subsystems the step touched, by cross-referencing the step's file footprint against TEST_TOPOLOGY.md — a document/diff check, not a test re-execution. Mismatches produce a WARN."
tags: [test-topology, verifier, tier-appropriateness, scoped-tests, behavioral]
made_by: agent
agent_type: systems-architect
branch: worktree-test-topology-activation
pipeline_tier: full
affected_files:
  - agents/verifier.md
affected_reqs: [REQ-14, REQ-15]
---

## Context

When the test-topology protocol is active, an implementation step may run only a scoped subset of the test suite (`Tests: groups=[...] tier=step`). This introduces a new failure mode the M1 trunk did not need to guard: a step that *touched* code across several subsystems but *declared* a narrow `tier=step` run would test only one group, potentially masking a cross-group regression. `RESEARCH_FINDINGS.md` named this explicitly as an open item for the architect: "a step that touched 3 subsystems but ran `tier=step` on one group."

The question is whether the verifier — the post-implementation reviewer — should validate that scoped runs were tier-appropriate, and if so, how. The verifier has a hard constraint: it does not run tests; it reads test results and reports.

## Decision

The verifier validates tier-appropriateness as a **document cross-check** in Phase 10 (Test Coverage Assessment), not as a test re-execution.

For each implementation step that carried a `Tests:` field:

1. Map the step's `Files` to topology groups via the `file_dependencies` entries in `.ai-state/TEST_TOPOLOGY.md`.
2. If the step's `Files` span components belonging to more than one group, but the step declared `tier=step` (single-group closure, no integration boundaries followed), emit a **WARN**: the scoped run may have missed cross-group regressions; recommend re-running that step's tests at `tier=phase` or higher.
3. A step that declared `selector=manual` with a justification `reason` from the closed enum is **not** a finding — the manual escape hatch is honored by design.
4. When no step in the pipeline carried a `Tests:` field (protocol inactive), skip this check silently — the verifier's existing Phase 10 assessment is unchanged.

The check is a pure file-footprint-vs-declared-scope comparison, the same kind of document/diff cross-reference the verifier already performs for other Phase 10 dispositions (regression vs. pre-existing classification against `TEST_BASELINE.md`).

## Considered Options

### Option 1 — Verifier re-runs scoped tests at a wider tier

The verifier executes the step's tests at `tier=phase` to confirm nothing was missed.

- Pro: authoritative — actually catches a masked regression.
- Con: violates the verifier's "Do not run tests" constraint; expensive; duplicates the integration-checkpoint step that already runs the full suite at pipeline close. Rejected.

### Option 2 — Document cross-check: declared tier vs. actual file footprint (chosen)

The verifier compares the `Tests:` `tier` against the breadth of subsystems the step's `Files` touched and WARNs on a mismatch.

- Pro: stays within the verifier's read-only constraint; cheap; catches the exact failure mode the open item named; routes a human to re-run when warranted.
- Con: cannot *prove* a regression was missed — only flags the risk. Acceptable: the verifier is an auditor, and the pipeline-tier integration checkpoint is the actual full-suite backstop.

### Option 3 — Leave tier-appropriateness entirely to the sentinel

No verifier check; rely on the sentinel's periodic TT dimension.

- Pro: zero verifier change.
- Con: the sentinel runs out-of-band on a project-wide cadence, not per-pipeline; an under-scoped run in a specific pipeline would not be caught at the moment it matters (before the pipeline's verdict). Rejected — leaves a real gap.

## Consequences

**Positive:**
- The named failure mode (touched N subsystems, ran `tier=step` on one) is caught per-pipeline, at verification time, by an agent already equipped for document cross-checks.
- The verifier's "Do not run tests" constraint is preserved — no new capability, no new cost.
- Additive: pipelines that did not use the protocol see no verifier behavior change.

**Negative:**
- A document cross-check flags *risk*, not a confirmed regression — a WARN, not a FAIL. A user who ignores the WARN could still ship a masked regression. Mitigated by the pipeline-tier integration checkpoint, which always runs the full suite before pipeline close.

**Neutral:**
- The check depends on accurate `file_dependencies` globs in `TEST_TOPOLOGY.md`; stale globs would weaken it. This is the same staleness exposure the sentinel TT dimension already monitors — no new surface.
