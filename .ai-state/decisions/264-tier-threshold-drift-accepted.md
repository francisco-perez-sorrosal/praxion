---
id: dec-264
title: Accept periodic-detection-only for tier-threshold agreement — no bespoke drift check
status: accepted
category: architectural
date: 2026-07-01
summary: Formally accept that no mechanical check asserts tier-threshold agreement across the tier-selector surfaces; the post-consolidation restatement surface is minimal, the two "threshold" surfaces encode different decision procedures, and a standing check would fail cost/substance tests. Reversal trigger names the concrete signal to build a narrow check later.
tags: [calibration, tiering, sentinel, gate-liveness, tech-debt, consistency, reliability-hierarchy]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: lightweight
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/spec-driven-development/references/calibration-procedure.md
  - claude/canonical-blocks/praxion-process.md
  - rules/swe/agent-behavioral-contract.md
re_affirms: dec-261
dissent: If tier bands change more than once a year, an unenforced invariant will silently drift between the tier table and the calibration matrix, and "high visibility catches it" is a hope, not a gate — a narrow LLM-judgment check (as EC06 already does for the delegation block) was cheap enough to just build.
---

## Context

`td-046` records a deliberately-deferred gate from the direct-capture-contract pipeline (`dec-261`, Decision D8, Consequences): no mechanical check asserts that the tier thresholds (file-count bands, score bands) agree across the surfaces that state them. `dec-261` deferred the check because "a substantive cross-surface threshold-agreement check over heterogeneous prose risks the gate-liveness anti-patterns (brittle grep, existence-not-substance)" and left two close paths: (a) build a narrow sentinel EC-series check, or (b) formally accept periodic-detection-only via ADR.

Grounding the deferral against the actual surfaces changes the picture. The row's premise — "four surfaces state the thresholds" — is substantially overstated *after* D8's consolidation:

- **`swe-agent-coordination-protocol.md`** (tier table + fast-path selector) — the *one* surface that fully states the bands (`single` / `2-3` / `4-8` / `9+` files; behavior counts; architectural-scope). Authoritative.
- **`calibration-procedure.md`** (scoring matrix) — a *different representation*: an additive 6-signal model where the file-count band (`4-8: 3pt`) is an **input**, and the tier is a function of the **composite score** (`7-10 → Standard`), not of file count alone. The tier table is an OR-heuristic; the matrix is additive scoring. These two procedures share band *boundaries* as inputs but encode genuinely different decisions and can legitimately diverge on a given task.
- **`praxion-process.md`** (canonical block) — states only the two smallest cases ("Direct (single-file fix/typo)", "Lightweight (2–3 files)") and already **points** to the tier selector for the rest.
- **`agent-behavioral-contract.md`** — states **no** numeric bands at all; names "Direct tier", says "don't ritualize a typo", and points to the tier table.

So exactly one surface fully restates the bands; one uses a different model; two either partially-state-and-point or state nothing numeric. The residual duplication D8 left is small, and the only well-defined shared invariant is the **file-count band boundaries** (`single` / `2-3` / `4-8` / `9+`), which appear in the tier table, the fast-path selector (same file), and the calibration matrix's file-count-proxy row.

## Decision

**Formally accept periodic-detection-only.** No bespoke mechanical or LLM-judgment check is added to assert tier-threshold agreement. Drift, if it occurs, is caught by (i) the sentinel's existing structural-gap judgment pass (EC05) and (ii) human review of the tier bands — among the most-read lines in the coordination protocol. This is the reliability-hierarchy-honest answer for a **low-frequency, high-visibility, hard-to-mechanize-substantively** invariant: prompt/periodic detection at the floor, no standing machinery whose recurring cost outweighs the defect it guards.

The **reversal trigger** (below) names the concrete signal that flips this to "build the check", and scopes what to build: a narrow check over the *file-count band boundaries only* — the one well-defined invariant — never a scoring-model-agreement check.

`td-046` resolves as **accepted** (this ADR is the durable record); the orchestrator flips the row.

## Considered Options

### Option A — Build a narrow sentinel EC-series check
- **Pros:** mechanical enforcement; EC06 already demonstrates the sentinel doing semantic (L-marked) cross-surface comparison, so this need not be a brittle grep; a golden bad-case is easy to state ("tier table says 5-9 for Standard but matrix says 4-8 → FLAG").
- **Cons:** a substantive "agreement" check is **ill-defined** for the general case — the tier table (OR-heuristic) and the calibration matrix (additive scoring) are not the same statement in two dialects; only the file-count band *boundaries* are a well-defined shared invariant. A standing LLM-judgment check adds recurring token cost to every sentinel audit forever, guarding a rare, low-impact, easily-human-caught defect — it fails "every check earns its place." A literal-band grep would trip gate-liveness *substance-over-structure* (passes if `4-8` appears anywhere) and risk *no-self-contradiction* (asserting two intentionally different procedures produce identical strings).

