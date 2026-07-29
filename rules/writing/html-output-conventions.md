---
paths:
- dashboard_app/**
- '**/doc_manifest.yaml'
- dashboard_app/**/*.ts
- dashboard_app/**/*.tsx
core: false
---

## HTML Output Conventions

Praxion uses HTML as a **presentation veneer over Markdown source**, never as a replacement. Markdown stays the canonical source of truth for both human and agent reading; HTML enhances the human reading experience by adding visual structure, hides dense content behind anchored links to MD sections, and is assembled by the per-project dashboard server. `dashboard_app/` is the active runtime (Next.js App Router + TypeScript). This rule applies when authoring or modifying anything in the rendering layer — dashboard pages, component library files, doc manifests, and committed `.html` artifacts.

### The Architectural Pattern

```
MD = source of truth + agent surface  (always; never duplicated)
   ↑
   │ HTML wraps, never copies; links into MD section anchors
   ↓
HTML = human-only presentation veneer  (rendered, not authored)
   ↑
   │ Dashboard server assembles; reads MD/JSON/YAML/SVG live
   ↓
Dashboard server = single per-project entry point  (single-source aggregator)
```

**Three invariants:**

1. **Markdown is canonical.** Every fact lives in exactly one place — an MD file, a YAML manifest, an SVG render, or an ADR. HTML and the dashboard server are *views* of those facts, never owners.
2. **No content duplication.** HTML never copies MD prose. It links to MD section anchors, embeds rendered SVGs, and (when a section needs to be inlined) reads the MD at view-time through the dashboard server.
3. **Agents always read MD.** The HTML layer never enters agent context. Agent token budgets are unaffected by HTML rendering.

### Hybrid Render Boundary

Two render modes coexist; pick by audience and lifetime:

| Render mode | When | Where | Persistence |
|---|---|---|---|
| **Dashboard-rendered** (default) | Ephemeral pipeline artifacts, in-flight project state, per-project navigation | `dashboard_app/` reads MD/JSON/YAML on request, emits HTML through the server layer | None on disk; rendered live; closes when the dashboard server stops |
| **Pre-rendered** (committed) | Share-out artifacts intended to be linked from PRs, emails, slack, or external sites | Pre-commit hook generates `<file>.html` alongside the MD source; both committed | On disk in git; opt-in via frontmatter `share_out: true` |

**Defaults:**

- `IMPLEMENTATION_PLAN.md`, `SYSTEMS_PLAN.md`, `VERIFICATION_REPORT.md`, `IDEA_PROPOSAL.md`, `WIP.md`, `TEST_RESULTS.md` → **Dashboard-rendered only.** No `.html` companion on disk; the dashboard renders them live.
- `docs/architecture.md`, `.ai-state/DESIGN.md`, `docs/concepts.md`, `docs/aac-dac.md` → **Dashboard-rendered by default.** Add `share_out: true` to the frontmatter when a stable shareable link is needed (e.g., a public docs deploy or a one-off explainer for stakeholders).
- `README.md`, `CLAUDE.md`, ADRs, rules, skills → **MD only, no HTML at all.** These are agent-first or GitHub-first surfaces; HTML never enters their picture.

### Component Library

HTML rendering is **not hand-authored per artifact**. The as-built Next.js App Router structure is:

