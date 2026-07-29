# Document Templates and Lifecycle

Detailed templates for WIP.md and LEARNINGS.md, plus the end-of-feature workflow. Reference material for the [Software Planning](../SKILL.md) skill.

## WIP.md Structure

### Sequential Mode (default)

```markdown
# WIP: [Feature Name]

## Current Step

Step N of M: [Description]

## Status

[IMPLEMENTING] - Writing code
[TESTING] - Writing/running tests
[REVIEWING] - Checking quality
[WAITING] - Awaiting commit approval
[COMPLETE] - Step finished

## Progress

- [x] Step 1: [Description]
- [x] Step 2: [Description]
- [ ] Step 3: [Description] <- current
- [ ] Step 4: [Description]

## Blockers

[None / List current blockers]

## Next Action

[Specific next thing to do]

## Notes

[Optional: Brief notes about current work]

Tests: groups=[<group_id>, ...] tier=<step|phase|pipeline> selector=<auto|manual>
(Optional. Absence means topology protocol inactive — full suite runs. Mirrors the
**Tests**: field in IMPLEMENTATION_PLAN.md. See `skills/testing-strategy/references/test-topology.md`.)
```

### Parallel Mode

When the plan contains steps annotated with `[parallel-group]`, use the parallel format for batches of concurrent steps. Switch back to sequential mode for non-parallel steps.

```markdown
# WIP: [Feature Name]

## Current Batch

Mode: parallel
Steps: 3, 4
Status: in-progress

### Step 3 -- [Description]
- Assignee: implementer-1
- Status: [IN-PROGRESS]
- Files: path/to/file1.md, path/to/file2.md

### Step 4 -- [Description]
- Assignee: implementer-2
- Status: [IN-PROGRESS]
- Files: path/to/file3.md

## Progress

- [x] Step 1: [Description]
- [x] Step 2: [Description]
- [~] Step 3: [Description] <- parallel batch
- [~] Step 4: [Description] <- parallel batch
- [ ] Step 5: [Description]

## Blockers

[None / List current blockers]

## Next Action

Wait for all parallel implementers to complete, then run coherence review.
```

**Parallel mode rules:**

- Each implementer updates only its own step's `Status` field -- never another step's
- The planner writes the `Current Batch` header, `Mode`, `Steps`, and `Assignee` fields
- After all implementers report back, the planner runs a coherence review and advances to the next batch or step
- Use `[~]` in the Progress checklist to indicate in-progress parallel steps

### WIP Must Always Be Accurate

Update WIP.md:

- When starting a new step
- When status changes
- When blockers appear or resolve
- After each commit
- At end of each session

**If WIP.md doesn't reflect reality, update it immediately.**

## LEARNINGS.md Structure

```markdown
# Learnings: [Feature Name]

## Assumptions & Constraints Taken
- **[agent-name] [Title]**: The gap-filling assumption or constraint taken; mark the load-bearing ones and record the self-challenge result. Captured as taken — the orchestrator harvests this section to compose Conversation-checkpoint digests.

## Gotchas
- **[implementation-planner] [Title]**: Context, issue, solution
- **[implementer] [Title]**: Context, issue, solution

## Patterns That Worked
- **[implementer] [Title]**: What, why it works, brief example

## Decisions Made
- **[implementation-planner] [Title]**: Options considered, decision, rationale, trade-offs

## Edge Cases
- **[implementer]** [Edge case]: How we handled it
```

### Attribution Convention

Every entry must be prefixed with the source agent or actor in brackets: `**[agent-name]**`. This makes authorship unambiguous when multiple agents write to the same file. Common sources: `[implementation-planner]`, `[implementer]`, `[verifier]`, `[main-agent]`.

### Capture Learnings As They Occur

Don't wait until the end. When you discover something:

1. Add it to LEARNINGS.md immediately with your `**[agent-name]**` tag
2. Continue with current work
3. At end of feature, learnings are ready to merge

