## SWE Agent Coordination Protocol

Conventions for when and how to use the available software agents -- autonomous subprocesses that run in separate context windows.

### Available Agents

| Agent | Purpose | Output | Bg Safe |
|-------|---------|--------|---------|
| `promethean` | Feature-level ideation from project state | `IDEA_PROPOSAL.md`, `IDEA_LEDGER_*.md` | No |
| `researcher` | Codebase exploration, external docs, comparative analysis | `RESEARCH_FINDINGS.md` | Yes |
| `systems-architect` | Trade-off analysis, system design | `SYSTEMS_PLAN.md` | Yes |
| `implementation-planner` | Step decomposition, execution supervision | `IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md` | Yes |
| `context-engineer` | Context artifact domain expert; any pipeline stage | Audit report + artifact changes | Yes |
| `implementer` | Executes implementation steps with self-review | Code changes + `WIP.md` update | Yes |
| `verifier` | Post-implementation review against acceptance criteria | `VERIFICATION_REPORT.md` | Yes |
| `doc-engineer` | Documentation quality (READMEs, catalogs, changelogs) | Doc report or file fixes | Yes |
| `sentinel` | Read-only ecosystem auditor (independent, not a pipeline stage) | `SENTINEL_REPORT_*.md`, `SENTINEL_LOG.md` | Yes |
| `skill-genesis` | Learning triage, artifact proposal from experience | `SKILL_GENESIS_REPORT.md` | No |
| `cicd-engineer` | CI/CD pipeline design, GitHub Actions, deployment automation | Workflow files + pipeline config | Yes |

### Proactive Agent Usage

Spawn agents without waiting for the user to ask:

- Complex feature --> `researcher` then `systems-architect` (skip researcher if codebase context suffices)
- Architecture approved --> `implementation-planner`; resuming work --> same agent to re-assess `WIP.md`
- Plan ready --> `implementer`; implementation complete --> `verifier`
- Context artifacts stale/conflicting or plan touches them --> `context-engineer` (parallel with `researcher`/`systems-architect`)
- Ecosystem health or regression check --> `sentinel`; stale check: `.ai-state/SENTINEL_LOG.md` vs `git log -1 --format=%ci`
- Documentation impact likely --> `doc-engineer` (in background): feature planned in area with existing docs, implementation or refactoring complete, files added/removed/renamed, new public API or interface
- Pipeline complete + LEARNINGS.md has content --> `skill-genesis`

**Depth check:** Before spawning an agent recommended by another agent's output, confirm with the user if doing so would create a chain of 3+ agents from the original request.

**Multiplicity check:** Before spawning any Bg Safe agent, check whether the work decomposes into N independent targets with disjoint file sets. If so, spawn N instances (up to the concurrency limit in Intra-Stage Parallelism) rather than one sequential agent.

### Coordination Pipeline

Agents communicate through shared documents, not direct invocation.

```text
promethean --> researcher --> systems-architect --> implementation-planner --> implementer --> verifier
                                                                     context-engineer (any stage)
                                                                     doc-engineer (pipeline checkpoints)
                                                                     sentinel (independent audit)
```

**Pipeline rules:**

- **Do not skip stages.** Research before architecture (unless codebase context suffices). Re-invoke upstream agents when downstream input is incomplete.
- **Context-engineer** collaborates at any pipeline stage for context artifact work. Also operates independently for standalone audits.
- **Sentinel** is independent. Reports (`SENTINEL_REPORT_*.md`) are public -- any agent or user can consume them. Promethean may read them for ideation (its choice, not a pipeline handoff).
- Small-scope context work (single artifact) --> context-engineer directly; large-scope (3+) --> full pipeline.
- **Doc-engineer** is a proactive pipeline participant, not a cleanup agent. Invoke at natural checkpoints: after planning (assess documentation scope), after implementation (update affected docs), after refactoring (sync docs with structural changes). Runs in background when independent of other pipeline stages.

### Boundary Discipline

| Agent | Does | Does NOT |
|-------|------|----------|
| Promethean | Ideates through dialog, writes proposals | Research, design |
| Researcher | Presents options with trade-offs | Recommend |
| Architect | Designs structure, makes decisions | Plan steps |
| Planner | Decomposes and supervises | Redesign |
| Context Engineer | Manages information architecture, implements context artifacts | Implement features |
| Implementer | Receives and implements steps | Plan, skip, reorder steps |
| Verifier | Identifies issues, recommends actions | Fix issues |
| Doc-engineer | Proactively maintains project documentation at pipeline checkpoints | Manage context artifacts |
| Sentinel | Diagnoses and reports across ecosystem | Fix artifacts |
| Skill-Genesis | Triages learnings into artifact proposals, delegates creation | Ideate features, audit ecosystem, create artifacts |
| CI/CD Engineer | Designs and writes CI/CD pipelines, optimizes and debugs workflows | Modify application code, manage infrastructure |

When an agent encounters work outside its boundary, it flags the need and recommends invoking the appropriate agent.

### Agent Selection Criteria

Use an agent when the task benefits from a separate context window (large scope, multiple phases, structured output). Work directly for quick lookups, single changes, one-step edits.

