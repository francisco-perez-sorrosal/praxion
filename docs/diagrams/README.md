---
diataxis: reference
audience: developer
---

# Diagrams

Source files and rendered output for diagrams referenced from `docs/*.md`.

The convention is codified in [`../../rules/writing/diagram-conventions.md`](../../rules/writing/diagram-conventions.md): diagram source code (Mermaid `.mmd`, LikeC4 `.c4`) lives in dedicated source files under `<diagram-name>/src/`; rendered output sits under `<diagram-name>/rendered/`; markdown embeds **only** the rendered `.svg`/`.png`. Inline ` ```mermaid `, ` ```c4 `, ` ```d2 ` blocks in committed docs are not allowed.

## View catalog

### Architecture views (LikeC4)

`architecture/` holds the Praxion model in `src/architecture.c4` and one render per view in `rendered/`, each as `<view>.svg` with its intermediate `<view>.d2`. Documents embed the `.svg`.

| View | Title | C4 type | Render | Embedded in |
|---|---|---|---|---|
| `index` | Praxion in its context | System Context | `rendered/index.svg` | [`DESIGN.md`](../../.ai-state/DESIGN.md) |
| `components` | Praxion's building blocks | Container | `rendered/components.svg` | [`../architecture.md`](../architecture.md), [`DESIGN.md`](../../.ai-state/DESIGN.md) |
| `knowledge_components` | Knowledge layer | Component | `rendered/knowledge_components.svg` | [`../architecture.md`](../architecture.md) |
| `orchestration_components` | Orchestration layer | Component | `rendered/orchestration_components.svg` | [`../architecture.md`](../architecture.md) |
| `persistence_components` | Persistence layer | Component | `rendered/persistence_components.svg` | [`../architecture.md`](../architecture.md) |
| `tooling_components` | Tooling layer | Component | `rendered/tooling_components.svg` | [`../architecture.md`](../architecture.md) |
| `agent_pipeline` | Agent pipeline, ideation to design | Component | `rendered/agent_pipeline.svg` | [`../architecture.md`](../architecture.md) |
| `agent_pipeline_plan` | Agent pipeline, acceptance tests and plan | Component | `rendered/agent_pipeline_plan.svg` | [`../architecture.md`](../architecture.md) |
| `agent_pipeline_build` | Agent pipeline, plan to build | Component | `rendered/agent_pipeline_build.svg` | [`../architecture.md`](../architecture.md) |
| `agent_pipeline_verify` | Agent pipeline, verification | Component | `rendered/agent_pipeline_verify.svg` | [`../architecture.md`](../architecture.md) |
| `supporting_agents` | Shadow and gated agents | Component | `rendered/supporting_agents.svg` | — |
| `independent_agents` | Independent and post-pipeline agents | Component | `rendered/independent_agents.svg` | — |
| `feedback_loops` | Feedback loops | Component | `rendered/feedback_loops.svg` | [`../architecture.md`](../architecture.md) |
| `challenge_loop_detail` | Challenge loop | Component | `rendered/challenge_loop_detail.svg` | — |
| `cis_loop_detail` | Continuous improvement signals loop | Dynamic | `rendered/cis_loop_detail.svg` | [`../architecture.md`](../architecture.md) |
| `rework_loop_detail` | Rework loop | Dynamic | `rendered/rework_loop_detail.svg` | [`../architecture.md`](../architecture.md) |

### Other diagrams (Mermaid)

| Diagram | Source | Renders | Embedded in |
|---|---|---|---|
| `aac-dac-feedback-loop/` | `src/aac-dac-feedback-loop.mmd` | `rendered/aac-dac-feedback-loop.svg` | [`../aac-dac.md`](../aac-dac.md) |
| `concepts-agent-pipeline/` | `src/concepts-agent-pipeline.mmd` | `rendered/concepts-agent-pipeline.svg` | [`../concepts.md`](../concepts.md) |
| `concepts-component-layers/` | `src/concepts-component-layers.mmd` | `rendered/concepts-component-layers.svg` | [`../concepts.md`](../concepts.md) |
| `getting-started-pipeline/` | `src/getting-started-pipeline.mmd` | `rendered/getting-started-pipeline.svg` | [`../getting-started.md`](../getting-started.md) |
| `hackathon-spine/` | `src/hackathon-spine.mmd` | `rendered/hackathon-spine.svg` | [`../architecture.md`](../architecture.md) |
| `rework-dispatch/` | `src/user-flow.mmd` | `rendered/user-flow.svg` | [`../rework-dispatch.md`](../rework-dispatch.md) |
| `sdd-stage-flow/` | `src/sdd-stage-flow.mmd` | `rendered/sdd-stage-flow.svg` | [`../spec-driven-development.md`](../spec-driven-development.md) |
| `skill-genesis-harvest/` | `src/skill-genesis-harvest.mmd` | `rendered/skill-genesis-harvest.svg` | [`../skill-genesis.md`](../skill-genesis.md) |

## Regeneration

LikeC4 renders, from the repository root with the pinned `likec4` and `d2`:

```bash
python3 scripts/regenerate_diagrams.py            # write every render in place
python3 scripts/regenerate_diagrams.py --check    # byte-compare and run the review checks
```

Mermaid → SVG:

```bash
mmdc -i docs/diagrams/<name>/src/<name>.mmd -o docs/diagrams/<name>/rendered/<name>.svg
```

The pre-commit hook (`scripts/diagram-regen-hook.sh`) regenerates and stages the LikeC4 renders when a `.c4` file is staged, and CI fails when the committed renders differ from the model. Mermaid has no auto-regen hook yet — invoke `mmdc` manually after editing a `.mmd` source. The full how-to, with the pinned install lines, is [`../architecture-diagrams.md`](../architecture-diagrams.md).

## Tooling

- `mmdc` — `npm install -g @mermaid-js/mermaid-cli`
- `likec4` and `d2` — pinned versions and install lines in [`../architecture-diagrams.md`](../architecture-diagrams.md)
