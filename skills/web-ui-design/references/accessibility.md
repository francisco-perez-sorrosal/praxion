# Accessibility (Web UI)

Full WCAG 2.2 audit guidance, ARIA patterns, keyboard navigation, focus management, accessible primitives, and screen reader considerations. Back to [SKILL.md](../SKILL.md). <!-- last-verified: 2026-05-12 -->

Accessibility is not a feature to add after launch — it is what correct interactive behavior looks like. An inaccessible button is a broken button. An inaccessible modal is a broken modal.

---

## WCAG 2.2 AA — Full Requirements

Current standard: **WCAG 2.2**, released October 2023. Supersedes 2.1. AA is the legal minimum in most jurisdictions (EU, UK, ADA/Section 508).

### Contrast Requirements

| Criterion | AA Requirement | AAA |
|-----------|---------------|-----|
| Normal text | 4.5:1 | 7:1 |
| Large text (≥18px regular or ≥14px bold) | 3:1 | 4.5:1 |
| Non-text UI (icons, input borders, chart lines, focus indicators) | 3:1 | N/A |
| Decorative elements (background textures, inactive controls) | No requirement | N/A |

**Testing tools**: WebAIM Contrast Checker (browser extension), Figma Contrast plugin, Chrome DevTools accessibility panel, Accessible Colors (`accessible-colors.com`).

### Focus Indicators (New in 2.2 — SC 2.4.11, 2.4.12)

Every focused element must have:
- **≥2px perimeter** of visible focus indicator
- **3:1 contrast** between focused and unfocused states (not against background — against the element itself)

The default browser outline is often insufficient. Design explicit focus styles:

```css
:focus-visible {
  outline: 2.5px solid var(--color-brand);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}
```

Never `outline: none` without a replacement — this makes the element invisible to keyboard users.

### Keyboard Navigation (SC 2.1.1)

Every interactive element must be reachable and operable with a keyboard alone:
- **Tab**: move to next focusable element
- **Shift+Tab**: move to previous focusable element
- **Enter**: activate buttons and links
- **Space**: toggle checkboxes, activate buttons
- **Arrow keys**: navigate within composite widgets (radio groups, tab panels, menus, sliders)
- **Escape**: close modals, dismiss tooltips, cancel operations

Tab order must match the **visual reading order** (left-to-right, top-to-bottom in LTR). Never create a tab order that jumps around the page illogically.

### Touch Targets (New in 2.2 — SC 2.5.8)

- **24×24 CSS pixels** minimum (AA)
- **44×44 CSS pixels** (AAA, recommended for primary actions)
- Spacing between targets counts — a 24px target with 5px on each side is effectively larger

Note: touch targets apply to any pointer input (mouse, touch, stylus), not just mobile touchscreens.

### Text Resizing (SC 1.4.4)

Text must be resizable up to 200% without loss of content or functionality. Use relative units (`em`, `rem`) for font sizes, not `px` in stylesheets. Never disable browser text zoom.

---

## Semantic HTML: The First Principle

Use the right HTML element for the semantic role. Browser-native semantics are free, accessible, and universally understood by assistive technology.

