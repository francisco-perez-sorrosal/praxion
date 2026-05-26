# Project Exploration

Systematic methodology for understanding any unfamiliar software project — from a small CLI tool to a massive monorepo. Produces layered output from a quick executive summary through deep architecture dives, adapting analysis strategy to project size, type, and documentation quality.

## When to Use

- Joining a new project or codebase for the first time
- Producing a project overview or architecture understanding for a team
- Orienting before planning implementation work (pre-cursor to `software-planning`)
- Discovering doc-code drift (README claims vs. actual codebase state)
- Running a guided, interactive exploration session with a developer
- Before a roadmap audit (`roadmap-synthesis`) on an unfamiliar project

## Activation

Load explicitly with `project-exploration` or reference trigger phrases: joining a new project, exploring an unfamiliar codebase, project overview, architecture understanding, codebase orientation, codebase walkthrough, code exploration, project analysis, developer onboarding. The `/explore-project` command drives the workflow interactively.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: project characterization dimensions, four-phase analysis framework, executive summary template, guided exploration protocol, adaptation rules |
| `README.md` | This file — overview and usage guide |
| `references/analysis-checklists.md` | Detailed per-phase checklists with specific files, patterns, and tool invocations |
| `references/framework-signatures.md` | Recognition patterns for common frameworks organized by language ecosystem |
| `references/architecture-patterns.md` | Architecture pattern identification guide with Mermaid diagram templates |

## Quick Start

1. **Characterize the project** — detect ecosystem (scan config files), size (file count), type (web app / CLI / library / etc.), and documentation quality
2. **Phase 1 — First Impressions** — read README, CLAUDE.md, top-level structure, recent git history
3. **Phase 2 — Architecture Discovery** — identify entry points, module boundaries, data flow; produce a Mermaid diagram
4. **Phase 3 — Development Workflow** — discover build, test, lint commands; CI/CD pipeline; git conventions
5. **Phase 4 — Deep Dives** (on request) — focused exploration of a specific module, data model, API surface, or security model
6. **Output** — fill the executive summary template; flag doc-code discrepancies prominently

For guided/interactive mode: run `/explore-project guide` and present one phase at a time, waiting for developer direction.

## Related Skills

- [`roadmap-synthesis`](../roadmap-synthesis/) — lens-based audit to produce a `ROADMAP.md`; run after exploration to apply findings
- [`software-planning`](../software-planning/) — plan implementation steps once the project is understood
