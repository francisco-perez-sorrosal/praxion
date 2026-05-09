---
diataxis: reference
audience: developer
---

# Praxion docs

Long-form documentation for humans navigating the project.

For agent-facing baseline (build/test/lint, conventions, agent reading order), see [`../CLAUDE.md`](../CLAUDE.md). For first-contact narrative and install, see [`../README.md`](../README.md).

The docs below are organized by [Diátaxis](https://diataxis.fr) quadrant — pick the section that matches what you're trying to do, not just the topic.

## Tutorials — learning by doing

Step-by-step walkthroughs to build skill. Read these front-to-back; expect to type along.

- [Getting started](getting-started.md) — first-time setup; build a small URL shortener through the full pipeline
- [Greenfield onboarding](greenfield-onboarding.md) — start a new project with Praxion (`new_project.sh` + `/new-project`)
- [Existing-project onboarding](existing-project-onboarding.md) — add Praxion to a project that already has code (`/onboard-project`)
- [ML training onramp](ml-training-onramp.md) — Praxion conventions for ML/AI training projects (`program.md`, GPU budget, experiment tracking)

## How-to guides — achieving a specific goal

Focused recipes assuming familiarity. Skim for the step you need.

- [Cursor compatibility](cursor-compat.md) — set up Praxion for Cursor in addition to Claude Code
- [External API docs](external-api-docs.md) — configure context-hub MCP for SDK/API references
- [Observability](observability.md) — wire up Phoenix telemetry for a managed project

## Reference — information lookup

Authoritative tables and schemas. Look up, don't read sequentially.

- [Architecture](architecture.md) — code-verified Praxion architecture (paths, components, dependencies)
- [Architecture diagrams](architecture-diagrams.md) — LikeC4 view catalog and regen workflow
- [Spec-driven development](spec-driven-development.md) — REQ ID conventions, traceability protocol, sentinel checks
- [Metrics schema](metrics/README.md) — `/project-metrics` JSON output schema and field reference

## Concepts — mental models (the why)

Discursive explanations of design decisions and ideas. Read for understanding, not action.

- [Concepts overview](concepts.md) — pipeline, learning loop, ecosystem-as-philosophy mapping
- [Decision tracking](decision-tracking.md) — ADR conventions, lifecycle, supersession, finalize protocol
- [Architecture-as-Code (AaC) and Documentation-as-Code (DaC)](aac-dac.md) — the toolchain and rationale for the LikeC4 + Diátaxis approach
- [Memory architecture](memory-architecture.md) — Praxion memory MCP design and lifecycle
- [Claude ecosystem learning resources](claude-ecosystem-learning-resources.md) — curated external links for Claude API/SDK/Code

## Diagrams

Diagram source files (Mermaid, LikeC4, D2) and rendered SVGs live under per-diagram subdirectories. See [`diagrams/README.md`](diagrams/README.md) for the convention and view catalog. Source-of-truth files are under `<doc-dir>/diagrams/<name>/src/`; rendered output sits in `<doc-dir>/diagrams/<name>/rendered/` and is what markdown embeds. The convention is codified in [`../rules/writing/diagram-conventions.md`](../rules/writing/diagram-conventions.md).

## Adding a new doc

1. Choose the Diátaxis quadrant (compass: action vs cognition × acquisition vs application — see <https://diataxis.fr/compass/>).
2. Add `diataxis:` and `audience:` YAML frontmatter at the top of the file.
3. Link it from this index under the matching quadrant.
4. If you add diagrams, follow [`diagrams/README.md`](diagrams/README.md) — source files in `diagrams/<name>/src/`, rendered in `diagrams/<name>/rendered/`.
