---
id: dec-207
title: Architect Phase 2.5 Pre-Refactor Sub-Pipeline — bundled architecture decision
status: accepted
category: architectural
date: 2026-05-27
summary: Adds a Phase 2.5 (Pre-Refactor Assessment) to the architect, an artifact-driven in-worktree mini sub-pipeline, a new post-refactor-adaptation re-entry mode, and a verifier scope-switch — all reusing existing primitives (artifact-presence trigger, prompt-directive mode signaling, Conversation Checkpoint, in-place td-NNN status flips) without expanding the four-writer ledger policy.
tags: [agent-pipeline, refactoring, tech-debt-ledger, orchestrator-mediation, sentinel-gate, architecture]
made_by: agent
agent_type: systems-architect
branch: worktree-architect-pre-refactor
pipeline_tier: standard
affected_files:
  - agents/systems-architect.md
  - agents/CLAUDE.md
  - agents/README.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - agents/sentinel.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-intermediate-documents.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/references/tech-debt-ledger.md
  - skills/refactoring/SKILL.md
  - claude/config/CLAUDE.md.tmpl
  - claude/canonical-blocks/agent-pipeline.md
  - commands/onboard-project.md
  - commands/resume-rework.md
  - .ai-state/DESIGN.md
affected_reqs:
  - REQ-01
  - REQ-02
  - REQ-03
  - REQ-04
  - REQ-05
  - REQ-06
  - REQ-07
  - REQ-08
  - REQ-09
  - REQ-10
  - REQ-11
  - REQ-12
  - REQ-13
  - REQ-14
  - REQ-15
  - REQ-16
  - REQ-17
  - REQ-18
---

## Context

