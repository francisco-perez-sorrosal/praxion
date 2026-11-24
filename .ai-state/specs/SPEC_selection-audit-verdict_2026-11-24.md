# Spec: selection-audit-verdict (the selection audit's verdict names only reads a reader can act on)

**Task slug**: `selection-audit-verdict`
**Feature**: The weekly selection audit sets aside the reads a test makes by copying the whole checkout into a sandbox: a fourth tracer channel, `copy`, for the source-side open of a `shutil` copy of the repository root (a `copytree` of the root, or path-keeping copies after the running test listed the checkout with `git ls-files`), counted in the verdict's notes and not judged per file. Every other read, a copying test's own included, is judged as before. Each real gap the audit then named is closed by an additive, reader-sized entry in `tests/declared-deps.toml`, so no change selects less than at the base. The audit passes locally for the first time since it shipped.
**Tier**: Standard (the verifier's retrospective calibration reads correct after both rounds: 8 charged spawns of 16, 21 of 37 loop iterations, no re-tier, rework in place)
**Complexity**: large: 14 requirements, 22 plan steps (14 driven), 34 commits and 26 files changed against `260a6d02` (+2,339 and -42 lines); no resolver code change; `tests/declared-deps.toml` +429 lines, additive only
**Base commit**: `260a6d02` (main on 2026-11-22); the loop's base `91a0ca95`
**Head at archival**: `07f63817`. Landmarks: acceptance design `12d11cbe` and `b8210535`; the design `91a0ca95`; first production commit `2782aff2`; the hook closure `82aaa90f`; the closures the first local pass named `cc46be4c`; the root gate bound re-size `e6f565b5` (a separate change, see Key Decisions); the heads the verifier read `736c02e4` (round 1) and `c17d04e5` (round 2)
**Pipeline branch**: `worktree-selection-audit-verdict`
**Start date**: 2026-11-22
**End date**: 2026-11-24
**Archived**: 2026-11-24 (pre-merge; the merge, the push and the Linux `Gate liveness` reading follow)
**Status**: completed -- verified: PASS WITH FINDINGS after one in-place rework round. Round 1 read FAIL (3 FAIL, 11 WARN: the audit job wrote its report into a `tmp/` no fresh runner has, and two Spec Questions lacked their records); round 2 read 0 FAIL and 8 WARN, and its two record fixes (`07f63817`) were accepted by a fresh light review. macOS only; Linux from the post-merge `Gate liveness` run (AC-04)
**ADRs**: `dec-525` (category: behavioral -- checkout copies set aside by source root; narrows `dec-420`'s `direct` clause, `supersedes_in_part`; promoted at the merge)
**Evidence base**: `dec-525`; the pipeline's completion row in `.ai-state/calibration_log.md` dated 2026-11-24; the Traceability matrix below (rendered from the ephemeral `.ai-work/selection-audit-verdict/traceability.yml`, 59 nodes, every one a `def` at `c17d04e5`; spec extract digest `0d34a271a2db`); the readings at `c17d04e5`: the default traced audit passed with 0 unselected reads, the suite 1,448 s of its 4,620 s bound (FC-03 96.0 % of the 1,509 s baseline), copy note "47784 reads by 63 tests"; FC-01 25.6 % of 769 root test files against 21.6 % at the base (limit +5 points); FC-02 5 of 50 change sets widened (unchanged); never narrower 0 misses over 3,910 paths in every pocket; ledger rows td-689 (the hook-replay edge source, filed), td-690, td-691 and td-692 (follow-ups, filed at the close).

## Feature Summary

At the base the audit failed on 44,582 unselected reads locally and 39,753 on Linux, about 40,000 of them from some 30 tests credited with building a sandbox copy of the checkout, so the verdict said nothing a reader could act on and its size depended on the xdist worker count. Now the tracer records a copy of the checkout as a whole on its own `copy` channel; the judge audits `direct` and `child` reads only and states in every verdict how many (test, file) pairs it set aside, by how many tests, and that later reads from the copies are unaudited. A copy of a named file or directory is still a read. The remaining gaps (the eval pocket's project file, the kernel adoption ledger, the adherence results, the hook helpers, the testing conventions rule, every rule file, every hook module, and the scanners and remainders) are closed by reader-sized declared entries. `check_gates_bite.py` gains `--json-report PATH` for the workflow's uploaded verdict, exiting 2 with the reason when the report cannot be written. The workflow header no longer says the audit is red by design.

## Requirements

A test is *selected* for a file when the resolver's answer for a change to that file alone, in the pocket that holds the test, is that pocket's full suite or a test list that names the test. A test *reads* a file when it opens it, in its own process or in any process it starts. The audit judges the root pocket's answer, as it does today.

### REQ-01: A copy of the checkout is not a read of each copied file

**When** a test in the audit's traced suite copies the checkout as a whole into a sandbox (every tracked file, or every tracked file outside the parts it leaves out)
**the system** reports no file that copy read as an unselected read of that test, whichever test a run credits with a copy that one test made and later tests reuse
**so that** the verdict's failures name only reads that show a test depends on a file.

### REQ-02: The verdict states what the copy rule set aside

**When** the audit reaches a verdict, pass or fail
**the system** says in the verdict's notes how many reads it set aside as copies of the checkout, counted as (test, file) pairs the way its unselected reads are, every pair judged by the copy rule rather than as an ordinary read whether or not a change to that file would have selected the test, how many tests made them, and that what those tests read later from their copies is not audited, with a count of none when no test copied the checkout
**so that** the audit's new blind spot is visible with its size on every run, as its limit on reads made at import time already is.

### REQ-03: Copying a particular file or directory is still a read

**When** a test copies a particular file, or a particular directory, rather than the checkout as a whole
**the system** judges each file that copy read as an ordinary read, and fails the verdict on it when a change to that file does not select the test
**so that** the copy rule cannot hide a real dependency, such as a test that copies the committed adherence results it checks.

### REQ-04: A copying test's other reads still count

**When** a test that copies the checkout as a whole also reads a repository file in any other way, in its own process or in a process it starts
**the system** judges that read as an ordinary read, even when the same file was also part of the copy
**so that** making a copy never excuses a test from the reads that show what it depends on.

### REQ-05: The audit still fails on a lost dependency

**When** a change to a file a test reads no longer selects that test, in a run where other tests copy the checkout
**the system** fails the verdict and names that test and that file among the unselected reads
**so that** the copy rule cannot turn the audit into a check that always passes.

### REQ-06: The audit passes when every dependency is selected

**When** the audit runs on a commit where a change to each file a test reads selects that test, every read the copy rule sets aside apart
**the system** exits 0 with a passing verdict inside its declared time bound, on a developer machine and on the Linux runner of the weekly `Gate liveness` run, and the two whole-suite scenarios that need the audit to pass pass with it
**so that** a red audit is news again, not the state of every week.

### REQ-07: Closing a gap never narrows a selection

**When** this change is complete and any file tracked at both its base commit and its final head changes alone (a bound on this change, compared once at its final head; after the merge the weekly audit is the standing check, and a later deliberate narrowing is judged on its own)
**the system** selects, in every pocket, at least every test it selected for that file at the base commit that still exists, and the full suite of every pocket whose full suite it selected at the base commit
**so that** closing one gap cannot open another.

The real gaps the audit names follow, one requirement each. Every pair below was checked on 2026-11-22 at the base: the resolver's answer for the file alone does not select the test. Each requirement covers every test that reads the file, not only the one named as an example.

### REQ-08: A change to the eval pocket's project file selects the tests that start that pocket

**When** `eval/pyproject.toml` changes alone
**the system** selects each root-pocket test that reads it, such as `scripts/test_pocket_gate_declarations.py`, including a test that reads it only through the eval pocket's runner, started with `uv run --project` in a child process
**so that** a change to how the eval pocket is built runs the root tests that drive it.

### REQ-09: A change to the kernel adoption ledger selects the tests that read it through the spawn hook

**When** `.ai-state/kernel_adoption.yaml` changes alone
**the system** selects each test that reads it, including a test that reads it only through the spawn hook it runs in a child process, such as `tests/acceptance/test_spawn_kernel_injection.py`
**so that** a ledger edit runs the tests whose outcome depends on it.

### REQ-10: A change to a committed adherence results file selects the tests that read it

**When** a committed results file under `.ai-state/eval_ledger/adherence/` changes alone
**the system** selects each test that reads it, the kernel-manifest tests among them, such as `scripts/test_kernel_run_evidence_parity.py`
**so that** a recorded run's evidence is never changed without the checks that judge it.

### REQ-11: A change to a hook helper selects the tests whose hook processes read it

**When** `hooks/_hook_utils.py` or `hooks/_commit_command.py` changes alone
**the system** selects each test that reads it: for `hooks/_commit_command.py`, including a test that reads it only through a hook it starts in a child process, such as `hooks/test_inject_subagent_context_delivery.py`; for `hooks/_hook_utils.py`, each of the four tests outside the checkout copies that the local audit of 2026-11-22 found unselected, `tests/acceptance/test_adherence_eval_stays_out_of_band.py`, `tests/acceptance/test_live_eval_treats_archives_as_byproducts.py`, `tests/acceptance/test_log_archives_stay_out_of_version_control.py` and `tests/acceptance/test_log_health_checks.py`, by whatever process they read it (the verdict does not record which)
**so that** a change to a helper every hook shares runs the tests that exercise those hooks.

### REQ-12: A change to the testing conventions rule selects the test that pins its exported form

**When** `rules/swe/testing-conventions.md` changes alone
**the system** selects `tests/acceptance/test_other_channels_carry_the_kernel.py`
**so that** an edit to the rule cannot break its pinned Cursor export unseen, as one did before.

The local audit run of 2026-11-22 named two more classes of real gap, larger than the named ones together. They are requirements too, since the audit cannot pass while they stand (REQ-06).

### REQ-13: A change to any rule file selects the tests that read every rule

**When** any rule file changes alone, a rule file being every tracked file under the rules tree except its two prose guides, `rules/README.md` and `rules/CLAUDE.md`, with the manifests `rules/_manifest.yaml` and `rules/_audience.yaml` included, such as `rules/swe/vcs/git-conventions.md`
**the system** selects each test that reads it, including a kernel test that reads every rule file through the kernel tools it runs, such as `scripts/test_check_kernel_manifest.py`
**so that** a rule edit runs the checks that hold the kernels equal to the rules.

### REQ-14: A change to any hook module selects the tests that read every hook

**When** any hook module changes alone, such as `hooks/inject_rules.py`
**the system** selects each test that reads it, including a test that reads it only through the hooks it starts, such as `hooks/test_inject_subagent_context_delivery.py`
**so that** a hook edit runs the tests that deliver through the registered hooks.

### Observable Surface

- `check_gates_bite.py --gate selection-audit`, `check_gates_bite.py --gate selection-audit --json` — the selection audit's existing command and its JSON verdict (unselected pairs, notes)
- `resolve_test_scope.py --changed <file> --json` — the resolver's existing answer for one changed file
- `measure_selection_size.py`, `python3 scripts/measure_selection_size.py --ref <base> --json` — the existing selection-size instrument
- `<python> scripts/check_gates_bite.py --gate selection-audit --json` — the audit run with the project's interpreter, as the footprint row runs it
- `selection-audit-timeout-seconds` — the audit's declared time bound in the root project file
- `Gate liveness`, `.github/workflows/gate-liveness.yml`, `selection-audit`, `scenarios-whole-suite-audit-gated` — the weekly workflow, its file and the two jobs the audit decides
- `test_every_liveness_check_passes_on_this_change_and_leaves_no_trace`, `test_a_dead_gate_fails_its_own_check_while_the_other_three_still_run_and_pass` — the two audit-gated scenarios
- `.ai-state/TECH_DEBT_LEDGER.md` — the ledger where a gap with a design of its own is filed
- `uv run --project` — how a root test starts the eval pocket, named in the brief
- `eval/pyproject.toml`, `.ai-state/kernel_adoption.yaml`, `.ai-state/eval_ledger/adherence/`, `hooks/_hook_utils.py`, `hooks/_commit_command.py`, `rules/swe/testing-conventions.md` — the files the named gaps are about
- `rules/swe/vcs/git-conventions.md`, `rules/_manifest.yaml`, `rules/_audience.yaml`, `rules/README.md`, `rules/CLAUDE.md`, `hooks/inject_rules.py` — files of the two gap classes the local audit named, and the two prose guides of the rules tree
- `tests/acceptance/test_adherence_eval_stays_out_of_band.py`, `tests/acceptance/test_live_eval_treats_archives_as_byproducts.py`, `tests/acceptance/test_log_archives_stay_out_of_version_control.py`, `tests/acceptance/test_log_health_checks.py` — existing tests the local audit found reading the hook utilities unselected
- `tests/acceptance/test_spawn_kernel_injection.py`, `scripts/test_kernel_run_evidence_parity.py`, `hooks/test_inject_subagent_context_delivery.py`, `tests/acceptance/test_other_channels_carry_the_kernel.py`, `scripts/test_check_kernel_manifest.py`, `scripts/test_pocket_gate_declarations.py` — existing tests that read those files

## Traceability

Rendered from `.ai-work/selection-audit-verdict/traceability.yml` at the close (59 node entries, every one a `def` at `c17d04e5`); `Test(s)` lists the outer-loop nodes first, then the unit tests. REQ-06's Linux half and the two `tests/e2e/test_gate_liveness_run.py` whole-suite nodes are proven by the post-merge `Gate liveness` run.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_whole_copy_leaves_only_the_copying_tests_other_reads_unselected<br>tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_run_whose_only_unselected_reads_are_copies_passes<br>tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_neither_the_test_that_made_a_shared_copy_nor_one_that_reused_it_is_failed_for_it<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_record_on_the_copy_channel_is_parsed_into_its_own_channel<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_trace_without_a_copy_record_has_an_empty_copy_channel<br>scripts/gate_probes/test_selection_copy_rule.py::test_an_unknown_channel_is_still_an_unreadable_record<br>scripts/gate_probes/test_selection_copy_rule.py::test_the_copy_channel_is_not_a_verdict_channel<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_pair_read_directly_as_well_is_audited_and_not_counted_as_set_aside<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_pair_read_by_a_child_as_well_is_audited_and_not_counted_as_set_aside<br>scripts/gate_probes/test_selection_copy_rule.py::test_an_untracked_copied_file_is_not_counted<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_path_keeping_copy_after_listing_the_checkout_is_a_copy_read<br>scripts/gate_probes/tracer/test_copy_channel.py::test_listing_from_another_directory_with_the_c_option_naming_the_root_counts<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_listing_in_one_test_never_classifies_the_next_tests_copy<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_listing_made_in_another_process_arms_nothing<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_traced_run_classifies_listed_copies_and_leaves_other_reads_alone<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copytree_of_the_root_with_an_ignore_filter_is_a_copy_read<br>scripts/gate_probes/tracer/test_copy_channel.py::test_the_inner_recursion_of_a_copytree_of_the_root_does_not_hide_the_outermost | scripts/gate_probes/selection.py::copy_note<br>scripts/gate_probes/selection.py::parse_records<br>scripts/gate_probes/tracer/sitecustomize.py::Tracer | PASS |
| REQ-02 | tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_failing_verdict_notes_the_one_copying_test_and_that_its_copy_is_not_audited<br>tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_passing_verdict_notes_how_many_reads_one_copying_test_made_and_that_they_go_unaudited<br>tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_run_with_no_copy_notes_that_the_copy_rule_set_none_aside<br>scripts/gate_probes/test_selection_copy_rule.py::test_set_aside_reads_and_the_tests_that_made_them_are_counted<br>scripts/gate_probes/test_selection_copy_rule.py::test_the_note_says_what_the_copying_tests_read_later_is_not_audited<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_run_with_no_copy_says_none_was_set_aside_with_zero_reads_by_zero_tests<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_passing_verdict_carries_the_copy_note<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_failing_verdict_carries_the_copy_note_and_judges_the_copying_tests_other_reads<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_verdict_of_a_run_with_no_copy_carries_the_none_note | scripts/gate_probes/selection.py::copy_note<br>scripts/gate_probes/selection.py::parse_records | PASS |
| REQ-03 | tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_copying_one_directory_is_a_read_of_each_file_in_it<br>tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_copying_one_file_is_a_read_of_that_file<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copy_by_name_with_no_listing_is_a_direct_read<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_command_that_does_not_list_the_root_arms_nothing<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copy_to_another_relative_path_is_a_direct_read<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copytree_of_a_directory_below_the_root_is_a_direct_read<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_stale_armed_copy_is_cleared_by_the_next_read_of_anything<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copy_that_does_not_qualify_disarms_an_earlier_one | scripts/gate_probes/tracer/sitecustomize.py::Tracer | PASS |
| REQ-04 | tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_copying_test_still_answers_for_what_it_reads_itself_or_through_a_child<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_failing_verdict_carries_the_copy_note_and_judges_the_copying_tests_other_reads<br>scripts/gate_probes/test_selection_copy_rule.py::test_a_pair_read_directly_as_well_is_audited_and_not_counted_as_set_aside<br>scripts/gate_probes/tracer/test_copy_channel.py::test_both_records_exist_for_a_file_the_test_also_opens_itself<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copytree_of_the_root_leaves_the_tests_other_reads_counted | scripts/gate_probes/selection.py::verdict_pairs<br>scripts/gate_probes/tracer/sitecustomize.py::Tracer | PASS |
| REQ-05 | tests/acceptance/test_copies_of_the_checkout_are_judged_by_their_own_rule.py::test_a_read_no_change_selects_fails_the_verdict_beside_copies_of_the_checkout<br>scripts/gate_probes/tracer/test_copy_channel.py::test_a_copytree_of_the_root_leaves_the_tests_other_reads_counted | scripts/gate_probes/tracer/sitecustomize.py::Tracer | PASS |
| REQ-06 | tests/e2e/test_gate_liveness_run.py::test_every_liveness_check_passes_on_this_change_and_leaves_no_trace<br>tests/e2e/test_gate_liveness_run.py::test_a_dead_gate_fails_its_own_check_while_the_other_three_still_run_and_pass<br>tests/acceptance/test_the_liveness_workflow_expects_no_job_to_be_red.py::test_the_header_expects_no_job_to_be_red | tests/declared-deps.toml::[[dep]] paths=["agents/*.md"] (reader-sized entry)<br>tests/declared-deps.toml::[[dep]] paths=["skills/*/SKILL.md", "skills/*/references/*.md", "skills/*/contexts/*.md"] (reader-sized entry)<br>tests/declared-deps.toml::[[dep]] paths=["skills/eval-praxion/**"] (reader-sized entry)<br>tests/declared-deps.toml::[[dep]] paths=["scripts/_sidecar_git.py", "scripts/_state_repo.py", "scripts/check_squash_safety.py"] (finalize chain, reader-sized entry)<br>tests/declared-deps.toml::[[dep]] paths=["scripts/_budget_scope.py", "scripts/render_claude_md.py", "scripts/praxion_feedback/fingerprint.py"] (hook-imported scripts, reader-sized entry) | PASS locally (AC-03); Linux pending the post-merge `Gate liveness` run (AC-04) |
| REQ-07 | — (none by design: a bound on this change, judged once at the final head) | — | PASS (AC-05 at c17d04e5: 0 misses over 3,910 paths, every pocket) |
| REQ-08 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[eval/pyproject.toml-scripts/test_pocket_gate_declarations.py] | tests/declared-deps.toml::[[dep]] paths=["eval/pyproject.toml"], ["eval/EVAL_PLAN.md"], ["eval/src/praxion_evals/adherence/model.py"] | PASS |
| REQ-09 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[.ai-state/kernel_adoption.yaml-tests/acceptance/test_spawn_kernel_injection.py] | tests/declared-deps.toml::[[dep]] paths=[".ai-state/kernel_adoption.yaml"] (reader-sized entry) | PASS |
| REQ-10 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_any_committed_results_file_selects_the_parity_test_that_reads_them_all | tests/declared-deps.toml::[[dep]] paths=[".ai-state/eval_ledger/adherence/**"] (reader-sized entry) | PASS |
| REQ-11 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_commit_command.py-hooks/test_inject_subagent_context_delivery.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_hook_utils.py-hooks/test_inject_subagent_context_delivery.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_hook_utils.py-tests/acceptance/test_adherence_eval_stays_out_of_band.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_hook_utils.py-tests/acceptance/test_live_eval_treats_archives_as_byproducts.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_hook_utils.py-tests/acceptance/test_log_archives_stay_out_of_version_control.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/_hook_utils.py-tests/acceptance/test_log_health_checks.py] | tests/declared-deps.toml::[[dep]] paths=["hooks/[!t]*", "hooks/_observation_log/*.py"] (reader-sized entry) | PASS |
| REQ-12 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[rules/swe/testing-conventions.md-tests/acceptance/test_other_channels_carry_the_kernel.py] | tests/declared-deps.toml::[[dep]] paths=["rules/_*.yaml", "rules/*/*.md", "rules/*/*/*.md"] (reader-sized entry) | PASS |
| REQ-13 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[rules/swe/vcs/git-conventions.md-scripts/test_check_kernel_manifest.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[rules/_manifest.yaml-scripts/test_check_kernel_manifest.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_any_rule_file_selects_the_kernel_test_that_reads_every_rule | tests/declared-deps.toml::[[dep]] paths=["rules/_*.yaml", "rules/*/*.md", "rules/*/*/*.md"] (reader-sized entry) | PASS |
| REQ-14 | tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_the_file_alone_selects_the_test_that_reads_it[hooks/inject_rules.py-hooks/test_inject_subagent_context_delivery.py]<br>tests/acceptance/test_each_named_gap_selects_the_test_that_reads_its_file.py::test_a_change_to_any_hook_module_selects_the_test_that_delivers_through_every_hook | tests/declared-deps.toml::[[dep]] paths=["hooks/[!t]*", "hooks/_observation_log/*.py"] (reader-sized entry) | PASS |

## Key Decisions

- **[systems-architect] Checkout copies are set aside by source root (`dec-525`)**: a read is `copy` when it is the source-side open of a `shutil.copyfile` inside a `copytree` whose outermost source is the repository root, or of path-keeping copies after the running test listed the checkout with `git ls-files` at the root. **Why**: structural, threshold-free, independent of which test a run credits, and it holds at every copy site in the repository. **Alternatives**: a size or coverage threshold (refuted by the measured sites: the kernel sandbox copies 285 of 3,915 files, the testkit 5 named files, the canary 8 of 9); self-declaring copiers (excuses by test, not by read); widening every change to every copier (fails the selection-size bound by far).
- **[systems-architect] Gaps close by additive, reader-sized declared entries; no resolver code change**: never-narrower then holds by construction (no removal, no `[[inert]]`, no full-suite widening). The proper fix for the hook classes, an edge source for a test that replays the registered hooks, is td-689.
- **[systems-architect] The workflow's verdict comes from `check_gates_bite.py --json-report PATH`**, not `--json | tee`: the default `bash -e` has no pipefail, and the log keeps the text form.
- **[user] FC-01 limit amended from +3 to +5 points (SQ-05, 2026-11-23, "Accept, amend the limit (Recommended)")**: a declared entry holds at every hop, so the 27 hook-replay test files join every change that reaches a module the hooks import; those tests run those modules, so the widening closes a real gap the audit cannot see (import-time reads are not audited). Final reading +4.0 points.
- **[orchestrator] REQ-07 is a bound on this change, compared once at the final head (SQ-04)**: a standing guard over a frozen record of the base's answers would fail every later deliberate narrowing and add about 2.5 minutes to every default root run; the verifier ran it (0 misses over 3,910 paths).
- **[orchestrator] The step loop's root gate bound moves from 1,500 s to 2,500 s (SQ-06, `e6f565b5`)**: at 769 test files the root suite runs 1,595 to 1,617 s on 12 workers, so the checkpoint's whole run was cut off at 99 %. A separate change from the feature, named so at the merge; both frozen guards keep their assertion (the audit's own 4,620 s bound outlasts the loop's).
- **[orchestrator] Rework in place, two rounds, a fresh verifier each**: the branch was unmerged and the rows edited gitignored records a rework worktree cannot see; registered as an objection to the manifest's three worktrees (verifier B6, PASS).
- **[implementation-planner] The tracer is built in two steps split by copy shape** (path-keeping copies after a listing, then a `copytree` of the root), after the judge learns the channel, because a tracer emitting `copy` before the judge parses it fails every audit.

## Declared Limits

- A test that lists the checkout and then copies one named file under its own path has that read set aside (counted in the note).
- A hand-rolled copy loop is not recognised (errs toward auditing); `cp`, `git archive` and `git clone` are untraced, as at the base.
- A symlink copied with `follow_symlinks=False` never opens its source, but the `shutil.copyfile` audit event carries no flag to tell, so the test's next read of that path is counted as a copy: the one case that errs away from auditing.
- A copy whose source is not a path (a file descriptor) keeps `shutil`'s own outcome, but the tracer cannot decode it and records the failure, so the traced audit fails naming it: errs loudly toward red.
- Reads made later from a copy are unaudited, as they were under `dec-420`; now stated, counted and attributed on every run.

## Lessons

- **A gitignored directory does not exist on a fresh runner.** Every local run passed while the job would have exited 2 every week; compose a job's steps in a fresh `git clone --no-local` before calling a workflow change verified. Pinned by `tests/test_gate_liveness_workflow_invariants.py::test_each_report_directory_is_made_before_the_gate_command_writes_into_it`.
- **Write a Spec Question's record at the edit, not at verification.** An orchestrator edit to an outer-loop guard or a footprint row was right both times and still failed AI-3 and AI-4 for want of an answered Spec Question with `Resolved in:`.
- **A sentence moved from `LEARNINGS.md` into a durable record is a claim to re-check against the code.** The decision draft's first A3 wording was copied and wrong on mechanism and outcome; reproducing a finding covers its content too.
- **A declared entry holds at every hop**, so a reader-sized entry for a widely imported module widens far more changes than its own paths; size such entries with the selection-size instrument before committing them.
- **Run `check_shallow_collection.py` with the pocket's own interpreter**: under ambient `python3` pytest rejects `-n` (exit 4), which says nothing about the branch.
- **Carried to the ledger at the close**: td-690 (the judge-seam canaries resolve an unpinned import-linter by environment: 2.11 locked, 2.17 fresh, which rejects the contracts' `description`), td-691 (the probe's mutation reading without its subprocess test file), td-692 (implementers routed around a refused `.github` command instead of returning [BLOCKED]).
