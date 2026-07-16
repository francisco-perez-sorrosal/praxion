---
id: dec-186
title: "Skill-genesis: pull-driven autonomous-report inversion with deferred disposition via /skill-genesis-review"
status: accepted
category: behavioral
date: 2026-05-15
summary: "Invert skill-genesis from interactive end-of-pipeline blocker to autonomous background report writer; user dispositions via new /skill-genesis-review batch multi-select command; auto-fire trigger removed."
tags: [skill-genesis, agent-pipeline, ux, coordination-protocol, slash-commands, pull-driven, behavioral-inversion]
made_by: agent
agent_type: systems-architect
branch: worktree-skill-genesis-pull-driven
pipeline_tier: standard
affected_files:
  - agents/skill-genesis.md
  - commands/skill-genesis.md
  - commands/skill-genesis-review.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/agent-model-routing.md
  - skills/software-planning/references/agent-pipeline-details.md
  - .ai-state/DESIGN.md
  - docs/skill-genesis.md
re_affirms: # none — fresh decision per researcher's ADR survey
re_affirmed_by:
  - dec-187
---

## Context

`skill-genesis` is the pipeline's post-run learning harvester. It analyses `LEARNINGS.md`, memory entries, verification reports, sentinel findings, and ADR patterns, triages them into proposed artifacts (skills, rules, memory entries, CLAUDE.md additions), and presents each proposal interactively to the user one at a time via `AskUserQuestion`.

Two friction modes accumulated over the verifier-rework-loop pipeline session and were captured in `ROADMAP.md` Topic 3:

1. **The interactive AskUserQuestion-per-proposal pattern paused the agent mid-run.** During Praxion's own verifier-rework-loop pipeline, skill-genesis presented Proposal 1 of 4 and waited for the user's disposition. The user dispositioned it, but the agent could not be resumed: `SendMessage` is not available in the current Claude Code tool surface and subagents cannot spawn other agents (confirmed convention). The orchestrator had to materialize Proposal 1 manually and explicitly skip Proposals 2–4. The interactive loop was load-bearing but unresumable.
2. **Skill-genesis runs at end-of-pipeline, when the user is least interested in another decision cycle.** A long pipeline lands, the merge succeeds, ADRs finalize — and then the system asks "by the way, want to harvest 4 patterns into new skills?" The cognitive load lands on top of an already-saturated session.

A research pass (`.ai-work/skill-genesis-pull-driven/RESEARCH_FINDINGS.md`) confirmed:

- **No existing ADR** establishes "auto-fire at end-of-pipeline" as a decided policy. The pattern emerged from a single line in `rules/swe/swe-agent-coordination-protocol.md` (line 98), not from a deliberate architectural decision. Seven ADRs (`dec-029`, `dec-043`, `dec-051`, `dec-117`, `dec-139`, `dec-140`, `dec-183`) mention skill-genesis incidentally; none of them is a supersession target. This is a fresh decision, not an overturn.
- **Sentinel is the canonical autonomous-report precedent**: `agents/sentinel.md` runs without `AskUserQuestion`, has `background: true`, writes timestamped `SENTINEL_REPORT_*.md` files in `.ai-state/sentinel_reports/`, and accumulates a sibling `SENTINEL_LOG.md`. The same primitives transfer cleanly to skill-genesis.
- **`/roadmap` is the precedent** for "previously-auto-pipeline agent now accessible as an on-demand command" — the roadmap-cartographer, like the proposed pull-driven skill-genesis, is invoked via a slash command rather than auto-triggered mid-pipeline.
- **The Diátaxis how-to shape** is the right home for a new user-facing doc; `docs/rework-dispatch.md` is the closest structural precedent (it opens with a "Why this guide exists" section explaining the cognitive-load problem the dispatcher solves — exactly the structural move this work needs).

The user accepted the inversion bundle (A+C from ROADMAP Topic 3 — autonomous mode plus decouple-from-merge) before this pipeline started; this ADR codifies the decision.

## Decision

Invert `skill-genesis` from a push-driven interactive blocker to a pull-driven autonomous report writer, paired with a new on-demand `/skill-genesis-review` command for deferred disposition. Four coupled changes:

