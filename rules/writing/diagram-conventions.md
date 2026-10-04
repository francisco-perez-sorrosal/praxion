---
paths:
- docs/**
- README.md
- '**/README.md'
- '**/DESIGN.md'
- '**/SYSTEM_DEPLOYMENT.md'
- .ai-state/**
- '**/IDEA_PROPOSAL.md'
- '**/RESEARCH_FINDINGS.md'
- '**/SYSTEMS_PLAN.md'
- '**/IMPLEMENTATION_PLAN.md'
- '**/*.c4'
core: false
---

## Diagram Conventions

### Source / Rendered Separation (mandatory)

Diagram **source code** (Mermaid `.mmd`, LikeC4 `.c4`, D2 `.d2`) lives in dedicated source files. Markdown documentation embeds **only the rendered output** (`.svg` / `.png`). Inline ` ```mermaid `, ` ```c4 `, and ` ```d2 ` code blocks are not permitted in committed documentation.

**Per-diagram directory layout** — for any markdown file `<doc>` that contains diagrams, source and renders live under a `diagrams/` sibling directory, organized per-diagram:

```
<doc-tree>/
  <doc>.md                            # embeds rendered output
  diagrams/
    <diagram-name>/                   # one directory per diagram
      src/
        <diagram-name>.mmd            # Mermaid source (or .c4 / .d2)
      rendered/
        <diagram-name>.svg            # rendered output, committed
        <diagram-name>.png            # optional alternate format
```

For LikeC4 sources that compile to multiple views, all views render into the same `rendered/` dir alongside the single `src/<name>.c4` source.

**Embedding in markdown:**

```markdown
![Architecture L0 — context](diagrams/architecture/rendered/context.svg)
```

**Use markdown image syntax `![alt](path)` — never a raw `<img>` tag — in committed `.md` files.** Raw `<img>` is reserved for committed `.html` share-out renders. (`react-markdown`, the dashboard's renderer, escapes raw HTML; a `<img>` in a `.md` body shows as literal text.)

Use a descriptive alt-text — it serves both accessibility and the agent's text-mode read.

**Dashboard server exception:** The `![alt](path)` embedding rule applies to committed Markdown artifacts; the `<img>` tag applies to committed `.html` share-out artifacts. The dashboard server may rewrite those refs to its `/api/diagram` route or render SVGs inline for interactive surfaces (e.g., `DiagramFrame`, `DecisionGraph`) — provided the SVG source path follows the `diagrams/<name>/rendered/<name>.svg` convention. The committed Markdown source never changes.

**Rationale:**

- **Renderer-agnostic** — any markdown viewer shows the figure (no Mermaid plugin required); the dashboard's documentation page renders trivially
- **Token-efficient for agents** — diagram source is heavy; rendered SVGs are invisible to a text-mode agent read of the doc
- **Editable in place** — source files open in any editor with proper diagram tooling (LikeC4 LSP, mermaid-cli watch, etc.)
- **Reusable** — one source can render into multiple outputs (`.svg` + `.png` + `.pdf`)
- **PR-reviewable** — image diff in PR review surfaces structural changes more visibly than source-line diff

### Toolchain Selection

| Need | Toolchain | Source extension | Render command |
|------|-----------|------------------|----------------|
| Multi-view C4 architecture (System Context L0, Container/Component L1+) | LikeC4 → D2 → SVG | `.c4` | `python3 scripts/regenerate_diagrams.py` |
| Single architectural view, sequence, state, ER, flowchart, process | Mermaid | `.mmd` | `mmdc -i src/<name>.mmd -o rendered/<name>.svg` |
| Layout-only diagrams not in C4 vocabulary | D2 (direct) | `.d2` | `d2 src/<name>.d2 rendered/<name>.svg` |

No other diagram format (ASCII art, PlantUML, hand-drawn-image embeds) is acceptable for committed documentation.

**When in doubt:** if the diagram is one of multiple views over a shared architectural model, use LikeC4. Otherwise use Mermaid.

### Migration of legacy inline diagrams

Existing inline ` ```mermaid `, ` ```c4 `, and ` ```d2 ` blocks must be migrated when their host doc is touched for any other reason — the cost is paid once, the next reader sees the new convention. Frozen historical artifacts (finalized ADRs, archived sentinel reports, archived specs) are exempt: their inline diagrams are factual history and stay in place.

### Clarity First

- **Node budget — advisory per-view heuristic**: a Mermaid flowchart or sequence should target **~10-12 nodes per view** — its auto-layout degrades past that; group related items into a parent subgraph when you would exceed it. **LikeC4 and D2 architecture models are exempt from a flat node cap** — they nest (groups, boundaries) and project several focused views from one model. Author the full model; project views that each stay legible. The binding checks for LikeC4 views are in the linked list below.
- **One concept per diagram** — if a diagram explains both data flow and component hierarchy, split it into two
- **Every arrow must be verifiable** against actual code — diagrams are claims about the system, not decorations

### LikeC4 views

A LikeC4 view is held to the review checks, each decidable from the model, the render's markup or a command's output: title with subject and C4 type; legend; element content (name, category or technology, responsibility); arrow intent and direction; categories told apart without colour; contrast; legibility at the reference embed width; proportions and arrow fan-in; one abstraction level; render agreement with a fresh regeneration. Read the project's `_spec.c4` style kit before editing a `.c4`, apply every check to each view you touch, and record any check you could not run. Thresholds and pass conditions live only in the [review checks of the `likec4-diagramming` skill](../../skills/likec4-diagramming/references/review-checks.md); the skill carries the authoring loop.

### Diagram Type Selection

| Need | Type | Toolchain / Keyword |
|------|------|---------------------|
| Multi-view C4 architecture | LikeC4 model + view projections | `.c4` + generated `.d2`/`.svg` |
| Component relationships, architecture | Flowchart | `graph TD` or `graph LR` |
| Request/response flows, protocols | Sequence | `sequenceDiagram` |
| Data models, class relationships | Class | `classDiagram` |
| Database schemas | ER | `erDiagram` |
| Lifecycle, workflow states | State | `stateDiagram-v2` |
| Process timelines | Gantt | `gantt` |

Use `graph TD` (top-down) for hierarchies and `graph LR` (left-right) for pipelines and flows.

### Styling Consistency

- **Subgraphs** for logical grouping (layers, bounded contexts, deployment units)
- **Standard node shapes**: rectangles for components, `[(Database)]` for storage, `([Queue])` for message systems, `{{Decision}}` for decision points
- **Edge conventions**: solid arrows (`-->`) for direct dependencies, dotted arrows (`-.->`) for async/event-based, labeled edges (`-->|label|`) when the relationship type is not obvious
- **No inline HTML styling** — rely on Mermaid's native syntax for readability across renderers
- **Labels over IDs** — use `A[Auth Service]` not bare `A`; the diagram must read without a legend

### When NOT to Diagram

- Simple lists or hierarchies that a bullet list conveys equally well
- One-to-one relationships that a sentence explains clearly
- Diagrams that duplicate what the code structure already shows (e.g., a file tree)
