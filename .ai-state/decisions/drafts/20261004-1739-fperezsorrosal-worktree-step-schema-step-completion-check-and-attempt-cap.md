---
id: dec-draft-5649ee8e
title: Plan steps declare a machine-checked completion criterion that the reconciler judges first from the step's recorded result, and a step at two fresh attempts gets its own human-routed verdict
status: proposed
category: architectural
date: 2026-10-04
summary: "A new stdlib module scripts/_loop_fields.py owns the grammar of a plan step's Check: line (backticked command + pass/fail/skip/pending expectations with = or >=) and of WIP.md's orchestrator-written Attempts: sub-bullet, and evaluates a check against the step's own latest Result: line (the sole reader of pending=). The reconciler's verdict state machine moves to a new pure module scripts/_step_verdict.py, which judges a declared check first (fallback: declared Files changed plus green tests), stamps decided_by (check/fallback/none) plus outcome_source and attempt when present, and routes any non-complete step at attempt >= 2 to a new attempts-exhausted verdict (exit 2, never auto-resumed). The reconciler reads recorded results only and never runs a declared command"
tags: [step-completion, reconciler, step-schema, attempt-cap, step-loop, check-field]
made_by: agent
agent_type: systems-architect
branch: worktree-step-schema
pipeline_tier: standard
affected_files:
  - scripts/_loop_fields.py
  - scripts/_step_verdict.py
  - scripts/reconcile_pipeline_state.py
  - scripts/compose_handoff.py
  - commands/resume-pipeline.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/systems-architect.md
  - skills/software-planning/SKILL.md
  - skills/software-planning/references/document-templates.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/coordination-details.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-12, REQ-13]
---

## Context

A plan step's `Done when` is prose that nothing parses. The reconciler judges completion with a proxy: the declared `Files:` changed and the tests are green. Advancing the loop still rests on the agent's marker and checkbox. In recent pipelines, steps that did not converge were re-spawned or absorbed by the orchestrator with no per-step bound. The step-loop driver that follows this change needs a done criterion and an attempt count that are data.

Two modules are at the 800-line ceiling. `scripts/_step_schema.py` is at 806 lines. `scripts/reconcile_pipeline_state.py` is at 794, with its `_classify_step` at about 60 lines. The existing `blocked` verdict already means "a step tagged `mutation: on` has no usable reading" (dec-421).

**Activation:** fired. The tier is Standard, the change touches about 22 files across scripts and prose, and at least two paths were plausible for both the module placement and the run/read question. The lens sweep ran in reduced form (developer, test, operations, simplicity). Security and performance stakes are absent.

## Decision

1. **Grammar module.** New `scripts/_loop_fields.py` (stdlib, Python 3.9-safe) owns two line grammars in its normative docstring:
   - `Check: `<command>` expects <key><op><n> ...`, with keys `pass`, `fail`, `skip`, `pending` and operators `=` and `>=`. `pass` and `fail` are required, each key appears at most once, and an unknown key or trailing token makes the line unreadable.
   - `- Attempts: Step <id> count=<n>[ [BLOCKED] replan: <text>]`. Lines naming the same step merge to the highest count.

   The module evaluates a check against the latest `Counts` `Result:` line in the step's own `TEST_RESULTS.md` block, reading `pending=` (absent counts as 0). The outcome is one of `Met`, `Unmet(unmet expectations)` or `NoResult`. The attempt cap lives here as `ATTEMPT_CAP = 2`.
2. **Verdict module.** The reconciler's classification section moves, behavior-preserving, to new pure `scripts/_step_verdict.py`. The reconciler keeps evidence gathering.
3. **Check first.** In `_step_verdict.py`, a declared check decides first:
   - `Met` gives `verified-complete`, or `blocked` when a mutation reading is missing.
   - `Unmet`/`NoResult` with a `[COMPLETE]` claim gives `mismatch`, naming each unmet `key=`, the expected count and the observed count.
   - `Unmet`/`NoResult` otherwise gives the existing incomplete-claim classification.
   - An unreadable check gives `unknown`.

   Steps without a check keep the existing rules unchanged.
