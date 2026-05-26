# Component Patterns (Web UI)

Depth on modal/drawer/inline patterns, table/card/list patterns, form patterns, empty states, the five UI states, and keyboard-first interaction patterns. For the decision tables at a glance, see the `SKILL.md` body. Back to [SKILL.md](../SKILL.md).

---

## Modal Dialogs

Modals interrupt the user's flow completely. They exist to force a decision before the user can continue. This is a high cost — use it only when the decision genuinely cannot be deferred.

### When to Use a Modal

- **Destructive confirmation**: "Delete this project? This cannot be undone." The user must decide before anything happens. The modal forces the binary choice.
- **Critical decisions requiring full attention**: payment confirmation, permission grants, accepting terms. The user must pause.
- **Short forms where the context is irrelevant**: "Create new project" when the user has no current project context to lose. Keep these ≤3–4 fields.

### When Never to Use a Modal

- Forms that require scrolling — the user loses context of what they filled in above
- Operations the user opens and dismisses repeatedly — each open/close cycle is expensive
- Displaying information only (use a drawer or inline expansion instead)
- Anything that can be done inline or in a panel alongside the current view

### Modal Design Requirements

1. **Focus management**: on open, move focus to the first focusable element inside (usually the primary action button or the first input). On close, return focus to the element that triggered the modal.
2. **Keyboard trap**: Tab/Shift-Tab must cycle through the modal content only, not escape to the background. This is required by WCAG.
3. **Escape key**: always closes the modal (unless the action is destructive — then require explicit Cancel or X).
4. **Click outside**: closes most modals; does not close destructive confirmation modals.
5. **Background overlay**: semi-transparent scrim (not full black) to maintain awareness of context.
6. **Accessible title**: `<dialog>` with `aria-labelledby` pointing to the modal heading.

### Accessible Modal Pattern (React)

Use Radix UI's `Dialog` primitive — it handles:
- Focus trapping and restoration
- `aria-modal`, `aria-labelledby`, `aria-describedby`
- Body scroll lock
- Portal rendering to document root

```tsx
<Dialog.Root>
  <Dialog.Trigger>Open</Dialog.Trigger>
  <Dialog.Portal>
    <Dialog.Overlay />
    <Dialog.Content>
      <Dialog.Title>Confirm Delete</Dialog.Title>
      <Dialog.Description>This cannot be undone.</Dialog.Description>
      {/* form or content */}
      <Dialog.Close>Cancel</Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
```

---

## Drawers / Panels

Drawers allow the main content to remain visible while the user interacts with a secondary surface. They are the correct alternative to modals for contextual operations.

### When to Use a Drawer

- **Contextual editing**: editing a row's details while the table remains visible
- **Detail views**: clicking a list item to see its full details in a side panel
- **Filters and settings**: filter controls for a data table, settings panels
- **Any operation the user wants to perform alongside the main view**

### When Not to Use a Drawer

- Operations that require the user's full attention (use a modal)
- When the drawer would cover >50% of the main content on mobile (use a new page or modal instead)
- Full-page workflows — use a new page with proper back navigation

### Drawer Design Requirements

1. Same focus management requirements as modal
2. Width: typically 380–480px on desktop; full-width below breakpoint
3. Push vs overlay: "push" the main content aside when horizontal space is ample; "overlay" on constrained viewports
4. Clear visual connection between the trigger and the panel (selected row highlight, active state)

---

## Tables

Tables are the correct choice when the user's primary task is **comparing attributes across rows**.

### Table Design Requirements

1. **Column headers**: sticky on scroll for tall tables; sortable indicators (caret icons)
2. **Row density**: compact (32px), default (40px), comfortable (48px) — offer a density toggle for data-heavy apps
3. **Numerical data**: right-align numbers so decimal points and units stack vertically
4. **Column widths**: auto-size text columns; fixed-width for narrow columns (checkboxes, actions, status badges)
5. **Selection**: checkbox column at left; "select all" in header; selected count in bulk-action bar
6. **Responsive**: below a breakpoint, stack rows (each row becomes a card) rather than allowing horizontal overflow
7. **Empty state**: a table with zero rows still needs a full empty state treatment

### When Tables Beat Cards

- Multiple columns to compare (price, date, status, author — comparing these across 20 rows)
- Users need to sort or filter by column values
- Dense data with known structure

### Table vs Card Toggle Pattern

When the data benefits from both scan (table view) and glance (card view), provide a toggle. The ADR list is a good example: default to table (sortable by date/status/category, scannable by tag) with a card view as secondary. Persist the preference to localStorage.

---

## Cards

Cards work when each item is independently valuable and visual differentiation across items matters.

### Card Design Requirements