The architect today produces `SYSTEMS_PLAN.md` whose `§ Codebase Readiness § Prerequisites` is the lone landing zone for *all* preparatory refactor work, regardless of magnitude. For trivial refactors (1–3 files, a rename, a helper extraction) this is right-sized. For substantive refactors (4+ files, multi-commit, behavior-preserving but high-blast-radius, characterization-tests required) the line silently overflows: the architect designs the feature *against the un-refactored shape*, the planner inherits a Prerequisites bullet that maps to a hidden multi-step refactor, and the implementer either bundles the refactor into feature commits (losing reviewability) or re-negotiates module locations mid-feature (losing the architect's mental model).

Two existing orchestrator-mediated patterns demonstrate the shape of the solution:

- **Pattern A** — interface-designer challenge loop (`agents/interface-designer.md`, `coordination-details.md` §Architecture-Challenge Loop): same-worktree, one-cycle architect re-evaluation triggered by a non-empty `## Architecture Challenges` section; orchestrator mediates; user has final say on non-convergence.
- **Pattern B** — verifier rework loop (`agents/verifier.md` Phase 12.5): per-row-worktree sub-pipeline triggered by `REWORK_MANIFEST.md` presence; orchestrator dispatches via `EnterWorktree`; tech-debt `td-NNN` rows flipped `open → in-flight` at row creation and `→ resolved` at merge.

Neither pattern fits directly: Pattern A has no work-execution semantics; Pattern B's per-row-worktree topology is wrong because a pre-refactor is structurally a *prerequisite* of the parent task, not an alternative branch.

Additionally, the architect's relationship to the tech-debt ledger today is consumer-only (`agents/systems-architect.md` Phase 7 line 184 — "permission, not obligation; address items where natural by updating status in place; do not create rows"). Any redesign must honor the four-writer policy (`skills/software-planning/references/tech-debt-ledger.md:11-17` — verifier, sentinel, orchestrator, architect-validator only).

Finally, the architect operates in three implicit invocation contexts: feature-scope (Standard/Full pipelines), baseline-audit (`/onboard-project` Phase 8 — explicit "no SYSTEMS_PLAN.md, no invented components, no L2 detail, no source edits"), and now a needed third context where the architect re-enters *after* a mini-pipeline to adapt the feature design to the refactored codebase shape.

This decision bundles the architectural choices because the four sub-decisions share one constraint set — they all govern how Phase 2.5's artifact, the mini-pipeline, the re-entry mode, and the verifier coordinate — and splitting them into four ADRs would obscure the interlocking nature of the design (per the M2-six-axis-bundle pattern: when N coupled axes share a constraint set, one bundled ADR beats N fragments).

## Decision

Add a Phase 2.5 (Pre-Refactor Assessment) to the systems-architect's process that:

1. **Always runs in Standard/Full pipelines unless the mode is `baseline-audit` or `post-refactor-adaptation`** (REQ-01, REQ-06)
2. **Emits one of four outcomes** — `no-refactor`, `fold-into-Prerequisites`, `emit-PRE_REFACTOR_PLAN`, `rescope-and-restart` (REQ-02, REQ-04, REQ-05)
3. **Writes an ephemeral `.ai-work/<task-slug>/PRE_REFACTOR_PLAN.md` artifact** when the outcome is `emit-PRE_REFACTOR_PLAN`, with eight required sections including YAML blocks for `## Verifier Bypass Criteria` and `## Loop-Back Conditions` (REQ-03)
4. **Triggers an in-worktree mini sub-pipeline** (planner → test-engineer characterization first → implementer ∥ test-engineer → optional verifier) via artifact-presence orchestrator detection (REQ-07, REQ-10, REQ-11, REQ-12)
5. **Uses the existing `[Phase: Refactoring]` tag** for the planner's steps; no new tag (REQ-11)
6. **Has the verifier scope-switch to `PRE_REFACTOR_PLAN.md § Acceptance Criteria`** when in pre-refactor mode (detected by artifact presence + absence of feature-AC in SYSTEMS_PLAN); REQ-13
7. **Has the orchestrator mechanically parse the Bypass / Loop-Back YAML** and surface a recommendation through the existing Conversation Checkpoint — user has final say (REQ-08, REQ-09)
8. **Has the architect re-enter in `Mode: post-refactor-adaptation`** after mini-pipeline completion to update SYSTEMS_PLAN against the refactored codebase, with Phase 2.5 disabled to prevent recursion (REQ-14)
9. **Flips matching `td-NNN` rows in place** at plan-write (`open → in-flight`) and at mini-pipeline completion (`→ resolved`), preserving the architect's consumer-only privilege; no writer-set expansion (REQ-15)
10. **Is gate-liveness-conformant**: sentinel `PR01` structural check + canary fixtures for both the sentinel check and the orchestrator's YAML parse (REQ-16, REQ-17)

All four domain decisions (mode signaling, verifier scope-switch, sentinel canary, test-engineer pairing) share a single ADR because they are interlocking — changing any one would force changes to the others.

## Considered Options

### Option A (chosen) — Bundle as one ADR with prompt-directive mode signaling, artifact-presence verifier scope-switch, sentinel canary + fixture, planner-enforced characterization-tests-first

The chosen design composes existing primitives. Mode signaling reuses the baseline-audit prompt-directive convention. Verifier scope-switch reuses the verifier's existing artifact-presence pattern in Phase 1. Sentinel `PR01` follows the gate-liveness PROMPT-kind proof requirement. Characterization-tests-first is enforced by the planner's first-non-trivial-step contract in pre-refactor mode.

**Pros:**
- Zero new infrastructure (no new agent, no new worktree primitive, no new orchestrator mediation mechanism, no new ledger writer, no new phase tag)
- Mode catalog in one place (`agents/CLAUDE.md`)
- All decisions are observable (PROGRESS.md mode log, Conversation Checkpoint user record, sentinel audit, git-tracked ledger flips)
- Backward-compatible (existing pipelines work unchanged; no-refactor and fold-into-Prerequisites outcomes match today's behavior)

**Cons:**
- One more sentinel check + one fixture file to maintain
- Mini-pipeline planner's first-step invariant is implicit (relies on planner's decomposition rules + a prompt note); could be more rigid
- Mode is invisible to filesystem-only observers (mitigated by PROGRESS.md log)

### Option B — Frontmatter-flag mode signaling

Pass mode via a frontmatter field on the architect's spawn prompt rather than an inline `Mode:` directive.

**Pros:** Type-safe; tooling could validate the enum.
**Cons:** Requires spawn-machinery schema changes; diverges from existing baseline-audit convention; one more place mode signaling can drift between agents.
**Rejected because:** existing baseline-audit precedent is exactly the same channel (inline directive); adding a frontmatter mechanism just for this one mode is over-engineering.

### Option C — Marker-file mode signaling

Use a sentinel file (e.g., `.ai-work/<task-slug>/.post-refactor-adaptation`) as the mode signal.

**Pros:** Filesystem-visible; sentinel can inspect.
**Cons:** Couples mode to filesystem state; orphaned markers are a real failure mode; mode becomes a side-effect rather than a contract; harder to reason about across re-entries.
**Rejected because:** filesystem state is the wrong substrate for an invocation-mode contract; prompt directives are pure inputs.

### Option D — Sub-agent definition

Split the architect into three agents (`systems-architect`, `systems-architect-pre-refactor`, `systems-architect-post-refactor`).

**Pros:** Each agent has a single concern; pipeline dispatch is unambiguous.
**Cons:** Triples the architect maintenance surface (three prompt files, three skill lists, three model declarations); mode catalog still needs to exist somewhere; behavior duplication across three files; defeats progressive disclosure (the user reading agents/ now has three almost-identical files to grep).
**Rejected because:** the design changes amount to a few-paragraph addition + a single new phase; tripling the agent count is wildly disproportionate to the change.

### Option E — Per-row-worktree mini-pipeline (Pattern B clone)

Treat the pre-refactor as a per-row-worktree spawned by the orchestrator, mirroring the verifier rework loop's `EnterWorktree`-per-row pattern.

**Pros:** Reuses the rework-loop infrastructure exactly.
**Cons:** Wrong worktree topology — a pre-refactor is a *prerequisite* of the parent task, not an *alternative branch*; forces an artificial merge step; loses the natural "complete the refactor, then resume the parent task in the same worktree" flow.
**Rejected because:** structural fit beats mechanical reuse — Pattern B is the right reference for the artifact-driven discipline and ledger-flip semantics, but its worktree topology is structurally inappropriate here.

### Option F — Expand the tech-debt-ledger writer set to add `systems-architect`

Add the architect as a fifth writer so Phase 2.5 can *create* `td-NNN` rows for refactor-worthy debt the architect discovered that no prior verifier/sentinel pass caught.

**Pros:** Honest provenance for new debt the architect surfaces.
**Cons:** Expands a deliberately-bounded four-writer policy; introduces a fifth producer with overlapping scope (verifier and sentinel will eventually surface the same finding); contradicts the user's locked decision 4 in the task brief.
**Rejected because:** the locked decision is explicit; the consumer-only flip discipline is sufficient because newly-surfaced debt eventually gets logged by the next verifier or sentinel pass — an eventual-consistency arrangement that costs nothing more than a delayed audit-trail entry.

## Consequences

**Positive:**

- The architect now classifies preparatory refactor explicitly (four labeled outcomes), making the "small vs. substantive" judgment a routine call and an audit-trail entry
- Substantive refactors get their own plan (`PRE_REFACTOR_PLAN.md`) with declared behaviors, scope, bypass criteria, and loop-back conditions — none of which exists today
- The mini-pipeline carries characterization-tests-first orthodoxy by construction (planner's first-step contract + test-engineer pre-refactor mode), so behavior preservation is enforceable, not aspirational
- The architect's feature design rests on the post-refactor codebase shape (post-refactor-adaptation mode re-reads), eliminating the silent re-negotiation that happens today
- The orchestrator's role is bounded by mechanical YAML evaluation (no LLM judgment on routing) and the user-final-say Conversation Checkpoint; no fourth open-ended mediation point added
- Tech-debt ledger lifecycle is honored (in-place flips only; four-writer policy preserved); finalize migration to TECH_DEBT_RESOLVED.md works unchanged
- Gate-liveness conformance is built in (sentinel `PR01` + canary; orchestrator YAML parse canary)
- Zero net-new architecture-level abstractions

**Negative:**

- One more sentinel check (`PR01`) to maintain; one new fixture file
- The architect's prompt grows by ~60-80 lines (the Phase 2.5 contract + the mode catalog cross-reference); existing token budget for the agent file remains under ceiling
- One new ephemeral artifact (`PRE_REFACTOR_PLAN.md`) to document in `rules/swe/agent-intermediate-documents.md`
- The mode catalog now has three modes (feature, baseline-audit, post-refactor-adaptation) instead of two implicit ones; cognitive cost is small but real
- The orchestrator's mediation surface grows from three points (pre-verification checkpoint, verifier rework dispatch, interface-designer challenge loop) to four — adding a fifth would trigger the "third-instance extraction" decision from `skills/refactoring/SKILL.md:196`

**Neutral:**

- The bundled ADR shape means future supersession of *any one* of the four sub-decisions requires partial-supersession discipline (per the partial-supersession-clause pattern from my agent memory): set supersedes/superseded_by links + scope in body, don't flip status of the bundled ADR as a whole
- Newly-surfaced refactor-worthy debt the architect discovers in Phase 2.5 lives in `SYSTEMS_PLAN.md § Codebase Readiness` until the next verifier/sentinel pass converts it to a `td-NNN` row; this is an eventual-consistency arrangement, acceptable because the ledger is not the only learning channel
