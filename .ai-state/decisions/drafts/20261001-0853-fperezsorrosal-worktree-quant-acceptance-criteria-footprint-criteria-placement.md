---
id: dec-draft-d23f86c2
title: Footprint criteria are authored in the spec and routed by acceptance design to measurement steps and the verifier
status: proposed
category: behavioral
date: 2026-10-01
summary: "A change that moves a measurable footprint states its quantitative criteria as a ### Footprint Criteria table (and reasoned ### Footprints Not Measured rows) inside the spec's Acceptance Criteria; acceptance design files each row under Not Black-Box Testable routed to measurement steps and the verifier instead of encoding it as an outer-loop test; table criteria are FAIL when unmeasured while prose numeric claims keep the spec-driven-development WARN rule; an unbounded moved footprint is a WARN"
tags: [spec-driven-development, acceptance-design, verifier, footprint, quantitative-criteria, measurement]
made_by: agent
agent_type: systems-architect
branch: worktree-quant-acceptance-criteria
pipeline_tier: standard
affected_files:
  - agents/systems-architect.md
  - agents/test-engineer.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - skills/spec-driven-development/SKILL.md
  - skills/spec-driven-development/references/spec-format-guide.md
  - skills/spec-driven-development/references/footprint-criteria.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/references/document-templates.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06]
---

## Context

In selection-gaps-dogfood, the independent acceptance designer encoded REQ-04 faithfully. Only a later re-measurement showed that the change had raised median narrow test selection from 36% to 82%. Spec independence protects against implementation bias, not against a wrong spec. The brief asks that a change with a measurable footprint carry a quantitative criterion, with a named measurement command, from the spec all the way to the verifier. It also asks that a change without a footprint pay nothing, and that the placement (spec template, acceptance-design stage, or both) be decided and recorded.

The evidence that shaped the decision:

- A probe showed that the existing `extract_spec.py` passes a criteria table inside `## Acceptance Criteria` with zero findings, as long as each command is declared on `### Observable Surface`.
- A measurement guard test would cost 100–200 s (selection size, with `--compare-ref`) in every inner-loop run of exactly the pipelines it targets.
- Outer-loop tests are read-only to the implementer.
- The acceptance designer cannot know a base value, because oracles come from the spec only.
- The suite's own elapsed time cannot be tested inside that suite.

## Decision

1. **Spec template.** A quantitative criterion is a row of a `### Footprint Criteria` table (Id, Footprint, Metric, Comparator, Limit, Against, Command) inside `## Acceptance Criteria`. A footprint with no usable instrument is a row of `### Footprints Not Measured` (Footprint, Reason). Both tables are optional, and a spec with neither has today's shape. The grammar's normative text lives in the docstring of the check script (see `dec-draft-5c302933`).
2. **Acceptance design classifies; it does not encode.** The test-engineer files each row under `## Not Black-Box Testable`, routed "measurement step, then verifier". A footprint criterion is never written as an outer-loop test pinned to a dated baseline.
3. **Enforcement.** The plan adds baseline and final measurement steps. The verifier's Phase 3b runs the mechanical check and grades each value against its limit.
4. **Severity.** A table criterion with a missing, no-reading, stale, late or incomparable measurement is FAIL. A numeric claim written as prose acceptance criteria keeps the spec-driven-development skill's WARN-when-unmeasured rule; that skill's gotcha is rewritten to state both cases. A registered footprint moved without any row is a WARN, so the verdict is at best PASS WITH FINDINGS. The plan stage raises the same omission earlier, as a Spec Question.

## Considered Options

### Spec template only (chosen)

- **Pros:**
  - The threshold is fixed before design.
  - The extract is unchanged.
  - A wrong threshold is corrected by a spec amendment.
  - No test-time cost.
- **Cons:** the value-versus-limit grade is a judgment (PROMPT gate), not a RED test.

### Acceptance-design stage only (a guard measurement test)

- **Pros:** a mechanical RED.
- **Cons:**
  - The designer has no source for the number.
  - It costs minutes per run.
  - The test pins a dated baseline, so the next legitimate growth fails it.
  - It is read-only to the implementer.
  - It cannot measure the suite's own elapsed time.

### Both

- **Pros:** the spec fixes the number and a test enforces it.
- **Cons:** it inherits every cost of the guard-test option, and the threshold sits in two places.

### Plan and verifier only

- **Pros:** the trigger is mechanical at verify time.
- **Cons:**
  - The threshold is chosen after the design exists, which weakens independence.
  - It contradicts the user's Key Signal that the spec carries the criterion.

## Consequences

**Positive:**
- A footprint regression becomes a stated bound before design and a FAIL at verification.
- Footprint-free pipelines are unchanged.
- The 236 byte-identity guards are untouched.

**Negative:**
- The comparison against the limit relies on the verifier's reading of free-text limits. This is mitigated by golden bad-cases and by the mechanical check covering everything else.
- Authors must declare each command on `### Observable Surface`, which the lint already enforces.