4. **Verdict keys.** Every verdict carries `decided_by`: `none` exactly when the verdict is `pending`, else `check` or `fallback`. It also carries `outcome_source` (`recorded`) and `attempt` when they have a value. Optional keys are omitted, not null, so a legacy plan's output gains only `decided_by`.
5. **Cap precedence.** When `attempt >= ATTEMPT_CAP` and the verdict is not `verified-complete`, the verdict becomes `attempts-exhausted`. Its evidence carries the replan request and the underlying verdict, it joins `unknown` and `blocked` in exit status 2, and it is never an auto-resume or auto-mark candidate.
6. **No run mode.** The reconciler reads recorded results only and never runs a declared command. `outcome_source: run` is reserved for the step-loop driver.
7. **Procedure.** The orchestrator writes the `Attempts:` line write-ahead at each fresh spawn and never on a resume. The cap is stated once, in `agent-pipeline-details.md § Completion handshake`.

## Considered Options

### Option A: A sibling post-pass that overrides the reconciler's fallback verdict (no refactor)

- **Pro:** no move commit, and the reconciler's state machine is untouched.
- **Con:** "check unmet, claim not complete, all files changed" must be re-classified outside the state machine, which means a second copy of the incomplete-claim rules. The wiring still exceeds the reconciler's 6 lines of headroom.

### Option B: Grow `_step_schema.py` and `_classify_step` in place

- **Pro:** fewest files.
- **Con:** both modules break the 800-line ceiling, and `_classify_step` breaks the 50-line function ceiling.

### Option C: New grammar module plus extracted verdict module (chosen)

- **Pro:** one copy of the verdict rules, both ceilings held, and the policy becomes testable without I/O. It follows dec-421's split: the step-document module owns the line, the reconciler side owns the verdict. The driver imports the grammar without the reconciler's policy.
- **Con:** two more modules and one behavior-preserving move step.

### Run or read (sub-decision)

- **Read-only** (chosen) keeps the reconciler side-effect-free by construction and leaves one runner of plan-authored commands: the driver's gate.
- **An explicit run mode** (the brief's default) would be a second runner with no consumer in this change.
- **Always run** breaks the safe-at-any-seam property of `/resume-pipeline`.

### Cap verdict (sub-decision)

- **Reusing `blocked`** gives an old name a new meaning, so `/resume-pipeline`, `compose_handoff` and the agents would mis-explain the step.
- **Applying the cap only to `mismatch`/`partial`** leaves `in-flight`, which `/resume-pipeline` auto-resumes, as a path to a third attempt.

## Consequences

- **Positive:** the step-loop driver gets a parsed done criterion, a parsed attempt count and a total cap rule. An agent's self-report cannot pass an unmet check. Every verdict says what decided it. A legacy pipeline is unchanged except for one added key.
- **Negative:**
  - The recorded `Result:` line is writer-trusted: a stale or hand-written line meets a check until the driver gates by running the command.
  - A second attempt still running reads `attempts-exhausted` until it returns.
  - The cap is procedure-enforced in this change.
  - The verdict vocabulary grows by one value that every prose reader must learn in the same commit.

## Disconfirmation

- **Falsifier:** the decision is wrong if, over the next three Standard pipelines that declare checks, either of these holds:
  - Plan-authored `Check:` lines are routinely unreadable or wrong (they force `unknown` or a plan edit on more than a quarter of checked steps). That would mean the grammar is too strict, or the count expectations are not knowable at plan time.
  - A `verified-complete` from a met check is later contradicted by the orchestrator's own handshake run or the verifier on more than one step. That would mean read-only trust in the recorded line is insufficient.
- **Steelmanned runner-up (Option A, the post-pass with no refactor):** it leaves a load-bearing, well-tested state machine untouched at the moment the pipeline's recovery path depends on it most. Overrides are easy to delete if the driver later replaces the reconciler's role. The duplicated incomplete-claim rule is four lines, and a test can pin the two copies together. It defers the module split until the driver's needs are known, instead of guessing them now.
- **Reversal trigger:** if the step-loop driver ends up owning completion judgment entirely (running checks, deciding verdicts) and the reconciler is reduced to legacy recovery, fold `_step_verdict.py` back or retire the check path from it. If the run-mode gap shows up as accepted-but-false completions (the falsifier's second clause), add an explicit run mode to the reconciler.
