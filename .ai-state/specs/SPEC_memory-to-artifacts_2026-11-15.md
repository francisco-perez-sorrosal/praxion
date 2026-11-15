# Spec: memory-to-artifacts (process knowledge moves from memory to the artifacts that govern it; memory keeps status and preferences)

**Task slug**: `memory-to-artifacts`
**Created**: 2026-11-12
**Pipeline run**: 2026-11-12 to 2026-11-15. The stages:
- intake, then an inventory of the memory index, its 134 topic files and seven handoff prompts by four independent context-engineer instances (324 rows), reconciled into a placement plan of 256 pieces; the spec (23 requirements) with three Spec Questions answered by the orchestrator; the run re-tiered from Standard to Full after the inventory (131 moves into 59 files in 14 batches, 3 of them code);
- acceptance design (the outer loop: 10 files, 40 test functions, 63 cases, 34 of them red at the base), with its own questions (AD-SQ-O1 and AD-SQ-01 to AD-SQ-06);
- design (one decision record) and a 24-step plan (17 steps for implementers, 7 for the orchestrator);
- implementation on 2026-11-12: 15 of the 17 implementer steps in three waves of lane implementers (one step each, in its own scratch worktree, cherry-picked in plan order), the integration checkpoint and the re-pin of six frozen guards;
- first verification (2026-11-12);
- 2026-11-13: `process-principles` had merged to main and was taken in (REQ-07 dropped under SQ-07, batch W1 landed with ten of its eleven pieces), the delta verification, a second merge of main and the CI-equivalent run in full; then a follow-up pass of two text commits;
- 2026-11-15: the merge into main as a fast-forward, the release v0.64.0, the installation of v0.65.0, the memory pass (run by the orchestrator, outside the repository) and its verification.

