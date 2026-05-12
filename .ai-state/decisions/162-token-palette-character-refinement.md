---
id: dec-162
title: Token palette character refinement — warmer-neutral base with identity anchors
status: re-affirmation
category: implementation
date: 2026-05-12
summary: User steer after architecture stage refines the visual-language ADR — use the designer's token structure but lean warmer (reduce clinical feel), retain the ◆ glyph and 2px active-nav left-bar as identity anchors, progressive disclosure as the coherence spine.
tags: [dashboard, design-tokens, visual-design, web-ui, palette]
made_by: agent
agent_type: implementation-planner
branch: main
pipeline_tier: standard
affected_files:
  - dashboard_app/src/app/globals.css
re_affirms: dec-157
---

## Context

After the interface-designer (`dec-157`) and the systems-architect both ratified the "cool-neutral professional console" direction, the user introduced a refinement steer during the implementation-planning stage: *"fully neutral sans-serif as you said, but with character. get inspired by minimalistic-effective designs that reduce the cognitive load of the user but allow him to dig deep if he wants to in a very cohesive, integrated and coherent way, showing all the details progressively as he decides to navigate further."*

The original `dec-157` palette reads correctly as "professional operations console" but leans toward the clinical end of the neutral spectrum. The user wants the same calm and density, but with a distinctive quality — the feeling of a coherent instrument, not a generic admin panel.

## Decision

The designer's token *structure* (§3.1 tables, shade scale, alias block, semantic set) is used as-is. The palette *values* are adjusted during implementation to:

1. Lean the neutral surface scale slightly warmer than pure cool-slate (`#f8fafc` as a floor, not a ceiling — a neutral with a subtle warm undertone that avoids the clinical reading while still being professional).
2. Treat the `#4338ca` indigo accent as the identity anchor — do not swap it for a warmer accent; the contrast between a warm-neutral surface and a cool indigo interactive affordance is the character source.
3. Retain two explicit identity anchors: the `◆` brand glyph (sidebar brand line) and the 2px active-nav left-accent bar. These are the signature micro-treatments that make the dashboard feel like one coherent instrument across all 8 surfaces.
4. Use elevation (shadow/depth tokens) only where it builds the hierarchy that enables progressive disclosure — cards barely lift; modal/popover lift clearly. Shadow is not decoration.
5. The throughline: every screen is calm and scannable at a glance; every detail is one consistent gesture away (expand, hover, anchor-link, navigate).

The `dec-157` ADR is not superseded — the structural decisions (system-sans, flat surfaces, no glassmorphism, semantic-color discipline, backward-compat aliases, dark-mode structure) all stand. This is a palette-character refinement applied during Step 1's implementation.

## Considered Options

### A — Use the designer's exact `#f8fafc` values unchanged

Pros: precisely as specified, no deviation. Cons: the user explicitly flagged the "clinical" reading and asked for more character. Not responsive to the steer.

### B (chosen) — Lean the base warmer while keeping the cool accent + identity anchors

Pros: responsive to the user steer; preserves the professional console feel; the cool-warm contrast (warm surface / cool accent) is a proven character technique (Stripe, Linear). Cons: the implementer has a degree of palette judgment that must align with the "with character" steer — the variance band is narrow (not warm-beige, not coffee-brown, just "not clinical cool").

### C — Add a second, warmer accent color for identity

Pros: more distinctive. Cons: two accent colors are two competing visual identities; the `◆` glyph and the left-bar are the right identity vehicle — not a second accent. Rejected: adds complexity without focus.

## Consequences

Positive: a dashboard that reads "coherent instrument" rather than "generic admin panel"; the user's progressive-disclosure mental model is expressed through the visual language itself (calm surface → slightly elevated card → clearly elevated modal); dark mode remains a token-flip.

Negative: the implementer carries a non-trivial palette judgment call. Mitigated by: the direction is specific ("warmer undertone, not beige; cool accent stays; ◆ glyph + left-bar are the signature micro-treatments"); the verifier reviews the result against WCAG-AA constraints and the "with character" steer.

## Prior Decision

`dec-157` (visual-language shift) is re-affirmed by this ADR. The structural decisions stand; only the palette-character tuning is added. See `re_affirms` frontmatter.
