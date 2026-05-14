---
id: dec-draft-aa2cbabc
title: LikeC4 feedback-loop modeling — multiple focused views, tagged edges, document-substrate handoffs
status: proposed
category: architectural
date: 2026-05-14
summary: Model the Praxion agent pipeline's two feedback loops (CIS forward, Rework backward) as tag-classified edges over a per-agent, per-document graph projected through multiple focused LikeC4 views rather than a single omnibus diagram; keep agent-to-agent communication routed through .ai-work/ document elements to match the coordination protocol's "agents communicate through shared documents, not direct invocation" rule.
tags: [architecture, likec4, c4-model, diagrams, feedback-loops, agent-pipeline, cis, rework]
made_by: agent
agent_type: systems-architect
branch: worktree-pipeline-loops-docs
pipeline_tier: standard
affected_files:
  - docs/diagrams/architecture/src/architecture.c4
  - docs/diagrams/architecture/rendered/agent_pipeline.svg
  - docs/diagrams/architecture/rendered/feedback_loops.svg
  - docs/diagrams/architecture/rendered/cis_loop_detail.svg
  - docs/diagrams/architecture/rendered/rework_loop_detail.svg
  - .ai-state/DESIGN.md
re_affirms: dec-164
---

## Context

The Praxion pipeline gained two substantive feedback loops in recent work:

