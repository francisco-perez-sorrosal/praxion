---
diataxis: reference
audience: developer
---

# Diagrams

Source files and rendered output for diagrams referenced from `docs/*.md`.

The convention is codified in [`../../rules/writing/diagram-conventions.md`](../../rules/writing/diagram-conventions.md): diagram source code (Mermaid `.mmd`, LikeC4 `.c4`, D2 `.d2`) lives in dedicated source files under `<diagram-name>/src/`; rendered output sits under `<diagram-name>/rendered/`; markdown embeds **only** the rendered `.svg`/`.png`. Inline ` ```mermaid `, ` ```c4 `, ` ```d2 ` blocks in committed docs are not allowed.

## View catalog

| Diagram | Source | Renders | Embedded in |
|---|---|---|---|
| `architecture/` | `src/architecture.c4` | `rendered/{context,components,index}.{d2,svg}` | [`../architecture.md`](../architecture.md), `.ai-state/DESIGN.md` |
| `aac-dac-feedback-loop/` | `src/aac-dac-feedback-loop.mmd` | `rendered/aac-dac-feedback-loop.svg` | [`../aac-dac.md`](../aac-dac.md) |
| `concepts-agent-pipeline/` | `src/concepts-agent-pipeline.mmd` | `rendered/concepts-agent-pipeline.svg` | [`../concepts.md`](../concepts.md) |
| `concepts-component-layers/` | `src/concepts-component-layers.mmd` | `rendered/concepts-component-layers.svg` | [`../concepts.md`](../concepts.md) |
| `getting-started-pipeline/` | `src/getting-started-pipeline.mmd` | `rendered/getting-started-pipeline.svg` | [`../getting-started.md`](../getting-started.md) |
| `sdd-stage-flow/` | `src/sdd-stage-flow.mmd` | `rendered/sdd-stage-flow.svg` | [`../spec-driven-development.md`](../spec-driven-development.md) |

## Regeneration

LikeC4 → D2 → SVG (committed alongside source):

```bash
likec4 gen d2 docs/diagrams/architecture/src -o docs/diagrams/architecture/rendered/
d2 docs/diagrams/architecture/rendered/context.d2 docs/diagrams/architecture/rendered/context.svg
d2 docs/diagrams/architecture/rendered/components.d2 docs/diagrams/architecture/rendered/components.svg
```

Mermaid → SVG:

```bash
mmdc -i docs/diagrams/<name>/src/<name>.mmd -o docs/diagrams/<name>/rendered/<name>.svg
```

The pre-commit hook (`scripts/diagram-regen-hook.sh`) regenerates LikeC4 outputs automatically when staged `.c4` files change. Mermaid currently regenerates on demand (no hook yet — see deferred TODO in `IMPROVEMENT_PLAN.md`).

## Tooling

- `mmdc` — `npm install -g @mermaid-js/mermaid-cli`
- `likec4` — `npm install -g likec4` (also available via Homebrew: `brew install likec4`)
- `d2` — `brew install d2` or see <https://d2lang.com>
