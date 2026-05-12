---
id: dec-161
title: Server-side SVG normalization + responsive-default diagram frame + opt-in pan/zoom Expand modal
status: accepted
category: architectural
date: 2026-05-12
summary: Normalize Mermaid/LikeC4 SVGs server-side, render them responsively by default, demote pan/zoom to a fullscreen Expand modal.
tags: [dashboard, diagrams, svg, rendering, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/server/diagrams/normalize-svg.ts
  - dashboard_app/src/server/view-models/architecture.ts
  - dashboard_app/src/components/viz/diagram-viewer.tsx
  - dashboard_app/src/components/viz/diagram-frame.tsx
  - dashboard_app/src/components/viz/diagram-modal.tsx
  - dashboard_app/src/components/viz/use-pan-zoom.ts
  - dashboard_app/src/app/globals.css
---

> **Architect amendment (2026-05-12, systems-architect, pipeline `dashboard-ux-overhaul`):** two refinements to the Decision below — (1) `normalizeSvg` runs in the `architecture.ts` view-model path **only**; `/api/diagram/route.ts` is **unchanged in the first cut** (it serves SVGs as opaque `<img src>` — no aspect-box wrapper, no React layer to read `data-aspect`, and adding `normalizeSvg` there would require adding `sanitizeSvg` too, which the route deliberately omits today; a thin `stripIntrinsicSizing` subset is a documented follow-up if an `<img>`-path sizing defect surfaces). (2) The regex-not-XML-reparse technique is ratified with an explicit input→output contract and an idempotency requirement (see the **Normalization contract** subsection added under the Decision). The `affected_files` list above is updated to drop `route.ts` and add the split components.

## Context

The Architecture page's "Diagrams" section renders Mermaid sequence diagrams and LikeC4 flowcharts as inline SVGs inside a `usePanZoom` pan/zoom viewport (`diagram-viewer.tsx` + `use-pan-zoom.ts`), in a fixed `clamp(280px, 55vh, 560px)` `overflow: hidden` container. It renders badly: the SVG appears at near-native size with only the top-left corner visible; fit-to-viewport is unreliable.

Root cause (confirmed against the 6 rendered SVGs in `.ai-state/diagrams/*/rendered/`): Mermaid emits the root element as `<svg id="my-svg" width="100%" style="max-width: 1645.5px; background-color: white;" viewBox="-50 -10 1645.5 597">` — no `height` attribute, and an **inline `style` with `max-width`** whose specificity (1000) beats the stylesheet's `.diagram-viewer-transform svg { max-width: none }`. The SVG therefore lays out at roughly its `max-width` inside the cramped clipped viewport, and the JS `fitTransform` transform math runs against a box that is already mis-sized → top-left-corner crop. LikeC4 flowcharts carry the same `style="max-width: <N>px"` pattern. The SVGs are sanitized server-side (`sanitize.ts`) but not normalized.

Pan/zoom is also the wrong *default* interaction: the operator almost always wants to look at a diagram, not pan it. Pan-on-first-contact is an affordance mismatch (Norman) and a Hick's-Law cost.

## Decision

Three layers:

1. **Server-side SVG normalization** — a new pure module `dashboard_app/src/server/diagrams/normalize-svg.ts` (`normalizeSvg(svg: string): string`), invoked immediately after `sanitizeSvg` in the `architecture.ts` view-model path (the `/api/diagram` route is unchanged — see the architect amendment above). On the **root `<svg>` only** (regex rewrite of the open-tag — not a full XML re-parse): parse the `viewBox` (fall back to `width`/`height` attrs; if neither, leave untouched and mark "unmeasurable"); strip the `width` and `height` *attributes*; strip `max-width`, `max-height`, `width`, `height`, and `background-color` from the inline `style=` (string-edit, keeping any other style content); add `preserveAspectRatio="xMidYMid meet"` if absent; add `data-aspect="<vbW/vbH>"`, `data-vb-w`, `data-vb-h` attributes. Idempotent; pure; trivially testable.

   **Normalization contract** (binding — the implementer codes to this; the test-engineer derives the test matrix from it):

   - **Input:** an already-sanitized SVG string. **Output:** an SVG string.
   - **Technique:** a regex rewrite of the **first `<svg ... >` open-tag only** — not a full `htmlparser2` reparse-and-reserialize. Rationale: we touch exactly one element and four kinds of attribute; a full reparse on every SVG on every request is unnecessary cost, and reserialization risks subtle changes (entity encoding, self-closing form, attribute order) to the already-sanitized inner markup that could break Mermaid/LikeC4's own `<style>#my-svg{...}` ID-scoped rules. `sanitize.ts` already does the heavyweight parse; this is a light post-pass on a bounded, well-understood string (`<svg` appears once, near the start, after sanitization has normalized tag casing).
   - **Operations on the root `<svg>` open-tag:** (a) parse `viewBox` → `[minX, minY, vbW, vbH]`; if absent or unparseable, parse the `width`/`height` *attributes* as the intrinsic box; if neither yields two positive numbers, **return the input string unchanged** (no `data-aspect`) and do not throw; (b) remove the `width` and `height` *attributes*; (c) in the `style=` value, remove the `max-width`, `max-height`, `width`, `height`, `background-color` declarations (case-insensitive, semicolon-delimited); preserve any other declarations; if `style` becomes empty/whitespace, drop the attribute; (d) add `preserveAspectRatio="xMidYMid meet"` only if no `preserveAspectRatio` attribute is already present; (e) add `data-vb-w="<vbW>"`, `data-vb-h="<vbH>"`, `data-aspect="<vbW/vbH>"` (aspect rounded to ~4 decimal places).
   - **Idempotent:** `normalizeSvg(normalizeSvg(s)) === normalizeSvg(s)` for all `s` (stripped attrs → no-op; `data-*` overwritten with the same value; `preserveAspectRatio` already present → not re-added).
   - **Scope guard:** match only the *first* `<svg` occurrence; nested `<svg>` elements and all `<style>`/element internals are out of bounds.

2. **Responsive-by-default rendering** — a new `<DiagramFrame>` component replaces `DiagramViewer` for the inline-card use: a CSS `aspect-ratio`-boxed container (the ratio comes from the server-computed `data-aspect`, so the layout is correct on the server-rendered HTML before any JS runs) with the SVG at `width: 100%; height: 100%`. No scroll, no crop, for any diagram size. A `max-height: min(70vh, 720px)` cap keeps an extreme aspect ratio from blowing the page height — and that is exactly when the user reaches for Expand.

3. **Opt-in pan/zoom Expand modal** — the diagram caption carries a `⤢ Expand` button that opens a focus-trapped fullscreen modal (`role="dialog"`, `aria-modal="true"`, Escape closes, focus returns to the trigger). The existing `usePanZoom` hook and `fitTransform` math are reused *inside the modal* — where the box is now well-sized (the modal is a fixed large viewport and the SVG no longer carries a rogue `max-width`), so the existing fit-on-mount + ResizeObserver logic finally works. Keyboard `+`/`−`/`0`/arrows already implemented.

## Considered Options

### A — Keep pan/zoom as the default; only fix the normalization

Pros: smallest diff. Cons: pan/zoom is still the wrong first-contact interaction; the operator pays a Hick's-Law cost on every diagram view; "fit" still has to be reliable as the *default* render which is harder than fixing it as a *modal* render.

### B — Server-render diagrams to rasterized PNGs

Pros: no SVG-rendering quirks at all; fixed dimensions. Cons: loses vector crispness; loses LikeC4 styling; cannot theme for dark mode; adds a server-side rasterization dependency; defeats the existing sanitized-inline-SVG pipeline.

### C (chosen) — Normalize server-side → responsive default → opt-in pan/zoom modal

Pros: the default view is correct by construction (server-computed aspect box, zero JS, works pre-hydration); the power tool is one click away; the existing pan/zoom code is reused, not rewritten; works in dark mode (we drop `background-color: white`). Cons: one new server module + a component split; the pan/zoom code moves but does not change.

### D — Technique sub-decision: regex on the root open-tag vs. full `htmlparser2` reparse

`htmlparser2` is available transitively via `sanitize-html`. **Chosen: regex on the root `<svg>` open-tag** (see the Normalization contract above). A full reparse-and-reserialize on every SVG on every request is unnecessary cost when we touch exactly one element, and reserialization risks subtle changes to the already-sanitized inner markup. Rejected the full-reparse option for cost + reserialization risk; the tight scope (one element, near the start) plus an explicit idempotency + unmeasurable-input test matrix make the regex safe.

## Consequences

Positive: the #1 reported dashboard defect is fixed at the root (upstream of rendering); diagrams of any size render correctly with no scroll/crop on the inline Architecture-page path; dark-mode theming becomes possible (no forced white background); the `DiagramViewer`-conflates-show-with-pan-zoom cohesion smell is resolved (`DiagramFrame` + `DiagramModal`); `normalizeSvg` is a pure, idempotent string function — trivially unit-testable.

Negative: a new `~60-line` server module and a component split (`DiagramViewer` → `DiagramFrame` + `DiagramModal`); the Architecture page must collapse all-but-the-first diagram to avoid painting 6 large SVGs at once (a separate, trivial `defaultOpen` change); the `/api/diagram` `<img>`-served path does **not** get the `max-width`-strip in the first cut (accepted — browsers size `<img>`-embedded SVGs by their own box, and no `<img>`-path crop defect is reported; a `stripIntrinsicSizing` subset is a documented follow-up). The "unmeasurable SVG" edge case (no `viewBox`, no `width`/`height`) degrades to the current behavior — acceptable, rare.
