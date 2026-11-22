# Spec: per-step-gate (a widened pocket waits for one checkpoint)

**Task slug**: `per-step-gate`
**Feature**: A driven step's gate runs the step's own `Check:` and the tests its change reaches; a pocket the test scope widens to its whole suite waits for one checkpoint, which the step-loop driver runs before `complete`, each waiting pocket once, stopping for a person when one is red. The resolver is unchanged.
**Tier**: Standard (the verifier's retrospective calibration reads correct: 7 charged spawns of 16, 11 of 17 loop iterations, no re-tier)
**Complexity**: medium: 19 requirements, 10 plan steps (4 driven), 23 commits and 44 files changed against `ec962553` (+3,815 and -80 lines), two new modules (`scripts/_step_loop_checkpoint.py`, `scripts/_step_loop_checkpoint_run.py`), one new action and two new stop causes (`checkpoint-red`, `checkpoint-due`)
**Base commit**: `ec962553` (main on 2026-11-21); the loop's base `85177ad9`
**Head at archival**: `958c4d73` plus the re-verification's two text revisions. Landmarks: acceptance design `7c808253`; first production commit `b5ebe7d2`; the switch `42cab00b`; the head the verifier read `c32d04c6`.
**Pipeline branch**: `worktree-per-step-gate`
**Start date**: 2026-11-20
**End date**: 2026-11-21
**Archived**: 2026-11-21 (pre-merge; the merge into main, the push and any release are the user's)
**Status**: completed -- verified: PASS WITH FINDINGS (0 FAIL, 4 WARN: two fixed in `e445a38a` and `958c4d73`, two declined under their ceilings); the fixes re-read by a fresh light review, whose two text revisions were applied; macOS only, Linux from CI after the merge
**ADRs**: `dec-523` (category: architectural -- the checkpoint's two modules; checking widened pockets moves from the per-step gate to the checkpoint; promoted at the merge)
**Evidence base**: `dec-523`; the pipeline's completion row in `.ai-state/calibration_log.md` dated 2026-11-21; the Traceability matrix below (rendered from the ephemeral `.ai-work/per-step-gate/traceability.yml`; spec extract digest `e299d2712c25`); the measurements: always-loaded 20,310 and listing 13,335 tokens at base and head; Key Signal 9 on scratch clones with the real driver (the eval pocket's whole suite inside a widening step's gate 544.1 s at the base, none at the head; the gate 1,376.1 s and 979.5 s; the checkpoint ran it once, 451.6 s, green); ledger row td-688 (filed: the second pocket's narrow near-whole selection, out of scope by the user's choice) and td-676 (resolved).

## Feature Summary

Before this change every driven step whose change widened a pocket ran that pocket's whole suite at its own gate, one pocket after another, so a step that touched a pocket's runner configuration paid the whole suite every time. Now a non-goal step with a readable `Check:` leaves each such pocket unrun and writes `Deferred: <root> (widened): whole suite waits for the checkpoint` in its block; the waiting pockets are derived on every call from those lines, the ledger's commit field and green `## Checkpoint <root> at <head7>` blocks. When every step is done, a `record` stops `checkpoint-due` and `next` runs each waiting pocket's whole suite once: green prints `complete`, red stops `checkpoint-red` naming the pocket's waiting steps, unfinished answers `gate-running`. `status --json` and every stop carry `waiting`. A step with no check and a goal step gate as before.

## Requirements

### REQ-01: A widened pocket waits at a step with a check

**When** `record` gates a driven step that is not a goal step and declares a `Check:`
**and** the test scope of the step's changed files marks one or more pockets `widened`
**the system** runs the step's `Check:` and every `narrow` pocket, starts no run of any `widened` pocket's suite, and decides the step's verdict, commit and record from the runs it made
**so that** a step pays for its own check and the tests its change reaches, and not for a whole suite the scope could not narrow; the step's own check still decides.

### REQ-02: Steps with only narrow pockets are unchanged

**When** `record` gates a driven step whose test scope has only `narrow` pockets, or is `nothing-to-run`
**the system** makes the same runs, writes the same block, gives the same verdict and makes the same commit as on the base commit, and adds no pocket to the waiting ones
**so that** the change touches only the gates it concerns.

### REQ-03: The block records each deferral

**When** a step's gate defers a pocket
**the system** writes in the step's block in `TEST_RESULTS.md` one `Deferred:` line per deferred pocket, naming the pocket and saying it waits for the checkpoint, placed before the block's `Result:` lines so the deciding line stays last, and writes no `Scope:` or `Result:` line for a deferred pocket
**so that** the verifier and a person reading the block see which pockets the step did not run and why, and the block stays one block per gate as today.

### REQ-04: A deferral is read as no evidence either way

**When** `reconcile_pipeline_state.py` reads a step whose latest block carries a `Deferred:` line
**the system** gives the verdict the step's `Check:` decides from the block's `Result:` lines (verified complete when the check is met and the runs are green), exactly as for the same block without the `Deferred:` line, and `record` gives the same verdict
**so that** a deferral never reads as an unverified or a failed step, and the driver and the reconciler never disagree about one.

### REQ-05: A step with no check gates as today

**When** `record` gates a driven step that declares no `Check:`
**and** the test scope of its changed files marks a pocket `widened`, whether or not other pockets are `narrow`
**the system** runs every pocket of its scope, each `widened` one whole, decides as on the base commit, and defers nothing; `reconcile_pipeline_state.py` reads its block as it reads it today
**so that** the loop never commits a step that no run at its own gate has judged: a step with no check has no other evidence to decide it, which is the reason a step with no check and nothing to run already reads as unverified; a step earns the cheaper gate by declaring a check, as every step the planner gives the implementer already does.

### REQ-06: A goal step's gate is unchanged

**When** `record` gates an iteration of a goal step
**the system** runs its `Check:` and its whole test scope, every `widened` pocket whole, decides as on the base commit, and adds nothing to the waiting pockets
**so that** every iteration a goal loop keeps without a person is first judged on regressions in every pocket its change reaches: once an iteration is kept and the next builds on it, no later run can say which iteration broke a pocket, and the goal's worker may write the task directory, so a record it could edit must not stand in for a run.

### REQ-07: A committed deferral makes its pocket wait

**When** a step whose gate deferred a pocket is committed by the loop
**the system** makes that pocket wait with the step among its waiting steps, named once however many of its attempts deferred it
**and** an attempt that is not committed (red, refused, or returned with a blocked or conflict marker) adds nothing to the waiting pockets
**so that** the checkpoint runs exactly the pockets whose whole suites committed changes have not yet passed, and names exactly the steps whose changes reached them.

### REQ-08: The checkpoint runs before complete

**When** every step is done
**and** one or more pockets wait
**the system** runs each waiting pocket's whole suite once, one run per pocket whatever the number of its waiting steps, and prints `complete` (exit 0) only when every one of those runs is green; a pocket whose run is green stops waiting and is not run again
**and** with no pocket waiting it prints `complete` exactly as on the base commit
**so that** `complete`, and the pre-verification checkpoint after it, mean that every pocket the loop's committed changes reached has passed whole since the last of those changes.

### REQ-09: No checkpoint runs while a step remains

**When** pockets wait and a step remains to be done
**the system** issues that step's request, or the stop it would issue on the base commit, and starts no checkpoint run; no plan field moves the checkpoint earlier
**so that** the change adds no plan grammar and one checkpoint per loop pays each waiting suite once; a plan that wants a whole suite judged at a step puts it in that step's `Check:`, which decides that step like any check and leaves the pocket waiting.

### REQ-10: A checkpoint longer than one call resumes

**When** a checkpoint run is still inside its pocket's bound when the call's wait ends
**the system** prints the error code `gate-running` (exit 4), prints no `complete` and records nothing for that pocket
**and** the same call made again picks up the runs already started and never starts a second run of a pocket the checkpoint has already started or finished
**so that** a checkpoint costs calls, not reruns, as a step's gate does today.

### REQ-11: A red checkpoint stops for a person

**When** a checkpoint run of a waiting pocket is red: a failing test, an error, no readable summary, or a run cut off at its bound
**the system** prints the outcome `needs-human` (exit 2) with the stop cause `checkpoint-red`, naming each red pocket, its failing tests as a gate's `Failed:` and `Cut off:` lines name them, and every waiting step of that pocket, and writes `HANDOFF.md` as every stop does
**and** it changes no commit, no `WIP.md` tick and no step's verdict, and the red pocket keeps waiting with the same steps, while a pocket whose run in the same checkpoint was green stops waiting
**so that** a person looks for the cause among the named steps and chooses the remedy (a fix step, a plan revision or a fix by hand), committed steps are never rewritten, and the next call after the remedy runs the red pocket again.

### REQ-12: The checkpoint's evidence is recorded apart

**When** a checkpoint run of a pocket finishes, green or red
**the system** records it in `TEST_RESULTS.md` in a block of its own that belongs to no step, naming the pocket, the run's counts and the waiting steps it covered
**and** recording it leaves the verdict of every step, as `reconcile_pipeline_state.py` reads it, the same as before the block was written
**so that** the verifier and a person find the checkpoint's evidence beside every gate's, and no step's evidence is re-read through it.

### REQ-13: The waiting pockets survive a stop

**When** a call is made from a new session, after a compaction, after a stop and its resume, or after a call cut off part-way, including one cut off after a step's commit
**the system** reads the same waiting pockets with the same waiting steps from the task directory, never loses a committed deferral and never counts one twice
**and** `status` lists each waiting pocket with its waiting steps
**so that** a deferral outlives the conversation that made it, as every other loop fact already does.

### REQ-14: Every stop names the waiting pockets

**When** the loop stops for a person for any cause, or prints `budget-exhausted`, while pockets wait
**the system** names each waiting pocket and its waiting steps in the stop and in `HANDOFF.md`
**so that** a loop that ends before `complete` still has its deferred suites run before the verifier; a step run outside the loop (a `not-driven` step, or the steps left after `budget-exhausted`) keeps today's by-hand run of its derived scope and adds nothing to the waiting pockets.

### REQ-15: A project with one pocket

**When** a project has a single pocket
**and** a driven step with a `Check:` changes files whose test scope widens that pocket
**the system** runs only the step's `Check:` at the gate, defers the pocket, and runs the pocket's whole suite once at the checkpoint
**so that** the change holds where the one pocket is the whole suite.

### REQ-16: A test scope that widens at every step

**When** the test scope of every driven step widens every pocket it reaches
**the system** defers those pockets at every step with a `Check:`, runs each pocket's whole suite once at the checkpoint whatever the number of steps, and treats every pocket by what the test scope says of it, never by a pocket name built into the driver
**so that** a managed project whose test scope cannot narrow pays each whole suite once per loop instead of once per step.

### REQ-17: The test-scope command is unchanged

**When** `resolve_test_scope.py` is asked for any change set after this change
**the system** gives the same answer as on the base commit; it still never narrows, and the deferral is the gate's own reading of a `widened` pocket
**so that** every other reader of the test scope (the inner loop, the integration checkpoint, a step run by hand) is untouched.

### REQ-18: Records written before the change read as before

**When** the driver or `reconcile_pipeline_state.py` reads a task directory written by the base commit's driver: blocks without any `Deferred:` line, `WIP.md`, the iteration ledger and the gate's run records
**the system** gives the same outcome for `next`, the same `status` and the same verdicts as the base commit gives, and no pocket waits
**so that** a pipeline in flight when the change lands resumes where it stood.

### REQ-19: Always-loaded content and the fast gate probes are unchanged

**When** the always-loaded content is measured with `measure_token_budget.py`, and the three fast probes of `check_gates_bite.py` are run, after the change
**the system** shows the base commit's always-loaded count, and each probe passes as it does on the base commit
**so that** the change costs no session any context and leaves every gate it does not concern biting.

## Traceability

Rendered from `.ai-work/per-step-gate/traceability.yml` at the close (127 node entries, every one
collected at `ba3c962b`); `Test(s)` lists the outer-loop nodes first, then the unit tests.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_checked_step_starts_no_run_of_the_pocket_its_change_widens<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_checked_step_is_decided_by_its_check_whatever_its_widened_pocket_holds<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_narrow_pocket_still_fails_a_step_that_also_widens_another<br>scripts/test_loop_record_deferral.py::test_a_widened_pocket_is_not_run_and_its_root_is_returned_when_asked_to_defer<br>scripts/test_loop_record_deferral.py::test_the_record_that_leaves_only_the_checkpoint_stops_checkpoint_due_and_starts_no_run | scripts/_step_loop_io.py::run_derived_scope<br>scripts/_step_loop_record_gate.py::scope_run<br>scripts/_step_loop_record_gate.py::run_gate | PASS |
| REQ-02 | tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_step_with_only_narrow_pockets_runs_records_and_commits_as_before<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_step_whose_scope_has_nothing_to_run_is_decided_by_its_check_as_before | scripts/_step_loop_record_gate.py::run_gate<br>scripts/_step_loop_record_gate.py::Gate.deferred | PASS |
| REQ-03 | tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_each_deferred_pocket_has_a_line_of_its_own_before_the_deciding_result<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_deferred_line_says_its_pocket_waits_for_the_checkpoint_and_no_scope_line_names_it<br>scripts/test_loop_record_deferral.py::test_a_checked_step_writes_a_deferred_line_after_the_scope_lines_and_before_every_result<br>scripts/test_loop_record_deferral.py::test_a_gate_block_read_back_after_a_cut_off_call_carries_the_same_deferral<br>scripts/test__step_loop_checkpoint.py::test_deferred_line_names_the_pocket_and_says_its_whole_suite_waits<br>scripts/test__step_loop_checkpoint.py::test_deferred_line_names_the_root_pocket_by_a_dot<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_reads_back_the_root_a_deferred_line_was_written_for<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_returns_each_root_in_the_order_its_line_appears<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_ignores_every_line_that_does_not_open_with_the_marker<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_ignores_a_line_that_is_indented<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_ignores_a_line_inside_a_code_fence<br>scripts/test__step_loop_checkpoint.py::test_deferred_roots_is_empty_for_lines_that_defer_nothing | scripts/_step_loop_checkpoint.py::deferred_line<br>scripts/_step_loop_checkpoint.py::deferred_roots<br>scripts/_step_loop_record_gate.py::run_gate<br>scripts/_step_loop_record_gate.py::Gate.deferred | PASS |
| REQ-04 | tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_the_reconciler_gives_a_deferring_step_the_verdict_its_check_decides<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_the_reconciler_reads_a_deferring_block_as_the_same_block_without_its_deferred_lines | scripts/_step_loop_record_gate.py::scope_run | PASS |
| REQ-05 | tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_step_with_no_check_runs_its_widened_pocket_whole_beside_its_narrow_one<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_step_with_no_check_whose_change_only_widens_runs_it_whole_and_reads_unverified<br>tests/acceptance/test_a_step_gate_leaves_a_widened_pocket_for_the_checkpoint.py::test_a_committed_step_with_no_check_leaves_nothing_for_the_checkpoint<br>scripts/test_loop_record_deferral.py::test_a_step_with_no_check_runs_its_widened_pocket_whole_and_defers_nothing | scripts/_step_loop_record_gate.py::run_gate | PASS |
| REQ-06 | tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_a_goal_iteration_runs_its_widened_pocket_whole_and_defers_nothing<br>scripts/test_loop_record_deferral.py::test_a_goal_step_runs_its_widened_pocket_whole_and_defers_nothing | scripts/_step_loop_record_gate.py::goal_runs | PASS |
| REQ-07 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_red_attempt_that_widened_a_pocket_leaves_nothing_waiting<br>tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_step_that_deferred_a_pocket_on_two_attempts_is_one_waiting_step<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_keeps_its_root_and_its_steps<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_accepts_steps_in_plan_order_with_lettered_ids<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_is_frozen<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_refuses_no_steps<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_refuses_a_step_named_twice<br>scripts/test__step_loop_checkpoint.py::test_waiting_pocket_refuses_steps_out_of_plan_order<br>scripts/test__step_loop_checkpoint.py::test_a_committed_deferral_makes_its_pocket_wait_with_the_step<br>scripts/test__step_loop_checkpoint.py::test_a_deferral_in_an_attempt_that_was_not_committed_adds_nothing<br>scripts/test__step_loop_checkpoint.py::test_a_deferral_in_a_block_no_ledger_record_names_adds_nothing<br>scripts/test__step_loop_checkpoint.py::test_a_step_that_deferred_a_pocket_on_two_committed_attempts_is_named_once<br>scripts/test__step_loop_checkpoint.py::test_a_committed_attempt_counts_though_an_uncommitted_one_of_the_same_step_deferred_too<br>scripts/test__step_loop_checkpoint.py::test_two_steps_that_deferred_the_same_pocket_share_one_waiting_pocket<br>scripts/test__step_loop_checkpoint.py::test_waiting_steps_are_in_plan_order_whatever_order_the_records_come_in<br>scripts/test__step_loop_checkpoint.py::test_a_step_that_deferred_two_pockets_is_named_under_each<br>scripts/test__step_loop_checkpoint.py::test_each_pocket_waits_only_for_the_steps_that_deferred_it<br>scripts/test__step_loop_checkpoint.py::test_a_gate_block_that_deferred_nothing_makes_no_pocket_wait | scripts/_step_loop_checkpoint.py::waiting_pockets<br>scripts/_step_loop_checkpoint.py::WaitingPocket<br>scripts/_step_loop_record_gate.py::run_gate | PASS |
| REQ-08 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_complete_is_printed_only_after_the_waiting_pocket_ran_whole<br>tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_pocket_two_steps_deferred_runs_once_at_the_checkpoint<br>tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_pocket_whose_checkpoint_run_was_green_is_not_run_again<br>scripts/test_loop_checkpoint_action.py::test_every_step_done_with_a_pocket_waiting_is_a_checkpoint<br>scripts/test_loop_checkpoint_action.py::test_every_step_done_and_nothing_waiting_is_complete<br>scripts/test_loop_checkpoint_action.py::test_a_checkpoint_of_no_pocket_cannot_be_built<br>scripts/test_loop_checkpoint_action.py::test_checkpoint_red_is_a_human_stop_that_belongs_to_no_step<br>scripts/test_loop_checkpoint_run.py::test_a_green_run_writes_its_block_and_the_pocket_stops_waiting<br>scripts/test_loop_checkpoint_run.py::test_two_waiting_steps_give_one_run<br>scripts/test_loop_checkpoint_run.py::test_next_runs_the_waiting_pocket_and_prints_complete_once_it_is_green<br>scripts/test__step_loop_checkpoint.py::test_a_green_checkpoint_after_the_deferral_clears_the_pocket<br>scripts/test__step_loop_checkpoint.py::test_a_deferral_placed_after_a_green_checkpoint_waits_without_the_earlier_steps<br>scripts/test__step_loop_checkpoint.py::test_a_green_checkpoint_for_one_pocket_leaves_another_pocket_waiting<br>scripts/test__step_loop_checkpoint.py::test_a_green_checkpoint_clears_every_earlier_deferral_of_its_pocket<br>scripts/test__step_loop_checkpoint.py::test_a_red_checkpoint_then_a_green_one_clears_the_pocket<br>scripts/test__step_loop_checkpoint.py::test_the_waiting_steps_follow_the_deferrals_and_checkpoints_in_file_order | scripts/_step_loop_action.py::Checkpoint<br>scripts/_step_loop_action.py::next_action<br>scripts/_step_loop_checkpoint_run.py::run_checkpoint<br>scripts/step_loop.py::run_next<br>scripts/step_loop.py::_checkpoint_answer | PASS |
| REQ-09 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_no_checkpoint_run_starts_while_a_step_remains<br>scripts/test_loop_checkpoint_action.py::test_a_step_still_to_do_is_spawned_though_a_pocket_waits<br>scripts/test_loop_checkpoint_action.py::test_a_checkpoint_outranks_a_human_stop_as_complete_does | scripts/_step_loop_action.py::next_action | PASS |
| REQ-10 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_checkpoint_run_inside_its_bound_answers_gate_running_and_prints_no_complete<br>tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_checkpoint_call_cut_off_and_made_again_never_starts_a_second_run<br>scripts/test_loop_checkpoint_run.py::test_a_run_inside_its_bound_is_still_running_and_the_next_call_attaches_to_it<br>scripts/test_loop_checkpoint_run.py::test_a_still_running_call_writes_no_block<br>scripts/test_loop_checkpoint_run.py::test_the_run_directory_changes_with_head_and_with_the_waiting_steps<br>scripts/test_loop_checkpoint_run.py::test_next_over_a_run_still_inside_its_bound_answers_gate_running | scripts/_step_loop_checkpoint_run.py::run_directory<br>scripts/_step_loop_checkpoint_run.py::CheckpointRunning<br>scripts/step_loop.py::_checkpoint_answer | PASS |
| REQ-11 | tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_red_checkpoint_run_stops_for_a_person_with_the_cause_checkpoint_red<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_the_checkpoint_red_stop_names_the_pocket_and_its_failing_test<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_the_checkpoint_red_handoff_names_the_cause_the_pocket_and_its_failing_test<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_the_checkpoint_red_stop_names_every_step_that_deferred_the_pocket_once<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_red_checkpoint_changes_no_commit_tick_or_step_verdict<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_checkpoint_run_cut_off_at_its_bound_is_red_and_says_it_was_cut_off<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_after_a_remedy_the_next_call_runs_the_red_pocket_again_and_not_the_green_ones<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_red_pocket_keeps_its_waiting_steps_while_a_green_one_stops_waiting<br>scripts/test_loop_checkpoint_run.py::test_a_red_run_keeps_the_pocket_waiting_and_names_the_failing_test<br>scripts/test_loop_checkpoint_run.py::test_a_run_past_its_bound_is_red_and_says_it_was_cut_off<br>scripts/test_loop_checkpoint_run.py::test_a_remedy_commit_starts_a_fresh_run<br>scripts/test_loop_checkpoint_run.py::test_next_over_a_red_pocket_stops_naming_it_its_test_and_its_steps<br>scripts/test__step_loop_checkpoint.py::test_a_red_checkpoint_clears_nothing<br>scripts/test__step_loop_checkpoint.py::test_a_red_checkpoint_then_a_green_one_clears_the_pocket<br>scripts/test__step_loop_checkpoint.py::test_the_waiting_steps_follow_the_deferrals_and_checkpoints_in_file_order | scripts/_step_loop_checkpoint_run.py::CheckpointRed<br>scripts/_step_loop_checkpoint_run.py::RedPocket<br>scripts/step_loop.py::_checkpoint_answer<br>scripts/_step_loop_cli.py::stop_object | PASS |
| REQ-12 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_the_checkpoint_records_a_block_of_its_own_naming_the_pocket_its_counts_and_steps<br>tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_recording_the_checkpoint_leaves_every_steps_verdict_as_the_reconciler_read_it<br>scripts/test_loop_checkpoint_run.py::test_the_block_names_the_pocket_the_counts_and_the_covered_steps<br>scripts/test_loop_checkpoint_run.py::test_a_finished_run_asked_again_adds_no_block_and_starts_no_run<br>scripts/test_step_schema.py::test_is_checkpoint_heading_accepts_the_heading_the_checkpoint_writes<br>scripts/test_step_schema.py::test_is_checkpoint_heading_rejects_every_other_heading<br>scripts/test_step_schema.py::test_a_checkpoint_block_after_a_step_block_gives_the_step_none_of_its_lines<br>scripts/test_check_test_results_shape.py::test_checkpoint_heading_is_not_a_non_step_heading_finding<br>scripts/test_check_test_results_shape.py::test_another_level_two_heading_is_still_a_non_step_heading_finding<br>scripts/test_check_test_results_shape.py::test_green_checkpoint_block_over_the_ceiling_is_flagged<br>scripts/test_check_test_results_shape.py::test_checkpoint_block_with_no_result_line_is_flagged<br>scripts/test_check_test_results_shape.py::test_red_checkpoint_block_is_never_flagged_for_size | scripts/_step_loop_checkpoint.py::checkpoint_heading<br>scripts/_step_loop_checkpoint.py::covers_line<br>scripts/_step_schema.py::is_checkpoint_heading<br>scripts/check_test_results_shape.py::_split_checkpoint_blocks<br>scripts/_step_loop_checkpoint_run.py::block<br>scripts/_step_loop_checkpoint_run.py::record_once | PASS |
| REQ-13 | tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_status_lists_each_waiting_pocket<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_the_waiting_pockets_read_the_same_before_and_after_a_stop<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_record_call_cut_off_and_made_again_counts_its_deferral_once<br>scripts/test_loop_checkpoint_run.py::test_next_runs_the_waiting_pocket_and_prints_complete_once_it_is_green<br>scripts/test_loop_waiting_envelopes.py::test_status_lists_each_waiting_pocket_with_its_steps<br>scripts/test_loop_waiting_envelopes.py::test_the_status_table_names_each_waiting_pocket_with_its_steps<br>scripts/test_loop_waiting_envelopes.py::test_status_has_no_waiting_key_when_no_pocket_waits<br>scripts/test_loop_waiting_envelopes.py::test_status_of_a_done_plan_with_a_pocket_waiting_reports_the_checkpoint_due_stop<br>scripts/test__step_loop_checkpoint.py::test_the_same_text_and_records_give_the_same_answer_every_time<br>scripts/test__step_loop_checkpoint.py::test_waiting_steps_are_in_plan_order_whatever_order_the_records_come_in<br>scripts/test__step_loop_checkpoint.py::test_a_committed_deferral_makes_its_pocket_wait_with_the_step | scripts/_step_loop_state.py::LoopInputs<br>scripts/_step_loop_checkpoint.py::waiting_pockets<br>scripts/step_loop.py::read_task<br>scripts/_step_loop_cli.py::status_object<br>scripts/_step_loop_cli.py::status_table | PASS |
| REQ-14 | tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_stop_while_a_pocket_waits_names_the_pocket_in_the_stop[blocked]<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_stop_while_a_pocket_waits_names_the_pocket_in_the_stop[not-driven]<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_stop_while_a_pocket_waits_names_the_pocket_in_the_handoff<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_stop_while_a_pocket_waits_names_its_waiting_steps<br>tests/acceptance/test_a_red_checkpoint_stops_for_a_person.py::test_a_budget_stop_while_a_pocket_waits_names_the_pocket<br>scripts/test_loop_waiting_envelopes.py::test_every_stop_cause_carries_the_waiting_pockets<br>scripts/test_loop_waiting_envelopes.py::test_the_stop_envelope_carries_the_waiting_pockets_under_stop<br>scripts/test_loop_waiting_envelopes.py::test_the_stderr_block_names_each_waiting_pocket_and_its_steps<br>scripts/test_loop_waiting_envelopes.py::test_the_handoff_paragraph_names_each_waiting_pocket_and_its_steps<br>scripts/test_loop_waiting_envelopes.py::test_a_stop_object_has_no_waiting_key_when_no_pocket_waits | scripts/_step_loop_cli.py::stop_envelope<br>scripts/_step_loop_render.py::stop_stderr<br>scripts/_step_loop_render.py::stop_next_action<br>scripts/step_loop.py::run_next | PASS |
| REQ-15 | tests/acceptance/test_the_checkpoint_runs_each_waiting_pocket_once.py::test_a_single_pocket_project_runs_only_the_check_at_the_gate_and_its_suite_at_the_checkpoint | scripts/step_loop.py::run_next<br>scripts/step_loop.py::_checkpoint_due | PASS |
| REQ-16 | tests/e2e/test_a_plan_whose_every_step_widens_pays_each_suite_once.py::test_every_widened_pocket_runs_whole_once_at_the_checkpoint_and_never_at_a_gate[a-pocket-of-its-own]<br>tests/e2e/test_a_plan_whose_every_step_widens_pays_each_suite_once.py::test_every_widened_pocket_runs_whole_once_at_the_checkpoint_and_never_at_a_gate[named-like-praxions-eval]<br>tests/e2e/test_a_plan_whose_every_step_widens_pays_each_suite_once.py::test_every_widened_pocket_runs_whole_once_at_the_checkpoint_and_never_at_a_gate[named-like-praxions-mcp] | scripts/step_loop.py::run_next<br>scripts/step_loop.py::_checkpoint_due | PASS |
| REQ-17 | tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_the_test_scope_command_is_byte_for_byte_the_base_commits[scripts/resolve_test_scope.py]<br>tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_the_test_scope_command_is_byte_for_byte_the_base_commits[scripts/_python_selection.py]<br>tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_the_test_scope_command_is_byte_for_byte_the_base_commits[scripts/_native_selection.py] | — (unchanged by construction; its guard nodes are the evidence) | PASS |
| REQ-18 | tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_records_the_base_driver_wrote_over_a_widened_step_read_as_they_did[widened-all-done]<br>tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_records_the_base_driver_wrote_over_a_widened_step_read_as_they_did[widened-then-outstanding]<br>tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_reading_the_base_drivers_records_runs_no_checkpoint_and_rewrites_none[widened-all-done]<br>tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_reading_the_base_drivers_records_runs_no_checkpoint_and_rewrites_none[widened-then-outstanding]<br>scripts/test__step_loop_checkpoint.py::test_a_results_file_written_before_deferrals_existed_makes_no_pocket_wait<br>scripts/test__step_loop_checkpoint.py::test_an_empty_results_file_and_no_records_make_no_pocket_wait | scripts/_step_loop_checkpoint.py::waiting_pockets<br>scripts/step_loop.py::read_task | PASS |
| REQ-19 | tests/acceptance/test_what_the_deferral_leaves_as_it_was.py::test_the_three_fast_gate_probes_pass | — (unchanged by construction; its guard nodes are the evidence) | PASS |

## Key Decisions

- **[user] Proceed as confirmed (SQ-01)**: only `selection: full` pockets wait. **Why**: the driver-repairs cost that prompted the change came from the second pocket's narrow near-whole selection (115 of 117 test files, about 483 s), which a widened-pocket deferral does not touch; the radius is td-688. **Alternatives**: deferring a near-whole narrow selection (contradicts "the tests its change reaches"), re-scoping to the radius.
- **[systems-architect] A step with no check and a goal step gate as today (SQ-02)**; no plan-declared earlier checkpoint.
- **[systems-architect] The waiting set is derived, never stored**: no second writer, replay keys reused. **Alternatives**: a state file.
- **[implementation-planner] Two modules, not one**: the gate imports the deferral grammar and the run imports the gate's reading, so one module would be an import cycle (`85177ad9`).
- **[orchestrator, user-confirmed] A `record` never runs the checkpoint**: the last step's `record` with a pocket waiting stops `checkpoint-due` (resume `next`), and `status` reads that state as the same stop. **Why**: REQ-01 and nine acceptance nodes forbid a widened run in `record`; REQ-08 keeps `complete` for green checkpoint runs; the outcome set is closed. **Alternatives**: `complete` (an orchestrator would leave the loop with suites unrun), a new outcome word, the design's original chained run.
- **[orchestrator] SQ-03, a scenario's setup amended**: the budget scenario spent 3 of 4 iterations and could not reach the stop it asserts; one red attempt added, assertions unchanged (`4e10fb64`).
- **[verifier] Two WARNs declined**: `run_gate` at 49 of 50 lines and `scripts/_step_loop_io.py` at 777 of 800 lines; both under their ceilings, to be split on their next edit.
