# Agent Pipeline Details

Detailed tables and specifications for the SWE agent coordination pipeline. This reference supplements the always-loaded [coordination protocol rule](../../../rules/swe/swe-agent-coordination-protocol.md) with information agents load on demand.

## Boundary Discipline

| Agent | Does | Does NOT |
|-------|------|----------|
| Promethean | Ideates through dialog, writes proposals | Research, design |
| Researcher | Presents options with trade-offs | Recommend |
| Architect | Designs structure, makes decisions | Plan steps |
| Planner | Decomposes and supervises | Redesign |
| Context Engineer | Manages information architecture, implements context artifacts, shadows research/architecture stages with `CONTEXT_REVIEW.md` | Implement features |
| Implementer | Implements steps, makes tests pass, fixes broken pre-existing tests | Plan, skip, reorder steps |
| Test-Engineer | Designs behavioral tests from acceptance criteria, writes test suites concurrently with implementer | Write production code, modify plans |
| Verifier | Identifies issues, recommends actions | Fix issues |
| Doc-engineer | Proactively maintains project documentation at pipeline checkpoints and in parallel execution during implementation | Manage context artifacts |
| Sentinel | Diagnoses and reports across ecosystem | Fix artifacts |
| Skill-Genesis | Triages learnings into artifact proposals, delegates creation | Ideate features, audit ecosystem, create artifacts |
| CI/CD Engineer | Designs and writes CI/CD pipelines, optimizes and debugs workflows | Modify application code, manage infrastructure |

When an agent encounters work outside its boundary, it flags the need and recommends invoking the appropriate agent.

## Agent Selection Criteria

| Situation | Use |
|-----------|-----|
| Multi-source research, architecture 3+ components, large feature decomposition | Agent |
| Ecosystem audit or 3+ context artifacts | `context-engineer` or `sentinel` |
| Complex test design, test suite refactoring, testing infrastructure setup | `test-engineer` |
| Post-implementation quality review | `verifier` |
| Documentation scope assessment, post-implementation doc updates, cross-reference fixes | `doc-engineer` |
| Feature-level ideation from project state | `promethean` |
| Post-pipeline learning harvest or 3+ accumulated LEARNINGS.md entries | `skill-genesis` |

## Parallel Execution

Launch independent agents concurrently whenever possible.

| Parallelize | Do Not Parallelize |
|-------------|--------------------|
| Multiple independent research questions | One agent's output feeds the next (pipeline dependency) |
| Separate codebase areas needing analysis | Two agents analyzing and modifying the same files |
| Context audit alongside development planning | |
| Doc-engineer alongside implementer or verifier | |
| Implementer + test-engineer on paired steps (disjoint: production vs test files) | Implementer + test-engineer modifying the same files |
| Implementer + test-engineer + doc-engineer on triple steps (disjoint: production / test / doc files) | Doc-engineer modifying files that overlap with production or test code |
| N same-type agents on disjoint work units (see Intra-Stage Parallelism) | Same-type agents whose file sets overlap |
| Context-engineer alongside researcher or systems-architect | |

## Intra-Stage Parallelism

Multiple instances of the same agent type can run concurrently on disjoint work units within a single pipeline stage. Distinct from cross-agent parallelism above. Limit to 2-3 concurrent agents.

**Direct-supervised** (any Bg Safe agent):

1. Main agent identifies N independent work units with disjoint file sets
2. Spawns N instances with `isolation: "worktree"` when agents modify files, each scoped to its target via the task prompt
3. Each instance reports independently
4. Main agent reviews all outputs for coherence

**Planner-supervised** (implementer/test-engineer under implementation-planner):

1. Planner prepares `WIP.md` in parallel mode with per-step assignees and file lists
2. Main agent spawns N implementer or test-engineer agents with `isolation: "worktree"`, each assigned one step
3. Each agent updates only its own step status in `WIP.md`
4. After all report back, planner runs coherence review (re-reads modified files, verifies integration, merges learnings)

**Conflict avoidance:** Before spawning parallel instances, verify file disjointness across all work units. If an agent needs a file outside its declared set, it stops and reports `[CONFLICT]`.

## Multi-Perspective Analysis

For high-risk decisions, use parallel agents with distinct lenses: **correctness** (requirements satisfied?), **security** (vulnerabilities introduced?), **performance** (bottlenecks?), **maintainability** (evolvable?). Reserve for decisions with significant blast radius; most tasks need only the standard pipeline.

## Context-Engineer Pipeline Engagement

