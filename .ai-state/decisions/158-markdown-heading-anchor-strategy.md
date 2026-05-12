---
id: dec-158
title: Markdown heading anchoring via rehype AST plugins (no rehype-raw), with a shared slugify/extractToc util
status: accepted
category: architectural
date: 2026-05-12
summary: Add rehype-slug + rehype-autolink-headings to react-markdown for slugged headings and section-link affordances, preserving the no-rehype-raw posture; consolidate slugify/extractToc into one shared util.
tags: [dashboard, markdown, react-markdown, accessibility, progressive-disclosure, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/components/markdown-surface.tsx
  - dashboard_app/src/lib/markdown-headings.ts
  - dashboard_app/src/components/markdown-toc.tsx
  - dashboard_app/src/components/shells/reference.tsx
---

## Context

`MarkdownSurface` renders project Markdown via `react-markdown` + `remark-gfm`, deliberately **without `rehype-raw`** (security posture: no raw-HTML re-parse — `prepareMarkdownBody` instead strips HTML comments and normalizes stray `<img>` to MD image syntax). Rendered headings currently carry **no `id` attributes**, so cross-linking into a section, an in-page table of contents, and shareable section URLs are all impossible. The `ReferenceShell` has its own `slugify` + `extractToc` for its sidebar ToC — meaning the ToC `href`s and the (absent) heading `id`s would drift if both existed. The dashboard's progressive-disclosure model (Overview → Surface → Artifact → Section anchor) and the `html-output-conventions.md` rule ("hides dense content behind anchored links to MD sections") both require working heading anchors.

## Decision

Add `rehype-slug` and `rehype-autolink-headings` to `react-markdown`'s `rehypePlugins` in `MarkdownSurface`. These are **pure HAST (HTML AST) transforms** — they run on the tree react-markdown has already parsed from Markdown; they do **not** re-introduce a raw-HTML parse step (that is `rehype-raw`, which stays out). The no-raw-HTML security posture is fully preserved. Configuration: `rehype-slug` adds `id="kebab-slug"` to every `h1`–`h6`; `rehype-autolink-headings` with `behavior: "append"`, a small `§` icon as `content`, and `properties: { className: "heading-anchor", ariaLabel: "Link to this section" }` appends a focusable anchor that is visually hidden until the heading is hovered or focused. `prepareMarkdownBody` (comment strip + `<img>` normalize) is unchanged and still runs first.

Extract a shared `dashboard_app/src/lib/markdown-headings.ts` exporting `slugify(text)` and `extractToc(body)`; `MarkdownSurface` (indirectly, via the slug algorithm `rehype-slug` uses — configure `rehype-slug` with the same slugger or accept GitHub-style slugs and align `extractToc` to match) and `ReferenceShell` and a new `<MarkdownToc body>` component all consume it, so heading `id`s and ToC `href`s cannot diverge. The `ReferenceShell`'s private `slugify`/`extractToc` are deleted in favor of the shared util.

Fallback (if the architect rejects the two new deps): a custom `components={{ h1, h2, h3 }}` override in `MarkdownSurface` that slugs the child text with the shared `slugify` and renders `<hN id={slug}>{children}<a className="heading-anchor" href={'#'+slug} aria-label="Link to this section">§</a></hN>`. ~20 lines, zero deps, slightly more brittle on heading text containing inline code or links. The design (ToC, cross-links, shareable URLs) works either way.

## Considered Options

### A — Add rehype-raw and author HTML anchors in the MD

Pros: total control. Cons: re-introduces the raw-HTML parse the project deliberately excluded; security regression; and it would mean authoring anchor markup into MD source, violating the MD-is-source-of-truth-but-not-presentation boundary.

### B (chosen) — rehype-slug + rehype-autolink-headings (AST transforms)

Pros: preserves the no-raw-HTML posture (AST transforms ≠ raw-HTML parse); two small, widely-used, well-maintained deps; headings get IDs server-side so anchors work before hydration; consolidates the duplicated `slugify`. Cons: two new deps (a few KB); a behavior the architect should ratify since it touches the no-`rehype-raw` area.

### C — Custom `components` h1–h3 override, zero deps

Pros: no new deps; full control; works server-side. Cons: ~20 lines of bespoke code to maintain; more brittle on headings with inline code/links; still needs the shared `slugify`. (This is the fallback.)

## Consequences

Positive: heading anchors enable the in-page ToC (used as the "Component index" on the Architecture page, and on Roadmap / long Documentation surfaces), the "link to this section" affordance, hash-scroll with a highlight flash, shareable `…#slug` URLs, and the cross-reference hover-cards (ADR id / file path / component name) — the core progressive-disclosure interactions. The `ReferenceShell` `slugify` duplication is eliminated.

Negative: two new deps (or ~20 lines of bespoke code under the fallback); the no-`rehype-raw` posture's wording should be updated to clarify "no raw-HTML re-parse — AST transform plugins are fine" so a future reader doesn't think the posture was relaxed.
