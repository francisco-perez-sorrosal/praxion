---
name: software-planning
description: Planning complex software tasks using a three-document model (IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md) for tracking work in small, known-good increments. Use when starting significant development work, breaking down complex features, doing architecture planning, managing multi-session projects, or when the user mentions feature breakdown, work planning, work breakdown, task tracking, WIP management, or incremental development.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Software Planning in Small Increments

**All work must be done in small, known-good increments.** Each increment leaves the codebase in a working state.
Create and maintain planning documents (IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md) following the [agent intermediate documents](../../rules/swe/agent-intermediate-documents.md) placement convention.

**Satellite files** (loaded on-demand):

- [references/document-templates.md](references/document-templates.md) -- WIP.md and LEARNINGS.md templates, parallel mode, end-of-feature workflow
- [references/decomposition-guide.md](references/decomposition-guide.md) -- feature breakdown examples, spike steps, anti-patterns, Claude Code agent usage
- [references/agent-pipeline-details.md](references/agent-pipeline-details.md) -- boundary discipline, parallel execution, intra-stage parallelism, pipeline engagement tables
- [references/coordination-details.md](references/coordination-details.md) -- pipeline worktree lifecycle, BDD/TDD execution, batched improvement procedure, context-engineer/doc-engineer parallel details, fragment files
- [references/tier-templates.md](references/tier-templates.md) -- parametric tier-prompt scaffolds (Standard/Full/Lightweight) with seven angle-bracket placeholders; payload links to the coordination rule's delegation checklists
- [references/adr-authoring-protocols.md](references/adr-authoring-protocols.md) -- ADR file creation, index regeneration, supersession protocol
- [phases/refactoring.md](phases/refactoring.md) -- refactoring phase integration
- [contexts/python.md](contexts/python.md) -- Python-specific quality gates and step templates
- [assets/ARCHITECTURE_TEMPLATE.md](assets/ARCHITECTURE_TEMPLATE.md) -- 8-section template for `.ai-state/ARCHITECTURE.md` architect-facing design target
- [references/architecture-documentation.md](references/architecture-documentation.md) -- dual-audience architecture documentation methodology: lifecycle, section ownership, validation models for both architect and developer documents
- [references/behavioral-contract.md](references/behavioral-contract.md) -- four-behavior contract deep dive: definitions, per-agent application, objection templates, DRY relationship

## Three-Document Model

For significant work, maintain three documents:

| Document | Purpose | Lifecycle |
|----------|---------|-----------|
| **IMPLEMENTATION_PLAN.md** | What we're doing | Created at start, changes need approval |
| **WIP.md** | Where we are now | Updated constantly, always accurate |
| **LEARNINGS.md** | What we discovered | Temporary, merged at end then deleted |

### Document Relationships

```text
IMPLEMENTATION_PLAN.md (static)          WIP.md (living)           LEARNINGS.md (temporary)
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Goal            │       │ Current step    │       │ Gotchas         │
│ Acceptance      │  ──►  │ Status          │  ──►  │ Patterns        │
│ Steps 1-N       │       │ Blockers        │       │ Decisions       │
│ (approved)      │       │ Next action     │       │ Edge cases      │
└─────────────────┘       └─────────────────┘       └─────────────────┘

END OF FEATURE: Merge LEARNINGS into CLAUDE.md / ADRs, then DELETE all three docs
```

## Language Context

When planning work in a specific language or tech stack, load the relevant **context overlay** alongside this skill. Contexts augment the planning workflow with language-specific quality gates, step templates, and testing patterns — without duplicating content from language skills.

**Available contexts**:

| Context | File | Related Skills |
|---------|------|----------------|
| Python | [contexts/python.md](contexts/python.md) | [Python](../python-development/SKILL.md), [Python Project Management](../python-prj-mgmt/SKILL.md) |

**How contexts integrate**:

- **IMPLEMENTATION_PLAN.md**: Add a `Tech Stack` field linking to the relevant context and skills
- **Step templates**: Use language-specific templates for common step types (new module, add dependency, etc.)
- **Quality gates**: Run language-specific format → lint → type check → test before each commit
- **Testing field**: Choose testing approach based on language-specific patterns

If no context exists for your language, use the generic planning workflow and reference language-specific documentation directly.

## Phase Delegations

Some plan steps delegate to a **specialized skill** for their methodology. A phase is a group of consecutive steps that follow a specialized skill's workflow while remaining tracked by the plan.

**Available phases**:

| Phase | File | Delegated Skill |
|-------|------|-----------------|
| Refactoring | [phases/refactoring.md](phases/refactoring.md) | [Refactoring](../refactoring/SKILL.md) |

**How phases integrate**:

- **Detection**: During plan creation, look for signals that a phase is needed (each phase doc lists its signals)
- **Step marking**: Tag delegated steps with `[Phase: <Name>]` in the step title and a `Skill` field pointing to the delegated skill
- **Entry/exit criteria**: Each phase defines what must be true before starting and after completing
- **Scoped**: Phase steps serve the plan's goal — they are not open-ended improvement