| Situation | Use |
|-----------|-----|
| Multi-source research, architecture 3+ components, large feature decomposition | Agent |
| Ecosystem audit or 3+ context artifacts | `context-engineer` or `sentinel` |
| Post-implementation quality review | `verifier` |
| Documentation scope assessment, post-implementation doc updates, cross-reference fixes | `doc-engineer` |
| Feature-level ideation from project state | `promethean` |
| Post-pipeline learning harvest or 3+ accumulated LEARNINGS.md entries | `skill-genesis` |

### Background Agents

Run agents in the background when their output is not immediately needed (research, audits, parallel investigation). Check the Bg Safe column before using `run_in_background`. Monitor `.ai-work/PROGRESS.md` for status; check output before proceeding with dependent work.

### Delegation Depth

- **Depth 0-1:** Standard. **Depth 2:** Main agent decides. **Depth 3+:** Requires explicit user confirmation.
- Agents at depth 1 can recommend further agents but never auto-chain to depth 3+.

### Parallel Execution

Launch independent agents concurrently whenever possible.

| Parallelize | Do Not Parallelize |
|-------------|--------------------|
| Multiple independent research questions | One agent's output feeds the next (pipeline dependency) |
| Separate codebase areas needing analysis | Two agents analyzing and modifying the same files |
| Context audit alongside development planning | |
| Doc-engineer alongside implementer or verifier | |
| N same-type agents on disjoint work units (see Intra-Stage Parallelism) | Same-type agents whose file sets overlap |
| Context-engineer alongside researcher or systems-architect | |

### Intra-Stage Parallelism

Multiple instances of the same agent type can run concurrently on disjoint work units within a single pipeline stage. Distinct from cross-agent parallelism above. Limit to 2-3 concurrent agents.

**Direct-supervised** (any Bg Safe agent):

1. Main agent identifies N independent work units with disjoint file sets
2. Spawns N instances with `isolation: "worktree"` when agents modify files, each scoped to its target via the task prompt
3. Each instance reports independently
4. Main agent reviews all outputs for coherence

**Planner-supervised** (implementer under implementation-planner):

1. Planner prepares `WIP.md` in parallel mode with per-step assignees and file lists
2. Main agent spawns N implementer agents with `isolation: "worktree"`, each assigned one step
3. Each implementer updates only its own step status in `WIP.md`
4. After all report back, planner runs coherence review (re-reads modified files, verifies integration, merges learnings)

**Conflict avoidance:** Before spawning parallel instances, verify file disjointness across all work units. If an agent needs a file outside its declared set, it stops and reports `[CONFLICT]`.

### Multi-Perspective Analysis

For high-risk decisions, use parallel agents with distinct lenses: **correctness** (requirements satisfied?), **security** (vulnerabilities introduced?), **performance** (bottlenecks?), **maintainability** (evolvable?). Reserve for decisions with significant blast radius; most tasks need only the standard pipeline.

### Context-Engineer Pipeline Engagement

| Stage | Role | Trigger |
|-------|------|---------|
| Research | Domain expertise on context artifacts; evaluates findings through artifact placement lens | Research involves context engineering topics |
| Architecture | Artifact type selection, token budget, progressive disclosure constraints | Architecture affects context artifacts or introduces new conventions |
| Planning | Reviews step ordering for artifact dependencies, validates crafting spec compliance | Plan creates, modifies, or restructures context artifacts |
| Execution | Executes artifact steps using crafting skills; planner supervises | Large-scope context work (3+ artifacts, restructuring) |
| Verification | N/A (verifier checks code, not context artifacts) | Verifier finds planned context updates were skipped --> routes to context-engineer |

**Scale:** Single artifact --> context-engineer directly. 3+ artifacts or restructuring --> full pipeline under planner supervision.

### Doc-Engineer Pipeline Engagement

| Stage | Role | Trigger |
|-------|------|---------|
| Planning | Assess existing documentation in the affected area; flag docs that will need updates | Plan touches area with README, catalog, or architecture docs |
| Implementation | Update affected READMEs, catalogs, changelogs after code changes | Implementation adds, removes, or renames files; new public APIs or interfaces |
| Refactoring | Sync documentation with structural changes | Refactoring moves, renames, or reorganizes modules or directories |
| Verification | N/A (verifier checks code) | Verifier finds documentation updates were planned but not executed --> routes to doc-engineer |

**Timing:** Runs in background parallel with other agents when its work is independent. Post-implementation documentation updates can run alongside the verifier.

### Interaction Reporting

When the Task Chronograph MCP server is registered, call `report_interaction(source, target, summary, interaction_type)` at these moments:

| Moment | source | target | interaction_type |
|--------|--------|--------|-----------------|
| Receiving user query | `"user"` | `"main_agent"` | `"query"` |
| Delegating to agent | `"main_agent"` | `"{agent_type}"` | `"delegation"` |
| Receiving agent result | `"{agent_type}"` | `"main_agent"` | `"result"` |
| Making pipeline decision | `"main_agent"` | `"main_agent"` | `"decision"` |
| Responding to user | `"main_agent"` | `"user"` | `"response"` |