| Stage | Role | Trigger |
|-------|------|---------|
| Research | Domain expertise on context artifacts; evaluates findings through artifact placement lens. **Shadowing:** runs in parallel with researcher, writes `## Research Stage Review` in `CONTEXT_REVIEW.md` | Research involves context engineering topics; task creates/modifies/restructures context artifacts |
| Architecture | Artifact type selection, token budget, progressive disclosure constraints. **Shadowing:** runs in parallel with architect, reads research-stage review, appends `## Architecture Stage Review` to `CONTEXT_REVIEW.md` | Architecture affects context artifacts or introduces new conventions |
| Planning | Reviews step ordering for artifact dependencies, validates crafting spec compliance. Reads full `CONTEXT_REVIEW.md` | Plan creates, modifies, or restructures context artifacts |
| Execution | Executes artifact steps using crafting skills; planner supervises | Large-scope context work (3+ artifacts, restructuring) |
| Verification | N/A (verifier checks code, not context artifacts) | Verifier finds planned context updates were skipped --> routes to context-engineer |

**Scale:** Single artifact --> context-engineer directly. 3+ artifacts or restructuring --> full pipeline under planner supervision.

**Shadowing activation:** Conditional — only when the task involves context artifacts. Pure application code does not trigger shadowing. `CONTEXT_REVIEW.md` is cumulative (stage-delimited sections) and single-writer (context-engineer only).

## Doc-Engineer Pipeline Engagement

| Stage | Role | Trigger |
|-------|------|---------|
| Planning | Assess existing documentation in the affected area; flag docs that will need updates | Plan touches area with README, catalog, or architecture docs |
| Execution | **Parallel mode:** runs concurrently with implementer + test-engineer on planner-assigned doc steps, updating documentation files (disjoint file sets). Writes to fragment files (`WIP_doc-engineer.md`, etc.) | Planner assigns a doc step to the parallel group (files added/removed/renamed, new APIs, module structure changes) |
| Implementation (checkpoints) | Update affected READMEs, catalogs, changelogs after code changes | Implementation adds, removes, or renames files; new public APIs or interfaces (when no parallel doc step was assigned) |
| Refactoring | Sync documentation with structural changes | Refactoring moves, renames, or reorganizes modules or directories |
| Verification | N/A (verifier checks code) | Verifier finds documentation updates were planned but not executed --> routes to doc-engineer |

**Timing:** In parallel execution mode, runs as part of the implementation batch (up to 3 concurrent agents per group). At pipeline checkpoints, runs in background parallel with other agents when its work is independent. Post-implementation documentation updates can run alongside the verifier.

## Interaction Reporting

When the Task Chronograph MCP server is registered, call `report_interaction(source, target, summary, interaction_type)` at these moments:

| Moment | source | target | interaction_type |
|--------|--------|--------|-----------------|
| Receiving user query | `"user"` | `"main_agent"` | `"query"` |
| Delegating to agent | `"main_agent"` | `"{agent_type}"` | `"delegation"` |
| Receiving agent result | `"{agent_type}"` | `"main_agent"` | `"result"` |
| Making pipeline decision | `"main_agent"` | `"main_agent"` | `"decision"` |
| Responding to user | `"main_agent"` | `"user"` | `"response"` |

## Semantic Document Reconciliation

When concurrent agents write to fragment files (`WIP_<agent>.md`, `LEARNINGS_<agent>.md`, `PROGRESS_<agent>.md`), the supervising agent (implementation-planner) merges fragments into canonical documents after all agents in a batch complete. All fragment files and canonical documents live inside the task-scoped directory (`.ai-work/<task-slug>/`). Each document type has its own schema and merge semantics -- naive concatenation produces structurally invalid documents.

**Note:** `CONTEXT_REVIEW.md` is not subject to fragment patterns — it is single-writer (context-engineer only) with cumulative stage-delimited sections. No reconciliation needed.

### WIP.md Reconciliation

**Schema:**

```
## Current Batch
Mode: parallel
Steps: N, M
Status: in-progress

### Step N -- [Description]
- Assignee: [agent-type]
- Status: [IN-PROGRESS|COMPLETE|BLOCKED|CONFLICT]
- Files: [file list]

## Progress
- [x] Step 1: ...
- [~] Step N: ... <- parallel batch
- [ ] Step K: ...
```

**Fragment structure:** Each `WIP_<agent>.md` (e.g., `.ai-work/<task-slug>/WIP_implementer.md`, `WIP_test-engineer.md`, `WIP_doc-engineer.md`) contains a single `### Step N` section with an updated `Status` field. No batch header, no progress checklist, no blockers section.

**Merge procedure:**

