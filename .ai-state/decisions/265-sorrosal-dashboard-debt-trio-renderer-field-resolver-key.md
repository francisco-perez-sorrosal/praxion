---
id: dec-265
title: Manifest `renderer:` field becomes a first-class resolveRenderer key
status: accepted
category: architectural
date: 2026-07-01
summary: Extend resolveRenderer to consult the manifest `renderer:` field as highest-priority lookup key, generalizing the api_reference special-case so the five per-artifact renderers resolve without hijacking shared diataxis/type keys.
tags: [dashboard, renderer-registry, diataxis, interface-design]
made_by: agent
agent_type: interface-designer
branch: dashboard-debt-trio
pipeline_tier: standard
affected_files:
  - dashboard_app/src/components/registry.ts
  - dashboard_app/src/app/documentation/page.tsx
dissent: The api_reference special-case already works; a fourth resolver key adds surface area for five renderers that could instead each be a distinct diataxis-like value, avoiding a signature change.
---

## Context

The five per-artifact renderers in td-027 (`metrics_view`, `plan_view`, `verification_report`, `idea_grid`, `architecture_explorer`) must be reachable from the one registry consumer — the documentation page — which dispatches through `resolveRenderer(diataxis?, contentType?)`. That resolver keys only on the Diátaxis value then the content `type`, then falls back to `DefaultShell`.

The doc manifest already assigns these names to surfaces via a `renderer:` field (e.g. `docs/architecture.md` carries `diataxis: reference` **and** `renderer: architecture_explorer`; `IDEA_LEDGER.md` carries `renderer: idea_grid`; the metrics JSONs carry `renderer: metrics_view`). But `resolveRenderer` never consults `renderer:` — it is dead metadata today, except `api_reference`, which is special-cased inside the server view-model (`documentation.ts`) by an inline `surface.renderer === "api_reference"` branch.

Keying the five renderers by `diataxis` or `type` is unsafe: `architecture_explorer`'s surface is `diataxis: reference` + `type: markdown` — the same keys shared by every reference doc. Registering `architecture_explorer` under `reference` or `markdown` would hijack all reference/markdown surfaces. The `renderer:` field is the only key that uniquely selects these surfaces. The concurrent hardening of `documentation.ts` on `main` (td-029, Wave 2) makes that file off-limits for this pipeline, so the api_reference special-case pattern (which lives in `documentation.ts`) cannot be extended for the five new renderers.

## Decision

Extend `resolveRenderer` to accept the manifest `renderer:` value as a new **highest-priority** lookup key, ahead of `diataxis` and `contentType`, terminating in the unchanged `DefaultShell` fallback:

```
resolveRenderer(renderer?, diataxis?, contentType?)
  → RENDERER_REGISTRY.get(renderer)   // NEW, highest priority
  → RENDERER_REGISTRY.get(diataxis)
  → RENDERER_REGISTRY.get(contentType)
  → DefaultShell
```

Register the five renderer-name keys plus (already-present) three Diátaxis keys in `RENDERER_REGISTRY`. The documentation page passes `selectedSurface?.renderer` as the new first argument. All changes live in `registry.ts` + `page.tsx` — `documentation.ts` is untouched. The `api_reference` special-case in `documentation.ts` stays as-is (it selects a distinct `renderMode: "api"` read path and is out of this pipeline's scope); this ADR does not remove it, only establishes the general resolver key that future work can migrate it onto.

## Considered Options

### Option A — `renderer:` as first-class highest-priority resolver key (chosen)

- Pros: uniquely selects the five surfaces; preserves the terminal `DefaultShell` fallback (the brief's guard); no `documentation.ts` change; additive and backward-compatible (all existing `resolveRenderer(diataxis, type)` calls keep working since the new param is optional and leading); one obvious place (`registry.ts`) owns renderer→component mapping.
- Cons: adds a third positional arg to a public-ish helper; two dispatch idioms coexist temporarily (`renderer:` key here vs. `api_reference` branch in `documentation.ts`).

### Option B — invent new pseudo-`diataxis` values for each renderer

- Pros: no resolver signature change.
- Cons: overloads the Diátaxis axis with non-Diátaxis concepts (`metrics_view` is not a Diátaxis mode); the manifest would need a second contract for the same surfaces; loses the honest `renderer:` field the manifest already emits. Rejected — conflates two orthogonal axes.

### Option C — extend the `documentation.ts` special-case per renderer

- Pros: matches the existing `api_reference` idiom exactly.
- Cons: `documentation.ts` is off-limits this pipeline (td-029 merge-conflict guard). Would also scatter renderer dispatch across the server view-model rather than centralizing it in the registry. Rejected on the hard constraint.

## Consequences

- Positive: the five renderers resolve deterministically; the registry becomes the single source of truth for renderer dispatch; fallback semantics unchanged; zero server-layer churn.
- Positive: `metrics_view` (a `type: json` surface rendering `renderMode: "code"`) is reachable via a small `page.tsx` branch that routes registered-renderer code surfaces through the registry — again no `documentation.ts` change.
- Negative: transitional duplication — `api_reference` still dispatches via the `documentation.ts` branch until a later pipeline migrates it onto the `renderer:` key. Tracked as a follow-up, not resolved here.

## Disconfirmation

- **Falsifier**: if a future surface legitimately needs the same `renderer:` value to map to different components by context, a flat registry key is wrong and dispatch must move back into a context-aware view-model.
- **Steelmanned runner-up (Option C)**: extending the `documentation.ts` special-case is the lowest-novelty choice — it reuses the exact api_reference idiom the team already reads. If `documentation.ts` were not off-limits, C's consistency-over-cleverness argument would be strong; the only decisive factor against it is the concurrent-hardening merge-conflict guard.
- **Reversal trigger**: revisit if renderer dispatch needs to depend on more than a single manifest field (e.g., audience + renderer), or if the api_reference migration onto the `renderer:` key proves the two-idiom split was avoidable from the start.
