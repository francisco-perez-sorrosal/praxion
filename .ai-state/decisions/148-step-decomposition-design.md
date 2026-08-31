---
id: dec-148
title: Dashboard redesign step ordering and decomposition design
status: accepted
category: implementation
date: 2026-05-12
summary: Records the four non-obvious step-ordering and component-design decisions made during implementation plan decomposition for the dashboard redesign.
tags: [dashboard, decomposition, step-ordering, recharts, pan-zoom, implementation]
made_by: agent
agent_type: implementation-planner
branch: worktree-dashboard-redesign
pipeline_tier: full
affected_files:
  - dashboard_app/src/components/viz/use-pan-zoom.ts
  - dashboard_app/src/components/viz/diagram-frame.tsx
  - dashboard_app/src/components/viz/decision-graph.tsx
  - dashboard_app/src/components/metrics-dashboard.tsx
  - dashboard_app/src/components/metrics-summary-cards.tsx
  - dashboard_app/src/components/metrics-trends.tsx
  - dashboard_app/src/server/view-models/metrics.ts
  - dashboard_app/src/app/globals.css
---

## Context

The systems-architect produced SYSTEMS_PLAN.md with a high-level 7-concern decomposition and sequencing constraints. The implementation-planner decomposed those concerns into 42 steps across 9 phases. Four non-obvious ordering and structural decisions were made during decomposition that a future implementer or planner should understand.

## Decision

Four decomposition choices are recorded here:

1. **Token layer before component primitives**: `globals.css` token layer (Step 11) lands before `ArtifactCard`, `MetadataChips`, `ErrorState`, etc. (Steps 24–25). Components consume CSS custom properties; if tokens don't exist first, components hard-code values and need a retrofit.

2. **`parseMarkdownTable` retained during Sentrux removal**: The function is currently used only by Sentrux code but is correct and will be immediately repurposed for `parseMetricsLog` in Step 26. Deleting it in Step 4 and reimplementing in Step 26 is unnecessary churn. The Sentrux *callers* are removed in Step 4; the function itself stays.

3. **`usePanZoom` extracted into `use-pan-zoom.ts` in Step 17 (not embedded in `diagram-viewer.tsx`)**: Both `DiagramViewer` (Step 17) and `DecisionGraph` (Step 22) need the hook. Embedding it inside `diagram-viewer.tsx` would require `DecisionGraph` to either import from that file (coupling) or copy the code (duplication). The correct seam is `src/components/viz/use-pan-zoom.ts` as a shared module, created in Step 17 alongside `DiagramViewer`.

4. **Metrics-dashboard.tsx file split combined with recharts wiring (Step 34)**: The architect flagged the 701-line file and recommended splitting AFTER Sentrux removal + recharts swap. Placing the split in its own step (before recharts wiring) adds churn with no behavior change. Combining the recharts swap + split in one commit (Step 34) keeps the diff readable and the step count minimal.

## Considered Options

**Token layer timing:**
- (a) *Token layer first* (chosen): establishes the CSS contract before components consume it; no retrofit needed.
- (b) Components first, add tokens after: requires a second pass over every component to replace hardcoded values; more total work.

**parseMarkdownTable deletion:**
- (a) *Retain and repurpose* (chosen): zero extra work; the function is immediately reused.
- (b) Delete in Step 4, reimplement in Step 26: equivalent result, more churn.

**usePanZoom placement:**
- (a) *Shared `use-pan-zoom.ts`* (chosen): clean import for both components; no coupling or duplication.
- (b) Embedded in `diagram-viewer.tsx`, imported by `decision-graph.tsx`: creates a directional coupling (graph imports from viewer file — wrong semantic).
- (c) Duplicated: violates DRY; the ~80 LOC hook would drift between the two copies.

**File-split timing:**
- (a) *Combined with recharts wiring* (chosen): one commit, readable diff; satisfies the architect's "after recharts swap" constraint.
- (b) Pre-split before recharts: adds a commit that touches `metrics-dashboard.tsx` twice; harder to bisect.
- (c) Post-recharts in a separate step: adds a step and a commit boundary with no user-visible change.

## Consequences

**Positive:**
- `usePanZoom` is shared cleanly; adding a third consumer (e.g., a future `MapViewer`) is a single import change.
- `parseMarkdownTable` reuse avoids reimplementation risk.
- Token layer is load-bearing from Step 11 onward; all component steps know where to find the CSS contract.
- The file split at Step 34 produces a clean diff bounded to the recharts wiring commit.

**Negative:**
- Step 11 touches three concerns (token layer + parseWipBody + validateProjectRoot). This is a wide step but the concerns are all "global infrastructure before any new code." Splitting further would create two steps where one is "add CSS variables" (tiny) and one is "fix two TypeScript lines" (also tiny) — not worth the ceremony.
- If Step 17 is blocked (network or dependency), Step 22 cannot import `usePanZoom`. The dependency is explicit in the step ordering.
