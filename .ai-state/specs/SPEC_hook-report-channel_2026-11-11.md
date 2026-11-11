# Spec: hook-report-channel (the first-session hook's reports reach the user as one systemMessage)

**Task slug**: `hook-report-channel`
**Created**: 2026-11-10
**Pipeline run**: 2026-11-10 to 2026-11-11 (one session: intake, acceptance design with one Spec-Question resume, four plan steps plus one rework step, verification and a narrow re-verification)
**Archived**: 2026-11-11 (pre-merge, on branch `fix/hook-report-channel`; merged to main at `13cd3c5f`, which promoted the ADR draft to dec-501)
**Status**: completed -- final verdict PASS WITH FINDINGS (the first run FAILed once, on an acceptance-independence audit: the designer read git history; accepted by the orchestrator as a recorded deviation because every oracle traces to the spec, procedure gap filed as td-621)
**Tier**: Standard (the calibration verdict reads `correct`: five requirements across two production modules and a split of a 2,153-line test module were too much for Lightweight, and nothing needed Full)
**Complexity**: medium (5 requirements, 2 production modules, 9 hook files and 3 outer-loop files changed)
**Base commit**: `e83fc846` · acceptance design `6adcfd60` · split `259fa10e` · first production commit `12d55689` · `433799b3` · rework `7be59770`
**Pipeline branch**: `fix/hook-report-channel`
**ADRs**: `dec-501` (category: behavioral -- every first-session report goes to the user as one systemMessage per run; it extends dec-500 from the floor notice to every report; promoted at merge from `dec-draft-09b8d460`)
**Related spec**: `SPEC_install-refresh_2026-11-10.md`. Its REQ-14 was amended through its SQ-06, and its frozen refresh acceptance test gained two channel tests.

## Feature Summary

Claude Code shows no one the standard error of a hook that exits 0. So the first-session hook's install and refresh reports (`[Praxion] Auto-install complete.`, and the failure line naming `/praxion-complete-install`) reached nobody, and they would also have collided with the interpreter-floor notice dec-500 writes to stdout.

Now:
- Every report a run produces is gathered in firing order and written once, as the `systemMessage` of the single JSON object that is the hook's whole standard output.
- A run with nothing to report writes nothing.
- No report goes to standard error. The first-install confirmation prompt, td-620, still does.
- A closed standard output still ends the hook with status 0.
- In the same change, the 2,153-line test module was split by a pure move (td-611).

## What Was Built

- **`hooks/auto_complete_install.py`:**
  - `main()` owns the gathered report and is the sole stdout writer (`_write_system_message`).
  - A failing write is absorbed, and fd 1 is pointed at `os.devnull`, so the interpreter's shutdown flush cannot fail.
  - Lines gathered before an unexpected exception are still written.
  - `_run(report)` appends the floor notice (`_shortfall_line`), then the update or install path's lines.
- **`hooks/_install_update.py`:**
  - The line builders `_install_complete_line` and `_incomplete_line` return lines.
  - `_run_update_path` and `_fresh_instructions_setup` hand theirs back. The third report site is the completion line of an instructions set-up inside the update path.
- **Tests:**
  - New `hooks/test_install_reports.py` covers one object with one field, silence, firing order, a notice surviving a raise, an absorbed write, and exit 0 with a closed reader.
  - The split into `test_auto_complete_install.py`, `test_install_cold_path.py`, `test_install_surfaces.py` and `test_install_carry_forward.py` collects the same 194 nodes.
  - New outer-loop scenarios are in `tests/acceptance/test_hook_reports_reach_the_user.py` (driver `tests/acceptance/drivers/hook_reports.py`).

## Requirements

### Observable Surface

