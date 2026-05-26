# Web UI Design Review Checklist

The quality audit checklist for web UI surfaces. Run this when reviewing a web UI implementation, preparing a PASS/FAIL/WARN Interface Design Review, or running `verifier` quality checks. Reference the in-scope skill reference files for depth on any item. Back to [SKILL.md](../SKILL.md).

---

## How to Use

For each item below, assess the implementation and mark:
- **PASS** — criterion met
- **WARN** — criterion partially met or edge case present; note what is borderline
- **FAIL** — criterion not met; cite the specific file/component/line where possible

A surface with any FAIL item fails the review. Surface FAIL and WARN items in findings sorted by severity.

---

## Contrast and Color

- [ ] Body text contrast ≥ **4.5:1** against its background (WCAG 2.2 AA)
- [ ] Large text (≥18px regular or ≥14px bold) contrast ≥ **3:1**
- [ ] Non-text UI elements (icons, input borders, dividers) contrast ≥ **3:1**
- [ ] Color is **not the sole conveyor** of meaning — every color-coded status also uses an icon, label, or pattern
- [ ] Color-blindness safe — red/green only statuses have additional differentiators (shape, icon, text)
- [ ] Dark mode token swap present (`prefers-color-scheme: dark`) — or explicitly acknowledged as out of scope with a WARN

---

## Keyboard Navigation and Focus

- [ ] Every interactive element is reachable by **Tab** (no interactive element keyboard-inaccessible)
- [ ] Tab order matches **visual reading order** (left-to-right, top-to-bottom in LTR)
- [ ] **Focus indicators** are visible (≥2px outline, ≥3:1 contrast focused vs unfocused) — not the browser default
- [ ] **Skip to main content** link present as the first focusable element in the page
- [ ] No `:focus { outline: none }` without a replacement
- [ ] Arrow key navigation implemented for composite widgets (tabs, radio groups, menus, sliders)

---

## Focus Management (Modal/Overlay)

- [ ] On modal/dialog/drawer **open**: focus moves to first focusable element inside
- [ ] On modal/dialog/drawer **close**: focus returns to the element that triggered the open
- [ ] **Focus trap** active while modal is open (Tab/Shift+Tab cycle within modal only)
- [ ] Escape key closes modal/dialog/drawer (except destructive confirmations)

---

## The Five UI States

For every data surface (table, list, card grid, form):
- [ ] **Default state** (loaded data) — designed and implemented
- [ ] **Loading state** — skeleton or spinner (no blank white); skeleton approximates final layout
- [ ] **Empty state** — reason for emptiness + CTA (never blank white)
- [ ] **Error state** — what went wrong + why + how to recover; no stack trace
- [ ] **Partial result** — what succeeded shown; what failed indicated with retry option

---

## Design Token Consistency

- [ ] All spacing values are **multiples of 4px** (no ad-hoc 13px, 22px, etc.)
- [ ] Colors reference **design tokens** (CSS custom properties), not hard-coded hex values
- [ ] Typography uses **token-based font sizes** — no raw `14px`, `16px` outside the token definition
- [ ] Shadows are from the **shadow scale** — no ad-hoc box-shadow values
- [ ] Z-index values reference **z-index tokens** — no arbitrary z-index numbers scattered across components

---

## Motion and Animation

- [ ] All CSS transitions/animations wrapped in `@media (prefers-reduced-motion: no-preference)` — or animations removed entirely in `reduce` mode
- [ ] Micro-interactions: **100–200ms** duration
- [ ] Entrance animations: **200–300ms** duration
- [ ] **No linear easing** for UI transitions (must be ease-in, ease-out, or ease-in-out)
- [ ] **No animations > 500ms** (except deliberate slow reveals with user initiation)
- [ ] Animations are purposeful — each animation communicates orientation or feedback, not decoration
- [ ] Loading skeletons have the pulse animation **disabled** when `prefers-reduced-motion: reduce`

---

## Component Taste

- [ ] **No modals for forms that require scrolling** — use drawer instead
- [ ] **No modals for non-destructive informational content** — use inline or drawer
- [ ] **Tables used only when comparison across rows is the primary task** — not for all structured data
- [ ] **Empty states** include an explanation + CTA (no blank white areas)
- [ ] **Toast notifications** auto-dismiss within 4–6s; errors use persistent banners or inline messages
- [ ] **Form labels above inputs** — no placeholder-only labels
- [ ] **Form validation on blur** (not on every keystroke); full form validation on submit
- [ ] **Inline errors directly below the field** that caused them

---

## Typography

- [ ] Body text **≥16px**
- [ ] Body text measure **45–75ch** (line length) — `max-width: 65ch` or equivalent on prose content
- [ ] Line height **1.4–1.6** for body text
- [ ] Weight **and** color used for hierarchy (not size alone)
- [ ] No more than **two typeface families** in use (body + mono is the standard for developer UIs)

---

## Accessibility: Semantic HTML

- [ ] Clickable actions use `<button>`, not `<div>` or `<span>` with click handlers
- [ ] Page has a single `<main>` landmark
- [ ] Navigation wrapped in `<nav aria-label="...">` landmarks
- [ ] Icon buttons without visible text have `aria-label` or visually-hidden `<span>`
- [ ] Images have meaningful `alt` text; decorative images have `alt=""`
- [ ] Form inputs have associated `<label>` elements (`htmlFor` + `id` or wrapping `<label>`)
- [ ] Data tables have `<th scope="col">` and `<th scope="row">` as appropriate

---

## Touch Targets

- [ ] Interactive elements have a hit area of **≥24×24px** (AA minimum)
- [ ] Primary actions have hit areas of **≥44×44px** (recommended)
- [ ] Adjacent interactive elements have sufficient spacing (stacked hit areas ≥4px apart)

---

## Notes for Findings Report

When writing Interface Design Review findings for this checklist, use the format:

```
[FAIL|WARN|PASS] Category — Specific finding. File: path/to/file.tsx:line
```

Example:
```
[FAIL] Focus Management — Modal Dialog in src/components/DeleteConfirmDialog.tsx does not 
       return focus to the trigger element on close. Focus is lost entirely. 
       File: src/components/DeleteConfirmDialog.tsx:47

[WARN] Motion — PageTransition component uses 600ms duration (exceeds 500ms maximum).
       Not a FAIL because the transition is gated behind prefers-reduced-motion.
       File: src/components/PageTransition.tsx:12
```
