---
id: dec-157
title: Shift the dashboard visual language from literary/glassmorphic to professional operations-console
status: accepted
category: architectural
date: 2026-05-12
summary: Replace the parchment/serif/glassmorphic aesthetic with a cool-neutral, system-sans, flat-surface console design system on an 8px grid, with dark-mode token structure.
tags: [dashboard, design-system, design-tokens, visual-design, accessibility, web-ui]
made_by: agent
agent_type: interface-designer
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/app/globals.css
  - dashboard_app/src/app/layout.tsx
  - dashboard_app/src/components/sidebar-nav.tsx
re_affirmed_by:
  - dec-162
---

## Context

The current dashboard aesthetic is distinctive but reads "literary essay", not "professional status instrument": a warm parchment radial-gradient `html` background, `backdrop-filter: blur(24px)` glassmorphism on every card, serif-display headings (Iowan Old Style) — including on numeric KPI values — `border-radius: 1.5rem` cards, and a dramatic warm drop-shadow (`0 24px 60px rgba(41,25,7,0.08)`). The CSS-custom-property token layer is partial: typography/spacing/radii scales exist, but there is no real color shade scale (components reach for ad-hoc `rgba(255,255,255,0.55)`), no z-index scale, only two shadow values, no `prefers-color-scheme` dark swap, and several borderline-AA color pairings (e.g. `--status-proposed: #c9aa1a` ≈ 2.6:1 on white — a fail). The directive is a "big jump in UI/UX quality" toward a practical, low-cognitive-load console.

## Decision

Adopt a professional operations-console design language, expressed entirely through the CSS-custom-property token layer (no styling-framework swap):

- **Color**: a cool-neutral slate shade scale (`--color-bg` near-white flat, `--color-surface-1..3`, hairline `--color-border` + `--color-border-strong` for 3:1 UI-element contrast); a single restrained indigo accent (`--color-accent`, used only for interactive affordances and the active-nav state); a full semantic set (success/warn/danger/info, each with `-text` AA-on-white, `-subtle` tinted surface, `-border`) reserved strictly for status meaning, never decoration; sentinel A/B/C/D grades map onto the semantic set (one mapping, no separate `--grade-*` tokens). Every text pairing ≥ 4.5:1, every UI-element pairing ≥ 3:1, WCAG 2.2 AA. Backward-compat aliases keep existing class names working.
- **Typography**: drop the serif-display stack entirely (`--font-display` aliases to `--font-sans`); a system-sans stack; a tight ~1.20 modular scale snapped to nice px (11/12/14/15/17/20/24/32/40); KPI values in sans-bold (a number must be unambiguous); the all-caps "eyebrow" treatment reduced to at most one micro-label per page.
- **Surfaces/elevation**: flat surfaces with hairline borders (no glassmorphism, no `backdrop-filter`); shadow = elevation (`--shadow-card` barely lifts; `--shadow-popover` / `--shadow-modal` lift clearly); no warm drama.
- **Spacing**: the 4px grid (drop the off-grid `--space-7: 28px`; add `--space-10/12/16`); card padding 20px, inter-card gap 16px, inter-section gap 32px — ~30% tighter than today.
- **Radii**: `--radius-xs/sm/md/lg/full` (4/6/8/12/9999) — `--radius-lg: 12px` is the largest in the system (was 24px).
- **Motion**: `--duration-micro/enter/exit` + `--ease-out/in`, all consumed inside `@media (prefers-reduced-motion: no-preference)`.
- **Z-index**: a named-layer scale (`--z-sticky/drawer/popover/modal/toast`) replacing ad-hoc `z-index: 10`.
- **Dark mode**: a `@media (prefers-color-scheme: dark)` `:root` block ships in the first cut with an AA-meeting dark palette; the bulk of the work is auditing the ~30 hardcoded colors out of components and into tokens so dark mode is a token-flip later, not a component sweep.

> **User amendment (2026-05-12, applied during pipeline `dashboard-ux-overhaul` Step 1; formal re-affirmation recorded as `dec-162`):** the designer's exact token *values* (`#f8fafc` bg / `#4338ca` accent) are a *starting point*, not the final spec. Three refinements to the palette tuning, leaving every structural decision above untouched: (1) the neutral *surface* scale is nudged a near-imperceptible hair warmer than pure cool-slate — a warm-gray undertone on `--color-bg`/`--color-surface-2/3`/`--color-border` (e.g. `#f8f7f5` / `#f1f0ec` / `#e5e2dc`) so the UI reads "considered" rather than "clinical"; `--color-surface-1` stays pure `#ffffff` so cards lift cleanly; the `--color-text` family stays on the slate scale (temperature is invisible at near-black/near-white). (2) the cool indigo accent (`#4338ca`) is **retained as the identity anchor** — not swapped for a warm accent; the subtle temperature contrast (faintly-warm neutral surface ↔ cool indigo affordance) *is* the character. (3) Two explicit identity anchors are preserved: the `◆` brand glyph (sidebar brand line) and the active-nav micro-treatment — a `2px` left accent bar (`--color-accent`) over a `--color-accent-subtle` background, with no transform/glow. WCAG 2.2 AA still holds for every pairing on its intended surface; the contrast-ratio annotations live as CSS comments in `globals.css`. The dark palette gets the same faint-warmth-on-surfaces, cool-accent treatment.

## Considered Options

### A — Re-skin in place (tweak the existing tokens; keep serif headings, soften the glass)

Pros: smallest effort. Cons: does not deliver the "big jump"; the serif-on-KPI-values legibility problem persists; the partial token layer (no color scale, no dark structure) stays partial; AA fails (`--status-proposed`) stay.

### B — Migrate to Tailwind + shadcn/Radix

Pros: a mature design-token + component system out of the box. Cons: this is a rewrite, not an overhaul — ~30 components and one CSS file replaced; large blast radius; not what "overhaul" was asked for. (Registered as an Architecture Challenge recommending *against*.)

### C (chosen) — Evolve the CSS-custom-property token layer to a complete professional-console system

Pros: the existing token mechanism is sound and stays; backward-compat aliases mean component classes keep working during the transition; delivers the visual jump; completes the token layer (color scale, z-index, motion, dark structure); fixes the AA fails. Cons: a full pass over `globals.css` and a de-hardcode sweep across components.

## Consequences

Positive: a calm, dense, professional console aesthetic; a complete, consistent token layer; WCAG 2.2 AA across the board; dark mode becomes a token-flip; components stop inventing ad-hoc colors. The token mechanism — and the renderer-registry / server-component architecture — is unchanged, so the change is contained to styling + chrome markup.

Negative: every block in `globals.css` is restyled; ~30 components have hardcoded colors swapped for tokens; the serif aesthetic (which some may have liked) is gone — a deliberate taste call (Rams: a status instrument is not the place for a literary typeface).
