---
id: dec-439
draft_id: dec-draft-2fbfa6d3
title: A diagram element's category is its kind's `notation`, overridden by element `metadata { category }`; a token table gives each category a distinct non-colour mark
status: accepted
category: architectural
date: 2026-10-04
summary: "Published contract shipped in the onboarding style kit: categories resolve as kind notation unless the element declares metadata.category; the kit's kinds person/system/external/container/component/datastore carry notations Person/System in scope/External system/Container/Component/Data store; Praxion keeps its kinds and overrides its 20 component elements (Layer, Knowledge asset, Runtime agent, Pipeline document, Tooling, Persistent store); a command-owned token table (values per dec-444), optionally extended per project by style.json, gives every category a non-colour mark that is distinct within its vocabulary, plus AA contrast."
tags: [diagrams, c4, likec4, categories, style-kit, onboarding, data-structures, legend]
made_by: agent
agent_type: systems-architect
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - claude/aac-templates/likec4-style-kit.c4.tmpl
  - claude/aac-templates/likec4-example-model.c4.tmpl
  - docs/diagrams/architecture/src/_spec.c4
  - docs/diagrams/architecture/src/architecture.c4
  - scripts/regenerate_diagrams.py
  - skills/likec4-diagramming/SKILL.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-15]
dissent: "Re-kinding Praxion's components into knowledge/store/tooling/layer kinds would make the category a single-source property LikeC4's own UI and MCP preview also style, at the cost of teaching the projection check a few kind names."
---

## Context

Every rendered view must let a reader tell categories apart without colour, name them in a legend with exact names, and show a category line per element. Praxion's vocabulary is fixed: Person, System in scope, External system, Knowledge asset, Runtime agent, Pipeline document, Persistent store, Tooling. Onboarded projects get a floor: Person, System in scope, External system, Container, Component, Data store. The acceptance contract needs the model to record each element's category name in a readable place.

Praxion's `component` kind spans four categories (layers, knowledge assets, stores, tooling). Re-kinding them would touch `check_architecture_projection.py`, which parses kinds and binds the 16 §3a rows to `component` leaves, and the §3a contract text. It would also leave `orchestration.pipeline` and `orchestration.aiwork` without a natural kind.

## Decision

**Resolution rule:** category(e) = `e.metadata.category` when declared, else `notation` of `e.kind`. The renderer is the one parser:
- a kind without `notation` is an error;
- a duplicated `category` key (which LikeC4 merges into an array) is an error;
- a category with no token is an error.

**Kit (published):** the installed `_spec.c4` declares kinds with exact notations. A `datastore` kind supplies the Data store category.

**Praxion:** kinds are unchanged. Twenty `component` elements declare `metadata { category … }`:

| Elements | Category |
|---|---|
| Four layers | Layer (an added category) |
| `knowledge.*` | Knowledge asset |
| `orchestration.pipeline` | Runtime agent |
| `orchestration.aiwork` | Pipeline document |
| `hooks`, `chronograph`, `tooling.*` leaves | Tooling |
| `aistate`, `adrs`, `tdl` | Persistent store |

**Token table:** owned by the regeneration command. Values and marks are those of `dec-444` (interface designer). Within each vocabulary, box marks are pairwise distinct as the tuple (geometry, dash, stroke width, icon), and so are frame marks. Cross-vocabulary twins that never co-occur are allowed: Layer and Component are both double-border; Persistent store and Data store are both cylinder. The only icon is the Person glyph. Drawing class names are `category_<snake name>`.
- **Extension:** a project may add or recolour categories in `<diagram-dir>/style.json` (`schema: 1`). The renderer validates contrast and mark distinctness for every addition.
- **Native styling:** the kit's LikeC4-native kind styles use the same colours, checked by test.

## Considered Options

### Option 1: Kinds only (re-kind Praxion's components)

**Pros:**
- One source, closed by the parser.
- LikeC4's native UI, legend and MCP preview style every element.

**Cons:**
- `check_architecture_projection.py` must learn category kind names (a distant component gains category knowledge).
- The §3a "component element" contract changes.
- `pipeline` and `aiwork` need an extra "Component" category or contortions.

### Option 2: Kind notation + metadata override (chosen)

**Pros:**
- Kits and new models stay idiomatic (pure kinds).
- No other component changes.
- Category names are written in the model, readable by agents and by the acceptance driver.

**Cons:**
- Two sources with a precedence rule.
- Overridden elements render as plain `component` in LikeC4's native UI.

### Option 3: `category_<snake>` tags (proposed by the interface designer in a withdrawn sibling draft)

The proposal: one declared tag per category; kind-level where every element of a kind shares the category (`element agent { #category_runtime_agent }`), otherwise on the element; category name = the tag stem, with `_` read as a space and an initial capital.

**Pros:**
- No kind changes.
- Kind-level tags reach `export json` `elements[].tags` (confirmed on 1.56.0).
- Queryable through the LikeC4 MCP tag tools.
- A typo may be rejected if undeclared tags fail validation (unverified).

**Cons:**
- Zero or two category tags per element are representable, so they need an "Uncategorised" fallback and a check.
- The legend name comes from a naming convention instead of being stated.
- The kit would need both a kind-level tag and a `notation` to keep LikeC4's native legend.

Rejected in the architect's challenge round; the draft was deleted before finalize.

## Consequences

**Positive:**
- Every view's legend and category lines come from one rule.
- Managed projects get a ready, extensible vocabulary.
- The projection check and §3a are untouched.

**Negative:**
- LikeC4's native UI does not show Praxion's override categories.
- Adding a category means a token entry, which is validated.

## Disconfirmation

- **Falsifier:** authors in managed projects routinely need the override (a kind spanning categories) rather than declaring a kind, or the native-UI mismatch causes recurring review confusion.
- **Steelmanned runner-up:** kinds only. LikeC4's `notation` exists exactly to name an element type in the legend, and kind styles drive every LikeC4 surface (UI, MCP `preview-view`, VS Code preview). Re-kinding gives one source closed by the parser, with no precedence rule, and the projection check's change is a regex alternation plus a set constant.
- **Reversal trigger:** the falsifier fires, or the interactive LikeC4 site ships, which makes native styling a first-class surface. Then re-kind Praxion's components and teach the projection check the kinds.

Activation: fired — structural + published template + multiple plausible paths; lens set = Simplicity, Testability (Security, Performance n/a); convergence = stable.