| Layer | Location | Role |
|---|---|---|
| **Server view-models** | `dashboard_app/src/server/view-models/<surface>.ts` | Data shaping — reads MD/JSON/YAML from disk, returns typed props |
| **Presentation primitives** | `dashboard_app/src/components/` | Stateless React components: `EmptyState`, `MarkdownSurface`, `LiveRefresh`, `MetricsDashboard`, `SidebarNav`, `MetricsSummaryCards`, `MetricsTrends`, `ArtifactCard`, `MetadataChips`, `EducationalPopover`, `AppHeader`, `PageShell`, `MarkdownToc` |
| **Diátaxis shells** | `dashboard_app/src/components/shells/` | Layout chrome wrapping `MarkdownSurface`: `ReferenceShell`, `ExplanationShell`, `DefaultShell`, `TutorialShell` (ordered step-rail), `HowToShell` (goal-banner), `ConceptsShell` (narrative + takeaway aside) |
| **Per-artifact renderers** | `dashboard_app/src/components/renderers/` | Five specialized components for artifact types: `MetricsViewRenderer`, `PlanViewRenderer`, `VerificationReportRenderer`, `IdeaGridRenderer`, `ArchitectureExplorerRenderer`; all accept `{body, surface?}` and gracefully degrade to `DefaultShell` on malformed input |
| **Renderer registry** | `dashboard_app/src/components/registry.ts` | `RENDERER_REGISTRY: Map<string, ComponentType<{body: string; surface?: ManifestSurface}>>` + `resolveRenderer(renderer?, diataxis?, contentType?)` — `renderer:` field is highest-priority key; preserves pre-existing diataxis/contentType fallback chain |
| **Viz components** | `dashboard_app/src/components/viz/` | Interactive: `DiagramFrame`, `DiagramModal`, `DecisionGraph`, `TrendChart`, `Sparkline`, `usePanZoom` |
| **Library utilities** | `dashboard_app/src/lib/`, `dashboard_app/src/server/` | Pure utilities: `markdown-headings.ts` (slugify, extractToc), `health-tone.ts` (metrics aggregation), `sidebar-signals.ts` (view-model for sidebar state), `normalize-svg.ts` (SVG attribute normalization) |
| **Chrome components** | `dashboard_app/src/components/chrome/` | `Chip`, `Tabs`, `ErrorState` |
| **Page routes** | `dashboard_app/src/app/<surface>/page.tsx` | 7 surface pages: `adrs`, `architecture`, `documentation`, `metrics`, `roadmap`, `sentinel`, `workshops` |

**Initial surface coverage:**

| Surface | Consumes | Implemented in |
|---|---|---|
| `plan_view` | `IMPLEMENTATION_PLAN.md` + `WIP.md` | `dashboard_app/src/components/renderers/plan-view.tsx` — derives step list from task items or H2/H3 headings |
| `adr_card` | `<NNN>-*.md` ADR + graph | `dashboard_app/src/app/adrs/` |
| `verification_report` | `VERIFICATION_REPORT.md` | `dashboard_app/src/components/renderers/verification-report.tsx` — scans for PASS/FAIL/WARN verdict badge |
| `architecture_explorer` | `DESIGN.md` + `architecture.md` + diagrams | **Pathway A (full page)**: `dashboard_app/src/app/architecture/` — interactive; **Pathway B (thin renderer)**: `src/components/renderers/architecture-explorer.tsx` — compact section nav + link-out |
| `traceability_matrix` | `traceability.yml` + spec | `dashboard_app/` (via `MarkdownSurface`) |
| `idea_grid` | `IDEA_PROPOSAL.md` + `IDEA_LEDGER_*.md` | `dashboard_app/src/components/renderers/idea-grid.tsx` — renders three status columns (Implemented/Pending/Discarded) from H2 sections |
| `metrics_view` | `METRICS_REPORT_*.json` | **Pathway A (full page)**: `dashboard_app/src/app/metrics/` — interactive dashboard; **Pathway B (thin renderer)**: `src/components/renderers/metrics-view.tsx` — summary cards + link-out |

**Adding a new component:** add a server view-model under `dashboard_app/src/server/view-models/`, a React component in `dashboard_app/src/components/`, and wire a page route under `dashboard_app/src/app/<surface>/page.tsx`. For content-typed rendering, register the component in `RENDERER_REGISTRY` keyed by its `diataxis:` value or content-type string. There is no `render(source_paths)` callable, no `__init__.ts`, and no top-level `dashboard_app/components/` directory — these do not exist in the as-built Next.js structure.

### Diátaxis-Typed Shells

The renderer registry (`dashboard_app/src/components/registry.ts`) maps `diataxis:` frontmatter values to shell components. The documentation page dispatches through it:

