# Visual Design Fundamentals (Web)

Web-specific deepening of visual hierarchy, typography, color, and layout. The cross-cutting design canon (Rams, Norman, Nielsen, Tufte, Bloch) lives in [`design-fundamentals.md`](design-fundamentals.md). This file covers web-specific application.

---

## Visual Hierarchy

**The importance signal stack** — in order of strength:

1. **Size** — larger elements claim more attention. Use deliberately. Every size change signals a change in importance.
2. **Weight** — bold text is read before regular text at the same size. Use weight to establish hierarchy within a single type size.
3. **Color** — higher contrast = higher importance. Muted text recedes; full-contrast text leads. Use color to differentiate, not decorate.
4. **Position** — top-left is where the eye begins in LTR layouts. Above the fold, left column, the start of a list.
5. **Contrast** — the ratio between foreground and background. A 7:1 ratio demands attention; a 2:1 ratio recedes.

**The principle**: the most important element must be unambiguously the first thing the eye encounters. If you must ask "is this element more or less important than that one?" — the hierarchy is broken.

**Grayscale-first design**: design in grayscale before adding color. If the hierarchy is broken in grayscale, color cannot save it. Color should enhance a working hierarchy, not substitute for a missing one.

---

## CARP Principles

Four principles that govern every compositional decision:

**Contrast** — make different things look different; make same things look the same.
- Too much sameness creates visual noise — everything competes at equal weight.
- Too much contrast creates fragmentation — the eye cannot find a resting point.
- The calibrated middle: a few things with high contrast (primary actions, headings) against a field of low contrast (body text, secondary elements).

**Alignment** — nothing should be placed arbitrarily. Every element should align with something.
- Use a grid. Every column, every row, every inset should trace back to a grid line.
- Misalignment at the micro level (a label 1px off-grid) is visible to the eye even when unnoticed consciously — it reads as "careless."
- Left alignment is the default for LTR reading; center alignment only for headings and standalone elements; right alignment for numbers in tables.

**Repetition** — repeat visual styles to create coherence and guide the eye.
- Every time a style appears, it signals "this element has the same role as those other elements."
- Breaking repetition signals "this element is different." Use it intentionally (the one red button in a sea of gray buttons signals danger).
- A design system is formalized repetition.

**Proximity** — group related items close together; separate unrelated items.
- Items with no spatial relationship look unrelated. Items that are spatially close look related.
- Form groups, card clusters, navigation sections, setting panels — all use proximity to communicate structure.
- White space is not empty; it is a separator. Generous white space between unrelated items is as communicative as close proximity between related items.

---

## Typography in Depth

Typography is the primary tool of web visual design — most web UI is text.

### Type Scale Construction

A modular scale (ratio multiplied repeatedly) creates harmonious size relationships:

| Step | Size | Use |
|------|------|-----|
| `xs` | 12px | Captions, metadata, secondary labels |
| `sm` | 14px | Secondary body text, table cells, UI labels |
| `base` | 16px | **Primary body text** (minimum for readable prose) |
| `lg` | 18px | Large body, lead paragraph |
| `xl` | 20px | H4, small heading |
| `2xl` | 24px | H3, card heading |
| `3xl` | 30px | H2 |
| `4xl` | 36px | H1 |
| `5xl` | 48px | Display, hero heading |

Use a ratio of 1.25 (Major Third) or 1.333 (Perfect Fourth) to derive the scale. The exact values matter less than consistency — use the scale, not ad-hoc sizes.

### Readable Measure

Line length (measure) for comfortable reading: **45–75 characters per line**.
- Below 45 chars: eye movement too frequent, reading rhythm disrupts.
- Above 75 chars: eye must travel far to find the next line start, causing reading errors.
- A `max-width: 65ch` on body text containers is a reasonable default.

### Line Height

| Context | Line Height |
|---------|------------|
| Body text | 1.5–1.6× font size |
| Heading | 1.1–1.3× font size |
| UI labels (short lines) | 1.2–1.4× font size |

Never use `line-height: 1` for body text — it creates illegible cramped text.

### Optical Alignment

- Numbers in tables: **right-align** for easy scanning of magnitude (units stack vertically).
- Text in tables: **left-align** for natural reading.
- Hanging punctuation: pull opening quotes and list bullets into the margin for true left-alignment of the text baseline.
- Optical kerning: rely on the browser's kerning for body text; check display headings manually for awkward pairs (AV, To, etc.).

### Font Weight for Hierarchy

Use at least three weights:
- **Regular (400)**: body text, secondary UI text
- **Medium (500)**: emphasis within body, table headers, form labels
- **Semibold/Bold (600–700)**: headings, primary action labels, strong emphasis

Never fake bold with CSS `font-weight: 900` on a font that doesn't have the weight variant — it degrades readability.

### The Right Typeface

