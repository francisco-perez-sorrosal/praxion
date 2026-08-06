---
id: dec-097
title: AaC+DaC cornerstone framed as clauses under existing principles, not a new top-level principle
status: accepted
category: architectural
date: 2026-04-30
summary: 'Engrave Architecture-as-Code + Documentation-as-Code as cornerstone via two ≤2-sentence clauses — one under Context Engineering, one under Structural Beauty — rather than introducing a seventh top-level principle.'
tags: [philosophy, claude-md, aac, dac, context-engineering, structural-beauty, token-budget]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - claude/config/CLAUDE.md
---

## Context

The user posited model-centric Architecture-as-Code (AaC) + Documentation-as-Code (DaC) as a *philosophical* cornerstone of Praxion — not just tooling. The promethean ideation surfaced three framings: (a) add a new top-level principle ("Model-Centric Architecture" or "Architectural Context as First-Class Citizen"), (b) extend the existing Context Engineering principle, (c) extend the existing Structural Beauty principle. The promethean registered an objection against (a) on token-budget grounds; the user accepted that objection.

The decision must (i) preserve the cornerstone framing the seed brief specified, (ii) keep both halves explicit (machine-readable model SSOT *and* authored rationale co-equal), and (iii) respect the 25,000-token always-loaded budget guardrail.

## Decision

Add two short clauses to `~/.claude/CLAUDE.md`, one under each of the existing **Context Engineering** and **Structural Beauty** principle headings. No new top-level principle is added.

**Under Context Engineering** (the principle whose substance is "the right information at the right place at the right time"), add:

> **Architectural context is first-class.** Structural facts live in machine-readable models — a DSL, ADRs, traceability matrices — while rationale lives in authored narrative; both are versioned together, and neither degrades silently.

**Under Structural Beauty** (the principle whose substance is "well-organized code is easier to trust"), add:

> **The architecture you describe is the architecture you ship.** When the system is modeled — DSL, fences, fitness functions — the description and the running code are the same artifact, by construction.

Combined token cost: ~90 tokens. Hard ceiling per the v1 acceptance criterion is ≤200 tokens.

## Considered Options

### Option 1 — New top-level principle ("Architectural Context as First-Class Citizen")

**Pros:** Maximum visibility for the cornerstone framing; readers who skim only principle headers see it.

**Cons:** Adds a seventh principle to a curated set of six (Pragmatism, Context Engineering, Behavior-Driven Development, Incremental Evolution, Structural Beauty, Root Causes Over Workarounds). Each principle currently carries 30%+ session relevance. A seventh principle dedicated to AaC carries <30% relevance for projects that do not opt into the AaC stack. Principle bloat decays the always-loaded surface's signal-to-noise ratio. Promethean registered the objection against this option; user accepted.

### Option 2 — Single clause under Context Engineering only

**Pros:** Most natural home; "machine-readable models + authored narrative + both versioned together" is squarely a context-engineering claim.

**Cons:** The "describe == ship" claim is structural-beauty in flavor (about reliability and the integrity of the system's own description); housing it under Context Engineering buries the second half. The user's seed brief specifically asked for both halves to be explicit.

### Option 3 — Two clauses, one under each principle (chosen)

**Pros:** Keeps both load-bearing halves visible at the head of their respective parent principles. No principle bloat. Combined token cost (~90) is well under the 200-token v1 ceiling. Preserves the "co-equal carriers" intent the promethean's risk note flagged. Cornerstone framing achieved without elevating AaC to its own principle slot.

**Cons:** Two edits to `CLAUDE.md` instead of one. Future drift — a contributor might revise one clause and miss the other. Mitigated by the fact that both clauses sit under stable, well-known section headers in a small file (123 lines).

### Option 4 — Defer the philosophy edit; ship only the operational stack (Ideas 2/4/5)

**Pros:** Smallest blast radius; zero token cost.

**Cons:** Defeats the seed brief's premise that AaC+DaC be engraved as *philosophy*, not just tooling. The operational stack without the framing reads as "another set of fitness rules" rather than as a load-bearing principle. Rejected.

## Consequences

**Positive:**

- Cornerstone status established without principle bloat.
- Both halves of the decision (machine-readable SSOT + authored rationale) are explicit.
- Future agents and humans reasoning about the philosophy see the AaC framing in the same locality as its parent principles.
- Token cost (~90) leaves headroom under the 25,000-token guardrail.

**Negative:**

- Two edits to `CLAUDE.md` to maintain; drift between them is a low-likelihood failure mode.
- Readers who skim only top-level principle headers (rare) miss the framing — acceptable because the clauses sit immediately under their parent headers.

**Operational:**

- Verifier's Phase 5 measures token cost when reviewing CLAUDE.md changes; a budget regression fails the verification.
- The clauses are referenced as `CLAUDE.md§Context Engineering` and `CLAUDE.md§Structural Beauty` in fitness-rule citations (per the citation contract in the related fitness-functions-infra ADR).