### Option B — Formally accept periodic-detection-only via ADR (chosen)
- **Pros:** proportional to the (low) real drift frequency post-D8; honors the reliability hierarchy for a high-visibility invariant; zero recurring cost; zero new machinery; a load-bearing reversal trigger keeps the door open with a concrete, observable build signal.
- **Cons:** the invariant is unenforced — a genuine band-boundary drift could land if review misses it; relies on visibility + EC05 judgment rather than a deterministic gate.

### Option C — Single-source-of-truth structural fix (extract bands, others reference)
- **Pros:** matches Praxion's structural-fix-over-detector preference; would dissolve the drift-check need rather than detect drift.
- **Cons:** **largely already realized by D8's consolidation** — the surface is already down to one authoritative statement plus pointers. Markdown prose has **no import mechanism**: the tier table must physically read "4-8 files" for a scanning agent, so "reference the canonical bands" still restates the boundaries in each surface and merely adds a sync-contract — which itself would need a checker (looping back to Option A). No net structural gain; adds ceremony.

## Consequences

**Positive:**
- Zero recurring sentinel/token cost; no new standing gate for a rare defect.
- The reliability hierarchy is honored: for a high-visibility, low-frequency invariant, periodic/human detection is the proportional floor.
- The reversal trigger converts a vague "we should check this someday" into a concrete, observable build condition with a pre-scoped design.

**Negative / accepted:**
- The file-count band-boundary invariant is unenforced between the tier table and the calibration matrix; a drift that slips past review persists until the next reader or EC05 pass notices.
- A rejected lightweight follow-up — a `<!-- keep bands in sync -->` comment in the calibration-procedure file-count-proxy row — was **not** taken: `skills/` is a shipped surface (per `shipped-artifact-isolation.md`) so it may not cite the ADR by number, and a bare unenforced sync-comment is decoration that gate-liveness rightly discounts. The ADR is the record instead.

## Disconfirmation

- **Falsifier:** A commit reaches `main` in which the tier table's file-count band boundaries and the calibration matrix's file-count-proxy bands **disagree** (e.g., tier table `5-9` for Standard vs. matrix `4-8`), and it is *not* caught in review or by an EC05 pass before a downstream tier-selection uses the stale band. That would show the invariant needed a deterministic gate, not visibility.
- **Steelmanned runner-up (Option A — narrow EC(L) check):** The honest case for building it now is that EC06 already proves the sentinel performs cheap semantic cross-surface comparisons routinely, so the "heterogeneous prose → brittle grep" fear that drove `dec-261`'s deferral is weaker than it looked: an L-marked check reading the file-count-proxy row against the tier table, with a documented golden bad-case, sidesteps the grep anti-pattern entirely. "High visibility catches drift" is an untested assumption about human attention on lines that experienced readers skim; a one-line addition to Batch-3 buys a deterministic backstop for near-zero incremental design cost. It loses today only because the guarded defect is rare and high-visibility and the check carries a standing per-audit cost — but it wins the instant the falsifier fires.
- **Reversal trigger (load-bearing):** Build the check when **either** (i) one genuine file-count band-boundary drift reaches `main` (a commit where the tier table and the calibration matrix disagree on a boundary), **or** (ii) ≥2 such drifts are caught only in review (near-misses) within any rolling window. On that signal, add a single **narrow LLM-judgment EC-series check** scoped to the **file-count band boundaries only** — comparing the tier table, the fast-path selector, and the calibration-procedure file-count-proxy row — using the sentinel's existing semantic-comparison pattern (as EC06 does), with a documented golden bad-case. Never a literal-band grep; never a scoring-model-agreement check (the tier table and matrix are intentionally different procedures and cannot be asserted string-identical).

## Prior Decision

Re-affirms `dec-261` (direct-capture-contract), whose D8 consolidation deferred this very check and recorded the deferral rationale. This ADR does not overturn that deferral — it completes it by grounding the "four surfaces" premise against the actual (post-D8, largely-consolidated) surface and formally choosing acceptance path (b) with a concrete reversal trigger, rather than leaving the choice open on the ledger.
