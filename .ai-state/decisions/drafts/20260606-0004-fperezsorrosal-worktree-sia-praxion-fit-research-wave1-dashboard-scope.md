---
id: dec-draft-43d35093
title: Wave 1 Dashboard Eval Panel — Kept in Wave 1
status: accepted
category: implementation
date: "2026-06-06"
summary: Dashboard eval panel kept IN Wave 1 as Step 12 (user decision 2026-06-06, overriding the planner's defer recommendation), built with a paired implementer + test-engineer vitest step.
tags: [dashboard, wave-planning, eval-panel, scope]
made_by: agent
agent_type: implementation-planner
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - dashboard_app/src/server/view-models/evals.ts
  - dashboard_app/src/lib/evals.ts
  - dashboard_app/src/components/eval-leaderboard.tsx
  - dashboard_app/src/app/evals/page.tsx
  - dashboard_app/tests/eval-leaderboard.test.ts
---

## Context

Wave 1 has two independent streams (P2 and P3). The P2 stream includes three items:
`commands/scores.md` (1 file, read-only), `rules/ml/eval-driven-verification.md` extension
(2 files with manifest regen), and a `dashboard_app/` eval panel. The first two items are
small (1-2 files each, < 100 lines of new content). The dashboard panel requires 4-5 new
TypeScript files across view-model, types, component, and page-route layers, plus vitest
tests — comparable in size to the entire metrics panel that was delivered separately.

Including the dashboard panel in Wave 1 creates an asymmetric step that would:
- Dominate the P2 stream review, making the minimal `/scores` command and verifier wiring
  harder to review independently
- Block any Wave 2 start until the Next.js build pipeline is verified clean
- Require the implementer to context-switch between Markdown convention authoring (P2/P3)
  and TypeScript component development (dashboard) in the same wave

The `dashboard_app/src/server/view-models/metrics.ts` (the analog) was itself a significant
deliverable — reading it reveals ~200 lines of typed parsing logic, coercion functions,
and null-handling. The eval view-model will be comparable.

**DECISION: keep the dashboard eval panel IN Wave 1 (Option A) — user-decided 2026-06-06.**
Build it as Step 12 with a paired implementer + test-engineer step (vitest against the
`run-ledger-schema.md` §Minimal Valid Example as the fixture). Wave 1 ships four items:
`/scores` command, verifier reuse wiring, all P3 governance content, and the dashboard panel.

**Override on record:** the implementation-planner recommended Option B (defer to Wave 1.5)
on asymmetric-scope grounds (see Considered Options). The user chose Option A to ship a
user-visible eval leaderboard in a single wave, accepting the longer, mixed Markdown +
TypeScript review. The behavioral-contract Register-Objection was honored (the planner stated
the conflict with a reason); the user made the final call.

## Considered Options

### Option A: Keep in Wave 1 (CHOSEN by user)

Implement the dashboard panel as Step 12 in the current wave. Pros: single merge,
no additional plan pass, user-visible leaderboard in one wave. Cons: asymmetric step size;
blocks Wave 2 on the Next.js build; mixes Markdown + TypeScript review. Mitigation: Step 12
is sequenced as its own paired (implementer + test-engineer) step to stay isolable.

### Option B: Defer to Wave 1.5 (planner-recommended; not chosen)

Dashboard panel gets its own plan pass after Wave 1 merges. Pros: clean step sizes throughout;
Wave 1 stays reviewable; Wave 1.5 can design the view-model and component with full attention.
Cons: one more planning pass; no eval panel until then.

### Option C: Defer to Wave 3

Dashboard panel rides the P1 archetype-detection wave. Pros: the dashboard is most meaningful
when the full managed-project pipeline exists. Cons: long wait; the `/scores` command will
expose the data anyway; dashboard is a nice-to-have, not a gate.

## Consequences

- Wave 1 ships a user-visible eval leaderboard (dashboard panel) in one wave — no separate pass
- Wave 1 review mixes Markdown (P2/P3) and TypeScript (panel); Step 12 is sequenced as its own
  paired step (implementer + test-engineer) with vitest to keep it isolable within the wave
- Wave 2 start waits on a clean `cd dashboard_app && ./node_modules/.bin/next build` + vitest run
- The panel's view-model reads `run-ledger-schema.md` §EVAL_LOG.md Column Set as the authoritative
  source, keeping it consistent with the Wave 0 schema

## Prior Decision

None (first decision on Wave 1 scope).
