---
id: dec-038
title: TEST_RESULTS.md as formal implementer→verifier handoff artifact
status: accepted
category: architectural
date: 2026-04-12
summary: Formalize test outcome handoff from implementer to verifier via TEST_RESULTS.md in .ai-work/<slug>/, per-implementer fragment files in parallel mode
tags: [pipeline, artifact, implementer, verifier, testing, handoff]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - agents/implementer.md
  - agents/verifier.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/swe-agent-coordination-protocol.md
affected_reqs: []
---

## Context

Today the implementer runs tests in step 6 of its workflow, but the outcome is ephemeral — held only in the implementer's own context window and in an ad-hoc line inside `WIP.md`. The verifier, whose Phase 5 explicitly says "read test results, never execute tests," has no canonical location to read them from. This creates an implicit handoff: the verifier either trusts that "tests passed" was reported correctly, re-derives the state from code, or (against its mandate) re-runs tests.

ROADMAP.md Phase 2.2 requires a formal `TEST_RESULTS.md` artifact. The design question is shape, location, and parallel-execution semantics — aligning with existing `.ai-work/<slug>/` conventions and the fragment-file pattern used for `WIP.md`, `LEARNINGS.md`, and `PROGRESS.md`.

## Decision

Introduce `TEST_RESULTS.md` as an ephemeral pipeline artifact at `.ai-work/<task-slug>/TEST_RESULTS.md`, written by the implementer after step 6 (run tests) and read by the verifier in Phase 5 (Test Coverage Assessment). In parallel mode, each implementer writes a scoped fragment (`TEST_RESULTS_implementer_stepN.md`); the implementation-planner merges fragments into a canonical `TEST_RESULTS.md` during its coherence review, following the existing fragment reconciliation protocol.

**Schema** (a concise Markdown table + per-failure blocks, not free prose):

```markdown
# Test Results — Step N: <step title>

**Run at**: <ISO 8601 timestamp>
**Command**: <exact test invocation, e.g., `uv run pytest tests/ -v`>
**Exit code**: <0 | non-zero>

## Summary

| Metric | Value |
|--------|-------|
| Passed | <n> |
| Failed | <n> |
| Skipped | <n> |
| Errors | <n> |
| Duration | <seconds> |
| Coverage | <%, or `not measured`> |

## Failures

<one block per failure, or "None" if all passed>

### <test id or name>

- **File**: <path>
- **Line**: <lineno if available>
- **Assertion**: <assertion message>
- **Excerpt**:
  ```
  <traceback / output, trimmed>
  ```

## Coverage Highlights (optional)

<files with <80% coverage, or "N/A" if coverage not measured>

## Notes

<optional free-text — flaky tests observed, skipped with reason, etc.>
```

**Writer contract**: implementer writes this file at the end of step 6, before step 7 (self-review). Even on success, the file is written — the presence of `TEST_RESULTS.md` is the handoff signal.

**Reader contract**: verifier reads `TEST_RESULTS.md` in Phase 5 before any convention-compliance or coverage judgments. Absence of the file when tests were expected becomes a `WARN` (not a `FAIL`) — the artifact is advisory infrastructure, not a quality gate.

## Considered Options

### Option A — Per-step TEST_RESULTS_stepN.md files (one per step)

- **Pros**: Fine-grained; trivially parallel-safe; no merge needed.
- **Cons**: Fragments the verifier's view; forces the verifier to glob and stitch. Doesn't match the existing single-canonical-artifact pattern of `WIP.md`/`LEARNINGS.md`.

### Option B — Single canonical TEST_RESULTS.md, appended by each step (chosen)

- **Pros**: One file the verifier reads. Matches existing artifact conventions. Parallel mode uses the established fragment pattern (`TEST_RESULTS_implementer_stepN.md` → merged by planner), so the mechanics are already familiar.
- **Cons**: Requires an append discipline in sequential mode and merge discipline in parallel mode — but both patterns exist already.

### Option C — Embed in WIP.md under each step

- **Pros**: No new file.
- **Cons**: Conflates state tracking with test artifacts; makes `WIP.md` noisy and hard to scan; violates single-responsibility for pipeline artifacts; verifier would have to grep into `WIP.md` to find test outcomes.

### Option D — Structured format (JSON/YAML) instead of Markdown

- **Pros**: Machine-parseable.
- **Cons**: All other `.ai-work/` artifacts are Markdown; the verifier is an LLM that reads Markdown natively; JSON/YAML adds schema-validation burden with no current consumer that benefits from it.

## Consequences

**Positive**:

- Verifier Phase 5 has a deterministic input contract: read one file, classify findings against it.
- Implementer's "I ran tests" claim becomes auditable — the file is the evidence.
- Parallel execution safe via existing fragment pattern, no new protocol.
- Failed-test details travel with the pipeline instead of being reconstructed from logs after the fact.

**Negative**:

- One more file in `.ai-work/<slug>/` for every pipeline run — small footprint, deleted with the rest at pipeline end.
- Implementer must remember to write the file even on success (the "no failures" case). Mitigation: bake it into step 6's contract so success writes a `## Failures\n\nNone` block.
- Merging fragments in parallel mode adds one more merge target for the planner — negligible marginal cost since the protocol is already in use.

**Neutral**:

- The artifact is advisory, not a gate. A missing `TEST_RESULTS.md` does not block the pipeline; it produces a `WARN`. This keeps the hardening change low-risk.

## Addendum (2026-04-12) — Implementation Reconciliation

The ADR body above reflects the architect-stage design. During pipeline-hardening implementation, three decisions shifted per `RECONCILIATION.md` and landed differently:

| Topic | ADR body | As implemented | Source |
|-------|----------|----------------|--------|
| Implementer write location | end of step 6 (run tests) | **sub-step 7.8** (after `docs/architecture.md` update at 7.7) | RECONCILIATION Decision 5 — avoids cascading renumber of hardcoded step 7.6/7.7 refs |
| Verifier read location | Phase 5 | **Phase 10** (same workflow stage, post full-renumber of verifier phases to sequential 1..12) | Task 2.1 phase renumber (same pipeline) |
| Parallel-mode fragment naming | `TEST_RESULTS_implementer_stepN.md` (step-scoped) | **`TEST_RESULTS_<agent-type>.md`** (agent-scoped; e.g., `TEST_RESULTS_implementer.md`, `TEST_RESULTS_test-engineer.md`) | RECONCILIATION Decision 4 — step sections are internal to the file; agent-scoped fragments follow the existing `<DOC>_<agent-type>.md` convention from `skills/software-planning/references/agent-pipeline-details.md` |

The ADR's core decision (introduce `TEST_RESULTS.md` as a `.ai-work/<slug>/` ephemeral artifact, advisory/WARN-not-FAIL semantics, Markdown schema) is unchanged. The shifts above are placement and fragment-naming refinements that preserve the artifact's purpose.

Additionally, the canonical writer rule was clarified: **test-engineer** is the canonical writer when paired with implementer on BDD/TDD execution; **implementer** writes only when running tests independently. The ADR body's implementer-only framing was broadened to cover this paired-execution case.

ADR body preserved unchanged above to maintain historical integrity; downstream agent prompts (`agents/implementer.md:90`, `agents/test-engineer.md:142`, `agents/verifier.md:174-183`) and rule files (`rules/swe/agent-intermediate-documents.md`, `rules/swe/swe-agent-coordination-protocol.md`) reflect the as-implemented values.