| `diataxis:` value | Shell | Status |
|---|---|---|
| `reference` | `ReferenceShell` — fixed ToC sidebar slot + dense-table styling | Implemented |
| `explanation` | `ExplanationShell` — wide prose column + "why this matters" aside slot | Implemented |
| `tutorial` | `TutorialShell` — ordered step-rail layout with left nav of H2 headings | Implemented |
| `how-to` | `HowToShell` — goal-first layout with goal banner and body | Implemented |
| `concepts` | `ConceptsShell` — narrative layout with key-takeaway aside | Implemented |
| *(fallback)* | `DefaultShell` — plain card wrapping `MarkdownSurface` | Implemented |

The MD body is rendered into the shell's content slot. **Same source, different cognitive ergonomics.** Other pages may dispatch through the registry but are not required to; the documentation page does.

### SVG and Diagram Rendering

Two embedding strategies apply depending on the context:

| Context | Strategy | Rationale |
|---|---|---|
| Committed Markdown (`.md` files) | Markdown image syntax `![alt](diagrams/<name>/rendered/<name>.svg)` | Renderer-agnostic; GitHub-renderable; renders correctly in react-markdown (the dashboard's renderer) — security posture: no raw-HTML re-parse step (rehype-raw stays out), but HAST-transform plugins (rehype-slug, rehype-autolink-headings) are compatible and in use. `<img>` in a `.md` body shows as literal text unless preprocessed via `MarkdownSurface`'s normalization helper. |
| Committed `.html` share-out files | `<img>` tag referencing `diagrams/<name>/rendered/<name>.svg` | HTML files allow raw tags; no react-markdown involved |
| Dashboard server (interactive surfaces) | Inline SVG via `dangerouslySetInnerHTML` or the `/api/diagram` route | Enables pan/zoom, node events, CSS interaction — only the dashboard server may use this pattern |

The dashboard server's `/api/diagram` route streams allowlisted SVGs from the project root. SVGs served through this route or injected inline in the React tree must be sanitized via `sanitize-html` (see `dashboard_app/src/server/diagrams/sanitize.ts`). Committed Markdown source never uses raw `<img>` — the `![alt](path)` convention stays.

The dashboard server's `MarkdownSurface` component strips YAML frontmatter (`---` blocks at the head of the document), strips `<!-- ... -->` comments, and normalises any stray raw `<img>` to markdown image syntax at render-time, providing a safety net for legacy `.md` files. Raw frontmatter, unparsed metadata blocks, and unstripped HTML comments must never appear in rendered dashboard surfaces — they are machine-oriented metadata, not part of the human-readable body. New commits always use `![alt](path)` directly.

### No JavaScript in Committed HTML

Committed `.html` files (share-out renders) are **declarative HTML + CSS + SVG only.** No `<script>` tags. No client-side fetch. No interactive widgets embedded in the HTML.

**Interactivity lives in the dashboard server:**

| Interaction | Mechanism |
|---|---|
| Filter / search | dashboard UI controls |
| Sort / re-order | dashboard tables with column sort |
| Export / copy | server-generated file exports and snippet copy controls |
| "Copy as prompt" pattern | dashboard action that writes to server state and displays a text snippet |
| Diff annotations / highlight | server-rendered HTML with a strict allowlist |

**Why:** two interaction layers (HTML JS + dashboard widgets) double maintenance and conflict over event handling. Pushing all interactivity to the dashboard server unifies the model.

### MD Inlining via the Dashboard Server

When a renderer needs to embed MD content inline, read it server-side using the project's file utilities:

```typescript
// dashboard_app/src/server/view-models/documentation.ts
import { readText } from "@/server/artifacts/files";

export async function getHowToViewModel(surface: string) {
  const raw = await readText(`docs/${surface}.md`);
  const { content, data: frontmatter } = parseFrontmatter(raw);
  return { body: content, frontmatter };
}
```

**Never:**

- Pre-bake MD content into the HTML at build time (creates a stale derivative; defeats the single-source rule).
- Fetch MD via client-side JavaScript at render time (fragile, breaks offline, security headaches).
- Copy MD prose into the renderer's source code (dual-maintenance burden).

The only allowed flow is: `MD on disk → dashboard server reads at view-time → renders into shell → user sees`.

### `doc_manifest.yaml` — the Entry-Point Spine

Each project ships a `.ai-state/doc_manifest.yaml` listing every doc surface with type, renderer, location, and relationships. The dashboard reads it on startup to build navigation. Schema lives in [`skills/doc-management/references/doc-manifest-schema.md`](../../skills/doc-management/references/doc-manifest-schema.md).

The manifest is **generated**, not hand-maintained — `scripts/build_doc_manifest.py` walks `docs/`, `.ai-state/`, `.ai-work/<active-slug>/` and emits the YAML.

### Sharability and File Layout

For pre-rendered share-out artifacts:

- `<file>.html` lives alongside `<file>.md` (same directory, parallel name).
- Pre-commit hook generates the HTML from MD source.
- `.gitattributes` marks `*.html` files as generated (so GitHub diff view collapses them by default).
- The MD always remains the canonical edit target; humans never edit the `.html` directly.

For dashboard-rendered artifacts:

- The dashboard is launched via `/dashboard` (delegates to `praxion-dashboard`).
- The same MD source feeds both human-via-dashboard and agent-direct-read.
- A "share" button in the dashboard page can export a snapshot HTML for one-time send-out.

### Runtime Constraints

Two operational invariants apply to every dashboard surface:

- **Narrow live refresh.** Live-refresh / polling MUST be confined to in-flight workshop surfaces or similarly narrow status views (e.g., `PROGRESS.md` while a pipeline is running). Full-dashboard polling, whole-route reload loops, or client refresh paths that invalidate unrelated read-mostly pages are prohibited. Most dashboard surfaces are read-mostly reference views; broad polling adds noise, load, and visual instability without improving operator value.
- **Empty-state degradation.** Every surface MUST handle missing or unreadable source artifacts gracefully. Pages MUST NOT crash on absent files that are legitimately sparse or ephemeral; they degrade to an informative empty/error state. `.ai-work/` directories disappear after cleanup, `.ai-state/` grows incrementally, and freshly-onboarded projects often start without the full artifact set.

### Authorship Boundary (Who Writes HTML?)

| Author | What they author |
|---|---|
| Skill / agent / convention authors | **MD only.** Never HTML. Frontmatter declares `diataxis:` and (optionally) `share_out: true`. |
| `dashboard_app/src/components/` maintainers | Renderer code (TypeScript + React). Components are reusable; one renderer serves N artifacts of the same type. |
| Pre-render hook (auto-generated) | `<file>.html` for `share_out: true` files. Never hand-edit the output. |
| User / dashboard user | Reads only. May export ad-hoc snapshots via dashboard "share" buttons. |

This is the same single-author-per-surface discipline already enforced for MD docs (per `rules/writing/readme-style.md`) — extended to the HTML layer.

### Scope: Canonical Surfaces, Not Ephemeral Output

The Authorship Boundary above governs **canonical, persistent human-facing surfaces** — the artifacts covered by the Hybrid Render Boundary, where an MD source of truth exists (or should exist) and must stay in sync with any HTML view. It does not extend to **ephemeral HTML explicitly requested by the user in-session** (e.g. "show me this as an HTML page/chart/table") that has no persistent MD counterpart. There, the responding agent may author HTML directly — there is no MD source for it to drift out of sync with, so the dual-maintenance risk this boundary exists to prevent does not apply.

Two conditions keep the exception from becoming a loophole:

- **No persistent MD backing.** If the content already exists (or should exist) as a canonical MD artifact, render *that* through the dashboard instead of hand-authoring a parallel HTML copy — the exception covers content with no MD source, not an escape hatch around one.
- **Not committed by default.** Ephemeral HTML lives inside `.ai-work/<task-slug>/` when a pipeline task slug is active — this narrows, but does not contradict, the global "temporary files in `tmp/`" convention: `.ai-work/` is already the documented ephemeral-pipeline-intermediates home (see `rules/swe/agent-intermediate-documents.md`), gitignored and cleaned up with the pipeline like every other ephemeral document there. Outside a pipeline (no active task slug), it falls back to plain `tmp/`. Either way it is uncommitted by default, so it carries none of the dual-maintenance burden this rule otherwise guards against; a mechanical pre-commit guard (`scripts/check_html_authorship.py`) backstops this by blocking any staged `.html` file that is neither an allowlisted standalone tool UI nor backed by a `share_out: true` MD sibling. If the user wants the output kept, that's a decision to make a canonical `share_out: true` MD-sourced artifact, not to leave an orphaned `.html` file outside the manifest.

**Promote durable learnings, not just the HTML.** An ephemeral artifact can still surface something worth keeping — a decision, a gotcha, a pattern. When it does, that content goes into the normal stateful home (`LEARNINGS.md`, an ADR, `.ai-state/DESIGN.md`) in MD form — the HTML itself stays disposable either way. Markdown-is-canonical holds even for content that started life as a one-off HTML answer.

For visual polish (palette, type scale, motion, accessibility), load `web-ui-design` — ad hoc HTML still owes the same visual-craft bar as the dashboard, it just skips the renderer-registry plumbing.

### Visual Style Defers to `web-ui-design`

This rule covers HTML *architecture* (Markdown-as-source-of-truth, no JS in committed HTML, server-only data access, renderer registry). It does **not** define visual style — color palette, typography scale, spacing rhythm, component density, motion timing, dark-mode handling, accessibility bar. Those live in [`skills/web-ui-design/SKILL.md`](../../skills/web-ui-design/SKILL.md) and its references. Authors working in `dashboard_app/` or producing `share_out: true` HTML defer to:

- **Design tokens** in `dashboard_app/src/app/tokens.css` — single source of truth for color, spacing, typography, radii, motion, z-index; never inline `style="..."` or hard-coded color literals
- **WCAG 2.2 AA** — 4.5:1 text contrast, 3:1 non-text, ≥24px touch targets, focus indicators, `prefers-reduced-motion`, `prefers-color-scheme: dark`
- **The five UI states** — Default / Loading / Empty / Error / Partial; every surface designs all five (the existing `Runtime Constraints` clause on empty-state degradation is one specific instance)
- **Motion timing** — 100–200ms micro-interactions, 200–300ms entrances; ease-out for entering, ease-in for leaving; never linear
- **Emoji and color discipline shared with Markdown** — same rules as [`skills/doc-management/references/advanced-markdown-patterns.md`](../../skills/doc-management/references/advanced-markdown-patterns.md) (*Emojis as Cognitive Anchors* and *Color & Visual Tone*): selective emoji use, no color-as-sole-signal, calm-not-exclamatory tone. The HTML render must respect the visual vocabulary of the Markdown source it's rendering.

**When to invoke which expertise:**

| Question | Where to look |
|---|---|
| Where does this rendering live in the architecture? (server vs client, MD vs HTML, dashboard vs share-out) | This rule |
| What should this look like? (palette, type scale, motion, accessibility) | `web-ui-design` skill |
| Structural design of a *new* dashboard surface, component family, or framework choice | `interface-designer` agent |
| Visual review of an *existing* dashboard surface or share-out | `doc-engineer` (loads `web-ui-design` on-demand) |

### Integration with `diagram-conventions.md`

The diagram source/render separation already established in [`diagram-conventions.md`](diagram-conventions.md) composes cleanly. For committed Markdown and HTML artifacts, SVG renders are embedded as `<img>` tags. When the dashboard server renders SVGs inline for interactive surfaces (e.g., `DiagramFrame`, `DecisionGraph`), the SVG source path still follows the `diagrams/<name>/rendered/<name>.svg` convention — only the delivery mechanism changes (route-served or inline-injected vs. `<img>` tag). The committed Markdown source never changes.

### Self-test Before Committing HTML-Layer Changes

- Did I author MD source first, with HTML rendering as a derived view?
- Did I check that no MD content is duplicated into HTML or TypeScript source?
- Did I use the renderer registry or an appropriate existing component from `dashboard_app/src/components/` rather than hand-authoring a one-off HTML page?
- For interactivity, did I use dashboard controls rather than HTML+JS?
- For MD content embedding, did I read the Markdown at view-time using `readText()` rather than pre-baking it into HTML?
- Did I add the new doc surface to `.ai-state/doc_manifest.yaml` (or trigger the generator that does)?
- For SVG in the dashboard server, did I sanitize via `sanitize-html` before injecting inline?
