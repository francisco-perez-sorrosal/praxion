---
core: true
load: always_on
install: symlink
---

## SWE Agent Coordination Protocol

Conventions for when and how to use the software agents — autonomous subprocesses in separate context windows.

### Process Calibration

Assess the task before starting work. Each tier prescribes what to do — higher tiers include everything below them.

| Tier | Signals | Process |
|------|---------|---------|
| **Direct** | Single-file fix, config, doc, typo | Fix → verify → commit. No agents, no planning documents, no spec. |
| **Lightweight** | 2-3 files, single behavior, clear scope | Optional researcher; no other agents (escalate to Standard if architect/planner needed). Acceptance criteria inline. Task tools for tracking. No SDD, no three-document planning. |
| **Standard** | 4-8 files, 2-4 behaviors, architectural decisions | Full agent pipeline. [SDD](../../skills/spec-driven-development/SKILL.md) behavioral spec with REQ IDs. [Three-document model](../../skills/software-planning/SKILL.md). |
| **Full** | 9+ files, 5+ behaviors, cross-cutting | Standard plus parallel execution, doc-engineer in groups, context-engineer shadowing, structured decisions, spec archival. |
| **Spike** | Exploratory, outcome uncertain | Timeboxed researcher. Decision in LEARNINGS.md. No implementation until resolved. |

