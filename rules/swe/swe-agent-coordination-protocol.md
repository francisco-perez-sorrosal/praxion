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

Standard and Full tier pipelines **must** operate in a dedicated worktree to prevent collisions when multiple pipelines run concurrently on the same repository.

**Isolation by tier:**

| Tier | Isolation |
|------|-----------|
| Direct, Lightweight, Spike | None — work in the current checkout |
| Standard, Full | Worktree — main agent calls `EnterWorktree` before spawning any agent |

**At pipeline start** (immediately after tier selection and task slug generation):

1. Call `EnterWorktree` with `name: "<task-slug>"` — creates a worktree and switches the session into it
2. All subsequent work (`.ai-work/`, `.ai-state/`, code changes) happens inside the worktree
3. Parallel file-modifying agents (implementer + test-engineer + doc-engineer) additionally use `isolation: "worktree"` on the Agent tool for intra-pipeline isolation

**At pipeline end:**

1. Verify all `.ai-state/` artifacts (ADRs, specs, calibration log) are committed — no untracked stragglers
2. Commit all remaining changes in the worktree branch
3. Call `ExitWorktree` with `action: "keep"` — preserves the branch for user review and merge
4. Report branch name + `.ai-state/` artifact summary + merge notes to the user

See [agent-pipeline-details.md](../../skills/software-planning/references/agent-pipeline-details.md#pipeline-worktree-lifecycle) for the full lifecycle, merge procedure, and multi-instance guidance.

### Available Agents

| Agent | Purpose | Output | Bg Safe |
|-------|---------|--------|---------|
| `promethean` | Feature-level ideation from project state | `IDEA_PROPOSAL.md`, `IDEA_LEDGER_*.md` | No |
| `researcher` | Codebase exploration, external docs, comparative analysis | `RESEARCH_FINDINGS.md` | Yes |
| `systems-architect` | Trade-off analysis, system design | `SYSTEMS_PLAN.md`, `SPEC_DELTA.md` (conditional) | Yes |
| `implementation-planner` | Step decomposition, execution supervision | `IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md` | Yes |
| `context-engineer` | Context artifact domain expert; any pipeline stage | Audit report + artifact changes, `CONTEXT_REVIEW.md` (shadowing) | Yes |
| `implementer` | Executes implementation steps with self-review | Code changes + `WIP.md` update | Yes |
| `test-engineer` | Dedicated testing: complex test design, test suite refactoring, testing infrastructure | Test code + `WIP.md` update | Yes |
| `verifier` | Post-implementation review against acceptance criteria | `VERIFICATION_REPORT.md` | Yes |
| `doc-engineer` | Documentation quality (READMEs, catalogs, changelogs) | Doc report or file fixes | Yes |
| `sentinel` | Read-only ecosystem auditor (independent, not a pipeline stage) | `SENTINEL_REPORT_*.md`, `SENTINEL_LOG.md` | Yes |
| `skill-genesis` | Learning triage, artifact proposal from experience | `SKILL_GENESIS_REPORT.md` | No |
| `cicd-engineer` | CI/CD pipeline design, GitHub Actions, deployment automation | Workflow files + pipeline config | Yes |

### Proactive Agent Usage

Spawn agents without waiting for the user to ask:

- Complex feature --> `researcher` then `systems-architect` (skip researcher if codebase context suffices)
- Architecture approved --> `implementation-planner`; resuming work --> same agent to re-assess `WIP.md`
- Plan ready --> `implementer` + `test-engineer` concurrently (paired steps on disjoint file sets); both complete --> run tests --> fix cycle if needed --> `verifier`
- Context artifacts stale/conflicting or plan touches them --> `context-engineer` (parallel with `researcher`/`systems-architect`); when work involves context artifacts during research or architecture stages --> `context-engineer` shadows in parallel, producing cumulative `CONTEXT_REVIEW.md` that flows forward to downstream stages
- Ecosystem health or regression check --> `sentinel`; stale check: `.ai-state/SENTINEL_LOG.md` vs `git log -1 --format=%ci`
- Documentation impact likely --> `doc-engineer`: at pipeline checkpoints (after planning, after implementation, after refactoring), or in parallel with `implementer` + `test-engineer` when the planner assigns a doc step to the parallel group
- Pipeline complete + LEARNINGS.md has content --> `skill-genesis`

**Depth check:** Before spawning an agent recommended by another agent's output, confirm with the user if doing so would create a chain of 3+ agents from the original request.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets. If so, spawn N instances (up to 2-3 concurrent) rather than one sequential agent. Each instance receives the same task slug — they share a task-scoped directory and use fragment files to avoid collisions (see [agent-intermediate-documents](agent-intermediate-documents.md)).

**Task slug propagation:** At pipeline start, the main agent generates a kebab-case task slug (2–4 words) derived from the task description. For Standard/Full tiers, the slug also names the worktree (see [Pipeline Isolation](#pipeline-isolation)). Every subagent prompt must include `Task slug: <slug>`. All `.ai-work/` reads and writes use `.ai-work/<task-slug>/`. The slug never changes mid-pipeline. See the [task slug convention](agent-intermediate-documents.md#task-slug-convention) for naming guidelines.

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
- **BDD/TDD execution.** The planner produces paired implementation and test steps. Test-engineers design behavioral tests from the systems plan's acceptance criteria. Implementers and test-engineers execute concurrently on disjoint file sets. After both complete, tests are run against the implementation. Failing tests trigger a fix cycle until all tests pass — including pre-existing tests broken by the change (boy scout rule).
- **Context-engineer shadowing.** When work involves context artifacts, the context-engineer runs in parallel with the researcher (research-stage shadow) and/or systems-architect (architecture-stage shadow), appending stage-delimited sections to a cumulative `CONTEXT_REVIEW.md`. The architect reads the research-stage section; the planner reads both. Shadowing is conditional — it activates only when the task creates, modifies, or restructures context artifacts. For pure application code, no shadowing occurs.
- **Context-engineer** also collaborates at any pipeline stage for direct context artifact work and operates independently for standalone audits.
- **Sentinel** is independent. Reports (`SENTINEL_REPORT_*.md`) are public -- any agent or user can consume them.
- Small-scope context work (single artifact) --> context-engineer directly; large-scope (3+) --> full pipeline.
- **Doc-engineer parallel execution.** When the planner assigns a doc step to a parallel group, the doc-engineer runs concurrently with the implementer and test-engineer on disjoint file sets (documentation files vs production code vs test code). A parallel group can have up to three concurrent agents. Doc steps are assigned only when a group adds/removes/renames files, introduces new APIs, or changes module structure — not 1:1 with every implementation step. The doc-engineer also continues to run at pipeline checkpoints (after planning, after implementation, after refactoring) as before.

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