1. Read each `WIP_<agent>.md` from `.ai-work/<task-slug>/`. Extract the step number (from `### Step N`) and the new `Status` value.
2. In canonical `.ai-work/<task-slug>/WIP.md`, locate `### Step N` under `## Current Batch`. Update the `Status` field.
3. In `## Progress`, update the step marker: `[~]` becomes `[x]` if `COMPLETE`, stays `[~]` if `IN-PROGRESS`, becomes `[!]` if `BLOCKED` or `CONFLICT`.
4. If all batch steps show `COMPLETE`: set batch `Status: complete`, update `## Next Action`.
5. If any step shows `BLOCKED`/`CONFLICT`: add the blocker to `## Blockers`.
6. Delete fragment files after successful update.

**Post-merge invariants:** Exactly one `### Step N` per step (no duplicates). Every step in `Steps:` has a section. Progress checklist has one entry per plan step. Statuses from closed set. Batch `Status` is `complete` iff all steps are `COMPLETE`.

### LEARNINGS.md Reconciliation

**Schema:** Five fixed topic sections (`## Gotchas`, `## Patterns That Worked`, `## Decisions Made`, `## Edge Cases`, `## Technical Debt`). Entries are bullet points with `**[agent-name]**` attribution.

**Fragment structure:** Each `LEARNINGS_<agent>.md` (in `.ai-work/<task-slug>/`) contains only the topic sections the agent has entries for, with entries under `##` headings matching canonical section names.

**Merge procedure:**

1. Read each `LEARNINGS_<agent>.md` from `.ai-work/<task-slug>/`. For each `## [Topic]` section, extract bullet-point entries.
2. In canonical `.ai-work/<task-slug>/LEARNINGS.md`, locate the matching `## [Topic]` section. Append entries at the end.
3. If a fragment contains an unrecognized `## [Topic]` header: create a `## Uncategorized` section and place entries there.
4. Entry order within a section reflects merge order (no re-sorting -- entries are unordered within topics).
5. Delete fragment files after successful merge.

**Deduplication:** Do not deduplicate by content. Different agents may report similar learnings from different perspectives -- both are valuable. Flag suspicious near-duplicates for human review during end-of-feature learnings merge.

**Post-merge invariants:** Every entry has `**[agent-name]**` attribution. Every entry under a topic section. No duplicate `## [Topic]` headers. File header present exactly once.

### PROGRESS.md Reconciliation

**Schema:** Timestamped log lines, one per entry:

```
[TIMESTAMP] [AGENT] Phase N/M: [phase-name] -- [summary] #label1 #key=value
```

Append-only. Entries in chronological order by timestamp.

**Fragment structure:** Each `PROGRESS_<agent>.md` (in `.ai-work/<task-slug>/`) contains the agent's own entries in the same format, chronologically ordered within the fragment.

**Merge procedure:**

1. Read canonical `.ai-work/<task-slug>/PROGRESS.md` and all `PROGRESS_<agent>.md` fragments from the same directory.
2. Collect all fragment entries into a single list.
3. Sort by timestamp (ISO 8601 prefix enables lexicographic sorting).
4. Append sorted entries to canonical `PROGRESS.md`. Do not re-sort existing canonical entries.
5. Delete fragment files after successful append.

**Validation:** No two entries with the same timestamp + agent + phase number (discard duplicates). Phase transitions per agent should be monotonically increasing -- non-monotonic transitions are warnings, not merge failures.

**Post-merge invariants:** All entries in timestamp order. Every entry matches the format pattern. No exact-duplicate entries.

### .ai-state/ Reconciliation for Worktree Merges

When worktree branches are merged, `.ai-state/` documents are subject to git merge semantics. Most avoid conflicts by design (timestamped filenames), but two cases need attention:

- **SENTINEL_LOG.md** — append-only table. If merge conflicts arise, resolve by keeping both entries in timestamp order. Git usually auto-merges concurrent appends.
- **IDEA_LEDGER_\*.md** — each promethean run creates a timestamped file carrying forward previous entries. If two worktrees both run promethean, the later ledger may miss the earlier's new entries. Create a reconciled ledger with suffix `_reconciled` containing the union of both.
- **specs/** — unique feature-name filenames. No reconciliation needed -- git merge handles distinct file additions natively.

### Post-Worktree .ai-work/ State Reconciliation

`.ai-work/` is gitignored, so git merge does not touch it. After merging a worktree branch, the main worktree's `.ai-work/` may contain stale state.

**Reconciliation procedure:**

1. Check if `.ai-work/<task-slug>/WIP.md` exists in the main worktree.
2. Compare the `## Progress` checklist against git log: check if commits for "completed" steps exist on the current branch.
3. Update steps whose implementation is visible in git history but marked incomplete: set status to `[COMPLETE]`, marker to `[x]`.
4. Incorporate `LEARNINGS.md` entries from the merged worktree using the topic-section merge protocol above.
5. Same for `PROGRESS.md` fragments.

This is a safety net -- normal reconciliation happens before worktree merge during the planner's batch supervision.