**Inter** (Rasmus Andersson): designed specifically for screen legibility at small sizes. Open source, variable font (one file, all weights). The de-facto standard for developer tools and SaaS. Default choice unless the project has a strong existing typographic identity.

Font stacks: `Inter, system-ui, -apple-system, sans-serif` for body; `JetBrains Mono, SFMono, Menlo, Consolas, monospace` for code.

---

## Color Systems

### The 5-Shade Palette

For any color in a UI (brand color, danger, warning, success, info), create 5 shades from near-white to near-dark. Use the full range:

| Shade | Use |
|-------|-----|
| **50** (near-white) | Backgrounds, hover states, light surfaces |
| **100** | Light backgrounds, selected states |
| **300** | Borders, dividers, decorative elements |
| **600** | Primary text, icons, interactive elements |
| **900** (near-dark) | Strong emphasis, dark backgrounds |

**Semantic token layer** on top of the palette:

```
--color-danger: var(--red-600);
--color-danger-surface: var(--red-50);
--color-danger-border: var(--red-300);
```

This two-layer approach allows switching the palette (brand rebrand, dark mode) without touching every component.

### Grayscale First

Design the UI in grayscale. If the hierarchy, readability, and information structure work without color:
- Color will enhance the design
- The design is accessible to color-blind users
- Color is doing purposeful work, not compensating for structural weaknesses

If the design breaks without color — fix the structure, not the color.

### Dark Mode Token Swap

Dark mode is not "invert the colors." It requires a designed token swap:

| Light | Dark |
|-------|------|
| White background | Near-black background (not pure `#000`) |
| Near-black text | Near-white text |
| Brand color (stay the same or shift slightly lighter) | |
| Shadows become less visible — use borders instead | |

Implement via `@media (prefers-color-scheme: dark)` that redefines the token values. Do not maintain two CSS files — maintain one token file with both contexts.

### Shadow Discipline

All shadows on a page must be consistent with **a single light source overhead**. Shadow is elevation — elements closer to the user cast larger, blurred shadows; elements further back cast smaller, sharper shadows.

```
--shadow-1: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08);  /* barely lifted */
--shadow-2: 0 4px 6px rgba(0,0,0,0.1), 0 2px 4px rgba(0,0,0,0.06);   /* card elevation */
--shadow-3: 0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05); /* dropdown */
--shadow-4: 0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04); /* modal */
```

---

## Layout Systems

### The 4px Grid

All spacing must be multiples of 4: `4, 8, 12, 16, 24, 32, 40, 48, 64, 96px`. Never use `13px`, `22px`, or other ad-hoc values for spacing between elements.

The 4px grid aligns with sub-pixel rendering on retina displays and creates visual harmony across all screen sizes.

### The 8px Major Rhythm

Inter-section spacing should be multiples of 8: `8, 16, 24, 32, 48, 64px`. The body font size (16px = 2×8) anchors the system.

### Common Layout Patterns

| Pattern | When to Use |
|---------|------------|
| **Sidebar + main** (fixed or collapsing) | Application UIs with persistent navigation; the Praxion dashboard shape |
| **Two-column** (content + detail panel) | Master-detail: list on left, selected item detail on right |
| **Full-width single column** | Long-form reading content; landing pages |
| **Card grid** | Browsable collections with visual differentiation |
| **Data table** | Dense structured data; sortable and filterable |

### Responsive Layout Principles

1. **Mobile-first**: define the base layout at small breakpoints, then progressively enhance.
2. **Avoid fixed pixel widths** for layout containers; use relative units (`%`, `ch`, `vw`) with `max-width` constraints.
3. **Breakpoints around content**, not around device sizes — the layout breaks when it breaks, not at 768px exactly.
4. **Grid and Flexbox**: Flexbox for component-level layout (nav items, button groups); CSS Grid for page-level layout (sidebar + main, card grids).

---

## Praxion Dashboard Observations

Current state of `dashboard_app/`:

**Token layer:** Design tokens live in `tokens.css` (imported by `globals.css`, which is now a ~16-line `@import` manifest across 6 cascade layers). The token layer is complete:
- Typography scale (`--font-size-sm` through `--font-size-5xl`), 4px-grid spacing scale (`--space-1` through `--space-16`)
- Border-radius scale (`--radius-sm`, `--radius-md`, `--radius-full`), z-index scale (`--z-dropdown`, `--z-modal`, `--z-toast`)
- Motion tokens (`--duration-micro`, `--duration-enter`, `--ease-out`)
- Semantic + sentinel-grade color tokens (`--accent`, `--danger`, `--good`, `--warning`, `--info`, `--muted`)
- Dark-mode swap via `@media (prefers-color-scheme: dark)`

**What works well:**
- Semantic HTML (`<aside>`, `<nav>`, `aria-label`)
- Three-font-stack (display/sans/mono)
- Sidebar+main layout

**Remaining opportunities:**
- No skeleton loading states for data surfaces
- No skip-to-content link (keyboard accessibility gap)
