---
id: dec-203
title: Recalibrate sentinel T03 with a named line-count exception for the sentinel's irreducible Check Catalog
status: accepted
category: architectural
date: 2026-05-23
summary: Give agents/sentinel.md a higher T03 threshold (warn 550 / fail 700) because its ~260-line Check Catalog is irreducible gate substance — externalizing it risks a dead gate and trimming it removes checks; all other agents keep warn 300 / fail 500.
tags: [sentinel, t03, token-budget, gate-liveness, agent-prompt-size, quality-gate, tech-debt]
made_by: user
pipeline_tier: direct
affected_files:
  - agents/sentinel.md
---

## Context

Sentinel check **T03** ("Agent prompt size within range") flagged two agents at FAIL
(>500 lines): `agents/sentinel.md` (581) and `agents/verifier.md` (588). The td-040
ledger row called for a "progressive-disclosure split (core prompt + reference files)."

A full read-through of both files (the "assess, then trim or report" path) found the
oversize is **largely intrinsic, not bloat**:

- **`sentinel.md`** is dominated by its `## Check Catalog` (~260 lines): ~80 distinct
  per-dimension check rows (`ID | Type | Rule | Pass`). This *is* the gate — the data
  the sentinel executes in Pass 1 / Pass 2. It has near-zero redundancy.
- **`verifier.md`** had genuine cleanup headroom (misplaced main-agent rework
  documentation + a conditional ML-metric block) and is brought under 500 by that
  cleanup in a sibling change — so it does **not** need a threshold exception.

Two ways to force the sentinel under 500 both violate the gate-liveness rule
(`rules/swe/gate-liveness.md`, "substance over structure"):

1. **Trim the catalog** → removes checks → reduces the gate's coverage (gutting substance).
2. **Externalize the catalog to a reference the sentinel reads at runtime** → a missed
   read silently disables every check (a "dead gate"). The genuinely-conditional check
   detail (SH, TT) is *already* externalized; the core catalog is executed inline.

The sentinel is the ecosystem's single most comprehensive artifact by design — one
auditor covering sixteen dimensions. Its size reflects genuine breadth, and the T03
threshold (tuned for ordinary agent prompts) is miscalibrated for it.

## Decision

Recalibrate T03 with a **narrow, documented, monitored** exception:

- `agents/sentinel.md` is assessed at **warn 550 / fail 700** (rather than 300 / 500).
- **All other agents retain warn 300 / fail 500.**

The exception names exactly one agent. It is monitored, not a free pass: the sentinel
still WARNs above 550 (it is 581 today → WARN, not FAIL), keeping pressure against
unbounded catalog growth while not forcing a cosmetic, gate-endangering split.

The verifier is **not** covered by this exception — it clears the standard 500 ceiling
through genuine cohesion cleanup (relocating misplaced main-agent docs to
`skills/software-planning/references/agent-pipeline-details.md` and externalizing the
conditional Phase 3a ML-metric procedure into the `llm-training-eval` skill's
references, loaded only on an ML signal).

## Considered Options

### A. Extract the Check Catalog to a reference the sentinel loads at runtime
- **Pro**: brings `sentinel.md` under 500.
- **Con**: dead-gate risk — the sentinel executes the catalog inline; a missed load
  silently disables checks. Rejected per gate-liveness.

### B. Trim the catalog to fit
- **Pro**: brings `sentinel.md` under 500 with no new file.
- **Con**: the only way to remove ~80 lines is to remove checks — gutting coverage to
  pass a line count. Gaming the gate. Rejected.

### C. Raise the global agent T03 threshold
- **Pro**: one number change; both agents pass.
- **Con**: blinds the gate for *every* agent — a genuinely-bloated 600-line non-gate
  agent would pass silently. Rejected: the gate must keep biting for ordinary agents.

### D. Named exception for the sentinel only (chosen)
- **Pro**: keeps the gate at 500 for all other agents; acknowledges the sentinel's
  catalog is irreducible; stays monitored (WARN at 550).
- **Con**: a named exception is brittle if a second comprehensive gate-agent later
  emerges. Mitigated: revisit and generalize the exception (e.g., a "catalog-dominated
  agent" rule) only when a real second case appears — do not pre-generalize.

## Consequences

**Positive:**
- The sentinel no longer FAILs T03 on a cosmetic line-count for irreducible gate substance.
- The gate stays honest (500) for every other agent.
- Growth pressure is retained (WARN at 550); the catalog cannot grow unboundedly without surfacing.

**Negative:**
- A per-agent exception in T03 is a small special-case in the check catalog. Accepted as
  the least-bad option; the alternatives either weaken the gate globally or endanger it.
- The sentinel may grow to 700 before FAILing. Mitigated by the 550 WARN and by this
  ADR's instruction to generalize (not widen) the exception if a second case appears.

A future supersession would be warranted if (a) a second agent legitimately needs the
exception (generalize to a principled "catalog-dominated" rule), or (b) a reliable
agent-local lazy-load mechanism appears that lets the catalog externalize without
dead-gate risk.
