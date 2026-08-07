---
id: dec-050
title: Raise always-loaded budget to 25,000 tokens and reframe as attention-relevance guardrail
status: accepted
category: architectural
date: 2026-04-17
summary: Raise the always-loaded token ceiling from 15,000 to 25,000 and reframe it as a failure-mode guardrail — the principle is that every always-loaded token must earn its attention share, not "minimize tokens."
tags: [token-budget, always-loaded, attention-relevance, configuration, decision-quality]
made_by: user
pipeline_tier: lightweight
affected_files:
  - CLAUDE.md
  - README_DEV.md
  - rules/CLAUDE.md
  - ROADMAP.md
  - agents/sentinel.md
affected_reqs: []
---

## Context

The always-loaded budget ceiling has evolved implicitly:

- **Feb 2026**: 8,500-token ceiling (see `.ai-state/TOKEN_BUDGETING_2026-02-09_15-18-42.md:6`)
- **Later**: raised to 15,000 tokens without a dedicated ADR (referenced in `dec-022`, `dec-027`, `dec-034`, and three declaration sites)
- **Now (2026-04-17)**: measured always-loaded surface is 54,071 chars / ~15,449 tokens at 3.5 chars/token — right at the 15k ceiling, ~100 tokens of headroom

The 15k rationale in `dec-022` was "preserve headroom for session work." That reasoning was written against 200k context. Under Opus 4.7's 1M context window:

- 15k is 1.5% of the window; 25k is 2.5%
- Raw-capacity headroom is no longer a binding constraint at either ceiling
- Attention-dilution remains a constraint, but effective attention (empirically ~200k) is not meaningfully degraded between 15k and 25k always-loaded
- Per-turn input cost at 25k × 100 sessions/month is <$8 uncached, <$1 cached — trivial

The current equilibrium is unhealthy: rules sit at the ceiling, so any worthwhile new content forces either rejection or re-extraction cycles. The Phase 1.7 ROADMAP baseline (`ROADMAP.md:599`) already aimed for `<8,500` rules-only and `<8,000` at Phase 3 — targets that pre-date the 1M-context reality and the project's recent growth.

The deeper issue is that a raw token cap is a *proxy* for "attention-relevance per token." When the cap is treated as the principle, the project optimizes for shrinkage rather than for each rule earning its attention share.

## Decision

**Raise the always-loaded token ceiling to 25,000 tokens** (from 15,000). Update all three declaration sites, the sentinel T02 check, and the ROADMAP Phase 3 targets.

**Reframe the budget** from "total token cap" to "attention-relevance guardrail":

> Every always-loaded token must earn its attention share — applied in >30% of sessions, or unconditionally relevant (like the behavioral contract). The 25,000-token cap is a failure-mode guardrail, not a target.

The number provides mechanical enforcement (sentinel T02); the principle provides judgment during rule authoring.

This decision does **not** supersede `dec-022` (coordination-detail-extraction) or `dec-027` (principles-embedding-strategy). Both were correct under the old ceiling and remain correct under the new ceiling — they address artifact placement, not budget size.

## Considered Options

### Option A — Keep at 15,000

Preserves historical discipline and forces continuous pressure to move content to skills. But current state (~15.5k) means any new rule causes a cap breach, forcing either rejection of worthwhile content or aggressive re-extraction. The cap becomes an anti-signal — filtering not on relevance but on incumbency.

### Option B — Raise to 20,000

Smaller bump; ~4.5k headroom. Disciplined but tight. Loses the reframing opportunity; the gap between current state and cap is narrow enough that discipline remains forced rather than principled.

### Option C — Raise to 25,000 (chosen)

1.67× the prior ceiling. Provides ~9.5k headroom from current state — enough for 2-3 moderate new rules without immediately re-triggering cap pressure. Cost at Opus 4.7 is <$8/month uncached at 100 sessions. Attention-dilution remains well within effective window. The reframe from "target" to "guardrail" forces authors to reason about attention-relevance rather than just token count.

### Option D — Raise to 30,000+

Loses the cap's function as a forcing-function. A cap that never bites is decoration. If 25k proves too tight in practice, re-examine rather than pre-emptively over-allocate.

### Option E — Remove hard cap; use attention-relevance principle only

Attention-relevance is the real principle, but principles without numbers are hard to enforce by sentinel checks. The 25k number provides mechanical enforcement; the principle provides authorial judgment. Both coexist.

## Consequences

### Positive

- Current state (~15.5k) fits with ~9.5k headroom — eliminates false-positive cap-breach pressure
- Reframing shifts authorial conversation from "how to fit" to "is this worth attention"
- Opens space for modest additions (e.g., `design-synthesis` reference file in the in-progress `design-dialectic` pipeline) without triggering re-extraction cycles
- Aligned with 1M context reality (2.5% of window)
- Lightweight-tier cost to ship: 5 file edits + 1 ADR + 1 index regen

### Negative

- Raising the cap sends a "more is OK" signal unless the reframing is internalized — docs must lead with the reframe, not the number
- Larger always-loaded surface = larger attention-dilution tail risk (mitigated: still 2.5% of 1M window; effective attention bounded by training, not window size)
- Sentinel T02 check threshold updated; historical sentinel reports use 15k baseline — trend analysis for pre-2026-04-17 reports must use the old ceiling

### Neutral

- `dec-022`, `dec-027`, `dec-034` remain in force. Budget pressure was never the sole rationale for those decisions; artifact-placement reasoning carries them independently of the ceiling value.

### Follow-ups (non-blocking)

- Monitor actual utilization across the next 5 sentinel reports. If it stays below 70% of 25k (≈17,500 tokens) with no pressure, the cap is functioning as a guardrail and not a constraint.
- If a single artifact exceeds 30% of the ceiling (≈7,500 tokens) it should trigger authorial review for progressive-disclosure opportunities — independent of total-budget status.
