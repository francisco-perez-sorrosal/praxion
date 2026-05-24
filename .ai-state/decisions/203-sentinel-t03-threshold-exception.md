---
id: dec-203
title: Recalibrate T03 with a line-count exception for the gate-encoding agents (sentinel + verifier)
status: accepted
category: architectural
date: 2026-05-23
summary: Give the two gate-encoding agents (agents/sentinel.md, agents/verifier.md) a higher T03 threshold (warn 550 / fail 700) because their size is substantially intrinsic — sentinel's ~260-line Check Catalog and verifier's comprehensive Process plus its deliberately tested-in-place rework-spawn contract; all other agents keep warn 300 / fail 500.
tags: [sentinel, verifier, t03, token-budget, gate-liveness, agent-prompt-size, quality-gate, tech-debt]
made_by: user
pipeline_tier: direct
affected_files:
  - agents/sentinel.md
  - agents/verifier.md
---

## Context

Sentinel check **T03** ("Agent prompt size within range") flagged two agents at FAIL
(>500 lines): `agents/sentinel.md` (580) and `agents/verifier.md` (587). The td-040
ledger row called for a "progressive-disclosure split (core prompt + reference files)."

A full read-through of both files (the "assess, then trim or report" path) found the
oversize is **largely intrinsic, not bloat** — and that both files are *gate-encoding
agents*: the sentinel is the ecosystem auditor; the verifier is the verification gate.

- **`sentinel.md`** is dominated by its `## Check Catalog` (~260 lines): ~80 distinct
  per-dimension check rows (`ID | Type | Rule | Pass`). This *is* the gate — the data
  the sentinel executes in Pass 1 / Pass 2. Near-zero redundancy.
- **`verifier.md`** is a comprehensive `## Process` (Phases 1–12.5) plus a rework-spawn
  contract that is **deliberately documented in-place and locked by ship-gate tests**
  (`tests/orchestration/test_rework_spawn.py`, `test_pipeline_cleanup.py`) per the
  verifier-rework-loop feature (dec-173..182). Relocating that contract to dodge a
  line-count would amend a tested design decision and rewrite its ship-gate tests — a
  larger, riskier change than tidying. A genuinely-clean de-dup *was* applied (the
  conditional Phase 3a ML-metric procedure already lived in
  `skills/llm-training-eval/references/training-results-schema.md`; the verifier now
  points to it instead of duplicating it), taking the verifier 587 → 556. The residual
  size is the tested contract + intrinsic gate Process.

Two ways to force either agent under 500 violate the gate-liveness rule
(`rules/swe/gate-liveness.md`, "substance over structure"):

1. **Trim the substance** → removes checks (sentinel) or guts the tested contract (verifier).
2. **Externalize core gate logic to a reference read at runtime** → a missed read silently
   disables it (a "dead gate"). The genuinely-conditional detail (SH/TT for sentinel,
   Phase 3a for verifier) is already externalized; the cores are executed/asserted in-place.

The T03 threshold (tuned for ordinary agent prompts) is miscalibrated for the two agents
whose function *is* comprehensive gating.

## Decision

Recalibrate T03 with a **narrow, documented, monitored** exception:

- `agents/sentinel.md` and `agents/verifier.md` are assessed at **warn 550 / fail 700**
  (rather than 300 / 500).
- **All other agents retain warn 300 / fail 500.**

The exception names exactly two agents — the ecosystem's gate-encoding pair. It is
monitored, not a free pass: both still WARN above 550 (sentinel 580, verifier 556 →
WARN, not FAIL), keeping pressure against unbounded growth while not forcing a cosmetic,
gate-endangering split or a rewrite of the verifier's ship-gate tests.

The verifier's Phase 3a de-dup (pointing at the existing schema reference instead of
duplicating its procedure) is retained as a genuine lean-up independent of the threshold.

## Considered Options

### A. Extract the core gate logic to a reference read at runtime
- **Pro**: brings both agents under 500.
- **Con**: dead-gate risk — the agents execute/assert this content in-place; a missed load
  silently disables it. Rejected per gate-liveness.

### B. Trim the substance to fit
- **Con**: the only way to shed the lines is to remove sentinel checks or gut the
  verifier's tested rework contract. Gaming the gate. Rejected.

### C. Raise the global agent T03 threshold
- **Con**: blinds the gate for *every* agent — a genuinely-bloated 600-line non-gate agent
  would pass silently. Rejected: the gate must keep biting for ordinary agents.

### D. Relocate the verifier's rework contract + rewrite its ship-gate tests
- **Pro**: gets the verifier genuinely under 500.
- **Con**: overrides a deliberate, tested design (dec-173..182) for a line count, and
  rewrites 5 ship-gate tests. Disproportionate; rejected in favour of the exception.

### E. Named exception for the two gate-encoding agents (chosen)
- **Pro**: keeps the gate at 500 for all other agents; acknowledges the two auditing/gating
  agents are intrinsically large; stays monitored (WARN at 550); respects the verifier's
  tested contract.
- **Con**: a named exception is a small special-case. Mitigated: generalize to a principled
  "gate-encoding agent" rule only if a third such agent emerges — do not pre-generalize.

## Consequences

**Positive:**
- Neither gate-encoding agent FAILs T03 on a cosmetic line-count for irreducible substance.
- The gate stays honest (500) for every other agent.
- Growth pressure is retained (WARN at 550).
- The verifier's tested rework contract and its ship-gate tests are left intact.

**Negative:**
- A two-agent exception in T03 is a small special-case in the check catalog. Accepted as
  the least-bad option; the alternatives weaken the gate globally, endanger it, or override
  a tested design.
- Either agent may grow to 700 before FAILing. Mitigated by the 550 WARN.

A future supersession is warranted if (a) a third agent legitimately needs the exception
(generalize to a principled "gate-encoding agent" rule), or (b) a reliable agent-local
lazy-load mechanism appears that lets core gate logic externalize without dead-gate risk.
