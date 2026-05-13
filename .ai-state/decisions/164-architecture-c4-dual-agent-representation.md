---
id: dec-164
title: Architecture C4 dual-agent representation (knowledge.agents + orchestration.pipeline)
status: accepted
category: architectural
date: 2026-05-13
summary: Dual-represent Agents in the LikeC4 model — authored Markdown family in the Knowledge layer (knowledge.agents) and the spawned-subprocess runtime in the Orchestration layer (orchestration.pipeline, renamed from orchestration.agents) — linked by a "spawns" edge.
tags:
  - architecture
  - likec4
  - layer-model
  - agents
  - documentation
made_by: user
agent_type: systems-architect
branch: main
pipeline_tier: standard
affected_files:
  - docs/diagrams/architecture/src/architecture.c4
  - docs/diagrams/architecture/rendered/components.d2
  - docs/diagrams/architecture/rendered/components.svg
  - .ai-state/DESIGN.md
  - docs/architecture.md
  - .ai-state/DESIGN_CHANGELOG.md
---

## Context

Praxion's LikeC4 architecture model, when authored at `docs/diagrams/architecture/src/architecture.c4`, placed Agents in the Orchestration layer only — alongside Hooks and `.ai-work/`. The Knowledge layer carried Skills, Rules, and Commands. On the rendered L1 components view this looked structurally clean, but the user observed that Agents were *missing* from the Knowledge cluster where they semantically sit alongside Skills / Rules / Commands as a deployable authoring surface — the `.md` family on disk under `agents/`, deployed by the same installers, edited by the same skill-/agent-/rule-/command-crafting workflow, and shaping runtime behavior via the same progressive-disclosure pattern.

The model was conflating two axes Praxion already operates on:

1. **Authorship axis** — `agents/*.md` is a knowledge surface. Each file is a *specification*: system prompt, tool/skill access, model tier, behavioral contract. It is on disk, version-controlled, deployed by installers, edited by users. From this axis it is a peer of `skills/*/SKILL.md`, `rules/**/*.md`, and `commands/*.md`.
2. **Runtime axis** — an *agent run* is a spawned subprocess with its own context window, executing one of those definitions. From this axis it is a peer of Hooks (lifecycle) and `.ai-work/` (ephemeral state).

A single `orchestration.agents` node could not honestly represent both. The asymmetry was particularly visible because installers deploy `agents/`, `skills/`, `rules/`, and `commands/` together (the same `install.sh` pass over `~/.claude/`), but the model only drew "deploys" edges from `tooling.installers` to `knowledge.{skills,rules,commands}` — not to agents.

The relaxed LikeC4 node ceiling (commit `cee12ed`) gave the model room for a structural fix without the previous tradeoff against view legibility.

## Decision

**Option C — Dual representation.**

In `docs/diagrams/architecture/src/architecture.c4`:

1. **Add `knowledge.agents`** — a `component "Agents"` sibling of `skills` / `rules` / `commands` inside the `knowledge` cluster. Description: `"Authored subprocess specifications"` — emphasizes that these are the `.md` files on disk under `agents/`, the same authoring surface as skills/rules/commands.

2. **Rename `orchestration.agents` to `orchestration.pipeline`** — keep it in the Orchestration cluster but reframe semantically as the runtime side. Description: `"Spawned subprocesses (runtime instances)"`.

3. **New linking edge** `knowledge.agents -> orchestration.pipeline "spawns"` — makes the relationship between the authored definition and its runtime instantiation explicit in the model.

4. **Retarget existing knowledge→runtime edges** to `orchestration.pipeline` (target rename — `skills` *injects*, `rules` *constrains*, `commands` *triggers* the runtime; they do not act on the authored definition family).

5. **New `tooling.installers -> knowledge.agents "deploys"` edge** — installers deploy the authored agent family alongside the other three knowledge surfaces.

6. **Internal Orchestration edges** retargeted: `orchestration.hooks -> orchestration.pipeline "enforces"`, `orchestration.pipeline -> orchestration.aiwork "reads/writes"`, `orchestration.pipeline -> persistence.aistate "persists"`.

The `components` view's `include` list is updated to reference the new node names.

The dual representation is documented in `.ai-state/DESIGN.md` §3 (as a `>` callout above the components table plus two table rows: "Agents (authored definitions)" and "Agent runtime / Pipeline") and in `docs/architecture.md` §3 (parallel two-row treatment with the same dual-representation framing). The image alt-text in `docs/architecture.md` is updated to mention the four Knowledge components and the `spawns` linking edge.

