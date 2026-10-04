# Architecture

<!-- Design-target architecture document. Abstracts above concrete code to define the space of valid
     implementations. Component names may be abstract; file paths are illustrative; planned components
     are included with Status markers. For code-verified developer navigation, see docs/architecture.md.
     Maintained by pipeline agents via section ownership.
     Created by systems-architect, updated by implementer, validated by verifier/sentinel.
     See skills/software-planning/references/architecture-documentation.md for the full methodology. -->

## 1. Overview

| Attribute | Value |
|-----------|-------|
| **System** | [Project name] |
| **Type** | [e.g., Web application, CLI tool, Library, API service] |
| **Language / Framework** | [e.g., Python 3.13 / FastAPI] |
| **Architecture pattern** | [e.g., Layered, Hexagonal, Microservices, Monolith] |
| **Source stage** | [Phase 5 creation / Step N update / Pipeline `<slug>`] |
| **Current as of** | [dec-NNN — authored high-water mark; asserted YYYY-MM-DD. Advance only after considering every architecture-bearing decision up to this id (folded in or judged not applicable). See "Checkpoint" in skills/software-planning/references/architecture-documentation.md] |
| **Last verified** | [YYYY-MM-DD by agent or human] |

[One paragraph describing the system's purpose and high-level architectural approach.]

## 2. System Context

<!-- L0 diagram: system boundary + external actors/dependencies. No flat node cap: nest, and
     project focused views that pass the review checks of the `likec4-diagramming` skill.
     Shows WHAT interacts with the system, not internals.
     May include planned external integrations with a note.
     Cross-reference docs/architecture.md for code-verified component details.
     This file lives in .ai-state/, so embeds climb to ../docs/diagrams/...;
     alt text is the view title plus its C4 type. -->

![System Context, C4 system context view](../docs/diagrams/architecture/rendered/context.svg)

> **Component detail:** [Components](#3-components)

## 3. Components

<!-- L1 diagram: major building blocks and their relationships. No flat node cap for a
     LikeC4 view (rules/writing/diagram-conventions.md): a model that outgrows a legible
     view gains structure and focused projections, not fewer elements.
     Dual ownership: systems-architect writes the skeleton, implementer fills as-built details.
     Status values: Designed (interface defined, not yet implemented), Built (code exists on disk),
     Planned (roadmap item, no interface yet), Deprecated (scheduled for removal). -->

![Components, C4 component view](../docs/diagrams/architecture/rendered/components.svg)

<!-- aac:generated source=docs/diagrams/architecture/src/architecture.c4 view=components last-regen=YYYY-MM-DD -->

<!-- TWO-TIER SECTION. 3a holds structural building blocks -- one row per `component`
     element in the LikeC4 model above. Population follows the model, not a node
     budget, so the row count is however many `component` elements exist.
     3b holds capabilities: cross-cutting features and loops COMPOSED FROM those blocks,
     owning no single directory and no model element.
     Keep them apart from the first row. A single merged table grows without bound as
     features land, until the table silently contradicts the diagram above it -- and
     nothing can be reconciled against the model any more. Consumers that read
     *components* (AC06) resolve against 3a only. -->

### 3a. Structural components

| Component | Responsibility | Status | Key Files |
|-----------|---------------|--------|-----------|
| [Component A] | [What it does] | Built | `src/component_a/` |
| [Component B] | [What it does] | Built | `src/component_b/` |
| [Component C] | [What it does] | Designed | `src/component_c/` |

### 3b. Capabilities

| Capability | Responsibility | Status | Key Files |
|-----------|---------------|--------|-----------|
| [Capability A] | [Cross-cutting feature composed from the components above] | Built | `src/a/`, `src/b/` |

<!-- aac:end -->

## 4. Interfaces

<!-- Key APIs, contracts, and integration points between components.
     Dual ownership: systems-architect documents design-time contracts,
     implementer updates as-built details.
     Focus on boundaries that other components or external systems depend on. -->

| Interface | Type | Provider | Consumer(s) | Contract |
|-----------|------|----------|-------------|----------|
| [e.g., REST API] | HTTP | [Component A] | [External clients] | [e.g., OpenAPI spec at docs/api.yaml] |
| [e.g., Event bus] | Async | [Component B] | [Component C] | [e.g., JSON schema at schemas/events/] |

## 5. Data Flow

<!-- How data moves through the system for key scenarios.
     Use sequence diagrams for request flows, flowcharts for data pipelines.
     Focus on the 2-3 most important scenarios, not exhaustive coverage. -->

### [Primary Scenario Name]

![Sequence diagram example — User → Component A → Component B → Database, then response back through the chain](../docs/diagrams/architecture-template-sequence-example/rendered/architecture-template-sequence-example.svg)

## 6. Dependencies

<!-- External dependencies the system relies on.
     Dual ownership: systems-architect lists initial dependencies,
     implementer updates as dependencies are added/removed.
     May include planned dependencies with a note. -->

| Dependency | Version | Purpose | Criticality |
|-----------|---------|---------|-------------|
| [e.g., PostgreSQL] | [17.x] | [Primary data store] | Critical |
| [e.g., Redis] | [7.x] | [Caching layer] | Non-critical (degrades gracefully) |

## 7. Constraints

<!-- Known limitations, performance boundaries, quality attributes, and compatibility requirements.
     Type: Performance, Security, Compatibility, Regulatory, Technical, Quality. -->

| Constraint | Type | Rationale |
|-----------|------|-----------|
| [e.g., Response time < 200ms for API endpoints] | Performance | [User experience requirement] |
| [e.g., Must run on Python 3.11+] | Compatibility | [Minimum supported runtime] |
| [e.g., All data at rest must be encrypted] | Security | [Compliance requirement] |

## 8. Decisions

<!-- Architectural decisions are recorded as ADRs in .ai-state/decisions/.
     This section is a single pointer — the canonical, auto-generated index lives in
     .ai-state/decisions/DECISIONS_INDEX.md. Do NOT duplicate ADR titles or summaries here:
     summaries drift, indexes regenerate. Inline `dec-NNN` references in the section bodies
     above (Components, Interfaces, Constraints) are validated by sentinel AC04. -->

<!-- aac:authored owner=systems-architect last-reviewed=YYYY-MM-DD -->

Architectural decisions are recorded as ADRs in [`.ai-state/decisions/`](decisions/). The canonical, auto-generated cross-reference is [`DECISIONS_INDEX.md`](decisions/DECISIONS_INDEX.md). In-flight pipeline ADRs live as fragments under [`decisions/drafts/`](decisions/drafts/) and are promoted to stable `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`.

<!-- aac:end -->
