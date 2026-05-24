---
name: web-ui-design
description: >
  Web UI design craft for React, Next.js, and component-based UIs. Visual
  hierarchy (Laws of UX),
  design canon (Rams/Norman/Nielsen/Tufte/Refactoring UI/Linear/Stripe/Vercel),
  design tokens, 4px/8px grid, typography, WCAG 2.2 AA accessibility, component
  taste, motion timing, RAIL perceived performance, Radix/shadcn
  accessible-primitives. Triggers: designing/reviewing web UI, design systems,
  tokens, component ergonomics, UI framework selection, auditing React/Next.js
  quality and accessibility. Not for CLI/terminal (tui-design) or API/tools
  (api-design-craft, agentic-interface-design).
staleness_sensitive_sections:
  - "WCAG 2.2 AA — The Numbers"
  - "RAIL Model"
---

# Web UI Design

Web UI design is the craft of the boundary between a system and its human consumer through a graphical interface. The measure of quality is not visual novelty but whether the interface disappears — whether the user accomplishes their task without friction, confusion, or accessibility barrier.

The durable cross-cutting fundamentals (Rams, Norman, Nielsen, Tufte, Bloch, Zhuo, perception thresholds, the full canon with one lesson each) live in [`references/design-fundamentals.md`](references/design-fundamentals.md). Load it when you need the canon depth. This SKILL.md body carries the web-specific application.

**Separation of contexts**: this skill covers web UI only. For terminal/CLI output design, use the `tui-design` skill. For API and agent-tool design, use `api-design-craft` or `agentic-interface-design`.

---

## Laws of UX + Visual Hierarchy (Web)

| Law | Web Application |
|-----|----------------|
| **Fitts's Law** | Primary CTAs large and positioned where the cursor naturally rests (center/bottom, not top-corner). Touch targets ≥24px (AA) / 44px (AAA). Float action buttons at bottom-center for mobile. |
| **Hick's Law** | Navigation ≤7 top-level items. Progressive disclosure for secondary actions. Command palette for power users (Cmd+K pattern). Avoid mega-menus. |
| **Miller's Law** | Paginate lists. Chunk forms into groups ≤7 fields. Use tabs only when all options are always relevant (not for long lists of items). |

**Visual hierarchy signals** — in order of strength: size → weight → color → position → contrast. Use all five; never rely on color alone (8% of men are color-blind). The most important element must be unambiguously the first thing the eye sees.

**CARP principles** (Contrast, Alignment, Repetition, Proximity):
- Contrast makes different things look different; makes same things look same
- Alignment: nothing arbitrary; every element aligns with something
- Repetition: repeated visual styles create coherence and guide the eye
- Proximity: group related items close; separate unrelated items

---

## Design Tokens

A design token system is a prerequisite for consistent, maintainable UI. Without tokens, every style decision becomes ad-hoc and maintenance becomes impossible at scale.

### Token Categories

| Category | Examples | CSS Variable Pattern |
|----------|---------|---------------------|
| **Color** | Brand, semantic (danger/warning/success/info/muted), surface, text | `--color-danger`, `--color-surface-1` |
| **Spacing** | 4px grid scale | `--space-1: 4px`, `--space-2: 8px`, `--space-3: 12px`, `--space-4: 16px`, `--space-6: 24px`, `--space-8: 32px`, `--space-12: 48px`, `--space-16: 64px` |
| **Typography** | Size scale, line height, weight | `--font-size-sm: 14px`, `--font-size-base: 16px`, `--font-size-lg: 18px`, `--line-height-body: 1.5` |
| **Shadow** | Elevation levels 1–4 | `--shadow-1: 0 1px 3px rgba(0,0,0,0.1)` |
| **Border Radius** | None / subtle / medium / full | `--radius-sm: 4px`, `--radius-md: 8px`, `--radius-full: 9999px` |
| **Motion** | Duration, easing curves | `--duration-micro: 150ms`, `--duration-enter: 250ms`, `--ease-out: cubic-bezier(0.0,0,0.2,1)` |
| **Z-index** | Named layers | `--z-dropdown: 100`, `--z-modal: 300`, `--z-toast: 400` |

### The 4px Grid

Use 4px as the atomic spacing unit. All spacing values must be multiples of 4. The 8px major rhythm (inter-section spacing) aligns with 16px base font size (16 = 2 × 8). Never use ad-hoc values like 13px or 22px for spacing.

**Praxion dashboard observation**: Design tokens live in `tokens.css` (one of 6 cascade-layer files that `globals.css` now `@import`s). The token layer is complete — typography scale, 4px-grid spacing scale, radii scale, z-index scale, motion tokens, semantic + sentinel-grade color tokens, and dark-mode swap via `@media (prefers-color-scheme: dark)`. `globals.css` is a ~16-line `@import` manifest; `tokens.css` is the single source of truth for all custom-property values.

