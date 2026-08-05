---
id: dec-153
title: '`/review-interface` spawns the `interface-designer` agent in standalone mode — extending the Skill+Command family with a separate-context-window rule'
status: accepted
category: architectural
date: 2026-05-12
summary: /review-interface is a thin wrapper that spawns the interface-designer agent in standalone mode (dec-029's agent+skill+command shape, not dec-014/dec-015's bare Skill+Command), producing an Interface Design Review. Extends the pattern family with the rule — separate-context-window-for-cross-codebase-reasoning → agent; interactive-and-main-conversation-bound → Skill+Command.
tags: [architecture, command, interface-design, skill-command-pattern, review, pipeline]
made_by: agent
agent_type: systems-architect
branch: worktree-interface-design
pipeline_tier: full
affected_files:
  - commands/review-interface.md
  - agents/interface-designer.md
  - commands/README.md
---

## Context

Praxion has two established patterns for user-triggered cross-cutting workflows: the **bare Skill+Command** pattern (dec-014 upstream-stewardship, dec-015 project-exploration — methodology in a skill, trigger in a command, no agent, because those workflows are *interactive* and need the main conversation context) and the **agent+skill+command** pattern (dec-029 roadmap-creation — the workflow runs in its own context window, because it's a cross-codebase audit). Adding `interface-designer` (see `dec-149`) requires a standalone-mode trigger — a `/review-interface` slash command, peer to `/review-pr` (code-review). The question: does `/review-interface` follow dec-014/dec-015 (invoke skills in the main conversation) or dec-029 (spawn an agent)?

## Decision

`/review-interface` **spawns the `interface-designer` agent in standalone mode** (dec-029's shape). The command file (`commands/review-interface.md`) is a thin wrapper: frontmatter `description` / `argument-hint: [PR-number|branch|file|surface]` / `allowed-tools: [Bash, Read, Grep, Glob, Task]`; body = a numbered Process that (1) resolves the review target from `$ARGUMENTS` (PR → `gh pr diff`; branch → diff vs default; file → that file; surface name → the relevant directory/module; no arg → current branch vs default), (2) invokes `interface-designer` via the Task tool in standalone mode (instructing it to produce an Interface Design Review, not an `INTERFACE_DESIGN.md` — that's pipeline mode), (3) outputs the review (PASS/FAIL/WARN findings with file:line locations) in the conversation. The design knowledge lives in the agent and its four injected skills; the command is glue.

Rationale: interface design review is **not interactive** — it's a focused analysis pass over a target producing a structured report — and it needs **cross-codebase reasoning under trade-offs** (read the components, the CSS tokens, the API endpoints, the tool schemas; assess against the canon; weigh the findings). That profile is exactly dec-029's (roadmap-cartographer — agent for project-level audit), not dec-014/dec-015's (interactive, main-conversation-bound). `/review-pr` invokes a skill in the main conversation because PR review is line-scoped, not cross-codebase; `/review-interface` is broader, hence the agent. The `Task` allowed-tool is required for the agent invocation — a small, documented divergence from `/review-pr`'s tool set.

This decision **extends the Skill+Command pattern family** with an explicit rule: *when a user-triggered cross-cutting workflow needs a separate context window for cross-codebase reasoning, add an agent (dec-029's shape); when it's interactive and main-conversation-bound, keep it Skill+Command (dec-014/dec-015's shape).*

## Considered Options

### Option 1 — `/review-interface` invokes the four skills directly in the main conversation (dec-014/dec-015's bare Skill+Command pattern)

Rejected — interface design review isn't interactive (no back-and-forth with the user during the pass) and needs cross-codebase reasoning that would pollute the main conversation with the full codebase read. The skills would need manual loading. dec-014/dec-015's pattern fits *interactive* workflows; this isn't one.

### Option 2 — `/review-interface` spawns the `interface-designer` agent in standalone mode (dec-029's agent+skill+command shape) (chosen)

The review runs in an isolated context window, gets the four skills injected automatically, and uses the same agent that does pipeline-mode design (one agent, two modes — consistency with `context-engineer`).

- **Pro**: isolated context window; automatic skill injection; one agent two modes; the Skill+Command family gets a clarifying rule rather than a contradiction.
- **Con**: needs `Task` in `allowed-tools` (a documented divergence from `/review-pr`); spawning an agent has higher latency than an inline skill invocation — accepted because interface review is a deliberate, occasional action.

## Consequences

**Positive:**
- The standalone review runs isolated (doesn't pollute the main conversation with the full codebase read), gets the four skills injected automatically, and uses the same agent as pipeline mode — consistency with `context-engineer`.
- The Skill+Command pattern family gets a clarifying rule (separate-context-window-for-cross-codebase-reasoning → agent) rather than a contradiction.
- `/review-interface` is a true peer to `/review-pr` — `/review-pr` checks code conventions and test coverage; `/review-interface` checks interface design quality.

**Negative / accepted:**
- `/review-interface` needs `Task` in `allowed-tools` — documented in the command body with the rationale.
- Agent-spawn latency > inline-skill latency — accepted; interface review is occasional.

## Prior Decision

This decision **acknowledges and builds on** dec-014 (Skill+Command composition for upstream issue stewardship), dec-015 (Skill+Command composition for project exploration), and dec-029 (Shape B-hybrid — agent + skill + command — for roadmap-creation).

**Supersession of dec-014 / dec-015 was considered and rejected.** Neither is obsoleted by `/review-interface`: dec-014 chose Skill+Command-no-agent for upstream stewardship *because that workflow is interactive* (the user reviews the sanitized issue, edits it, decides whether to file) — that remains correct; dec-015 chose Skill+Command-no-agent for project exploration *because that workflow is interactive* (the developer asks follow-up questions in the same conversation) — that remains correct. `/review-interface` is a *fourth, distinct* feature decision (the standalone-mode trigger for the `interface-designer` agent), not a re-litigation of either prior — there is no single "review-command-shape" decision that dec-014/dec-015 made and `/review-interface` overturns, because dec-014/dec-015 are about *their* features, not about review-command shape in general. A supersession would dangle (`finalize_adrs.py` cannot rewrite already-finalized ADRs anyway) and would misrepresent the relationship. So this ADR stays `status: accepted` with **no frontmatter changes to dec-014, dec-015, or dec-029** — the implementer must not edit those files' `status:`/`superseded_by:` fields.

What this ADR *does* add is a **clarifying family rule** so the dec-014/dec-015 vs dec-029 distinction is explicit for future commands: *when a user-triggered cross-cutting workflow needs a separate context window for cross-codebase reasoning, add an agent (dec-029's shape); when it's interactive and main-conversation-bound, keep it Skill+Command (dec-014/dec-015's shape).* `/review-interface` is non-interactive cross-codebase analysis — the same profile that gave `roadmap-cartographer` an agent — so it follows dec-029's shape; `/review-pr` is line-scoped, not cross-codebase, so it stays a main-conversation skill invocation. The family rule is a *note*, not a re-affirmation in the formal ADR sense — none of the three priors was re-opened, so `status: re-affirmation` and the `re_affirms:` frontmatter field would both be inaccurate; `accepted` with this body section is the honest classification.

Pairs with `dec-149` (the agent whose standalone mode this command triggers). Recorded in `LEARNINGS.md ### Decisions Made` by the implementation-planner.
