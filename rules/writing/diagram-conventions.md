---
paths:
  - "**/*.md"
---

## Diagram Conventions

All diagrams in project documentation use **Mermaid** syntax. No other diagram format (ASCII art, PlantUML, embedded images of hand-drawn diagrams) is acceptable for committed documentation.

### Clarity First

- **10-12 nodes maximum** per diagram — group related items into their parent module when exceeding this
- **One concept per diagram** — if a diagram explains both data flow and component hierarchy, split it into two
- **Every arrow must be verifiable** against actual code — diagrams are claims about the system, not decorations

### Decomposition Strategy

When a system has more than 12 components, use layered decomposition:

- **L0 — Context**: System boundary + external actors. Shows what interacts with the system, not internals
- **L1 — Components**: Major building blocks and their relationships. The default level for architecture documentation
- **L2 — Internals**: Detail view of one L1 component. Only create when that component's internal structure matters to the reader

Each level must be self-contained — a reader should understand L1 without needing L2. Label diagrams with their level when multiple levels coexist in the same document.

### Diagram Type Selection

| Need | Type | Mermaid Keyword |
|------|------|-----------------|
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
