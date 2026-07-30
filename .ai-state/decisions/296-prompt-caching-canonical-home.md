---
id: dec-296
title: Single canonical home for Anthropic prompt-caching mechanics
status: accepted
category: implementation
date: 2026-07-30
summary: platform-services.md is the canonical, detailed home for Anthropic prompt-caching mechanics; api-features.md keeps only the cache_control parameter shape and a link back.
tags: [context-engineering, skills, claude-ecosystem, prompt-caching, duplication]
made_by: agent
agent_type: context-engineer
branch: main
pipeline_tier: lightweight
affected_files:
  - skills/claude-ecosystem/references/platform-services.md
  - skills/claude-ecosystem/references/api-features.md
  - skills/claude-ecosystem/SKILL.md
  - skills/llm-prompt-engineering/SKILL.md
  - skills/llm-prompt-engineering/contexts/python.md
  - skills/llm-prompt-engineering/references/versioning.md
  - skills/agent-crafting/SKILL.md
  - skills/multi-perspective-analysis/references/heterogeneous-orchestration.md
---

## Context

Praxion had two independent "Prompt Caching" sections — one in `skills/claude-ecosystem/references/platform-services.md` (owns cost/ops framing) and one in `skills/claude-ecosystem/references/api-features.md` (owns API feature parameters) — each carrying its own copy of the TTL/pricing table. The two copies drifted: `platform-services.md` stated a 25% write premium for the 1-hour TTL tier (the correct figure is 100%/2x — 25% applies only to the 5-minute tier), and both files carried a flat, now-outdated Opus/Sonnet-vs-Haiku minimum-block-size split that Anthropic has since made per-model. Four other files (`claude-ecosystem/SKILL.md`, `llm-prompt-engineering/SKILL.md`, `llm-prompt-engineering/contexts/python.md`, `llm-prompt-engineering/references/versioning.md`) each carried their own hardcoded copy of the stale 1024/2048 numbers, multiplying the drift surface.

## Decision

`platform-services.md` is the single canonical home for detailed Anthropic prompt-caching mechanics (TTL/cost tables, automatic caching, the 20-block lookback window, the cache invalidation hierarchy, and the per-model minimum-block-size table). `api-features.md` keeps only the `cache_control` parameter shape (2-3 lines) and a link back to `platform-services.md § Prompt Caching`. All other files that referenced specific numbers (SKILL.md gotcha bullets, `contexts/python.md`, `versioning.md`) were rewritten to point at the canonical table instead of restating it, and the per-model minimum-block table is explicitly flagged as "shifts with every model release — verify at platform.claude.com/docs" rather than presented as permanently fixed.

## Considered Options

### A: Keep both detailed copies, just fix the numbers in both

Fixes the immediate staleness but reproduces the exact failure mode that caused the drift — two independently-edited copies of the same fast-moving numbers. Rejected: doesn't address the root cause.

### B: Single canonical home (chosen)

`platform-services.md` owns the mechanics; every other reference is a link, not a copy. New model releases require exactly one edit. `api-features.md`'s existing boundary note ("API feature parameters" vs. platform-services.md's "cost strategies") already made platform-services.md the more natural fit for cost/TTL/premium content.

### C: Extract a new shared reference file for prompt-caching mechanics

Considered and rejected as unnecessary indirection — `platform-services.md` already existed as a Prompt Caching section with the right boundary framing; adding a third file would have added a hop without removing duplication risk elsewhere (skills still need *a* file to point at).

## Consequences

**Positive:** one edit point for future model-lineup changes to the minimum-block table; the two files' existing "cost strategies" vs. "API parameters" boundary is now actually honored instead of both drifting into each other's territory; four downstream files no longer hardcode a number that will go stale again.

**Negative:** `api-features.md` readers must follow a link for the full mechanics instead of reading inline — acceptable given the file's own stated boundary is parameters, not cost/ops depth.

## Disconfirmation

- **Falsifier:** if `api-features.md` readers are shown to need the full TTL/premium/invalidation detail inline (e.g., because they never navigate to platform-services.md in practice), the summary-and-link split is wrong and the content should be duplicated or merged into one file instead.
- **Steelmanned runner-up:** Option A (fix both copies in place) is simpler to review in a diff and requires no cross-file navigation — its weakness is only realized on the *next* Anthropic pricing/model change, which is exactly when this decision was made in response to the same failure recurring.
- **Reversal trigger:** if a second file drifts from `platform-services.md` again within the next few model-lineup updates despite this split, escalate to a shared skill-level reference file (Option C) as the more durable fix.
