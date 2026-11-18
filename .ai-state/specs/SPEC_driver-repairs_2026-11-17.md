# Spec: driver-repairs (the step-loop driver's repairs, three hooks and tests that read what the machine supplies)

**Task slug**: `driver-repairs`
**Feature**: Repairs to the step-loop driver (`scripts/step_loop.py` and the modules behind it) found by driving three earlier pipelines through it, with a commit gate that judges only real commits, a hook that says where a Bash call left the session, three tests that no longer read what the machine supplies, and the lessons of the pipelines before it placed in the artifacts that govern them.
**Tier**: Full (budget 32 charged agent starts, used 19, planned 14, the archival's own start the nineteenth; 29 plan steps, 15 of them through the step loop, in 37 of its 66 iterations)
**Pipeline branch**: `worktree-driver-repairs`
**Start date**: 2026-11-16
**End date**: 2026-11-17
**Archived**: 2026-11-17 (before the merge, at head `328ce460`; the merge is the user's)
**Status**: completed -- verified: PASS WITH FINDINGS after two passes (first pass 1 FAIL and 9 WARN, second pass 0 FAIL and 5 WARN; each finding of the second pass was fixed before the merge; the second pass did not reach the mutation of REQ-28's nested suite)
**ADRs**: four drafts under `.ai-state/decisions/drafts/`, promoted at the merge, whose finalize rewrites their ids in this file: `dec-517` (category: architectural -- the request lifecycle read as one sum type, and the record lock), `dec-516` (category: architectural -- one ownership rule for Read-only entries), `dec-518` (category: implementation -- the commit gate asks a stdlib reader of the command), `dec-519` (category: architectural -- the working-directory notice hook). Each was amended after it was written to say what was built (`c4fdba53`, `fa534b3a`, `328ce460`); the commit gate's and the notice hook's carry an `As built` section.
**Evidence base**: the pipeline's 42 commits `38fa7725..328ce460` (the worktree was cut at `fbac3a2e`; `38fa7725` is the state commit the acceptance tests and the footprint baselines are measured from); the acceptance tests committed test-only before any production code (`53384787`); the integration checkpoint run twice, every pocket green both times: on `c7dfabf4` before verification, and on `fa534b3a` after the fix batch for the first verification pass (main pocket 20,442 passed, 5 skipped and 1 expected failure; 896, 4,781 and 288 in the other three; the three gate probes and the two liveness tests pass); after it one more code commit (`02187d79`), whose derived scope passed on its tree (6,548, 4,781 and 128), with the commit reader's, the commit gate's and the record path's unit suites re-run green on `328ce460` at archival (302 and 162 passed); the pipeline's completion row in `.ai-state/calibration_log.md` dated 2026-11-17; the 22 ledger rows resolved against these commits.

## Feature Summary

Before this change every pipeline paid for the step-loop driver's gaps each time it ran through it. The three pipelines before this one lost implementer attempts, a re-tier and hours of hand work to them: a request that could not be taken back without being issued again; a read-only entry naming one test that kept its whole file out of the commit; a red test owned by a later step that read as a failure in any pocket but the root; a second-round review that accepted and was read as a second revise; printed commands that dropped the base the caller gave; a plan defect that cost an attempt; a record call that could be run twice. Each had a workaround in a prompt or a reference, kept alive by memory.

The driver now gives a moment with no request out: a withdrawal issues nothing, and the plan is amended in that moment. One ownership rule serves the gate, the commit and the prompt, in every pocket. A review file's current round is read above a superseded-record heading. Every printed command carries the location options the caller gave, so the relay gives the base once. A plan field that cannot be read, a check that cannot print a summary and a plan changed while a request is out each stop under a cause of their own, at no attempt. A record in flight holds an operating-system lock that a second record and the stop guard can see. The driver copies a return's follow-up line into the follow-up record itself. A result block's command line keeps to a ceiling, with the whole command in a file.

Three things outside the driver went with it. The commit gate reads the command exactly and asks a stdlib reader, so a read-only command that mentions a commit starts no checker, and its first test no longer sits behind a pipe that read a dead producer as no commit. A shell-only hook tells the agent where a Bash call left the session, after a call that succeeds and after one that fails. Three acceptance tests no longer read what the machine supplies (an ambient variable, a wall-clock guess, a bound under load). Twenty lessons that lived in session prompts are in the skills and references that govern the behaviour they are about, and five interim workarounds went with the defects they stood in for.

Shape of the delivery: the acceptance tests were designed from the specification alone and committed before any production code; two architect passes; 29 plan steps, of which 15 ran through the loop this pipeline repairs, from a pinned copy of the last committed driver refreshed after every driver commit. Seven loop steps needed a second or third implementer round (five because the plan's list of the standing tests a step would meet fell short), and one was revised after its review. Three batches of fixes closed the step reviews' remarks before verification, and a fourth closed the verifier's findings, among them the hook's missing registration for failed calls. The hook has not run under a live harness.

## Requirements

Verbatim from the specification as extracted by `extract_spec.py` (digest `f0b2b222c312`), headings one level down. Requirement ids are pipeline-local and appear nowhere in code, tests or docstrings. Two entries of the Observable Surface (a session prompt and a placement plan of the interim lessons) name files of the main checkout's working area: they were inputs to the pipeline, are kept nowhere in the repository, and a later reader cannot open them. The "Open for design" list cites the brief's key signals as KS-nn; the archive does not carry the brief, and the requirement in parentheses is the one each bears on.

### Acceptance Criteria

Interpretation, stated once: "the driver" is the step-loop command and the modules behind it; every requirement below is judged at that command's printed envelope, its exit code and the files it leaves in the task directory, or at a hook's printed output, never at internal names. Stated assumptions are marked **Assumption** inline.

- [ ] Each requirement REQ-01 to REQ-43 below holds, judged by the scenario the acceptance designer derives from it, or, for the text and closure requirements REQ-14, REQ-18, REQ-35 to REQ-39, REQ-41 and REQ-42, by the reviewed reading or table each one names (Not Black-Box Testable: a test pinned to a sentence's wording breaks the next legitimate edit).
- [ ] Every requirement whose title ends "stays unchanged" holds against the base commit: what an existing pipeline observes there, it observes after the change.
- [ ] The existing driver, hook and acceptance tests pass unedited, except the pinned assertions whose contract a requirement changes: each is listed under "Standing tests whose contract changes" below with the requirement that changes it, and is amended under an answered Spec Question.
- [ ] Records the driver wrote before a change (progress-file attempt lines, ledger lines, result blocks, review files, handoff files) are read after it the way they were read before (REQ-40).

#### Standing tests whose contract changes

Each pins today's behaviour of a surface a requirement changes. No other standing test may be edited.

- `tests/acceptance/test_step_loop_stops.py`, `test_the_stop_names_the_command_that_resumes_the_loop`: changed by REQ-15 and ruled on in REQ-17. It pinned the resume command without the base the caller gave.
- `tests/acceptance/test_compaction_orientation_follows_the_driver.py`, `test_the_orientation_names_the_outstanding_request_and_its_record_call`: changed by REQ-15. It looked for the whole record call that one reader printed inside what another reader printed; the two are called with different location options, so it now compares the call up to those options.
- `scripts/test_loop_cli_record_caps.py`, `test_the_withdrawal_envelope_is_the_next_action_with_a_recorded_object_and_no_ledger`: changed by REQ-01. It pinned a withdrawal that issues the request again in the same call.
- `scripts/test_loop_cli_next.py`, `test_a_record_refused_after_a_step_block_revision_names_the_cause_and_the_way_back`: changed by REQ-03. It pinned the refusal of a withdrawal after the plan changed.
- `scripts/test_goal_run_guards.py`, `test_the_request_that_would_have_followed_is_withdrawn_unspent`: changed by REQ-01. It pinned the attempts line of a request issued again at once.
- `tests/acceptance/test_a_refused_record_names_the_revision_and_the_recovery.py`, `test_following_the_recovery_records_the_request_and_resumes_the_loop`: changed by REQ-04. It re-applied a revision while a request was out and expected a second request to be issued; it now takes the unstarted request back first.
- `scripts/test_loop_state_bound.py`, `test_the_causes_are_the_closed_set_the_stop_texts_cover`: changed by REQ-04 and REQ-26. It counts the stop causes, and two are added.
- `scripts/test_loop_io_vcs.py`, the node-form cases of `test_a_read_only_entry_withholds_its_path_in_every_form`, of `test_a_read_only_entry_in_any_spelling_keeps_a_declared_directory_file_out` and of `test_a_read_only_entry_of_any_step_keeps_a_file_out_of_the_commit`: changed by REQ-07. They pinned that an entry naming one node withholds its whole file from a commit. Their bare-path and directory cases stay as they are (REQ-08).
- `scripts/fixtures/step_loop_prompt_golden.md`, the fixture that `scripts/test_loop_render_module.py`, `test_the_rendered_prompt_is_pinned_byte_for_byte_by_the_golden_fixture` compares a rendered implement prompt with, byte for byte: changed by REQ-11, which adds two sentences to the closing instructions. The fixture is regenerated; the test's assertion is not edited.
- `scripts/test_loop_bound_readers.py`, `test_an_unreadable_iterations_field_is_a_human_verdict_to_the_driver_state`: changed by REQ-19. It pinned that an unreadable iterations value reads to the driver's state as a human verdict of unknown; the state now names the field that cannot be read.
- `scripts/test_loop_one_state.py`, `test_every_state_kind_has_a_case_and_every_case_gives_a_word_of_the_closed_set`: changed by REQ-19. Its table holds one case for every kind of series state, and one kind is added; the closed set of status words stays as it is.
- `scripts/test_loop_invocation.py`, `test_drive_by_default_prints_a_then_that_ends_at_the_request_id_and_its_placeholders`: changed by REQ-01. It pinned the request issued again after a withdrawal.
- The unit tests that pin the cause human-verdict, or its action line, for an unreadable Iterations or Change type value: changed by REQ-24. The step that meets them names each one before it edits it.
- `tests/acceptance/drivers/step_loop.py`, the environment it gives a scenario: changed by REQ-30. It let a gate's own pocket-timeout override reach the scenario's task. No assertion changes.
- `tests/acceptance/drivers/compaction_orientation.py` and the scenarios of `tests/acceptance/test_compaction_orientation_follows_the_driver.py` that run the real driver: changed by REQ-29. They depended on the driver answering inside the hook's own bound on a loaded machine. One assertion is added (the call the hook makes); none is weakened.
- `tests/acceptance/drivers/adherence_eval.py`, the limit it gives the nested eval suite: changed by REQ-28. It was a fixed figure unrelated to the bound of the run that contains the test. No assertion changes.
- The five nodes that hold the PR rule's Cursor copy byte for byte, in `tests/acceptance/test_exports_stay_byte_identical.py`, `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py`, `tests/acceptance/test_other_channels_carry_the_kernel.py`, `tests/acceptance/test_routing_facts_keep_every_other_reach.py` and `tests/acceptance/test_routing_move_keeps_every_other_reach.py`: changed by REQ-36. Their frozen fixtures are regenerated by the method that produced them, and each fixture's change is the rule's copy and nothing else.

#### Rows found already fixed

Each line names the evidence on this head (worktree cut from the base commit fbac3a2e). None of these is a requirement; the verifier confirms each line still holds.

- td-354, item "a review due with no commit range stops as loop-state-defect with no step": fixed. On this head such a review stops under its own cause, review-without-work, naming the step and saying no commit holds its work (read on this head; the triage of 2026-11-13 says the same).
- td-354, item "a replayed record of a review request reports a null review verdict": fixed. A replayed record of a review request reads the review file's verdict and reports it (read on this head).
- td-353, the derived-scope part: fixed. The derived-scope command no longer appears whole in a block (a summary line names at most three declared files). Of the driver blocks in the four parked results files, two still exceed the ceiling (1,136 and 1,026 bytes, both in one pipeline), and both are over because their Command line holds the plan's Check command verbatim, 752 characters long. REQ-27 specifies that residual. td-354's fourth item (the attempt check) still holds and is REQ-26.
- td-354, item "the review module imports the ledger at runtime for an annotation-only name": fixed. The review module now imports the ledger name only for type checking, like its siblings (read on this head).
- td-561, part: the Stop guard already lets a stop through while a gate run of the outstanding request is live inside its bound (the guard's probe reads the run's start record). What remains open is specified in REQ-19 to REQ-21.

#### How each row was checked on this head

- Driven on scratch checkouts outside the worktree, through the driver's command line: td-560, td-658, td-659, td-648, td-655, td-537, td-351 (each holds as the requirement's "Observed" line says).
- Read on the code path: td-654, td-650, td-561, td-573, td-652, td-354 (four items, decided separately above), td-151, td-670, td-671 (the commit gate's fast path tests the whole stdin payload for git followed by commit).
- Measured on the parked results files: td-353.
- Not reproduced in this phase, taken from the rows' own reproductions: td-640, td-653, td-656, td-657 (each needs a saturated machine or a specific ambient override inside a step gate) and td-669 (its one open fact needs a live session).

#### Rows whose observed failure differs from the row's text

- td-655 says a red node is held pending for its later owner only when it is an outer-loop test. Observed on this head: a root-pocket unit-test node that a later, not-done step names reads as pending (gate line pending=1, step verified complete). The failure is per pocket, not per outer-loop-ness: a node in a non-root pocket named repository-relative by the later step reads as a failure (gate line fail=1, a Failed line naming the node, an attempt spent). This is td-537's cause; REQ-09 specifies the observed behaviour.
- td-351 says a bare call keeps its resume text because a standing test pins it. Observed: the pinning test drives the call with the repository-root and base-ref options and asserts the resume command carries neither, so it pins the defect itself, not a bare call. REQ-17 rules on it.
- td-659 says the second round "keeps the first round's record at the end of the file". Observed in the parked record: the reviewer wrote its own verdict on the file's first line, then a separator and a section headed as the superseded first-round record holding its own bare verdict line. REQ-05 specifies that shape.

#### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | always-loaded-tokens | always-loaded tokens of the worktree | at or below | 25000 tokens | reference: the published always-loaded budget | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | listing-tokens | listing tokens of agents and skills | at or below | the baseline plus 40 tokens | baseline: listing tokens at the base commit | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | prompt-size | lines of the implementation planner's definition, and every agent against its fail ceiling | at or below | the baseline plus 4 lines, and no agent over its fail ceiling | baseline: line counts at the base commit | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-04 | hook-latency | median wall time of the commit gate on a read-only Bash payload whose command or other fields name both git and commit, over 20 runs | at or below | the baseline median of a payload naming neither word, plus 30 ms | baseline: the commit gate on a payload naming neither word, at the base commit | `/usr/bin/time -p <command...>` |

#### Footprints Not Measured

| Footprint | Reason |
|---|---|
| spawn-count | the only spawn-count instrument counts a pipeline that has already run, not a change |
| spawn-startup-tokens | its only instrument starts a headless claude session, which this pipeline may not start without the user's go at that moment |

### Behavioral Specification

#### Observable Surface

The driver, its verbs, options and printed fields:

- `step_loop.py`, `python3 scripts/step_loop.py` -- the driver, in its two printed forms
- `next`, `record`, `status`, `run` -- its verbs
- `--base-ref`, `--repo-root`, `--worktree-root`, `--request`, `--agent-id`, `--marker`, `--not-started`, `--session-exited`, `--json` -- its options
- `outcome`, `spawn`, `complete`, `needs-human`, `error` -- the envelope's outcome field and values
- `request`, `request.id`, `request.step`, `request.kind`, `request.reissued`, `then` -- the spawn fields
- `stop`, `stop.cause`, `stop.step`, `stop.evidence`, `stop.resume`, `stop.handoff` -- the stop fields
- `recorded`, `recorded.review_verdict`, `recorded.stop_reason`, `recorded.commit`, `recorded.gate`, `recorded.gate.verdict`, `recorded.replayed` -- the record fields
- `warnings`, `outer-loop-edit`, `undeclared-edit` -- the warnings list and two of its codes
- `error.code`, `error.message`, `request-not-pending`, `gate-running`, `agent-running`, `worker-not-started` -- error fields and codes
- `loop-state-defect`, `review-revised-twice`, `human-verdict`, `attempts-exhausted`, `not-driven` -- existing stop causes
- `verified-complete`, `mismatch`, `pending=`, `fail=`, `Failed:` -- gate verdicts and result-line tokens
- `s1-a1-implement`, `s1-a1-review-r2` -- request ids in the driver's printed shape (step, attempt, kind, round)
- exit codes 0, 2, 3, 4 and 1 as the driver's documented contract assigns them

Plan, progress and task-directory files the driver reads or writes:

- `IMPLEMENTATION_PLAN.md`, `WIP.md`, `ITERATION_LEDGER.jsonl`, `TEST_RESULTS.md`, `HANDOFF.md`, `FOLLOW_UPS.md`, `PROMPT_<request>.md`, `LIGHT_REVIEW_step-<id>.md`
- `Files:`, `Read-only:`, `Check:`, `Iterations:`, `Change type:`, `review: force`, `Attempts:`, `Done when:` -- plan and progress fields
- `path::node` -- a node entry of a plan field; `tests/acceptance` -- the outer-loop test directory; `eval` -- a non-root pocket (a directory with its own pytest configuration)
- `Result:`, `by=step-loop`, `Scope:`, `Derived from:`, `Command:` -- lines of a result block the driver writes
- `scripts/check_test_results_shape.py`, `check_test_results_shape.py` -- the result-block shape checker and its green-section ceiling
- `python3 scripts/measure_token_budget.py --json`, `python3 scripts/check_agent_prompt_size.py --json`, `/usr/bin/time -p <command...>` -- the footprint instruments the criteria name
- `- [open] <item>` -- the open line shape of the follow-up record
- `Follow-ups:` -- the implementer's return line `Follow-ups: <item>; <item>`
- `verdict:`, `verdict: accept`, `verdict: revise`, `verdict: [PARTIAL]` -- light-review verdict lines
- `python3 -m pytest`, `uv run python -m pytest`, `--collect-only` -- Check commands and the collection probe
- `PRAXION_STEP_LOOP_POCKET_TIMEOUTS`, `PRAXION_STEP_LOOP_GATE_WAIT_SECONDS`, `PYTEST_XDIST_AUTO_NUM_WORKERS` -- environment the gate reads

Hooks, their inputs and outputs:

- `hooks/guard_step_loop_stop.py` -- the Stop guard; its output `{"decision": "block", "reason": ...}` or nothing
- `hooks/commit_gate.sh` -- the commit gate on Bash calls; the gated checkers it starts
- `hooks/hooks.json` -- hook registrations
- `Stop`, `PreToolUse`, `PostToolUse` -- hook events; `cwd`, `tool_input.command`, `tool_input.description`, `transcript_path`, `session_id` -- payload fields
- `additionalContext` -- the context a hook adds beside a tool result
- `git commit`, `git log`, `git status`, `git add`, `git -C`, `bash -c`, `sh -c`, `cd` -- command forms the hooks judge

Shipped and repository Markdown whose text a requirement changes:

- `skills/step-loop/SKILL.md`, `skills/step-loop/references/stop-recoveries.md`
- `agents/implementation-planner.md`, `agents/verifier.md`
- `rules/swe/vcs/pr-conventions.md`, `skills/merge-worktree/SKILL.md`
- `skills/software-planning/references/document-templates.md`, `skills/software-planning/references/intra-step-review.md`, `skills/software-planning/references/tech-debt-ledger.md`, `README_DEV.md`
- `TEST_BASELINE.md` -- the planner's baseline record
- `.ai-state/TECH_DEBT_LEDGER.md` -- the ledger rows this pipeline closes or files
- `tmp/praxion-next-session-prompt-2026-11-16.md` -- the main checkout's session prompt holding the fourteen prompt-only lessons, section "Lessons not yet in the artifacts"
- `.ai-work/_harvest/handoff-lessons/PLACEMENT_PLAN.md` -- the main checkout's placement plan of the interim lessons

Standing tests named by a requirement:

- `tests/acceptance/test_step_loop_stops.py`, `test_the_stop_names_the_command_that_resumes_the_loop`
- `tests/acceptance/test_adherence_eval_tests_start_no_claude.py`, `test_the_eval_suite_passes_without_ever_starting_claude`, `tests/acceptance/drivers/adherence_eval.py`
- `tests/acceptance/test_compaction_orientation_follows_the_driver.py`, `hooks/inject_compaction_orientation.py`
- `tests/acceptance/test_abandoned_gate_run_is_stopped.py`
- `test_the_orientation_names_the_outstanding_request_and_its_record_call`
- `scripts/test_loop_cli_record_caps.py`, `test_the_withdrawal_envelope_is_the_next_action_with_a_recorded_object_and_no_ledger`
- `scripts/test_loop_cli_next.py`, `test_a_record_refused_after_a_step_block_revision_names_the_cause_and_the_way_back`
- `scripts/test_goal_run_guards.py`, `test_the_request_that_would_have_followed_is_withdrawn_unspent`
- `tests/acceptance/drivers/step_loop.py`, `tests/acceptance/drivers/compaction_orientation.py`
- `tests/acceptance/test_a_refused_record_names_the_revision_and_the_recovery.py`, `test_following_the_recovery_records_the_request_and_resumes_the_loop`
- `scripts/test_loop_state_bound.py`, `test_the_causes_are_the_closed_set_the_stop_texts_cover`
- `scripts/test_loop_io_vcs.py`, `test_a_read_only_entry_withholds_its_path_in_every_form`, `test_a_read_only_entry_in_any_spelling_keeps_a_declared_directory_file_out`, `test_a_read_only_entry_of_any_step_keeps_a_file_out_of_the_commit`
- `scripts/fixtures/step_loop_prompt_golden.md` (the pinned implement prompt), read by `scripts/test_loop_render_module.py`, `test_the_rendered_prompt_is_pinned_byte_for_byte_by_the_golden_fixture`
- `scripts/test_loop_bound_readers.py`, `test_an_unreadable_iterations_field_is_a_human_verdict_to_the_driver_state`
- `scripts/test_loop_one_state.py`, `test_every_state_kind_has_a_case_and_every_case_gives_a_word_of_the_closed_set`
- `scripts/test_loop_invocation.py`, `test_drive_by_default_prints_a_then_that_ends_at_the_request_id_and_its_placeholders`
- `tests/acceptance/test_exports_stay_byte_identical.py`, `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py`, `tests/acceptance/test_other_channels_carry_the_kernel.py`, `tests/acceptance/test_routing_facts_keep_every_other_reach.py`, `tests/acceptance/test_routing_move_keeps_every_other_reach.py`

#### REQ-01: A withdrawn request leaves no request out

When the driver has issued a request that no agent started (the progress file's attempts line names it, the ledger does not),
and the orchestrator runs record for it with the not-started option and a reason,
the system prints an envelope that issues no request (its outcome is not spawn and it carries no request field) and that names, in a printed command, the call that continues the loop, and afterwards the progress file names no outstanding request for that step, and status reports no request out,
so that the orchestrator holds a moment with no request out, the only state in which a plan block may be amended.

Observed on this head (td-560): the same call prints outcome spawn with the same request id, reissued false, so no such moment exists.

#### REQ-02: A withdrawn attempt costs no attempt and is issued again by next

When a request was withdrawn as in REQ-01 and the plan is left as it was,
and the orchestrator runs next,
the system issues exactly one request, for the same step, with the same attempt number the withdrawn request carried, and the step's attempt count is unchanged by the withdrawal,
so that a failed Agent call is retried without spending an attempt, as today.

#### REQ-03: The plan may be amended while no request is out

When a request was withdrawn as in REQ-01,
and a person then amends the plan, either inserting a new step block that the plan orders ahead of the withdrawn step or revising the withdrawn step's own block,
the system's next call issues exactly one request, for the step the amended plan puts first, and prints no stop, no error and no warning about a revised block,
so that a step can be put ahead of the next without a hand edit of the progress file.

Observed on this head (td-658): after the insertion, record with the not-started option is refused (error code request-not-pending), next issues the inserted step's request while the other is still outstanding, the inserted step's record is refused, and every later next stops with cause loop-state-defect naming two outstanding requests.

#### REQ-04: No documented call sequence leaves two requests out

When a request is outstanding (issued, not recorded, not withdrawn),
and the plan has been changed so that another step would now come first, or any other sequence of next, record and status calls is made,
the system never issues a second request while the first is outstanding: next either issues the outstanding request again (reissued true) or prints a stop or an error whose text names the outstanding request id and the record call that takes it back, and the progress file never names two outstanding requests,
so that a plan change made at the wrong moment costs one corrected call, not a loop that refuses every later call, records included.

#### REQ-05: A second-round accept is read as accepted whatever the first round left after it

When a step marked for a light review has had its first review answer revise and its revision recorded green,
and the second-round reviewer leaves a review file whose first line is verdict: accept, whose second line names the step and round 2, and which then holds, after a separator, the superseded round-1 record including its own bare line verdict: revise, and the reviewer's final message carries verdict: accept and the complete marker,
the system's record of that review reports the review verdict accept, prints no stop with cause review-revised-twice, and the loop goes on to the step's successor,
so that an accepted second round never reads as a second revise.

Observed on this head (td-659): the record prints review verdict revise and stops with cause review-revised-twice.

#### REQ-06: Review readings that stay unchanged

When a review file holds a single round written as the review prompt asks (verdict: [PARTIAL] first, findings, the verdict line last), or a second round whose own verdict is revise,
and its review request is recorded,
the system reads the verdict as it does on the base commit: accept accepts, revise asks for a revision after the first round and stops with cause review-revised-twice after the second, and a file whose only verdict is [PARTIAL] reads as unfinished,
so that the repair changes no reading a correct review file gets today.

#### REQ-07: A node entry does not withhold its file from the step that owns the file

When step A's Files names a test file and a later step B's Read-only names one node of that file in the path::node form,
and step A (or any step whose Files names that file) returns complete with that file edited and its gate green,
the system's commit for that step includes the file, and its envelope carries no outer-loop-edit warning for it,
so that a node entry means the same thing to the gate and to the commit: it says who owns the node's verdict, not that the file may not be committed.

Observed on this head (td-648): the commit of the step whose Files names the file leaves it out, the envelope warns outer-loop-edit naming it, and the edit stays uncommitted while the step reads verified complete.

#### REQ-08: Withholding that stays unchanged

When a step edits a file under the outer-loop test directory, or a file that some step's Read-only names as a bare path (no node part) and that the editing step's Files does not name,
and the step's return is recorded,
the system leaves that file out of the commit and warns outer-loop-edit naming it, as on the base commit,
so that an outer-loop test still cannot be committed by the step it judges.

**Assumption**: a bare-path Read-only entry that the same step's Files also names keeps today's reading (withheld); only the node form changes. The design may propose otherwise through a Spec Question.

#### REQ-09: A red node a later step owns reads as pending in every pocket

When the step being gated turns a test node red, and a later step that is not done names that node in its Read-only field, by the node's repository-relative id,
and the node lives in the root pocket as an ordinary unit test, or under the outer-loop test directory, or in a non-root pocket such as eval,
the system's gate counts the node as pending (the result line's pending count includes it and its fail count does not), names no Failed line for it, and reads the step verified complete when nothing else is red,
so that a plan can schedule a re-pin of a test in any pocket after the step that changes its value, without spending the earlier step's attempt.

Observed on this head (td-537, td-655): the root-pocket case reads pending; the eval-pocket case reads fail=1 with a Failed line naming the node, verdict mismatch, and a second attempt is issued.

#### REQ-10: Ownership that stays unchanged

When a red node is named by no Read-only entry, or only by the gated step's own entry, or only by a step already done, or by entries tied for longest of which one is the gated step's own,
and the step is gated, in any pocket,
the system counts the node as a failure, as on the base commit,
so that widening ownership to every pocket never turns a real failure into pending.

#### REQ-11: The rendered prompt says who runs what

When the driver renders the prompt of an implement or a revise request,
and an agent reads that prompt file,
the system's prompt states that the driver runs the step's derived test scope itself once the agent returns, and that the agent runs the step's Check command (in the foreground, finished before it returns) and does not start the derived scope or a whole suite itself,
so that an agent on the cheapest model does not compete with the gate for the machine.

Observed on this head (td-654): the implement and revise prompts' closing instructions say to record a result section ending with the Check's result line and never to commit; they say nothing about the derived scope.

#### REQ-12: A Follow-ups line reaches the follow-up record through the driver

When an implementer's or reviser's final message holds a line "Follow-ups: first item; second item" before its terminal marker,
and the orchestrator records that request (whatever the marker and the gate verdict),
the system appends one line of the form - [open] <item> per item, in order, to the task's follow-up record (creating the file when absent), keeps every line already there unchanged, and a second record call for the same request (a replay) appends nothing more,
so that small out-of-scope debt reaches the record without the orchestrator reading the return for it.

Observed on this head (td-650): no part of the driver writes the follow-up record; only the shipped ledger reference tells the orchestrator to copy the line.

#### REQ-13: A return with no Follow-ups line writes nothing

When a final message holds no Follow-ups line, or one with no item after the colon,
and its request is recorded,
the system leaves the follow-up record byte for byte as it was (absent stays absent),
so that the record holds only what an agent reported.

#### REQ-14: The shipped follow-up guidance matches what the driver does

When a reader follows the tech-debt-ledger reference and the step-loop skill for a pipeline whose implementer steps run through the driver,
and an implementer's return carries a Follow-ups line,
the system's guidance says the driver copies the line's items into the follow-up record when it records the return, and keeps the orchestrator's copy step only for returns that do not pass through the driver,
so that no instruction asks the orchestrator to copy what the driver already copied. The proof is a reviewed reading of the two files, not a scenario.

#### REQ-15: Printed commands carry the base the caller gave

When the caller runs next, record or status with the base-ref option (alone, or with the repository-root or worktree-root options),
and the driver prints a then command, a stop's resume command, the next-action line of the handoff file, or the next command that the status table's last line names when a request is due and none is out (before the loop's first request, and after a withdrawal as in REQ-01),
the system ends each printed command with every one of those location options exactly as the caller gave them, so running the printed command verbatim keeps the caller's base,
so that a pipeline whose verdict base differs from the merge-base default can follow the skill's rule to run only the printed commands.

**Assumption**: "any other state flag" in td-351 means the three location options; the run verb already echoes them and stays as it is.

A call that gives a location option without the base-ref option echoes the options it gave in the same way. Two readers called with different location options therefore print the same command up to those options, and no reader echoes an option it was not given.

#### REQ-16: A bare call's printed commands stay unchanged

When the caller runs next, record or status with none of the three location options,
and the driver prints a then or resume command,
the system prints exactly the text it prints on the base commit (the program form, the verb, the slug and, for then, the request, agent-id and marker placeholders, with no option appended),
so that a pipeline already relying on the bare form sees no change.

#### REQ-17: Ruling on the pinned resume text

When the standing test test_the_stop_names_the_command_that_resumes_the_loop in tests/acceptance/test_step_loop_stops.py drives the stop with the repository-root and base-ref options and asserts the resume command equals the bare form,
and REQ-15 holds,
the system's resume command for that call carries both options, so the test's exact-equality assertion no longer holds; this spec rules that the pinned text changes for that call (the test's subject, "the stop names the command that resumes the loop", stays), and the change goes through an answered Spec Question to the test's owner,
so that the one standing test pinning the defect is named before any step meets it.

#### REQ-18: The step-loop skill stops telling the relay to add the base by hand

When a reader follows the step-loop skill's procedure for a worktree whose base is not the merge-base,
and reads its first step,
the system's skill text says to give the base-ref option on the first call and then run the printed commands as printed, and no longer says that the printed then omits it,
so that the procedure and the driver agree. The proof is a reviewed reading of the skill, not a scenario.

#### REQ-19: The Stop guard does not demand a record that is already running

When a record call for an outstanding request is still running (in the foreground, or moved to the background by the tool's time limit), at any point of that call (waiting on the agent's end, waiting on or between gate runs, running the Check, committing),
and the session's turn ends so the Stop guard runs,
the system's Stop guard prints nothing (the stop goes through), or prints a message saying the record for that request is in flight and must not be run again,
so that the guard never asks for a second record of the same request.

#### REQ-20: A second record call cannot write beside the first

When a record call for a request is running,
and a second record call for the same request starts before the first ends,
the system's second call writes nothing to the ledger, the result file, the progress file or git, and exits with an error envelope whose message names the running record (or waits and then answers as a replay of the first call's outcome); the ledger holds exactly one record for the request once both have ended,
so that a demand made while a record is in flight cannot corrupt the ledger.

#### REQ-21: The Stop guard's hold that stays unchanged

When no record call is running for a request whose agent has ended unrecorded and no gate run of it is live,
and the Stop guard runs,
the system holds the stop once with the exact record command, as on the base commit, and passes a stop when the hook input says a stop hook already held it,
so that the guard still catches a return left unrecorded.

The cause of a record call outliving the 600-second tool ceiling (td-561) is not established in this phase; the design phase reproduces or bounds it (see Open for design).

#### REQ-22: A Check that cannot print a summary is caught before it spends an attempt

When a plan step's Check command, run under the interpreter and environment the driver will run it with, cannot print a pytest summary (for example a bare python3 -m pytest under an interpreter that lacks a plugin the project's pytest configuration requires),
and the driver is about to issue that step's first request, or reads the plan for any call,
the system either refuses with a stop or an error naming the step, the Check command and what its collection printed, before any request for the step is issued, or runs the Check under an interpreter that can print the summary; in neither case does a gate read the step as a mismatch for a Check that printed no summary, and no attempt is counted for it,
so that a plan defect costs no implementer attempt.

Observed on this head (td-573): nothing in the driver's plan read or gate probes whether a Check can collect, and the planner's definition names no project runner; a Check with no summary reads as a result of none and the gate reads a mismatch.

#### REQ-23: A Check that collects keeps today's path

When every Check command of the plan prints a pytest summary under the driver's interpreter,
and the driver issues and records the steps,
the system issues, gates and records them as on the base commit, with no extra stop, warning or attempt,
so that the probe costs a sound plan nothing observable.

#### REQ-24: An unreadable plan field stops under a cause of its own

When a step's Iterations or Change type value cannot be read by the driver's plan grammar,
and the driver reaches that step,
the system stops with a stop cause that names an unreadable plan field (a cause distinct from human-verdict and from every other existing cause), whose evidence names the step and the field, and whose handoff next-action line tells the reader to fix that field of the step's block and run the printed resume command,
so that the stop's action line follows from its cause, not from matching another module's wording.

#### REQ-25: Stops for other causes stay unchanged

When a stop arises for any cause other than an unreadable plan field,
and the driver prints it,
the system prints the same cause, evidence and handoff next-action line as on the base commit,
so that adding a cause changes no other stop.

#### REQ-26: An outstanding request whose attempt disagrees with the recorded count is named

When the progress file's attempts line for a step names an outstanding request id whose attempt number differs from the count on that same line,
and the orchestrator runs next or record for that step,
the system does not issue or record a request whose attempt number differs from the recorded count, and its envelope names the disagreement (the step, the request id and the count) in a stop's evidence or a warning,
so that a hand-edited or stale attempts line cannot pass unseen (the td-354 attempt-check residual).

#### REQ-27: Every result block the driver writes fits the shape checker's ceiling

When the driver writes a green result block (marked by=step-loop) for a step whose declared Files list is long (thirty paths of sixty characters), whose derived scope spans three pockets and more than a hundred test files, and whose Check command is 760 characters long (a uv run python -m pytest naming twenty test files),
and the shape checker is run over the result file,
the system's block passes the checker with no green-over-ceiling finding, and the block still lets a reader find the exact Check command that ran (in the block, or in a file the block names),
so that the driver, the canonical writer of these blocks, never writes one its own checker reports.

#### REQ-28: The adherence-eval tripwire test survives a loaded gate and still bites

When the test test_the_eval_suite_passes_without_ever_starting_claude runs inside a step gate's root pocket with as many test workers as the machine has cores, beside another full suite run,
and the eval suite it drives is sound,
the system's test passes, also with an ambient pocket-timeout override naming the eval pocket in its environment; and when the eval suite does start claude (its subject broken), the same test fails,
so that a test a step cannot touch no longer spends that step's attempt (td-640, td-657).

#### REQ-29: The compaction-orientation scenarios survive a saturated machine and still bite

When the scenarios of the compaction-orientation acceptance test run with twelve test workers on a saturated machine,
and the orientation hook is sound and its own subprocess bound is unchanged,
the system's scenarios pass, also with an ambient pocket-timeout override naming the eval pocket in their environment; and when the hook reports the driver position wrongly, they fail,
so that load alone never reads as an unreadable driver position (td-653).

#### REQ-30: The abandoned-gate-run scenario ignores an ambient pocket-timeout override

When the abandoned-gate-run acceptance test runs with an ambient pocket-timeout override in its environment that names the eval pocket, or only the root pocket, or none,
and the stopping it tests is sound,
the system's scenario passes in all three environments; and when an abandoned gate run is not stopped, it fails,
so that a gate run with a pocket override cannot fail it (td-656).

#### REQ-31: The cwd notice tells the agent where the session moved

When a Bash call's command changes the session's working directory and the call ends with the session in a directory other than the project root,
and the agent makes its next move,
the system tells the agent, in one line, the directory the session is now in and the project root, no later than before the agent's next tool call runs (together with that call's own result when the hook payload of that call already shows the new directory),
so that relative paths, the observation log and the worktree guard are not silently read against the wrong directory.

#### REQ-32: The cwd notice stays silent when nothing moved or the session came home

When a Bash call ends with the session at the project root (whether or not its command changed directory), or its command holds no directory change,
and the hook runs,
the system adds nothing to the agent's context, and for a command whose text holds no directory change starts no interpreter (only the shell prefilter runs),
so that every Bash call of every managed project pays nothing when there is nothing to say. A malformed or empty payload adds nothing and exits 0.

#### REQ-33: The commit gate runs no checker for a read-only command that mentions a commit

When a Bash payload's command is not a commit, and the words git and commit appear only in another payload field (the description, the transcript path) or as an argument of a git subcommand other than commit (git log with a grep for commit, git show with a description that says commit),
and the commit gate runs,
the system starts none of the gated checkers and lets the call through,
so that a read-only command is never refused by a checker judging a staged set no commit is about to record (td-671).

#### REQ-34: No real commit skips the commit gate's checkers

When a Bash payload's command records a commit in any of these forms: git commit with a message holding escaped double quotes, single quotes or a newline; git add then git commit chained with and, or, a semicolon or a newline; git with the directory option before commit; an environment assignment before git commit; git commit amend; a commit inside bash -c or sh -c,
and the commit gate runs,
the system runs every gated checker for it, as on the base commit; a command whose form the gate cannot read with certainty also runs them,
so that narrowing the fast path never skips a real commit, the worse failure. The cost bound is FC-04.

#### REQ-35: The planner's baseline step captures every tier a gate or CI job runs

When an implementation planner follows its definition's baseline-capture step in a project where a gate or a CI job runs a test tier that the canonical test target leaves out (a fitness tier, for example),
and it writes the baseline record,
the system's definition directs it to capture each such tier as its own invocation under its own heading in the baseline record, beside the canonical target,
so that a regression in a tier outside the canonical target has a baseline row to be judged against. The proof is a reviewed reading of the definition, not a scenario.

#### REQ-36: The PR rule names the merge procedure's exception

When a reader follows the merge-policy paragraph of the PR conventions rule for a diverged pipeline branch,
and that branch's state files cite its own commit hashes,
the system's paragraph names the exception the merge procedure carries (such a branch may take the target in by a merge commit as its last change, so the target still fast-forwards), and keeps the rebase rule for every other diverged branch,
so that the rule and the merge procedure agree. The proof is a reviewed reading of the rule, not a scenario.

#### REQ-37: Each prompt-only lesson is placed or filed

When the pipeline closes,
and the verifier reads the fourteen lessons of the session prompt's section "Lessons not yet in the artifacts",
the system's lesson table (one row per lesson: the lesson, the artifact that governs it, and either the sentence now present there or the ledger row filed with the reason it could not be placed) has fourteen rows, each judged against the named artifact at the pipeline's head, and no lesson is dropped silently,
so that every lesson lives in an artifact, not in a prompt. The proof is that reviewed table; no scenario pins a lesson's wording.

#### REQ-38: An interim lesson goes only when the row it stands in for is fixed

When the pipeline closes,
and the verifier reads the five interim lessons of the placement plan (L-04, L-05 in part, L-39, L-40, L-43) at their four sites (the document templates' Read-only paragraph, the intra-step review reference's reviewer output contract, the stop recoveries' piece on putting a step ahead of the next, and the developer readme's section on verifying changes),
the system's interim-lesson table names, per lesson, the row it stands in for and that row's state at the pipeline's head, and the lesson's text is removed if and only if that row is fixed by this pipeline: L-04 with td-648 and td-655 (the node-entry warning text goes; the rule that a red unit node needs an owner becomes the owning rule itself); L-05 with td-560 (only its "costs an attempt" clause goes; the rule to list a frozen guard's file under a not-done step's Read-only before the first production gate stays); L-39 with td-658 and td-560 (the whole piece goes); L-40 with td-659 (the whole piece goes); L-43 with td-653, td-656 and td-657 (the environment recipe and the worker cap go),
so that no workaround is removed while its defect stands and none outlives its fix. The proof is that reviewed table.

#### REQ-39: The pipeline closes its rows against their commits

When the pipeline closes,
and the verifier reads the tech-debt ledger and its resolved sibling,
the system shows each row this pipeline fixed as resolved with the commit that fixed it, each row found already fixed as resolved with the evidence line above, each row left open with a note saying why, the spec archived, and the calibration row written,
so that the ledger states what this pipeline changed. The proof is a reviewed table.

#### REQ-40: Records written before a change stay readable after it

When a task directory holds progress-file attempts lines, ledger lines, result blocks, review files and a handoff file that the base commit's driver wrote, including this pipeline's own,
and the changed driver runs status and next over them,
the system reads every record as the base commit's driver does (the same per-step series state, verdicts, attempt counts and outstanding request), prints no unreadable-record finding for any of them, and rewrites none of them,
so that this pipeline, which runs through the driver it changes, never loses its own history at a step boundary.

A printed command is compared without the location options it ends with: those echo the caller's own words (REQ-15) and are no part of how a record is read.

The same holds when the driver decides whether to write a stop's handoff file again and one side carries no location options: a handoff file whose commands carry none (a record the base commit's driver wrote, or one written for a bare call) is not rewritten because the caller now gives a base, and a file whose commands carry them is not rewritten because a later call gives none. When both carry location options and they differ, the next action moved, and the file is written again with the caller's options; a handoff the driver writes for a new stop or a moved one carries the caller's options (REQ-15).

#### REQ-41: Shipped text changes remove nothing whose defect stands

When a shipped Markdown file named on the surface loses a sentence in this pipeline,
and the verifier reads the change,
the system's change table names, per removed sentence, the defect it worked around and the requirement above that fixes it; a sentence whose defect is not fixed is kept,
so that nothing is cut to meet a number. The proof is a reviewed table.

#### REQ-42: The shipped loop guidance describes the withdrawal as the driver does it

When a reader follows the step-loop skill's procedure for an Agent call that failed before any agent started, or the stop recoveries' guidance for putting a step ahead of the next,
and the driver behaves as REQ-01 to REQ-04 say,
the system's guidance says that the not-started record takes the request back and issues none, that the printed command continues the loop, and that a plan block is amended in the moment between the two; it no longer says that a withdrawn request is issued again at once,
so that the relay, and a person amending a plan, follow what the driver does. The proof is a reviewed reading of the two files, not a scenario.

#### REQ-43: A step is told that a file of its own stays its to edit when a node of it is named

When a step's Files names a test file outside the outer-loop test directory and the same step's Read-only names one node of that file in the path::node form,
and the driver renders that step's implement or revise prompt,
the system's prompt states that the named node is the step's to turn green and that the file is the step's to edit; for an entry under the outer-loop test directory it states no such permission,
so that an agent does not read the ownership of a node as a ban on editing its file.

Observed on this head (td-648): the prompt carries the step block as written and says nothing on what a node entry permits; in the pipeline that met it, the implementer read the entry as do-not-edit and stopped.

#### Open for design

- KS-16 (REQ-31): the one unknown fact is whether the PostToolUse payload of the call that ran the directory change already holds the new directory in its cwd field. If it does, the notice rides that call's own result. If it does not, the notice comes at the latest before the next tool call runs (from that call's PreToolUse payload, compared with the directory the earlier PreToolUse saw). The live probe (one session, a two-line hook) decides which; without the user's go for it, the design ships the form that holds under either answer, or cuts the hook to a batch of its own.
- KS-17 (REQ-33, REQ-34): the exact reader of the command field and its cost (FC-04); which ambiguous forms run the checkers.
- KS-08 (REQ-19, REQ-20): why one record call outlives 600 seconds (the scope wait of 480 seconds followed by a Check run held to its own pocket bound is the leading suspect, not established); how the guard and a second call see a record in flight.
- KS-09 (REQ-22): whether the check lives at plan time, in the driver's choice of interpreter, or both.
- KS-02 (REQ-05): which signal identifies the current round (the round named in the file, the request's round, the reviewer's final message).
- KS-03 and KS-04 (REQ-07 to REQ-10): whether one ownership rule serves all three rows.
- REQ-04: whether a misplaced next reissues the outstanding request or stops.

#### Non-goals

- Left for a second pipeline: the reconciler's attribution rows (td-255, td-256, td-309, td-462, td-592, td-326), goal mode (td-366, td-371, td-372, td-651), the mutation sensor's sandbox (td-338, td-510) and the test-file splits (td-536).
- Not this pipeline's: the weekly workflow and the eval tool (td-499, td-500, td-672, td-673, td-674).
- Domain packs: off the plan since 2026-11-16, on the user's word. No requirement here serves it.
- Narrowing what a step gate runs (gating each step on the tests the change reaches, the full pocket at checkpoints): a separate change the user has not confirmed. The gate's derived scope stays as it is.

#### Orchestrator amendments at the spec checkpoint (2026-11-16)

Made before the base commit was recorded, so the acceptance designer's extract carries them.

- REQ-01 now also asks that the withdrawal's envelope names the call that continues the loop: the relay runs only the commands the driver prints, so an envelope that issues nothing must still say what comes next.
- REQ-42 added: the shipped guidance for a failed Agent call and for putting a step ahead of the next must follow the new withdrawal. Without it the skill would still tell the relay that a withdrawn request comes back at once.
- REQ-43 added: td-648 records that the implementer read a node entry as do-not-edit and stopped. REQ-07 repairs the commit; REQ-43 repairs what the agent is told.
- The assumption under REQ-08 is confirmed: a bare-path entry keeps today's reading. The record-time warning already names the file, so the conflict is not silent; a plan-time refusal stays open for design.
- The assumption under REQ-15 is confirmed: the three location options are echoed.
- REQ-17 stands: the pinned assertion changes, through a Spec Question the acceptance designer raises at round 0.
- After design pass B, two questions, both answered by the requirements as written and recorded in the list of standing tests whose contract changes: the three load-sensitive tests can only be repaired in their own drivers (REQ-28 to REQ-30 name them), and the PR rule's sentence moves five frozen copies of the rule (REQ-36). Each is a planned test-only step, not an edit made here.
- The live probe of the working-directory notice is not needed: the scenarios drive both answers of the open payload question, the design is right under either, and neither answer would take anything off the path of a call with nothing to say. No session is started for it.
- After design pass A, two questions on REQ-15 against existing tests, both answered by the requirement text above and by a test-only amendment made before any production commit. The old-records guard compared printed commands whole; REQ-40 now says a printed command is compared without the location options it ends with. The compaction-orientation scenario looked for one reader's whole record call inside another reader's output; REQ-15 now says two readers print the same command up to their own location options. The acceptance criterion on unedited tests names the standing tests whose contract changes.
- Round 0, second question (in which state the status table prints a next command): REQ-15 now names the state. The table's last line names a next command when a request is due and none is out, which is before the loop's first request and, once REQ-01 holds, after a withdrawal. In every other state it names none, and none is asked for.

## Traceability Matrix

Rendered from `traceability.yml` at archival: unit tests and acceptance nodes (outer-loop, designed from the extract alone before any production commit) per requirement, with the files of the implementation. Nine requirements have no scenario by design (REQ-14, REQ-18, REQ-35 to REQ-39, REQ-41 and REQ-42): each is judged by a reviewed reading or table, and its row names the standing files that keep its text. `Status` follows the archival procedure: PASS, because every requirement has tests and the integration checkpoint was green, with a parenthesis where the final verifier's reading adds to the tests or leaves a residual.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 5 -- `scripts/test_loop_request_lifecycle.py` (test_a_current_request_is_withdrawn_and_nothing_is_issued, test_the_withdrawn_envelope_prints_the_next_call_and_exits_zero); `scripts/test_loop_cli_record_caps.py` (test_the_withdrawal_envelope_is_the_next_action_with_a_recorded_object_and_no_ledger); `scripts/test_goal_run_guards.py` (test_the_request_that_would_have_followed_is_withdrawn_unspent); `scripts/test_loop_invocation.py` (test_drive_by_default_ends_a_withdrawal_on_a_then_naming_next_without_the_location) | 2 -- `tests/acceptance/test_a_withdrawn_request_leaves_none_out.py` (test_a_withdrawal_issues_no_request_and_prints_the_call_that_continues, test_after_a_withdrawal_neither_the_progress_file_nor_status_names_a_request_out) | `scripts/step_loop.py`, `scripts/_step_loop_cli.py`, `scripts/_step_loop_record.py` | PASS |
| REQ-02 | 1 -- `scripts/test_loop_request_lifecycle.py` (test_a_request_whose_block_was_revised_is_withdrawn_to_its_earlier_count) | 1 -- `tests/acceptance/test_a_withdrawn_request_leaves_none_out.py` (test_a_withdrawn_attempt_is_issued_again_with_its_number_and_costs_no_attempt) | `scripts/_step_loop_record.py` | PASS |
| REQ-03 | 3 -- `scripts/test_loop_request_lifecycle.py` (test_a_request_superseded_by_a_step_put_ahead_is_withdrawn, test_a_step_put_ahead_gets_its_checklist_line_in_front_of_the_next_one); `scripts/test_loop_cli_next.py` (test_a_record_refused_after_a_step_block_revision_names_the_cause_and_the_way_back) | 3 -- `tests/acceptance/test_a_withdrawn_request_leaves_none_out.py` (test_a_step_put_ahead_of_the_withdrawn_one_is_issued_first_without_a_warning, test_the_withdrawn_steps_own_revised_block_is_issued_without_a_warning, test_the_step_put_ahead_is_recorded_and_the_loop_moves_on) | `scripts/_step_loop_record.py`, `scripts/step_loop.py` | PASS |
| REQ-04 | 5 -- `scripts/test_loop_request_lifecycle.py` (test_an_attempts_line_reads_as_one_arm_of_the_outstanding_request, test_a_request_the_plan_no_longer_issues_stops_and_issues_nothing, test_a_member_of_several_naming_its_own_step_is_withdrawn, test_status_names_the_request_the_reading_holds_out, test_status_names_a_reissued_request_the_base_driver_wrote_as_it_did) | 3 -- `tests/acceptance/test_a_withdrawn_request_leaves_none_out.py` (test_a_plan_changed_while_a_request_is_out_never_yields_a_second_request, test_one_withdrawal_after_a_plan_change_at_the_wrong_moment_restores_the_loop, test_status_never_reports_two_requests_out_after_a_plan_change) | `scripts/_step_loop_action.py`, `scripts/_step_loop_record.py`, `scripts/_step_loop_cli.py` | PASS |
| REQ-05 | 4 -- `scripts/test_loop_review_round.py` (test_a_verdict_above_a_superseded_heading_is_the_files_verdict, test_a_line_that_is_not_a_superseded_heading_is_no_boundary, test_a_separator_alone_is_no_boundary, test_a_single_round_file_reads_by_its_last_verdict_as_before) | 2 -- `tests/acceptance/test_a_second_round_accept_reads_as_accepted.py` (test_a_second_round_accept_above_the_superseded_revise_reads_as_accepted, test_after_a_second_round_accept_the_loop_goes_on_to_the_next_step) | `scripts/_step_loop_review.py` | PASS |
| REQ-06 | 3 -- `scripts/test_loop_review_round.py` (test_a_round_two_review_prompt_names_the_boundary_heading, test_a_round_one_review_prompt_names_no_boundary, test_a_round_whose_own_verdict_is_revise_still_reads_revise) | 4 -- `tests/acceptance/test_a_second_round_accept_reads_as_accepted.py` (test_a_second_round_whose_own_verdict_is_revise_still_stops_for_a_human, test_a_single_round_written_as_the_prompt_asks_reads_by_its_last_verdict[accept-last], test_a_single_round_written_as_the_prompt_asks_reads_by_its_last_verdict[revise-last], test_a_review_whose_only_verdict_is_partial_reads_as_unfinished) | `scripts/_step_loop_render.py` | PASS |
| REQ-07 | 2 -- `scripts/test_loop_ownership.py` (test_a_bare_path_withholds_its_files_a_node_entry_none_and_the_outer_loop_always, test_the_commit_split_leaves_a_node_entrys_file_in_and_a_bare_paths_file_out) | 1 -- `tests/acceptance/test_a_node_entry_names_ownership_not_a_ban.py` (test_a_node_entry_of_a_later_step_does_not_withhold_the_file_from_its_owning_step) | `scripts/_step_loop_ownership.py`, `scripts/_step_loop_io.py` | PASS |
| REQ-08 | 1 -- `scripts/test_loop_ownership.py` (test_a_bare_path_withholds_its_files_a_node_entry_none_and_the_outer_loop_always) | 3 -- `tests/acceptance/test_a_node_entry_names_ownership_not_a_ban.py` (test_an_outer_loop_or_bare_read_only_file_is_still_withheld_and_warned_about[an-outer-loop-test], test_an_outer_loop_or_bare_read_only_file_is_still_withheld_and_warned_about[a-bare-read-only-path-the-step-does-not-declare], test_an_outer_loop_or_bare_read_only_file_is_still_withheld_and_warned_about[a-bare-read-only-path-the-step-also-declares]) | `scripts/_step_loop_ownership.py` | PASS |
| REQ-09 | 3 -- `scripts/test_loop_ownership_pockets.py` (test_the_same_node_id_is_pending_in_the_pocket_that_holds_it_and_not_in_the_root, test_a_node_nobody_owns_in_a_pocket_run_still_fails_named_as_the_repository_does, test_a_check_in_a_pocket_names_a_node_nobody_owns_as_the_repository_does) | 3 -- `tests/acceptance/test_a_red_node_a_later_step_owns_is_pending_in_every_pocket.py` (test_a_red_node_a_later_step_owns_reads_as_pending[root-unit-test], test_a_red_node_a_later_step_owns_reads_as_pending[outer-loop-test], test_a_red_node_a_later_step_owns_reads_as_pending[eval-pocket]) | `scripts/_step_loop_ownership.py`, `scripts/_step_loop_record_gate.py` | PASS |
| REQ-10 | 3 -- `scripts/test_loop_ownership.py` (test_an_entry_owns_the_nodes_it_is_a_prefix_of_at_a_boundary, test_a_node_a_later_step_owns_is_pending_for_the_step_before_it, test_the_gate_the_commit_and_the_prompt_read_one_entry_alike) | 4 -- `tests/acceptance/test_a_red_node_a_later_step_owns_is_pending_in_every_pocket.py` (test_a_red_node_no_step_owns_is_a_failure[root-unit-test], test_a_red_node_no_step_owns_is_a_failure[eval-pocket], test_a_red_node_only_the_gated_step_owns_is_a_failure, test_a_red_node_only_a_done_step_owns_is_a_failure) | `scripts/_step_loop_ownership.py` | PASS |
| REQ-11 | 2 -- `scripts/test_loop_prompt_roles.py` (test_the_closing_instructions_say_the_driver_runs_the_derived_test_scope, test_the_closing_instructions_say_the_agent_runs_its_check_in_the_foreground) | 4 -- `tests/acceptance/test_the_step_prompt_says_who_runs_what.py` (test_the_prompt_says_the_driver_runs_the_derived_scope[implement], test_the_prompt_says_the_driver_runs_the_derived_scope[revise], test_the_prompt_says_the_agent_runs_its_check_in_the_foreground[implement], test_the_prompt_says_the_agent_runs_its_check_in_the_foreground[revise]) | `scripts/_step_loop_render.py` | PASS |
| REQ-12 | 8 -- `scripts/test_follow_ups_line.py` (test_the_items_of_the_line_come_back_in_order_stripped, test_the_last_line_that_starts_with_the_prefix_is_the_one_read, test_the_record_is_created_with_its_heading_and_the_items_in_order, test_an_item_whose_open_line_is_already_there_is_skipped, test_writing_the_same_items_twice_equals_writing_them_once); `scripts/test_loop_follow_ups_record.py` (test_each_item_of_the_line_is_appended_whatever_the_marker_and_verdict, test_the_items_are_in_the_record_before_the_ledger_record_is_appended, test_a_replayed_record_reads_no_text_and_appends_nothing) | 5 -- `tests/acceptance/test_follow_ups_reach_the_record_through_the_driver.py` (test_each_item_of_the_line_is_appended_as_an_open_follow_up[complete-and-green], test_each_item_of_the_line_is_appended_as_an_open_follow_up[complete-and-red], test_each_item_of_the_line_is_appended_as_an_open_follow_up[blocked], test_items_already_in_the_record_stay_as_they_were, test_a_replayed_record_appends_nothing_more) | `scripts/_follow_ups.py`, `scripts/_step_loop_record.py` | PASS |
| REQ-13 | 4 -- `scripts/test_follow_ups_line.py` (test_no_items_leave_an_absent_record_absent, test_no_items_leave_a_present_record_byte_for_byte); `scripts/test_loop_follow_ups_record.py` (test_a_return_with_no_line_leaves_an_absent_record_absent, test_a_return_with_a_line_and_no_item_leaves_the_record_byte_for_byte) | 4 -- `tests/acceptance/test_follow_ups_reach_the_record_through_the_driver.py` (test_a_return_with_no_item_leaves_an_absent_record_absent[no-line], test_a_return_with_no_item_leaves_an_absent_record_absent[no-item], test_a_return_with_no_item_leaves_the_record_byte_for_byte[no-line], test_a_return_with_no_item_leaves_the_record_byte_for_byte[no-item]) | `scripts/_follow_ups.py` | PASS |
| REQ-14 | 2 -- `tests/acceptance/test_small_debt_is_fixed_not_filed.py`; `scripts/test__follow_ups.py` | none | `skills/software-planning/references/tech-debt-ledger.md`, `skills/step-loop/SKILL.md` | PASS (read by the verifier) |
| REQ-15 | 4 -- `scripts/test_loop_location_echo.py` (test_the_separate_spelling_is_echoed_as_the_option_and_its_value, test_the_equals_spelling_is_echoed_as_the_option_and_its_value, test_the_options_keep_the_order_and_the_values_the_caller_gave, test_main_prints_a_then_ending_with_the_options_the_call_was_given) | 9 -- `tests/acceptance/test_printed_commands_carry_the_callers_base.py` (test_then_ends_with_the_location_options_the_caller_gave[base-ref-alone], test_then_ends_with_the_location_options_the_caller_gave[base-ref-and-repo-root], test_then_ends_with_the_location_options_the_caller_gave[all-three], test_a_stops_resume_ends_with_the_location_options_the_caller_gave[base-ref-alone], test_a_stops_resume_ends_with_the_location_options_the_caller_gave[base-ref-and-repo-root], test_a_stops_resume_ends_with_the_location_options_the_caller_gave[all-three], test_the_handoffs_next_action_command_carries_the_callers_base, test_the_status_tables_last_line_names_next_with_the_callers_base[before-the-first-request], test_the_status_tables_last_line_names_next_with_the_callers_base[after-a-withdrawal]) | `scripts/_step_loop_cli.py`, `scripts/step_loop.py` | PASS |
| REQ-16 | 2 -- `scripts/test_loop_location_echo.py` (test_execute_called_directly_prints_the_bare_commands, test_main_prints_a_then_with_no_location_for_a_call_given_none) | 2 -- `tests/acceptance/test_printed_commands_carry_the_callers_base.py` (test_a_bare_calls_then_is_printed_as_before, test_a_bare_calls_resume_is_printed_as_before) | `scripts/step_loop.py` | PASS |
| REQ-17 | 4 -- `scripts/test_loop_location_echo.py` (test_a_handoff_differing_only_by_the_options_the_call_added_is_left_as_it_is, test_a_handoff_differing_only_by_the_options_the_call_left_out_is_left_as_it_is, test_a_handoff_whose_next_action_moved_is_rewritten_with_the_options_of_the_call, test_a_first_handoff_is_written_with_the_options_of_the_call) | 2 -- `tests/acceptance/test_printed_commands_carry_the_callers_base.py` (test_a_stops_resume_ends_with_the_location_options_the_caller_gave[base-ref-and-repo-root]); `tests/acceptance/test_step_loop_stops.py` (test_the_stop_names_the_command_that_resumes_the_loop) | `scripts/_step_loop_cli.py`, `scripts/_step_loop_files.py` | PASS |
| REQ-18 | 1 -- `tests/acceptance/test_step_loop_relay_skill.py` | none | `skills/step-loop/SKILL.md` | PASS (read by the verifier) |
| REQ-19 | 7 -- `scripts/test_loop_record_lock.py` (test_an_ended_agent_whose_record_holds_the_lock_is_in_flight_not_held, test_the_probe_creates_no_lock_file_for_a_request_never_recorded); `scripts/test_loop_recording.py` (test_a_held_record_reads_in_flight_and_a_finished_one_does_not, test_a_probe_with_no_lock_file_reads_no_record_and_creates_nothing, test_a_probe_that_cannot_open_the_lock_file_reads_no_record, test_a_probe_whose_lock_call_errors_reads_no_record, test_a_child_the_record_starts_does_not_keep_the_lock_after_the_record_ends) | 1 -- `tests/acceptance/test_a_record_in_flight_is_never_demanded_twice.py` (test_the_stop_guard_never_demands_a_record_that_is_running) | `scripts/_step_loop_recording.py`, `scripts/_step_loop_outstanding.py` | PASS |
| REQ-20 | 10 -- `scripts/test_loop_record_lock.py` (test_a_second_record_while_the_first_holds_the_lock_exits_four_and_writes_nothing, test_a_withdrawal_while_a_record_holds_the_lock_is_refused_too, test_a_record_holds_the_lock_while_it_reads_the_task_and_takes_the_return_back, test_a_record_of_an_unknown_request_is_refused_before_any_lock_is_taken, test_the_error_vocabulary_names_record_running_beside_gate_running); `scripts/test_loop_recording.py` (test_a_second_record_is_refused_naming_the_request_and_the_holder, test_a_second_record_waits_the_whole_wait_before_it_refuses, test_a_lock_released_while_the_record_waits_is_taken, test_a_lock_taken_on_a_file_its_holder_just_removed_is_taken_again_on_the_new_file, test_a_finished_record_leaves_no_lock_file) | 1 -- `tests/acceptance/test_a_record_in_flight_is_never_demanded_twice.py` (test_a_second_record_while_the_first_runs_writes_beside_nothing) | `scripts/_step_loop_recording.py`, `scripts/step_loop.py`, `scripts/_step_loop_cli.py` | PASS |
| REQ-21 | 1 -- `scripts/test_loop_record_lock.py` (test_an_ended_agent_whose_record_lock_is_free_is_held_as_before) | 2 -- `tests/acceptance/test_a_record_in_flight_is_never_demanded_twice.py` (test_an_ended_unrecorded_request_with_no_record_running_still_holds_the_stop_once); `tests/acceptance/test_stop_guard.py` | `scripts/_step_loop_outstanding.py` | PASS |
| REQ-22 | 7 -- `scripts/test_loop_check_collects.py` (test_a_collect_only_summary_is_read_off_any_duration_line, test_a_missing_plugin_refuses_naming_the_check_and_what_collection_printed, test_a_check_that_collects_is_not_refused, test_a_test_file_the_step_has_yet_to_write_is_not_refused, test_a_module_that_fails_to_import_is_a_red_check_not_a_refused_one, test_the_series_first_implement_request_is_refused_before_it_goes_out, test_a_request_that_is_not_the_series_first_is_not_asked_to_collect) | 3 -- `tests/acceptance/test_a_plan_defect_costs_no_attempt.py` (test_a_check_that_cannot_print_a_summary_is_refused_before_any_request, test_the_refusal_names_the_step_the_check_and_what_collection_printed, test_a_refused_check_spends_no_attempt_and_writes_no_ledger_record) | `scripts/_step_loop_gate.py`, `scripts/_step_loop_record_gate.py`, `scripts/step_loop.py` | PASS |
| REQ-23 | 4 -- `scripts/test_loop_check_collects.py` (test_a_check_with_a_shell_operator_word_is_not_probed, test_a_check_that_is_not_pytest_is_never_run_by_the_probe, test_a_run_that_exits_clean_is_never_a_refusal_whatever_it_printed, test_a_run_that_exits_without_a_summary_is_refused_with_its_exit_when_silent) | 1 -- `tests/acceptance/test_a_plan_defect_costs_no_attempt.py` (test_a_plan_whose_checks_collect_is_issued_gated_and_recorded_as_before) | `scripts/_step_loop_action.py`, `scripts/_step_loop_render.py`, `skills/step-loop/references/stop-recoveries.md` | PASS |
| REQ-24 | 6 -- `scripts/test_loop_unreadable_field.py` (test_an_unreadable_field_stops_under_its_own_cause_naming_step_and_field, test_an_unreadable_field_is_stopped_on_whatever_the_reconciler_says, test_the_state_of_an_unreadable_field_holds_the_field_and_the_fix); `scripts/test_loop_state_change_type.py` (test_an_unreadable_step_line_is_an_unreadable_field_naming_value_legal_values_and_line); `scripts/test_loop_bound_readers.py` (test_an_unreadable_iterations_field_is_an_unreadable_field_to_the_driver_state); `scripts/test_loop_one_state.py` (test_every_state_kind_has_a_case_and_every_case_gives_a_word_of_the_closed_set) | 4 -- `tests/acceptance/test_a_plan_defect_costs_no_attempt.py` (test_an_unreadable_plan_field_stops_under_a_cause_of_its_own_naming_step_and_field[iterations], test_an_unreadable_plan_field_stops_under_a_cause_of_its_own_naming_step_and_field[change-type], test_an_unreadable_plan_fields_handoff_says_to_fix_that_field_and_resume[iterations], test_an_unreadable_plan_fields_handoff_says_to_fix_that_field_and_resume[change-type]) | `scripts/_step_loop_state.py`, `scripts/_step_loop_action.py` | PASS |
| REQ-25 | 5 -- `scripts/test_loop_unreadable_field.py` (test_the_handoff_names_the_field_and_the_command_that_resumes, test_the_stderr_block_says_to_correct_the_line_the_evidence_names, test_a_human_verdict_whose_evidence_names_a_field_keeps_its_own_action, test_the_cause_is_one_of_the_human_stops); `scripts/test_loop_render_texts.py` (test_an_unreadable_plan_field_says_to_correct_the_plan_line_the_evidence_names) | 3 -- `tests/acceptance/test_step_loop_stops.py`; `tests/acceptance/test_step_loop_attempt_cap.py`; `tests/acceptance/test_step_loop_light_review.py` | `scripts/_step_loop_render.py` | PASS |
| REQ-26 | 3 -- `scripts/test_loop_request_lifecycle.py` (test_a_miscounted_line_is_named_with_its_request_and_its_count, test_a_line_that_disagrees_with_itself_refuses_the_withdrawal_naming_step_id_and_count); `scripts/test_loop_state_bound.py` (test_the_causes_are_the_closed_set_the_stop_texts_cover) | 2 -- `tests/acceptance/test_a_withdrawn_request_leaves_none_out.py` (test_next_names_an_attempts_line_whose_request_disagrees_with_its_count, test_record_names_an_attempts_line_whose_request_disagrees_with_its_count) | `scripts/_step_loop_action.py`, `scripts/_step_loop_record.py` | PASS |
| REQ-27 | 6 -- `scripts/test_loop_result_command_cap.py` (test_a_command_over_the_ceiling_is_cut_and_points_at_the_file, test_the_file_beside_the_run_logs_holds_the_whole_command_and_ends_its_line, test_a_command_that_fits_is_written_whole_and_leaves_no_file, test_the_same_command_always_renders_the_same_line, test_a_line_exactly_at_the_ceiling_is_not_cut_and_one_over_is, test_a_block_written_with_the_old_full_line_reads_back_as_before) | 2 -- `tests/acceptance/test_driver_result_blocks_fit_the_shape_ceiling.py` (test_the_drivers_green_block_passes_the_shape_checker, test_the_exact_check_command_is_found_from_the_block) | `scripts/_step_loop_record_gate.py` | PASS |
| REQ-28 | 2 -- `tests/acceptance/test_adherence_eval_tests_start_no_claude.py` (test_the_eval_suite_passes_without_ever_starting_claude); `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_adherence_eval_tripwire_passes_with_an_eval_override) | 2 -- `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_adherence_eval_tripwire_passes_with_an_eval_override[eval-short], test_the_adherence_eval_tripwire_passes_with_an_eval_override[eval-long]) | none | PASS (the verifier did not run the mutation of the nested suite; the repair is the nested `timeout=` alone and its oracle is untouched) |
| REQ-29 | 7 -- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` (test_the_orientation_names_the_outstanding_request_and_its_record_call, test_the_orientation_names_the_step_the_driver_acts_on_with_its_state_and_attempts, test_the_orientation_never_reports_the_step_records_stale_position, test_the_orientation_keeps_its_cap_its_pointers_and_its_withheld_words, test_a_stopped_loop_is_reported_as_stopped_with_its_cause, test_a_complete_loop_is_reported_as_complete); `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_compaction_orientation_scenarios_pass_with_an_eval_override) | 2 -- `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_compaction_orientation_scenarios_pass_with_an_eval_override[eval-short], test_the_compaction_orientation_scenarios_pass_with_an_eval_override[eval-long]) | none | PASS (the oracle was sharpened after the verifier's mutation, `6a09d67e`) |
| REQ-30 | 2 -- `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient); `tests/acceptance/test_abandoned_gate_run_is_stopped.py` (test_the_bound_in_force_is_the_one_recorded_when_the_run_started) | 4 -- `tests/acceptance/test_loop_tests_ignore_an_ambient_pocket_override.py` (test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient[eval-short], test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient[eval-long], test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient[root-short], test_the_abandoned_gate_run_scenario_passes_whatever_pocket_override_is_ambient[root-long]) | none | PASS |
| REQ-31 | 9 -- `hooks/test_notice_working_directory.py` (test_each_transition_leaves_its_record_and_announces_only_a_move_away_from_home, test_a_directory_change_word_anywhere_in_the_command_marks_the_call_moving, test_the_notice_is_one_line_of_context_for_the_firing_event_naming_both_directories, test_a_move_away_adds_exactly_one_line_whichever_payload_shows_it, test_a_payload_without_spaces_after_its_colons_reads_the_same, test_a_cd_from_an_entered_worktree_into_the_main_checkout_is_announced, test_a_record_of_another_shape_reads_unseen_and_is_rewritten, test_a_new_session_clears_records_quiet_for_a_week_and_keeps_the_rest, test_the_hook_is_executable) | 4 -- `tests/acceptance/test_the_agent_is_told_where_the_session_moved.py` (test_a_move_outside_the_project_names_the_new_directory_and_the_root_in_one_line[payload-shows-the-move], test_a_move_outside_the_project_names_the_new_directory_and_the_root_in_one_line[payload-shows-the-old-directory], test_a_move_into_a_subdirectory_names_the_new_directory[payload-shows-the-move], test_a_move_into_a_subdirectory_names_the_new_directory[payload-shows-the-old-directory]) | `hooks/notice_working_directory.sh`, `hooks/hooks.json` | PASS (not run under a live harness; the failure event's firing is pinned by a registry test, not observed) |
| REQ-32 | 10 -- `hooks/test_notice_working_directory.py` (test_a_call_that_changes_nothing_neither_writes_nor_adds, test_a_directory_change_outside_the_command_is_not_a_pending_move, test_the_same_physical_directory_by_another_name_is_not_a_move, test_a_session_in_its_entered_worktree_hears_nothing, test_a_subagent_payload_adds_nothing_and_leaves_the_record_untouched, test_an_unreadable_payload_adds_nothing_keeps_no_record_and_exits_cleanly, test_a_path_holding_a_double_quote_is_never_announced, test_an_unknown_event_argument_adds_nothing, test_an_unwritable_config_directory_adds_nothing_and_exits_cleanly, test_a_silent_call_starts_no_interpreter) | 5 -- `tests/acceptance/test_the_agent_is_told_where_the_session_moved.py` (test_a_call_that_comes_back_to_the_root_adds_nothing, test_a_call_that_moves_nothing_adds_nothing, test_an_unreadable_payload_adds_nothing_and_exits_cleanly[empty], test_an_unreadable_payload_adds_nothing_and_exits_cleanly[malformed], test_an_unreadable_payload_adds_nothing_and_exits_cleanly[not-an-object]) | `hooks/notice_working_directory.sh` | PASS (not run under a live harness; the failure event's firing is pinned by a registry test, not observed) |
| REQ-33 | 7 -- `hooks/test_commit_command.py` (test_a_read_only_form_reads_not_a_commit, test_each_rule_of_the_table_decides_its_form, test_the_reader_prints_one_word_as_the_gate_runs_it, test_the_subcommands_the_gate_decides_in_shell_are_built_ins_the_reader_knows, test_a_row_the_shell_may_decide_gets_the_readers_answer_through_the_gate); `hooks/test_commit_gate.py` (test_a_read_only_command_mentioning_a_commit_never_reaches_python, test_a_plain_git_log_mentioning_a_commit_is_decided_before_the_reader) | 4 -- `tests/acceptance/test_the_commit_gate_judges_only_real_commits.py` (test_a_read_only_command_mentioning_a_commit_starts_no_checker[description-says-commit], test_a_read_only_command_mentioning_a_commit_starts_no_checker[transcript-path-says-commit], test_a_read_only_command_mentioning_a_commit_starts_no_checker[log-grep-for-commit], test_a_read_only_command_mentioning_a_commit_starts_no_checker[show-described-as-commit]) | `hooks/commit_gate.sh`, `hooks/_commit_command.py` | PASS |
| REQ-34 | 9 -- `hooks/test_commit_command.py` (test_every_real_commit_form_reads_commit, test_each_rule_of_the_table_decides_its_form, test_a_commit_by_another_route_is_never_read_as_none, test_an_unreadable_payload_reads_uncertain, test_the_payload_is_decoded_once_so_an_escaped_word_is_read_as_written, test_every_real_commit_form_starts_the_checker_through_the_gate); `hooks/test_commit_gate.py` (test_a_reader_that_cannot_answer_leaves_the_hook_to_run, test_a_command_the_shell_cannot_read_plainly_reaches_the_reader, test_a_real_commit_starts_the_checker_with_no_grep_on_the_path) | 12 -- `tests/acceptance/test_the_commit_gate_judges_only_real_commits.py` (test_every_real_commit_form_starts_the_checkers[escaped-double-quotes], test_every_real_commit_form_starts_the_checkers[single-quotes], test_every_real_commit_form_starts_the_checkers[newline-in-message], test_every_real_commit_form_starts_the_checkers[add-and-commit], test_every_real_commit_form_starts_the_checkers[add-or-commit], test_every_real_commit_form_starts_the_checkers[add-semicolon-commit], test_every_real_commit_form_starts_the_checkers[add-newline-commit], test_every_real_commit_form_starts_the_checkers[directory-option], test_every_real_commit_form_starts_the_checkers[environment-assignment], test_every_real_commit_form_starts_the_checkers[amend], test_every_real_commit_form_starts_the_checkers[bash-c], test_every_real_commit_form_starts_the_checkers[sh-c]) | `hooks/_commit_command.py`, `hooks/commit_gate.sh` | PASS (the verifier's script-name and `rebase -x` classes closed, the latter by `02187d79`; a word split in shell syntax is a declared limit) |
| REQ-35 | 2 -- `tests/acceptance/test_light_review_trigger_texts.py` (test_the_site_states_the_three_annotations_of_the_rule, test_the_site_never_names_an_indirect_signal_as_a_trigger) | none | `agents/implementation-planner.md` | PASS (read by the verifier) |
| REQ-36 | 5 -- `tests/acceptance/test_exports_stay_byte_identical.py` (test_every_codex_and_cursor_export_file_is_byte_identical_to_todays); `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_the_cursor_export_is_the_bases_byte_for_byte); `tests/acceptance/test_other_channels_carry_the_kernel.py` (test_the_cursor_export_is_byte_identical_to_before_the_change); `tests/acceptance/test_routing_facts_keep_every_other_reach.py` (test_the_cursor_export_writes_the_bases_files_and_all_but_the_routing_rule_unchanged); `tests/acceptance/test_routing_move_keeps_every_other_reach.py` (test_every_cursor_file_but_the_routing_rules_is_the_bases_byte_for_byte) | none | `rules/swe/vcs/pr-conventions.md`, `rules/_manifest.yaml` | PASS (read by the verifier) |
| REQ-37 | 3 -- `tests/acceptance/test_merge_triggers_texts.py`; `tests/acceptance/test_command_family_is_retired.py`; `tests/acceptance/test_small_debt_is_fixed_not_filed.py` | none | `skills/release/SKILL.md`, `skills/merge-worktree/SKILL.md`, `skills/software-planning/references/decomposition-guide.md`, `skills/software-planning/references/tech-debt-ledger.md`, `skills/software-planning/references/agent-pipeline-details.md`, `skills/software-planning/references/coordination-details.md`, `skills/spec-driven-development/references/footprint-criteria.md`, `skills/step-loop/SKILL.md`, `skills/step-loop/references/stop-recoveries.md`, `skills/hook-crafting/SKILL.md`, `skills/testing-strategy/SKILL.md`, `agents/implementer.md`, `docs/lean-spawn-how-to.md`, `scripts/CLAUDE.md`, `README_DEV.md` | PASS (read by the verifier) |
| REQ-38 | 2 -- `tests/acceptance/test_loop_texts_point_at_the_driver.py`; `tests/acceptance/test_merge_triggers_texts.py` | none | `skills/software-planning/references/document-templates.md`, `skills/software-planning/references/intra-step-review.md`, `skills/step-loop/SKILL.md`, `README_DEV.md` | PASS (read by the verifier) |
| REQ-39 | 1 -- `scripts/test_check_state_ledgers.py` | none | `.ai-state/TECH_DEBT_LEDGER.md` | PASS (the 22 rows read resolved against commits of the pipeline in the working tree at archival; the closure commit, with the calibration row, follows the archive) |
| REQ-40 | none | 4 -- `tests/acceptance/test_records_written_before_the_repair_read_the_same.py` (test_records_the_earlier_driver_wrote_read_as_they_did[exhausted-with-handoff], test_records_the_earlier_driver_wrote_read_as_they_did[reviewed-then-outstanding], test_reading_the_earlier_records_rewrites_none_of_them[exhausted-with-handoff], test_reading_the_earlier_records_rewrites_none_of_them[reviewed-then-outstanding]) | none | PASS |
| REQ-41 | 3 -- `tests/acceptance/test_step_loop_relay_skill.py`; `tests/acceptance/test_small_debt_is_fixed_not_filed.py`; `tests/acceptance/test_loop_texts_point_at_the_driver.py` | none | `rules/swe/vcs/pr-conventions.md`, `agents/implementation-planner.md` | PASS (read by the verifier) |
| REQ-42 | 3 -- `tests/acceptance/test_loop_texts_point_at_the_driver.py`; `tests/acceptance/test_step_loop_relay_skill.py`; `tests/acceptance/test_step_loop_skill_answers_interim_notifications.py` | none | `skills/step-loop/SKILL.md`, `skills/step-loop/references/stop-recoveries.md` | PASS (read by the verifier) |
| REQ-43 | 2 -- `scripts/test_loop_ownership.py` (test_a_step_whose_files_name_the_file_of_its_node_entry_is_told_the_file_is_its_to_edit, test_a_step_is_told_nothing_when_it_has_no_node_entry_of_a_file_it_declares) | 2 -- `tests/acceptance/test_a_node_entry_names_ownership_not_a_ban.py` (test_a_step_told_of_a_node_of_its_own_file_is_told_the_file_is_its_to_edit, test_a_step_told_of_an_outer_loop_node_is_never_told_it_may_edit_that_file) | `scripts/_step_loop_ownership.py`, `scripts/_step_loop_render.py` | PASS |

## Key Decisions

Decisions made in the design, each a decision draft promoted at the merge:

- **The request lifecycle.** A withdrawal has an outcome of its own and issues nothing; a plan changed while a request is out stops and names the request; a record holds a lock on a file it removes as it lets go.
- **One ownership rule.** A bare path owns every node of its file and keeps the file out of the commit; an entry naming a node owns the node and withholds nothing; ids are compared in the repository's own form in every pocket.
- **The commit gate's reader.** Only the exact word for "not a commit" skips the checkers, so a crash or any doubt runs them. As built, the first test is two shell builtins and the shell settles one simple read-only git command before the reader.
- **The working-directory notice.** One shell hook, a record per session, a notice when a Bash call leaves the session away from its home. As built, registered for failed calls too.

Decisions made while building, each recorded where it governs:

- **The loop was run from a pinned copy of the driver** exported from the last driver commit and refreshed after each one, after showing that the new copy read the pipeline's own records as the old one did. The loop is measured from the last commit before its first step, not from the acceptance base.
- **Spec Questions SQ-01 to SQ-11** are recorded with their resolutions in the pipeline's acceptance document, now parked with the pipeline's directory. Two changed what was built: whether a stop's handoff is written again is judged without the location options when one side carries none (ruled twice: the first ruling broke a scenario and the implementer's counter-example corrected it); and the orientation scenario looks for the request's id outside the record call and as a whole word.
- **What counts as a check that cannot collect** is a run that exits without a summary. A path that does not exist yet and a module that fails to import both print one and are not refused. The plan's own line, that a `Check` that names a file its own step has not yet created cannot collect and stops, is not what was built or what the requirement asks: such a path prints a summary and is not refused.
- **Review remarks were fixed before verification, outside the loop**, each reproduced by a failing test first. Several were defects: a result line over its ceiling, pending tests merged across pockets, a lock release that could remove another call's file, a probe that would have stopped the first step of a fresh worktree.
- **The verifier's findings were fixed before the merge**, the hook's registration for failed calls among them, and a second pass checked the fixes.

Left open, each a ledger row: a check run through a project option gets its pocket's directory twice, held by a strict expected failure (`td-678`); a read-only pipeline that names both words still starts the commit checkers (`td-677`); readers that make their own driver call cannot echo a base they were never given (`td-675`); the review skill that three agents reported arriving as another skill of the same name, not verified (`td-676`); one signal-handling test that fails when the suite is started as a shell background job (`td-679`); and the worktree guard's refusals of compound commands that name git, of inline scripts that name git commands and of two bare argument words (`td-680`).