- `hooks/auto_complete_install.py` — the plugin's first-session hook, registered for `SessionStart`; a test stands in for a session start by running it with `HOME` and `CLAUDE_PLUGIN_ROOT` set, the payload on standard input, as Claude Code does
- `SessionStart` — the Claude Code hook event the hook runs on
- `HOME` — the user's home directory
- `CLAUDE_PLUGIN_ROOT` — the variable Claude Code sets to the plugin version a hook runs from
- `systemMessage` — the JSON output field Claude Code shows the user, per its hooks reference
- `[Praxion]` — the prefix every report carries
- `[Praxion] Auto-install complete.` — the existing completion line of a first install
- `/praxion-complete-install` — the existing, documented hand path that completes an install
- `python3` — the interpreter on the user's PATH that every hook runs under
- `PRAXION_DISABLE_AUTO_COMPLETE` — the existing opt-out; set to 1, the hook does nothing
- `~/.claude/plugins/installed_plugins.json` — Claude Code's plugin registry under `HOME`; the hook falls back to the install path it lists for the praxion plugin when `CLAUDE_PLUGIN_ROOT` names no directory

### REQ-01: A failed refresh tells the user how to finish

**When** the first session of a new plugin version runs the update refresh
**and** any step of the refresh fails, for example a directory is not writable or a file cannot be read
**the system** writes, as its whole standard output, one JSON object whose `systemMessage` carries one line that names the kind of failure and `/praxion-complete-install` as the way to finish the refresh by hand, and writes that line nowhere else
**so that** the user, who sees a `systemMessage` and never sees a hook's standard error on a success exit, learns how to finish it.

### REQ-02: A failed first install tells the user how to finish

**When** a first install runs in a session start
**and** any step of it fails
**the system** reports the failure the same way: one line naming the kind of failure and `/praxion-complete-install`, carried by the `systemMessage` of the one JSON object that is its whole standard output, and written nowhere else
**so that** a user whose install did not finish learns it and how to complete it.

### REQ-03: A completed first install says so where the user sees it

**When** a first install completes in a session start
**the system** carries `[Praxion] Auto-install complete.` in the `systemMessage` of the one JSON object that is its whole standard output, and writes that line nowhere else
**so that** the user knows the plugin finished setting itself up.

### REQ-04: Reports from one session start arrive as one message

**When** more than one report fires in the same session start, for example the notice that `python3` is below the hooks' floor together with an install or refresh report
**the system** writes exactly one JSON object as its whole standard output, whose `systemMessage` carries every report on its own line in the order they fired, each beginning with `[Praxion]`
**so that** Claude Code reads the output as one message to show the user, never as context text for Claude and never as output it fails to parse.

### REQ-05: Nothing to report prints nothing

**When** a session start has nothing to report: an update refresh that finishes, a later session of a version whose first session already ran, a run with `PRAXION_DISABLE_AUTO_COMPLETE` set to 1, or a run with no resolvable plugin root (`CLAUDE_PLUGIN_ROOT` absent or naming no existing directory, and `~/.claude/plugins/installed_plugins.json` absent or listing no existing install path for the praxion plugin; SQ-01)
**the system** writes nothing to standard output and nothing to standard error
**so that** a quiet session start adds nothing to the user's screen or to Claude's context.

## Spec Question Answers

### SQ-01: Which session start has "no resolvable plugin root"?

- **Raised by:** acceptance design. Without `CLAUDE_PLUGIN_ROOT`, the base hook still found its plugin through the registry the test machine writes.
- **Answer:** REQ-05's When clause now names it: `CLAUDE_PLUGIN_ROOT` absent or naming no existing directory, and `~/.claude/plugins/installed_plugins.json` absent or listing no existing install path for the praxion plugin. The registry joined the Observable Surface, and the spec digest moved from `40efee691f54` to `33cbafa499eb`. Two guard cases were added.
- **Resolved in:** `6adcfd60`.

### SQ-06 (raised on install-refresh, carried here): On which channel does a failed refresh's line reach the user?