1. **Agent (`agents/skill-genesis.md`) becomes autonomous and background-safe.** Drop `AskUserQuestion` from `tools:`; add `background: true`; add `disallowedTools: Edit` (mirror sentinel's read-only-except-own-output stance); rewrite Phase 5 ("Interactive Proposals") to "Report Synthesis" — all triaged items become proposals in the report with `Disposition: pending`; rewrite Phase 6 to populate a `## Recommended Delegations` table in the report rather than executing delegations inline; redirect Phase 7's output from `.ai-work/<task-slug>/SKILL_GENESIS_REPORT.md` to `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<YYYY-MM-DD_HH-MM-SS>.md` with a `SKILL_GENESIS_LOG.md` sibling for run history.

2. **Memory entries become pending proposals, not auto-stores.** The current "execute `remember()` inline after user approval" path is replaced by "list memory entries as `pending` proposals in the report; `/skill-genesis-review` executes the `remember()` call after disposition." Structural consequence: every artifact type now has the same approval gate; the agent never creates anything, including memory entries.

3. **New `commands/skill-genesis-review.md` is the disposition surface.** Auto-discovers the most recent report whose frontmatter `review_status` is `pending` or `partial`; batch-presents all pending proposals in a single `AskUserQuestion` multi-select (paginated 10-at-a-time when N > 20); for each user-selected proposal, asks for one of four dispositions (approve / reject / refine / defer) via per-proposal `AskUserQuestion` follow-ups; appends rows to the report's `## Disposition Log` section; updates the report's frontmatter `review_status` and `disposition_count`; updates the run-log's Review Status column in place; executes `remember()` for approved memory proposals; surfaces a delegation-handoff confirmation step for approved skill / rule / claude.md proposals before any downstream agent spawns. Idempotent on re-run — a fully-dispositioned report exits with a no-op message.

4. **New `commands/skill-genesis.md` is the invocation surface; auto-fire is removed.** Thin command delegating to the skill-genesis agent via `Task`, with optional `--since <commit>` / `--scope <area>` / `--dry-run` flags. The coordination-protocol line `Pipeline complete + LEARNINGS.md has content --> skill-genesis` is deleted; the corresponding agent-table row has `Bg Safe` flipped from `No` to `Yes` and `Output` updated to the new permanent path; the routing rule's description is updated from "interactive proposals" to "autonomous report writing"; the intermediate-document rule moves `SKILL_GENESIS_REPORT.md` from the Ephemeral row to a new Permanent-tier row with the run-log sibling.

The four changes are decoupled (the agent rewrite alone produces a working autonomous report; the commands work as soon as a report exists; the rule edits make the new model discoverable). Implementer ships them in any safe order.

**Activation:** no — the user has already decided on the A+C bundle before this pipeline started; the architect's role is to codify, not re-litigate. Single behavioral inversion; no cross-cutting security / performance tradeoffs; lens sweep not triggered.

## Considered Options

### A. Pull-driven autonomous-report + new disposition command + auto-fire removed (CHOSEN)

The full A+C bundle from ROADMAP Topic 3. Pros: addresses both friction modes at root (autonomous = unblocking the orchestrator pause; on-demand = decoupling cognitive load from merge moment); structurally mirrors sentinel; pairs cleanly with the rework-dispatch precedent; matches user's stated direction. Cons: introduces a new "report + paired disposition command" pattern (sentinel has no equivalent because its findings are diagnostic); adds modest repo noise per harvest run.

### B. Batch-disposition only (single AskUserQuestion, no autonomous mode, no decouple-from-merge)

Keep skill-genesis blocking + end-of-pipeline, but replace the N-iterations-of-AskUserQuestion loop with one multi-select. Pros: minimal-blast-radius change; reduces session interruptions from N to 1. Cons: doesn't address the second friction mode (cognitive load lands at exactly the wrong moment regardless of how many AskUserQuestion calls); the user explicitly rejected this as the only fix during the ROADMAP-Topic-3 discussion. Subsumed by Option A's batch-multi-select inside `/skill-genesis-review`.

### C. Autonomous-mode only (auto-fire kept, just no interaction at the end)

Skill-genesis runs at end-of-pipeline as today, but writes a report without blocking. The user dispositions later via `/skill-genesis-review`. Pros: smaller change to coordination protocol; preserves the "no LEARNINGS go unharvested" implicit guarantee. Cons: the cognitive load is still attached to the merge moment — the user knows the report just landed; the "another report in the inbox at the worst moment" friction is real even when no interaction is required. This is the option the architect would object to if asked; the user explicitly preferred full on-demand.

### D. Status quo + SendMessage feature request upstream

File an issue with Claude Code asking for `SendMessage` capability so the orchestrator can resume a paused skill-genesis after dispositioning Proposal 1. Pros: doesn't change Praxion at all; benefits many features beyond skill-genesis. Cons: external dependency (Anthropic-side roadmap); does not address the cognitive-load timing problem (the merge moment is still the wrong moment for a decision cycle). Filed separately per the prompt; not a substitute for the inversion.

## Consequences

### Positive

- **Cognitive load is decoupled from merge.** The user controls when to disposition learning candidates; the merge moment stops being a decision-cycle moment. This is the core ROADMAP Topic 3 fix.
- **Skill-genesis becomes resumable-by-design.** No blocking `AskUserQuestion` inside the agent body means no orchestrator-pause-then-stuck failure mode; the friction that surfaced this work cannot recur.
- **The agent's boundary becomes cleaner.** Pre-inversion: the agent proposes, presents interactively, executes memory stores inline, defers other delegations. Post-inversion: the agent proposes and writes; the review command dispositions and delegates. No "execute inline" exception remains for any artifact type.
- **Structural parallelism with sentinel.** Two autonomous report writers with `.ai-state/<type>_reports/` placement, timestamped accumulation, run-log siblings. Easier mental model; easier sentinel extension later (a future SG01–SG02 check family will be a near-copy of DL01–DL05).
- **Discoverability improves.** `/skill-genesis` and `/skill-genesis-review` surface in `/`-completion; today's auto-fire is invisible until the agent appears at the end of a pipeline. The new how-to doc (`docs/skill-genesis.md`) makes the flow explicit.

### Negative

- **One implicit guarantee is dropped: "no LEARNINGS go unharvested."** If the user never invokes `/skill-genesis`, learnings accumulate in `LEARNINGS.md` indefinitely. Mitigated by (a) the planner's existing convention of merging LEARNINGS.md into permanent locations at feature end, (b) the user-facing how-to doc explaining when to invoke the command, (c) a deferred follow-up to add a sentinel check for stale unreviewed reports.
- **`.ai-state/skill_genesis_reports/` accumulates per-run commits.** Each harvest run produces one report file + one log row, committed to git. Modest repo noise; bounded by user invocation rate (the inverse of the cost is the team-visibility gain from the artifact being committed).
- **A new pattern enters the ecosystem: paired autonomous-report + disposition-command.** The pattern is generalizable (could apply to future systems) but is uncommon today. The documentation surface (how-to doc + this ADR) is the mitigation.
- **One-cognitive-step cost shifts to `/skill-genesis-review`.** Memory entries were auto-stored after approval (one cognitive step total); they now require disposition (one cognitive step plus one `remember()` execution by the command). Net cost in `/skill-genesis-review`: zero — the cognitive step is consolidated with all other proposal dispositions.

### Risks Accepted

- Pagination behavior of `AskUserQuestion` for N > 20 proposals is implementer-defined; if upstream changes break the assumption, the disposition surface degrades to per-page batches. Acceptable — pagination is a UX refinement, not a correctness concern.
- The new `.ai-state/skill_genesis_reports/` directory shape is not yet covered by sentinel; a stale `pending` report could go undetected for arbitrarily long. Acceptable for v1; deferred sentinel check filed as a follow-up tech-debt item.

## Prior Decision

None — the researcher's ADR survey confirmed no prior decision establishes auto-fire as policy or commits to the interactive AskUserQuestion-per-proposal pattern. Seven ADRs reference skill-genesis incidentally; none are supersession targets. This is a fresh behavioral decision.

`dec-043` (Behavioral Contract layer) notes that skill-genesis receives no behavioral-contract injection because it does not emit code/plan/review artifacts. That note remains accurate post-inversion — the autonomous mode does not change the artifact-type boundary, so no re-affirmation is required. The decision still holds; the architect re-reads it and confirms.