**Delegated step template**:

```markdown
### Step N: [Phase: <Name>] One sentence description

**Skill**: [<Skill Name>](link/to/SKILL.md)
**Implementation**: What structural change will we make?
**Testing**: How do we verify behavior is preserved / new behavior works?
**Done when**: Concrete exit condition
```

**Contexts and phases compose**: A plan can use a language context (Python quality gates) *and* a phase (refactoring methodology) simultaneously. The context provides the quality checks; the phase provides the approach.

## Spec-Driven Development Integration

For medium and large features, the [spec-driven-development](../spec-driven-development/SKILL.md) skill provides behavioral specification format, requirement ID conventions, and traceability threading patterns. The two skills compose:

- **Software-planning** provides the three-document model, step decomposition, and execution workflow
- **Spec-driven-development** provides the behavioral specification format and requirement traceability
- The implementation-planner loads both when working on medium/large features
- Trivial and small tasks use software-planning alone — no spec overhead

The SDD skill is a **phase delegation** peer, not a dependency: planning works without it, and SDD methodology can be loaded independently for reference.

## What Makes a "Known-Good Increment"

Each step MUST:

- Leave the system in a working state
- Be independently testable
- Have clear done criteria
- Fit in a single commit
- Be describable in one sentence

**If you can't describe a step in one sentence, break it down further.**

## Step Size Heuristics

**Too big if:**

- Takes more than one session
- Requires multiple commits to complete
- Has multiple "and"s in description
- Involves more than 3-5 files
- Tests would be too complex to write

**Right size if:**

- One clear objective
- One logical change
- Can explain to someone in 30 seconds
- Obvious when done
- Single responsibility

## Testing in Plan Steps (BDD/TDD)

**Behavioral tests first.** Tests are designed from the acceptance criteria in the systems plan — they encode what the system should do, not how it does it. The test-engineer and implementer work concurrently on paired steps with disjoint file sets.

**Paired step pattern:**
1. **Test step** (test-engineer): design behavioral tests from acceptance criteria
2. **Implementation step** (implementer): write production code
3. **Integration checkpoint** (implementer): run full test suite, fix all failures including pre-existing broken tests (boy scout rule)

**Create paired test steps when:**

- The step implements behavioral acceptance criteria
- Complex algorithms or business logic
- Critical user flows or integration points
- Edge cases in important features
- Fixing bugs (regression tests)

**Skip paired test steps when:**

- Obvious code with no logic (simple wiring, config)
- Framework-provided functionality
- Code that will be deleted soon

## Commit Discipline

**NEVER commit without user approval.**

After completing a step:

1. Verify formatters and linters pass (fix mode already applied)
2. Verify type checker passes (if configured)
3. Run relevant tests if they exist
4. Verify system is in working state
5. Update WIP.md with progress
6. Capture any learnings in LEARNINGS.md
7. **STOP and ask**: "Ready to commit [description]. Approve?"

Only proceed with commit after explicit approval.

## IMPLEMENTATION_PLAN.md Structure

```markdown
# Plan: [Feature Name]

## Goal

[One sentence describing the outcome]

## Tech Stack

[Language/framework and relevant context, e.g., "Python 3.13 with pixi — see [Python context](contexts/python.md)"]

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Steps

### Step 1: [One sentence description]

**Implementation**: What code will we write?
**Testing**: What needs testing? (if critical/complex)
**Done when**: How do we know it's complete?

### Step N: [One sentence description]

**Implementation**: ...
**Testing**: ...
**Done when**: ...
```

**Acceptance criteria source**: In the agent pipeline, copy criteria verbatim from `SYSTEMS_PLAN.md` — the architect's criteria are authoritative and drive test design downstream. In manual planning (no `SYSTEMS_PLAN.md`), define criteria directly in the plan as concrete, testable conditions for "done."

### Plan Changes Require Approval

If the plan needs to change:

1. Explain what changed and why
2. Propose updated steps
3. **Wait for approval** before proceeding

Plans are not immutable, but changes must be explicit and approved.

## WIP.md Structure

Track current step, status (IMPLEMENTING/TESTING/REVIEWING/WAITING/COMPLETE), progress checklist, blockers, and next action. Supports sequential mode (default) and parallel mode for concurrent steps.

**If WIP.md doesn't reflect reality, update it immediately.** Update when starting a step, when status changes, when blockers appear/resolve, after each commit, and at end of each session.

--> See [references/document-templates.md](references/document-templates.md) for full WIP.md templates (sequential and parallel modes).

## LEARNINGS.md Structure

Sections: Gotchas, Patterns That Worked, Decisions Made, Edge Cases, Technical Debt. Capture learnings immediately as they occur -- don't wait until the end. Every entry must be tagged with the source: `**[agent-name]**` (e.g., `[implementation-planner]`, `[implementer]`, `[verifier]`, `[main-agent]`).

