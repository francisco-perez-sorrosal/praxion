---
id: dec-draft-33f2d19b
title: "The role eval gains a refactoring-delivery arm axis and refactoring-mode tasks graded from the end state"
status: proposed
category: implementation
date: 2026-11-14
summary: "The adherence role eval keeps its inherited-context axis (full, lean) as the default and gains a second axis, refactoring-delivery, whose arms (preloaded, delivered) are checkout copies set by the shared move tool and proven before scoring; the implementer and the test-engineer gain refactoring-mode tasks delegated with the marker and graded on the refactoring skill's verification checklist from what the session left behind."
tags: [eval, adherence, paired-run, refactoring, arms, graders, move]
made_by: agent
agent_type: systems-architect
branch: feat-refactoring-delivery
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/adherence/role_kits.py
  - eval/src/praxion_evals/adherence/model.py
  - eval/src/praxion_evals/adherence/arms.py
  - eval/src/praxion_evals/adherence/cli.py
  - eval/src/praxion_evals/adherence/fixtures/implementer/
  - eval/src/praxion_evals/adherence/fixtures/test-engineer/
affected_reqs: [REQ-18, REQ-19, REQ-20]
---

## Context

`dec-504`'s reversal rule says removing a preload runs as a paired run of the role's kit. The user decided that this pipeline builds the tasks, the graders and the paired run's two arms, and runs none of it (Q4). Three facts shape the build:
- The role eval's two arms differ only by `omitClaudeMd: true`. The implementer and the test-engineer already carry it, so `full` and `lean` are the same for them.
- The moves package grades main-session moves and has no change type for an agent definition's preload.
- Neither role's kit has a task in refactoring mode. The test-engineer's `pre-refactor` mode is declared unmeasured.

## Decision

1. **A second arm axis.** `--axis refactoring-delivery` on the existing `praxion-evals-adherence` entry, with arms `preloaded` and `delivered`; the default axis `inherited-context` is unchanged.
   - Each arm is a checkout copy set to its state by that copy's own `scripts/refactoring_move.py --to <state>`.
   - Each arm is verified by the delivery module's preload reader.
   - Each arm is proven by a marked proof spawn before any task is scored: the delivery label (the arm copy's own `shows_arrival`) in the delivered arm, and the harness's preload message in the preloaded arm.
2. **Refactoring-mode tasks for both roles, in a separate per-role pool planned only on the new axis.** Each task's delegation carries the step heading with `[Phase: Refactoring]` in its own words.
   - Each role's pool holds at least two templates. For the test-engineer they are `pre-refactor` templates.
   - The default axis never plans them: every role's default template pool, its frozen task list, the full-set template floor and `ROLE_MODES` are unchanged.
   - The test-engineer's `pre-refactor` stays declared unmeasured on the default axis and is covered only on the new one.
   - This keeps every ordinary run comparable with the runs before it.
3. **End-state graders from the refactoring skill's verification checklist.**
   - Implementer: the tests pass, the hidden characterization tests pass, no caller imports the old location, no moved name is left defined there, no re-export shim remains.
   - Test-engineer: characterization tests exist while production files are unchanged, and they import only the fixture's public names.

   The session's final message is never evidence.

## Considered Options

### Option 1: a main-session move kit under `--move`

Rejected. Its arms and proofs target main-session rules, and it would need a new change type for a definition's preload plus a spawn-level proof it does not have.

### Option 2: reuse `full` and `lean`

Rejected. For these two roles the arms are identical, so the run would measure nothing.

### Option 3: a second arm axis on the role eval (chosen)

Reuses the role kits, the stand-in-`claude` dry run, the arm-copy discipline and the proof-before-scoring rule.

## Consequences

Positive:
- A paired run of the move is one command per role on the user's go.
- The dry run exercises it at $0.
- The default axis and every existing dry run stay byte-identical.

Negative:
- A second axis is a concept the eval's reader must learn.
- Each template ships a start tree, a clean solution tree and one mutation per checklist item, so the graders can be proven on known-good and known-bad end states.
- No standing pin on the role kits' default task lists or on `pre-refactor` being unmeasured moves. In exchange, ordinary runs never exercise refactoring mode.
