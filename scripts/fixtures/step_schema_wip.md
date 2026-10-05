# WIP: step-schema

**Mode**: sequential (the plan has no `[parallel-group]` step). **Plan**: `IMPLEMENTATION_PLAN.md`, 21 steps. **Task slug**: `step-schema`.

## Current Step

All 21 steps complete; last production commit a933ca31, measured tree cfa031f4. Current: the pre-verification checkpoint, then the verifier.

## Status

[COMPLETE] - Pipeline closed 2026-10-04. All 21 steps committed (last production commit 48183ea2 after two in-place rework rounds; measured tree 48183ea2). Verification: first pass FAIL on one convention breach with nine WARN findings and every acceptance criterion and requirement passing; rework round 1 (651fe3a3) closed the FAIL and WARN 1 to 5, the orchestrator closed WARN 6 and 8 in the pipeline documents, rework round 2 (48183ea2) closed WARN 5's remainder, and the footprint rows were re-taken at the final head; final verdict PASS WITH FINDINGS, one new WARN (the reconciler's dual-shape JSON output when unnamed attempt lines exist) filed as td-344. Re-tiered Standard to Full by the user at the verifier rework seam; calibration `under-calibrated`. Spawns: 18 charged (17 starts plus 1 heavy resume), 8 light resumes. Light reviews: Steps 3, 6, 7 all accept. Rework manifest: all three rows closed. Awaiting the user's merge (`/merge-worktree`), which finalizes the two ADR drafts.

## Progress

- [x] Step 1: Bind the step-check drivers (BA-01..BA-04, BA-07) to the designed surface
  - Attempts: Step 1 count=1
- [x] Step 2: Bind the ledger drivers (BA-05, BA-06) to the designed library surface
  - Attempts: Step 2 count=1
- [x] Step 3: [Phase: Refactoring] Extract the verdict state machine into its own module [COMPLETE]
  - Attempts: Step 3 count=1
  - Principles checked (advisory): beauty-storytelling, beauty-simplicity, beauty-clarity-of-intent, beauty-expressiveness, beauty-purity, beauty-sustainability, beauty-durability, beauty-creativity
- [x] Step 4: Parse and evaluate a step's `Check:` line (new `_loop_fields.py`) [COMPLETE]
  - Attempts: Step 4 count=1
  - Principles checked (advisory): beauty-storytelling, beauty-simplicity, beauty-clarity-of-intent, beauty-expressiveness, beauty-purity, beauty-sustainability, beauty-durability, beauty-creativity
- [x] Step 5: Parse a step's attempt count (`Attempts:` line and `ATTEMPT_CAP`) [COMPLETE]
  - Attempts: Step 5 count=1
  - Principles checked (advisory): beauty-storytelling, beauty-simplicity, beauty-clarity-of-intent, beauty-expressiveness, beauty-purity, beauty-sustainability, beauty-durability, beauty-creativity
- [x] Step 6: Check-first verdict with the attempt cap (`_step_verdict.py`) [COMPLETE]
  - Attempts: Step 6 count=1
  - Principles checked (advisory): beauty-storytelling, beauty-simplicity, beauty-clarity-of-intent, beauty-expressiveness, beauty-purity, beauty-sustainability, beauty-durability, beauty-creativity
