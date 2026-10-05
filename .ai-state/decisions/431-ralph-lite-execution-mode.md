---
id: dec-431
draft_id: dec-draft-72288a3b
title: Ralph-lite is an execution mode named in the Lightweight tier row, with its /goal recipe in tier-templates — recommended over a sixth tier row, pending the user's confirmation
status: accepted
category: behavioral
date: 2026-10-05
summary: The /goal-based Ralph-lite recipe for one well-gated single-behaviour task is reachable from tier selection through one clause in the always-loaded Lightweight row and lives in tier-templates.md (scratch worktree, auto mode or an allow-listed check, never acceptEdits alone, the derived test command printed every turn, a turn clause, the impossible exit, not for Standard/Full or background agents); a sixth tier row is the documented alternative.
tags: [ralph-lite, goal, tier, execution-mode, lightweight, calibration]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/tier-templates.md
affected_reqs: [REQ-34, REQ-35]
re_affirms: dec-262
dissent: []
---

## Context

The spike's Option 3, a native `/goal` loop for a task whose done-state is one command's output, needs a home that the tier selector reaches. The user said "I think Ralph-lite worths a tier." The brief registered an objection: tiers measure task size, while Ralph-lite changes who turns the crank. dec-262 already ruled that the tier is the calibration value for process weight, and that execution mode is an orthogonal axis. The context review costed three placements.

## Decision

**Recommend Option B; the user confirms at the architecture checkpoint.** One clause in the Lightweight row's Process cell of the always-loaded coordination protocol names "Ralph-lite recipe" with a link to `tier-templates.md § Ralph-Lite Recipe (/goal)`. The existing "Automated is an execution mode orthogonal to the tier" sentence extends to name it. The recipe follows the interface design's scaffold:

- a scratch worktree;
- auto mode, or `acceptEdits` with the check command allow-listed, never `acceptEdits` alone;
- the `resolve_test_scope.py`-derived check, printed every turn;
- a turn clause;
- the evaluator's "impossible" verdict as the exit to a human;
- not for Standard or Full step loops, or for work that spawns background agents.

## Considered Options

### Option A — A sixth tier row (the user's literal wording)
- **Cost:** about 60–80 always-loaded tokens.
- **Consistency sites:** the selector order sentence, the isolation table (Lightweight reads "none", but the recipe needs a worktree), the shipped `claude/canonical-blocks/agent-pipeline.md` and `hackathon-mode.md` ("5-tier selector"), `skills/spec-driven-development` SKILL and calibration procedure, and the closed `_KNOWN_TIERS` enum at `scripts/project_metrics/collectors/cost_collector_tier.py:24`.
- **Partially supersedes dec-262.** The category would flip to architectural, because a shipped canonical block changes.
- **Pros:** first-class in the table.
- **Cons:** breaks "higher tiers include everything below them"; a Ralph-lite row would record an execution mode as a tier, polluting the calibration log's accuracy analysis.

### Option B — An execution mode named in the Lightweight row (recommended)
- **Cost:** about 20–30 always-loaded tokens; 2–3 files; no enum or canonical-block edit.
- **Pros:** consistent with dec-262; the recipe is named at the moment of choice.
- **Cons:** not a row of its own, so the user's "worth a tier" is honoured in reach, not in form.

### Option C — Scaffold only, plus a pointer
- **Cost:** about 10–15 tokens.
- **Cons:** the least discoverable; the recipe reads as a footnote.

## Consequences

The always-loaded delta is measured before and after (FC-03, ≤ +100 tokens). The calibration log keeps recording the size tier, and the `Source` cell says when the recipe ran. If the user picks A, the planner adds the A consistency sites as one step, and this record changes its category and gains `supersedes_in_part: dec-262`.