Answered in `SPEC_install-refresh_2026-11-10.md` § SQ-06, resolved in `6adcfd60`. The line rides the one `systemMessage` and is written nowhere else. The frozen refresh test gained two channel tests, and no existing assertion changed.

## Footprint Readings

No footprint criterion. The only footprint row, `hook-latency`, is declared under Footprints Not Measured: no registry instrument exists, and the added work is one JSON encoding per first session of a version.

Health readings:
- The always-loaded reading stays 19,918 tokens.
- The Codex and Cursor exports are byte-identical from base to head (172 files, roots normalised).
- Every hook unit-test module this pipeline touched is at or under 800 lines.

## Traceability

Rendered from the reconciled `traceability.yml` (single file, no fragments), with implementation names as of the archive head. Every node passed in the verifier's runs, scoped at 401/0 and step-5 Check at 300/0. The full root suite passed 18,062 with 0 failed.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01: A failed refresh tells the user how to finish | `hooks/test_install_update.py::TestUpdatePath::test_a_failure_prints_one_line_with_the_exception_type_only`<br>`hooks/test_install_update.py::TestUpdatePath::test_the_first_of_several_failures_is_the_one_reported`<br>`hooks/test_install_update.py::TestUpdatePath::test_an_unwritable_marker_after_a_failure_still_reports_the_failure`<br>`hooks/test_install_update.py::TestUpdatePath::test_a_fully_successful_run_prints_nothing`<br>`hooks/test_install_update.py::TestInstructionStates::test_a_failed_setup_is_reported_once_and_the_marker_is_still_written`<br>`hooks/test_install_update.py::TestInstructionSetupPrompt::test_a_refusal_is_no_failure_and_the_rules_and_scripts_are_still_refreshed`<br>`hooks/test_install_carry_forward.py::TestInstructionsCarryForward::test_an_unrecoverable_render_is_reported_in_one_line_naming_its_type`<br>`tests/acceptance/test_plugin_update_fails_open_and_quietly.py::test_a_failed_refresh_reports_itself_in_the_message_claude_code_shows_the_user`<br>`tests/acceptance/test_plugin_update_fails_open_and_quietly.py::test_a_failed_refresh_writes_its_report_nowhere_but_that_message` | `hooks/_install_update.py::_incomplete_line`<br>`hooks/_install_update.py::_run_update_path`<br>`hooks/auto_complete_install.py::_run` | PASS |
| REQ-02: A failed first install tells the user how to finish | `hooks/test_install_reports.py::TestFirstInstallReports::test_a_failed_first_install_reaches_the_message_and_not_standard_error`<br>`hooks/test_install_surfaces.py::TestPerformInstall::test_a_failed_install_still_records_completion`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_failed_first_install_reports_one_line_naming_the_command_to_finish_by_hand`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_failed_first_install_writes_its_report_nowhere_but_the_message`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_failed_first_install_report_carries_no_personal_value_or_exception_text`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_failed_first_install_ends_with_a_success_status` | `hooks/_install_update.py::_incomplete_line`<br>`hooks/auto_complete_install.py::_perform_install`<br>`hooks/auto_complete_install.py::_run` | PASS |
| REQ-03: A completed first install says so where the user sees it | `hooks/test_install_reports.py::TestFirstInstallReports::test_a_completed_first_install_reaches_the_message_and_not_standard_error`<br>`hooks/test_install_reports.py::TestUpdateReports::test_the_completion_line_of_a_dangling_link_set_up_again_is_gathered`<br>`hooks/test_install_update.py::TestInstructionSetupPrompt::test_the_prompt_shows_on_the_terminal_and_nowhere_else`<br>`hooks/test_install_cold_path.py::TestRealInstallLayout::test_a_first_session_links_the_contract_and_renders_claude_md`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_completed_first_install_says_so_in_its_message`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_completed_first_install_writes_its_completion_line_nowhere_but_the_message`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_completed_first_install_message_carries_no_personal_value` | `hooks/_install_update.py::_install_complete_line`<br>`hooks/_install_update.py::_fresh_instructions_setup`<br>`hooks/_install_update.py::_run_update_path`<br>`hooks/auto_complete_install.py::_perform_install`<br>`hooks/auto_complete_install.py::_run` | PASS |
| REQ-04: Reports from one session start arrive as one message | `hooks/test_install_reports.py::TestOneSystemMessage::test_the_whole_of_standard_output_is_one_object_with_one_field`<br>`hooks/test_install_reports.py::TestOneSystemMessage::test_a_notice_gathered_before_an_unexpected_failure_is_still_emitted`<br>`hooks/test_install_reports.py::TestOneSystemMessage::test_a_failing_write_is_absorbed`<br>`hooks/test__interpreter_floor.py::TestFirstSessionNotice::test_a_shortfall_reaches_the_user_as_a_system_message`<br>`hooks/test_install_reports.py::TestUpdateReports::test_a_failed_refresh_after_a_floor_notice_gives_two_lines_notice_first`<br>`hooks/test_install_reports.py::TestAClosedStandardOutput::test_the_hook_exits_zero_when_the_reader_of_standard_output_has_gone`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_lone_floor_notice_arrives_as_the_one_message`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_floor_notice_and_a_failed_refresh_share_one_message_each_on_its_own_line`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_floor_notice_and_a_failed_refresh_write_neither_report_to_standard_error`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_floor_notice_and_a_completed_install_share_one_message_each_on_its_own_line`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_floor_notice_and_a_completed_install_write_neither_report_to_standard_error` | `hooks/auto_complete_install.py::main`<br>`hooks/auto_complete_install.py::_point_standard_output_at_devnull`<br>`hooks/auto_complete_install.py::_run`<br>`hooks/auto_complete_install.py::_shortfall_line`<br>`hooks/_install_update.py::_run_update_path`<br>`hooks/auto_complete_install.py::_perform_install` | PASS |
| REQ-05: Nothing to report prints nothing | `hooks/test_install_reports.py::TestNothingToReport::test_a_run_with_nothing_to_report_writes_to_neither_stream`<br>`hooks/test__interpreter_floor.py::TestFirstSessionNotice::test_an_interpreter_that_meets_the_floor_prints_nothing`<br>`hooks/test__interpreter_floor.py::TestFirstSessionNotice::test_a_session_after_the_marker_is_not_told_again`<br>`tests/acceptance/test_hook_reports_reach_the_user.py::test_a_session_start_with_nothing_to_report_writes_nothing_to_either_stream` | `hooks/auto_complete_install.py::main`<br>`hooks/auto_complete_install.py::_run`<br>`hooks/auto_complete_install.py::_shortfall_line` | PASS |

## Key Decisions

- **The channel:** `systemMessage` only, one object per run, no stderr copy, no `additionalContext`. See dec-501.
  - **Dissent:** Claude never learns of a failure.
  - **Reversal trigger:** an interactive session that does not display a plugin SessionStart `systemMessage` (unproven live, 7/10).
- **Split first, as a pure move:**
  - Shared fixtures stay in the original module; siblings import them by name, which is the repository's pattern, since `hooks/` has no conftest.
  - The channel change went in two implementer steps (the sole writer, then the reports), so the hook worked after each commit.
- **Refresh-step return values become user lines, with no type guard.** The verifier's judgement: the step list is private, and two real-step tests pin the exact gathered lines. A future refresh step must return `None` or a `[Praxion]` line.
- **Out of scope by decision:**
  - td-620: the first-install confirmation prompt is unseen and unanswerable in a hook.
  - td-623: the render module's own unresolved-placeholder warning on stderr.
- **Process findings filed:**
  - td-621: git-history reads are unclassified in the acceptance-design inputs, and an ADR draft was committed in the Base commit.
  - td-622: the step schema silently drops a `- [x] [COMPLETE] Step N` line.