1. **Consistent structure**: every card in a set must have the same layout (title, metadata, description, actions — always in the same slots)
2. **Clear hierarchy within the card**: title at top, most important metadata prominent, secondary info reduced
3. **Actionable**: if a card navigates, the whole card should be the target (avoid small link at bottom). If a card has multiple actions, they should be clearly differentiated.
4. **Empty state per card**: if a card can have missing optional data, define how it renders without that data (don't let it collapse unpredictably)

### Card Grid Layout

Use CSS Grid for card grids:

```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-6);
}
```

`auto-fill` with `minmax` adapts the number of columns to the viewport without explicit breakpoints.

---

## Form Patterns

Forms are where users and systems exchange structured data. The design determines whether data comes back correct or corrupted.

### Input Design

- **Label above the field** (never placeholder-as-label): the label must remain visible while the user is typing. Placeholders disappear. Placeholders may carry hint text inside the field, but the label must be persistent.
- **Input width signals expected content length**: a postal-code input should be short; a description input should be wide. Never use full-width inputs for short expected values (phone number, zip code).
- **Character count** for length-limited fields (tweet, bio, headline): show `n / 280` below the field, turning yellow near limit, red at limit.

### Validation Timing

- **On blur** (when the user leaves the field): validate the field they just finished. This is the right default — the user has declared they are done with this field.
- **On submit**: validate the full form. Show all errors at once — not one at a time (sequential validation forces multiple submit attempts).
- **On change**: only for fields where real-time feedback is intrinsically valuable (password strength meter, username availability check). Never for most fields — keystroke validation is aggressive and annoying.
- **Never validate before the user has touched the field**: marking an empty required field as an error before the user has had a chance to fill it is hostile.

### Error Display

- **Inline below the field** — directly under the input, in the field's visual group
- **Plain language** — "Must be a valid email address" not "INVALID_EMAIL_FORMAT"
- **Be specific** — "Password must be at least 8 characters" not "Invalid password"
- **Distinguish errors from warnings**: errors block submission; warnings are advisory
- **For multi-field forms**: show a brief summary at the top on submit ("Please fix 2 errors before continuing") AND inline errors per field. The summary helps screen reader users who may have missed inline errors.

### Field Grouping

Group fields by semantic relationship:

```
Personal Information
  First name   [___]   Last name   [___]
  Email        [_________________________________]

Contact Preferences  
  Notify by email    [checkbox]
  Notify by SMS      [checkbox]
```

The visual group (proximity + a group label) signals "these belong together." Improves cognitive flow and reduces form abandonment.

### Required vs Optional

Mark optional fields "(optional)" in a parenthetical after the label. Do not use asterisks (*) for required fields — screen readers announce them awkwardly, and most form fields are required anyway.

---

## The Five UI States

Every surface that displays dynamic data — a list, a table, a card, a form, a dashboard — must be designed in all five states. Designing only the "happy path" (default state with data) is incomplete and produces poor production experiences.

### 1. Default State (Loaded Data)

The intended rendering with normal data. Design this first, but not last.

### 2. Loading State

The surface while data is being fetched.

**Decision guide**:
- If the operation takes >1s and the layout is known: **skeleton screen** (placeholder shapes approximating the loaded layout)
- If the operation is <1s or the layout varies: **spinner** (single loading indicator for the component)
- If the operation takes <100ms: **no indicator** (showing a flash of a loading indicator then data is worse than showing data directly)

**Skeleton rules**:
- Approximate the final layout accurately — skeletons that look nothing like the content they precede undermine trust
- Use a subtle pulse animation to indicate activity
- Match the number of placeholder items to the typical data count (3 skeleton rows for a list that usually has 3–10 items)

### 3. Empty State

The surface when there is no data yet (or no results matching a filter).

**Empty states must include**:
- A reason for being empty ("You haven't created any ADRs yet" or "No decisions match your current filters")
- A CTA to create data or clear the filter
- Optionally: an illustration or icon that reinforces the context

Never display a blank white space. An empty state is a marketing opportunity — it tells the user what they can do.

**Filtered empty state**: "No results for 'authentication'" + a "Clear filters" button. Different message from "no data" empty state.

### 4. Error State

The surface when something went wrong loading or processing the data.

**Must include**:
- What went wrong (in plain language, not error codes)
- Why it failed (if known and useful: "The server is temporarily unavailable")
- How to recover: "Retry" button, "Refresh the page", or specific action

**Never include**:
- Stack traces
- Internal error codes as the primary surface (log them; show a friendly message + a reference code for support)
- Generic "Something went wrong" without recovery guidance

### 5. Partial Result State

The surface when some data loaded but some failed (common with parallel requests or streaming data).

**Design requirements**:
- Show what succeeded clearly
- Indicate what failed specifically ("3 of 7 metrics failed to load — Retry")
- Retry mechanism for the failed parts

---

## Keyboard-First Interaction (Linear Patterns)

Keyboard-first design is not just accessibility — it is respect for power users who live in the keyboard. The Linear project management tool demonstrates the pattern best.

### Command Palette (`Cmd+K`)

A fuzzy-search interface for every action in the application:

- Accessible from anywhere with a global keyboard shortcut
- Replaces the need to navigate menus for frequent operations
- Search by action name, not by menu location
- The power user's primary navigation after the first few days

Implementation: Radix `Command` (with `cmdk`) handles the search + keyboard navigation primitives.

### Shortcut Discoverability

Keyboard shortcuts should be discoverable without reading documentation:
- Tooltips that appear after hovering ~2 seconds reveal the keyboard shortcut
- `title` attributes on interactive elements include the shortcut: "Delete (Del)"
- A `?` shortcut or a help modal listing all shortcuts

Never require users to read documentation to discover shortcuts. The UI teaches itself.

### Focus Indicators

Focus indicators must be:
- Visible — 2px outline minimum, high contrast
- Consistent — same style across all interactive elements
- Complementary to the design — focus rings in the brand color, not the browser default blue (which often clashes)

```css
:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
:focus:not(:focus-visible) {
  outline: none; /* suppress for mouse users; preserve for keyboard */
}
```

Using `:focus-visible` instead of `:focus` shows focus rings only for keyboard navigation, not mouse clicks — a better experience for both user types.

### Skip Links

The first interactive element in the page's source must be a "Skip to main content" link, visually hidden but keyboard-accessible:

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  &:focus { top: 0; }
}
```

Essential for keyboard and screen-reader users who would otherwise have to tab through the entire navigation on every page load.
