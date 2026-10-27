# Spec: gate-repairs (the five rows Phase 3 leans on)

**Task slug**: `gate-repairs`
**Feature**: Repair the gates the startup-context diet's Phase 3 is built through: td-476 (eval-driving root tests never selected), td-433 (the spawn tally over-charges a pipeline), td-491 (the implementer's id-citation pre-check), td-492 (a hung gate run is killed only on attach), td-494 W5 (a cut-off run in a `-q` pocket shows no failures).
**Tier**: Full (re-tiered from Standard at Step 9 when the step loop spent 18 of 18 iterations; 13 requirements over 45 files; 13 of 32 charged spawns by the counter).
**Pipeline branch**: `worktree-gate-repairs`
**Start date**: 2026-10-26
**End date**: 2026-10-27
**Archived**: 2026-10-27 (post-merge; merged to main at `47b2272f` with `--no-ff`, finalized in `cab4de14`)
**Status**: completed -- first verdict FAIL (the spawn row took its checkout from `CLAUDE_PROJECT_DIR`; a pyright error in an acceptance file; stale traceability; an unrecorded acceptance-file edit), fixed in `c21d9a65`, `d639909f` and the pipeline records; re-verification PASS WITH FINDINGS.
**ADRs**: `dec-474` (behavioral: a module outside a pocket holding `--project` and the pocket's root drives it), `dec-475` (behavioral: a background watchdog stops a gate run at its recorded bound; gate runs set pytest verbosity absolutely; narrows `dec-467`), `dec-476` (behavioral: spawn rows carry session kind and the logging checkout; the tally leaves headless slug-less spawns out; narrows `dec-413`)
**Evidence base**: the commits from `db5ea37d` to `bf397171`; the calibration row dated 2026-10-27; the integration run (root 15023, eval 2707, chronograph 288 passed) and the rework's derived scope (4983 + 1976 root, 2707 eval, 128 chronograph, 0 failed).

## Feature Summary

The step loop, the spawn budget and the test selector are the gates Phase 3 is built through, and five open rows made them miss tests, overcharge a budget, waste attempts or leave runs hanging. A change inside a pocket now selects the root tests that start that pocket in a child process. Spawn rows record whether their session was headless and the checkout they were logged in, and the tally charges a pipeline only its own spawns, listing the headless slug-less ones apart. The implementer runs the commit's citation check before it reports, and the Codex wrapper carries that instruction. A detached gate run stops itself at its recorded bound through a background watchdog, with the command keeping default signal handling, in the kill form dash accepts. Gate runs set pytest's verbosity absolutely, so a quiet pocket still names its failures.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (final digest after the answered Spec Questions SQ-01 to SQ-03, SQ-P1, SQ-L1 and SQ-L2). REQ ids are pipeline-local and appear in no code.
Complexity: medium (five independent behaviours, one per ledger row, each local to one gate). Brownfield baseline: no archived spec covers these gates; the governing decisions are dec-413 (spawn attribution by stated slug), dec-419 (gate-liveness probes), dec-467 (detached pocket runs and their bounds), dec-471 (bare names stay inside a pocket). td-500 (the selection audit's own verdict), td-497 and td-488 are out of scope.

Vocabulary used below (behavioural, not design):

- A **pocket** is a directory with a test runner configuration of its own (the root, the eval, the dashboard, the chronograph server); the **root pocket** is the repository root.
- A test **drives a pocket in a child process** when it, or a module it imports, starts that pocket's code in a separate process through `uv run --project` naming the pocket's directory, rather than importing it; **driving the eval** is this repository's instance. Another launcher (a shell change of directory, a different tool) is outside this repair.
- A **headless session** is a Claude Code session started non-interactively (`claude -p`, or an Agent SDK host); an **interactive session** is one a person types into.
- A **gate run** is one detached test invocation the step-loop driver starts for a step; its **bound** is the seconds its pocket allows; it is **cut off** when it outlives the bound.
- A pocket is **quiet** when its own runner configuration lowers pytest's verbosity (`-q` or `-qq` in `addopts`).

### Observable Surface

- `resolve_test_scope.py` — the existing test-scope resolver
- `uv run --project` — uv's way to run a command inside a named project's own environment
- `eval/pyproject.toml` — the eval pocket's runner configuration
- `eval/uv.lock` — the eval pocket's lockfile
- `spawn_count.py` — the existing per-pipeline spawn tally
- `--slug`, `--budget` and `--json` — existing options of the spawn tally
- `charged`, `verdict`, `unattributed`, `within`, `over` and `indeterminate` — existing fields and verdict words of the tally's output
- `Task slug:` — the line every pipeline spawn prompt states
- `claude -p` — Claude Code's non-interactive print mode
- `check_id_citation_discipline.py` — the existing identifier-citation check the commit gate runs
- `step_loop.py` — the existing step-loop driver
- `record` — the driver verb that takes back an agent's return and runs its gate
- `Failed:` — the existing evidence line naming a failed test for the next attempt
- `addopts` — pytest's configured default options
- `-q`, `-qq` and `-v` — pytest's verbosity options
- `task-chronograph-mcp` — the existing pocket whose options carry `-q`
- `generate_kernels.py --check` — the existing kernel freshness check
- `check_kernel_manifest.py` — the existing kernel commit gate
- `python3 scripts/check_agent_prompt_size.py --json` — the registered prompt-size instrument
- `python3 scripts/measure_token_budget.py --json` — the registered token instrument (free counting endpoint)
- `python3 <token-reading...>` — the free-endpoint reading of one definition's tokens (see SQ-06)
- `python3 scripts/measure_selection_size.py --json --compare-ref <base>` — the registered selection-size instrument

### REQ-01: An eval change selects the root tests that drive the eval

**When** a change set holds any file of the eval package, `eval/pyproject.toml` or `eval/uv.lock`
**and** the root pocket holds tests that drive the eval in a child process, in this repository or in a managed project with an eval pocket of its own
**the system** (`resolve_test_scope.py`) includes every such test in the root pocket's derived scope, each naming the changed path that selected it, while still widening the eval pocket to its full suite for a configuration or lockfile change as today
**so that** a step's derived scope no longer misses the root tests that would catch an eval regression, and selection keeps never narrowing.

### REQ-02: A test added later that drives the eval is selected without a per-test listing

**When** a new root-pocket test drives the eval in a child process, itself or through a module it imports that already does
**the system** selects it on an eval package, configuration or lockfile change with no per-test entry written by hand
**so that** the repair does not decay into a hand-kept list that the next such test silently escapes.

### REQ-03: Selection without the condition is unchanged

**When** a change set touches no eval file, or the project has no root test that drives another pocket in a child process
**the system** returns exactly the scope it returns today
**so that** managed projects and unrelated changes pay nothing for the repair.

### REQ-04: A headless session's slug-less spawn is not charged to the checkout's slug

**When** a headless session spawns an agent whose prompt states no task slug
**the system** (`spawn_count.py`) charges that agent to no slug, does not count it among `unattributed`, leaves the `verdict` unmoved by it, and lists it apart with the reason it was left out
**so that** measurement and probe sessions run inside a pipeline's worktree stop inflating that pipeline's tally, while what was left out stays visible.

### REQ-05: Only spawns that state the slug, or the checkout's own interactive slug-less spawns, are charged

**When** the tally counts a slug
**the system** charges an agent whose spawn prompt states that slug, whichever checkout or session kind spawned it, charges an interactive session's slug-less spawn to the pipeline only when it was recorded in the pipeline's own checkout, and never charges a slug-less spawn whose row records any other checkout, even one whose directory name equals the slug (a spawn whose session kind is unknown records no checkout and keeps today's attribution, as REQ-06 states); the pipeline's own checkout is the checkout the tally runs from when that checkout is named after the slug, and, when the tally runs from a checkout not named after the slug, every checkout named after it, as today
**so that** a pipeline's tally is its own spawns, and a pipeline that moved checkouts is still counted whole.

### REQ-06: An unattributable spawn still withholds the verdict, and old logs read as before

**When** an agent cannot be attributed to any slug, or its spawning session cannot be shown to be headless
**the system** keeps the unattributable agent in the pending pool that keeps the verdict from reading `within`, keeps today's attribution for an agent whose session kind is unknown, and tallies a log whose rows carry no session-kind evidence exactly as today
**so that** the repair can only remove a proven over-charge, never turn an unknown into a silent zero.

### REQ-07: The implementer runs the commit's citation check on its own files before reporting

**When** the implementer finishes a step and before it reports the step done
**the system** has it run `check_id_citation_discipline.py` over the files it changed in that step, with the same exemptions the step's commit applies, and remove every citation that check refuses before reporting
**so that** an identifier-citation refusal at the driver's commit no longer costs an attempt or an orchestrator fix.

### REQ-08: The instruction reaches every implementer spawn, and degrades to today

**When** the implementer is spawned from its plugin definition, as a kernel-switched role, or from the Codex export, in this repository or a managed project
**the system** carries the pre-report citation check in each of those forms, and where the check cannot run (not installed, an older Praxion, a host without it) the implementer reports it as not run and proceeds as today, with the commit's own gate still the backstop
**so that** the repair reaches every spawn through its artifacts and never leaves a host with less than today.

### REQ-09: A gate run past its bound is stopped with no later call

**When** a detached gate run is still running when its pocket's bound expires
**and** no `record` call attaches to it (the session ended, the task was dropped)
**the system** stops the run and every process it started, no later than 30 seconds past the bound
**so that** an abandoned run never keeps its processes alive indefinitely.

### REQ-10: A stopped run reads as cut off, never as anything else

**When** a later `record` call attaches to a run that was stopped for outliving its bound
**the system** reads it as cut off, red, with the failures its output showed before the stop kept as evidence for the next attempt, never as not started and never as finished
**so that** the stop changes when a run ends, not what the gate concludes about it.

### REQ-11: The stop is safe and self-contained

**When** a run finishes inside its bound, or the process number on record now belongs to something else
**the system** never signals it, holds the run to the bound recorded when it started whatever the environment says later, and enforces the bound on macOS and Linux with no tool those systems do not ship by default and with no Praxion hook installed
**so that** the stop cannot kill innocent work or depend on an installation a managed project may lack.

### REQ-12: A cut-off run in a quiet pocket names its failures

**When** a gate run in a quiet pocket is cut off
**and** some tests had failed before the cut
**the system** names each of them, pocket first, in the next attempt's `Failed:` evidence, exactly as it does for the same run in a pocket that is not quiet
**so that** the next attempt is told which tests failed rather than only that the run was cut off.

### REQ-13: The quiet pocket's own configuration and other readings are untouched

**When** the gate runs in a quiet pocket, finished or cut off
**the system** leaves the pocket's committed runner configuration unchanged, keeps today's counts and failures for a finished run, and reads a cut-off run with no failure before the cut as cut off with no `Failed:` line, never as green
**so that** a developer's own runs in that pocket stay as configured and no reading regresses.

## Acceptance Criteria

Standing constraints (the user's non-negotiables, cited below as NN-1 to NN-6):

- **NN-1** No rule moves and no always-loaded text changes: no rule file, rule delivery manifest, user instruction template or project instruction file changes, and the always-loaded budget reading is unchanged.
- **NN-2** Nothing is cut to meet a number; no Praxion principle or process step loses meaning.
- **NN-3** The process reaches every session and spawn through its artifacts (rules, kernels, hooks, definitions, gates), never through memory; the behavioural contract still reaches every agent.
- **NN-4** Gates stay deterministic. With hooks absent (Codex, Cursor, a broken install) behaviour falls back to today's, never to nothing.
- **NN-5** Every behaviour holds in a managed project (more agents, older Praxion), not only in this repository; a project without the condition a requirement repairs behaves exactly as today.
- **NN-6** No paid eval run and no API call beyond the free token-counting endpoint; footprints are measured in real tokens where a context artifact changes, and only what a measurement shows is claimed.

Checklist (each item names the requirements and constraints it discharges):

- [ ] **AC-01** For a change set holding any file of the eval package, `eval/pyproject.toml` or `eval/uv.lock`, the root pocket's derived scope from `resolve_test_scope.py` includes every root-pocket test that drives the eval through the eval project's own environment in a child process, including the partial-output scenarios, the spend-and-results journey and the no-claude tripwire; each such test names the changed path it was selected for; a change to the eval runner configuration or lockfile still widens the eval pocket to its full suite as today. (REQ-01, REQ-02)
- [ ] **AC-02** A planted root-pocket test that drives the eval the same way as the existing ones, added with no other edit, is selected by an eval package change like the rest. (REQ-02)
- [ ] **AC-03** For a change set that touches no eval file, the root pocket's selection is identical to today's; in a fixture project with no second pocket driven in a child process, every derived scope is byte-identical to today's answer. (REQ-03; NN-5)
- [ ] **AC-04** Over a planted observation log: an agent spawned by a headless session whose spawn prompt states no task slug, run in the pipeline's own checkout, is not counted in `charged` for the slug the checkout is named after, is not listed under `unattributed`, and does not move the `verdict`; it is listed apart with the reason it was left out; the same agent spawned by an interactive session is charged exactly as today. (REQ-04; NN-5)
- [ ] **AC-05** Over a planted log: an agent whose spawn prompt states the pipeline's slug is charged to it from whichever checkout or session kind spawned it, headless included; an agent recorded in another checkout whose prompt states no slug is never charged to the pipeline, even when that checkout's directory name equals the slug. (REQ-05)
- [ ] **AC-06** Over a planted log: an agent no rule can attribute still keeps the verdict from reading `within` (it reads `indeterminate`, or `over` when the definite count alone exceeds the budget); an agent whose spawning session cannot be shown to be headless keeps today's attribution; a log written by an older Praxion whose rows carry no session-kind evidence tallies byte-identically to today's output. (REQ-06; NN-4, NN-5)
- [ ] **AC-07** The instruction to run `check_id_citation_discipline.py` over the step's own changed files before reporting done reaches the implementer in every form it is spawned in: the plugin definition, a kernel-switched spawn, and the Codex export; a citation the commit's check would refuse is found and removed before the report, and a host where the check cannot run reports it as not run. (REQ-07, REQ-08; NN-3, NN-4)
- [ ] **AC-08** A detached gate run started by `step_loop.py` `record` that is still running at its pocket's bound is stopped, no later than 30 seconds past the bound, with every process it started, with no later `record` call; a later `record` that does attach reads it as cut off, with the failures it showed before the stop, never as not started. (REQ-09, REQ-10)
- [ ] **AC-09** A run that finishes inside its bound is never stopped; a process that is not the run's own (a reused process number) is never signalled; the bound in force is the one recorded when the run started, whatever the environment says later; the stop works on macOS and Linux with no tool those systems do not ship by default and with no Praxion hook installed. (REQ-10, REQ-11; NN-4, NN-5)
- [ ] **AC-10** A gate run cut off in a pocket whose `addopts` carry `-q` (the `task-chronograph-mcp` pocket, or a planted pocket with `-q` or `-qq`) names, in the next attempt's `Failed:` evidence, each test that had failed before the cut, pocket first, exactly as a run in a pocket without `-q` does; the pocket's committed runner configuration is unchanged, so a developer's own run there stays quiet. (REQ-12, REQ-13; NN-5)
- [ ] **AC-11** A finished run in a quiet pocket keeps today's counts and failures; a cut-off quiet run with no failure before the cut reads as cut off with no `Failed:` line, never as green. (REQ-13)
- [ ] **AC-12** Health guards: no rule file or rule delivery manifest changes and FC-04 holds; after any agent-definition edit `generate_kernels.py --check` is clean, `check_kernel_manifest.py` is clean, and the Codex and Cursor exports are checked; the root suite and the eval pocket pass on their CI commands; ruff and pyright are clean on touched files; FC-01 to FC-05 hold. (NN-1, NN-3, NN-6)

### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | prompt-size | implementer definition length, in lines, as the prompt-size instrument reads it | at or below | 400 lines (the standard warn ceiling: no finding for the implementer definition) | reference: the standard agent warn ceiling, 400 lines | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-02 | listing-tokens | skill and agent description listing, in tokens, on the instrument's ruler | at or below | the baseline reading (no description changes) | baseline: listing tokens at the pipeline base | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | implementer-definition-tokens | the implementer definition plus its kernel text, in tokens, through the free counting endpoint | at or below | the baseline reading plus 250 tokens | baseline: the same reading at the pipeline base | `python3 <token-reading...>` |
| FC-04 | always-loaded-tokens | governed always-loaded total, in tokens, on the instrument's ruler | at or below | the baseline reading (no always-loaded text changes) | baseline: governed total at the pipeline base | `python3 scripts/measure_token_budget.py --json` |
| FC-05 | test-selection-size | root pocket narrow-run median, in test files, over the last 50 non-merge commits | at or below | the reference resolver's median times 1.10 | reference: the resolver at the pipeline base, run by the instrument over the same tree and change sets | `python3 scripts/measure_selection_size.py --json --compare-ref <base>` |

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| spawn-startup-tokens | its registered instrument starts a headless claude session per role, which this pipeline's cost rule forbids; FC-03 bounds the same growth through the free counting endpoint |
| hook-latency | the registry names no instrument for hook latency; recorded only in case the spawn-tally repair adds evidence at recording time |
| observation-log-volume | the registry names no instrument for log volume; recorded only in case the spawn-tally repair adds a field to recorded rows |
| spawn-count | the registry names no instrument (`spawn_count.py` counts a pipeline that has already run, not a change); moved because the spawn-budget reference is updated to describe the repaired tally |

## Traceability Matrix

Rendered from `traceability.yml` at archival (repaired after the first verification). `Status` is the re-verification's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 4 -- `scripts/test__python_selection_pockets.py` (test_a_test_importing_a_driver_of_the_changed_pocket_is_selected, test_a_test_holding_both_constants_is_itself_a_driver, test_a_driver_is_selected_by_a_change_to_any_file_of_the_pocket, test_a_test_reaches_a_driver_through_a_non_test_module) | 4 -- `tests/acceptance/test_eval_change_selects_the_root_tests_that_drive_it.py` (test_an_eval_change_selects_each_root_test_that_drives_the_eval, test_an_eval_configuration_or_lockfile_change_still_widens_the_eval_pocket, test_a_managed_projects_root_test_driving_its_eval_pocket_is_selected, test_a_managed_projects_root_test_that_itself_starts_the_eval_is_selected) | 3 -- `scripts/_python_selection.py` (_PocketDrivers, Graph._dependents, _reach) | PASS |
| REQ-02 | 2 -- `scripts/test__python_selection_pockets.py` (test_a_test_holding_both_constants_is_itself_a_driver, test_a_test_importing_a_driver_of_the_changed_pocket_is_selected) | 1 -- `tests/acceptance/test_eval_change_selects_the_root_tests_that_drive_it.py` (test_a_root_test_added_later_that_drives_the_eval_is_selected_with_no_other_edit) | 1 -- `scripts/_python_selection.py` (_PocketDrivers.add_module) | PASS |
| REQ-03 | 5 -- `scripts/test__python_selection_pockets.py` (test_a_module_holding_only_the_project_flag_drives_nothing, test_a_module_holding_only_the_pocket_path_drives_nothing, test_a_driver_is_not_selected_by_a_file_outside_the_pocket, test_a_pocket_file_met_on_the_way_does_not_select_the_pocket_drivers, test_a_project_with_only_a_root_pocket_has_no_drivers) | 1 -- `tests/acceptance/test_eval_change_selects_the_root_tests_that_drive_it.py` (test_without_the_condition_the_answer_is_byte_identical_to_todays) | 2 -- `scripts/_python_selection.py` (_PocketDrivers.driving, _reach) | PASS |
| REQ-04 | 2 -- `hooks/test_capture_observations_session_kind.py` (test_a_spawn_result_records_the_origin_it_is_handed, test_the_hook_records_the_session_kind_its_entrypoint_shows_and_the_checkout_it_logs_in); 3 -- `hooks/test_hook_utils.py` (test_session_origin_names_the_kind_of_each_classified_entrypoint_with_the_checkout, test_session_origin_shows_nothing_for_an_unclassified_entrypoint, test_session_origin_never_reads_the_directory_the_session_was_started_in); 4 -- `scripts/test_spawn_count_left_out.py` (test_a_slugless_headless_spawn_is_left_out_wherever_it_ran, test_the_envelope_lists_each_left_out_agent_with_its_reason, test_the_envelope_has_no_left_out_key_when_nothing_was_left_out, test_a_left_out_agent_makes_no_slug_seen_through_its_owner) | 4 -- `tests/acceptance/test_spawn_tally_charges_only_its_pipelines_spawns.py` (test_a_headless_slugless_spawn_in_the_pipelines_checkout_is_not_charged, test_a_headless_slugless_spawn_is_not_pending_as_unattributed, test_a_headless_slugless_spawn_is_listed_apart_with_the_reason_it_was_left_out, test_a_slugless_spawn_a_person_made_in_the_pipelines_checkout_is_charged_as_today) | 1 -- `hooks/_hook_utils.py` (session_origin); 2 -- `hooks/capture_observations.py` (spawn_result_fields, main); 1 -- `hooks/_observation_log/registry.py` (_AGENT_SPAWN_FIELDS); 4 -- `scripts/spawn_count.py` (_row_owner, slugless_owner, _session_kind, _build_envelope) | PASS |
| REQ-05 | 3 -- `hooks/test_capture_observations_session_kind.py` (test_a_spawn_result_records_the_origin_it_is_handed, test_the_hook_records_the_session_kind_its_entrypoint_shows_and_the_checkout_it_logs_in, test_a_session_started_below_the_checkout_root_records_the_checkout_not_its_start_directory); 3 -- `hooks/test_hook_utils.py` (test_session_origin_names_the_kind_of_each_classified_entrypoint_with_the_checkout, test_session_origin_shows_nothing_for_an_unclassified_entrypoint, test_session_origin_never_reads_the_directory_the_session_was_started_in); 4 -- `scripts/test_spawn_count_left_out.py` (test_a_stated_slug_owns_the_agent_from_any_session_kind_and_checkout, test_a_slugless_spawn_in_another_checkout_bearing_the_roots_name_is_left_out, test_a_slugless_spawn_in_the_root_itself_belongs_to_the_roots_name, test_a_slugless_spawn_belongs_to_the_checkout_it_ran_in); 1 -- `scripts/test_spawn_count_session_origin.py` (test_an_interactive_slugless_spawn_is_charged_to_the_pipeline_whatever_directory_it_began_in) | 4 -- `tests/acceptance/test_spawn_tally_charges_only_its_pipelines_spawns.py` (test_a_spawn_stating_the_slug_is_charged_from_any_checkout_and_session_kind, test_a_slugless_spawn_in_another_checkout_bearing_the_slugs_name_is_never_charged, test_from_a_checkout_not_named_after_the_slug_every_checkout_named_after_it_is_charged, test_a_slugless_spawn_of_unknown_kind_in_another_checkout_keeps_todays_attribution) | 1 -- `hooks/_hook_utils.py` (session_origin); 2 -- `hooks/capture_observations.py` (spawn_result_fields, main); 1 -- `hooks/_observation_log/registry.py` (_AGENT_SPAWN_FIELDS); 4 -- `scripts/spawn_count.py` (_row_owner, slugless_owner, _session_kind, _build_envelope) | PASS |
| REQ-06 | 2 -- `hooks/test_capture_observations_session_kind.py` (test_a_spawn_result_records_the_origin_it_is_handed, test_the_hook_records_the_session_kind_its_entrypoint_shows_and_the_checkout_it_logs_in); 3 -- `hooks/test_hook_utils.py` (test_session_origin_names_the_kind_of_each_classified_entrypoint_with_the_checkout, test_session_origin_shows_nothing_for_an_unclassified_entrypoint, test_session_origin_never_reads_the_directory_the_session_was_started_in); 3 -- `scripts/test_spawn_count_left_out.py` (test_a_result_row_without_the_new_keys_belongs_to_its_project, test_an_unattributed_agent_stays_unattributed_without_a_transcript, test_an_unrecognised_session_kind_is_never_read_as_headless) | 3 -- `tests/acceptance/test_spawn_tally_charges_only_its_pipelines_spawns.py` (test_an_agent_no_rule_can_attribute_keeps_the_verdict_from_reading_within, test_an_unattributable_agent_beside_a_count_already_over_budget_reads_over, test_a_log_whose_rows_carry_no_session_kind_tallies_exactly_as_today) | 1 -- `hooks/_hook_utils.py` (session_origin); 2 -- `hooks/capture_observations.py` (spawn_result_fields, main); 1 -- `hooks/_observation_log/registry.py` (_AGENT_SPAWN_FIELDS); 4 -- `scripts/spawn_count.py` (_row_owner, slugless_owner, _session_kind, _build_envelope) | PASS |
| REQ-07 | -- | 1 -- `tests/acceptance/test_implementer_checks_its_citations_before_reporting.py` (test_the_plugin_definition_carries_the_pre_report_citation_check) | 1 -- `agents/implementer.md` (Self-Review (pre-report citation check item)) | PASS (agent behaviour: verifier judgment) |
| REQ-08 | 4 -- `scripts/test_export_codex_agents.py` (test_a_marked_passage_is_embedded_once_outside_the_capsule, test_two_marked_passages_keep_their_order, test_an_unmarked_definition_exports_the_unchanged_wrapper, test_a_malformed_marker_raises_naming_the_file) | 2 -- `tests/acceptance/test_implementer_checks_its_citations_before_reporting.py` (test_a_kernel_switched_implementer_receives_the_pre_report_citation_check, test_the_codex_export_carries_the_pre_report_citation_check) | 2 -- `codex/config/export-codex-agents.py` (extract_wrapper_passages, render_developer_instructions); 1 -- `agents/implementer.md` (Self-Review (pre-report citation check item)) | PASS (agent behaviour: verifier judgment) |
| REQ-09 | 4 -- `scripts/test__step_loop_pocket_shell.py` (test_a_run_that_outlives_its_bound_is_stopped_by_its_launcher_with_its_child, test_the_cut_marker_exists_before_the_launcher_signals_the_run_whatever_the_shell, test_a_command_run_through_the_launcher_keeps_the_default_interrupt_and_terminate_handling, test_a_run_and_its_child_that_both_ignore_sigterm_are_still_gone_after_the_second_signal) | 1 -- `tests/acceptance/test_abandoned_gate_run_is_stopped.py` (test_an_abandoned_run_past_its_bound_is_stopped_with_every_process_it_started) | 2 -- `scripts/_step_loop_pocket_runs.py` (_LAUNCHER, _launch) | PASS |
| REQ-10 | 2 -- `scripts/test__step_loop_pocket_shell.py` (test_a_run_that_outlives_its_bound_is_stopped_by_its_launcher_with_its_child, test_a_cut_marker_that_cannot_be_written_means_no_signal_whatever_the_shell) | 1 -- `tests/acceptance/test_abandoned_gate_run_is_stopped.py` (test_a_later_record_reads_the_stopped_run_as_cut_off_with_its_earlier_failures) | 2 -- `scripts/_step_loop_pocket_runs.py` (_LAUNCHER, read_run) | PASS |
| REQ-11 | 4 -- `scripts/test__step_loop_pocket_shell.py` (test_a_run_that_exits_inside_its_bound_is_untouched_and_its_watchdog_ends_with_it, test_the_bound_the_launcher_is_handed_is_the_one_the_run_was_started_with, test_a_launcher_that_does_not_lead_its_group_signals_no_sibling, test_a_bound_too_large_for_the_shells_arithmetic_is_capped_before_it_reaches_the_shell) | 4 -- `tests/acceptance/test_abandoned_gate_run_is_stopped.py` (test_a_run_that_finishes_inside_its_bound_is_never_stopped, test_the_bound_in_force_is_the_one_recorded_when_the_run_started, test_a_process_number_that_now_belongs_to_something_else_is_never_signalled, test_the_stop_needs_no_tool_beyond_the_systems_own_and_no_hook) | 2 -- `scripts/_step_loop_pocket_runs.py` (_LAUNCHER, _launch) | PASS on macOS (dash, sh, bash); Linux CI pending (td-507) |
| REQ-12 | 2 -- `scripts/test__step_loop_pocket_runs.py` (test_a_quiet_pocket_still_prints_each_outcome_and_names_its_failure, test_a_pytest_invocation_is_asked_for_each_outcome_and_the_failures_and_errors_it_names); 1 -- `scripts/test_loop_io_vcs.py` (test_a_pytest_invocation_is_run_with_the_flags_that_report_each_outcome) | 1 -- `tests/acceptance/test_quiet_pocket_cut_off_names_its_failures.py` (test_a_cut_off_quiet_run_names_its_failures_as_a_plain_pocket_run_does) | 2 -- `scripts/_step_loop_pocket_runs.py` (_OUTCOME_REPORTS, with_outcome_reports) | PASS |
| REQ-13 | 1 -- `scripts/test__step_loop_pocket_runs.py` (test_a_quiet_pocket_still_prints_each_outcome_and_names_its_failure) | 4 -- `tests/acceptance/test_quiet_pocket_cut_off_names_its_failures.py` (test_the_quiet_pockets_committed_configuration_is_left_as_it_is, test_the_chronograph_pocket_stays_quiet_for_a_developers_own_runs, test_a_finished_quiet_run_keeps_the_counts_and_failures_a_plain_run_shows, test_a_cut_off_quiet_run_with_no_failure_reads_cut_off_with_no_failed_line) | 1 -- `scripts/_step_loop_pocket_runs.py` (with_outcome_reports) | PASS |

## Key Decisions

- `dec-474`: a module outside pocket P whose code holds the constant `--project` and a constant equal to P's root drives P; a change inside P selects, through the import closure, every test that is or imports a driver.
- `dec-475`: a detached gate run's command keeps the launcher's foreground (a background command in a non-interactive POSIX shell starts with SIGINT ignored); a background watchdog writes the cut marker first and then signals the launcher's own group with `kill -s TERM`, then `kill -s KILL`, once the run outlives its recorded bound by a 5 s grace; gate pytest runs pass `--verbosity=1` with `-rfE` instead of `-v`.
- `dec-476`: the spawn-result row records `session_kind` (a closed map of the harness entrypoint) and `checkout` (the checkout the row is logged in) together or not at all; the tally leaves a headless slug-less spawn out under `left_out`, charges an interactive slug-less spawn only from the pipeline's own checkout, and reads rows without the keys as before.

## Footprints

- FC-01 implementer definition size: 229 lines, no finding (warn ceiling 400).
- FC-02 listing tokens: 14268 at baseline and final.
- FC-03 implementer definition plus kernel: 13246 at baseline, 13452 final (+206 against a +250 bound).
- FC-04 always-loaded tokens: 23652 at baseline and final.
- FC-05 test-selection size (root pocket, 50 change sets): narrow median 96 against the reference resolver's 96 (ratio 1.00 against a 1.10 bound).
- Declared not measured: spawn-startup-tokens, hook-latency, observation-log-volume, spawn-count.

## Deferred

td-492 (in flight until a Linux CI run proves the dash kill form; td-507), td-499 (the canaries job ran out of disk), td-500 (the selection audit's verdict, mostly whole-checkout copy reads), td-501 (47 hook commands with an unquoted plugin root), td-505 (scope or locate `left_out` entries), td-506 (end the watchdog when its launcher is gone), td-509 (`scripts/CLAUDE.md` catalog stale under NN-1), td-510 (mutation sensor recipes for `hooks/` and `scripts/` modules importing `hooks/`), td-511 (the validator-advisory tolerance anchored by text).
