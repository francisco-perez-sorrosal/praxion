# Feature Decomposition Guide

Techniques for breaking down complex features into incremental steps, handling unknowns, and avoiding common planning mistakes. Reference material for the [Software Planning](../SKILL.md) skill.

## Breaking Down Complex Features

### Start with the Goal

**Bad**: "Improve user authentication"
**Good**: "Add OAuth2 login alongside existing email/password authentication"

### Identify Acceptance Criteria

What does "done" look like?

- [ ] Users can log in with Google OAuth2
- [ ] Existing email/password login still works
- [ ] User accounts are linked correctly
- [ ] Error states are handled gracefully

### Decompose into Steps

Ask: "What's the smallest change that moves toward the goal?"

Before listing feature steps, check for **phase signals** -- does the current codebase need preparatory work (refactoring, migration, etc.) before the feature can be built cleanly? If yes, prepend a [phase delegation](../SKILL.md#phase-delegations) to the step list.

**Example breakdown:**

1. Add OAuth2 library dependency
2. Create OAuth2 configuration module
3. Implement OAuth2 callback handler
4. Add user account linking logic
5. Update login UI to show OAuth2 option
6. Add error handling for OAuth2 failures
7. Test integration with Google OAuth2

Each step is one commit, leaves system working.

### Validate Step Size

For each step, ask:

- Can I describe this in one sentence? (yes)
- Can I do this in one session? (yes)
- Will the system still work after? (yes)
- Is it obvious when I'm done? (yes)

If any answer is "no", break it down further.

## Handling Unknowns

### Spike Steps

For exploratory work, add spike steps:

```markdown
### Step 2: Spike - Investigate OAuth2 library options

**Implementation**: Research and test 2-3 OAuth2 libraries
**Done when**: Decision made and documented in LEARNINGS.md
**Timebox**: 1 hour max
```

**Spike characteristics:**

- Timeboxed exploration
- May not result in production code
- Must produce a decision
- Document findings in LEARNINGS.md

After a spike, update the plan: document findings in LEARNINGS.md, propose plan changes, get approval, then continue.

<a id="step-risk-tagging"></a>
## Step Risk Tagging

The planner annotates steps with risk signals so the orchestrator can decide at step completion whether to spawn an intra-step pair-review. This annotation is part of step decomposition (Phase 3–4 of the implementation-planner process).

### `tier: H` — High-complexity step

Add `tier: H` to a step when the change is cross-cutting, high-complexity, or architecturally load-bearing:

| Signal | Example |
|--------|---------|
| Touches 4+ files across package boundaries | Core abstraction shared by many consumers |
| Refactors or replaces a central interface | Auth session handler, configuration loader |
| Architect flagged the step as high-risk in `SYSTEMS_PLAN.md § Risk Assessment` | Migration, permission model change |
| Implementer was routed to `tier: H` override in `agent-model-routing.md` | Cross-codebase refactor |

```markdown
### Step N: [Cross-cutting refactor description]

tier: H
**Implementation**: ...
**Files**: ...
**Done when**: ...
```

The `tier: H` annotation is already used by `agent-model-routing.md` to route the implementer to `opus`. The intra-step pair-review feature additionally reads this tag as a RISKY signal to spawn a reviewer.

### `review: force` and `review: off`

Planner overrides — higher precedence than every auto-signal:

```markdown
**review**: force   # spawn reviewer regardless of signals
**review**: off     # suppress reviewer regardless of signals
```

When to use `force`: the planner judges the step risky independent of signals (e.g., a simple-looking step that changes a critical invariant).

When to use `off`: the planner judges the step safe despite signals (e.g., a `tier: H` step whose diff is mechanical and already verified by a paired test).

Full procedure and composition table: [`intra-step-review.md`](intra-step-review.md).

## Anti-Patterns

**Don't:** Commit without approval -- always wait for explicit "yes" before committing

**Don't:** Let steps span multiple commits -- break down further until one step = one commit

**Don't:** Use vague "done when" criteria -- "when it works" is not specific enough. Be concrete: "When users can log in with Google and existing tests pass"

**Don't:** Let WIP.md become stale -- update immediately when reality changes

**Don't:** Wait until end to capture learnings -- add to LEARNINGS.md as discoveries occur

**Don't:** Change plans silently -- all plan changes require discussion and approval

**Don't:** Keep planning docs after feature complete -- delete them; knowledge is now in permanent locations

**Don't:** Skip tests for complex logic -- critical and complex components need tests; don't defer testing indefinitely

## Claude Code Usage

When using this skill with Claude Code specifically:

- The **development crew** (`researcher` -> `systems-architect` -> `implementation-planner`) splits the planning workflow into focused phases. The `implementation-planner` agent uses this skill directly -- it owns step decomposition, document creation (`IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md`), and execution supervision.
- The **`researcher` agent** gathers codebase and external information into `RESEARCH_FINDINGS.md`.
- The **`systems-architect` agent** produces `SYSTEMS_PLAN.md` (Goal, Criteria, Architecture, Risks).
- The **`implementation-planner` agent** produces `IMPLEMENTATION_PLAN.md` with incremental steps and maintains `WIP.md` and `LEARNINGS.md`.
- For **manual planning** without agents, use `Write` and `Edit` tools to create and maintain IMPLEMENTATION_PLAN.md, WIP.md, and LEARNINGS.md directly.
- For simple multi-step tasks that don't warrant three-document planning, use `TaskCreate`/`TaskUpdate`/`TaskList` to track micro-tasks within a session.
- Both approaches can coexist: task tools track current session's micro-tasks while IMPLEMENTATION_PLAN.md tracks overall feature steps.

| Use the agent crew when: | Use manual planning when: | Use Task Tools when: |
|--------------------------|---------------------------|----------------------|
| New feature or architectural change | Iterative plan refinement | Single-session task |
| Need codebase analysis first | Plan already exists | Simple checklist |
| Starting from scratch | Adjusting existing steps | Independent tasks |
| Complex scope requiring risk assessment | User wants direct control | Clear requirements |
| Trade-off analysis needed | Minor plan adjustments | No plan needed |
| Supervising execution against a plan | -- | -- |