---

## WCAG 2.2 AA — The Numbers
<!-- last-verified: 2026-05-12 -->

The current standard (released October 2023):

| Criterion | AA Requirement | Notes |
|-----------|---------------|-------|
| **Text contrast** | **4.5:1** minimum | Body text, UI labels |
| **Large text contrast** | **3:1** minimum | ≥18px regular or ≥14px bold |
| **Non-text UI contrast** | **3:1** minimum | Icons, input borders, focus indicators, chart elements |
| **Focus indicator** | **≥2px perimeter, 3:1** focused vs unfocused | New in WCAG 2.2. Outline offset outward |
| **Touch targets** | **24×24 CSS px** (AA), 44×44 (AAA) | Interactive elements |
| **Keyboard navigation** | All interactive elements reachable via Tab | Tab order must match visual order |

**Never use color alone** to convey meaning — pair with shape, label, pattern, or text.

**`prefers-reduced-motion`**: wrap all CSS transitions/animations in `@media (prefers-reduced-motion: no-preference)`. Users with vestibular disorders have opted out of motion.

**`prefers-color-scheme`**: dark mode is an accessibility requirement for many users, not just an aesthetic option. Design the dark-mode token swap from the beginning; retrofitting it is expensive.

---

## Component Taste

Specific guidance on when to use which pattern. The question is always "what does the user need to accomplish?" — not "which component is most modern?"

### Modal vs Drawer vs Inline

| Pattern | Use When | Never Use When |
|---------|----------|---------------|
| **Modal dialog** | Destructive confirmation; critical decision that requires pausing all other context; the user must decide before proceeding | Form that requires scrolling; form the user will open/close repeatedly; anything non-critical |
| **Drawer / panel** | Contextual editing alongside the main view; detail view that coexists with the parent; filter/settings panel | The user needs to see main content + edit simultaneously (use split view instead) |
| **Inline** | Validation, editing, filter chips, accordion content — whenever the user can stay in their current context | Never refuse inline when inline is possible |
| **Toast notification** | Transient success or info (auto-dismiss 4–6s) | Errors that require action (use inline or persistent banner instead) |

The default should be inline. Reach for drawer before modal. Reach for modal only when the interruption is justified.

### Table vs Card vs List

| Pattern | Use When | Avoid When |
|---------|----------|-----------|
| **Table** | Comparing attributes across rows; sorting columns; dense structured data where column-scanning matters | Mobile-first with many columns; unstructured or heterogeneous content |
| **Card** | Content is browsable; items independently valuable; visual presentation matters | Comparing attributes across items is the primary task |
| **List** | Text-heavy, ordered, homogeneous content (file list, log entries) | Visual differentiation between items matters |
| **Hybrid** | Medium-complexity data benefiting from both scan (table) and glance (card) | Do not build two versions unless users genuinely need both |

### Form Patterns

- **Labels above fields** — never placeholder-only (placeholder disappears on focus, destroying guidance at the moment the user needs it most)
- **Validate on blur** for individual fields; validate on submit for the full form; never validate on every keystroke (too aggressive)
- **Inline errors directly below the field** — not in a banner at the top (the user cannot see which field caused an error from a top banner)
- **Group related fields** by visual proximity — name fields together, address fields together, payment fields together
- **Mark optional not required** — most fields are required; saying "(optional)" for the few that are not is cleaner than asterisks everywhere

### The Five UI States

Every data surface must define and design all five states. Missing a state means the user encounters broken UI in production:

| State | What It Means | Design Requirement |
|-------|--------------|-------------------|
| **Default** | Data loaded, normal operation | The table/card/list in its designed form |
| **Loading** | Data in flight | Skeleton (>1s expected) or spinner (unknown/quick); never blank white |
| **Empty** | No data, but not an error | Explain why empty + call to action ("No ADRs yet. Create your first decision record.") |
| **Error** | Something went wrong | What went wrong + why + exact action to recover; never a stack trace |
| **Partial result** | Some data loaded, some failed | Show what succeeded; indicate what failed; allow retry for failed parts |

**Empty state rule**: a blank space is a design failure. Every empty state needs: an icon or illustration, a reason for emptiness, and a CTA (button or link) to resolve it.

### Linear Keyboard-First Patterns

- **Command palette** (`Cmd+K`) accessible from anywhere — the power user's entire navigation
- **Shortcut tooltips** that appear after hovering ~2s — progressive disclosure of keyboard shortcuts without requiring documentation
- **Inline filters** not modal filters — never force a modal context-switch for a common operation
- **Keyboard shortcuts** for every frequent action — revealed in tooltips, never hidden

---

## Motion Timing + Perceived Performance
<!-- last-verified: 2026-05-12 -->

### Animation Timing

