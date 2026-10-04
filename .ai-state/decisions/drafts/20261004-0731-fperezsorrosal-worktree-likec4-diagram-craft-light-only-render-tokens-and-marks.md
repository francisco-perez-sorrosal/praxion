---
id: dec-draft-026e4301
title: Light-only C4 render tokens with one non-colour mark per category
status: proposed
category: configuration
date: 2026-10-04
summary: "Committed architecture renders use a tint-fill/strong-stroke/slate-text token set on an opaque white canvas, a unique non-colour mark per category and form, a single vendored Person glyph, an in-image title block and Legend container, and no dark-mode CSS in this change"
tags: [diagrams, design-tokens, accessibility, wcag, colour-blind, c4, d2]
made_by: agent
agent_type: interface-designer
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - docs/diagrams/architecture/src/architecture.c4
  - rules/writing/diagram-conventions.md
  - dashboard_app/src/server/diagrams/sanitize.ts
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-12]
---

## Context

Today every element in every render is the same blue rectangle. There is no legend, title, technology or responsibility in the image, and five of seven renders fall below legible size at the 960 px reference width.

- **LikeC4's built-in theme fails on light pages:** text on its theme fills measures 3.38–4.55:1, and its edge labels `#C9C9C9` reach 1.66:1 on white.
- **Dark mode via D2 is broken:** `--dark-theme` swaps only theme-code colours, not custom hex fills.
- **The acceptance driver flattens CSS:** it unwraps `@media` blocks and keys class rules on the last compound selector, so any dark-mode CSS would be measured as the render's colours.

## Decision

- **Token set.** Each category gets a tint fill, a strong category stroke and slate text `#0F172A`. The only solid fill is the System in scope box (indigo `#4338CA`, white text). Canvas is opaque `#FFFFFF`; edges `#475569`; edge labels `#334155`; dynamic steps `#4338CA` 2.5 px. Every text is ≥ 7.9:1 against its surface and every outline ≥ 3.56:1 against the canvas. Hue families are Okabe-Ito, and every category pair below CIEDE2000 ΔE 7 under Machado-2009 simulation differs in shape.
- **Marks.** Each (category, form) has a unique non-colour mark, uniform across views:
  - boxes: person = square + glyph; system = square, stroke 3; external = dashed; knowledge = package; agent = rounded r16; document = document; store = cylinder; tooling = 3d; layer = double-border;
  - frames: system = solid; layer = dashed square; runtime agent = dashed rounded;
  - the onboarded floor adds container = rounded r8 and component = double-border.
- **Icons:** only the Person glyph, vendored and embedded as a data URI. Product identity goes in the category line as text.
- **Typography:** element labels are 15 px (14 px floor); the title block is one line `<view title> — <C4 type> diagram` at 24 px bold, `near: top-center`.
- **Legend:** a D2 container labelled exactly `Legend` at `near: bottom-center`, holding one sample per (category, form) drawn and one arrow sample per line meaning.
- **No dark-mode CSS** in this change. The dark token values are reserved.

## Considered Options

### Option 1: Light-only token set on an opaque canvas (chosen)
- **Pros:** AA everywhere, by computation; byte-stable; readable by the bound acceptance driver; no dashboard change.
- **Cons:** dark dashboards and GitHub dark show a white card.

### Option 2: One SVG with a class-keyed dark CSS layer
- **Pros:** themed in both modes.
- **Cons:** the acceptance driver applies `@media` rules unconditionally, so REQ-08 and REQ-01 would be judged on dark or mixed values; S6 does not require it.

### Option 3: LikeC4 theme colours and Structurizr's blue ramp
- **Pros:** familiar.
- **Cons:** 7 of 8 LikeC4 theme fills, and three Structurizr roles with white text, fail 4.5:1.

### Option 4: Per-element identity icons
- **Pros:** recognisable logos.
- **Cons:** a category then draws several ways, which fails REQ-01's cross-view consistency; CDN icons break offline determinism.

## Consequences

- **Positive:** categories are distinguishable in greyscale and under colour-vision deficiency, with consistent marks across views and in onboarded projects.
- **Negative:** no dark theme, and a single type size per stock-D2 label (no bold name line without post-processing).
- **Category:** `configuration`. It sets values and formats inside the render; no component is added, removed or re-bounded.