**Archived**: 2026-11-15
**Status**: completed -- every verification failure cleared (the delta verification's last full verdict read FAIL on one procedural finding: the spec extract could not be written; it was fixed in the work directory and the extract is fresh at archival; the memory pass then verified PASS with 11 PASS, 4 WARN and 0 FAIL); the follow-on text batch for the two held lessons and one uncarried sentence is not yet merged
**Tier**: Full (re-tiered from Standard on 2026-11-12, after the inventory: 131 moves into 59 files in 14 batches, 3 of them code; the verifier's retrospective calibration reads correct)
**Complexity**: large: 23 requirements (22 in force), 24 plan steps, 31 commits of its own and 92 files changed against main as it stood at the second merge of main (`git diff --shortstat d2ee23a2 c55721e2`: +2,640 and -105 lines; 40 of those files are shipped text, 19 are scripts and hooks with their tests, 19 sit under `tests/` (the outer-loop files, their drivers and the re-pinned guards and fixtures), 9 are documents and other files, 4 are state files and 1 is a workflow comment), one new reference file, five script modules and three hooks with changed behaviour, and a memory directory cut from 134 topic files to 15.
**Base commit**: `54cc2f9c` (main after the third wave of small ledger rows; the branch was first cut from `f3988742` and rebased onto `54cc2f9c` before any production commit). Further commits:
- acceptance design `118a9a3c`, design `2e5678db`;
- 15 lane commits `f1ad51b9` to `2a674358`, and the re-pin of six frozen guards `3d9d68c0`;
- main taken in as `98b6ff2a` (with `process-principles`), the REQ-07 drop `92cb5c10`, batch W1 `88ab2cc2`, main taken in again as `44ef7f0a`;
- the follow-up text commits `cc77138b` and `c55721e2` (the head that was merged); the state commit `2648659f`.

**Pipeline branch**: `feat/memory-to-artifacts`
**Merged**: into main as a fast-forward at `c55721e2` (state commit `2648659f`), released in v0.64.0 and installed with v0.65.0
**ADRs**: `dec-512` (behavioral): the memory index budget is one declared ceiling, owned by the audit
**Related specs**: `SPEC_process-principles_2026-11-12.md` (the pipeline whose merge batch W1 waited for, and whose generated principles pointer made REQ-07 moot)

## Feature Summary

The process knowledge held in memory now reaches every session through the artifact that governs its surface.

Before this:
- The project's auto-memory index held 134 lines (17,616 bytes), loaded into every session and every spawn here, and 73 gotchas sat in seven handoff prompts that reach a session only when the user pastes one. Most of it was process knowledge (how to drive the step loop, how a hook is registered, what a refusal means), not live status or a preference.
- The index audit warned only past four fifths of the harness load limit (160 lines or 20,000 bytes), so the index grew from 12.2 KB to 17.6 KB with no warning.
- Six gate, hook and script messages stopped or refused without saying what the stop meant or how to clear it.

Now:
- **The index has a budget.** `scripts/check_memory_index.py` warns once on an index above 5,000 bytes or 40 lines (a fifth of the load limit), and `hooks/guard_memory_index.py` lets a write land and warns when it leaves the index above that budget and larger than before. Every refusal the guard made is unchanged. One declared value serves both (`dec-512`).
- **Six messages carry their own recovery.** The blocked-marker stop of the step loop, the refusal of a record after a step block was revised, the clean-tree note of the test-scope resolver, the wrong-command finding of the footprint check, every commit-gate refusal (now with the checker's findings and the way out) and the task-brief reminder (now naming the root it looked under).
- **The text moved.** Ten batches (B1 to B10, 113 pieces by the spec's counts) and batch W1 (ten of eleven pieces) landed in the skill, rule, reference, maintainer-document and code-comment homes the placement plan names. No always-loaded file grew; moved text cites no ledger or decision ids; each fact observed once carries its observation date.
- **The memory pass ran** (2026-11-15, after the merge, the release and the plugin update): 256 pieces each got one class and one fate, 119 topic files were deleted against a byte-checked backup, and the index fell to 15 lines and 2,091 bytes. The section Memory Pass has the totals and what is held.
- **One requirement was dropped** (REQ-07, the principles-pointer test message): the other pipeline now generates the pointer's names from the template's headings, so there is no hand list to forget.

What the user decides next: the placement plan's seven questions. Q2, Q3, Q6 and Q7 each hold a piece (see Memory Pass); Q1 (where the standing policy lives) is untouched here; Q4 (a hook for a bare `cd`) and Q5 (an installer guard) hold nothing.

## What Was Built

- **The budget (code):**
  - `scripts/check_memory_index.py`: `IndexSize` (an immutable value built by `IndexSize.of`), `INDEX_BUDGET` (40 lines, 5,000 bytes) and `LOAD_LIMIT` (200 lines, 25,000 bytes) as the only literals of either limit, `_size_findings` (one `over-budget` warning; an index past the load limit fails as before with no second size finding) and the pure `budget_warning(before, after)`; the four-fifths share is removed.
  - `hooks/guard_memory_index.py`: when nothing is refused, it calls `budget_warning` and returns the warning as `additionalContext` on an allowed write; it holds no number of its own and still fails open.
- **The messages (code):**
  - `scripts/_step_loop_render.py` (`_ACTIONS`: the blocked-marker stop on stderr and in `HANDOFF.md`) and `scripts/_step_loop_record.py` (`_pending`: the refusal after a revised step block, error code and exit status kept);
  - `scripts/resolve_test_scope.py` (a stderr note on a clean tree, stdout and exit status unchanged) and `scripts/check_footprint_criteria.py` (`_row_defects`: the token-by-token matching rule);
  - `hooks/commit_gate.sh` (on a block it re-emits the checker's captured findings on stderr and appends the way out; the checker is unchanged) and `hooks/remind_task_brief.py` (`_process`).
- **The text (ten batches and W1):**
  - skills `ralph-lite`, `step-loop` (with the new `references/stop-recoveries.md`, linked once from the body), `hook-crafting`, `co` and `cop` (through `claude/canonical-blocks/commit-process.md`), `handoff`, `merge-worktree`, `release`, `resume-rework`, `test`, `triage-debt`, `testing-strategy`, `python-development`, `mcp-crafting`, `cicd`, `evidence-appraisal`, `python-prj-mgmt`, `rule-crafting`, `skill-crafting`, and the software-planning and spec-driven-development references;
  - bullets in three path-scoped rules (`gate-liveness`, `id-citation-discipline`, `testing-conventions`), with `rules/_manifest.yaml` regenerated and `rules/_audience.yaml` untouched;
  - maintainer documents (`README_DEV.md`, `claude/config/README.md`, `dashboard_app/README.md`, `docs/observability.md`, `eval/README.md`, `agents/CLAUDE.md`, `docs/claude-code-limitations.md`, `docs/lean-spawn-how-to.md`, `docs/lean-spawn-kernels.md`, `docs/rework-dispatch.md`, `rules/CLAUDE.md`, `scripts/CLAUDE.md`) and comments in five code files with no behaviour change;
  - W1: `skills/software-planning/references/coordination-details.md` (774 of its 800 lines).
- **The tests:**
  - nine outer-loop files in force (eight under `tests/acceptance/` and one under `tests/e2e/`, with three drivers; a tenth, for REQ-07, was removed with the requirement): 38 test functions, 61 cases, each code requirement with a canary at the edge (5,001 bytes warns and 5,000 does not; 41 lines warns and 40 does not; a write from 4,990 to 5,010 bytes lands and warns; a shrink above the ceiling does not warn);
  - unit tests beside each changed module (`scripts/test_check_memory_index.py`, `hooks/test_guard_memory_index.py`, `scripts/test_loop_render_texts.py`, `scripts/test_loop_cli_next.py`, `scripts/test_resolve_test_scope.py`, `scripts/test_check_footprint_criteria_judge.py`, `hooks/test_commit_gate.py`, `hooks/test_remind_task_brief.py`).
- **Frozen guards re-pinned (step 19):** six guards that pin text the rule lessons moved, entry by entry and never as a blanket re-freeze: seven declared-rewording rows in the moved-not-cut guard and the Cursor export digests of three rules in five fixtures (AD-SQ-01 to AD-SQ-06).
- **The documentation:** `.ai-state/DESIGN.md` section 7 gained two design-target rows (the index budget; a refusal or stop carrying its own recovery), now marked Built; the `scripts/CLAUDE.md` catalog line for `check_memory_index.py` names `over-budget` and the budget.

## Memory Pass

The pass (REQ-21 to REQ-23) was run by the orchestrator on 2026-11-15, outside the repository and never through a commit, on main at `6bb19a53` with v0.65.0 installed. It waited for the merge, the release and the plugin update (the orchestrator's execution policy, stricter than REQ-21), and a backup of the whole memory directory was taken before the first edit: `tmp/memory-backup-2026-11-15/` (135 files; machine-local, not in git, kept beside the older `tmp/memory-backup-2026-11-12/`). "The placement plan" below is the pipeline's piece-by-piece plan of where each lesson goes; it is a pipeline document and is not kept.

- **Totals.** 256 pieces: 128 moved, 62 carried, 46 superseded, 14 kept, 6 held. The 134 topic files became 15 (119 deleted, each only after a byte comparison with the backup; 11 stay; 4 held). The index went from 134 lines and 17,616 bytes to 15 lines and 2,091 bytes (ceiling 40 lines and 5,000 bytes); the memory directory from 495,815 to 30,795 bytes. No link in a surviving file points at a deleted one.
- **Against the plan's 131 moved, 61 carried, 46 superseded and 18 kept:** moved is 131 less three (P-131, superseded by the generated pointer; P-044, superseded by a fix already in the tree; P-045, held). Superseded is 46 plus those two, less P-203 and P-204 (held). Carried is 61 plus the reputable-sources line (P-241). Kept is 18 less P-241 and the three prompt-only pieces now held.
- **Proof rules applied (REQ-21).** A moved piece: its recorded search finds the lesson on main and in the installed copy, and the earliest commit on main that adds the text is an ancestor of `v0.65.0`. A carried piece: the cited lines still stand word for word on main and in the installed copy, or were re-read by hand where they had moved (13 of 61 citations had moved or been reworded by this pipeline's own batches). A superseded piece: every cited commit is on main, every cited decision has its file, every cited ledger row is resolved, and cited lines or machine state were re-read. A held piece is never deleted.
- **Three departures from the placement plan.**
  - The rerere and update-refs lesson (P-204) is held, not superseded. The plan's evidence was that the global git configuration sets neither, but a `--global` read does not follow included files; `git config --show-origin --get-regexp` shows five keys on, all from one included file. The lesson is live and no installed text carries it.
  - The large-push lesson (P-203, HTTP 400 on push) is held, not superseded. The plan's evidence was a global post-buffer setting; it is set only in this repository's own configuration, so a fresh clone lacks it, and no installed text carries the lesson.
  - The preference line on reputable sources (P-241) went as carried, not kept: its content is stated in the installed principle and in `evidence-appraisal`, and the session prompt of 2026-11-15 retired the line.
- **The six held pieces** (each keeps its topic file and index line where it has one):
  - P-045, a resolved ledger row migrating after a commit, amend or ride the next state commit: the user's ruling on Q2;
  - P-203 and P-204 above: the next batch of their homes, or the user's acceptance of the local setting;
  - P-252, merge with `--no-ff` or the fast-forward default (the shipped text says fast-forward): Q3;
  - P-254, an instruction about cutting command lists whose premise is unclear: Q7, retiring the old prompts' gotcha sections;
  - P-255, the user's secret-disclosure hook refusing a command by its text (outside the repository; a refusal text is proposed): Q6.
- **Verification (2026-11-15).** REQ-21, REQ-22, REQ-23 and FC-05 pass (11 PASS, 4 WARN, 0 FAIL in that pass). All 128 recorded searches were re-run on main and in the installed copy, with every carrying commit an ancestor of `v0.65.0`. 256 piece rows, 134 topic-file rows, 134 index-line rows and 73 handoff-gotcha rows were checked against the backup: none unaccounted for, none with two fates. The index is the plan's twelve lines less one plus four held, byte for byte, and the audit reports 0 failing and 0 warning. Three of the four WARN were record defects, corrected in the fate table (a search that did not parse, two stale line citations, a piece's second home unrecorded with three prompt-only pieces labelled kept instead of held); the fourth is the uncarried sentence below.
- **Not yet merged: the follow-on text batch.** The two live lessons held above (P-203 and P-204) and one sentence the verifier found uncarried (a background session's log drops letters, so its completion is read from the `✻ <verb> for <N>m` line; it belonged to a deleted rework-sessions note) are being written by a follow-on text batch on the branch `feat/handoff-lessons`. At archival that work is uncommitted edits in its worktree and the branch has no commit ahead of main; until it lands the backup holds the sentence.

## Footprint Readings

| Id | Baseline | Final | Limit | Reading |
|---|---|---|---|---|
| FC-01 always-loaded tokens | 19918 tokens (spec baseline, `2e5678db`); 19988 on the base after main was taken in (`d2ee23a2`) | 19988 tokens (`c55721e2`) | at or below the baseline | measured |
| FC-02 skill and agent listing tokens | 13335 tokens (`d2ee23a2`) | 13335 tokens (`c55721e2`) | at or below 13335 (the baseline) | measured |
| FC-03 prompt-size findings | 3 warn, 0 fail (`d2ee23a2`) | 3 warn, 0 fail (`c55721e2`) | no new warn on an edited file, no fail | measured |
| FC-04 test-selection size | widened 0, median 136.5, p90 392.0 (`d2ee23a2`) | widened 0, median 191.0, p90 407.9 (`44ef7f0a`); the base resolver over the same 50 commits reads the same | equal to the reference run's figures | measured |
| FC-05 memory index | 17616 bytes, 134 lines (`2e5678db`) | 2091 bytes, 15 lines (`c55721e2`, taken 2026-11-15) | at or below 5000 bytes and 40 lines | measured |

Notes on the readings:
- **Sources:** the `final` rows of `MEASUREMENTS.md` with the commands of the criteria table (`measure_token_budget.py --json`, `check_agent_prompt_size.py --json`, `measure_selection_size.py --compare-ref 54cc2f9c --json` and `wc -c -l` on the index). FC-05's final was taken after the memory pass; its head column carries the pipeline head `c55721e2` because the value is a property of a machine-local file no commit can change.
- **FC-01's baseline moved with the base.** The spec's 19,918 was read at `2e5678db`; after main was taken in, the base tree reads 19,988 (70 more, from another pipeline's rule sentence). The limit keeps its meaning, no rise from this pipeline's own commits, and the baselines were re-taken at `d2ee23a2`.
- **FC-04's final row is at `44ef7f0a`;** the two commits after it are text only. Its comparator is equality with the reference resolver's run over the same commits, not with the baseline row.
- **FC-05 is an unregistered footprint** (the index is outside the repository), so `check_footprint_criteria.py` reports one FP04 info for it. At the pipeline's head the verifier's run (`--stage verify --base-ref d2ee23a2`, from the pipeline worktree) read 0 fail, 0 warn and 1 info.
- **Staleness at archival, stated:** the same check run at archival on main at `6bb19a53` reports 5 fail (FP03 stale-final on FC-01 to FC-05), 1 warn (FP01 on observation-log-volume, moved by a file outside this pipeline's diff) and 1 info (FP04). The cause is the commits after the final rows' heads (a later pipeline's merge and the release bumps among them); none of them is this pipeline's, and no file the criteria bound changed in this pipeline after its final rows.
- **Declared not measured, with reasons:** `hook-latency` (no registered instrument; the guard adds one size comparison to a write it already reads), `spawn-count` (the only counter counts a pipeline that has already run; this change adds no spawn) and `spawn-startup-tokens` (a paid probe on the user's go; no edited file reaches a spawn at start, and the kernel generator's check staying clean is the free reading).
- **Health readings:** the first CI-equivalent run (`d87be46b`) read 18,770 passed, 8 failed and 10 errors: 10 load-only errors, 2 regressions of this pipeline (fixed) and 6 frozen guards (re-pinned). The full rerun at `44ef7f0a`, the head containing main at `d2ee23a2`, read 18,934 passed, 37 skipped, the shell suite clean, the eval pocket 4,312 passed and the chronograph pocket 288 passed (`pass=23534 fail=0 skip=37`), with nine health guards at exit 0. The two follow-up text commits ran their derived scope (`pass=10477 fail=0 skip=13`). The mutation sensor ran on steps 2 and 5 and published survivors (111 of 354 mutants in the audit module, 299 of 948 in the resolver); it is a sensor, never a gate (td-644).

## Key Decisions

- **One index budget, declared once, owned by the audit** (`dec-512`). `scripts/check_memory_index.py` declares `IndexSize(40 lines, 5,000 bytes)` beside the load limit and owns the only literal of each; the guard imports `budget_warning` and holds no number. Evidence: the index grew from 12.2 KB to 17.6 KB without a warning, and the entries that belong there fit in 12 lines and 1,698 bytes. Rejected: a share of the load limit (the status quo, which warned nobody at 17.6 KB) and a guard-local constant (two literals drift). "Crosses" means the write leaves the index above the ceiling and larger than before, so every growth past the budget warns and a shrink never does. Cost: one ceiling for every index both tools judge, so `--all` warns on two other local projects' indexes (15.6 KB and 11.8 KB; nothing here edits them), and the hook warning reaches marketplace sessions only after a release.
- **The commit gate re-routes; the checker does not change** (design decision, no decision record). On a block the gate prints the checker's captured stdout on stderr (what a refused session reads) with the way out. A hand, pre-commit or CI run of the id-citation check is unchanged. Rejected: printing the findings on stderr in the checker (changes every caller's output and touches a second file).
- **A moved piece's memory line goes only once its carrying commit is on the default branch** (the orchestrator's ruling on SQ-01, written into REQ-21), and a grep run there shows the home says what the memory source says. The orchestrator's execution policy is stricter: deletions for moved pieces also wait for the release and the plugin update, because the marketplace install is a full copy and a plain session reads skills and hooks from the installed version. Carried and superseded pieces wait for no merge.
- **REQ-07 is dropped** (SQ-07, 2026-11-13). The check that held the principles pointer to the template's principles no longer has a hand list to forget, so a message naming the file to edit would now be wrong advice. Its acceptance file and three driver helpers were removed in `92cb5c10`; plan step 18 became a recorded no-op; the piece is superseded.
- **P-124 is re-homed** (the ruling on SQ-03 b): its planned home was an acceptance driver, read-only for the implementer, so the lesson (how a test that converses with the installer stands in for the optional tools it offers) went to `README_DEV.md` in batch B8. This overrides the placement plan for one piece.
- **Plan-level decisions** (in `LEARNINGS.md` only; it states that no decision record was drafted for them):
  - the index budget is two steps, the audit then the guard, so each carries one tag (the sensor on the script, a forced review on the hook);
  - batch W1 is gated by an orchestrator step left open while `process-principles` was unmerged, not by a plan revision;
  - B4's file set grew by the canonical commit block and `skills/cop/SKILL.md`, because the `co` pieces sit inside a byte-identical fenced block that `sync_canonical_blocks.py --write` rewrites;
  - a text step's Check is the existing guards for its file class, floored at their collected counts; a new presence test per batch was rejected as brittle and against the sizing instruction (tens of scenarios, not hundreds);
  - W1's escalation-ruling piece went into the Spec-Question Routing list because the plan's "self-gating" section does not exist.
- **Process:**
  - Lanes instead of a shared tree: one implementer per step in its own scratch worktree, committing there, cherry-picked in plan order. Fifteen steps in three waves landed with no conflict; the plan's "must not run together" list concerned a shared tree and did not bind lanes. A lane told another gate was using the machine ran only its Check; the first wave, not told, ran sensors and measurements whose load cost another pipeline's gate a false red.
  - Review fixes that were comment-only were applied by the orchestrator; fixes that change shell behaviour went to an implementer with a failing test first. Two forced light reviews (steps 3 and 6) each closed after one revision round.
  - The spawn tally at the verifier read `spawns=32 charged=35 budget=32 verdict=over`: each lane implementer is charged where the driver would have recorded an iteration. That is the cost of the execution choice, not evidence the tier was set too high.
- **Verification:**
  - First report (2026-11-12, `3d9d68c0`): FAIL on one procedural finding, a stale FC-03 final row after a fix commit, cleared when the finals were re-taken; 115 recorded presence searches re-run (114 found; the one that failed was a regex, with the text present).
  - Delta verification (2026-11-13, `45a4a05a` to `44ef7f0a`): FAIL on F-D2 (the spec extract could not be written because two orchestrator notes held commit ids in code spans), otherwise PASS with 5 new WARN; 55 PASS, 11 WARN, 1 FAIL and 4 pending by design at that report. F-D2 was fixed in the work directory (notes rewritten without code spans, the base-moved note moved into the Spec Questions); at archival `extract_spec.py memory-to-artifacts --check` reads fresh (`sha256:5b9de0316dea`). REQ-20 passed with W-D1a and W-D1b, fixed in `cc77138b` and `c55721e2`; a stale clause (P-044) was found against a fix already in the tree and dropped in `cc77138b`.
  - Memory pass verification (2026-11-15): 11 PASS, 4 WARN, 0 FAIL (see Memory Pass). No second full verification followed the two follow-up text commits; each ran its derived scope.
  - Calibration: correct, confirmed at the delta. The verifier registered one objection: a rework manifest would have spawned worktrees for small items on a pipeline already over its spawn budget, so none was written and the small items went to the follow-up record, whose open state blocks cleanup. At archival that record holds six lines, five final and one open (the uncarried sentence above, carried by the follow-on batch).
- **Patterns merged from verification and the pass** (from `LEARNINGS.md`):
  - a footprint `final` row goes stale when a fix commit lands after it, so re-take the finals at the head you ask to merge;
  - a grep recorded as evidence is re-run once as written, or the deletion it gates stalls;
  - a post-merge procedure keyed on commit shas must survive the rebase the merge convention prescribes (record sha plus subject);
  - interim text written against an open ledger row is re-checked against that row's status when it lands (P-044);
  - an orchestrator note added to the spec must pass `extract_spec.py --check` in the same sitting;
  - a proof that rests on machine state is re-read with the command that sees the whole state (`--show-origin`, not `--global`);
  - a proof by cited line numbers decays with the batches the same pipeline lands: check that the lines verified at the plan's base still exist word for word, and re-read only the ones that do not.
- **Out of scope, filed (in the live ledger at archival):** td-641 (`validate_references.py` checks only the first of several `--file` arguments), td-642 (no gate holds shipped Markdown free of pipeline ids), td-643 (the acceptance-design classes have no slot for current external harness documentation) and td-644 (mutation survivors in the world-read functions of the two sensor-tagged files).
- **Decision record and `LEARNINGS.md` cross-reference.** `dec-512` is the only record this pipeline wrote: accepted, category behavioral, `pipeline_tier: full`, `affected_reqs: [REQ-01, REQ-02]`, affected files the audit and the guard; no draft is left under the drafts directory, and `LEARNINGS.md` names it by its final id. Present in `LEARNINGS.md` and not in a record: the commit-gate re-route (a design decision of one adapter, with no statement either way; judged an implementation detail and not filed), the planner's sequencing choices and the implementer's step 24 homes (both by the file's own statement that no record was drafted). Present in a record and not in `LEARNINGS.md`: none.

## Requirements

Requirements are pipeline-local; never cite their ids in code, tests or docstrings. The text below is the behavioural specification as it stood at the end: 23 requirements, of which REQ-07 was dropped under SQ-07 (its text stays, struck, as the record), REQ-17 and REQ-19 were amended by the ruling on SQ-03 (b) and REQ-21 by the ruling on SQ-01. The spec extract's digest at the end is `sha256:5b9de0316dea`; it was `sha256:8c916b9d5268` when the spec was first frozen. Code requirements (REQ-01 to REQ-09) are verified by outer-loop scenarios with canaries, text requirements (REQ-10 to REQ-20) by one presence check per home file, and memory requirements (REQ-21 to REQ-23) by the verifier from the fate table, the memory directory and the backup.

### Scope and kinds

**Scope.** In scope: the memory index's size ceiling in the audit and the write-time guard; the seven message changes of batches M1 to M3; the text moves of batches B1 to B10 and W1 into the homes the placement plan names; the memory pass (deletions, mapping table, the index that remains). Out of scope: the wording of each move (the batch executor writes it from the piece's memory source); any home other than the placement plan's; the open ledger rows behind the plan's seven interim workarounds; an installer guard; the user's secret-disclosure hook (outside the repository); the untracked handoff prompts; other projects' memory indexes (the audit will warn on two of them; nothing here edits them).

**Verification kinds.** Each requirement title carries one kind.

- **code** — behaviour-bearing code. Outer-loop scenarios, and each code requirement has at least one canary: a known-bad input the behaviour must catch. REQ-01 to REQ-09.
- **text** — a text move into a home file whose shape the existing gates already guard (the shipped-artifact isolation check, the rules-manifest and kernel checks, the skill validators, the canonical-block sync). One presence check per home file by the verifier, against the mapping table; no scenario per lesson. REQ-10 to REQ-20.
- **memory** — the memory pass, done by the orchestrator outside the repository and never by a commit. Verified by the verifier from the mapping table, the memory directory and the backup. None of it can be an automated test: the memory directory is machine-local, outside the repository, and the mapping table lives in the gitignored work directory. REQ-21 to REQ-23.

**Reach before a release.** A hook change runs in a live session only after a release, a plugin update and a restart, because the hooks a session runs are the installed copies. Until then a hook requirement (REQ-02, REQ-08, REQ-09) is observable by running the hook from the checkout with a payload on its input, and not through a live session's own tool call. The audit and the scripts behind REQ-03 to REQ-07 are observable at once when run from the checkout; the copies a session reaches through the installed plugin or its command links change only at the release.

**Carried.** A piece is carried by its home when, after its batch's commit has landed: the home file the placement plan names holds, in the section it names, text that says what the piece's memory source says, shown by a grep of the moved text against the source and recorded in the mapping table; a shipped home (skills, rules, agents, the shipped configuration) cites none of this repository's td- or dec- ids, interim workarounds for open ledger rows included; a fact about the harness or an external tool that was observed and not re-probed carries its observation date, and the tool version where one is known; and the file's existing gates pass. A piece the placement plan lets the executor drop only on evidence (already said by the home, or a claim that fails a check of the repository) is recorded with that evidence instead.

**Held.** A piece or memory line is held when it waits on a batch that cannot land yet (W1) or on a user question. A held item is recorded in the mapping table with what it waits on, and is never deleted while held.

**What waits on whom.**

- Q1 (where the standing policy lives): the standing-policy paragraphs and the index lines that point at them stay; nothing in this specification moves them. A ruling for `CLAUDE.local.md` or a maintainer document is carried out as its own follow-on, and REQ-23 then admits the line it retires or rewords.
- Q2 (amend or ride the next state commit): one W1 piece and its memory line are held (REQ-20); nothing else waits on it.
- Q3 (merge style), Q4 (a guard for a bare directory change), Q6 (the secret-disclosure hook's message), Q7 (retiring the old prompts' gotcha sections): no requirement depends on the answer. Q4's memory line stays either way; Q6's file and Q7's prompts are outside the repository.
- Q5 (an installer guard): the B8 note lands either way; a guard would be a separate change.
- The merge of this pipeline's branch to the default branch (the user's): the deletion of every moved piece's memory line (REQ-21). Carried and superseded pieces wait for no merge.
- The `process-principles` merge: W1 only (REQ-20).

### REQ-01: The index audit warns above the ceiling (code)

**When** `scripts/check_memory_index.py` audits a memory index (this project's by default, every index with `--all`, or a given path)
**and** the index holds more than 5,000 bytes or more than 40 lines while staying within the harness load limit (200 lines and 25,000 bytes)
**the system** reports exactly one size warning for that index, naming its bytes, its lines and the ceiling, in the text output and in `--json`; a warning alone leaves the exit status 0; an index at or below both 5,000 bytes and 40 lines draws no size finding; an index past the load limit fails as it does today, with no second size warning; every other finding is judged as today
**so that** an index that starts to regrow is reported at a fifth of the load limit, long before entries stop loading, where today's warning at four fifths let the index grow from 12.2 KB to 17.6 KB unreported.

**Verified by:** outer-loop scenarios with canaries at both edges: an index of 5,001 bytes warns and one of 5,000 does not; an index of 41 lines warns and one of 40 does not.

### REQ-02: The write-time guard warns on a write past the ceiling (code)

**When** a Write or Edit to a memory index reaches `hooks/guard_memory_index.py`
**and** the index the write would leave holds more than 5,000 bytes or more than 40 lines, is larger in bytes or lines than before the write, stays within the load limit, and adds no line the guard refuses today
**the system** lets the write land and returns a warning the writing session reads, naming the index's bytes and lines after the write, the ceiling, and that detail belongs in the topic files; a write that leaves the index at or below both limits, or does not grow it, returns no warning; every refusal the guard makes today is unchanged, and a write the guard cannot judge still passes silently
**so that** whoever grows the index learns at that moment that it has passed its budget, without a block on legitimate work.

**Verified by:** outer-loop scenarios driving the guard from the checkout with a write payload, with canaries: a write from 4,990 to 5,010 bytes lands and warns; a write that ends at exactly 5,000 bytes does not warn; a write that shrinks an index still above the ceiling does not warn. Before a release this is all that can be observed; a live session's own write to its index is judged by the installed copy until the release.

### REQ-03: A blocked-marker stop says how it clears (code)

**When** `scripts/step_loop.py` stops on `next` with cause `blocked-marker` (the step's latest recorded return carried the blocked marker)
**the system** says, in its stop block on stderr and in the next-action section of `HANDOFF.md`, that the stop clears only when the step's block in `IMPLEMENTATION_PLAN.md` is revised once the blocker is resolved and the return is recorded, that the following `next` then issues the step afresh under the revised block, and that an appended iteration-ledger record or an edit of `WIP.md` leaves the stop standing
**so that** an orchestrator clears the stop at the first try instead of editing records the loop ignores.

**Verified by:** an outer-loop scenario over a plan whose step carries a recorded blocked return: both surfaces carry the three statements; canary: after an appended ledger record alone, the stop still stands.

### REQ-04: A refused record names the revised-block cause and the recovery (code)

**When** `scripts/step_loop.py` refuses a `record` because the loop no longer issues the named request (error `request-not-pending`, exit 4: the loop would now issue a different request, or stop, where it would have reissued this one)
**the system** keeps the error code and exit status and adds to its message that revising any step block of `IMPLEMENTATION_PLAN.md` while a request is outstanding produces this refusal, the recovery (put the revised block back as it was when the request was issued, record the request, then re-apply the revision and run `next`), and the order that avoids it (record the outstanding request before revising any step block); the refusal of a request that is neither pending nor recorded is unchanged
**so that** an orchestrator who revised a plan while a request was out recovers without touching attempt lines or ledgers.

**Verified by:** an outer-loop scenario that revises a step block after a request is issued and records it: the refusal carries the cause, the recovery and the order; canary: the unknown-request refusal does not.

### REQ-05: A clean-tree resolver run says why nothing is selected (code)

**When** `scripts/resolve_test_scope.py` runs with no change-set argument (it reads the working-tree diff and the untracked files)
**and** the working tree holds no changed or untracked path
**the system** adds a line on stderr saying it read a clean tree, so it selected nothing, and that `--changed-from` with a base revision judges committed work; standard output (the commands, or the `--json` object) and the exit status 0 are unchanged, and a run that reads any changed path prints no such line
**so that** "nothing to run" on a clean tree is not taken for a green suite over committed work.

**Verified by:** an outer-loop scenario in a clean temporary repository; canary: with one changed path the line is absent.

### REQ-06: The footprint check's wrong-command message states the matching rule (code)

**When** `scripts/check_footprint_criteria.py` reports a measurement row as `wrong-command` (its logged command is not the criterion's command plus options)
**the system** says in that finding's message that the logged command must repeat the criterion's command token by token, in order, and may add only options and their values after them, and that a placeholder in the criterion stands for one whole token, so a placeholder joined to other text inside one token is compared as literal text; the finding's code, severity and stage, and the matching itself, are unchanged
**so that** the measurer re-runs the declared instrument at the first refusal instead of guessing at the rule.

**Verified by:** outer-loop scenarios with a log row that adds a positional to the criterion's command, and with a criterion that joins a placeholder to an option inside one token: both messages carry the rule.

### REQ-07: The principles-pointer test names the file to edit (code, maintainer)

**DROPPED on 2026-11-13 under SQ-07.** The other pipeline now generates the pointer's names from the template's headings, so there is no hand list to forget and no file for a failure message to name. The text below stays as the record of what was planned.

**When** the check in `scripts/test_kernel_authored_texts.py` that holds the principles pointer to the user template's principles fails because a principle is missing from the pointer
**the system** fails with a message naming each missing principle and `claude/kernels/src/principles-pointer.md` as the file to edit
**so that** a principle change is finished in one pass instead of a search for the pointer.

**Verified by:** a test that drives the check with a pointer text lacking one principle and reads the failure message.

### REQ-08: Every commit-gate refusal shows its findings and the way out (code)

**When** the session commit gate `hooks/commit_gate.sh` refuses a tool call whose command carries `git commit`, because `scripts/check_id_citation_discipline.py` found a violation or another check run through the gate refused
**the system** makes the refusal the session reads carry the check's findings (today an id-citation refusal reaches the session with none) and say that no command of that call ran, that the check judged the files as they stood before the call began, and to fix and stage in one call and commit in a separate call; run by hand, by pre-commit or in CI, the id-citation check still shows its findings and keeps its exit codes; a call the gate does not refuse is unchanged
**so that** a refused commit is understood and fixed on the next call instead of being retried in the same bundled form.

**Verified by:** outer-loop scenarios driving the gate from the checkout with a commit payload: over a staged id-citation violation (canary: the refusal carries the finding and the hint) and over a refusal from another check (the hint). Live in sessions only after a release.

### REQ-09: The task-brief reminder says when it is wrong (code)

**When** the task-brief reminder `hooks/remind_task_brief.py` fires because it found no `TASK_BRIEF.md` for the slug a spawn states
**the system** names in its advisory the checkout root it looked under and says that a brief kept in another worktree of the repository, such as a pipeline worktree, is not seen from there, so the advisory is false when the brief lives in that worktree; a found brief still draws no advisory, and the reminder still never blocks a spawn
**so that** an orchestrator in the main checkout does not write a second brief for a pipeline whose brief already exists.

**Verified by:** an outer-loop scenario from the checkout with a spawn payload whose working directory holds no brief; canary: with the brief present, nothing is printed. Live in sessions only after a release.

### REQ-10: Batch B1 lands the step-loop and goal-mode lessons (text)

**When** batch B1's commit has landed
**the system** has each of B1's 12 pieces carried by its home among `skills/ralph-lite/SKILL.md`, `skills/step-loop/SKILL.md` and the new `skills/step-loop/references/stop-recoveries.md`, which the step-loop skill's body links once, one hop away; the skill validators pass
**so that** a session driving a step loop or a goal loop meets the recovery when a stop needs it.

**Verified by:** one presence check per home file (three).

### REQ-11: Batch B2 lands the planning-reference lessons (text)

**When** batch B2's commit has landed
**the system** has each of B2's 25 pieces carried by its home among `skills/software-planning/references/adr-authoring-protocols.md`, `skills/software-planning/references/agent-pipeline-details.md`, `skills/software-planning/references/decomposition-guide.md`, `skills/software-planning/references/document-templates.md`, `skills/software-planning/references/intra-step-review.md` and `skills/spec-driven-development/references/calibration-procedure.md`; the reference validators pass
**so that** an orchestrator, planner or reviewer reading the reference that governs a step meets the lesson there.

**Verified by:** one presence check per home file (six).

### REQ-12: Batch B3 lands the hook-crafting lessons (text)

**When** batch B3's commit has landed
**the system** has each of B3's 4 pieces carried by its home among `skills/hook-crafting/SKILL.md`, `skills/hook-crafting/references/output-patterns.md` and `skills/hook-crafting/references/testing-guide.md`, and the testing guide's example forwards a hook payload the way the moved gotcha prescribes (corrected in place, not given a second lesson)
**so that** a hook author meets the registration, environment, output and payload pitfalls in the skill that governs hooks.

**Verified by:** one presence check per home file (three).

### REQ-13: Batch B4 lands the operational-skill lessons (text)

**When** batch B4's commit has landed
**the system** has each of B4's 14 pieces carried by its home among `skills/co/SKILL.md`, `skills/handoff/SKILL.md`, `skills/merge-worktree/SKILL.md`, `skills/release/SKILL.md`, `skills/resume-rework/SKILL.md`, `skills/test/SKILL.md` and `skills/triage-debt/SKILL.md`; the test skill's step that tells the reader to change directory gives the same instruction without a directory change, in the same edit; the merge and release skills keep the safety contract of the PR conventions they already follow
**so that** each lesson applies at the moment of its action: a commit, a merge, a release, a test run, a handoff, a triage or a rework.

**Verified by:** one presence check per home file (seven).

### REQ-14: Batch B5 lands the testing and gate lessons in path-scoped rules (text)

**When** batch B5's commit has landed
**the system** has each of B5's 11 pieces carried as a bullet in an existing section (no new heading) of `rules/swe/gate-liveness.md`, `rules/swe/id-citation-discipline.md` or `rules/swe/testing-conventions.md`; each rule keeps its path scope; `rules/_manifest.yaml` is regenerated and its check passes; `rules/_audience.yaml` is unchanged
**so that** a lesson loads when a matching file is touched, and no always-loaded or spawn-delivered text grows.

**Verified by:** one presence check per rule file (three) and the manifest check.

### REQ-15: Batch B6 lands the testing and language-skill lessons (text)

**When** batch B6's commit has landed
**the system** has each of B6's 8 pieces carried by its home among `skills/mcp-crafting/contexts/python.md`, `skills/python-development/SKILL.md`, `skills/python-development/references/patterns-and-examples.md`, `skills/testing-strategy/SKILL.md`, `skills/testing-strategy/references/gate-canaries.md` and `skills/testing-strategy/references/test-selection.md`, and the moved text carries no selection-size counts (they drift)
**so that** a session writing or running tests meets the lesson in the skill it loads for that work.

**Verified by:** one presence check per home file (six).

### REQ-16: Batch B7 lands the CI and crafting lessons (text)

**When** batch B7's commit has landed
**the system** has each of B7's 7 pieces carried by its home among `skills/cicd/references/patterns-and-examples.md`, `skills/evidence-appraisal/SKILL.md`, `skills/python-prj-mgmt/references/uv.md`, `skills/rule-crafting/SKILL.md` and `skills/skill-crafting/references/user-invoked-skills.md`, each probed fact stamped with its observation date and the tool version it was seen on
**so that** a session building CI, a rule or a skill meets the pitfall with the evidence of when it held.

**Verified by:** one presence check per home file (five).

### REQ-17: Batch B8 lands the first maintainer-document lessons (text)

**When** batch B8's commit has landed
**the system** has each of B8's 12 pieces carried by its home among `README_DEV.md`, `claude/config/README.md`, `dashboard_app/README.md`, `docs/observability.md` and `eval/README.md`, the twelfth being the lesson re-homed from B10 into `README_DEV.md`: how a test that converses with the installer stands in for the optional tools the installer offers; `claude/config/README.md` gains a short note that its instructions file is generated from its template; the exporters' narrowed-copy claim lands only if a check of the repository confirms it, and otherwise that half is dropped with the reason in the mapping table
**so that** a maintainer of this repository finds the lesson in the document about the surface being maintained.

**Verified by:** one presence check per home file (five).

### REQ-18: Batch B9 lands the second maintainer-document lessons (text)

**When** batch B9's commit has landed
**the system** has each of B9's 15 pieces carried by its home among `agents/CLAUDE.md`, `docs/claude-code-limitations.md`, `docs/lean-spawn-how-to.md`, `docs/lean-spawn-kernels.md`, `docs/rework-dispatch.md`, `rules/CLAUDE.md` and `scripts/CLAUDE.md`; each new limitations entry names its upstream issue and ledger row, or says that none exists; each fact observed once carries its observation date; a version claim the source did not verify is not copied; the three nested instruction files stay loaded on demand
**so that** a maintainer meets the harness limitation or the instrument quirk where that surface is documented.

**Verified by:** one presence check per home file (seven).

### REQ-19: Batch B10 lands the code-comment lessons (text)

**When** batch B10's commit has landed
**the system** has each of B10's 5 pieces carried in a comment or docstring of `.github/workflows/reusable-ci-autofix.yml`, `eval/tests/test_harness_judge_client.py`, `scripts/check_agent_lifecycle_pairing.py`, `scripts/context_baseline.py` or `tests/onboard_project_test.sh`, with no behaviour change (every test that selects these files passes as before); no acceptance or end-to-end test file is edited
**so that** a reader of that code meets the pitfall at the line it concerns.

**Verified by:** one presence check per home file (five) and the derived test selection for the five files.

### REQ-20: Batch W1 lands after the other pipeline merges, without its held piece blocking the rest (text)

**When** the `process-principles` pipeline has merged to main and its changes are present on this pipeline's branch
**and** batch W1's commit has landed
**the system** has each W1 piece except the one held for the user's ruling on Q2 carried by its home in `skills/software-planning/references/coordination-details.md` or `skills/software-planning/references/tech-debt-ledger.md`; the held piece lands only after that ruling, in the form the ruling picks, and its memory line stays until then; while `process-principles` has not merged, W1 lands nothing, its memory lines are recorded as held, and no other batch waits for it
**so that** the delegation and ledger lessons land in the reference that governs them without colliding with the other pipeline's edits, and one open question holds back one piece only.

**Verified by:** one presence check per home file (two), and the mapping table's held rows when W1 or its held piece has not landed.

### REQ-21: A memory line goes only with its proof (memory)

**When** the orchestrator deletes a memory index line, a topic file, or part of one, outside the repository and never through a commit
**and** a backup of the whole memory directory, taken before the first memory edit, exists
**the system** deletes it only when its proof holds at deletion time, by the piece's fate: a moved piece only after the commit carrying it is on the default branch (the merge is the user's) and a grep run then, on the default branch, shows its home says what the memory source says, so a commit present only on this pipeline's branch never suffices; a carried piece only after its cited file and line are re-read and still carry it; a superseded piece only with its evidence (a commit, a decision or a release) checked in the repository and recorded; a carried or superseded piece waits for no merge, its proof being already on the default branch; a topic file only once every piece it holds has met its proof; a held piece never; and a link from a surviving topic file to a deleted one is removed with the deleted file
**so that** no lesson is lost on its way out of memory, no session of this repository is left with neither the memory line nor its carrier (the memory is shared by every session, worktrees included), and every deletion traces to what replaced or retired it.

**Verified by:** the verifier, from each deletion's row in the mapping table (its proof) and the memory directory read against the backup. Not an automated test, and the order of a deletion against its commit is attested by the orchestrator's record rather than reconstructed afterwards.

### REQ-22: The mapping table gives every item one class and one fate (memory)

**When** the memory pass closes, or the pipeline closes with items still held
**the system** has, in `MEMORY_MAP.md` under the placement plan's piece ids, every index line and topic file of the backup and every gotcha of the named handoff prompts in exactly one class (process knowledge; superseded, retired or closed; live project status; the user's preference) and exactly one fate: moved (home and section, carrying commit, grep evidence), carried (citation), superseded (evidence), kept, or held (what it waits on); no item is unaccounted for and none has two fates
**so that** a later reader can tell where each lesson went, or why it left.

**Verified by:** the verifier's totality check of the table against the backup's index and files and the placement plan's pieces. Not an automated test.

### REQ-23: The index that remains holds only status and preferences (memory)

**When** the last deletion the pipeline can make has happened
**the system** leaves a `MEMORY.md` that is the placement plan's twelve lines byte for byte, except a line a user ruling rewords or retires, plus one line for each topic file still held by a waiting batch or an unanswered question; every line is a pointer of at most 150 characters; `scripts/check_memory_index.py` reports no failing finding and no size warning for it; the topic files left are the placement plan's twelve plus the held ones
**so that** every session and spawn here loads only live status and the user's preferences, about a tenth of today's index.

**Verified by:** the verifier reads the index against the placement plan's text and the mapping table's held rows, and runs the audit on it (FC-05 records its size). Not a committed test: the index is machine-local.

### Observable Surface

- `MEMORY.md` — this project's auto-memory index, one pointer line per memory to a topic file beside it; the harness loads its first 200 lines or 25KB, whichever comes first (Claude Code memory documentation, read 2026-11-12)
- `scripts/check_memory_index.py` — the existing index audit, with `--all` and `--json`; exit 0 no failing finding, 1 a failing finding, 2 a read error; today it fails past 200 lines or 25,000 bytes and warns past four fifths of either
- `hooks/guard_memory_index.py` — the existing guard on a Write or Edit to a memory index; today it refuses a write that adds a line over 150 characters, adds a line that is not a pointer, or grows the index past the load limit
- `scripts/step_loop.py` — the step-loop driver, verbs `next` and `record`; stop cause `blocked-marker`; error `request-not-pending` with exit 4; it reads `IMPLEMENTATION_PLAN.md`, `WIP.md` and the iteration ledger, and writes `HANDOFF.md` on a stop
- `scripts/resolve_test_scope.py` — the test-scope resolver, with `--changed-from` and `--json`
- `scripts/check_footprint_criteria.py` — the footprint gate; its finding reason `wrong-command`
- `scripts/test_kernel_authored_texts.py` — the kernel-texts test; `claude/kernels/src/principles-pointer.md` — the principles pointer's source text
- `hooks/commit_gate.sh` — the session commit gate; `scripts/check_id_citation_discipline.py` — the id-citation check it runs; `git commit`
- `hooks/remind_task_brief.py` — the task-brief reminder; `TASK_BRIEF.md` — the task brief it looks for
- `PLACEMENT_PLAN.md` and `MEMORY_MAP.md` — this task's placement plan (pieces, homes, batches, the remaining index's exact text) and its mapping table, in the task's work directory
- `process-principles` — the other pipeline whose merge W1 waits for
- `tmp/memory-backup-2026-11-12/` — the memory backup taken 2026-11-12
- `CLAUDE.local.md` — the home the placement plan proposes for the standing policy (Q1)
- B1 homes: `skills/ralph-lite/SKILL.md`, `skills/step-loop/SKILL.md`, `skills/step-loop/references/stop-recoveries.md` (new, named by the placement plan)
- B2 homes: `skills/software-planning/references/adr-authoring-protocols.md`, `skills/software-planning/references/agent-pipeline-details.md`, `skills/software-planning/references/decomposition-guide.md`, `skills/software-planning/references/document-templates.md`, `skills/software-planning/references/intra-step-review.md`, `skills/spec-driven-development/references/calibration-procedure.md`
- B3 homes: `skills/hook-crafting/SKILL.md`, `skills/hook-crafting/references/output-patterns.md`, `skills/hook-crafting/references/testing-guide.md`
- B4 homes: `skills/co/SKILL.md`, `skills/handoff/SKILL.md`, `skills/merge-worktree/SKILL.md`, `skills/release/SKILL.md`, `skills/resume-rework/SKILL.md`, `skills/test/SKILL.md`, `skills/triage-debt/SKILL.md`
- B5 homes: `rules/swe/gate-liveness.md`, `rules/swe/id-citation-discipline.md`, `rules/swe/testing-conventions.md`, with `rules/_manifest.yaml` (regenerated) and `rules/_audience.yaml` (untouched)
- B6 homes: `skills/mcp-crafting/contexts/python.md`, `skills/python-development/SKILL.md`, `skills/python-development/references/patterns-and-examples.md`, `skills/testing-strategy/SKILL.md`, `skills/testing-strategy/references/gate-canaries.md`, `skills/testing-strategy/references/test-selection.md`
- B7 homes: `skills/cicd/references/patterns-and-examples.md`, `skills/evidence-appraisal/SKILL.md`, `skills/python-prj-mgmt/references/uv.md`, `skills/rule-crafting/SKILL.md`, `skills/skill-crafting/references/user-invoked-skills.md`
- B8 homes: `README_DEV.md`, `claude/config/README.md`, `dashboard_app/README.md`, `docs/observability.md`, `eval/README.md`
- B9 homes: `agents/CLAUDE.md`, `docs/claude-code-limitations.md`, `docs/lean-spawn-how-to.md`, `docs/lean-spawn-kernels.md`, `docs/rework-dispatch.md`, `rules/CLAUDE.md`, `scripts/CLAUDE.md`
- B10 homes: `.github/workflows/reusable-ci-autofix.yml`, `eval/tests/test_harness_judge_client.py`, `scripts/check_agent_lifecycle_pairing.py`, `scripts/context_baseline.py`, `tests/onboard_project_test.sh`
- W1 homes: `skills/software-planning/references/coordination-details.md`, `skills/software-planning/references/tech-debt-ledger.md`
- Footprint instruments: `scripts/measure_token_budget.py` (the always-loaded budget the brief names), `python3 scripts/measure_token_budget.py --json`, `python3 scripts/check_agent_prompt_size.py --json`, `python3 scripts/measure_selection_size.py --compare-ref`, `wc -c -l <index>`
- Health gates: `python3 scripts/sync_canonical_blocks.py --check`, `python3 scripts/regenerate_rules_manifest.py --check`, `python3 scripts/generate_kernels.py --check`, `python3 scripts/check_kernel_manifest.py`, `python3 scripts/check_gate_liveness.py`

## Spec Question Answers

Spec questions are pipeline-local. SQ-01 to SQ-03 and the base-moved note come from the spec; SQ-07 was raised at plan step 17; the acceptance-design stage numbered its own questions from 1 again, so they carry the prefix AD here.

Not part of the extract. Each names its evidence and whom it is for.

**Base moved (orchestrator note, 2026-11-13; for the verifier and the user).** The branch took in the default branch (`98b6ff2a`, `44ef7f0a`), so this pipeline's change is `main..HEAD` and the base tree is the default branch at `d2ee23a2`. The base's own always-loaded reading is 19,988 tokens: 70 more than the 19,918 above, from the other pipeline's rule sentence, measured under its own criterion. FC-01's limit keeps its meaning, "no rise from this pipeline's own commits": the baseline is the base tree's reading, the final is this head's. Baselines for FC-01 to FC-04 are therefore re-taken on the default branch's checkout at `d2ee23a2`, and the verify stage runs with `--base-ref main`. The two baseline rows at `92cb5c10` (written under step 23's wording) measured this branch's tree, not the base, and stay as history.

**SQ-01 (for the user): where must a carrying commit land before its memory line goes?** The user's rule is "delete a memory line only after its artifact commit lands" (handoff prompt, section D). Evidence: auto memory is per repository and shared across worktrees (Claude Code memory documentation, read 2026-11-12), so it also loads in main-checkout sessions; a worktree session loads main's rules (piece P-119), and hooks and command-linked scripts reach sessions only after a release (P-096). A line deleted once its commit is on the pipeline branch leaves every session outside the worktree with neither carrier until the merge to main (text batches) or the next release (M1 to M3 and the hooks). Options: (a) delete at the branch commit, the literal reading, accepting that window (the backup bounds the loss); (b) delete after the merge to main for text and after the release for messages.
**Ruled by the orchestrator (resume, under the user's standing delegation; listed for the user):** the stricter reading. A moved piece's line goes only once its carrying commit is on the default branch and the grep shows its home says the same; carried and superseded pieces wait for no merge. Written into REQ-21 and its criterion.
**Not written: the ruling's premise that no release is needed.** It contradicts section D ("A hook change goes live only after a release") and the machine state read on 2026-11-12: the marketplace install `~/.claude/plugins/cache/bit-agora/praxion/0.63.0` is a full copy, not links to the checkout, so only sessions launched with `praxion-claude-dev` (`--plugin-dir` on the working tree, README_DEV lines 461-465) load skills, agents and hooks from the checkout; a plain `claude` session runs the 0.63.0 copy until a release and plugin update. Scripts linked into `~/.local/bin` do point at the checkout. Open for the orchestrator or user: whether a moved piece whose carrier reaches plain sessions only through the installed copy (the two hook messages P-127 and P-128 at least, and shipped skill text for such sessions) also waits for the release before its memory line goes. REQ-21 as written requires the merge and is silent on the release.

**SQ-02 (for the context-engineer, via the orchestrator): two homes are near their size ceilings.** `skills/software-planning/references/coordination-details.md` is 763 lines against the 800-line fail ceiling for references (T04, `check_agent_prompt_size.py`), before `process-principles` edits it, and W1 brings 11 pieces into it: 37 lines of room. `skills/rule-crafting/SKILL.md` is 419 lines, already past its 400-line warning (fail at 600), and B7 grows it by one bullet. FC-03 bounds both; if W1's pieces do not fit after `process-principles` lands, which ones re-home is the context-engineer's call.
**Ruled (orchestrator):** no requirement change; FC-03 stays the bound. When W1 is due, the context-engineer decides any re-home; the planner sequences W1 last and marks that check.

**SQ-03 (for the context-engineer and the planner): two batch file sets do not match the code.** (a) M1: P-002's refusal text is built in `scripts/_step_loop_record.py` (`_pending`, lines 313-322: "record failed because the loop does not reissue it for ..."), which is in no batch; M1's set (`scripts/_step_loop_render.py`, `scripts/step_loop.py`) needs it. (b) B10: P-124's home `tests/acceptance/drivers/hand_path_command.py` lies under `tests/acceptance/`, read-only for the implementer (`rules/swe/testing-conventions.md` § Test File Organization); that edit needs the test-engineer, or another home.
**Ruled (orchestrator):** (a) a design and planning matter, no requirement change: the design phase names the module and the planner adds it to M1's step files. (b) P-124 is re-homed to `README_DEV.md` in batch B8 (the lesson, how a test that converses with the installer stands in for the optional tools it offers, is about maintaining this repository's tests). **This overrides the placement plan's home for one piece**, because its planned home is an acceptance driver the implementer may not edit. REQ-17 now carries 12 pieces in the same five files, REQ-19 5 pieces in five files; the batch file sets stay disjoint (B8 already held `README_DEV.md`).

**Note.** The placement plan's move table calls the installer-guard question Q6 (row of P-099) while its question list numbers it Q5; this spec uses the list's numbering.

**SQ-07 (raised by the orchestrator at plan step 17, 2026-11-13; for the user and the verifier): is REQ-07 still wanted?** REQ-07 asked the check that holds the kernels' principles pointer to the template's principles to fail naming each missing principle and the pointer's source file as the file to edit. The `process-principles` pipeline had merged first (`d278f8c2` on main, taken in by `98b6ff2a`): the pointer's count and names are now filled by the generator from the template's headings, and the pointer source holds two markers, not a list. A principle can no longer be missing by a forgotten hand edit, and naming that file as the one to edit would now be wrong advice. The lesson the requirement moved no longer describes the system.
**Answered (under the standing delegation):** REQ-07 is dropped, superseded by the generated pointer. Its acceptance file is removed by a test-engineer, plan step 18 becomes a recorded no-op, and the placement plan marks the piece superseded. **Resolved in:** `92cb5c10`.

**AD-SQ-O1 (raised by the orchestrator, 2026-11-12): the base moved before any production commit.** The first base, `f3988742`, carried a ledger line that failed an older pipeline's identity guard; main fixed it afterwards. The branch held only the acceptance-design and design commits, so it was rebased onto `54cc2f9c` (backup tag `d-pre-rebase-backup`), and the ten outer-loop files re-run at the new base read the same (34 red, 29 guards). **Answered. Resolved in:** `118a9a3c`.

**AD-SQ-01 to AD-SQ-06 (raised by the orchestrator; REQ-14): six frozen guards pin text the rule lessons moved.** Commit `57fd739d` added bullets and table rows to `rules/swe/gate-liveness.md`, `rules/swe/id-citation-discipline.md` and `rules/swe/testing-conventions.md`; no existing line was removed or reworded (checked line by line against the design commit). Two kinds of pin followed:
- AD-SQ-01, the moved-not-cut guard: it holds each paragraph of each rule by digest and reads a bullet or table row added to a list as a reworded paragraph. Seven entries changed.
- AD-SQ-02 to AD-SQ-06, the Cursor export digests of the same three rules in five fixtures (`kernel_pilot`, `routing_facts`, `model_routing_move`, `project_gating`, `adr_rule_move`).

**Answered:** re-pinned under plan step 19's rule, those entries alone, with each guard's own digest driver; the seven rewordings as declared-rewording rows in the guard's own mechanism, the frozen fixture untouched; every other key byte-identical to the parent. **Resolved in:** `3d9d68c0`.

### Assumptions taken

- **A1. The ceiling is 5,000 bytes or 40 lines**, the placement plan's recommendation from the data (the index that must stay is 12 lines and 1,698 bytes; the worst case with W1 still held is 21 lines and about 2.9 KB). The harness limit was re-read on 2026-11-12: first 200 lines or 25KB, whichever comes first; the audit already assumes 200 lines and 25,000 bytes and warns at 0.8 of either (160 lines or 20,000 bytes). The user ratifies the number at the spec checkpoint.
- **A2. "Crosses" means the write leaves the index above the ceiling and larger than before.** That covers an index already over the ceiling, so every growth past the budget warns, while a write that shrinks or keeps the size never does. A strict crossing (below before, above after) would warn once and then fall silent, which is how the index regrew.
- **A3. One ceiling for every index both tools judge**, project and agent indexes in every project, since neither tool tells them apart. Effect today: under `--all`, two other projects' indexes (15,614 and 11,843 bytes) draw the warning; nothing here edits them.
- **A4. The ceiling warning replaces the four-fifths warning** (one size warning, not two); the load-limit failure and every guard refusal stay.
- **A5. P-127 covers every refusal through the commit gate**, the code-quality hook's own block exit included (`hooks/check_code_quality.py` exits 2 itself, which bypasses the gate's translated branch), because the piece merges memory row 126, whose refusal comes from that hook. The id-citation findings are lost today because the check prints them on stdout (`check_id_citation_discipline.py` lines 558-564) and the harness shows stderr on a block.
- **A6. P-001.** A `blocked-marker` stop exists only after `record` took the blocked return; the series stays marked "until the step's block is revised" (`_step_loop_state.is_done`), and a hand-appended ledger record is ignored because the driver reads only request-bearing records (`driver_records`). The message carries the clearing rule, the negative, and the record-then-revise order.
- **A7. P-002.** The driver cannot tell why the loop stopped reissuing a request (a request id carries no block digest), so the message states the revised-block cause as one that produces the refusal, not as a diagnosis.
- **A8. P-129, P-130, P-131, P-128 behave as their lessons say.** Observed 2026-11-12: the resolver on this clean worktree prints `nothing-to-run` with "working-tree (0 path(s))" and exits 0; the `wrong-command` message reads "... which is not ... with options added"; the pointer assertion at line 170 carries no message; the reminder resolves its root from the spawning session's working directory.
- **A9. The memory index is an unregistered footprint by necessity** (outside the repository, so no registry glob can name it): an FP04 info finding is expected for FC-05.
- **A10. Footprint limits judge this pipeline's own commits.** If W1 needs `process-principles` taken into this branch, baselines are re-taken after that merge (design phase).
- **A11. Spawn-startup tokens are declared, not measured**: the instrument is a paid probe needing the user's go, the edits reach no spawn's start, and the kernel generator's check is the free evidence.

## Traceability

Rendered from the reconciled `traceability.yml` (one merged file, plan step 22, no fragments), with the requirement titles from the spec above. Each row lists the unit tests first, then the outer-loop acceptance nodes, then the implementation paths. Status is read from `TEST_RESULTS.md` (the last block reads `pass=10477 fail=0 skip=13`) and the verifier's reports.

- **REQ-10 to REQ-20 are text requirements.** Their `tests:` entries are the existing real-tree guards each batch's Check runs (gates the file class must keep passing), not content checks; the content check is the verifier's presence check per home file, recorded in each status.
- **REQ-21 to REQ-23 are memory requirements** and have no committed test by the spec's own kinds (the memory directory is machine-local and outside the repository). Their status comes from `VERIFICATION_REPORT.md`'s memory-pass verification of 2026-11-15, and their evidence is the fate table `MEMORY_MAP.md` (pipeline-local) and the backup `tmp/memory-backup-2026-11-15/`, as named in each row.
- **REQ-07 was dropped** (SQ-07): its three lists are empty in the record on purpose.
- **A gap in the record, filled here:** the reconciled file left REQ-20's `implementation:` list empty. Its home, `skills/software-planning/references/coordination-details.md`, is taken from the delta verification and the step 24 learnings.
- **Self-test at archival:** the matrix has 23 data rows, so it is not hollow. 19 requirements carry `tests:` or `acceptance:` entries beside an implementation path; the three memory requirements carry the verifier's evidence in place of a test; REQ-07 carries nothing, by design (dropped). No requirement is left without evidence except that one.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01: The index audit warns above the ceiling | `scripts/test_check_memory_index.py::test_index_size_counts_lines_and_utf8_bytes`<br>`scripts/test_check_memory_index.py::test_the_index_budget_is_strictly_below_the_load_limit_on_both_axes`<br>`scripts/test_check_memory_index.py::test_canary_one_byte_over_the_budget_warns_and_exactly_at_it_is_quiet`<br>`scripts/test_check_memory_index.py::test_canary_one_line_over_the_budget_warns_and_exactly_at_it_is_quiet`<br>`scripts/test_check_memory_index.py::test_the_over_budget_detail_names_lines_bytes_and_the_budget`<br>`scripts/test_check_memory_index.py::test_canary_past_the_load_limit_fails_with_no_second_size_finding`<br>`scripts/test_check_memory_index.py::test_budget_warning_fires_when_a_write_grows_the_index_past_the_budget`<br>`scripts/test_check_memory_index.py::test_budget_warning_is_quiet_for_a_write_that_ends_exactly_at_the_ceiling`<br>`scripts/test_check_memory_index.py::test_budget_warning_is_quiet_for_a_write_that_shrinks_an_index_still_above_it`<br>`scripts/test_check_memory_index.py::test_budget_warning_is_quiet_for_a_write_that_stays_under_the_budget`<br>`scripts/test_check_memory_index.py::test_budget_warning_leaves_growth_past_the_load_limit_to_the_gate`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_an_index_just_over_the_ceiling_draws_one_size_warning_naming_its_size`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_an_index_at_the_ceiling_draws_no_finding`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_the_text_output_carries_the_size_warning`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_an_index_near_the_load_limit_still_draws_only_one_size_warning`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_an_index_past_the_load_limit_fails_with_no_second_size_finding`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_every_index_under_the_config_directory_is_judged_with_all`<br>`tests/acceptance/test_memory_index_audit_warns_above_its_budget.py::test_a_content_finding_is_still_reported_beside_the_size_warning` | `scripts/check_memory_index.py::IndexSize`<br>`scripts/check_memory_index.py::INDEX_BUDGET`<br>`scripts/check_memory_index.py::LOAD_LIMIT`<br>`scripts/check_memory_index.py::_size_findings`<br>`scripts/check_memory_index.py::budget_warning` | PASS (step 2: `pass=37 fail=0`; verifier: PASS) |
| REQ-02: The write-time guard warns on a write past the ceiling | `hooks/test_guard_memory_index.py::test_canary_a_write_past_the_byte_ceiling_lands_and_warns`<br>`hooks/test_guard_memory_index.py::test_canary_an_edit_adding_the_forty_first_line_warns`<br>`hooks/test_guard_memory_index.py::test_a_write_ending_exactly_at_the_ceiling_draws_no_warning`<br>`hooks/test_guard_memory_index.py::test_a_write_that_shrinks_an_index_still_above_the_ceiling_draws_no_warning`<br>`hooks/test_guard_memory_index.py::test_a_growing_write_well_under_the_ceiling_draws_no_warning`<br>`hooks/test_guard_memory_index.py::test_a_refusal_wins_over_the_warning`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_write_that_crosses_the_byte_ceiling_lands_and_warns_the_session`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_an_edit_that_adds_the_forty_first_line_lands_and_warns_the_session`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_write_that_ends_exactly_at_the_ceiling_draws_no_warning`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_write_that_shrinks_an_index_still_over_the_ceiling_draws_no_warning`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_growing_write_well_under_the_ceiling_draws_no_warning`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_write_adding_an_over_long_line_to_an_index_over_the_ceiling_is_still_refused`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_write_past_the_load_limit_is_still_refused`<br>`tests/acceptance/test_memory_index_write_warns_past_its_budget.py::test_a_payload_the_guard_cannot_judge_passes_silently`<br>`tests/e2e/test_a_regrown_memory_index_is_caught_at_the_write_and_by_the_audit.py::test_a_write_past_the_budget_lands_with_a_warning_and_the_audit_then_reports_it` | `hooks/guard_memory_index.py::main`<br>`hooks/guard_memory_index.py::_emit` | PASS (step 3: `pass=24 fail=0`, forced review closed; verifier: PASS) |
| REQ-03: A blocked-marker stop says how it clears | `scripts/test_loop_render_texts.py::test_the_blocked_stop_block_says_how_the_stop_clears`<br>`scripts/test_loop_render_texts.py::test_the_blocked_handoff_paragraph_says_how_the_stop_clears`<br>`tests/acceptance/test_a_blocked_stop_says_how_it_clears.py::test_the_blocked_stop_says_how_it_clears`<br>`tests/acceptance/test_a_blocked_stop_says_how_it_clears.py::test_an_appended_ledger_record_alone_leaves_the_stop_standing`<br>`tests/acceptance/test_a_blocked_stop_says_how_it_clears.py::test_an_edit_of_wip_alone_leaves_the_stop_standing`<br>`tests/acceptance/test_a_blocked_stop_says_how_it_clears.py::test_revising_the_step_block_lets_next_issue_the_step_afresh` | `scripts/_step_loop_render.py::_ACTIONS` | PASS (step 4: `pass=188 fail=0`; verifier: PASS) |
| REQ-04: A refused record names the revised-block cause and the recovery | `scripts/test_loop_cli_next.py::test_a_record_refused_after_a_step_block_revision_names_the_cause_and_the_way_back`<br>`scripts/test_loop_cli_next.py::test_the_refusal_of_an_unknown_request_does_not_mention_a_revision`<br>`tests/acceptance/test_a_refused_record_names_the_revision_and_the_recovery.py::test_the_refusal_after_a_mid_flight_revision_says_what_happened_and_what_to_do`<br>`tests/acceptance/test_a_refused_record_names_the_revision_and_the_recovery.py::test_following_the_recovery_records_the_request_and_resumes_the_loop`<br>`tests/acceptance/test_a_refused_record_names_the_revision_and_the_recovery.py::test_the_refusal_of_an_unknown_request_is_unchanged` | `scripts/_step_loop_record.py::_pending` | PASS (step 4: `pass=188 fail=0`; verifier: PASS) |
| REQ-05: A clean-tree resolver run says why nothing is selected | `scripts/test_resolve_test_scope.py::test_a_clean_working_tree_says_on_stderr_why_nothing_was_selected`<br>`scripts/test_resolve_test_scope.py::test_a_clean_working_tree_json_run_keeps_its_stdout_and_says_why_on_stderr`<br>`scripts/test_resolve_test_scope.py::test_a_run_not_reading_the_bare_working_tree_prints_no_clean_tree_line`<br>`scripts/test_resolve_test_scope.py::test_a_run_that_reads_a_changed_path_prints_no_clean_tree_line`<br>`tests/acceptance/test_a_clean_tree_resolver_run_says_why_nothing_is_selected.py::test_a_clean_tree_run_says_on_stderr_that_it_read_a_clean_tree_and_names_changed_from`<br>`tests/acceptance/test_a_clean_tree_resolver_run_says_why_nothing_is_selected.py::test_a_clean_tree_run_prints_the_same_stdout_as_before`<br>`tests/acceptance/test_a_clean_tree_resolver_run_says_why_nothing_is_selected.py::test_a_run_that_reads_a_changed_path_prints_no_clean_tree_line` | `scripts/resolve_test_scope.py::main` | PASS (step 5: `pass=173 fail=0`; verifier: PASS) |
| REQ-06: The footprint check's wrong-command message states the matching rule | `scripts/test_check_footprint_criteria_judge.py::test_the_wrong_command_message_states_the_matching_rule`<br>`tests/acceptance/test_a_wrong_command_finding_states_the_matching_rule.py::test_the_wrong_command_message_states_the_matching_rule`<br>`tests/acceptance/test_a_wrong_command_finding_states_the_matching_rule.py::test_the_wrong_command_finding_keeps_its_code_and_severity`<br>`tests/acceptance/test_a_wrong_command_finding_states_the_matching_rule.py::test_a_command_the_rule_admits_is_not_a_wrong_command` | `scripts/check_footprint_criteria.py::_row_defects` | PASS (step 5: `pass=173 fail=0`; verifier: PASS) |
| REQ-07: The principles-pointer test names the file to edit | none (dropped) | none | DROPPED under SQ-07 (no test and no implementation by design; the acceptance file was removed in `92cb5c10`) |
| REQ-08: Every commit-gate refusal shows its findings and the way out | `hooks/test_commit_gate.py::test_a_blocked_refusal_carries_stdout_findings_and_the_hint_on_stderr`<br>`hooks/test_commit_gate.py::test_a_native_exit_two_keeps_its_stderr_and_gains_the_hint`<br>`hooks/test_commit_gate.py::test_a_refusal_without_findings_still_carries_the_hint`<br>`hooks/test_commit_gate.py::test_a_pass_prints_its_stdout_unchanged_and_no_hint`<br>`hooks/test_commit_gate.py::test_a_non_blocking_findings_exit_keeps_its_stdout_and_gains_no_hint`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_an_id_citation_refusal_carries_its_finding_to_the_session`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_the_refusal_says_what_happened_to_the_call_and_how_to_retry`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_another_checks_refusal_still_carries_that_checks_own_finding`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_the_id_citation_check_run_by_hand_still_shows_its_findings_and_exits_one`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_the_id_citation_check_run_by_hand_over_clean_code_exits_zero`<br>`tests/acceptance/test_a_commit_gate_refusal_shows_its_findings_and_the_way_out.py::test_a_commit_the_gate_does_not_refuse_passes_without_a_hint` | `hooks/commit_gate.sh` | PASS (step 6: `pass=91 fail=0`, forced review closed; re-review `pass=166` at `d87be46b`; verifier: PASS) |
| REQ-09: The task-brief reminder says when it is wrong | `hooks/test_remind_task_brief.py::test_missing_brief_advisory_names_the_root_it_looked_under`<br>`hooks/test_remind_task_brief.py::test_missing_brief_advisory_says_another_worktrees_brief_is_not_seen`<br>`hooks/test_remind_task_brief.py::test_a_found_brief_still_draws_no_advisory_for_the_root_it_looked_under`<br>`tests/acceptance/test_the_task_brief_reminder_says_where_it_looked.py::test_the_advisory_names_the_checkout_root_it_looked_under`<br>`tests/acceptance/test_the_task_brief_reminder_says_where_it_looked.py::test_the_advisory_says_a_brief_in_another_worktree_is_not_seen`<br>`tests/acceptance/test_the_task_brief_reminder_says_where_it_looked.py::test_a_found_brief_draws_no_advisory` | `hooks/remind_task_brief.py::_process` | PASS (step 6: `pass=91 fail=0`; verifier: PASS) |
| REQ-10: Batch B1 lands the step-loop and goal-mode lessons | `tests/acceptance/test_ralph_lite_skill.py`<br>`tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/ralph-lite/SKILL.md`<br>`skills/step-loop/SKILL.md`<br>`skills/step-loop/references/stop-recoveries.md` | PASS (step 7: `pass=27 fail=0`; verifier presence check 12 of 12; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-11: Batch B2 lands the planning-reference lessons | `tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/software-planning/references/adr-authoring-protocols.md`<br>`skills/software-planning/references/agent-pipeline-details.md`<br>`skills/software-planning/references/decomposition-guide.md`<br>`skills/software-planning/references/document-templates.md`<br>`skills/software-planning/references/intra-step-review.md`<br>`skills/spec-driven-development/references/calibration-procedure.md` | PASS (step 8: `pass=2 fail=0`; verifier presence check, 1 WARN fixed; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-12: Batch B3 lands the hook-crafting lessons | `tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/hook-crafting/SKILL.md`<br>`skills/hook-crafting/references/output-patterns.md`<br>`skills/hook-crafting/references/testing-guide.md` | PASS (step 9: `pass=2 fail=0`; verifier presence check 4 of 4; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-13: Batch B4 lands the operational-skill lessons | `tests/acceptance/test_merge_triggers_texts.py`<br>`tests/commands/test_merge_worktree_convergence.py`<br>`tests/commands/test_resume_rework.py`<br>`tests/acceptance/test_shipped_blocks_stay_in_sync.py` | `claude/canonical-blocks/commit-process.md`<br>`skills/co/SKILL.md`<br>`skills/cop/SKILL.md`<br>`skills/handoff/SKILL.md`<br>`skills/merge-worktree/SKILL.md`<br>`skills/release/SKILL.md`<br>`skills/resume-rework/SKILL.md`<br>`skills/test/SKILL.md`<br>`skills/triage-debt/SKILL.md` | PASS (step 10: `pass=61 fail=0`; verifier presence check 14 of 14; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-14: Batch B5 lands the testing and gate lessons in path-scoped rules | `scripts/test_regenerate_rules_manifest.py`<br>`tests/acceptance/test_both_source_rules_stay_whole.py` | `rules/swe/gate-liveness.md`<br>`rules/swe/id-citation-discipline.md`<br>`rules/swe/testing-conventions.md`<br>`rules/_manifest.yaml` | PASS (step 11: `pass=32 fail=0`; six frozen guards re-pinned in step 19; verifier presence check 11 of 11; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-15: Batch B6 lands the testing and language-skill lessons | `tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/mcp-crafting/contexts/python.md`<br>`skills/python-development/SKILL.md`<br>`skills/python-development/references/patterns-and-examples.md`<br>`skills/testing-strategy/SKILL.md`<br>`skills/testing-strategy/references/gate-canaries.md`<br>`skills/testing-strategy/references/test-selection.md` | PASS (step 12: `pass=2 fail=0`; verifier presence check 8 of 8; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-16: Batch B7 lands the CI and crafting lessons | `tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/cicd/references/patterns-and-examples.md`<br>`skills/evidence-appraisal/SKILL.md`<br>`skills/python-prj-mgmt/references/uv.md`<br>`skills/rule-crafting/SKILL.md`<br>`skills/skill-crafting/references/user-invoked-skills.md` | PASS (step 13: `pass=2 fail=0`; verifier presence check 7 of 7; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-17: Batch B8 lands the first maintainer-document lessons | `tests/acceptance/test_shipped_blocks_stay_in_sync.py` | `README_DEV.md`<br>`claude/config/README.md`<br>`dashboard_app/README.md`<br>`docs/observability.md`<br>`eval/README.md` | PASS (step 14: `pass=1 fail=0`; verifier presence check; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-18: Batch B9 lands the second maintainer-document lessons | `scripts/test_generate_kernels.py`<br>`scripts/test_check_kernel_manifest.py` | `agents/CLAUDE.md`<br>`docs/claude-code-limitations.md`<br>`docs/lean-spawn-how-to.md`<br>`docs/lean-spawn-kernels.md`<br>`docs/rework-dispatch.md`<br>`rules/CLAUDE.md`<br>`scripts/CLAUDE.md` | PASS (step 15: `pass=136 fail=0`; verifier presence check 15 of 15; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-19: Batch B10 lands the code-comment lessons | `scripts/test_check_agent_lifecycle_pairing.py`<br>`scripts/test_context_baseline.py` | `.github/workflows/reusable-ci-autofix.yml`<br>`eval/tests/test_harness_judge_client.py`<br>`scripts/check_agent_lifecycle_pairing.py`<br>`scripts/context_baseline.py`<br>`tests/onboard_project_test.sh` | PASS (step 16: `pass=67 fail=0`; verifier presence check 5 of 5; text requirement: the tests are the existing guards for the file class, not content checks) |
| REQ-20: Batch W1 lands after the other pipeline merges, without its held piece blocking the rest | `tests/acceptance/test_shipped_blocks_stay_in_sync.py`<br>`tests/acceptance/test_skill_descriptions_stay_reproducible.py` | `skills/software-planning/references/coordination-details.md` | PASS (step 24 gate: `pass=2 fail=0`; delta verification: 2 WARN, both fixed in `cc77138b` and `c55721e2`; ten of eleven pieces landed, the eleventh held for Q2) |
| REQ-21: A memory line goes only with its proof | none by design (memory requirement) | the fate table `MEMORY_MAP.md` (pipeline-local)<br>the backup `tmp/memory-backup-2026-11-15/` | PASS (verifier, memory pass): all 128 recorded searches re-run on main and in the installed copy, each carrying commit an ancestor of `v0.65.0`; 62 carried and 46 superseded re-checked; 119 deletions byte-compared with the backup. Evidence: the fate table `MEMORY_MAP.md` and the backup `tmp/memory-backup-2026-11-15/` |
| REQ-22: The mapping table gives every item one class and one fate | none by design (memory requirement) | the fate table `MEMORY_MAP.md` (pipeline-local)<br>the backup `tmp/memory-backup-2026-11-15/` | PASS (verifier, memory pass): 256 piece rows, 134 topic-file rows, 134 index-line rows and 73 handoff-gotcha rows, each in one class and one fate, none unaccounted for. Evidence: the fate table `MEMORY_MAP.md` and the backup `tmp/memory-backup-2026-11-15/` |
| REQ-23: The index that remains holds only status and preferences | none by design (memory requirement) | the project's auto-memory index `MEMORY.md` (outside the repository) | PASS (verifier, memory pass): the plan's twelve lines less one plus four held, byte for byte; audit 0 failing, 0 warning; FC-05 2091 bytes and 15 lines. Evidence: the surviving index, the fate table `MEMORY_MAP.md` and the backup `tmp/memory-backup-2026-11-15/` |
