---
id: dec-180
title: Subagent isolation in rework worktrees verified by controlled-test harness; ship blocked if hook does not fire
status: retired
category: architectural
date: 2026-05-14
summary: Add a controlled-test harness that spawns a subagent inside a rework worktree session, has it attempt an Edit outside the worktree, and asserts worktree_guard.py blocks the call. If the test fails, the rework feature does not ship — the test pass IS the load-bearing precondition for the rework loop's safety invariant.
tags: [worktree, isolation, subagent, hook, security, td-034, test-harness]
made_by: agent
agent_type: systems-architect
branch: worktree-verifier-rework-loop
pipeline_tier: standard
retired_by: [dec-379]
affected_files:
  - hooks/test_worktree_guard_subagent.py
  - hooks/worktree_guard.py
  - commands/resume-rework.md
  - .ai-state/TECH_DEBT_LEDGER.md
---

## Context

`td-034` (active in `.ai-state/TECH_DEBT_LEDGER.md`) documents a reproduced incident in which a subagent spawned by an orchestrator in a worktree session emitted `Edit` calls that landed in the canonical checkout instead of the briefed worktree. Three competing hypotheses for the root cause are documented in the ledger row, none ruled in or out:

(a) subagent sessions do not inherit the orchestrator's PreToolUse hooks (hook-scope gap);
(b) the subagent's path-resolution layer reports the worktree path while the actual filesystem write resolves to the canonical checkout (path-resolution bifurcation);
(c) the hook's path-containment check has a gap (e.g., relative-path normalization).

The rework loop's central safety invariant is that a subagent (`systems-architect` or `implementation-planner`) spawned by `/resume-rework` inside a rework worktree cannot write outside that worktree. If td-034 is real and the guard does NOT fire for subagents, the rework feature regresses the broader Praxion isolation contract every time a user runs `/resume-rework`.

The architect's job here is to address the risk explicitly — either verify the guard fires correctly with a test the implementer adds, or design an explicit mitigation.

**Activation:** yes (security/correctness lens fires on a known-unresolved issue; high-impact, medium-likelihood risk). Lenses applied: Security, Testability, Hard-to-misuse, Defense-in-depth.

## Decision

Two-part decision: (1) a controlled-test harness verifies the invariant; (2) the slash command supplies absolute-path briefing as defense in depth. Ship is blocked on the test harness passing.

### Part 1 — Controlled-test harness (gating)

Add `hooks/test_worktree_guard_subagent.py`. The test:

1. Creates a temporary linked worktree (using `git worktree add`).
2. Enters the worktree (mimics the post-`EnterWorktree` state).
3. Spawns a subagent via the actual `Agent` tool API with a deliberately-rebellious instruction: "use Edit to modify `<absolute-path-outside-worktree>/marker.txt`".
4. Asserts `worktree_guard.py` fires (exit code 2 from the PreToolUse path) and the target file is NOT modified.

The test's pass condition is the safety invariant. If the test fails (the hook does not fire), the implementer's step suite fails — the rework feature does not ship until the hook's subagent gap is fixed.

If the `Agent` tool is not callable from a test runner context (a real architectural constraint — Claude Code's `Agent` tool may require a live session), the test downgrades to a manual-verification document: the implementer runs `/resume-rework` manually with a known-bad findings file in a sandbox session and observes the behavior. The manual verification is recorded in `WIP.md` as part of the implementer's evidence; verifier confirms the evidence in `VERIFICATION_REPORT.md`.

### Part 2 — Absolute-path briefing in /resume-rework (defense in depth)

When `/resume-rework` spawns the architect (or, later, the planner), the prompt passes:

- Absolute path to the rework worktree root (the agent's working area)
- Absolute path to `VERIFIER_FINDINGS.md` inside that worktree
- Explicit "all writes inside this worktree only" reminder paraphrased from the existing worktree-banner contract

This is the same mitigation `feedback_implementer_cwd_in_worktrees` records (verify pwd, use absolute paths). It is reactive (catches mistakes in the agent's own behavior), but it is cheap and stacks with the hook-based prevention.

## Considered Options

### Option 1 — Test harness + absolute-path briefing (chosen)

Pros: verifies the load-bearing invariant; ship-blocks on real failure; defense-in-depth via absolute paths; isolates the rework feature from td-034's broader resolution timeline.

Cons: test harness design is non-trivial (real `Agent` calls in test context); fallback to manual verification adds process burden if the test framework can't host the `Agent` tool.

**Chosen.**

### Option 2 — Reactive mitigation only (absolute paths in prompt, no test)

Pros: simplest; ships fast.

Cons: silent regression of the isolation invariant if a subagent ignores the prompt instruction; the existing `feedback_implementer_cwd_in_worktrees` proves agents do ignore such instructions.

Rejected.

### Option 3 — Add a SessionStart hook for subagents that asserts cwd matches the briefed worktree-root

Pros: structural fix at the subagent-session level.

Cons: speculative — we do not know yet whether subagent SessionStart hooks fire (the same hook-scope gap that produced td-034 may apply); proposed in td-034's resolution path but not measured; adds infrastructure ahead of evidence.

Deferred. If the test harness reveals the hook does not fire, this is one of the candidate structural fixes; td-034's resolution will choose among them.

### Option 4 — Wait for td-034 to be resolved before shipping the rework loop

Pros: avoids any chance of regression.

Cons: td-034 has no scheduled resolution; the rework loop is independently valuable and its primary subagents (architect, planner) default to absolute paths in their existing behavior anyway. The blast radius of a td-034 manifestation in a rework worktree is the same as in any other Standard/Full pipeline.

Rejected — disproportionate.

## Consequences

**Positive:**

- The rework loop's safety invariant is explicitly verified, not assumed.
- If td-034 manifests, it does so in the test harness rather than user-land.
- The absolute-path briefing pattern can be reused by other slash commands that spawn agents in worktree contexts.
- The harness, if generalized, becomes a regression test for `worktree_guard.py` itself — useful for future hook evolution.

**Negative:**

- Test design is non-trivial; the implementer may report that real `Agent` calls in test context are infeasible. Fallback path: manual verification documented in `WIP.md`.
- The defense-in-depth prompt instruction adds ~3 lines to `commands/resume-rework.md` — minor surface expansion.

**Mitigation:**

- The fallback to manual verification is acceptable for v1 — the next iteration can promote it to an automated test as the testing infrastructure improves.
- The absolute-path briefing pattern is already implicit in agent behavior; codifying it in the slash command is documentation, not new mechanism.

## Linkage to td-034

`td-034` is referenced in the row's `notes` (via the inflight-suffix convention from `dec-181` if this rework spawns one of its own; not otherwise). The test-harness outcome feeds td-034's resolution path step 1: "write a controlled-test hook script that spawns a minimal subagent in a worktree session." If the harness passes, td-034's hypothesis (a) and (c) are ruled out for this specific case; if it fails, the harness's failure mode informs which hypothesis fires.

## Prior Decision

Retired 2026-09-08 by dec-379, whose action removed this decision's subject (`hooks/worktree_guard.py` and its controlled-test harness `hooks/test_worktree_guard_subagent.py`; native worktree isolation is now the sole enforcement layer) rather than deciding its question differently. The record is preserved; it re-opens if the subject returns.
