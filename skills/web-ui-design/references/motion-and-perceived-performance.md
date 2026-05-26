# Motion and Perceived Performance

Animation timing depth, the RAIL model, skeleton vs spinner implementation, optimistic UI patterns, debounce/throttle, and animation-to-mask-latency. Back to [SKILL.md](../SKILL.md). <!-- last-verified: 2026-05-12 -->

The perception thresholds (< 100ms instant / 100ms–1s progression / 1s–10s drift / > 10s abandonment) and the 50ms input budget live in [`design-fundamentals.md`](design-fundamentals.md). This file covers implementation and web-specific application.

---

## Animation Timing

### The Core Principle

Animation should **orient the user** — answer "where did this come from?" and "where is this going?" — not entertain. Animation is communication, not decoration.

Remove decorative animation without hesitation. Every animation that doesn't communicate something is costing the user attention and motion-discomfort risk.

"If in doubt, leave it out."

### Duration Guidelines

| Type | Duration Range | Default |
|------|---------------|---------|
| **Micro-interaction** (toggle, button press, hover state) | 100–200ms | 150ms |
| **Component entrance** (modal open, drawer slide in, element appear) | 200–300ms | 250ms |
| **Component exit** | 150–200ms | 175ms (exits should be faster — get out of the way) |
| **Page transition** | 300–500ms | 350ms |
| **Maximum** | 500ms | Never exceed for UI transitions |

**Why exits are faster**: when a user dismisses something, they are ready to continue. Making the exit fast feels responsive. Making the entrance 250ms feels smooth without feeling slow.

### Easing Functions

| Easing | When | CSS |
|--------|------|-----|
| **ease-out** | Element entering the screen (appears from edge/below, scales up) | `cubic-bezier(0.0, 0, 0.2, 1)` |
| **ease-in** | Element leaving the screen (recedes, fades away) | `cubic-bezier(0.4, 0, 1, 1)` |
| **ease-in-out** | Page transitions, complex choreographed sequences | `cubic-bezier(0.4, 0, 0.2, 1)` |
| **spring** (approximated) | Bouncy, organic motion (optional; sparingly) | Not native CSS — use `spring()` via Framer Motion |
| ~~linear~~ | **Never** for UI transitions | Looks mechanical, unnatural, cheap |

**Material Design easing values** as reference:
- Standard: `cubic-bezier(0.2, 0, 0, 1)` — most UI transitions
- Decelerate (ease-out for entering): `cubic-bezier(0.0, 0, 0.2, 1)`
- Accelerate (ease-in for leaving): `cubic-bezier(0.4, 0, 1, 1)`

### Properties to Animate

Prefer properties that do not trigger layout recalculation:

| Safe (GPU-composited, no layout) | Expensive (triggers layout) |
|----------------------------------|----------------------------|
| `transform: translate()` | `top`, `left`, `right`, `bottom` |
| `transform: scale()` | `width`, `height` |
| `transform: rotate()` | `margin`, `padding` |
| `opacity` | `border-width` |
| `filter` | `font-size` |

Animating `width` or `height` causes layout thrashing — every frame recalculates the document flow. Use `transform: scaleX()` for width-like animations. Use `clip-path` for reveal animations.

---

## The RAIL Model (Web Performance) <!-- last-verified: 2026-05-12 -->

RAIL = Response, Animation, Idle, Load. A user-centric performance model.

### Response (< 100ms perceived-instant)

- User action → visible feedback within **100ms**
- Processing must complete within **50ms** (background work consumes the other 50ms)
- What constitutes feedback: button state change, loading indicator start, any visual acknowledgment of the action

**The 50ms input budget**: input events are queued every 16ms (one frame). Processing an input event for longer than 50ms blocks the next event. At >100ms total, the user perceives lag.

**Practical**: event handlers should be short. Heavy work (filtering 10,000 items, complex calculations) must be deferred via `requestIdleCallback` or Web Workers.

### Animation (60fps)

- Target: **60 frames per second** = **16.67ms per frame**
- Browser rendering pipeline takes ~6ms: the application has **~10ms** of actual work per frame
- Exceeding 10ms drops a frame — the user sees jitter

**GPU-only animations**: `transform` and `opacity` are handled by the compositor thread — they do not affect the JavaScript thread. These can animate at 60fps even when JavaScript is busy.

**DevTools**: Chrome DevTools Performance panel → record while animating → look for dropped frames (red marks) and "Rendering" sections > 10ms.

### Idle

- Use `requestIdleCallback` for deferred, non-critical work
- Work in chunks of **≤50ms** — yield to input events between chunks
- Post-load work: analytics, prefetching next routes, preloading images, secondary data

```javascript
requestIdleCallback((deadline) => {
  while (deadline.timeRemaining() > 5 && tasks.length > 0) {
    doTask(tasks.shift());
  }
});
```

### Load

- **First Contentful Paint (FCP)**: ≤1.8s (Good), ≤3.0s (Needs Improvement)
- **Largest Contentful Paint (LCP)**: ≤2.5s (Good), ≤4.0s (Needs Improvement)
- **Time to Interactive (TTI)**: ≤5s on mid-range mobile, slow 3G (the baseline)
- **Cumulative Layout Shift (CLS)**: ≤0.1 (Good) — reserve space for images and ads; never let content shift under the user

