---
id: dec-draft-239ddd67
title: Family row form — a two-part sentinel row for scripts dispatched from the Family table
status: accepted
category: behavioral
date: 2026-09-12
summary: "A sentinel A row whose script is dispatched from the Phase 3 Family dispatch table may use a two-part form (the Family prefix, the python3 scripts/<name>.py --json invocation, then the verdict map) because the table carries the substrate condition and the Phase 3 preamble carries the spec pointer for every family; the four-part form stays valid for sentence-dispatched scripts. Verdict-map budget, Triangle binding and the invocation phrase are unchanged."
tags: [sentinel, process-economy, roadmap-p2-1, data-structures, byte-budget]
made_by: agent
agent_type: orchestrator
branch: worktree-process-economy-p2-wrap
pipeline_tier: lightweight
affected_files:
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - tests/test_sentinel_check_triangle.py
affected_reqs: []
supersedes_in_part: [dec-380]
---

## Context

The P2.1 residual pipeline (dec-381) measured what dec-380's four-part row costs: the template
floor is `110 + 3·len(name) + len(Conditional clause)` bytes ≈ 250–290 B of Pass column before
the verdict map. Twenty-nine of the fifty-five residual rows carried Pass columns of ≤100 B, so
extraction *grew* them, and the whole residual netted ≈0 bytes (107,397 → 107,347) even though
thirty-five verdicts became deterministic. Twenty rows were recorded leave-as-is for that reason
alone. Meanwhile the pipeline replaced the per-family dispatch sentences with one Family
dispatch table whose substrate cell already states each family's skip condition — the same
information the Conditional clause repeats in every row — and the Spec pointer is a fixed phrase
derivable from the script name.

## Decision

A row whose script appears in the Family dispatch table may take the **family form**:

```
Family: `python3 scripts/<name>.py --json`; <verdict map>
```

Two parts, in order, nothing else: the literal invocation phrase (still `python3 scripts/<name>.py`,
so `_delegated_gates`, GL04/GL05 and the Triangle keep keying on it) and the verdict map, still
≤300 UTF-8 bytes. The Conditional clause lives in the table's substrate cell; the Spec pointer
lives once in the Phase 3 preamble ("Spec + golden bad-cases for every family script: its module
docstring and canary `scripts/test_<name>.py`"). The contract test accepts either form and, for
the family form, asserts the script is present in the table — the structural fact that licenses
the omission. The four-part form remains valid for scripts dispatched by sentence (AC13, AC14,
GL, DH, P03, RD…) and for any row an author prefers to keep self-contained.

## Considered Options

### Keep the four-part form everywhere (dec-380 as written)

Rejected on measurement: twenty rows cannot be extracted without growing the file, and the
thirty-five already extracted carry ~200 B each of text the table and preamble duplicate.

### Raise the byte ceiling instead

Rejected: the ceiling is the guard that caught two in-flight breaches; the growth was template
overhead, not content, so the template is the right variable.

## Consequences

**Positive**: the twenty leave-as-is rows become extractable byte-neutrally; converting the
thirty-five family rows recovers ~7 KB of `agents/sentinel.md`; one sentence replaces
thirty-five spec pointers. **Negative / risk**: a family row is no longer self-contained — a
reader must consult the table for the substrate; the contract test's table check is what keeps
the two from drifting. The row form is a *convention amendment*, not a new component:
`behavioral` by the falsifier in `rules/swe/adr-conventions.md`.

## Prior Decision

dec-380 fixed one four-part shape for every extracted row and priced its verdict map. This record
narrows that clause: the shape is four-part for sentence-dispatched scripts and two-part for
table-dispatched ones. The budget, the parse-don't-strip guard, the three destinations and the
envelope contract are unchanged and re-affirmed.
