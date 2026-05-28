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
- Bug fixes: Direct unless 4+ files or structural issue (escalate to Standard). Refactoring: Standard with `[Phase: Refactoring]` delegation to the [refactoring skill](../../skills/refactoring/SKILL.md).
- The SDD skill's [complexity triage](../../skills/spec-driven-development/SKILL.md#complexity-triage) refines specification depth within Standard/Full.
- All tiers append a row to `.ai-state/calibration_log.md` on task completion (calibration accuracy analysis stays unbiased) and may create ADRs in `.ai-state/decisions/` when a decision is worth preserving — see [adr-conventions.md](adr-conventions.md).
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

Two hooks reinforce this boundary: `inject_worktree_banner.py` (SessionStart) announces the worktree root and the canonical checkout when a session opens inside a worktree; `worktree_guard.py` (PreToolUse) blocks `Write`/`Edit` that resolve outside the session worktree.

### Available Agents

Outputs use path prefixes to signal lifecycle: `.ai-work/<slug>/` = ephemeral (deleted after pipeline), `.ai-state/` = permanent (committed to git).

| Agent | Purpose | Output | Bg Safe |
|-------|---------|--------|---------|
| `promethean` | Feature-level ideation from project state | `.ai-work/<slug>/IDEA_PROPOSAL.md`, `.ai-state/idea_ledgers/IDEA_LEDGER_*.md` | No |
| `researcher` | Codebase exploration, external docs, comparative analysis | `.ai-work/<slug>/RESEARCH_FINDINGS.md` | Yes |
| `systems-architect` | Trade-off analysis, system design | `.ai-work/<slug>/SYSTEMS_PLAN.md`, `.ai-state/decisions/` (ADRs), `.ai-state/DESIGN.md`^1, `docs/architecture.md`^1 | Yes |
| `implementation-planner` | Step decomposition, execution supervision | `.ai-work/<slug>/IMPLEMENTATION_PLAN.md`, `.ai-work/<slug>/WIP.md`, `.ai-work/<slug>/LEARNINGS.md` | Yes |
| `context-engineer` | Context artifact domain expert; any pipeline stage | Audit report + artifact changes, `.ai-work/<slug>/CONTEXT_REVIEW.md` (shadowing) | Yes |
| `implementer` | Executes implementation steps with self-review | Code changes + `.ai-work/<slug>/WIP.md` update + `.ai-work/<slug>/TEST_RESULTS.md` (when step runs tests) | Yes |
| `test-engineer` | Dedicated testing: complex test design, test suite refactoring, testing infrastructure | Test code + `.ai-work/<slug>/WIP.md` update + `.ai-work/<slug>/TEST_RESULTS.md` (canonical when paired with implementer on tests) | Yes |
| `verifier` | Post-implementation review against acceptance criteria | `.ai-work/<slug>/VERIFICATION_REPORT.md` | Yes |
| `doc-engineer` | Documentation quality (READMEs, catalogs, changelogs, developer architecture guide) | Doc report or file fixes | Yes |
| `sentinel` | Read-only ecosystem auditor (independent, not a pipeline stage) | `.ai-state/sentinel_reports/SENTINEL_REPORT_*.md`, `.ai-state/sentinel_reports/SENTINEL_LOG.md` | Yes |
| `architect-validator` | Per-PR / on-demand structural validator for the code↔DSL↔ADR triangle | `.ai-work/<task-slug>/ARCHITECTURE_VALIDATION.md`, `.ai-state/TECH_DEBT_LEDGER.md` rows on FAIL | Yes |
| `skill-genesis` | Autonomous learning-harvest report writer; user dispositions via `/skill-genesis-review` | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_*.md`, `.ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md` | Yes |
| `cicd-engineer` | CI/CD pipeline design, GitHub Actions, deployment automation | Workflow files + pipeline config | Yes |
| `roadmap-cartographer` | Project-level audit-to-roadmap through a project-derived lens set (SPIRIT, DORA, SPACE, FAIR, CNCF, or Custom); invoked via `/roadmap` | `ROADMAP.md` at project root, `.ai-work/<slug>/ROADMAP_DRAFT.md`, `.ai-work/<slug>/AUDIT_<lens>.md` fragments | No |
| `interface-designer` | Interface-layer design specialist — peer sub-architect for web UI, TUI/CLI, REST/GraphQL/gRPC APIs, MCP/agent tools, A2A contracts; makes framework/paradigm/error-format/pagination decisions and sketches designs; writes ADR fragments for load-bearing calls | `.ai-work/<slug>/INTERFACE_DESIGN.md` + ADR fragments in `.ai-state/decisions/drafts/` | Yes |

**Conditional output footnotes:** ^1 For Standard/Full tier pipelines — always create both architecture docs unless the project is trivially simple (single module, no external dependencies).

### Delegation Checklists

<!-- Anchor preserved for cross-rule links; canonical content lives in coordination-details.md -->

When delegating to an agent, the main agent **must** include the per-agent deliverables in the prompt. The subagent's system prompt contains full instructions, but the main agent's prompt determines priority and scope.

The full per-agent checklists for systems-architect, implementation-planner, implementer, and verifier — including conditional clauses (`if deployment in scope`, `if structural`, `if tests`) — are the authoritative source at [`coordination-details.md § Delegation Checklists`](../../skills/software-planning/references/coordination-details.md#delegation-checklists). Sentinel `EC06` validates that the condensed block in `claude/config/CLAUDE.md` stays byte-equivalent with that section. When `REWORK_MANIFEST.md` is produced, the main agent is responsible for spawning rework worktrees before invoking cleanup.

### Proactive Agent Usage

Spawn agents without waiting for the user to ask:

- Complex feature --> `researcher` then `systems-architect` (skip researcher if codebase context suffices)
- Architecture approved --> `implementation-planner`; resuming work --> same agent to re-assess `WIP.md`
- Plan ready --> `implementer` + `test-engineer` concurrently (paired steps, disjoint file sets) **at Standard/Full only**; both done --> run tests --> fix cycle if needed --> `verifier`. Direct/Lightweight rarely reach the planner; if they do, the implementer's own test sub-step suffices — don't spawn `test-engineer`
- Context artifacts stale/conflicting or plan touches them --> `context-engineer` (parallel with `researcher`/`systems-architect` as shadow; see context-engineer shadowing rule below)
- Ecosystem health or regression check --> `sentinel`; stale check: `.ai-state/sentinel_reports/SENTINEL_LOG.md` vs `git log -1 --format=%ci`
- Documentation impact likely --> `doc-engineer`: at pipeline checkpoints (after planning, after implementation, after refactoring), or in parallel with `implementer` + `test-engineer` when the planner assigns a doc step to the parallel group
- On-demand only — `skill-genesis` runs when the user invokes `/skill-genesis` (autonomous harvest, background) or `/skill-genesis-review` (disposition pending proposals); never pipeline-spawned
- Task involves substantial interface surface (new web UI, new TUI, CLI-output pass, new/changed API, MCP tool surface) --> `interface-designer` (parallel with `researcher` / `systems-architect` as shadow; see Interface-designer shadowing + challenge loop rule below)

**Depth check:** Before spawning an agent recommended by another agent's output, confirm with the user if doing so would create a chain of 3+ agents from the original request.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets; if so, spawn N instances (up to 2-3 concurrent) instead of one sequential agent. Each gets the same task slug — they share a task-scoped directory and use fragment files to avoid collisions (see [agent-intermediate-documents](agent-intermediate-documents.md)).

**Task slug propagation:** At pipeline start, the main agent generates a kebab-case task slug (2–4 words) derived from the task description; every subagent prompt must include `Task slug: <slug>`, and all `.ai-work/` reads and writes use `.ai-work/<task-slug>/`. See [coordination-details.md#task-slug-propagation](../../skills/software-planning/references/coordination-details.md#task-slug-propagation) for the full propagation contract; see the [task slug convention](agent-intermediate-documents.md#task-slug-convention) for naming guidelines.

### Cross-Agent Skill Conventions

Phase-independent conventions for all pipeline agents: external API docs are mandatory (use the `external-api-docs` skill before writing/designing/testing against any external API or SDK; submit `chub_feedback` on drift); library version/capability checks are mandatory (verify before committing to a library; record confirmed versions in canonical outputs). Full text and per-agent obligations: [`skills/software-planning/references/cross-agent-skill-conventions.md`](../../skills/software-planning/references/cross-agent-skill-conventions.md).

### Coordination Pipeline

Agents communicate through shared documents, not direct invocation. The pipeline flows promethean → researcher → systems-architect → implementation-planner → (implementer ∥ test-engineer ∥ doc-engineer) → verifier, with context-engineer shadowing research+architecture and sentinel running as an independent audit. See [coordination-details.md#coordination-pipeline-diagram](../../skills/software-planning/references/coordination-details.md#coordination-pipeline-diagram) for the ASCII diagram.

**Pipeline rules** (deep-dive sections live in [coordination-details.md](../../skills/software-planning/references/coordination-details.md)):

| Rule | Behavior |
|------|----------|
| Return contract | A subagent's final message is a **pointer, not a payload**: a terse summary (≤ ~15 lines) + its `.ai-work/<task-slug>/` artifact path — never the artifact body. The orchestrator delegates for summaries and reads an artifact only when it needs the detail. Deep-dive: [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md#agent-return-contract). |
| Do not skip stages | Research before architecture (unless codebase context suffices); re-invoke upstream when downstream input is incomplete |
| BDD/TDD execution | Paired implementation + test steps; concurrent on disjoint file sets; tests run until green |
| Batched improvements | Evaluate independence; execute with maximum parallelism via Classify / Pair-spawn / Sequence / Full-suite-gate procedure |
| Context-engineer shadowing | Conditional on context artifacts being touched; runs parallel to researcher / systems-architect; appends to cumulative `CONTEXT_REVIEW.md` |
| Context-engineer scope | Single artifact → direct invocation any stage; 3+ artifacts → full pipeline; also runs for standalone audits |
| Sentinel | Independent of pipeline; reports (`SENTINEL_REPORT_*.md`) public to any agent or user |
| Doc-engineer parallel | When the planner assigns it to the parallel group: concurrent with implementer / test-engineer on disjoint files; also at pipeline checkpoints |
| Interface-designer shadowing + challenge loop | When an interface surface is in scope: parallel to researcher + systems-architect; forward-only `INTERFACE_DESIGN.md` with one orchestrator-mediated loop-back when `## Architecture Challenges` is populated |
| Verifier rework loop | When `REWORK_MANIFEST.md` is present in `.ai-work/<slug>/`, main agent creates a rework worktree per row via `EnterWorktree`, writes `VERIFIER_FINDINGS.md` inside, flips `td-NNN` rows to `in-flight`, and surfaces `/resume-rework` to the user. See `commands/resume-rework.md` for the fresh-session dispatch path. |
| Pre-refactor sub-pipeline | When `PRE_REFACTOR_PLAN.md` is present in `.ai-work/<slug>/` after the architect's Phase 2.5 emits `emit-PRE_REFACTOR_PLAN`, the orchestrator detects it by artifact-presence (mirroring verifier-rework and interface-designer-challenge triggers), mechanically parses the structured `## Verifier Bypass Criteria` and `## Loop-Back Conditions` YAML blocks, surfaces a recommendation through the existing pre-verification Conversation Checkpoint, and the user decides. The mini-pipeline runs **in the same worktree** as the parent task (no `EnterWorktree`); steps reuse the existing `[Phase: Refactoring]` tag (no new tag invented); first non-trivial step is a `test-engineer`-assigned characterization-tests-first step. One-pass recursion bound — the architect's re-entry runs in `post-refactor-adaptation` mode, which is forbidden from re-running Phase 2.5. Deep-dive: [`coordination-details.md` § Pre-Refactor Sub-Pipeline & the Verifier-vs-Loopback Decision](../../skills/software-planning/references/coordination-details.md#pre-refactor-sub-pipeline--the-verifier-vs-loopback-decision). |

### Conversation Checkpoints

The human-in-the-loop half of the Conversation discipline (the agent-side half is `Surface Assumptions` in the behavioral contract). The orchestrator owns two checkpoints, run at the seams between subagent spawns where the orchestrator is interactive:

- **Phase-transition surfacing** (Standard/Full) — at phase boundaries (research→architecture→planning→implementation) and load-bearing steps, *not* intra-phase agent handoffs, the orchestrator pauses, digests the critical assumptions and constraints taken, and lets the user reflect or roll back.
- **Pre-verification checkpoint** — before invoking the verifier, the orchestrator presents a curated executive digest plus an acknowledgement of the load-bearing assumptions; the user proceeds, or rolls back to a specific upstream agent with the pipeline still in flight. This is distinct from the verifier rework loop (the verifier-driven backstop) — the two rollback paths bracket the verifier by design.
  - **Verifier-vs-loopback recommendation** (named variant of the pre-verification checkpoint, active when `PRE_REFACTOR_PLAN.md` is present): the orchestrator mechanically evaluates the plan's `## Verifier Bypass Criteria` and `## Loop-Back Conditions` YAML blocks and surfaces one of three recommendations — `proceed-to-verifier`, `bypass-verifier-with-user-ack`, or `loop-back-to-architect`. The user retains final say in every case; the recommendation is advisory.

Direct/Lightweight tiers have no phases — the discipline collapses to intake `Surface Assumptions` plus a pre-commit digest. Interactive (pauses on) is the default; an explicitly requested automated run suppresses the pauses but still captures assumptions and writes the digest as a post-hoc record. Automated is an execution mode orthogonal to the tier.

Procedure — digest curation, acknowledgement shape, rollback routing, degraded-mode behavior: [coordination-details.md#conversation-checkpoints](../../skills/software-planning/references/coordination-details.md#conversation-checkpoints).

### Agent Selection Criteria

Use an agent when the task benefits from a separate context window (large scope, multiple phases, structured output). Work directly for quick lookups, single changes, one-step edits. Per-agent Claude model tier is governed by [`agent-model-routing.md`](agent-model-routing.md).

**Shipped-Explore fallback.** If `Agent(subagent_type="Explore", ...)` fails before producing output (harness error, orphaned-tool-start, no agent-start event), don't retry the same input — its tokens are already spent. Fall back to `i-am:researcher` for substantive code surveys (returns a structured `RESEARCH_FINDINGS.md`) or to direct `find`/`grep` via Bash for narrow lookups. Many-skill / many-MCP environments are especially prone to this.

### Delegation Depth

- **Depth 0-1:** Standard. **Depth 2:** Main agent decides. **Depth 3+:** Requires explicit user confirmation.
- Agents at depth 1 can recommend further agents but never auto-chain to depth 3+.

### Background Agents

Run agents in the background when their output is not immediately needed. Check the Bg Safe column before using `run_in_background`. Monitor `.ai-work/<task-slug>/PROGRESS.md` for status; check output before proceeding with dependent work.

### Parallel Execution & Boundary Discipline

Launch independent agents concurrently whenever possible. Each agent has strict boundaries — when an agent encounters work outside its boundary, it flags the need and recommends invoking the appropriate agent.

For detailed tables — boundary discipline, parallel execution, intra-stage parallelism, multi-perspective analysis, context-engineer and doc-engineer engagement, interaction reporting — load the `software-planning` skill's [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md).
