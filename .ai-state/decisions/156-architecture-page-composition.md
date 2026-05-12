---
id: dec-156
title: Architecture page two-column composition — Diagrams row + Component-index ToC + DESIGN.md/architecture.md cards
status: accepted
category: architectural
date: 2026-05-12
summary: Restructure the Architecture surface into a Diagrams row plus a two-column layout (sticky Component-index ToC parsed from DESIGN.md + the two doc cards), with AaC region badges as inline chips and section anchoring.
tags: [dashboard, architecture-page, information-architecture, progressive-disclosure, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/app/architecture/page.tsx
  - dashboard_app/src/components/markdown-toc.tsx
  - dashboard_app/src/components/viz/diagram-viewer.tsx
  - dashboard_app/src/app/globals.css
---

## Context

The Architecture surface today is a vertical stack of always-open giant collapsibles: Diagrams (a list of `defaultOpen` `ArtifactCard` + `DiagramViewer`), then "Design target" (`.ai-state/DESIGN.md` rendered via AaC generated/authored region split, each region with a full-width badge), then "Developer guide" (`docs/architecture.md`). There is no in-page navigation, no cross-referencing between the diagrams and the prose, no way to jump to a section, and the AaC badges are heavy banners. It is the most information-dense surface in the dashboard and reads as an undifferentiated dump.

## Decision

Restructure into a Diagrams row + a two-column body:

- **Row 1 — Diagrams** (full width): the first diagram open by default rendered via the new responsive `<DiagramFrame>` (see the SVG-normalization ADR); the rest collapsed (name + type, "▸ open" renders the frame on demand) — this also bounds the paint cost of multiple large SVGs. Diagram order is config derived server-side from the filenames (most-orienting first, e.g. `deployment-system-context`, `agent-pipeline-execution`, then the rest) — no MD duplication. Each has a `⤢ Expand` affordance opening the pan/zoom modal.
- **Row 2 — two columns** (single column below 1080px):
  - **Left (sticky, ~260px) — "Component index"**: a flat list of the components named in `DESIGN.md`'s component map, *parsed at view-time from the MD body* (never a hand-authored list — MD stays the single source of truth). Each entry anchors into the `DESIGN.md` body section that documents it. Hovering a component name shows a popover with that component's one-line role (the first sentence after its heading in `DESIGN.md`, read at view-time) plus an "open ↓" anchor. On this surface the Component index *is* the in-page ToC for the right column. Below 1080px it collapses to an "On this page ▸" disclosure above the doc cards.
  - **Right (fluid)** — two cards: "Design target — `.ai-state/DESIGN.md`" rendered via the existing AaC region split (each region keeps its badge, restyled from a full-width banner to a small inline chip at the region's top-left: `[Authored · owner=…]` / `[Generated · source=… view=…]`); and "Developer guide — `docs/architecture.md`" (no AaC regions). Both get slugged headings + the "link to this section" affordance (from the heading-anchor ADR). The page scrolls; the left ToC is `position: sticky` (no inner-scroll container — simpler and more robust).
  - Below the right column: a "Sources ▸" disclosure carrying the old source-contract text ("Reads `.ai-state/DESIGN.md`, `docs/architecture.md`, and SVGs directly").

State inventory (rich / no-diagrams / only-DESIGN / only-architecture.md / empty / loading / per-card error / all-diagrams-unreadable) is enumerated in `INTERFACE_DESIGN.md` §4.3 — every state degrades gracefully without crashing the page (`dashboard-conventions.md` #6).

## Considered Options

### A — Keep the vertical stack; just restyle and add a top-of-page ToC

Pros: minimal restructure. Cons: a single full-width ToC at the top of a long page is far less useful than a sticky side ToC the reader keeps in view while scrolling; no place for the diagrams-vs-prose relationship; the AaC banners stay heavy.

### B (chosen) — Diagrams row + two-column body with a sticky Component-index ToC

Pros: the Component index doubles as navigation, a hover-to-reveal architecture map, and the in-page ToC; the diagrams are bounded (collapse-all-but-first); the AaC badges shrink to inline chips; section anchoring + cross-links become possible. Cons: a real restructure of `architecture/page.tsx`; depends on the heading-anchor ADR and the DiagramFrame split.

### C — A dedicated graph/canvas view of the component map (LikeC4-style interactive)

Pros: visually impressive. Cons: large new build; the LikeC4 *diagrams* already cover the graph view; over-engineering for a status surface — the prompt asks for a targeted restructure, not a new canvas app.

## Consequences

Positive: the Architecture surface becomes navigable and cross-referenced; the diagrams render correctly and don't drown the page; the AaC provenance is visible but not shouty; section URLs are shareable. The MD remains the single source of truth (the Component index and the hover-card content are *parsed from* the MD at view-time, not copied).

Negative: a structural rewrite of `architecture/page.tsx` (one file); a new `<MarkdownToc>` component; a dependency on the heading-anchor and DiagramFrame decisions. If `DESIGN.md`'s component-map section structure is non-standard in some project, the Component-index parse degrades to "no index" — single column, just the doc cards.
