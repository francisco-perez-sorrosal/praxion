# Spec: loop-gate-hardening (the session-stall fixes and the flip gate's evidence)

**Task slug**: `loop-gate-hardening`
**Feature**: A synchronous Stop guard holds the orchestrator's stop once while an ended step-loop agent's return is unrecorded and names the exact `record` call (td-464); the step-loop skill says a marked return is final under an "interim" notice; the post-compaction orientation reports the driver's own position during a step loop (td-466); the implementer's adherence sessions score the project-convention check (td-468); and the flip gate judges every cited run from its own results files over a schema-2 run index, refusing a passing run that did not score the role's convention check (td-473).
**Tier**: Standard, re-tiered to Full at verification (17 requirements over about 21 production files; 17 of 32 charged spawns, the 17th the architect's draft corrections). 15 of 24 step-loop iterations.
**Pipeline branch**: `worktree-loop-gate-hardening`
**Start date**: 2026-10-20
**End date**: 2026-10-20
**Archived**: 2026-10-20 (post-merge; fast-forwarded to main at `fc9c64d1`, finalized in `ed4c2d1c`)
**Status**: completed -- final verdict PASS WITH FINDINGS (0 FAIL, 9 WARN). The one must-fix rework row (decision drafts and the how-to aligned with what was built) landed before merge in `a76d3d67`; the other warnings are ledger rows td-478 to td-486.
**ADRs**: `dec-463` (architectural: the flip gate's evidence from results files; narrows `dec-461`), `dec-464` (architectural: the orientation reports the driver's position; narrows `dec-387`), `dec-465` (architectural: the step-loop Stop guard).
**Evidence base**: the commits from `587dfca5` (acceptance design) to `fc9c64d1`; the calibration row dated 2026-10-20; the root suite (14408 passed, 32 skipped) and eval suite (2707 passed) run as CI runs them at `4e8cec21`; the footprint log (FC-01 to FC-03 equal to baseline; FC-04 64675 against 65043; verify stage 0 fail, 0 warn).

## Feature Summary

A five-hour stall in the previous pipeline came from the orchestrator ending its turn to wait for a notification that never came, although its loop agent had already returned with a terminal marker; and after a compaction the orientation named a step thirty-two behind the driver's. This pipeline closed both, made the implementer measurable on the project convention before its paid trial, and moved the flip gate's evidence from the run index to the results files. Twelve steps were driven under the step-loop driver; five light reviews ran (steps 2 and 3 returned revise, and the follow-up step 3a was accepted on re-review; steps 9 and 10 accepted with residuals, closed in step 11a); two outer-loop driver defects were fixed through Spec Questions; and the full suites ran green as CI runs them.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py`. REQ ids are pipeline-local and appear in no code.

Complexity: medium (17 requirements over four ledger rows: a new Stop-time guard and the step-loop skill's wording, the post-compaction orientation, the adherence eval's implementer kit and results, and the flip gate's evidence boundary). Brownfield baselines: the archived step-loop-driver spec (the driver's `record`, `status` and request ids, unchanged here) and the archived lean-spawn-continuation spec, whose run-index and continued-run requirements these extend: a continued run is still one run, and the gate still resolves cited runs through the index's digests, but no longer takes their standing from it.

### Observable Surface

- `Stop` — the Claude Code hook event fired when the main session would end its turn; a synchronous hook can hold the stop so that the turn continues with a message
- `stop_hook_active` — the `Stop` input flag, true when the session is already continuing because a stop hook held it
- `SessionStart`, `compact` — the Claude Code hook event and its source value after a compaction
- `hooks/hooks.json` — the plugin's hook registrations, shipped to every managed project
- `hooks/inject_compaction_orientation.py` — the existing post-compaction orientation hook (block capped at 1,024 bytes, exit 0 always)
- `skills/step-loop/SKILL.md` — the step-loop procedure the orchestrator relays by
- `description:` — the skill frontmatter key listed at every session start
- `step_loop.py` — the step-loop driver (`python3 scripts/step_loop.py` in the Praxion checkout)
- `next`, `record`, `status` — the driver's verbs: issue the next request, take back an ended agent's return, report the position read-only
- `then` — the field of a spawn envelope that carries the driver's record command for the request
- `agent-running` — the refusal `record` gives for an agent whose transcript does not show the end; the request stays pending
- `.ai-work/` — the ephemeral pipeline directory, one task directory per slug
- `WIP.md`, `ITERATION_LEDGER.jsonl`, `IMPLEMENTATION_PLAN.md`, `HANDOFF.md` — a task's step record, iteration ledger, plan and handoff
- `Attempts:` — the step record line on which the driver names each request it issued
- `CLAUDE.md` — a project instruction file (an eval fixture's included)
- `Filed under the project house rules.` — the line the pilot roles' project convention asks every document to carry
- `praxion-evals-adherence`, `--reindex` — the adherence eval entry and its option that rebuilds the run index from the results files
- `.ai-state/eval_ledger/adherence/` — the directory of adherence results files, one per run part
- `.ai-state/eval_ledger/adherence/index.json` — the run index beside them
- `.ai-state/kernel_adoption.yaml` — the per-role adoption ledger
- `passing_run`, `passes_flip_rule` — fields of a switched adoption record: the run it rests on, and each cited run's claimed pass flag
- `python3 scripts/check_kernel_manifest.py` — the kernel and adoption-ledger commit gate (the flip gate)
- `docs/lean-spawn-how-to.md` — the operator how-to for lean spawns and flips
- `.ai-state/decisions/` — the decision records
- `codex/config/export-codex-agents.py`, `cursor/config/export-cursor-rules.py` — the Codex wrappers and the Cursor export
- `python3 scripts/generate_kernels.py --check`, `python3 scripts/check_agent_shared_blocks.py`, `python3 scripts/sync_canonical_blocks.py --check` — the kernel freshness, universal-block and shipped-block checks
- `python3 scripts/measure_token_budget.py --json` — the always-loaded and listing token instrument
- `python3 scripts/check_agent_prompt_size.py --json` — the definition and skill line-count instrument
- `python3 scripts/measure_startup_payload.py main --strict-mcp-config --plugin-dir <checkout> --json` — the main session's real-token startup probe, strict MCP profile

### REQ-01: The guard holds a stop on an ended, unrecorded request

**When** the main session would end its turn (the `Stop` event)
**and** a task under `.ai-work/` has a request the driver issued (its `WIP.md` names it on an `Attempts:` line) that its `ITERATION_LEDGER.jsonl` does not record
**and** an agent this session started on that request (its first message names the request) has a transcript showing the agent has ended, by the same end evidence `record` judges by: a final text with or without a terminal marker, its turn cap reached, or a stop row for it in the observation log
**the system** holds that stop once: the turn continues with one message of at most 600 bytes that names the request, the agent and how it ended (its terminal marker, or that it carries none), says the return is not recorded, and gives the driver's exact `record` command for it with the slug, the request, the agent id and the marker filled in; when more than one request qualifies, the message names the first in a fixed order (the oldest issued first, ties broken by task slug), so a later stop names whichever request qualifies first at that moment: the same one until it is recorded, and the next one after
**so that** an ended agent's return is taken back at once instead of the session idling for a notification that will not come.

### REQ-02: The guard never holds a stop while the agent may still be running

**When** a request the driver issued is unrecorded
**and** the transcript of the agent this session started on it does not show the end by that evidence, or no transcript of this session names the request (the Agent call was never made, or an earlier session made it)
**the system** lets the stop through; and on any transcript, whenever the guard would hold a stop, `record` on the same transcript would accept the agent as ended, never refuse it as `agent-running`
**so that** the orchestrator's ordinary wait for a running background agent is never interrupted, and a request left by an earlier session stays with the restart path the skill already names.

### REQ-03: The guard never holds twice in a row

**When** the `Stop` input carries `stop_hook_active` as true
**the system** lets the stop through without reading anything else
**so that** one stop is never held twice and the guard can never loop the session.

### REQ-04: The guard fails open and only reads

**When** any input the guard needs is absent, unreadable or malformed (the hook input, a task's `WIP.md` or `ITERATION_LEDGER.jsonl`, a transcript, a marker it cannot read), or the guard raises, fails or runs past its time bound, or the guard is not registered at all; a transcript holding any line that does not parse counts as malformed, even when `record` would accept it as ended, because a half-written last line most often means the agent is still writing
**the system** lets the stop proceed exactly as it does today and prints nothing to the session; and in every case, holding or not, the guard writes no file, starts no agent and changes no pipeline document
**so that** a broken or missing guard costs the session nothing and a working one only reads.

### REQ-05: The guard costs nothing without a step loop

**When** the working tree has no `.ai-work/`, or no task under it has a driver-issued request that its ledger does not record (a managed project with no step loop is the common case)
**the system** lets the stop through after reading at most each task's `WIP.md` and `ITERATION_LEDGER.jsonl`, reading no transcript, starting no process and printing nothing
**so that** a hook shipped to every managed project costs nothing outside an active step loop.

### REQ-06: The skill says a terminal marker is final under an interim note

**When** an orchestrator relays a step loop by `skills/step-loop/SKILL.md`
**the system** states there, at the rule on when to call `record`: that an agent's return carrying a terminal marker, together with the progress the step record shows, is final even when the harness labels the completion notification as possibly interim (the agent left background work running); that the orchestrator then runs the `then` command at once instead of ending its turn to wait for another notification; that a return with no marker under such a note is answered the same way, with the marker none; and that running `record` is always safe, because it refuses an agent that has not ended (`agent-running`) and leaves the request pending, that refusal being the only signal to wait; the skill's `description:` stays byte for byte as it is
**so that** the rule reaches every orchestrator through the artifact it relays from, never through anyone's memory.

### REQ-07: The orientation reports the driver's position during a step loop

**When** a session is re-oriented after a compaction (`SessionStart` with source `compact`)
**and** the newest task (the one whose `WIP.md` was written last) is under the driver: its `WIP.md` names a driver-issued request, or it has an `ITERATION_LEDGER.jsonl`
**the system** reports in the orientation the driver's own position, read from the driver's read-only `status`: the step the driver's next action concerns and that step's state in the driver's words, with its attempts against its cap; the iterations used of the budget; whether the loop is complete or stopped, and a stop's cause; and, when a request is outstanding, its id and the driver's record command for it, with the agent id and the marker left as the driver's placeholders; it reports neither the current-step section, the first open progress item nor the recorded next action of `WIP.md` as the position; the block keeps its pointer lines (a handoff first), its 1,024-byte cap and its exit-0 contract, and carries none of the words it already withholds (spawn, commit, proceed to verification)
**so that** a resumed session is pointed at the step the driver will act on, and at the command that takes back an outstanding agent.

### REQ-08: An unreadable driver position never brings back the stale one

**When** the newest task is under the driver but its position cannot be read in time (the driver is absent, fails, runs past its time bound, or prints output that cannot be parsed)
**the system** states in the orientation that the driver's position could not be read, names the read-only `status` command for the task, and still reports no current-step section of `WIP.md` as the position
**so that** a failure to read the driver never reintroduces the stale position this change removes.

### REQ-09: Outside a step loop the orientation is unchanged

**When** there is no task with a step record, or the newest task is not under the driver
**the system** emits the orientation byte for byte as it does today and reads no driver output
**so that** pipelines outside a step loop see no change.

### REQ-10: The implementer's sessions score the project-convention check

**When** the adherence eval plans and scores the implementer's tasks
**the system** states a project convention only in each implementer fixture's instruction file (`CLAUDE.md`) — the pilot roles' convention, or an implementer-shaped wording of it whose observance the same line `Filed under the project house rules.` shows in a file the session writes — and scores every implementer session on the convention check exactly as it scores the five pilot roles' sessions: passed when a file the session wrote holds that line, failed when none does, not applicable when the task stopped the role early
**so that** a lean implementer's flip run shows whether its project's own instructions still reach it.

### REQ-11: The implementer's tasks are otherwise unchanged

**When** the implementer gains the convention
**the system** keeps the implementer's task ids, prompts, templates, fixture code, early-stop variants and every other check as they are, and adds no task
**so that** the implementer's other checks measure what they measured before.

### REQ-12: A finalized run records what it scored, and the index carries it

**When** an adherence run finalizes or is closed
**the system** records in the results file it writes, for each role the run measured, the standing of the run's whole lineage (for a run of one part, the run itself): its complete pairs, its flip label, and the checks it scored, namely those its verdict gives a per-check verdict and does not list as not covered; the run index, whether written at finalize, at close or by `--reindex`, carries that list of scored checks beside the complete pairs and flip label of every entry; results files written before this change stay byte for byte as they are
**so that** which checks a passing run rests on is evidence that a reader without eval code can see.

### REQ-13: The gate refuses a passing run that did not score the convention check

**When** a commit holds a switched record in `.ai-state/kernel_adoption.yaml`
**and** the run it names as its `passing_run` did not score that role's convention check: the check is absent from the run's scored checks, or its results record no scored checks for the role (for a results file of one part written before this change, which holds no list of scored checks, its scored checks are the checks its verdict for the role gives a per-check verdict and does not list as not covered, and it records no scored checks for the role when that verdict gives no per-check verdict)
**the system** (`python3 scripts/check_kernel_manifest.py`) refuses the commit with a finding naming the role and the run
**so that** no role switches to its lean kernel on a run that never checked whether its project's own instructions still reach it.

### REQ-14: The gate counts complete pairs from the results files

**When** the gate judges a run that a switched record cites
**the system** finds the run's lineage from the results files' own continuation links, counts the role's complete pairs over the sessions that lineage's files record (a task of the role is one complete pair when the latest session the lineage records for it in each of the two arms was measured), and refuses, naming the role, the run and both figures, when the index's lineage or count for the run, the record's count, or the count a results file records for the whole lineage differs from what it derived; the index's recorded standing is never the source of what it judges, only of which file to read and the digest to check it by
**so that** a hand-edited index whose digests are intact cannot raise a run's pairs or regroup its lineage.

### REQ-15: The gate takes flip standing from what the results files record

**When** the gate judges a run that a switched record cites
**the system** takes the run's flip standing from its results files: not clear when the lineage's last part records a closed ending, otherwise the standing that last part records for the whole lineage (for a run of one part written before this change, the role's verdict the file records: its flip label, or underpowered when it records itself underpowered); it refuses a cited run for which no results file records that standing, and refuses, naming the role and the run, an index whose flip label or a record whose `passes_flip_rule` disagrees with it; a `passing_run` must stand clear on at least 20 complete pairs it counted itself
**so that** a forged flip label in the index or the adoption record is refused, without the gate recomputing the eval's statistics.

### REQ-16: The gate's remaining trust is stated, not implied

**When** the change lands
**the system** states, in a decision record under `.ai-state/decisions/` related to dec-461 by the relation protocol that fits, and in `docs/lean-spawn-how-to.md`, what the gate derives itself (a run's lineage, its complete pairs, a closed ending), what it cross-checks against the results files' recorded fields (flip standing, scored checks, the index's and the record's figures), and what it trusts without checking: the per-check verdicts, allowances, intervals and flip label the eval computed, which checks a verdict covers, and a results file rewritten together with its digest in the index; naming the two human ratifications every switched record carries as the backstop for that trust
**so that** the gate's limit is a stated requirement anyone can check its behaviour against, never an unspoken gap.

### REQ-17: The evidence already ratified still passes

**When** the gate runs over the adoption ledger and the results directory as they stand at the base commit, with the index rebuilt by `--reindex`
**the system** reports no new finding, with the scored checks of each results file written before this change read as REQ-13 states: the researcher's switched record and every held record pass, and for every results file in `.ai-state/eval_ledger/adherence/` the lineage, complete pairs and flip standing the gate derives equal the ones the eval derives for it
**so that** the stricter gate refuses only what it should, and evidence already ratified stays valid.

## Acceptance Criteria

- [x] When the orchestrator would end its turn while a step-loop request has been issued, the transcript of the agent started on it has ended, and no record holds it, the stop is held once with one message naming the exact `record` command to run (REQ-01).
- [x] The guard never holds a stop for an agent whose transcript does not show the end, never holds twice in a row, lets the stop through on anything it cannot read, writes nothing, and costs nothing in a project with no step loop (REQ-02 to REQ-05).
- [x] `skills/step-loop/SKILL.md` says a terminal marker plus the step record's progress is final even under an "interim" notification, and that `record` is always safe to run because it refuses a running agent; its `description:` is unchanged byte for byte (REQ-06).
- [x] After a compaction during an active step loop the orientation names the driver's position and, when one is outstanding, the in-flight request with its record command, and never the stale current-step section; outside a step loop the orientation is unchanged byte for byte (REQ-07 to REQ-09).
- [x] The implementer's sessions score the project-convention check like the five pilot roles' sessions, with its tasks otherwise unchanged (REQ-10, REQ-11).
- [x] Every finalized run records, per role, which checks it scored, and the run index carries that list (REQ-12).
- [x] The flip gate refuses a switched record whose passing run did not score the role's convention check, naming the role and the run (REQ-13).
- [x] The flip gate derives each cited run's lineage, complete pairs and flip standing from the results files, so a hand-edited index whose digests are intact is refused; what it still trusts is stated in a decision record and in the how-to; the evidence already in the results directory still passes (REQ-14 to REQ-17).
- [x] Each new refusal and the new hold has a canary: a known-bad input it is proven to flag, beside a known-good input it lets through.
- [x] Health: no rule, kernel, skill or definition text loses semantics, and the footprint criteria below hold.
- [x] Health: `python3 scripts/generate_kernels.py --check`, `python3 scripts/check_kernel_manifest.py`, `python3 scripts/check_agent_shared_blocks.py` and `python3 scripts/sync_canonical_blocks.py --check` pass.
- [x] Health: the Codex wrappers (`codex/config/export-codex-agents.py`) and the Cursor export (`cursor/config/export-cursor-rules.py`) show no diff beyond the intended, and any new hook has been checked against the Codex hooks bridge.
- [x] Health: the root suite and the eval pocket are green on their CI commands, the eval pocket near its 247 s; ruff and pyright are clean on touched files; the hook-registration gates pass; a new hook passes the hook-crafting skill's validator.
- [x] Health: each decision record is categorised by the architectural test, with a Disconfirmation section where it is architectural.
- [x] No paid run, push or release happens in the pipeline.

### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | always-loaded-tokens | governed always-loaded total, in tokens, on the current ruler | at or below | 24,800 tokens | reference: the brief's health guard, 24,800 on the current ruler | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | listing-tokens | skill and agent description listing total, in tokens | at or below | the baseline reading (no description changes) | baseline: listing total at the pipeline base | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | prompt-size | agent definition and skill line counts against their ceilings | at or below | no file past its fail ceiling and none newly past its warn ceiling | baseline: findings at the pipeline base | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-04 | spawn-startup-tokens | first-request tokens of the main session, strict MCP profile | at or below | the baseline reading, within the probe's 2 percent tolerance | baseline: the main session at the pipeline base | `python3 scripts/measure_startup_payload.py main --strict-mcp-config --plugin-dir <checkout> --json` |

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| hook-latency | no instrument exists for it (the registry's command is none); the cost the brief asks to hold is stated as behaviour instead: with no step loop the guard reads no transcript and starts no process (REQ-05), and the orientation reads no driver output outside a step loop (REQ-09), both checked by the acceptance tests |

## Traceability Matrix

Rendered from `traceability.yml` at archival (reconciled at Step 18). `Status` is the final verifier's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 20 -- `scripts/test_loop_outstanding.py` (test_a_final_text_with_a_marker_holds_the_request_with_that_marker, test_a_final_text_without_a_marker_holds_the_request_as_none, test_an_agent_at_its_turn_cap_holds_the_request, test_an_agent_stop_row_holds_a_request_whose_agent_was_last_calling_a_tool, test_a_transcript_under_a_workflow_run_holds_the_request_too, test_two_qualifying_requests_come_back_oldest_issued_first, test_requests_issued_together_break_the_tie_by_task_slug, test_the_held_command_is_the_drivers_own_record_command, test_a_recorded_request_is_not_outstanding, test_two_tasks_issuing_one_request_id_hold_only_the_task_whose_agent_ended); `hooks/test_guard_step_loop_stop.py` (test_message_is_three_sentences_naming_the_fact_the_call_and_the_rule, test_message_stays_within_the_cap_for_long_slugs_and_ids, test_message_says_a_marker_less_agent_carries_none, test_message_names_the_marker_an_agent_ended_with, test_a_held_stop_prints_one_block_decision, test_driver_forms_equal_the_ones_the_driver_prints, test_the_guard_is_registered_once_under_stop_as_a_synchronous_command_with_a_timeout, test_the_guard_is_registered_after_every_other_synchronous_stop_entry, test_an_ended_agent_of_the_loop_holds_the_stop_with_its_own_task_and_agent, test_a_stale_task_sharing_a_request_id_is_never_held_with_the_current_agent) | 5 -- `tests/acceptance/test_stop_guard.py` (test_an_ended_unrecorded_request_holds_the_stop_with_the_exact_record_call, test_the_held_message_is_short_and_says_the_return_is_not_recorded, test_of_two_qualifying_requests_the_oldest_is_named_first_and_the_other_once_it_is_recorded, test_a_request_still_unrecorded_is_named_again_on_the_next_stop, test_a_held_stop_writes_nothing) | `hooks/guard_step_loop_stop.py`, `hooks/hooks.json`, `scripts/_step_loop_outstanding.py` | met |
| REQ-02 | 12 -- `scripts/test_loop_outstanding.py` (test_a_running_agent_does_not_hold_the_request, test_a_request_no_transcript_of_the_session_names_is_not_held, test_an_agent_that_wrote_no_transcript_does_not_hold_the_request, test_every_held_agent_is_one_record_reads_as_ended, test_a_held_agent_stopped_by_the_log_is_one_record_reads_as_ended, test_a_running_agent_is_one_record_would_refuse_as_running, test_the_agent_type_of_a_request_is_the_one_the_driver_spawns, test_a_request_with_one_agent_ended_and_one_running_is_not_held, test_a_transcript_that_names_the_request_but_not_the_task_is_not_tied_to_it, test_the_observation_log_is_read_at_the_root_that_holds_the_work_root); `hooks/test_guard_step_loop_stop.py` (test_the_hook_started_as_the_harness_starts_it_prints_nothing_when_nothing_is_held, test_a_nested_checkout_does_not_reach_the_outer_checkouts_loop) | 4 -- `tests/acceptance/test_stop_guard.py` (test_whenever_the_guard_holds_record_accepts_the_agent_as_ended, test_a_running_agent_never_holds_the_stop_and_record_refuses_it, test_a_request_whose_agent_call_was_never_made_lets_the_stop_through, test_a_request_an_earlier_session_started_lets_the_stop_through) | `hooks/guard_step_loop_stop.py`, `scripts/_step_loop_outstanding.py` | met |
| REQ-03 | 1 -- `hooks/test_guard_step_loop_stop.py` (test_a_stop_already_held_once_reads_nothing) | 1 -- `tests/acceptance/test_stop_guard.py` (test_a_stop_already_held_once_goes_through_without_reading_anything) | `hooks/guard_step_loop_stop.py` | met |
| REQ-04 | 15 -- `scripts/test_loop_outstanding.py` (test_a_transcript_with_one_unparseable_line_is_not_held_even_where_record_accepts_it, test_an_assistant_record_without_a_request_id_is_not_held, test_a_task_whose_ledger_has_a_broken_line_yields_no_request, test_a_task_whose_wip_cannot_be_read_yields_no_request, test_an_absent_work_root_yields_nothing, test_a_file_whose_name_is_not_an_agent_id_does_not_hold_the_request, test_a_task_directory_whose_name_is_not_a_slug_yields_no_request, test_a_transcript_last_modified_before_the_request_was_issued_is_not_read, test_a_request_whose_prompt_file_is_gone_keeps_every_transcript); `hooks/test_guard_step_loop_stop.py` (test_a_failing_probe_prints_nothing_and_does_not_raise, test_input_that_is_not_a_json_object_lets_the_stop_through, test_a_stop_that_does_not_locate_its_session_has_no_agent_transcripts_to_read, test_an_unreadable_step_record_marks_no_loop, test_a_session_id_that_is_not_a_plain_segment_lets_the_stop_through, test_no_checkout_above_the_working_directory_lets_the_stop_through) | 5 -- `tests/acceptance/test_stop_guard.py` (test_an_input_the_guard_cannot_read_lets_the_stop_through_silently, test_an_ended_transcript_holding_an_unparseable_line_lets_the_stop_through, test_an_unreadable_agent_transcript_lets_the_stop_through_silently, test_a_stop_let_through_writes_nothing, test_the_guard_is_registered_to_run_synchronously_within_a_time_bound) | `hooks/guard_step_loop_stop.py`, `scripts/_step_loop_outstanding.py` | met |
| REQ-05 | 6 -- `hooks/test_guard_step_loop_stop.py` (test_no_pipeline_directory_lets_the_stop_through, test_a_step_record_naming_a_request_marks_a_loop_in_play, test_a_step_record_without_an_issued_request_marks_no_loop, test_a_request_the_ledger_records_marks_no_loop_in_play, test_a_request_absent_from_the_ledger_marks_a_loop_in_play, test_a_loop_whose_requests_are_all_recorded_imports_no_probe) | 3 -- `tests/acceptance/test_stop_guard.py` (test_a_checkout_with_no_pipeline_directory_reads_nothing_and_starts_nothing, test_a_pipeline_outside_a_step_loop_reads_only_its_step_record, test_a_loop_whose_every_request_is_recorded_reads_no_transcript) | `hooks/guard_step_loop_stop.py` | met |
| REQ-06 | -- | 2 -- `tests/acceptance/test_step_loop_skill_answers_interim_notifications.py` (test_one_section_states_the_interim_rule_beside_the_record_call, test_the_skill_description_is_unchanged_byte_for_byte) | `skills/step-loop/SKILL.md` | met |
| REQ-07 | 17 -- `scripts/test_loop_cli_status.py` (test_a_pending_request_selects_its_step_and_carries_the_record_call, test_the_then_equals_the_spawn_envelopes_for_the_same_request, test_a_next_step_with_nothing_pending_is_selected_and_has_no_record_call, test_a_stopped_loop_selects_the_stops_step, test_a_complete_loop_selects_nothing_and_has_no_record_call, test_the_new_keys_leave_the_existing_ones_in_place, test_the_status_table_is_unchanged_for_a_pending_request); `hooks/test_orientation_loop_mode.py` (test_an_outstanding_request_is_reported_with_its_step_attempts_iterations_and_record_command, test_the_stale_step_record_lines_are_never_reported_in_loop_mode, test_a_next_action_with_nothing_outstanding_is_one_line, test_a_stop_is_reported_as_stopped_with_its_cause_whatever_the_exit_code, test_a_complete_loop_is_reported_as_complete, test_a_digest_line_that_would_direct_falls_back_to_its_location_form, test_the_block_keeps_its_cap_and_its_handoff_first_pointer, test_the_driver_is_asked_for_the_tasks_status_as_json_against_the_worktree_root, test_the_attempt_cap_mirrors_the_drivers, test_the_orientation_hook_imports_under_the_system_python_3_9) | 6 -- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` (test_the_orientation_names_the_outstanding_request_and_its_record_call, test_the_orientation_names_the_step_the_driver_acts_on_with_its_state_and_attempts, test_the_orientation_never_reports_the_step_records_stale_position, test_a_stopped_loop_is_reported_as_stopped_with_its_cause, test_a_complete_loop_is_reported_as_complete, test_the_orientation_keeps_its_cap_its_pointers_and_its_withheld_words) | `hooks/inject_compaction_orientation.py`, `scripts/_step_loop_cli.py` | met |
| REQ-08 | 1 -- `hooks/test_orientation_loop_mode.py` (test_an_unreadable_position_names_the_status_command_and_never_the_stale_lines) | 1 -- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` (test_an_unreadable_driver_position_names_the_status_command_never_the_stale_one) | `hooks/inject_compaction_orientation.py` | met |
| REQ-09 | 1 -- `hooks/test_orientation_loop_mode.py` (test_a_task_is_under_the_driver_by_a_request_line_or_an_iteration_ledger) | 2 -- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` (test_outside_a_step_loop_the_orientation_is_unchanged_byte_for_byte, test_outside_a_step_loop_the_orientation_starts_no_driver) | `hooks/inject_compaction_orientation.py` | met |
| REQ-10 | 3 -- `eval/tests/test_adherence_catalog.py` (test_each_role_carries_one_check_per_clause_of_its_row, test_a_role_carries_the_convention_check_exactly_when_it_is_a_pilot_role); `eval/tests/test_adherence_tasks.py` (test_every_task_of_a_pilot_role_names_a_convention_and_the_check_that_reads_it) | 5 -- `tests/acceptance/test_implementer_scores_the_project_convention.py` (test_every_implementer_task_states_a_project_convention_with_its_check, test_the_convention_is_stated_only_in_each_fixtures_instruction_file, test_the_conventions_observance_is_the_house_rules_line, test_the_convention_check_is_in_the_implementers_catalog, test_an_implementer_session_is_scored_on_the_convention_like_a_pilot_role) | `eval/src/praxion_evals/adherence/catalog.py`, `eval/src/praxion_evals/adherence/model.py` | met |
| REQ-11 | 1 -- `eval/tests/test_adherence_catalog.py` (test_each_role_carries_one_check_per_clause_of_its_row) | 3 -- `tests/acceptance/test_implementer_scores_the_project_convention.py` (test_the_implementers_task_list_is_unchanged_and_gains_no_task, test_each_implementer_task_keeps_its_prompt_template_variant_and_fixture, test_the_implementers_other_checks_are_unchanged) | `eval/src/praxion_evals/adherence/catalog.py`, `eval/src/praxion_evals/adherence/model.py` | met |
| REQ-12 | 25 -- `eval/tests/test_adherence_standing.py` (test_a_recorded_standing_round_trips_through_the_results_file, test_a_file_without_a_standing_loads_as_none_and_reserializes_without_the_key, test_a_standing_that_breaks_an_invariant_is_refused, test_a_lineage_that_ended_closed_stands_not_clear_or_is_refused, test_a_file_whose_recorded_standing_is_malformed_is_refused, test_a_run_of_one_part_stands_on_its_own_pairs_flip_and_scored_checks, test_a_continued_run_records_the_standing_of_its_whole_lineage, test_a_part_that_ends_a_lineage_leaves_the_parts_after_it_out, test_a_lineage_closed_on_request_reads_not_clear_however_its_pairs_read, test_a_role_whose_verdict_gives_no_per_check_verdict_scored_no_check, test_an_underpowered_role_scored_no_check, test_a_finalized_run_records_the_standing_its_verdict_gives, test_a_finalize_rewrites_no_results_file_already_written, test_closing_a_stopped_run_records_not_clear_in_its_own_file_and_no_other); `eval/tests/test_adherence_run_index.py` (test_each_role_carries_its_complete_pairs_and_flip_label, test_a_role_short_of_its_declared_pairs_is_underpowered_with_the_pairs_it_has, test_a_check_the_verdict_does_not_cover_is_not_listed_as_scored, test_every_part_of_a_continued_run_carries_the_pairs_and_label_of_the_whole_lineage, test_a_closed_run_is_not_clear_however_its_pairs_read, test_an_empty_directory_has_an_index_of_nothing, test_the_recorded_runs_are_indexed_with_the_pairs_and_labels_the_report_shows); `scripts/test_kernel_run_index.py` (test_an_index_of_any_other_shape_is_an_input_error_naming_it, test_a_schema_one_index_is_unreadable_and_names_reindex, test_each_role_carries_the_checks_its_verdict_scored, test_a_role_that_scored_no_check_carries_none) | 4 -- `tests/acceptance/test_ratified_evidence_and_the_run_index.py` (test_reindexing_keeps_every_earlier_results_file_byte_for_byte, test_the_index_lists_the_checks_each_earlier_run_scored_per_role); `tests/e2e/test_finalized_run_records_what_it_scored.py` (test_a_finalized_run_records_and_indexes_the_checks_it_scored, test_a_closed_run_records_its_lineage_standing_and_the_index_carries_it) | `eval/src/praxion_evals/adherence/results.py`, `eval/src/praxion_evals/adherence/run_index.py`, `scripts/kernel_run_index.py` | met |
| REQ-13 | 8 -- `scripts/test_kernel_run_evidence.py` (test_the_convention_check_name_fills_the_role_into_the_template, test_legacy_scored_checks_leave_out_the_checks_the_verdict_does_not_cover); `scripts/test_kernel_run_evidence_parity.py` (test_the_convention_check_template_equals_the_one_the_eval_names_checks_by); `scripts/test_kernel_ledger_checks_scored.py` (test_a_passing_run_that_scored_the_convention_check_passes, test_a_passing_run_that_left_the_convention_check_uncovered_is_refused, test_a_passing_run_whose_verdict_records_no_scored_checks_is_refused, test_an_earlier_cited_run_need_not_have_scored_the_convention_check, test_a_run_before_the_standing_was_recorded_is_judged_from_its_verdict) | 3 -- `tests/acceptance/test_flip_gate_takes_standing_from_results.py` (test_a_passing_run_that_left_the_convention_check_uncovered_is_refused, test_a_passing_run_whose_verdict_records_no_scored_checks_is_refused, test_a_passing_run_that_scored_the_convention_check_passes) | `scripts/kernel_ledger_checks.py`, `scripts/kernel_run_evidence.py` | met |
| REQ-14 | 21 -- `scripts/test_kernel_run_evidence.py` (test_latest_session_per_arm_wins_across_the_parts_of_a_lineage, test_task_whose_latest_lean_session_errored_is_not_a_complete_pair, test_task_whose_lean_error_came_before_its_measured_session_stays_complete, test_a_fork_in_the_continues_links_is_refused, test_a_gap_in_the_continues_links_is_refused); `scripts/test_kernel_run_evidence_parity.py` (test_the_derived_lineage_and_pairs_equal_the_index_entry); `scripts/test_kernel_ledger_checks_evidence.py` (test_a_record_citing_more_pairs_than_the_sessions_give_is_refused_naming_both, test_a_task_whose_latest_lean_session_errored_is_not_a_complete_pair, test_a_task_whose_lean_error_came_before_its_measured_session_stays_complete, test_a_passing_run_whose_sessions_give_nineteen_pairs_is_refused_whatever_it_claims, test_a_passing_run_of_twenty_pairs_standing_clear_passes, test_an_index_raising_a_runs_pairs_is_refused_naming_both_figures, test_an_index_listing_no_standing_for_the_role_is_refused, test_an_index_regrouping_two_runs_into_one_lineage_is_refused_for_each, test_a_continued_run_is_one_lineage_whichever_part_is_cited, test_a_part_cited_with_other_pairs_is_judged_against_the_whole_lineage, test_a_results_file_recording_more_pairs_than_its_sessions_give_is_refused, test_a_cited_run_whose_results_measured_another_role_is_refused, test_a_cited_run_the_results_files_cannot_chain_is_refused_as_missing, test_a_clear_run_short_of_the_floor_is_refused_naming_the_pairs_it_reached, test_a_closed_lineage_whose_tip_records_no_standing_is_judged_not_clear_and_no_more) | 6 -- `tests/acceptance/test_flip_gate_takes_standing_from_results.py` (test_an_index_and_record_raising_a_runs_pairs_are_refused_naming_both_figures, test_an_underpowered_run_dressed_as_clear_in_the_index_is_refused, test_an_index_regrouping_two_runs_into_one_lineage_is_refused, test_a_results_file_recording_more_pairs_than_its_sessions_give_is_refused, test_a_task_whose_latest_lean_session_errored_is_not_a_complete_pair, test_a_task_whose_lean_error_came_before_its_measured_session_stays_complete) | `scripts/kernel_ledger_checks.py`, `scripts/kernel_run_evidence.py` | met |
| REQ-15 | 13 -- `scripts/test_kernel_run_evidence.py` (test_a_closed_tip_is_judged_not_clear_without_a_recorded_standing, test_a_recorded_standing_is_read_as_the_lineage_standing_of_its_run, test_a_malformed_standing_is_refused_naming_the_run_and_what_is_wrong, test_legacy_underpowered_file_stands_underpowered_and_scored_nothing, test_an_underpowered_standing_listing_scored_checks_is_unrecorded_as_the_eval_refuses_it, test_an_underpowered_standing_listing_no_scored_check_is_read); `scripts/test_kernel_ledger_checks_evidence.py` (test_a_not_clear_run_flagged_as_passing_is_refused_though_the_index_says_clear, test_a_run_flagged_as_not_passing_beside_a_not_clear_standing_is_honest, test_an_index_labelling_a_not_clear_run_clear_is_refused_naming_both_labels, test_a_closed_lineage_stands_not_clear_whatever_its_file_records, test_a_lineage_whose_last_part_records_no_standing_is_refused_naming_role_and_run, test_a_flag_and_a_sufficiency_claim_a_not_clear_standing_refutes_are_refused_with_figures, test_an_open_lineage_whose_tip_records_no_standing_is_refused_naming_why) | 2 -- `tests/acceptance/test_flip_gate_takes_standing_from_results.py` (test_a_not_clear_run_labelled_clear_in_the_index_is_refused, test_an_earlier_run_labelled_clear_in_the_index_and_the_record_is_refused) | `scripts/kernel_ledger_checks.py`, `scripts/kernel_run_evidence.py` | met |
| REQ-16 | -- | -- | `.ai-state/decisions/387-intentional-compaction-handoff.md`, `.ai-state/decisions/461-eligibility-pin-in-gate-implementer-eligible.md`, `dec-463 (the flip-gate evidence decision record)`, `docs/lean-spawn-how-to.md` | met |
| REQ-17 | 4 -- `scripts/test_kernel_run_evidence_parity.py` (test_the_judged_flip_and_scored_checks_equal_the_index_entry, test_every_committed_results_file_is_read_and_listed_in_the_index); `scripts/test_kernel_run_evidence.py` (test_legacy_file_reads_its_verdict_as_the_standing_of_the_run); `scripts/test_kernel_ledger_checks_scored.py` (test_a_run_before_the_standing_was_recorded_is_judged_from_its_verdict) | 2 -- `tests/acceptance/test_ratified_evidence_and_the_run_index.py` (test_the_committed_ledger_over_a_reindexed_results_directory_passes, test_the_gate_derives_each_committed_runs_standing_as_the_eval_does) | `scripts/kernel_ledger_checks.py`, `scripts/kernel_run_evidence.py` | met |

## Key Decisions

- `dec-463`: the gate judges a cited run's lineage, complete pairs, standing and scored checks from the run's own results files (`scripts/kernel_run_evidence.py`, stdlib-only, with a parity test against the eval) and holds the record and the run index to them; the index is a locator and digest at schema 2, and its `scored_checks` is trusted text that feeds no verdict.
- `dec-464`: during a step loop the orientation reads `status --json` (`selected_step`, `then`) and reports the driver's position, with a fallback when the position cannot be read; it mirrors the driver's attempt cap until `status` emits each step's cap (td-481).
- `dec-465`: the Stop guard holds once per stop, only where `record` would accept the agent as ended (a strict subset), and fails open on any error; outside a loop it imports nothing, reads no transcript and starts no process.

## Footprints

- FC-01 always-loaded tokens: 24800 at baseline and final.
- FC-02 listing tokens: 14268 at baseline and final.
- FC-03 agent prompt size: 2 warn, 0 fail at both.
- FC-04 main-session startup: 65043 at baseline (Claude Code 2.1.303), 64675 final (2.1.304), on the subscription.

## Deferred

td-478 (the driver commits declared files on a `[CONFLICT]` return whose Check passes; important), td-479 (driver-written green sections over the shape checker's ceiling), td-480 (bound the guard's per-Stop transcript read), td-481 (`status` emits each step's attempt cap), td-482 (one `Standing` leaf for the two gate readers), td-483 (name a dropped results file), td-484 (pyright Optional subscripts in an outer-loop test), td-485 (gather the results files outside the gate's judging), td-486 (scanner allowlists in the acceptance-design path classes); td-475 extended with the flip test module's size.