--> See [references/document-templates.md](references/document-templates.md#learningsmd-structure) for the full template.

When recording entries in `### Decisions Made`, decision-making agents (systems-architect, implementation-planner) also create an ADR file in `.ai-state/decisions/` following the [adr-conventions rule](../../rules/swe/adr-conventions.md). See the [ADR authoring protocols reference](references/adr-authoring-protocols.md) for the file creation workflow.

## Workflow

```text
START: Create IMPLEMENTATION_PLAN.md (get approval) + WIP.md + LEARNINGS.md

FOR EACH STEP:
  1. Update WIP.md (IMPLEMENTING)
  2. Write implementation + tests (if critical)
  3. Format → lint (fix mode) → type check → test
  4. Capture learnings, update WIP.md (WAITING)
  5. WAIT FOR COMMIT APPROVAL

END: Verify all criteria met, merge learnings, delete all three docs
```

### Context Compaction Checkpoints

In long pipelines, the main agent should run `/compact` at natural phase boundaries to keep context clean. Recommended points:

- **After research + architecture** (high file reading is done; implementation needs clean context)
- **After each implementation group completes** (test output and diffs accumulate)
- **Before verification** (verifier benefits from a focused context with just the plan and outcomes)

The `PreCompact` hook snapshots pipeline documents to `.ai-work/PIPELINE_STATE.md` automatically. After compacting, re-read that file and `WIP.md` to restore orientation. Use `/compact Focus on [current phase]` with a hint when context is dominated by a prior phase's artifacts.

## End of Feature

When all steps are complete: verify all acceptance criteria met, merge learnings to permanent locations (CLAUDE.md, ADRs, issue tracker), then delete all planning documents.

--> See [references/document-templates.md](references/document-templates.md#end-of-feature) for the full verification, merge, and cleanup workflow.

## Breaking Down Complex Features

Start with a specific goal (not vague), identify concrete acceptance criteria, then decompose by asking "What's the smallest change that moves toward the goal?" Validate each step can be described in one sentence and done in one session.

--> See [references/decomposition-guide.md](references/decomposition-guide.md) for a full worked example with OAuth2, step validation checklist, and spike steps for unknowns.

## Handling Unknowns

Use timeboxed **spike steps** for exploratory work. Spikes must produce a decision documented in LEARNINGS.md, then update the plan.

--> See [references/decomposition-guide.md](references/decomposition-guide.md#handling-unknowns) for spike step templates and characteristics.

## Anti-Patterns

Critical gotchas (most common planning failures):

- **Letting WIP.md become stale** -- state drift between plan and reality causes cascading wrong decisions downstream
- **Vague "done when" criteria** -- "when it works" is not verifiable; leads to premature step completion or scope creep
- **Changing plans silently** -- unannounced plan changes break coordination and trust; all changes require discussion and approval
- **Steps spanning multiple commits** -- violates the known-good-increment principle; if a step needs multiple commits, break it down further
- **Keeping planning docs after feature complete** -- stale documents pollute future context loads; merge learnings to permanent locations and delete

--> See [references/decomposition-guide.md](references/decomposition-guide.md#anti-patterns) for the full list of planning anti-patterns to avoid.

## When to Use This Skill

Three-document planning maps to the **Standard** and **Full** tiers in the [process calibration](../../rules/swe/swe-agent-coordination-protocol.md#process-calibration). Direct and Lightweight tiers use simpler tracking or none.

**Use three-document planning for:**

- Features taking multiple sessions
- Complex features with many moving parts
- Work with architectural implications
- Projects where requirements may evolve
- Collaborative work needing clear status
- Anything where you need to track progress over time

**Skip for simple tasks:**

- Bug fixes (unless complex)
- Simple feature additions (1-2 files)
- Refactoring within single module
- Documentation updates
- Configuration changes

For simple multi-step tasks, use the agent's built-in task tracking instead.

## Claude Code Usage

The `implementation-planner` agent uses this skill directly for step decomposition, document creation, and execution supervision. For manual planning without agents, use `Write` and `Edit` tools directly. For simple single-session tasks, use `TaskCreate`/`TaskUpdate`/`TaskList`.

--> See [references/decomposition-guide.md](references/decomposition-guide.md#claude-code-usage) for the full agent crew workflow and selection table.

## Quick Reference

### Update Triggers

| Trigger | Update |
|---------|--------|
| Start new step | WIP.md status and progress |
| Discover gotcha | LEARNINGS.md gotchas section |
| Make decision | LEARNINGS.md decisions section |
| Complete step | WIP.md progress checklist |
| Hit blocker | WIP.md blockers section |
| Plan changes | IMPLEMENTATION_PLAN.md + get approval |
| End of session | WIP.md next action |

### Checklist Before Commit Approval

- [ ] Formatters and linters pass (fix mode already applied)
- [ ] Type checker passes (if configured)
- [ ] Relevant tests pass (if tests exist)
- [ ] Language-specific quality gates pass (see [Language Context](#language-context))
- [ ] System is in working state
- [ ] WIP.md reflects current state
- [ ] Learnings captured if any
- [ ] Can describe change in one sentence
