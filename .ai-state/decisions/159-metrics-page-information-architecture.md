---
id: dec-159
title: Metrics page information architecture — health-strip glance, KPI sparkline tiles, Tufte trend pass, relocated snapshot selector
status: accepted
category: architectural
date: 2026-05-12
summary: Restructure the Metrics surface around an at-a-glance health strip + KPI tiles with sparklines, a Tufte-discipline trend-chart pass, a relocated snapshot selector with an explicit compare mode, and a consolidated raw-data disclosure.
tags: [dashboard, metrics-page, information-architecture, data-visualization, tufte, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/components/metrics-dashboard.tsx
  - dashboard_app/src/components/metrics-summary-cards.tsx
  - dashboard_app/src/components/metrics-trends.tsx
  - dashboard_app/src/components/viz/trend-chart.tsx
  - dashboard_app/src/components/viz/sparkline.tsx
---

## Context

The Metrics surface answers the project manager's question: "is the codebase healthy, and which way is it trending?" Today it is a flat dump: a snapshot `<select>` buried mid-page → 5 summary cards → a recharts trend grid (with plot-area gradients and dashed gridlines — chartjunk) → a hot-spots table + collectors list → two `<details>` raw blobs at the bottom. Everything renders at once; there is no at-a-glance answer; the snapshot selector (which scopes everything below it) is not where the eye lands first; the delta is "vs previous comparable run" with no way to choose a comparison point.

## Decision

Restructure around an at-a-glance layer and a drill-down layer:

- **At-a-glance (above the fold)**: a *health strip* — one card, one sentence, that aggregates the four KPI tones into a single word (STABLE / IMPROVING / WORSENING / "data confidence reduced" when a collector is degraded) followed by the per-metric arrows (↘ improving · ↗ +2 hot-spots · → flat churn · 78% coverage ✓). The **snapshot selector lives here** (it scopes everything below), alonga a `⇄ compare` toggle. Below the strip: 4–5 **KPI tiles**, each = the value in sans-bold/32px + a ~60×20 `Sparkline` of *that metric's own history* + the delta vs. the previous comparable run (or vs. the chosen comparison snapshot when compare-mode is on) + a tone word + a 2px tone-color top accent.
- **Drill-down (below)**: the **trend charts** as small multiples (2-up, ~200px tall), with a **Tufte discipline pass** — one line per chart where units differ; no plot-area fill (remove the `linear-gradient`); no dashed gridlines (remove `stroke-dasharray: 4 8` — keep at most a single faint baseline); no legend box (direct-label the line at its right end via recharts `<Label position="right">`); x-ticks only at first / last / selected-snapshot; ≤ 3 y-ticks; the selected snapshot marked with a small filled dot + its date. Then the **hot-spots table** (top 10, "show all N ▸" reveals the rest; the Score column gets a CSS-only inline sparkbar for visual ranking; row hover → file-path popover with "rank X / score Y / churn Z"). Then the **collectors** as compact chips in one row (icon ✓/⚠/✕ + name + version-or-reason inline, `--color-danger-subtle` when degraded). Then **one** "Raw data ▸" disclosure containing both the selected-snapshot JSON `<pre>` and the `METRICS_LOG.md` markdown (consolidating the two current `<details>`).
- **Compare mode** (`⇄ compare`): reveals a second `<select>` ("compare to: <older snapshot>"); the KPI tiles then show two values (selected vs. comparison); the trend charts add a faint vertical band between the two dates. Replaces the implicit "vs previous comparable run" with an explicit user-chosen before/after — useful for "did my refactor help?". The existing `sliceSnapshotsUpTo` / `sliceLogSeriesUpTo` helpers already do most of the slicing; compare just picks two indices.

State inventory (rich / single-snapshot / no-hotspots / no-collectors / degraded-collector / empty / loading / malformed-snapshot / missing-log) is enumerated in `INTERFACE_DESIGN.md` §5.3 — every state degrades gracefully (`dashboard-conventions.md` #6); recharts already falls back from `seriesFromLog` to `seriesFromSnapshots` when `METRICS_LOG.md` is absent.

## Considered Options

### A — Keep the flat dump; just restyle the cards and remove the chart gradients

Pros: minimal effort. Cons: the PM still has to read the whole page to answer "is anything trending bad?"; the snapshot selector is still mis-placed; no explicit compare.

### B (chosen) — Health strip + KPI sparkline tiles + Tufte trend pass + relocated selector + compare mode

Pros: the question is answered in one line above the fold; the selector is where it scopes from; the charts shed chartjunk (Tufte: high data-ink ratio); compare-mode supports before/after analysis; raw data is one disclosure, not two. Cons: a restructure of `metrics-dashboard.tsx`; chart-config changes across `metrics-trends.tsx` + `trend-chart.tsx`.

### C — Replace recharts with a hand-rolled SVG chart layer for full Tufte control

Pros: total control over every pixel. Cons: recharts already supports the Tufte settings via props (`CartesianGrid horizontal={false} vertical={false}`, custom `ticks`, `<Label>`); hand-rolling is a maintenance liability for no gain — over-engineering. (There is already a hand-rolled `viz/trend-chart` SVG variant *and* a recharts one — consolidating *toward* recharts, not away.)

## Consequences

Positive: an at-a-glance health answer; a correctly-placed snapshot control; clean, high-data-ink trend charts; an explicit before/after comparison; consolidated raw data. The metrics view-model and the JSON-report contract are unchanged — this is presentation restructuring.

Negative: `metrics-dashboard.tsx` is restructured; `metrics-trends.tsx` and `trend-chart.tsx` get a config pass; `metrics-summary-cards.tsx` gains a sparkline per tile and a two-value display path. The "health strip sentence" derivation logic is new (aggregating the four tones into one word) — small, but new code with its own state-inventory.
