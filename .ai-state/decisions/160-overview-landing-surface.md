---
id: dec-160
title: Add an /overview landing surface aggregating sentinel grade, metrics health, active workshops and ADR counts
status: accepted
category: architectural
date: 2026-05-12
summary: New /overview route + a server view-model that composes existing view-model reads into an at-a-glance "state of everything" landing; / redirects there instead of /architecture.
tags: [dashboard, information-architecture, overview, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/app/overview/page.tsx
  - dashboard_app/src/server/view-models/overview.ts
  - dashboard_app/src/components/overview-grid.tsx
  - dashboard_app/src/app/page.tsx
  - dashboard_app/src/components/sidebar-nav.tsx
---

## Context

The dashboard has 7 surfaces and `/` redirects straight to `/architecture`. There is no "state of everything" landing — the operator must tour all 7 pages to answer "is anything on fire?". The sidebar also wants live signals (active-workshop count, latest sentinel grade) that have no home today. A status console without an overview is missing its front door.

## Decision

Add an `/overview` route (`src/app/overview/page.tsx`, a Server Component) backed by a new `src/server/view-models/overview.ts` that **composes the results of the existing view-models** — `sentinel.ts` (latest report grade), `metrics.ts` (latest aggregate + the four KPI tones + sparklines), `workshops.ts` (count of active `.ai-work/<slug>/` pipelines), `adrs.ts` (finalized vs. draft counts) — plus the max-mtime "last activity" stamp. It reads the **same files** those view-models read; it introduces **no new data store, no cache, no shadow copy** (`dashboard-conventions.md` #1). The four reads parallelize with `Promise.all`. The `/` redirect changes from `/architecture` to `/overview`. The page renders a KPI-tile grid + quick-links into each surface (`overview-grid.tsx`); the sidebar gains a live-workshop count badge and a sentinel-grade chip fed from the same composed data.

States: rich (everything present) → degrades tile-by-tile to "not run yet" placeholders for any missing artifact family; if a freshly-onboarded project has *nothing*, the overview is a friendly "this project hasn't run any pipelines yet — here's what each surface will show" board (never a crash).

This is recommended as **second-cut** work (after the chrome and the two priority pages settle), but recorded now so it is in the implementation plan.

## Considered Options

### A — No overview; keep `/` → `/architecture`

Pros: nothing to build. Cons: the operator has no glance; the sidebar live badges have no data source; "is anything on fire?" requires a 7-page tour.

### B (chosen) — `/overview` composed from existing view-models, no new store

Pros: the highest-value IA addition; gives the sidebar badges their data; respects the no-store rule (pure composition of existing reads); the front door of a status console. Cons: one new route + one new (mostly-composition) view-model + one presentation component + a redirect change; read-amplification (4 view-models on one page load) — acceptable for a localhost read-only dashboard, mitigated by `Promise.all`.

### C — Bolt overview widgets onto the Architecture page instead of a new route

Pros: no new route. Cons: conflates two surfaces; "where do I go to see everything?" has no clean answer; the Architecture page is already the densest surface — adding overview widgets makes it worse.

## Consequences

Positive: a real front door; the operator answers "state of everything" in one screen; the sidebar live badges work; quick navigation into every surface. No new persistence — the filesystem-is-source-of-truth contract holds.

Negative: one new route, one new view-model (composition-heavy but small), one new component, one redirect change; a minor read-amplification on the landing load (4 parallel view-model reads). If any composed view-model is slow, the overview load inherits that cost — the same cost the user would pay visiting that surface directly, so net-neutral.