| Type | Duration | Easing | Use |
|------|---------|--------|-----|
| **Micro-interaction** | 100–200ms | ease-out | Button press, toggle, hover state change |
| **Component entrance** | 200–300ms | ease-out | Modal open, drawer slide in, element appear |
| **Component exit** | 150–200ms | ease-in | Faster exits feel snappier |
| **Page transition** | 300–500ms max | ease-in-out | Never exceed 500ms |

**Easing rules**:
- Entering the screen: **ease-out** (fast start, slow finish — the element "arrives" naturally)
- Leaving the screen: **ease-in** (slow start, fast finish — gets out of the way)
- Never use **linear** easing for UI (looks mechanical and cheap)
- `cubic-bezier(0.25, 0.1, 0.25, 1.0)` = `ease` — acceptable default

**Purposeful animation only**: animation should orient the user (where did this come from? where is this going?), not entertain. Remove: auto-playing carousels, decorative hover animations on every card, parallax on informational content.

"If in doubt, leave it out."

### RAIL Model
<!-- last-verified: 2026-05-12 -->

| Phase | Target | Notes |
|-------|--------|-------|
| **Response** | User input → feedback ≤100ms; process ≤50ms | The 50ms processing budget (background work consumes the other 50ms) |
| **Animation** | 60fps = 16ms/frame; app gets ~10ms | Compositor-only transforms (translate, scale, opacity) stay on GPU |
| **Idle** | Work in ≤50ms chunks via `requestIdleCallback` | Yield to input events between chunks |
| **Load** | Interactive within 5s on mid-range mobile (slow 3G) | Subsequent loads under 2s |

### Skeleton vs Spinner

| Pattern | Use When | Never When |
|---------|----------|-----------|
| **Skeleton screen** | Load time >1s expected; layout known in advance; content-heavy surfaces | Load time <300ms (causes flash of nothing); layout varies significantly by content |
| **Spinner** | Unknown duration; single component; explicit user action (save, submit) | Full-page loads; multiple parallel fetches (multiple spinners are disorienting) |
| **No indicator** | Operation completes <100ms | Any operation >100ms |

**Skeleton rule**: the placeholder must accurately approximate the final layout. A skeleton that bears no resemblance to actual content creates a discontinuity that undermines the entire purpose.

### Optimistic UI

Update the interface immediately after user action; revert only on error.

**Use when**: low-risk, high-frequency actions (like, bookmark, mark-as-read, re-order).

**Never use when**: irreversible actions (delete), financial transactions, actions with significant side effects.

**Pattern**:
1. Immediately update local state
2. Display result to user
3. Fire API call in background
4. On error: revert state + show error toast ("Couldn't save — tap to retry")

### Debounce vs Throttle

| Technique | When to Use | Timing |
|-----------|-------------|--------|
| **Debounce** (delay until idle) | Search-as-you-type, auto-save, resize handlers | 150–300ms on text input |
| **Throttle** (rate-limit) | Scroll handlers, mouse-move, polling | 16ms (1 frame) or 100ms |

Never fire heavy operations on every keystroke.

---

## When to Reach for Which Reference

| Task | Reference |
|------|-----------|
| Visual hierarchy, CARP, typography in depth, 5-shade palette, grayscale-first | [`visual-design-fundamentals.md`](references/visual-design-fundamentals.md) |
| Modal/drawer/inline/table/card/form pattern depth, five UI states, Linear patterns | [`component-patterns.md`](references/component-patterns.md) |
| WCAG 2.2 full audit, ARIA patterns, keyboard nav, focus management, screen readers, accessible primitives | [`accessibility.md`](references/accessibility.md) |
| Animation timing depth, RAIL deep-dive, skeleton implementation, optimistic UI patterns, debounce/throttle | [`motion-and-perceived-performance.md`](references/motion-and-perceived-performance.md) |
| Running a web UI quality audit | [`design-review-checklist.md`](references/design-review-checklist.md) |
| Durable design canon (Rams/Norman/Nielsen/Tufte/Bloch/Zhuo), perception thresholds, full canon roll-call | [`design-fundamentals.md`](references/design-fundamentals.md) |

---

## Cross-References

- **`tui-design`** — sibling hat for terminal/CLI output design; when a surface has both web UI and CLI components, use both skills.
- **`api-design-craft`** — sibling hat for the API quality and taste lens; the web UI and the API it consumes are both interface surfaces.
- **`agentic-interface-design`** — when the web UI exposes a tool surface or is consumed by an agent rather than a human.
- **HTML output conventions rule** (`rules/writing/html-output-conventions.md`) — Praxion's dashboard runtime conventions (Markdown-as-source-of-truth, server-only filesystem access, renderer registry, narrow live refresh, empty-state degradation); auto-loads when working on `dashboard_app/`.