- The main agent selects the tier at task intake. User override always wins. Default to the lower tier when uncertain — process can be added later, but overhead cannot be reclaimed.
- Bug fixes: Direct unless 4+ files or structural issue (escalate to Standard). Refactoring: Standard with `[Phase: Refactoring]` delegation to the [refactoring skill](../../skills/refactoring/SKILL.md). Mid-task escalation mirrors Lightweight's: if it grows past a single file plus trivial siblings, or turns structural, stop and re-tier.
- The SDD skill's [complexity triage](../../skills/spec-driven-development/SKILL.md#complexity-triage) refines specification depth within Standard/Full.
- All tiers append a row to `.ai-state/calibration_log.md` on completion (keeps calibration accuracy analysis unbiased) and may create ADRs per [adr-conventions.md](adr-conventions.md). Direct tier uses the sanctioned single-line format ([spec](../../skills/spec-driven-development/references/calibration-procedure.md#calibration-log)); `Retrospective` is the micro-capture slot, promotable to ADR/ledger row if substantial.
- **Lightweight specifics** (acceptance criteria inline, researcher scaffold, no `TEST_RESULTS.md`, architecture-doc update on structural change, mid-task escalation to Standard rather than silent scope-creep): see [tier-templates.md#lightweight-snippet](../../skills/software-planning/references/tier-templates.md#lightweight-snippet).

**Tier Selector (fast path).** Walk top-to-bottom, stop at the first match: **Spike** (exploratory, uncertain) → **Direct** (single-file fix/config/doc/typo) → **Lightweight** (2–3 files, single behavior, clear scope) → **Standard** (4–8 files, or 2–4 behaviors, or an architectural decision) → **Full** (9+ files, or 5+ behaviors, or cross-cutting refactor). For ambiguous cases, use the SDD skill's [calibration-procedure.md](../../skills/spec-driven-development/references/calibration-procedure.md) signal scoring.

*Hackathon mode: if a project sets `PRAXION_HACKATHON_MODE=1`, the 5-tier selector above is replaced by the Hackathon Spine — a flexible-entry pipeline the user enters by natural language — see that project's `## Hackathon Mode` CLAUDE.md block for the definition.*

### Pipeline Isolation

<!-- Anchor preserved for cross-rule links; do not remove -->

Standard and Full tier pipelines **must** operate in a dedicated worktree to prevent collisions when multiple pipelines run concurrently on the same repository.

**Isolation by tier:**

| Tier | Isolation |
|------|-----------|
| Direct, Lightweight, Spike | None — work in the current checkout |
| Standard, Full | Worktree — main agent calls `EnterWorktree` before spawning any agent |

See [coordination-details.md#pipeline-worktree-lifecycle](../../skills/software-planning/references/coordination-details.md#pipeline-worktree-lifecycle) for the full entry, during-execution, and exit procedures, plus multi-instance guidance.

Native Claude Code worktree isolation refuses `Write`/`Edit` (including through a symlink whose realpath leaves the worktree) that targets outside the session worktree; Bash-path writes are not blocked mechanically and are covered procedurally by pathspec-scoped commits and merge gates verified from the main checkout.

### Available Agents

Every agent is safe to run in the background **except `promethean` and
`roadmap-cartographer`**, which are interactive. Each one's output paths follow the
lifecycle convention — `.ai-work/<slug>/` ephemeral, `.ai-state/` permanent (committed).

Full roster with per-agent output paths: [`coordination-details.md § Agent Roster`](../../skills/software-planning/references/coordination-details.md#agent-roster).

### Delegation Checklists

<!-- Anchor preserved for cross-rule links; canonical content lives in coordination-details.md -->

When delegating to an agent, the main agent **must** include the per-agent deliverables in the prompt. The subagent's system prompt contains full instructions, but the main agent's prompt determines priority and scope.

When the orchestrator authors a pipeline artifact itself rather than spawning its owning agent — legitimate at any tier — the document contract still binds: **the schema binds the path, not the author**. Write that agent's canonical section skeleton, or pick a filename it does not own.

Full per-agent checklists (systems-architect, implementation-planner, implementer, verifier) are authoritative at [`coordination-details.md § Delegation Checklists`](../../skills/software-planning/references/coordination-details.md#delegation-checklists). `REWORK_MANIFEST.md` triggers the main agent to spawn rework worktrees before cleanup.

### Proactive Agent Usage

Spawn agents without waiting for the user to ask:

- Complex feature --> `researcher` then `systems-architect` (skip researcher if codebase context suffices)
- Architecture approved --> `implementation-planner`; resuming work --> same agent to re-assess `WIP.md`
- Plan ready --> `implementer` + `test-engineer` concurrently (paired steps, disjoint file sets) **at Standard/Full only**; both done --> run tests --> fix cycle if needed --> `verifier`. Direct/Lightweight rarely reach the planner; if they do, the implementer's own test sub-step suffices — don't spawn `test-engineer`
- Context artifacts stale/conflicting or plan touches them --> `context-engineer` (parallel with `researcher`/`systems-architect` as shadow; see context-engineer shadowing rule below)
- Ecosystem health or regression check --> `sentinel`; stale check: `.ai-state/sentinel_reports/SENTINEL_LOG.md` vs `git log -1 --format=%ci`
- Documentation impact likely --> `doc-engineer`: at pipeline checkpoints (after planning, after implementation, after refactoring), or in parallel with `implementer` + `test-engineer` when the planner assigns a doc step to the parallel group

Gated/on-demand agents (`skill-genesis`, `interface-designer`, `agentic-transactions-architect`, `discipline-consultant`, RISKY-step `verifier` light-review) have their trigger conditions enumerated once, in the [Pipeline Rules table](#coordination-pipeline) below.

**Depth check:** Before spawning an agent recommended by another agent's output, confirm with the user if doing so would create a chain of 3+ agents from the original request.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets; if so, spawn N instances (up to 2-3 concurrent) instead of one sequential agent. Each gets the same task slug — they share a task-scoped directory and use fragment files to avoid collisions (see [agent-intermediate-documents](agent-intermediate-documents.md)). **Lens-independence mandate:** parallel lens/fan-out agents MUST NOT reference sibling lenses during collection; reconciliation happens only at the synthesis/aggregator layer. Violating this collapses independent perspectives into correlated ones, defeating the breadth rationale. Deep-dive: [`agent-pipeline-details.md` § Multi-Perspective Analysis](../../skills/software-planning/references/agent-pipeline-details.md).

**Task slug propagation:** At pipeline start, the main agent generates a kebab-case task slug (2–4 words) derived from the task description; every subagent prompt must include `Task slug: <slug>`, and all `.ai-work/` reads and writes use `.ai-work/<task-slug>/`. See [coordination-details.md#task-slug-propagation](../../skills/software-planning/references/coordination-details.md#task-slug-propagation) for the full propagation contract; see the [task slug convention](agent-intermediate-documents.md#task-slug-convention) for naming guidelines.

### Cross-Agent Skill Conventions

Phase-independent conventions for all pipeline agents: external API docs are mandatory (`external-api-docs` skill before designing/testing against any API/SDK; `chub_feedback` on drift); library version/capability checks are mandatory before committing to a library. Full text and per-agent obligations: [`skills/software-planning/references/cross-agent-skill-conventions.md`](../../skills/software-planning/references/cross-agent-skill-conventions.md).

### Coordination Pipeline

Agents communicate through shared documents, not direct invocation — see [coordination-details.md#coordination-pipeline-diagram](../../skills/software-planning/references/coordination-details.md#coordination-pipeline-diagram) for the full pipeline-flow diagram.

**Pipeline rules** (deep-dive sections live in [coordination-details.md](../../skills/software-planning/references/coordination-details.md)):

| Rule | Behavior |
|------|----------|
| Return contract | A subagent's final message is a **pointer, not a payload**: a terse summary (≤ ~15 lines) + its `.ai-work/<task-slug>/` artifact path — never the artifact body. The orchestrator delegates for summaries and reads an artifact only when it needs the detail. Deep-dive: [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md#agent-return-contract). |
| Completion handshake | Trust a subagent return only if it carries a recognized terminal marker (`[COMPLETE]`/`[BLOCKED]`/`[CONFLICT]`/`[PARTIAL]`) **and** the durable artifact agrees (step's `WIP.md` checkbox flipped). A missing or contradicted marker is a **suspected truncation**: do **not** advance and do **not** re-run from scratch — re-derive completion from ground truth (codebase + `git diff` + tests, never the checkboxes), then mark verified-done work complete or re-spawn the unfinished remainder. Operationalized by `scripts/reconcile_pipeline_state.py` + `/resume-pipeline`; every auto-recovery is logged to `RECOVERY_LOG.md` and surfaced to the user. Deep-dive: [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md#completion-handshake-truncation-detection). |
| Do not skip stages | Research before architecture (unless codebase context suffices); re-invoke upstream when downstream input is incomplete |
| BDD/TDD execution | Paired implementation + test steps; concurrent on disjoint file sets; tests run until green |
| Batched improvements | Evaluate independence; execute with maximum parallelism via Classify / Pair-spawn / Sequence / Full-suite-gate procedure |
| Context-engineer shadowing | Context artifacts touched → context-engineer shadows researcher/systems-architect, appending to cumulative `CONTEXT_REVIEW.md` — [deep-dive](../../skills/software-planning/references/coordination-details.md#context-engineer-shadowing). |
| Context-engineer scope | 1 artifact → direct invocation at any stage; 3+ artifacts or restructuring → full pipeline under planner supervision — same deep-dive as above. |
| Sentinel | Independent of pipeline; reports (`SENTINEL_REPORT_*.md`) public to any agent or user |
| Doc-engineer parallel | Planner assigns a doc step to the parallel group → doc-engineer runs concurrent with implementer/test-engineer on disjoint files — [deep-dive](../../skills/software-planning/references/coordination-details.md#doc-engineer-parallel-execution). |
| Interface-designer shadowing + challenge loop | Substantial interface surface in scope → interface-designer shadows researcher + systems-architect, writing forward-only `INTERFACE_DESIGN.md`, with one orchestrator-mediated loop-back when `## Architecture Challenges` is populated — [deep-dive](../../skills/software-planning/references/coordination-details.md#interface-designer-shadowing--the-architecture-challenge-loop). |
| Agentic-transactions-architect shadowing + challenge loop | Task involves agentic payments/trading → same shadow/loop-back pattern, writing forward-only `TRANSACTIONS_DESIGN.md` — [deep-dive](../../skills/software-planning/references/coordination-details.md#agentic-transactions-architect-shadowing--challenge-loop). |
| Discipline-consultant convening + disposition | Registry trigger predicate matches a load-bearing claim, or an agent nominates one → `discipline-consultant` convenes; per-challenge disposition lands in the fragment + `.ai-state/CONSULT_LEDGER.md` — [deep-dive](../../skills/software-planning/references/coordination-details.md#discipline-consultant-dialogue-protocol). |
| Verifier rework loop | `REWORK_MANIFEST.md` present in `.ai-work/<slug>/` → main agent creates a rework worktree per row via `EnterWorktree`, writes `VERIFIER_FINDINGS.md`, flips `td-NNN` rows to `in-flight`, and surfaces `/resume-rework` — dispatch path: `commands/resume-rework.md`. |
| Pre-refactor sub-pipeline | `PRE_REFACTOR_PLAN.md` present in `.ai-work/<slug>/` after the architect's Phase 2.5 → orchestrator runs a same-worktree mini-pipeline (no `EnterWorktree`) and surfaces a verifier-vs-loopback recommendation at the pre-verification checkpoint — [deep-dive](../../skills/software-planning/references/coordination-details.md#pre-refactor-sub-pipeline--the-verifier-vs-loopback-decision). |
| Intra-step pair-review | Step tagged RISKY (Uncertainty Flag < 7, one-way-door, `tier: H`) or carrying `review: force` → orchestrator spawns `verifier` in `Mode: light-review` at the implementer→planner seam (`review: off` suppresses) — [deep-dive](../../skills/software-planning/references/intra-step-review.md). |
| Skill-genesis | On-demand only — `/skill-genesis` (autonomous harvest, background) or `/skill-genesis-review` (disposition of pending proposals); never pipeline-spawned |

### Conversation Checkpoints

The human-in-the-loop half of the Conversation discipline (the agent-side half is `Surface Assumptions` in the behavioral contract). The orchestrator owns three checkpoints — one at intake, two at the seams between subagent spawns where the orchestrator is interactive:

- **Intake Clarity Gate** (all tiers above Direct) — before spawning the first agent, disambiguate intent (surface assumptions; blocking question only when ambiguity meets a hard-to-reverse wrong guess). Full procedure: `goal-disambiguation` skill.
- **Phase-transition surfacing** (Standard/Full) — at phase boundaries and load-bearing steps (not intra-phase handoffs); pauses to digest assumptions/constraints and lets the user reflect or roll back.
- **Pre-verification checkpoint** — before invoking the verifier, presents a digest + load-bearing-assumption acknowledgement; user proceeds or rolls back to a specific upstream agent (distinct from the verifier rework loop).
  - **Verifier-vs-loopback recommendation** (named variant, active when `PRE_REFACTOR_PLAN.md` is present) — mechanically evaluates Bypass/Loop-Back YAML blocks, surfaces one of three recommendations; user has final say.
- **Pre-mortem gate** (named variant of phase-transition surfacing, always-on at Standard/Full) — fires at the planner→implementer boundary: "assume this plan shipped and caused an incident — why?"; failure modes recorded in `WIP.md`.

Full digest-curation, acknowledgement-shape, rollback-routing, and degraded-mode procedure for every checkpoint above: [`coordination-details.md#conversation-checkpoints`](../../skills/software-planning/references/coordination-details.md#conversation-checkpoints).

Direct/Lightweight tiers have no phases — the discipline collapses to the Intake Clarity Gate (Lightweight; Direct uses only intake `Surface Assumptions`) plus a pre-commit digest. Interactive (pauses on) is the default; an explicitly requested automated run suppresses the pauses but still captures assumptions and writes the digest as a post-hoc record. Automated is an execution mode orthogonal to the tier.

### Agent Selection Criteria

Use an agent when the task benefits from a separate context window (large scope, multiple phases, structured output). Work directly for quick lookups, single changes, one-step edits. Per-agent Claude model tier is governed by [`agent-model-routing.md`](agent-model-routing.md).

**Shipped-Explore fallback.** If `Agent(subagent_type="Explore", ...)` fails before producing output, don't retry the same input — fall back to `praxion:researcher` for substantive code surveys or direct `find`/`grep` via Bash for narrow lookups. Full failure signature and tracking: [`docs/claude-code-limitations.md`](../../docs/claude-code-limitations.md).

### Delegation Depth

- **Depth 0-1:** Standard. **Depth 2:** Main agent decides. **Depth 3+:** Requires explicit user confirmation.
- Agents at depth 1 can recommend further agents but never auto-chain to depth 3+.

### Background Agents

Run agents in the background when their output is not immediately needed. Check the Bg Safe column before using `run_in_background`. Check output before proceeding with dependent work.

### Parallel Execution & Boundary Discipline

Launch independent agents concurrently whenever possible. Each agent has strict boundaries — when an agent encounters work outside its boundary, it flags the need and recommends invoking the appropriate agent.

For detailed tables — boundary discipline, parallel execution, intra-stage parallelism, multi-perspective analysis, context-engineer and doc-engineer engagement, interaction reporting — load the `software-planning` skill's [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md).
