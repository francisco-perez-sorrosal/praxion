---
id: dec-138
title: MCP TypeScript SDK v2 promotion — trigger-based review, not date-based
status: accepted
category: architectural
date: 2026-05-11
summary: mcp-crafting/contexts/typescript.md ships v1.x stable patterns; v2.0 alpha sub-package architecture is noted as preview. Promotion to v2 patterns triggered by upstream events, not calendar.
tags: [skills, mcp-crafting, typescript, sdk-versioning, review-protocol]
made_by: agent
agent_type: systems-architect
branch: worktree-multi-language-support
pipeline_tier: full
affected_files:
  - skills/mcp-crafting/contexts/typescript.md
  - .ai-state/LANDSCAPE_WATCHLIST.md
---

## Context

The MCP TypeScript SDK (`@modelcontextprotocol/sdk`) has a stable v1.x and an alpha v2.0 (sub-packaged: `@modelcontextprotocol/server`, `@modelcontextprotocol/node`, `@modelcontextprotocol/express`, `@modelcontextprotocol/hono`, `@modelcontextprotocol/fastify`) as of April 2026. v2 adds Standard Schema support (Zod v4, Valibot, ArkType acceptance), which would also resolve the Zod v3/v4 cross-skill version split (see Zod Version-Split Housing ADR).

The Phase 1b research identified an open question: when do we promote v2 patterns into `mcp-crafting/contexts/typescript.md`? The options are date-based ("review Q3 2026"), trigger-based (review when upstream events occur), or ad-hoc (rewrite when needed).

Date-based reviews decay — by the date, either v2 shipped early (review is too late) or upstream slipped (review fires on stale state). Praxion does not control the upstream release cadence; the review should fire on observable upstream events.

## Decision

`mcp-crafting/contexts/typescript.md` v1 documents the v1.x stable SDK (monolithic `@modelcontextprotocol/sdk` package) as the recommended baseline, with an explicit "v2 alpha (sub-package architecture) is preview as of April 2026 — promotion criteria below" note.

**Review triggers** — re-evaluate promoting v2 patterns into the context when ANY of these is true:

1. `@modelcontextprotocol/sdk` v2.0.0 stable release is announced upstream
2. The Anthropic-published MCP TypeScript SDK README declares v2 production-ready
3. The Standard Schema bridge (Zod v4 / Valibot / ArkType acceptance) lands in stable v1 — i.e., the v1→v2 promotion path becomes lossless and Zod v3/v4 cross-skill conflict resolves naturally

When ANY trigger fires, the next ADR-creating pipeline that touches `mcp-crafting` opens this ADR for supersession or update.

**Watchlist entry** — add an entry to `.ai-state/LANDSCAPE_WATCHLIST.md` referencing this ADR so the watchlist is the operational surface for "is anything new upstream?" sweeps. The watchlist already exists in Praxion (per the worktree state); this ADR is the binding artifact.

## Considered Options

### Option 1 — Date-based review (e.g., "review by Q3 2026")

**Pros**: Calendar-anchored; predictable cadence.

**Cons**: Date decays; either fires too late or on stale upstream state; nobody owns the calendar reminder; Praxion does not control upstream release timing.

### Option 2 — Trigger-based review (chosen)

**Pros**: Review fires only when material upstream change occurs; no calendar inertia; triggers are observable (release announcement, README declaration, feature landing).

**Cons**: Nobody is explicitly "watching" upstream; mitigated by the watchlist entry and by sentinel's periodic upstream scanning.

### Option 3 — No review schedule; rewrite when needed

**Pros**: Zero overhead; reactive.

**Cons**: Risks long-term drift — agents working in `mcp-crafting/contexts/typescript.md` may build on v1 patterns long after v2 is stable, accumulating retraining cost; no durable record that the question was asked.

## Consequences

### Positive

- Review fires on actual upstream change, not arbitrary calendar dates
- Watchlist entry concentrates "what to watch" into one operational surface
- The triggers are public and observable — anyone (Praxion maintainer, sentinel, external user) can detect them
- Future v3/v4 alpha lifecycles inherit the same pattern: ship stable patterns + note alpha + register triggers

### Negative

- Nobody explicitly owns watching the triggers — relies on Praxion's watchlist sweep cadence (informal)
- Review may lag the upstream stable release by weeks if the watchlist sweep isn't frequent — acceptable given v1.x stays usable

### Neutral

- Establishes a precedent for upstream-volatility decisions in Praxion: document the stable baseline + name the triggers + register a watchlist entry
