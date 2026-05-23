---
id: dec-201
title: Gate Liveness — prove Praxion's enforcement layer bites
status: accepted
category: architectural
date: 2026-05-23
summary: Introduce a gate-liveness discipline — a CODE/PROMPT gate taxonomy, a canary requirement for code gates enforced by a fitness meta-test, a path-scoped authoring rule, and a sentinel Gate Liveness (GL) family — so verification machinery is proven to fail on bad input rather than passing vacuously.
tags: [gate-liveness, verification, fitness, sentinel, canary, quality, meta-testing, enforcement]
made_by: agent
agent_type: orchestrator
branch: pipeline-efficiency-tier-ab
pipeline_tier: standard
affected_files:
  - rules/swe/gate-liveness.md
  - skills/testing-strategy/references/gate-canaries.md
  - fitness/tests/test_gate_canary_coverage.py
  - scripts/check_gate_liveness.py
  - agents/sentinel.md
  - rules/swe/adr-conventions.md
---

## Context

A pipeline-efficiency audit surfaced a recurring class of defect in Praxion: **gates that don't bite** — verification or enforcement machinery that passes regardless of whether the thing it checks is actually correct. Concrete instances found:

- A planner checkpoint grepped test files for `req{NN}_` patterns that `id-citation-discipline` *forbids* in test names — the grep can never match (a dead instruction).
- The traceability matrix could render empty yet pass the verifier's spec-conformance gate and sentinel `SH02`/`SH04` (a presence check, not a substance check).
- The conversation-checkpoint mechanism defined a consumer (orchestrator reads `### Assumptions & Constraints Taken`) with no producer instructing any agent to write it.
- A new ADR set `re_affirms` without the reciprocal `re_affirmed_by` back-link — a one-directional cross-reference nothing detects.
- `fitness/tests/test_meta_citation.py` asserts the *real repo currently passes*, never that the check *fails* on a citation-less fixture — so it proves compliance, not bite.

Root observation: Praxion holds **code** to a "prove it works" standard (tests, RED handshake, fitness CI) but holds its **instruction fabric and gates** to a "looks complete" standard. The project's own `CLAUDE.md` already states the governing principle — *"pair every claim a doc makes with a verification path."* A gate is a claim ("I catch defect class X"). This decision extends the principle Praxion already holds for code and docs to the enforcement layer itself.

## Decision

Adopt a **gate-liveness discipline** with a foundational taxonomy and three layers.

**Taxonomy (foundational):** every gate is either a **CODE gate** (deterministic execution — `scripts/check_*.py`, `scripts/validate_*.py`, `fitness/` tests and contracts, hook gate/guard scripts) or a **PROMPT gate** (LLM-interpreted — sentinel checks, verifier phases, planner/agent checkpoints, "verify/ensure X" instructions). Each routes to the proof mechanism that actually works for it; forcing a deterministic canary onto a judgment gate would itself be a gate that doesn't bite.

**L1 — Principle.** A gate must be proven to bite. Four clauses: substance over structure; a named producer for every consumer; no self-contradiction (never assert a pattern another rule forbids); pair with a verification path (CODE gate → canary; PROMPT gate → documented bad-case + an L3 detector entry). Codified as a **path-scoped rule** `rules/swe/gate-liveness.md` (loads only when gate-authoring surfaces are touched — not always-on), with the canary-authoring recipe in a `testing-strategy` skill reference.

**L2 — Canary discipline (CODE gates).** A canary is a deterministic negative-case test that feeds the gate a known-bad input and asserts it flags it. A fitness meta-test (`fitness/tests/test_gate_canary_coverage.py`, generalizing the existing `test_meta_citation.py` pattern) globs the gate set and asserts each gate has a sibling test with a negative-case-named test. Forward mandate for new gates; bounded one-time retrofit of existing canary-less gates. The meta-test ships with its own canary.

**L3 — Detection (PROMPT gates + cross-cutting).** A new sentinel **Gate Liveness (GL)** family: GL02 forbidden-pattern-contradiction as a committed script `scripts/check_gate_liveness.py` (a dead grep is a hard mechanical contradiction) shipped with a canary; GL01 orphaned-consumer and GL03 substance-not-presence as Pass-2 LLM judgment. (GL01 was prototyped as a regex but moved to LLM judgment after the prototype produced 7 false positives and 0 true positives on the real repo — "is this section produced anywhere?" is semantic, and the D0 taxonomy says route it to the proof that works.) ADR cross-reference reciprocity goes to the existing **Decision Log** family as **DL06**, not GL.

**Convention clarification.** `re_affirms` may accompany `status: proposed`/`accepted` when the ADR's primary purpose is a new decision that also confirms a prior one; `status: re-affirmation` is reserved for ADRs whose sole purpose is re-affirmation. Both link directions are mandatory (enforced by DL06).

## Considered Options

### Option A — Taxonomy + L1 + L2 + L3 as above (chosen)
- Pro: treats each gate kind with a proof that works; the canary discipline is enforceable (a test), not aspirational; GL makes "do our gates bite?" a visible scorecard grade.
- Pro: reuses existing patterns (co-located `test_*` siblings, the `test_meta_citation` meta-test, sentinel script-invocation) — minimal new conceptual surface.
- Con: a one-time retrofit cost for ~8 existing canary-less gates. Accepted — refusing to grandfather the debt is the point.

### Option B — L3 sentinel detection only (no canary discipline)
- Pro: smaller; catches existing instances periodically.
- Con: whack-a-mole — detects instances after they ship, never changes the standard, so new gates keep being born without bite. Rejected: does not address the root cause.

### Option C — Distribute the checks into existing sentinel families (EC/N/X), no GL family
- Pro: no new family.
- Con: buries the meta-concern with no single grade; invisibility is exactly how the pattern accumulated. Rejected.

### Option D — Make the L1 principle an always-on rule
- Pro: maximally visible to every agent.
- Con: the principle is relevant only when authoring a gate (a minority of sessions); the always-on surface is near its token budget. Rejected in favor of path-scoping.

## Consequences

**Positive:**
- New gates are born proven: a CODE gate without a canary fails CI; a PROMPT gate without a producer/bad-case is flagged by GL.
- The five real defects that motivated this become detectable as a *class* (GL01/02/03, DL06), not patched as instances.
- "Gate bite" gets a sentinel grade — a standing health signal.
- No always-on token cost (L1 path-scoped).

**Negative / accepted:**
- One-time retrofit of ~8 existing gates' canaries.
- GL01 (orphaned-consumer) and GL03 (substance-not-presence) are LLM-judgment checks, not deterministic — their reliability depends on the sentinel's Pass-2 reasoning, not a pinned test.
- Small bounded overlap between GL and EC/N/X lenses, accepted for the visibility a named family buys.

**Dogfood invariant:** every artifact this decision introduces must itself satisfy the discipline — the canary meta-test, each GL check, and DL06 each ship with a canary or golden bad-case. A gate-liveness mechanism that does not bite would refute its own thesis.
