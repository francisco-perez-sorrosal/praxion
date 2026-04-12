## SWE Agent Coordination Protocol

Conventions for when and how to use the available software agents -- autonomous subprocesses that run in separate context windows.

### Process Calibration

Assess the task before starting work. Each tier prescribes what to do — higher tiers include everything below them.

| Tier | Signals | Process |
|------|---------|---------|
| **Direct** | Single-file fix, config, doc, typo | Fix → verify → commit. No agents, no planning documents, no spec. |
| **Lightweight** | 2-3 files, single behavior, clear scope | Optional researcher. Acceptance criteria inline. Task tools for tracking. No SDD, no three-document planning. |
| **Standard** | 4-8 files, 2-4 behaviors, architectural decisions | Full agent pipeline. [SDD](../../skills/spec-driven-development/SKILL.md) behavioral spec with REQ IDs. [Three-document model](../../skills/software-planning/SKILL.md). |
| **Full** | 9+ files, 5+ behaviors, cross-cutting | Standard plus parallel execution, doc-engineer in groups, context-engineer shadowing, structured decisions, spec archival. |
| **Spike** | Exploratory, outcome uncertain | Timeboxed researcher. Decision in LEARNINGS.md. No implementation until resolved. |

- The main agent selects the tier at task intake. User override always wins.
- Default to the lower tier when uncertain — process can be added later, but overhead cannot be reclaimed.
- Bug fixes: Direct unless 4+ files or structural issue (escalate to Standard).
- Refactoring: Standard with `[Phase: Refactoring]` delegation to the [refactoring skill](../../skills/refactoring/SKILL.md).
- The SDD skill's [complexity triage](../../skills/spec-driven-development/SKILL.md#complexity-triage) refines specification depth within Standard and Full tiers.
- For structured calibration with signal scoring, see the SDD skill's [calibration procedure](../../skills/spec-driven-development/references/calibration-procedure.md).

### Pipeline Isolation

<!-- Anchor preserved for cross-rule links; do not remove -->

Standard and Full tier pipelines **must** operate in a dedicated worktree to prevent collisions when multiple pipelines run concurrently on the same repository.

**Isolation by tier:**

| Tier | Isolation |
|------|-----------|
| Direct, Lightweight, Spike | None — work in the current checkout |
| Standard, Full | Worktree — main agent calls `EnterWorktree` before spawning any agent |