**Core Web Vitals** (Google's subset of RAIL): LCP, CLS, and INP (Interaction to Next Paint, which replaced FID in 2024 — threshold ≤200ms for a single interaction).

---

## Skeleton Screens

### When to Use

A skeleton screen is a layout placeholder that approximates the final content's shape. It communicates "content is coming and it will look like this."

Use skeleton screens when:
- Load time is expected to be **>1s**
- The layout is **known in advance** (you know there will be a title, a paragraph, and a 3-column grid)
- The surface is **content-heavy** (feed, dashboard, list of articles)

Do not use skeleton screens when:
- Load time is <300ms (the flash of skeleton followed immediately by content is jarring)
- The layout varies dramatically by content (skeleton vs actual layout mismatch undermines trust)
- The user triggered an explicit action — a spinner better communicates "processing your request"

### Skeleton Design

**Accurate shape approximation**: the skeleton must resemble the actual content. Lines of the same approximate width, circles for avatars, rectangles for images. A skeleton that looks nothing like the content it precedes creates a jarring transition.

**Pulse animation**:

```css
@keyframes skeleton-pulse {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-surface-2) 25%,
    var(--color-surface-3) 50%,
    var(--color-surface-2) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}
```

This "shimmer" effect is the standard; `prefers-reduced-motion` should disable it:

```css
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
```

**Item count**: show skeleton items to match typical data density (3–5 skeleton rows for a list that usually has 3–10 items). Avoid showing a single skeleton item when the list typically has 20.

---

## Optimistic UI

Optimistic UI updates the interface immediately after user action, assuming the operation will succeed, and reverts only on failure.

### Benefits

- **Perceived instant response**: the action feels immediate even when the API call takes 200ms
- **Better for high-frequency, low-risk actions**: toggling a like, marking an item complete, reordering a list
- **Reduced loading states**: fewer spinners for short API calls

### When to Use

| Use | Don't Use |
|-----|-----------|
| Like / bookmark / subscribe | Delete (irreversible) |
| Mark as complete / read / archived | Financial transactions |
| Drag to reorder (within a list) | Anything with significant side effects |
| Tag or categorize an item | Operations where failure is common |

**Risk assessment heuristic**: would a momentary wrong display (the optimistic state) cause the user confusion or data loss if the server rejects it? If yes, wait for the server response.

### Implementation Pattern

```typescript
// 1. Capture current state for rollback
const previousItems = [...items];

// 2. Immediately update local state (optimistic)
setItems(items.map(item =>
  item.id === id ? { ...item, completed: true } : item
));

// 3. Fire the API call in background
try {
  await api.markComplete(id);
} catch (error) {
  // 4. On error: revert and notify
  setItems(previousItems);
  showToast("Couldn't save — tap to retry", { action: () => markComplete(id) });
}
```

**React Query / SWR**: both libraries have built-in optimistic update APIs (`useMutation`'s `onMutate` + `onError` for React Query; `mutate` with `optimisticData` for SWR).

### Retry on Error

When reverting, offer the user a retry:
- Toast with "Couldn't save — tap to retry" (auto-dismiss 8–12s, longer than success toasts)
- Undo-style recovery: "Undo" button instead of retry when appropriate (bookmark was removed — offer Undo rather than Retry)

---

## Debounce and Throttle

Both techniques prevent expensive operations from firing at the input rate.

### Debounce

Delays execution until the user is idle. Fires **once**, at the end of a burst.

```typescript
const debouncedSearch = useMemo(
  () => debounce((query: string) => search(query), 200),
  []
);
```

**Use for**: search-as-you-type, auto-save, window resize handler, input validation API calls.

**Timing**: 150–300ms for text input; 300–500ms for resize.

### Throttle

Rate-limits execution to at most once per interval. Fires **regularly** throughout a burst.

```typescript
const throttledScroll = useMemo(
  () => throttle((event: Event) => handleScroll(event), 16),
  []
);
```

**Use for**: scroll handlers, mouse-move tracking, real-time data polling, window resize (when immediate feedback is needed, unlike debounce).

**Timing**: 16ms (one frame, ~60fps) for smooth visual tracking; 100ms for less critical polling.

### The Rule

Never fire heavy operations (API calls, expensive calculations, DOM manipulation) at the raw input event rate. Users type faster than APIs respond. Scroll events fire at 60fps — a database query per scroll event would be disastrous.

---

## Animation to Mask Latency

Animation can make real latency invisible to the user:

**Loading skeleton pulse**: draws the eye while content loads — the user feels "something is happening" rather than "the page is broken."

**Button depression on click**: provides instant tactile feedback while the API call is in-flight. The button "depresses" in 50ms; the actual result arrives 200ms later. The user experienced instant feedback.

**Page transition animation**: sliding old content away while new content loads gives the impression of instant navigation. The transition takes 300ms; the new page data takes 150ms; the user sees no wait.

**The invariant**: transition duration must be ≤ the actual operation time. Never animate "after" data arrives — the user sees fake work being done after the real work is done, which undermines trust.

If the transition is 300ms and the data arrives in 100ms, either:
- Show data as soon as it arrives (skip the rest of the transition), or
- Keep the transition, but don't start it until data is ready (so data appears at the natural end of the transition)

Never hold data until the animation completes on the far side of the transition.