The `## Assumptions & Constraints Taken` section follows the same rule — record each load-bearing assumption the moment you take it, not batched at end-of-task, so a [Conversation Checkpoint](coordination-details.md#conversation-checkpoints) digests an accurate, current set.

## Handoff Prompt Structure

Generated on request from `WIP.md` + `TASK_BRIEF.md` (when present) + `LEARNINGS.md`, to resume work in a fresh session. A handoff prompt is a different artifact from a `WIP.md` "Next Action" line — it must stand alone for a session with zero prior context, so it carries the same explicit/disambiguated/test-criteria discipline the [`goal-disambiguation`](../../goal-disambiguation/SKILL.md) skill already applies at task intake, applied a second time at the handoff seam.

```markdown
Resume [Feature Name] (task slug: <slug>) — read `.ai-work/<slug>/WIP.md` and `.ai-work/<slug>/LEARNINGS.md` first.

**Goal**: <one sentence, from TASK_BRIEF.md Intent — the actual behavior being built, not "continue the work">

**Where it stands**: Step N of M complete. Current step: <WIP.md Current Step + Status>.

**Constraints already decided** (don't re-litigate): <load-bearing assumptions from LEARNINGS.md § Assumptions & Constraints Taken>

**Next action**: <WIP.md Next Action field, verbatim>

**Verify it worked by**: <the acceptance criterion or test command for the current step — from TASK_BRIEF.md Key Signals or IMPLEMENTATION_PLAN.md's Tests: field>
```

**Rules:**

- **`Verify it worked by` is mandatory whenever a source for it exists** (`TASK_BRIEF.md` Key Signals or the plan's `Tests:` field) — never skip composing it just because it's inconvenient. A handoff prompt that drops an available verification path reintroduces the exact ambiguity `goal-disambiguation` exists to prevent, one session later with less context to catch it.
- **Omit fields with no source rather than inventing content.** When `TASK_BRIEF.md` is absent (Direct/Lightweight tier, no pipeline), compose from `WIP.md` and conversational context alone; do not fabricate a Goal, Key Signal, or verification path that was never captured. This rule governs every field equally — `Verify it worked by` included — the "mandatory" clause above is about not skipping an available source, not about guaranteeing the field always appears.
- **This is a template, not a command.** Compose it inline when a user asks to continue elsewhere — it does not require its own pipeline document or tooling to exist.

## End of Feature

When all steps are complete:

### 1. Verify Completion

- All acceptance criteria met
- System is working
- Critical components tested
- All steps marked complete in WIP.md

### 2. Merge Learnings

Review LEARNINGS.md and determine destination:

| Learning Type | Destination | Notes |
|---------------|-------------|-------|
| Gotchas | CLAUDE.md | Add to relevant section |
| Patterns | CLAUDE.md | Document successful approaches |
| Architectural decisions | ADR or CLAUDE.md | Significant decisions get ADRs |
| Domain knowledge | Project docs | Update relevant documentation |

### 3. Verify ADR Consistency

- Verify that ADR files in `.ai-state/decisions/` covering the feature period are consistent with the decisions merged from `LEARNINGS.md`. Check for decisions in LEARNINGS.md that lack corresponding ADR files (may indicate the ADR creation protocol was not followed), and ADR files without corresponding LEARNINGS.md entries (unusual but not necessarily an error).

### 4. Delete Documents

After learnings are merged, delete all planning documents (see [agent intermediate documents](../../../rules/swe/agent-intermediate-documents.md) for cleanup instructions).

**The knowledge lives on in:**

- CLAUDE.md (gotchas, patterns, decisions)
- Git history (what was done)
- Project documentation (if applicable)

## TEST_RESULTS.md Schema

The canonical `TEST_RESULTS.md` schema (section headers, pass/fail/skip counts, failure blocks, coverage, fragment naming) is defined in [`agent-pipeline-details.md`](agent-pipeline-details.md) under `### TEST_RESULTS.md Reconciliation`.

**Test-topology optional fields**: when a step has a `Tests:` field activating the topology protocol, the `TEST_RESULTS.md` step section may include additional topology lines after the standard counts. These lines are optional and backward-compatible — see `agent-pipeline-details.md` for the extended schema.
