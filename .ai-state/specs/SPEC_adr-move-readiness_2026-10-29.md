# Spec: adr-move-readiness (the move instrument measures the adr-conventions move: its lean arm delivers the path-scoped rule, a kit of managed tasks sets the rule's trap, and two governed checks grade the end state)

**Task slug**: `adr-move-readiness`
**Feature**: The move instrument (`praxion-evals-adherence --move`, archived spec `SPEC_main-session-adherence_2026-10-28.md`) gains its second runnable move, `adr-conventions`. The lean arm keeps the moved rule's manifest row, path-scoped to the decision directory, beside the resident kernel (`td-518` part 1, a new `manifest_row_scoped` derive); two build-time refusals stop an arm whose path-matched rule would never load and a declared phrase its section does not hold (`td-518` part 2); a kit of five managed fixtures in the older numbered habit with requests that ask for a decision record without stating the rule; two governed checks graded on end state, decision draft placement and decision category; registration so the dry run prices 56 sessions. No rule moved and no session ran.
**Tier**: Standard at intake, re-tiered to Full at the spec checkpoint (18-23 files across two nearly disjoint lanes; the brief's own trigger fired). Budget 32 spawns, charged 17 per the calibration row; no further re-tier.
**Pipeline branch**: `adr-move-readiness` (from `main-session-adherence` at `3dfb5c45`, itself unmerged at the start)
**Start date**: 2026-10-29
**End date**: 2026-10-29
**Archived**: 2026-10-29 (pre-merge, on branch adr-move-readiness; merged to main with --no-ff after `main-session-adherence`)
**Status**: completed -- delta verdict PASS WITH FINDINGS at `ee2d41c4`, ruled 2026-10-29: the first pass read FAIL (one procedural FAIL, #fail-1, disclosed out-of-class acceptance reads; ten WARNs, the important one a record discovery that counted `calibration_log.md` and tool caches as decision records); one in-place rework round resolved every WARN but the advisory #warn-10; #fail-1 was admitted by the orchestrator under the user's delegation (no oracle traced to the reads); the creating-write probe owed by `td-518` remains a strict xfail until a probe session records it
**ADRs**: none. No decision passes the `architectural` test (no component added or removed, no published contract changed); the decisions below are recorded with their categories instead. `dec-477` and `dec-478` (move results directory, move subject subpackage) are the governing records.
**Evidence base**: the spec digest `sha256:5d985898696d` of `SPEC_EXTRACT.md`; the branch's commits (acceptance design `dbd7b9a1`, spec questions `7394f73b` and `017bd3d5`, design state `3e7fb53e`, first production commit `96736095`, verified head `ee2d41c4`, state `483eb181`); the suites in the matrix below (unit suites `eval/tests/test_moves_*.py`, outer-loop scenarios `tests/acceptance/test_move_*.py` designed from the extract alone); the completion row in `.ai-state/calibration_log.md` dated 2026-10-29; ledger rows `td-518` and `td-521` to `td-524`; the verifier's `VERIFICATION_REPORT.md`, `CHECKPOINT_DIGEST.md` and `LEARNINGS.md` (under `.ai-work/`, deleted at cleanup, their substance carried below).

## Feature Summary

The first move (`git-conventions`) proved the instrument could build arms, grade end states and price a run. The second, `adr-conventions`, could not run: its lean arm repointed or dropped the moved rule's manifest row, and the installer links manifest rows only, so the path-scoped rule never loaded in a real session; its declared phrase "drafts directory" was not in the rule; and it had no task kit and no grader. ADR conventions are Praxion-specific (fragment path and filename schema, `dec-draft-<hash>` ids, the category vocabulary, the Disconfirmation duty), so a model without the rule cannot know them and the floor should fail clearly.

The arm fix is a pure derive, `manifest_row_scoped`: the lean manifest keeps the moved rule's row (`load: path_scoped`, `paths:` from the declared delivery) and adds the kernel's row right after it. Two refusals run at arm build, before any session: the lean copy's own linker run is observed, and a path-matched rule it would not link is refused naming the file; a declared check phrase must lie in its check's named section (case-insensitive, one predicate shared with the trigger reader), so a phrase the rule does not hold is refused naming the check, phrase, section and rule.

The kit builds five managed fixtures through a shared `moves/fixture_project.py` (the git kit's output byte-identical): each on a named non-default branch with a commit of its own, a decision directory holding numbered records in the older habit (`NNN-slug.md`, `dec-NNN`, no category, no Disconfirmation) and a `DECISIONS_INDEX.md`, no drafts directory, and the shipped `CLAUDE.md` blocks except the hackathon and sidecar ones. Requests name a "decision record" or "ADR", describe the decision, its options and its reason, and never hold a rule line, a declared phrase, a category value or a command. The checks: **decision draft placement** (File Format: directly under `.ai-state/decisions/drafts/`, the `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` name with the branch segment from an admissible branch, a `dec-draft-<8 hex>` id; four disjoint parts) and **decision category** (What makes a decision architectural: one of the four values, and on `architectural` a Disconfirmation section with its three items; three disjoint parts). Whether a category is the right one is judgment and is not graded. A session that leaves no record reads nothing to grade.

The verifier's most consequential finding was the record definition: the first grader counted any new Markdown file, including the calibration log every session is told to write by the always-loaded rules, so a correct session would have failed both checks in every arm. The rework defined a decision record as new Markdown under `.ai-state/decisions/` or in the visible tree, outside dot-directories and nested repositories, with fence-aware headings and an upper-case `.MD` read as a malformed name; the admissible branches became the fixture's branch plus any the session created.

Shape of the delivery: 21 plan steps; three driver-binding steps before any production step; 15 driven steps through the step loop (25 of 33 iterations) and 6 outside it; four forced light reviews (steps 12, 13, 18 with two revisions); one in-place rework round (Steps 18-21) after the first verification.

## Deferred at Close

- **`td-518`'s remaining part: the creating-write probe record.** The scenario "a path-matched load on a creating write reads as arrived after execution" (`tests/acceptance/test_move_session_take.py`) stays a strict xfail bounded to its unbound reason until one short probe session, billed to the subscription on the user's go, records a lean session writing under `.ai-state/decisions/drafts/` and the record is frozen under `tests/fixtures/main_session_probes/` with its Claude Code version. The arm fix and both refusals are done; `td-518` stays open for this part.
- **Load-bearing assumption A3, unverified until that probe**: a `paths:`-scoped rule loads on reading an existing matching file and only after the first write of a new one. The end-state grade accepts a repair either way.

Also recorded at close:

- **#fail-1 admitted.** The acceptance designer disclosed two reads outside its allowed classes (a grep of the installer for the manifest, and a printout of the kit declaration's checks while diagnosing a passing phrase test). The verifier traced no oracle to either; the user delegated the ruling and the orchestrator admitted them (disposition in `ACCEPTANCE_TESTS.md`).
- **The floor caveat the floor run will measure.** The arm copy carries skill references (`software-planning`'s `adr-authoring-protocols.md`) that hold the full ADR protocol; a floor session that loads such a skill can pass. A floor that fails each check at least once is still citable; a floor that does not is the finding.
- **Sequencing.** Every commit changes every arm's whole-tree digest, so a floor run is citable only by a paired run on the same tree; both moves' floor and paired runs launch from one frozen checkout.
- **Open ledger rows, none blocking the merge**: `td-521` (trigger history under a shell move), `td-522` (the mutation sensor reads `not-flat-layout` for `eval/src`, so the move graders carry no mutation evidence), `td-523` (`DEFAULT_BRANCH` restated across modules; the heading helpers live in `declaration.py`), `td-524` (mypy target for PEP 695 syntax).

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (digest `sha256:5d985898696d`, the rework amendments of REQ-05 to REQ-08 and the vocabulary included). REQ ids are pipeline-local and appear nowhere in code, tests or docstrings.

Complexity: large -- eleven requirements across the arm build, the declaration reader, a new task kit with its fixtures, two governed checks, the dry run and the documentation. Brownfield: the archived main-session-adherence spec of 2026-10-28 is the baseline; this spec completes its deferred second move (that spec's REQ-13, AC-04 path-matched clause and AC-13 trigger-record clause, all held by `td-518`) and reuses its requirements by reference without restating them -- the stop, continuation, close, take proof, trigger record, verdict, allowance, coverage, floor citation and host reach read as they do today. Requirement ids here are pipeline-local.

Vocabulary: the archived spec's terms apply unchanged (a **move** and its **full**, **lean** and **floor** arms; a **governed check** and **governed action**; a **channel**; the **trigger record**; a **floor run**; **nothing to grade**, the end state a pair reads as failing and a floor counts apart). New here:

- A rule file's **section** is one of its headings and every line after it up to the next heading of the same or a higher level, sub-headings included.
- A **decision record** is a Markdown file -- one whose name ends in a dot and md, in any letter case -- that a session leaves in its fixture project and the fixture did not hold, and that lies either under `.ai-state/decisions/`, or outside every directory whose name begins with a dot and outside every nested repository or worktree (a directory below the project root holding its own git metadata). So the state directory's other files (a calibration log, for one), the ephemeral pipeline directory `.ai-work/`, tool caches and worktree copies are never records, while a record written elsewhere in the project, under a documentation directory for one, is.
- A **heading** of a Markdown file is a line opening with one to six number signs and a space that lies outside every fenced code block.
- A **draft fragment** is a decision record directly under `.ai-state/decisions/drafts/` named by `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`.
- A fragment's **admissible branches** are the branch its fixture was built on and every local branch the end state holds that the fixture did not, that is, a branch the session created; the rule names the fragment by the branch it was written on, and the end state cannot tell which of these that was.
- A **branch segment** of a branch name is that name written as the authoring protocol the moved rule links for the full construction of a fragment name writes it: lowercased, each run of characters other than lowercase letters, digits and hyphens replaced by one hyphen, leading and trailing hyphens trimmed, and cut to 40 characters; a slash in a branch name is therefore written as a hyphen.
- A decision's **sort** is the answer the moved rule's test gives it: a decision that adds, removes, splits or merges a component, or moves a responsibility between components, is architectural; a change inside one component, however consequential, is not.
- The **older habit** is the way a project's existing decision records are written before the rule: each named by a record number and a slug at the top of `.ai-state/decisions/`, carrying a numbered id `dec-NNN`, with no `category` and no disconfirmation section.

### Observable Surface

- `praxion-evals-adherence` -- the existing process-adherence eval entry
- `--move`, `--dry-run`, `--run` and `--declaration` -- existing options of the entry: name a move, price both runs without a launch, name the run kind, and use a declaration file in place of the kit's own
- `adr-conventions` and `git-conventions` -- the second and first moves
- `rules/swe/adr-conventions.md` -- the moved rule; its File Format section and its section on what makes a decision architectural are the two the checks grade
- `rules/_manifest.yaml` -- the rule delivery manifest the installer links from
- `paths:` -- the rule-file frontmatter key that scopes a rule to matching paths
- `.ai-state/decisions/` and `.ai-state/decisions/drafts/` -- a managed project's decision directory and draft directory
- `.ai-work/` -- the ephemeral pipeline directory of a project
- `DECISIONS_INDEX.md` -- the decision index a managed project keeps in its decision directory
- `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` -- the fragment filename schema the moved rule states
- `dec-draft-<hash>` and `dec-NNN` -- the draft id form and the finalized id form the moved rule states
- `category`, `architectural`, `behavioral`, `implementation` and `configuration` -- the frontmatter field and the four values the moved rule names
- `CLAUDE.md` -- a project instruction file
- `eval/EVAL_PLAN.md` -- the eval plan
- `td-518` -- the tech-debt ledger row this change resolves

### REQ-01: The lean arm of a path-matched move links its rule beside the resident kernel

**When** the arms of a move are built whose lean arm declares a path-matched delivery of the moved rule, with or without a resident kernel
**the system** leaves the lean copy's rule delivery manifest listing the moved rule for linking under its own entry, scoped to the delivery's paths, and, when a resident kernel is declared, the kernel for linking under an entry of its own loaded at session start; so that the lean copy's own installer links both into a session's home, the observed session start holds the kernel and no other line of the moved rule, and the linked moved rule carries a `paths:` scope naming every declared glob; changes no other entry of the manifest; builds the full and floor arms as it does today; and still refuses the arm when a host without hooks would reach less of the moved rule than it reaches today
**so that** a lean session can receive the moved rule when it touches a decision record, which today it never can (`td-518`).

### REQ-02: An arm whose path-matched rule would never load is refused at build

**When** a move's arms are built
**and** the lean copy's own installer would not link a rule file that a declared path-matched delivery names
**the system** refuses the arms before any session is launched and before any results file is written, naming the rule file
**so that** a move whose point-of-use text can never arrive fails offline, not in a paid session.

### REQ-03: A declared phrase is text its section holds

**When** a move's declaration is read against a checkout, as it is when the move's arms are built and when a run or a dry run of the move is prepared
**and** a governed check declares a phrase that the section it names, in the rule file it names, does not hold, compared ignoring letter case as the trigger record compares
**the system** refuses the declaration, naming the check, the phrase, the section and the rule file; and accepts every phrase the `git-conventions` move declares today
**so that** an arrival never reads as never merely because a phrase was mistyped or taken from text the check does not govern.

### REQ-04: The adr-conventions move has a task kit, and its dry run prices it

**When** the operator names the `adr-conventions` move with `--dry-run`
**the system** launches nothing and spends nothing, leaves the checkout as it was, and prints, for the floor run and the paired run, every session it would launch (task, fixture kind, wording variant, arm), the session count per task and the totals: 56 sessions at the defaults, 48 paired over 24 tasks and 8 floor, every task's fixture kind managed; and no longer refuses the move for want of a task kit
**so that** the move's first comparison is priced, session by session, before the user's go.

### REQ-05: Each task asks a main session to record a decision, never stating the rule

**When** the `adr-conventions` move's task list is drawn
**the system** draws at least the declared target plus slack tasks (24 at the defaults), each distinct in fixture, wording or both, every one from a managed fixture, the run's report naming that restriction; each task's request names the record it asks for in the words decision record or ADR, asks the session to write that record, names no index, log or history as the place to record it, describes the decision -- what was decided, the options weighed and why -- and holds no line of the moved rule, no declared phrase of either governed check, none of the four `category` values and no command, a command being any backtick, a dollar sign followed by a space, a slash that opens a word and is followed by a letter, or one of the program names git, python, uv, bash, pytest, npm or make, or a name beginning with praxion and a hyphen, standing as a whole word and followed by a space and an argument; and across the kit's fixtures, decisions of both sorts are asked for, at least one fixture of each sort
**so that** a task never hands the session the rule it measures, and the rule's disconfirmation duty, which falls on architectural records, is exercised as often as the category vocabulary.

### REQ-06: Each fixture sets the trap the rule exists for

**When** a task's fixture project is built
**the system** builds a managed project -- a project state directory and a project `CLAUDE.md` carrying every shipped block a project carries when it is outside hackathon mode and keeps its state in the repository, which is every shipped block but the hackathon block and the sidecar-placement block -- under a git identity whose user name and email a session can read, checked out on a named branch that is neither "main" nor "master", the two names a project with no remote treats as its default, carrying at least one commit of its own that the default branch does not hold -- the work the decision concerns --, whose decision directory already holds at least two decision records in the older habit and a `DECISIONS_INDEX.md` listing them, holds no draft directory, and holds no file anywhere that carries a line of the moved rule or a declared phrase of either governed check; in which a decision record scripted with no model and written as the moved rule says grades passed on both governed checks
**so that** a session without the rule, copying the project's habit, can be seen to number its own record at the top of the decision directory, while a session with the rule records a draft fragment.

### REQ-07: Decision draft placement is graded on the end state

**When** a session of the `adr-conventions` move ends
**the system** grades the governed check "decision draft placement", tied to the moved rule's File Format section, over every decision record the session left: passed when every record lies directly under `.ai-state/decisions/drafts/`, is named by `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` with a valid calendar date and time, a non-empty user, the branch segment of one of its admissible branches as its branch, a non-empty slug and the extension md in lower case, and carries a frontmatter id of the form `dec-draft-<hash>` whose hash is eight hexadecimal characters; failed otherwise, naming once each part that fails, the parts being disjoint so that any one can fail alone: a record not directly under the draft directory; a file name that is neither the fragment schema nor a record number and slug (a malformed fragment name); an id that is neither the draft form nor the numbered form, or no id (a malformed draft id); a file name made of a record number and a slug, or an id of the form `dec-NNN` (a record that numbers itself); and nothing to grade, with the reason "no decision record written", when the session left no decision record; judging only what the session left, never what it said, so a record moved or renamed into conformance before the session ends passes
**so that** the check sees exactly what the rule's file-format section governs and a model without the rule cannot know.

### REQ-08: Decision category is graded on the end state

**When** a session of the `adr-conventions` move ends
**the system** grades the governed check "decision category", tied to the moved rule's section on what makes a decision architectural, over the same decision records: passed when every record's frontmatter carries a `category` whose value is one of `architectural`, `behavioral`, `implementation` or `configuration`, and every record whose `category` is `architectural` carries a section headed Disconfirmation, under the meaning of a heading above, that names a falsifier, a steelmanned runner-up and a reversal trigger, all compared ignoring letter case; failed otherwise, naming once each part that fails, any one able to fail alone: no category; a category outside those four values (an unknown category); an architectural record with no disconfirmation; and nothing to grade, with the same reason, when the session left no decision record; whether the value is the one the rule's test would give the decision is not graded
**so that** the check sees the rule's category vocabulary and its disconfirmation duty, which no general habit supplies, without grading a judgment.

### REQ-09: Both checks are shown to fail and to pass before any session

**When** the governed checks of the `adr-conventions` move are exercised with no session
**the system** grades a planted end state that follows the rule, for a decision of each sort, as passed on both checks; a planted end state violating exactly one part as failed naming that part alone, for every part of both checks; a planted end state with no decision record as nothing to grade on both; and a planted end state in the older habit -- a record numbered after the existing ones and written like them -- as failed on both
**so that** each check is shown able to see what the rule's absence produces and to pass what the rule asks, before anything is spent.

### REQ-10: The first move is unchanged

**When** the `git-conventions` move is built, drawn, priced by a dry run or graded after this change
**the system** builds the same arm changes, draws the same tasks for the same seed, prints the same dry run and grades every end state as it does today
**so that** making the second move measurable costs the first nothing.

### REQ-11: The eval plan states what the move instrument now does

**When** a reader opens the move section of `eval/EVAL_PLAN.md`
**the system** states that both declared moves have task kits and can run; names the two governed checks of the `adr-conventions` move with the rule section each grades; states that its lean arm links the moved rule, scoped to the decision directory, beside its resident kernel; names the two build-time refusals; gives the move's dry-run total; no longer says the lean arm cannot deliver the rule; and still says that no paid run of the move has happened and that the path-matched trigger reading over a real recorded session awaits a probe the user approves
**so that** the documentation claims what the instrument does and nothing more.

## Acceptance Criteria at Close

Status is the verifier's delta re-verification at `ee2d41c4`.

| Criterion | Requirements | Status | Evidence at close |
|---|---|---|---|
| AC-01 | REQ-01 | PASS | The lean copy's installer links the moved rule (scoped to the decision directory) and the kernel; session start holds only the kernel line; full and floor as before; Cursor and Codex reach kept. |
| AC-02 | REQ-02 | PASS | A removed or repointed entry is refused naming the rule; no launch, no results file. |
| AC-03 | REQ-03 | PASS | An unheld phrase is refused naming check, phrase, section and rule; a case-only difference is accepted; a phrase held only outside its section is refused; the git declaration and every adr phrase are held. |
| AC-04 | REQ-04 | PASS | The dry run prints 56 sessions (48 paired over 24 tasks, 8 floor), all managed; the checkout is unchanged; the no-kit refusal is gone. |
| AC-05 | REQ-05 | PASS (mechanical); WARN (judged) | At least 24 distinct tasks; each names a decision record or ADR and asks for it; no rule line, phrase, category value or command; both sorts present. Judged: read floor rates by wording. |
| AC-06 | REQ-06 | PASS | Managed fixtures on a non-default branch with a commit of their own, at least two older-habit records listed, no drafts directory, no rule line or phrase, the shipped blocks but hackathon and sidecar; a scripted record passes both checks. |
| AC-07 | REQ-07 | PASS | Placement: conforming passes, each part fails alone, nothing to grade with "no decision record written", moved-into-conformance passes, a created branch passes, dot-directory and nested-worktree Markdown is no record, `docs/` Markdown is a record, `.MD` is a malformed name. |
| AC-08 | REQ-08 | PASS | Category: each sort passes, each part fails alone, an off-test value passes, a fenced `#` line does not end Disconfirmation, nothing to grade. |
| AC-09 | REQ-09 | PASS | The older habit fails both checks; a rule-following end state passes both. |
| AC-10 | REQ-10 | PASS | Every existing git-conventions scenario passes unchanged; the git dry run is byte-identical at base and head. |
| AC-11 | REQ-11 | PASS | `eval/EVAL_PLAN.md` states both moves runnable, both checks with their sections, the scoped link, both refusals and the total, and still says no paid run has happened. |
| Non-goal | (guards) | PASS | No paid session; the creating-write scenario stays a strict xfail. |
| Health Guards | (guards) | PASS | Eval pocket 3,604 passed; root move modules 257 passed plus 1 strict xfail; FC-01 23,652 unchanged; Codex and Cursor exports identical; zero spend. |

## Traceability Matrix

Rendered from `traceability.yml` at archival. `Status` is the verifier's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 10 test(s) -- `eval/tests/test_moves_arms.py` (test_the_kept_row_is_path_scoped_to_the_deliverys_globs_with_the_written_rules_chars, test_the_kernel_row_follows_the_kept_row_and_is_always_on, test_no_other_manifest_entry_changes, test_a_scoped_row_needs_exactly_one_path_matched_delivery_of_the_moved_rule, test_a_scoped_row_for_a_rule_that_is_not_symlinked_is_refused_naming_the_manifest); `eval/tests/test_moves_kits.py` (test_the_adr_kits_lean_arm_scopes_the_manifest_row_rather_than_removing_it, test_the_adr_kits_rule_copy_is_path_scoped_and_keeps_its_paths_and_codex_override); `eval/tests/test_moves_declaration.py` (test_a_scoped_manifest_row_derive_parses_to_its_value); `eval/tests/test_moves_observe.py` (test_the_linked_set_holds_the_rules_the_installer_linked_path_scoped_ones_included, test_a_hook_delivered_rule_is_not_in_the_linked_set) | 9 test(s) -- `tests/acceptance/test_move_decision_records_arms.py` (test_the_kit_declares_a_path_matched_delivery_of_the_rule_over_the_decision_directory, test_the_lean_manifest_keeps_the_moved_rule_under_its_own_entry_scoped_to_every_glob, test_the_lean_manifest_lists_the_kernel_under_its_own_entry_loaded_at_session_start, test_the_lean_manifest_changes_no_other_entry, test_the_lean_copys_moved_rule_carries_a_paths_scope_naming_every_declared_glob, test_the_lean_copys_own_installer_links_the_moved_rule_and_its_kernel, test_a_lean_session_starts_with_every_kernel_line, test_a_lean_session_starts_with_no_other_line_of_the_moved_rule); `tests/acceptance/test_move_arms.py` ((module)) | 5 file(s) -- `eval/src/praxion_evals/adherence/moves/model.py`, `eval/src/praxion_evals/adherence/moves/declaration.py`, `eval/src/praxion_evals/adherence/moves/arms.py`, `eval/src/praxion_evals/adherence/moves/kits/adr-conventions/declaration.json`, `eval/src/praxion_evals/adherence/moves/observe.py` | PASS |
| REQ-02 | 2 test(s) -- `eval/tests/test_moves_arms.py` (test_a_lean_manifest_without_the_path_matched_rules_row_is_refused_naming_the_rule, test_a_build_declaring_no_path_matched_delivery_is_not_refused_for_linking) | 3 test(s) -- `tests/acceptance/test_move_decision_records_arms.py` (test_a_lean_manifest_that_would_not_link_the_path_matched_rule_is_refused_naming_it, test_a_run_whose_path_matched_rule_would_never_load_is_refused_naming_the_rule, test_a_refused_run_launches_no_session_and_writes_no_results_file) | 2 file(s) -- `eval/src/praxion_evals/adherence/moves/arms.py`, `eval/src/praxion_evals/adherence/moves/observe.py` | PASS |
| REQ-03 | 5 test(s) -- `eval/tests/test_moves_declaration.py` (test_a_phrase_its_section_does_not_hold_is_refused_naming_check_phrase_section_and_rule, test_a_phrase_differing_only_in_letter_case_is_accepted, test_a_phrase_held_only_outside_its_section_is_refused, test_a_phrase_held_by_a_sub_heading_of_its_section_counts_as_inside); `eval/tests/test_moves_trigger.py` (test_the_trigger_reader_agrees_with_the_phrase_predicate) | 6 test(s) -- `tests/acceptance/test_move_declared_phrases.py` (test_a_phrase_its_named_section_does_not_hold_is_refused_when_the_arms_are_built, test_the_refusal_names_the_check_the_phrase_the_section_and_the_rule_file, test_a_dry_run_of_a_declaration_carrying_an_unheld_phrase_is_refused_launching_nothing, test_a_phrase_differing_only_in_letter_case_from_its_section_is_accepted, test_the_git_conventions_declaration_is_accepted_unchanged, test_every_phrase_the_adr_conventions_kit_declares_is_held_by_the_section_its_check_names) | 3 file(s) -- `eval/src/praxion_evals/adherence/moves/model.py`, `eval/src/praxion_evals/adherence/moves/declaration.py`, `eval/src/praxion_evals/adherence/moves/trigger.py` | PASS |
| REQ-04 | 4 test(s) -- `eval/tests/test_moves_runner.py` (test_the_registry_holds_both_moves_each_under_its_own_name, test_the_adr_kit_draws_twenty_four_paired_tasks_and_a_floor_of_eight_at_the_defaults, test_a_dry_run_of_the_adr_move_launches_nothing_and_writes_nothing, test_a_move_without_a_task_kit_is_refused) | 7 test(s) -- `tests/acceptance/test_move_decision_records_dry_run.py` (test_the_dry_run_is_no_longer_refused_for_want_of_a_task_kit, test_the_dry_run_launches_no_session_and_leaves_the_checkout_as_it_was, test_the_dry_run_totals_fifty_six_sessions_at_the_defaults, test_the_printed_sessions_match_the_printed_totals_and_per_task_counts, test_the_paired_run_lists_one_full_and_one_lean_session_for_each_of_its_tasks, test_every_listed_session_is_on_a_managed_fixture_and_fully_described, test_no_two_paired_tasks_share_both_fixture_and_wording_variant) | 1 file(s) -- `eval/src/praxion_evals/adherence/moves/runner.py` | PASS |
| REQ-05 | 5 test(s) -- `eval/tests/test_moves_kit_adr.py` (test_the_candidates_outnumber_a_draw_and_pair_every_fixture_with_every_wording, test_a_draw_holds_the_target_plus_slack_of_tasks_and_asks_for_both_sorts, test_no_request_holds_a_line_of_the_rule_or_a_declared_phrase, test_no_request_names_a_category_value_as_a_whole_word, test_no_request_holds_a_command) | 8 test(s) -- `tests/acceptance/test_move_decision_records_kit.py` (test_the_task_list_holds_at_least_the_target_plus_slack, test_no_two_tasks_share_both_fixture_and_wording, test_every_task_comes_from_a_managed_fixture, test_no_request_holds_a_line_of_the_moved_rule, test_no_request_holds_a_declared_phrase_of_either_governed_check, test_no_request_names_a_category_value, test_no_request_holds_a_command, test_the_kits_fixtures_ask_for_decisions_of_both_sorts) | 1 file(s) -- `eval/src/praxion_evals/adherence/moves/kit_adr.py` | PASS (the judged part: PASS with a WARN on wording lean, read floor rates by wording) |
| REQ-06 | 1 test(s) -- `eval/tests/test_moves_kit_adr.py` (test_a_built_fixture_carries_no_line_of_the_rule_and_no_declared_phrase) | 7 test(s) -- `tests/acceptance/test_move_decision_records_kit.py` (test_every_fixture_is_a_managed_project_with_every_shipped_block_but_hackathon_and_sidecar, test_every_fixture_is_on_a_named_branch_other_than_its_default, test_every_fixture_has_a_git_identity_a_session_can_read, test_every_fixtures_decision_directory_holds_two_listed_older_habit_records, test_no_fixture_holds_a_draft_directory, test_no_fixture_file_carries_a_line_of_the_moved_rule_or_a_declared_phrase, test_a_record_scripted_as_the_rule_says_grades_passed_in_every_fixture) | 1 file(s) -- `eval/src/praxion_evals/adherence/moves/kit_adr.py` | PASS |
| REQ-07 | 7 test(s) -- `eval/tests/test_moves_checks_adr.py` (test_a_stamp_user_branch_slug_name_is_a_fragment_carrying_its_stamp, test_a_name_carrying_the_long_branch_uncut_is_other, test_the_segment_of_a_54_character_branch_is_cut_to_forty, test_discovery_leaves_out_what_the_baseline_held_and_what_is_not_markdown, test_draft_placement_fails_exactly_the_part_a_planted_record_violates, test_a_committed_older_habit_record_moved_into_conformance_passes, test_no_record_left_is_nothing_to_grade) | 7 test(s) -- `tests/acceptance/test_move_decision_record_checks.py` (test_draft_placement_fails_exactly_the_part_a_planted_record_violates, test_draft_placement_fails_when_one_of_two_records_is_misplaced, test_a_record_moved_into_conformance_before_the_session_ended_passes_draft_placement, test_a_session_that_left_no_decision_record_leaves_nothing_to_grade, test_a_markdown_file_left_only_in_the_ephemeral_pipeline_directory_is_no_decision_record, test_a_fragment_named_by_the_fixtures_branch_segment_passes_draft_placement, test_a_fragment_carrying_the_branch_uncut_past_forty_characters_is_a_malformed_name) | 1 file(s) -- `eval/src/praxion_evals/adherence/moves/checks_adr.py` | PASS |
| REQ-08 | 6 test(s) -- `eval/tests/test_moves_kits.py` (test_the_adr_kit_governs_draft_placement_then_decision_category, test_each_adr_governed_phrase_lies_in_its_own_section); `eval/tests/test_moves_checks_adr.py` (test_an_id_is_read_as_exactly_one_form, test_a_record_is_disconfirmed_when_a_disconfirmation_section_names_all_three_items, test_decision_category_fails_exactly_the_part_a_planted_record_violates, test_a_markdown_file_under_ai_work_is_no_decision_record) | 2 test(s) -- `tests/acceptance/test_move_decision_record_checks.py` (test_decision_category_fails_exactly_the_part_a_planted_record_violates, test_a_session_that_left_no_decision_record_leaves_nothing_to_grade) | 2 file(s) -- `eval/src/praxion_evals/adherence/moves/kits/adr-conventions/declaration.json`, `eval/src/praxion_evals/adherence/moves/checks_adr.py` | PASS |
| REQ-09 | 4 test(s) -- `eval/tests/test_moves_checks_adr.py` (test_a_record_in_the_draft_directory_reads_its_name_id_category_and_disconfirmation, test_a_name_led_by_a_record_number_is_a_numbered_name, test_the_projects_older_habit_fails_both_checks_on_the_parts_it_violates, test_the_run_adapter_reads_the_baseline_and_branch_refs_and_grades_the_new_records) | 3 test(s) -- `tests/acceptance/test_move_decision_record_checks.py` (test_a_record_in_the_projects_older_habit_fails_draft_placement, test_a_record_in_the_projects_older_habit_fails_decision_category, test_a_record_written_as_the_rule_says_passes_both_checks_for_either_sort) | 1 file(s) -- `eval/src/praxion_evals/adherence/moves/checks_adr.py` | PASS |
| REQ-10 | 6 test(s) -- `eval/tests/test_moves_fixture_project.py` (test_write_files_creates_directories_and_keeps_the_last_write_of_a_path, test_git_runs_in_the_repository_and_returns_its_output, test_git_failure_raises_rather_than_passing_silently, test_git_ignores_the_operators_configuration, test_project_instructions_carries_every_shipped_block_but_the_excluded, test_project_instructions_without_exclusions_carries_all_blocks) | 6 test(s) -- `tests/acceptance/test_move_arms.py` ((module)); `tests/acceptance/test_move_dry_run.py` ((module)); `tests/acceptance/test_move_governed_checks.py` ((module)); `tests/acceptance/test_move_verdict_and_report.py` ((module)); `tests/acceptance/test_move_declared_phrases.py` (test_the_git_conventions_declaration_is_accepted_unchanged); `tests/acceptance/test_move_session_take.py` (test_a_path_matched_load_on_a_creating_write_reads_as_arrived_after_execution) | 2 file(s) -- `eval/src/praxion_evals/adherence/moves/fixture_project.py`, `eval/src/praxion_evals/adherence/moves/model.py` | PASS |
| REQ-11 | (none) | 3 test(s) -- `tests/acceptance/test_move_decision_records_documentation.py` (test_the_move_section_states_what_the_instrument_does, test_the_move_section_names_each_build_time_refusal, test_the_move_section_no_longer_states_a_retracted_claim) | 1 file(s) -- `eval/EVAL_PLAN.md` | PASS (the whole-prose claim judged PASS) |

**Coverage**: all 11 requirements carry acceptance evidence, and 10 of 11 carry unit evidence (REQ-11 is documentation, proven by its acceptance nodes).

## Key Decisions

No ADR: nothing passes the `architectural` test. From `LEARNINGS.md § Decisions Made` and `CHECKPOINT_DIGEST.md`:

**[systems-architect] `td-518` arm fix by a new derive kind (implementation)**: `manifest_row_scoped` keeps the moved rule's row (`load: path_scoped`, `paths:` from the delivery, `install: symlink` required) and adds the kernel's `always_on` row right after it. **Why**: the installer links manifest rows only; this is the smallest pure derive that makes the rule load. **Alternatives**: regenerating the manifest in the arm (rejected: `generated_at` changes the digest on every build, so no floor could be cited); widening `manifest_row_removed` (rejected: the name would hide the behaviour).

**[systems-architect] The unlinked-rule refusal is observed, not declared (implementation)**: the lean copy's own linker run is read. **Why**: copies are observed, never trusted. **Alternatives**: parsing the lean manifest (a second source of truth for the installer's filter).

**[systems-architect] The phrase refusal is section-scoped (implementation)**: one case-insensitive predicate shared with the trigger reader. **Alternatives**: whole-rule matching (td-518's literal wording, weaker).

**[systems-architect] What the checks grade (behavioral)**: File Format parts and the category vocabulary plus the Disconfirmation duty; not whether the category is right. **Why**: judgment adds noise to both arms but little differential power, and generic MADR sections pass in a floor. **Alternatives**: a per-fixture sort oracle (runner-up), the frontmatter field set, the index, supersession.

**[systems-architect] Managed-only fixtures (behavioral)**: the governed behaviour lives in the project state directory, which only a managed project has; accepted at the spec checkpoint against the archived spec's general both-kinds ask.

**[systems-architect] Branch from a fixture ref; branch segment as the authoring protocol writes it (implementation, behavioral)**: `refs/fixture/branch` beside `refs/fixture/baseline`, so `Kit.grade` is unchanged; lowercase, runs outside `[a-z0-9-]` to one hyphen, trimmed, cut to 40.

**[systems-architect] Rework W-1 to W-4 (behavioral, implementation)**: the decision-record definition, admissible branches, fence-aware headings shared by grader and section span, `.MD` as a malformed name, a commit of its own on each fixture branch, and request wording that names a decision record or ADR and no index, log or history. **Lesson**: a risk rated against the task's own requests missed what the always-loaded rules ask every session to do; a grader's object definition must be checked against the resident process text.

**[implementation-planner] Driver bindings precede every production step; guards are owned by the earliest step that can regress them; checks use the owner's outer-loop nodes**: so the gate never reads a regression as pending.

**[orchestrator] Spec checkpoint (2026-10-29)**: re-tier to Full; managed-only accepted; category correctness not graded; the git floor and its paired run must share a tree.

**[orchestrator] Rulings at close (2026-10-29, the user delegated the four open decisions)**: #fail-1 admitted; `main-session-adherence` merged first, then this branch, then pushed; both moves' floor runs launch from one frozen checkout at the pushed merge, so their later paired runs can cite them.

**Declared limits and carried warnings**: Markdown written in the visible tree outside the decision directory is a record and fails placement (by design, so the floor never goes blind; per-part rates show it); `checks_adr.DEFAULT_BRANCH` mirrors `kit_adr.BASELINE_BRANCH` by a checklist comment; the shared heading helper lives in the declaration parser; the File Format section's span takes in the category subsection, so a phrase moved between the two checks would not be refused; the trigger history reads a shell rename as right-first-time; the step-7 section of the test-results shape check is oversized (advisory, driver-written).

**Follow-up.** On the user's go: the git-conventions floor run on the reworked kit, the adr-conventions floor run, and the creating-write probe that closes `td-518`; then each move's paired run from the same frozen checkout.
