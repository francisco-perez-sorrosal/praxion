---
id: dec-513
draft_id: dec-draft-33f2d19b
title: "The role eval gains a refactoring-delivery arm axis and refactoring-mode tasks graded from the end state"
status: accepted
category: implementation
date: 2026-11-14
summary: "The adherence role eval keeps its inherited-context axis (full, lean) as the default and gains a second axis, refactoring-delivery, whose arms (preloaded, delivered) are checkout copies set by the shared move tool and proven before scoring; the implementer and the test-engineer gain refactoring-mode tasks delegated with the marker and graded on the refactoring skill's verification checklist from what the session left behind."
tags: [eval, adherence, paired-run, refactoring, arms, graders, move]
made_by: agent
agent_type: systems-architect
branch: feat-refactoring-delivery
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/role_kits.py
  - eval/src/praxion_evals/adherence/model.py
  - eval/src/praxion_evals/adherence/arms.py
  - eval/src/praxion_evals/adherence/cli.py
  - eval/src/praxion_evals/adherence/fixtures/implementer/
  - eval/src/praxion_evals/adherence/fixtures/test-engineer/
  - eval/src/praxion_evals/adherence/axis.py
  - eval/src/praxion_evals/adherence/axis_runs.py
  - eval/src/praxion_evals/adherence/session_arms.py
  - eval/src/praxion_evals/adherence/dry_run.py
  - eval/src/praxion_evals/adherence/refactoring_tasks.py
  - eval/src/praxion_evals/adherence/refactoring_arms.py
  - eval/src/praxion_evals/adherence/refactoring_assess.py
  - eval/src/praxion_evals/adherence/checks_refactoring.py
affected_reqs: [REQ-18, REQ-19, REQ-20, REQ-22, REQ-23]
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
   - Each arm is checked at no cost when it is built: the copy's own spawn hook runs once on a marked delegation, and the delivered copy must render the block while the preloaded copy must not.
   - Each arm is proven by a marked proof spawn before any task is scored, read from the proof spawn's own transcript and never from what the role says: exactly one delivered block and no preload message in the delivered arm, exactly one preload message and no block in the preloaded arm. The block is matched by the arm copy's own `shows_arrival`.
2. **Refactoring-mode tasks for both roles, in a separate per-role pool planned only on the new axis.** Each task's delegation carries the step heading with `[Phase: Refactoring]` in its own words.
   - Each role's pool holds at least two templates. The test-engineer's pool tasks run in the role's `paired` mode on a tagged step: the role's own definition puts a delegation with no pre-refactor plan there, and the grader reads the mode from the task.
   - The default axis never plans them: every role's default template pool, its frozen task list, the full-set template floor and `ROLE_MODES` are unchanged.
   - The test-engineer's `pre-refactor` stays declared unmeasured on the default axis and is covered only on the new one.
   - This keeps every ordinary run comparable with the runs before it.
3. **End-state graders from the refactoring skill's verification checklist.**
   - Implementer: the tests pass, the hidden characterization tests pass, no caller imports the old location, no moved name is left defined there, no re-export shim remains.
   - Test-engineer: characterization tests exist while production files are unchanged, and they import only the fixture's public names.

   The session's final message is never evidence.
4. **The paid loop is parameterised by one value per run.** The adherence loop reads one `AxisRun` record, chosen once per run by an exhaustive match on the run's axis.
   - Pure axis facts live in `axis.py`: the arms of each axis, which arm is the baseline and which the treatment, the paths each arm's build patches, and which arms are owed the kernel.
   - Every effectful difference between the axes lives in the record (`axis_runs.py`): plan, stage, build, proof, assess, catalog and refusals. The default axis's record holds the functions that ran before, so routing the loop through it changes no default run by a byte.
   - The loop, the pairing, the launch order, the report and the dry run read positions, never arm names. On `refactoring-delivery` the baseline is `preloaded` and the treatment `delivered`.
   - Every scored session of the new axis is graded on the role's ordinary checks, on the end-state checklist, and on a per-session arrival check (the skill reached the role its arm's own way), so a delivery that fails in one session is counted, not hidden.
   - A pool task is staged from its template's starting tree, without the grader's manifest or end states; the grader compares against the staged repository's root commit and takes the manifest from the template.
   - Continuing and calibrating a run of the new axis are refused before anything is written; closing, listing and reporting it work as for any run.

## Considered Options

### Option 1: a main-session move kit under `--move`

Rejected. Its arms and proofs target main-session rules, and it would need a new change type for a definition's preload plus a spawn-level proof it does not have.

### Option 2: reuse `full` and `lean`

Rejected. For these two roles the arms are identical, so the run would measure nothing.

### Option 3: a second arm axis on the role eval (chosen)

Reuses the role kits, the stand-in-`claude` dry run, the arm-copy discipline and the proof-before-scoring rule.

### How the paid loop tells the axes apart

Decided after the first build of the axis, when the pieces existed and nothing in the paid loop called them.

- **One record per run (chosen).** One place holds every difference between the axes, and a wrong-axis arm is refused where it would be built.
- **A `match` on the axis at each site.** Rejected: about eight scattered dispatches, the shape that let the pieces go uncalled.
- **A second loop module for the new axis.** Rejected: it would duplicate about 300 lines of stop, retry, checkpoint and spend logic that must not drift.
- **Renaming the pair's fields to baseline and treatment.** Rejected for now: a wide ripple through frozen report wording, for no behaviour.

Falsifier: a third axis needs a field the record lacks, or a default run's results change by a byte when routed through it. Reversal trigger: the record grows past about ten fields, or an axis needs per-task dispatch.

## Consequences

Positive:
- A paired run of the move is one command per role on the user's go.
- The dry run exercises it at $0.
- The default axis and every existing dry run stay byte-identical.

Negative:
- A second axis is a concept the eval's reader must learn.
- The pool holds six task pairs per role. A run of that size can show a regression and the arrival rate; it cannot clear most checks. A run that can needs about eight more templates per role, which this decision leaves to a later change.
- A stopped run of the new axis cannot be continued: it is closed and run afresh.
- Each template ships a start tree, a clean solution tree and one mutation per checklist item, so the graders can be proven on known-good and known-bad end states.
- No standing pin on the role kits' default task lists or on `pre-refactor` being unmeasured moves. In exchange, ordinary runs never exercise refactoring mode.