## Considered Options

### Option A — Keep `orchestration.agents`; add a note

Leave the model as-is and add an authored note (in `.ai-state/DESIGN.md`) explaining that `agents/` is also a knowledge surface.

- Pros: Zero diagram change. No regen needed.
- Cons: The model still misrepresents the structural reality. Future readers of the rendered view (anyone using the dashboard's Architecture surface, or any consumer of `components.svg`) get the wrong picture and the explanatory note may not be co-located with what they read. Installer-deploys edge for `agents/` cannot be drawn at all.

### Option B — Move `agents` into Knowledge only; remove from Orchestration

Treat Agents purely as a knowledge surface; let the runtime be implicit in Hooks + `.ai-work/`.

- Pros: Symmetric Knowledge cluster (four peers: skills/rules/commands/agents). One fewer node.
- Cons: The agent *runtime* is a load-bearing concept in Praxion — it's what the coordination protocol governs, what `.ai-work/<task-slug>/` exists to support, what Hooks fire against. Removing it from the diagram hides the most operationally significant element of the system. Edges like "agents persists to .ai-state" and "hooks enforces on agents" would have no source/target.

### Option C — Dual representation (chosen)

Knowledge layer holds the authored definitions; Orchestration layer holds the runtime; a "spawns" edge links them.

- Pros: Model faithfully represents both axes Praxion operates on. Installer-deploys edge for `agents/` is drawable. Runtime relationships (hooks-enforces, pipeline-persists, pipeline-reads/writes-aiwork) keep their semantic homes. View readers see Agents in the Knowledge cluster where they expect it AND see the runtime where execution belongs.
- Cons: Small uplift in cognitive cost — two related boxes instead of one. Requires a `likec4 gen d2` regen pass and an SVG rerender. Two table rows in each architecture doc instead of one. Mitigated by the `>` callout sentence in `.ai-state/DESIGN.md` §3 explaining the dual representation and the explicit cross-references between the two rows.

### Option D — Rename `knowledge` to something broader

Rename the Knowledge cluster to "Authored surfaces" or "Definitions" to make room for Agents without dual representation.

- Pros: Keeps a single `agents` node.
- Cons: "Knowledge layer" is the term the rest of the codebase uses (in `CLAUDE.md`, in skill descriptions, in the agent reading order). Renaming the cluster for diagram cosmetics propagates a rename burden through documentation that is not justified by the structural problem. And it still does not solve the runtime-vs-authorship conflation — the renamed cluster would still contain a node that means both things.

## Consequences

**Positive:**

- The model now distinguishes the two axes Praxion already operates on (authorship vs. runtime). Readers of the L1 components view get a structurally honest picture.
- Installer-deploys edge for `agents/` is now drawable, matching the on-disk installer behavior (same `install.sh` deploys all four knowledge surfaces).
- Runtime relationships (`hooks -> pipeline "enforces"`, `pipeline -> aistate "persists"`, etc.) sit cleanly in the Orchestration cluster where execution is the load-bearing concept.
- The `knowledge.agents -> orchestration.pipeline "spawns"` edge makes the authorship-to-runtime relationship a first-class element of the model — readers see *how* the two sides connect.

**Negative:**

- Small uplift in cognitive cost — readers see two related boxes ("Agents" in Knowledge, "Agent Pipeline" in Orchestration) and need to grok the dual representation. Mitigated by the explicit `>` callout in `.ai-state/DESIGN.md` §3 and by cross-references between the two table rows in both architecture docs.
- One-time regen cost: `likec4 gen d2 docs/diagrams/architecture/src -o docs/diagrams/architecture/rendered/` + `d2` rendering for `components.svg`. `context.{d2,svg}` and `index.{d2,svg}` are byte-identical to HEAD (the context view excludes layer internals).
- Two table rows in each of `.ai-state/DESIGN.md` §3 and `docs/architecture.md` §3 instead of one.

**Mitigations baked into this pass:**

- `>` callout sentence at the top of `.ai-state/DESIGN.md` §3 explicitly names the dual representation and points to this ADR.
- The `docs/architecture.md` image alt-text mentions the linking `spawns` edge so a text-mode reader sees the relationship without rendering the SVG.
- Each of the two table rows in each doc cross-references the other ("This row is the Orchestration-layer counterpart to the 'Agents (authored definitions)' Knowledge row" and vice versa).