1. **CIS (Continuous Improvement Signals)** — forward-feeding from researcher Hat 2 to architect disposition (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`).
2. **Verifier rework loop** — backward-feeding from verifier Phase 12.5 → orchestrator → rework worktrees → `/resume-rework` → systems-architect → re-pipeline.

A third local loop also exists: the interface-designer's one-round, orchestrator-mediated *challenge loop* between `INTERFACE_DESIGN.md § Architecture Challenges` and `SYSTEMS_PLAN.md`.

Before this pipeline, the LikeC4 model at `docs/diagrams/architecture/src/architecture.c4` was silent on:

- The forward agent pipeline (only abstract `orchestration.pipeline` existed; no per-agent elements)
- Agent-to-agent edges and document handoffs
- Either feedback loop
- The bidirectional shape of the pipeline overall

`.ai-state/DESIGN.md` §3 + §5 carried a rich narrative for the rework loop but no diagrammatic representation. `docs/architecture.md` §10 carried the rework loop's developer-facing description but no CIS coverage and no bidirectional visualization. Adding loop coverage to the model forces three coupled design decisions:

1. **Granularity** — promote individual agents to first-class addressable LikeC4 elements, or keep `orchestration.pipeline` opaque and model loops only at the layer level?
2. **View shape** — one omnibus view with every loop, or multiple focused views projecting subsets?
3. **Handoff representation** — model edges as agent-to-agent direct calls, or route through `.ai-work/` document elements?

The user explicitly authorized scope expansion: "redo properly as much as diagrams as you need beautifully designed and without restrictions in the number of components for the sake of clarity". This removes the artificial node-cap constraint that would otherwise bias toward (1) opaque pipeline + (2) single omnibus view.

## Decision

The LikeC4 model adopts three complementary modeling choices:

1. **Per-agent first-class elements.** Each pipeline agent (promethean, researcher, architect, interface-designer, context-engineer, planner, implementer, test-engineer, doc-engineer, verifier, sentinel, architect-validator, skill-genesis) and the orchestrator (main agent) are first-class `agent` elements inside `orchestration.pipeline`. This makes every pipeline view addressable down to the agent role while preserving the layer-cluster structure of L1 Components.

2. **Multiple focused views, each one concept per diagram.** Six views are projected from the single shared model:
   - `context` — L0 system boundary + external actors (kept from v1)
   - `components` — L1 layer-grouped components (kept from v1, lightly enriched with the orchestrator and ADR/ledger persistence subcomponents)
   - `agent_pipeline` — L2 forward flow only (linear shape; feedback edges excluded by tag filter)
   - `feedback_loops` — L2 pipeline + all three feedback edges in one view (the bidirectional-shape view)
   - `cis_loop_detail` — L2 CIS loop in isolation (researcher → architect → ADRs + tech-debt ledger)
   - `rework_loop_detail` — L2 rework loop in isolation (verifier → orchestrator → worktrees → /resume-rework → architect)
   
   No flat node cap (per `rules/writing/diagram-conventions.md`: LikeC4 + D2 architecture models are explicitly exempt). Each view is self-contained — a reader grasps it standalone — and shows one concept.

3. **Edges route through document elements.** Agent-to-agent communication is modeled as agent → document → agent rather than agent → agent. Pipeline documents (`IDEA_PROPOSAL.md`, `RESEARCH_FINDINGS.md`, `SYSTEMS_PLAN.md`, `INTERFACE_DESIGN.md`, `IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md`, `TEST_RESULTS.md`, `VERIFICATION_REPORT.md`, `REWORK_MANIFEST.md`, `VERIFIER_FINDINGS.md`, `CONTEXT_REVIEW.md`) are first-class `document` elements in the model. This matches the coordination contract: *"agents communicate through shared documents, not direct invocation"* (`rules/swe/swe-agent-coordination-protocol.md` Coordination Pipeline section). Edges carry verbs that match the document semantics (`writes`, `reads`, `updates`, `surfaces`, `disposes`, `dispatches`, `emits`, `flips`, `spawns`).

Three edge tags classify feedback-loop membership so views can filter:

- `forward` — primary forward flow
- `cis_loop` — Continuous Improvement Signals edges
- `rework_loop` — Verifier rework edges
- `challenge_loop` — Interface-designer one-round architecture challenge edges

The `agent_pipeline` view excludes everything except `forward`-tagged edges; the `feedback_loops` view includes all tags; the two `*_detail` views include only the relevant loop's tag.

## Considered Options

### Option A — Single omnibus view, opaque pipeline (status quo + loops bolted on)

Keep `orchestration.pipeline` as a single opaque component; add the two feedback loops as edges between layer-level components (e.g., `pipeline → pipeline` self-loop with a label). All flow visible in one diagram.

**Pros:**
- Minimal model change; one diagram to maintain
- Token-light for agent reads of the rendered SVG

**Cons:**
- Cannot show *which* agent participates in *which* loop (researcher, not "the pipeline", emits CIS)
- A self-loop on `pipeline` says nothing about the orchestrator's role in the rework loop
- Conflates forward flow with feedback, hiding the bidirectional shape
- Violates "one concept per diagram" — three flows mashed together

Rejected. The whole point of the work was to make the loops *legible*, not to add an edge label.

### Option B — Per-agent elements, multiple focused views, agent-to-agent edges (no document substrate)

Promote agents to first-class elements; project multiple views as in the chosen decision; but model edges directly agent-to-agent (e.g., `researcher → architect "surfaces CIS"`).

**Pros:**
- Visually simpler — fewer nodes per view
- Matches a casual reader's mental model of the pipeline

**Cons:**
- Contradicts the coordination contract — agents do *not* call each other; they exchange documents through `.ai-work/<task-slug>/`
- Hides the document handoff substrate which is itself architecturally load-bearing (subagent isolation, parallel-execution fragments, the entire reconciliation protocol)
- Future loops (e.g., when an unknown document mediates an unknown future feedback edge) would be impossible to introduce without breaking the agent-to-agent convention

Rejected. The document substrate *is* the architecture; hiding it for visual neatness erases what makes the pipeline reliable.

### Option C — Per-agent elements, multiple focused views, document-substrate edges (chosen)

The decision above. Combines per-agent first-class addressability, multiple focused views, and document-substrate edge routing.

**Pros:**
- Each loop has its own detail view that a reader can grasp standalone (`cis_loop_detail`, `rework_loop_detail`)
- The `feedback_loops` overlay view makes the bidirectional shape visually obvious in one frame
- The `agent_pipeline` view stays clean — feedback edges filtered out — for readers learning the forward flow first
- Document-substrate edges respect the coordination contract and surface the load-bearing handoff mechanism
- Tag-based filtering generalizes — future loops (e.g., context-engineer shadow review, doc-engineer parallel group) can be added with new tags without restructuring existing views

**Cons:**
- More nodes per view than Option A
- Six views to keep in sync (vs. two before) — but per `diagram-conventions.md` LikeC4 is exempt from the node cap and projects multiple views from one model anyway, so this is the intended use of the toolchain

### Option D — Multiple files, one model per loop

Split the LikeC4 source into multiple `.c4` files: one for context/components, one for the forward pipeline, one for CIS, one for rework. Use cross-file imports.

**Pros:**
- Maximum separation of concerns
- Each file is independently readable

**Cons:**
- LikeC4's cross-file model semantics add complexity for marginal benefit
- The forward pipeline and the feedback loops share most of their nodes — splitting them duplicates the agent + document inventory three ways
- `diagram-conventions.md` calls for one source file per `diagrams/<name>/` directory; splitting violates the convention

Rejected. LikeC4's view projection is the intended mechanism for separation; file-level split duplicates state.

## Consequences

**Positive:**

- The bidirectional shape of the pipeline is now visually obvious in `feedback_loops.svg`
- Each feedback loop has its own self-contained detail view that downstream readers (verifier, doc-engineer, sentinel) can reason about without loading the full model
- Per-agent addressability means future ADRs can pinpoint exactly which agent owns each edge (e.g., "the researcher's CIS surfacing obligation" not "the pipeline's CIS surfacing obligation")
- The document-substrate edges document the coordination contract directly in the model; if someone proposes a future agent-to-agent direct invocation, the model's edge-type catalog forces them to justify the deviation
- Tag-based filtering scales: a future doc-engineer-shadow loop or context-engineer-review loop can add a new tag without restructuring existing views
- The shared three-term disposition vocabulary (per `dec-179`) lets the `cis_loop_detail` and `rework_loop_detail` views use semantically identical edge labels for the same architectural answer (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`)