| Task | Correct Element | Wrong Element |
|------|----------------|--------------|
| Clickable action | `<button>` | `<div onClick>`, `<span onClick>` |
| Navigation link | `<a href>` | `<div onClick>`, `<button>` (unless it's an SPA nav) |
| Main content area | `<main>` | `<div id="main">` |
| Page navigation | `<nav aria-label="...">` | `<div class="nav">` |
| Page header | `<header>` | `<div class="header">` |
| Page footer | `<footer>` | `<div class="footer">` |
| Aside content | `<aside>` | `<div class="sidebar">` |
| Headings | `<h1>` through `<h6>` | `<div class="heading">` |
| Lists | `<ul>`, `<ol>`, `<dl>` | `<div>`s with items |
| Data tables | `<table>`, `<th scope>` | Grid of `<div>`s |
| Form fields | `<input>`, `<select>`, `<textarea>` + `<label>` | Styled `<div>`s |

**The test**: if you removed all CSS, would a screen reader still understand the page structure and all interactive elements? If no, the semantic HTML is broken.

---

## ARIA: When and How

ARIA (Accessible Rich Internet Applications) extends HTML semantics for interactive widgets that HTML alone doesn't express. Use ARIA only when HTML is insufficient.

**Rule**: ARIA should enhance, never replace, native semantics. A `<button>` with `role="button"` is redundant. A custom accordion component needs `role="button"`, `aria-expanded`, and `aria-controls`.

### Common ARIA Patterns

**Disclosure / Accordion**:
```html
<button aria-expanded="false" aria-controls="panel-1">Section Title</button>
<div id="panel-1" hidden>Content</div>
```

On toggle: set `aria-expanded="true"`, remove `hidden` from the panel.

**Modal Dialog**:
```html
<dialog aria-labelledby="dialog-title" aria-describedby="dialog-desc">
  <h2 id="dialog-title">Confirm Delete</h2>
  <p id="dialog-desc">This action cannot be undone.</p>
  <button>Cancel</button>
  <button>Delete</button>
</dialog>
```

Use `aria-modal="true"` when using `role="dialog"` without `<dialog>` element (tells screen readers that content behind the modal is inert).

**Live Regions** (for dynamic content updates):
```html
<div aria-live="polite" aria-atomic="true">
  {statusMessage}
</div>
```
- `aria-live="polite"`: announces update when the user is idle
- `aria-live="assertive"`: interrupts immediately (errors only)
- `aria-atomic="true"`: announce the entire region when any part changes

**Tab Interface**:
```html
<div role="tablist" aria-label="Settings">
  <button role="tab" aria-selected="true" aria-controls="panel-general">General</button>
  <button role="tab" aria-selected="false" aria-controls="panel-security">Security</button>
</div>
<div role="tabpanel" id="panel-general" aria-labelledby="tab-general">...</div>
<div role="tabpanel" id="panel-security" aria-labelledby="tab-security" hidden>...</div>
```

Arrow key navigation required within the `tablist`.

---

## Focus Management

Focus management is what makes modal-style components keyboard-accessible. It is also where most implementations fail.

### On Modal Open

When a modal, dialog, drawer, or sheet opens:
1. **Save the current focus** (the element that triggered the open)
2. **Move focus** to the first focusable element inside the modal (the primary action button or the first form field)
3. **Trap focus** within the modal — Tab/Shift+Tab cycles through modal content only

### On Modal Close

1. **Return focus** to the element that triggered the modal open (the saved reference from step 1)
2. If the trigger was destroyed (deleted item), return focus to a logical nearby element

### Focus Trap Implementation

Radix UI's `Dialog` and `AlertDialog` handle focus trapping and restoration correctly. Do not implement your own unless you have a specific reason — focus trapping has many edge cases (dynamically added elements, iframes, shadow DOM).

For custom implementations: use the `inert` attribute to make all content outside the modal unreachable by keyboard and assistive technology:

```js
document.getElementById('main-content').setAttribute('inert', '');
```

Remove `inert` when the modal closes.

### Skip Link

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  z-index: 999;
  padding: 8px;
  background: var(--color-brand);
  color: white;
  text-decoration: none;
}
.skip-link:focus {
  top: 0;
}
```

The first interactive element in the document, becomes visible when focused. Essential for keyboard users who otherwise Tab through the entire navigation on every page load.

---

## Accessible Primitives Pattern (Radix/shadcn)

The most reliable path to accessible interactive components is to use headless accessible primitives and apply your own styling.

**Radix UI** provides:
- Correct keyboard interactions (per ARIA Authoring Practices Guide)
- Proper ARIA attributes (automatically managed)
- Focus management (trap, restore, delegation)
- All standard patterns: Dialog, Select, Checkbox, Radio, Tabs, Accordion, Dropdown, Popover, Tooltip, Slider, Toggle, and more

**shadcn/ui** wraps Radix with Tailwind styling that you own (copy-paste into your project). The styling is yours; the behavior is Radix's.

**The pattern**:
1. Use Radix for behavior (keyboard interaction, ARIA, focus)
2. Apply your design system tokens for style
3. Never reimplement what Radix already solved correctly

---

## Color Blindness

Approximately 8% of men (1 in 12) and 0.5% of women have some form of color blindness. Red-green is the most common variant.

**Design rules**:
- Never use color alone to convey information — pair with shape, label, pattern, or text
- Error states: red + an error icon + error text (not just red color)
- Status badges: color + text label ("Active", "Inactive") — not just green/red dots
- Charts: use distinct patterns or textures in addition to colors; never rely on hue alone for distinguishing series

**Testing**: browser DevTools have a Vision Deficiency Emulation tab; Figma has a Color Blind plugin; Sim Daltonism (macOS) simulates all types in real-time.

---

## prefers-reduced-motion

The `prefers-reduced-motion` media query respects users who have requested reduced motion in their OS settings. This includes users with vestibular disorders (inner ear conditions that cause motion sickness from screen animations), epilepsy, and users who simply prefer less motion.

```css
@media (prefers-reduced-motion: no-preference) {
  .animated-element {
    transition: transform 250ms ease-out;
  }
}

/* Or the defensive form: remove motion by default, add back when safe */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

Never force motion. If a user has expressed a preference for reduced motion, honor it unconditionally.

---

## Screen Reader Considerations

Screen readers (NVDA, JAWS on Windows; VoiceOver on macOS/iOS; TalkBack on Android) read the accessibility tree — the semantic structure of the page.

**Common issues**:
- **Decorative images**: `alt=""` (empty alt) signals "skip this" to screen readers. Never omit `alt` — an image without `alt` is read as the image filename.
- **Icon buttons without text**: `<button><svg>...</svg></button>` will be read as "button" with no description. Add `aria-label="Delete"` or a visually hidden `<span>`.
- **Form fields without labels**: a `<input>` with no `<label>` or `aria-label` will be read as "edit text" with no context.
- **Dynamic updates**: content that changes dynamically (counter updates, toast notifications, search results loading) must use `aria-live` regions to announce changes.
- **Table headers**: use `<th scope="col">` and `<th scope="row">` so screen readers can associate cells with their headers when reading complex tables.

**Testing**: Use VoiceOver on macOS (Cmd+F5), NVDA + Firefox on Windows (free), or the browser's built-in accessibility tree viewer (Chrome DevTools Accessibility panel).
