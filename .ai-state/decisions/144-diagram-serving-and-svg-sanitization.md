---
id: dec-144
title: Dashboard diagram serving — route handler + markdown image-ref rewrite + server-side SVG sanitization
status: accepted
category: architectural
date: 2026-05-11
summary: A Next.js route handler streams allowlisted project-root SVGs; markdown bodies' relative <img> refs are rewritten server-side to that route; inline-injected SVGs (interactive viewer) are scrubbed with sanitize-html; pan/zoom is hand-rolled (no dep).
tags: [dashboard, diagrams, svg, sanitization, security, nextjs, route-handler]
made_by: agent
agent_type: systems-architect
branch: worktree-dashboard-redesign
pipeline_tier: full
affected_files:
  - dashboard_app/src/app/api/diagram/route.ts
  - dashboard_app/src/server/diagrams/sanitize.ts
  - dashboard_app/src/server/diagrams/rewrite-image-refs.ts
  - dashboard_app/src/server/artifacts/files.ts
  - dashboard_app/src/server/view-models/architecture.ts
  - dashboard_app/src/components/viz/diagram-frame.tsx
  - rules/writing/diagram-conventions.md
---

## Context

`dashboard_app/` renders DESIGN.md and architecture.md via `react-markdown`, which emits `<img src="...">` and `![]()` verbatim. The browser resolves those relative paths against the current page URL (`/architecture`), so `<img src="../docs/diagrams/architecture/rendered/context.svg">` 404s. There is no static file serving, no image proxy, no preprocessing. Separately, `walkRenderedSvgs` only scans `docs/diagrams/`, missing the four Mermaid-sourced SVGs DESIGN.md references under `.ai-state/diagrams/`. The redesign also adds an interactive (pan/zoom) diagram viewer, which requires inline SVG in the DOM — and the dashboard runs against arbitrary Praxion-managed projects, so an SVG committed into a project's `diagrams/` directory could carry `<script>` or `on*` handlers.

Activation: yes — new HTTP surface, security boundary for arbitrary-project content, technology choice (sanitizer dep).

## Decision

1. **Route handler** — `dashboard_app/src/app/api/diagram/route.ts`: `GET /api/diagram?path=<project-relative-path>` → streams the file with `Content-Type: image/svg+xml`, `Cache-Control: no-store`; reuses `assertAllowedArtifactPath` (the same gate every other read uses) → `403` on disallowed/outside-root, `400` on missing `path`, `404` on absent file; restricts to `.svg` extension as defense in depth.
2. **Markdown image-ref rewrite** — `dashboard_app/src/server/diagrams/rewrite-image-refs.ts`: rewrites relative `<img src>` / `![]()` references in DESIGN.md / architecture.md bodies whose resolved target is inside the allowlist to `/api/diagram?path=<rel>`; absolute and `http(s):` / `data:` URLs are left untouched; unrecognized embeds are left as-is (broken image, never a crash).
3. **Scanner second root** — `walkRenderedSvgs` scans both `docs/diagrams/**/rendered/*.svg` and `.ai-state/diagrams/**/rendered/*.svg`.
4. **Sanitization** — `dashboard_app/src/server/diagrams/sanitize.ts`: server-side `sanitize-html` with an SVG-permissive element/attribute allowlist (geometry + presentation + gradients + markers + `use` + `title`/`desc`/`style`), disallowing `script`, `foreignObject` script content, `iframe`, all `on*` handlers, and `javascript:` hrefs. Applied to every SVG before inline injection (the interactive viewer / any `dangerouslySetInnerHTML` SVG). Bytes served by the `<img>`-route are *not* sanitized — an SVG referenced via `<img src>` is opaque to the page and not a script-execution vector.
5. **Pan/zoom** — a hand-rolled `usePanZoom` hook (≈ 80 LOC, CSS-transform on a wrapper div: wheel = zoom-at-cursor, pointer-drag = pan, button + `0` key = fit-to-viewport), reused by `DiagramViewer` and `DecisionGraph`. No `svg-pan-zoom` / `@panzoom/panzoom` dep.
6. **Source markdown / templates** — the `<img>` / `![]()` paths in DESIGN.md / architecture.md are correct for GitHub and stay unchanged; `ARCHITECTURE_TEMPLATE.md` / `ARCHITECTURE_GUIDE_TEMPLATE.md` need no change. Only `diagram-conventions.md` gets a one-line clarifying note: the `<img>` embedding rule applies to committed Markdown/HTML; the dashboard server may rewrite those refs to its own route or render SVGs inline (sanitized) for interactive surfaces, provided the source path keeps the `diagrams/<name>/rendered/<name>.svg` convention.

## Considered Options

### A — Route handler only, no markdown rewrite

Pros: smallest. Cons: doesn't fix it — the browser still can't resolve `../docs/diagrams/...` from `/architecture`. Rejected.

### B — Server-side markdown→inline-SVG transform

Pros: no new HTTP surface. Cons: a full markdown preprocessor that loads and inlines every referenced SVG into the body; large bodies; the inlined SVGs would all need sanitization even when only displayed (not just when interactive); more code than route + regex. Rejected.

### C — View-model-level SVG embedding

Pros: predictable. Cons: same as B — everything inlined, everything sanitized, big bodies. Rejected.

### D — Route handler + markdown image-ref rewrite + inline only for the interactive viewer (chosen)

Pros: markdown bodies render with visible diagrams via a single `<img>` GET each; the existing path allowlist is the only security gate; `<img>`-served SVGs stay opaque (no sanitization needed); only the interactive viewer inline-injects, so sanitization is a small contained surface; pan/zoom is hand-rolled and reused. Cons: one new HTTP route; a regex rewrite that must handle the embed variants. Accepted.

### Sanitizer sub-decision

`sanitize-html` (server-side, MIT, widely used, maintained) over client-side DOMPurify (adds a client dep, runs every render) over "restrict to known-safe project paths" (impossible — the hard constraint is genericity across arbitrary projects; a project's `diagrams/` cannot be assumed trustworthy).

### Pan/zoom sub-decision

Hand-rolled `usePanZoom` (≈ 80 LOC, zero dep, reused twice) over `svg-pan-zoom` (~15 KB, unmaintained-ish) over `@panzoom/panzoom` (~3 KB, still a dep for ~80 lines).

## Consequences

**Positive:** Embedded diagrams become visible; the explicit-diagrams section finds all rendered SVGs (both roots); inline-injected SVGs cannot execute script even when sourced from an arbitrary project; one new dep (`sanitize-html`) that is genuinely the security boundary; pan/zoom adds no dep and is reused by the ADR graph; the source markdown stays GitHub-correct; the architecture templates are untouched.

**Negative:** One new HTTP route to maintain; the rewrite is regex-based (tested against Praxion's own DESIGN.md / architecture.md patterns); ~80 LOC of pointer math we own (touch pinch-zoom is implemented but under-tested without touch hardware — documented as a known v1 limitation; wheel-zoom covers the common case).

**Risks accepted:** `sanitize-html`'s default SVG handling might be too aggressive (strip legitimate gradients/markers) — mitigated by building the allowlist from a real rendered LikeC4 SVG and a snapshot test that round-trips it. A malformed SVG might survive sanitization and render oddly — but it can't execute script, which is the threat; localhost binding is the outer layer.