See [coordination-details.md#pipeline-worktree-lifecycle](../../skills/software-planning/references/coordination-details.md#pipeline-worktree-lifecycle) for the full entry, during-execution, and exit procedures, plus multi-instance guidance.

### Available Agents

Outputs use path prefixes to signal lifecycle: `.ai-work/<slug>/` = ephemeral (deleted after pipeline), `.ai-state/` = permanent (committed to git).

| Agent | Purpose | Output | Bg Safe |
|-------|---------|--------|---------|
| `promethean` | Feature-level ideation from project state | `.ai-work/<slug>/IDEA_PROPOSAL.md`, `.ai-state/IDEA_LEDGER_*.md` | No |
| `researcher` | Codebase exploration, external docs, comparative analysis | `.ai-work/<slug>/RESEARCH_FINDINGS.md` | Yes |
| `systems-architect` | Trade-off analysis, system design | `.ai-work/<slug>/SYSTEMS_PLAN.md`, `.ai-state/decisions/` (ADRs), `.ai-state/ARCHITECTURE.md`^1, `docs/architecture.md`^1 | Yes |
| `implementation-planner` | Step decomposition, execution supervision | `.ai-work/<slug>/IMPLEMENTATION_PLAN.md`, `.ai-work/<slug>/WIP.md`, `.ai-work/<slug>/LEARNINGS.md` | Yes |
| `context-engineer` | Context artifact domain expert; any pipeline stage | Audit report + artifact changes, `.ai-work/<slug>/CONTEXT_REVIEW.md` (shadowing) | Yes |
| `implementer` | Executes implementation steps with self-review | Code changes + `.ai-work/<slug>/WIP.md` update | Yes |
| `test-engineer` | Dedicated testing: complex test design, test suite refactoring, testing infrastructure | Test code + `.ai-work/<slug>/WIP.md` update | Yes |
| `verifier` | Post-implementation review against acceptance criteria | `.ai-work/<slug>/VERIFICATION_REPORT.md` | Yes |
| `doc-engineer` | Documentation quality (READMEs, catalogs, changelogs, developer architecture guide) | Doc report or file fixes | Yes |
| `sentinel` | Read-only ecosystem auditor (independent, not a pipeline stage) | `.ai-state/SENTINEL_REPORT_*.md`, `.ai-state/SENTINEL_LOG.md` | Yes |
| `skill-genesis` | Learning triage, artifact proposal from experience | `.ai-work/<slug>/SKILL_GENESIS_REPORT.md` | No |
| `cicd-engineer` | CI/CD pipeline design, GitHub Actions, deployment automation | Workflow files + pipeline config | Yes |

**Conditional output footnotes:** ^1 For Standard/Full tier pipelines — always create both architecture docs unless the project is trivially simple (single module, no external dependencies).

### Delegation Checklists

When delegating to an agent, the main agent **must** include these deliverables in the prompt. The subagent's system prompt contains full instructions, but the main agent's prompt determines priority and scope.

**systems-architect** — always include in prompt:
- "Produce `SYSTEMS_PLAN.md` at `.ai-work/<task-slug>/`"
- "Create ADRs in `.ai-state/decisions/` for significant trade-offs"
- "Create or update `.ai-state/ARCHITECTURE.md` (architect-facing design target)"
- "Create or update `docs/architecture.md` (developer-facing navigation guide, Built components only)"
- If deployment is in scope: "Create or update `.ai-state/SYSTEM_DEPLOYMENT.md`"

**implementation-planner** — always include in prompt:
- "Produce `IMPLEMENTATION_PLAN.md`, `WIP.md`, and `LEARNINGS.md` at `.ai-work/<task-slug>/`"
- "Read the `SYSTEMS_PLAN.md` at `.ai-work/<task-slug>/` for input"

**implementer** — always include in prompt:
- "Execute step N from `WIP.md` at `.ai-work/<task-slug>/`"
- "Update `WIP.md` with completion status"
- "If structural changes: update `.ai-state/ARCHITECTURE.md` (step 7.6) and `docs/architecture.md` (step 7.7)"

**verifier** — always include in prompt:
- "Produce `VERIFICATION_REPORT.md` at `.ai-work/<task-slug>/`"
- "Verify against acceptance criteria in the `SYSTEMS_PLAN.md`"
- "Check `.ai-state/ARCHITECTURE.md` design coherence (Phase 4.8a) and `docs/architecture.md` code accuracy (Phase 4.8b)"

### Proactive Agent Usage

Spawn agents without waiting for the user to ask:

- Complex feature --> `researcher` then `systems-architect` (skip researcher if codebase context suffices)
- Architecture approved --> `implementation-planner`; resuming work --> same agent to re-assess `WIP.md`
- Plan ready --> `implementer` + `test-engineer` concurrently (paired steps on disjoint file sets); both complete --> run tests --> fix cycle if needed --> `verifier`
- Context artifacts stale/conflicting or plan touches them --> `context-engineer` (parallel with `researcher`/`systems-architect` as shadow; see context-engineer shadowing rule below)
- Ecosystem health or regression check --> `sentinel`; stale check: `.ai-state/SENTINEL_LOG.md` vs `git log -1 --format=%ci`
- Documentation impact likely --> `doc-engineer`: at pipeline checkpoints (after planning, after implementation, after refactoring), or in parallel with `implementer` + `test-engineer` when the planner assigns a doc step to the parallel group
- Pipeline complete + LEARNINGS.md has content --> `skill-genesis`

**Depth check:** Before spawning an agent recommended by another agent's output, confirm with the user if doing so would create a chain of 3+ agents from the original request.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets. If so, spawn N instances (up to 2-3 concurrent) rather than one sequential agent. Each instance receives the same task slug — they share a task-scoped directory and use fragment files to avoid collisions (see [agent-intermediate-documents](agent-intermediate-documents.md)).

**Task slug propagation:** At pipeline start, the main agent generates a kebab-case task slug (2–4 words) derived from the task description; every subagent prompt must include `Task slug: <slug>`, and all `.ai-work/` reads and writes use `.ai-work/<task-slug>/`. See [coordination-details.md#task-slug-propagation](../../skills/software-planning/references/coordination-details.md#task-slug-propagation) for the full propagation contract; see the [task slug convention](agent-intermediate-documents.md#task-slug-convention) for naming guidelines.

### Coordination Pipeline

Agents communicate through shared documents, not direct invocation.

```text
promethean --> researcher ---------> systems-architect --> implementation-planner --+--> implementer    --+--> verifier
              + context-engineer     + context-engineer                             |                     |
                (shadow)               (shadow)                                    +--> test-engineer  --+
                                                                                   |
                                                                                   +--> doc-engineer   --+
                                                                                        (when assigned)
                                                                     sentinel (independent audit)
```

**Pipeline rules:**

- **Do not skip stages.** Research before architecture (unless codebase context suffices). Re-invoke upstream agents when downstream input is incomplete.
- **BDD/TDD execution.** Planner produces paired implementation and test steps; both execute concurrently on disjoint file sets, tests run until green. See [coordination-details.md#bdd-tdd-execution](../../skills/software-planning/references/coordination-details.md#bdd-tdd-execution).
- **Batched improvement execution.** When a list of improvements is presented, evaluate independence and execute with maximum parallelism. See [coordination-details.md#batched-improvement-execution](../../skills/software-planning/references/coordination-details.md#batched-improvement-execution) for the Classify/Pair-spawn/Sequence/Full-suite-gate procedure.
- **Context-engineer shadowing.** When work involves context artifacts, context-engineer runs in parallel with researcher and/or systems-architect, appending to a cumulative `CONTEXT_REVIEW.md`; conditional — pure application code does not trigger it. See [coordination-details.md#context-engineer-shadowing](../../skills/software-planning/references/coordination-details.md#context-engineer-shadowing).
- **Context-engineer scope.** Small-scope (single artifact) --> context-engineer directly at any stage. Large-scope (3+ artifacts) --> full pipeline. Also operates for standalone audits.
- **Sentinel** is independent. Reports (`SENTINEL_REPORT_*.md`) are public -- any agent or user can consume them.
- **Doc-engineer parallel execution.** When planner assigns a doc step to a parallel group, doc-engineer runs concurrently with implementer and test-engineer on disjoint file sets; also runs at pipeline checkpoints. See [coordination-details.md#doc-engineer-parallel-execution](../../skills/software-planning/references/coordination-details.md#doc-engineer-parallel-execution).

### Agent Selection Criteria

Use an agent when the task benefits from a separate context window (large scope, multiple phases, structured output). Work directly for quick lookups, single changes, one-step edits.

### Delegation Depth

- **Depth 0-1:** Standard. **Depth 2:** Main agent decides. **Depth 3+:** Requires explicit user confirmation.
- Agents at depth 1 can recommend further agents but never auto-chain to depth 3+.

### Background Agents

Run agents in the background when their output is not immediately needed. Check the Bg Safe column before using `run_in_background`. Monitor `.ai-work/<task-slug>/PROGRESS.md` for status; check output before proceeding with dependent work.

### Parallel Execution & Boundary Discipline

Launch independent agents concurrently whenever possible. Each agent has strict boundaries — when an agent encounters work outside its boundary, it flags the need and recommends invoking the appropriate agent.

For detailed tables on boundary discipline, parallel execution rules, intra-stage parallelism, multi-perspective analysis, context-engineer and doc-engineer pipeline engagement, and interaction reporting, load the `software-planning` skill's [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md) reference.