**Negative:**

- Model file grew from ~130 lines to ~270 lines — the marginal cost of multi-view projection
- Six rendered SVGs vs. two — `scripts/diagram-regen-hook.sh` regenerates all of them on every `.c4` change, which is correct but slightly slower
- Agent-element churn: when a new agent is added to the pipeline (e.g., a future test-orchestrator), the model has to be edited in two places — `knowledge.agents` (deployable count) and `orchestration.pipeline.<name>` (runtime instance) — matching the existing dual-representation pattern from `dec-164`

**Operational:**

- The architecture C4 dual-agent representation (`dec-164`) is re-affirmed: knowledge.agents stays the deployable family; orchestration.pipeline now contains the runtime per-agent instances, the orchestrator, and the document substrate
- The `aac-dac-conventions.md` fence convention applies: any rendered SVG embedded in `docs/architecture.md` or `.ai-state/DESIGN.md` under an `aac:generated` fence will pick up structural changes on regen; narrative remains authored
- Future feedback edges follow the same recipe: (1) tag the edge, (2) ensure source and target are first-class agent or document elements, (3) either add a new detail view or extend `feedback_loops`

**Verification:**

- `likec4 validate` passes cleanly on the new model
- All six rendered SVGs > 0 bytes, valid XML
- Every edge in the diagrams corresponds to behavior documented in either an agent definition (`agents/*.md`), the coordination protocol rule (`rules/swe/swe-agent-coordination-protocol.md`), or `.ai-state/DESIGN.md` §5 (verifier-rework-loop sub-section) and the new CIS sub-section

## Prior Decision

This decision re-affirms `dec-164` (Architecture C4 dual-agent representation) — the dual-representation pattern is the structural precondition that makes the per-agent elements in `orchestration.pipeline` coherent. `dec-164` established that authored agents (`knowledge.agents`) and runtime agents (`orchestration.pipeline`) are distinct conceptual entities linked by a "spawns" edge; this ADR extends that pattern downward: the runtime side now has per-agent children, and the document substrate is modeled alongside them.

Nothing in `dec-164` is contradicted. The decision space `dec-164` opened (runtime side can grow internal detail) is the space this ADR fills.

No prior decision is superseded.
