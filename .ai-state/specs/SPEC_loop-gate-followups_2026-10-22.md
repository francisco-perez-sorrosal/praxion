# Spec: loop-gate-followups (the step-loop driver, its Stop guard, the flip gate, agent hygiene)

**Task slug**: `loop-gate-followups`
**Feature**: Close the eleven rows the last two pipelines left (td-463, td-465, td-478 to td-486): the step-loop gate runs each pocket detached under its own declared bound, keeps a cut-off run's evidence and carries it into the next attempt, and a record call resumes across its ceiling; test selection scopes bare names, layout pairings and single-segment stems to their pocket; a [CONFLICT] or [BLOCKED] return commits nothing and a marked step is never done, with `status` and `next` reading one state, goal steps included; the Stop guard bounds its per-Stop reading; `status` reports each step's attempt cap; the flip gate shares one standing leaf, judges gathered evidence and names an unreadable earlier part; the return contract has every agent reap its background work; and an outer-loop allowlist path class lets the acceptance-design commit carry a scanner entry its fixtures need.
**Tier**: Full (21 requirements over 108 files; 27 of 32 charged spawns by hand count; the step loop used 30 of 30 iterations, steps 2 to 6 and 20 to 23 ran outside the loop).
**Pipeline branch**: `worktree-loop-gate-followups`
**Start date**: 2026-10-21
**End date**: 2026-10-22
**Archived**: 2026-10-22 (post-merge; fast-forwarded to main at `5ac5f62e`, finalized in `3e66a088`)
**Status**: completed -- first verdict FAIL (goal steps escaped the marked-return rule), fixed in place with a red-first scenario (`e0b8e1b3`, `2e3b81ff`); re-verification PASS WITH FINDINGS (0 FAIL, 8 WARN). Open residue: td-488, td-490, td-491, td-492, td-494 (the `-q` pocket part), td-495, td-496.
**ADRs**: `dec-466` (architectural: one standing leaf, gathered evidence, an unreadable earlier part named), `dec-467` (architectural: the gate's pocket runs; narrows `dec-386`), `dec-468` (behavioral: a marked return commits nothing, one state), `dec-469` (behavioral: the outer-loop fixture allowlist class; narrows `dec-410`), `dec-470` (behavioral: the return contract reaps background work), `dec-471` (behavioral: bare names scoped to a pocket; narrows `dec-411`), `dec-472` (behavioral: `status` reports each step's attempt cap; narrows `dec-464`), `dec-473` (behavioral: the Stop guard's per-Stop bounds; narrows `dec-465`).
**Evidence base**: the commits from `b035777a` to `5ac5f62e`; the calibration row dated 2026-10-22; the root suite (14848 passed, one gate-probe test that asserts the real observation log untouched failed while a concurrent agent wrote it and passed alone, td-496) and eval pocket (2707 passed) on their CI commands at `bba98e08`; the selection differential (`REQ03_DIFFERENTIAL.md`, 2007 dropped pairs, every one crossing pockets directly or through its chain).

## Feature Summary

The previous pipeline's gate could not finish a step that touched the eval pocket inside its single 540 s bound, committed a scope its agent had called incomplete, and left five smaller rows. This pipeline bootstrapped a new gate outside the loop (steps 2 to 6, each scope run by hand), then ran the rest under it: per-pocket declared bounds (eval 1,200 s, root 1,500 s), detached re-attachable runs with a `gate-running` refusal so `record` resumes, kept evidence of a cut-off run fed to the next prompt, the marked-return rule, one state for `status` and `next`, the bounded Stop guard, the per-step attempt cap, pocket-scoped test selection, the flip gate's shared leaf and gathered evidence, the return-contract reaping sentence and the allowlist path class. Reviews found real defects (steps 4, 6, 9, 11, 14 and 22 each needed a revise round); the iteration budget ran out at step 20 and steps 20 to 23 ran outside the loop; the final verifier's FAIL (goal steps) was fixed in place.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py`. REQ ids are pipeline-local and appear in no code.

Complexity: large (21 requirements over eleven ledger rows, across the step-loop driver, its Stop guard and orientation, the test-scope resolver, the kernel flip gate, the agent definitions and the acceptance-design procedure). Brownfield baseline: the archived loop-gate-hardening spec (the Stop guard, the orientation, the flip gate's evidence; dec-463, dec-464, dec-465), the step-loop driver specs (dec-432, dec-427, dec-434) and the derived test selection (dec-406, dec-411, dec-420); these requirements extend or narrow them and restate none.

Vocabulary used below (behavioural, not design):

- A **pocket** is a directory with its own test runner configuration (the root, the eval pocket, and the others the resolver finds); a **derived scope** is the set of test runs the resolver lists for a step's changed files, one or more per pocket.
- A **gate** is what record runs on an agent's return: the derived scope and the step's check, written as one block of the step result file ending on the deciding result line.
- A **series** is the run of attempts at one version of a step's block; revising the block opens a fresh series.

### Observable Surface

- `step_loop.py` — the step-loop driver command, with its verbs next, record and status (dec-432)
- `TEST_RESULTS.md` — the step result file the driver writes each gate block into
- `python3 scripts/check_test_results_shape.py` — the existing result-file shape checker, with its 1,024-byte green-section ceiling (dec-386)
- `resolve_test_scope.py` — the existing test-scope resolver
- `eval/src/praxion_evals/adherence/cli.py` — an existing eval-pocket file, the recorded over-selection case
- `eval/src/praxion_evals/adherence/lineage.py` — an existing eval-pocket file, the recorded over-selection case
- `cli.py` — a file name many pockets share
- `lineage.py` — the second file name of the recorded case
- `python3 scripts/check_gates_bite.py --gate selection-audit` — the existing selection audit: every tracked file a default-suite test reads must select that test
- `python3 scripts/check_kernel_manifest.py` — the existing kernel and flip-gate commit gate
- `python3 scripts/generate_kernels.py --check` — the existing kernel generator's freshness check
- `python3 scripts/check_agent_shared_blocks.py` — the existing gate holding the shared agent blocks identical
- `python3 scripts/sync_canonical_blocks.py --check` — the existing shipped-block drift check
- `agents/implementer.md` — the implementer definition
- `agents/test-engineer.md` — the test-engineer definition
- `agents/verifier.md` — the verifier definition, whose commit-order audit cites the path classes
- `.gitleaks.toml` — the repository's secret-scanner configuration and its allowlist
- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` — the existing orientation acceptance test
- `codex/config/export-codex-agents.py` — the existing Codex agent export
- `cursor/config/export-cursor-rules.py` — the existing Cursor rule export
- `python3 scripts/measure_token_budget.py --json` — the existing always-loaded and listing token instrument
- `python3 scripts/check_agent_prompt_size.py --json` — the existing prompt-size instrument
- `python3 scripts/measure_selection_size.py --compare-ref <args...>` — the existing selection-size instrument, run against a reference revision
- `/usr/bin/time -p uv run --directory eval pytest -q` — the eval pocket's suite on its CI shape, timed

### REQ-01: A bare common file name never pulls another pocket's tests into a scope

**When** a change touches a file in one pocket
**and** a test in another pocket is connected to that file only by its bare file name (a mention with no directory part, or a test named after a file of that name)
**the system** does not select that test on that connection, while a test that imports the file, names it by a path that includes a directory part, or declares it as a dependency is still selected, in any pocket
**so that** a common name such as `cli.py` cannot pull a whole other pocket into a step's scope. Closes td-463 (selection, basename).

### REQ-02: An import selects a test only through statements that can load the changed file

**When** a module's import names a module by a short name that several files in the repository share
**the system** connects that import only to the files it can load from where it is written, never to a same-named file in another pocket that it cannot load, and selects a test through imports only when import statements present in the files connect it to the changed file
**so that** no test is selected through an import edge that no file has. Closes td-463 (selection, import edge).

### REQ-03: A narrower selection never hides a test the change can break

**When** a change touches a file that no remaining connection ties to any test, or the resolver cannot account for a change
**the system** still widens to that pocket's full suite or the whole suite and names the path, exactly as before, and every tracked file a default-suite test reads or loads still selects that test when it changes, as the selection audit checks
**so that** the narrowing of REQ-01 and REQ-02 removes only connections that do not exist, and widening stays the safe direction. Closes td-463 (safety of the narrowing).

### REQ-04: A pocket whose tests legitimately take longer can pass the gate

**When** a step's derived scope includes a pocket whose selected tests take longer than today's single 540-second bound (the eval pocket's whole suite ran 822 seconds)
**and** those tests pass
**the system** lets that pocket's run finish and decides the step on its counts, within the step-loop skill's discipline for a record call (each call bounded at ten minutes; a call cut off is run again and continues without repeating a pocket run already finished), with no person running the scope by hand
**so that** an eval-pocket step whose own tests pass is never failed by the clock. Closes td-463 (bound).

### REQ-05: Every gate run still has a finite bound, and a cut-off run is red

**When** a pocket's run exceeds the time bound the gate allows that pocket
**the system** stops that run, records the gate as red (never passed, never read as having no failures) and states in the step's result block the bound it applied
**so that** a hung run can neither pass a step nor hold the loop without end. Closes td-463 (bound stays finite).

### REQ-06: A cut-off run names its pocket and keeps every failure seen

**When** a gate run is cut off by its bound
**the system** records in the step's result block which pocket ran out of time, the bound, every test failure that pocket's output had shown before the cut, and the counts and failures of every other pocket run that finished
**so that** a real failure seen before the bound is never hidden behind "timed out". Closes td-463 (evidence of a cut-off run).

### REQ-07: The next attempt's prompt carries the earlier gate's evidence, from the driver alone

**When** the driver issues a further attempt at a step whose earlier attempt's gate was red
**the system** puts into that attempt's prompt, from its own record of the earlier gate, the failing tests and, for a cut-off run, the pocket that ran out of time, within the prompt's size bound and with a pointer to the full record when cut, with no person editing the prompt or writing anything the prompt depends on
**so that** the next attempt starts from the evidence the gate saw, never from "timed out" alone. Closes td-463 (evidence channel).

### REQ-08: A green gate block summarises its selection and stays within the shape ceiling

**When** the driver writes a green gate block for a step
**the system** writes, for the derived scope, each pocket run with its test-file count, its test count and whether its selection was narrow or widened, in place of the full command, so the block stays within the shape checker's 1,024-byte green-section ceiling however many tests the scope selects, and a reader can still tell from the block which changed files the scope was derived from
**so that** green sections pass the shape check and the selection stays reproducible. Closes td-479.

### REQ-09: A [CONFLICT] return commits nothing and keeps its edits

**When** an agent's return carries [CONFLICT] (or [BLOCKED], SQ-01), whatever its check shows
**the system** makes no commit, leaves the step's progress line unticked, leaves every edit the attempt made in the working tree as it is, records the return in the iteration ledger with no commit, and stops the loop for a person with a stop that names the step, the marker and each uncommitted file the attempt left
**so that** HEAD never holds a scope its agent called incomplete, and no edit is silently discarded. Closes td-478 (commit).

### REQ-10: A conflicted step stays open until its scope is resolved

**When** a step's latest return carried [CONFLICT]
**the system** keeps the step open (never verified, never done), counts the conflicting attempt as one used attempt of the step's current series and one used iteration of the loop, stops with the same cause on every next until the step's block is revised in the plan, and after the revision issues the step as attempt 1 of a fresh series whose prompt names the uncommitted edits the conflicting attempt left
**so that** a resolution of the scope, not a retry of the same scope, is what moves the step on, and the kept edits reach the attempt that resumes the work. Closes td-478 (counting and revision).

### REQ-11: status and next read one state

**When** status is run, or next is run, for the same task over the same task files and tree
**the system** reports for every step, in status, the state next acts on (verified, open, running, marked, failed, exhausted, done outside the loop, not started), derived once for both, including after a plan revision and after a conflicting return
**so that** status never shows a step verified that next re-issues, nor the reverse. Closes td-478 (one state).

### REQ-12: The Stop guard's work per Stop is bounded and lets the stop through at the bound

**When** a Stop occurs while a task in the checkout has an issued request its iteration ledger does not record, a stale one issued long ago included
**the system**'s Stop guard reads a bounded amount of transcript evidence (bounded in the number of transcripts, in bytes read, and by a deadline of its own well inside the hook's 10-second registration) and, when a bound is reached before it finds an ended agent to hold, lets the stop through with no output
**so that** a stale request can neither make every Stop of the session read every transcript nor run the hook into the harness timeout. Closes td-480 (bound).

### REQ-13: The guard costs nothing outside a loop and holds as today inside one

**When** a Stop occurs with no step loop in the checkout, or with every issued request recorded
**the system** imports nothing beyond the guard's own file, reads no transcript and lets the stop through; when a recent agent of this session has ended unrecorded and no bound is reached, it holds the stop once with the record command, as today; any failure lets the stop through
**so that** the bound changes nothing a loop-free project or a healthy loop sees. Closes td-480 (non-regression).

### REQ-14: The 64-character task-name boundary is held from both sides

**When** a task's directory name is a slug of exactly 64 characters
**the system**'s guard reads that task and can hold its ended request, while a name of 65 characters is not read as a task
**so that** the size bound of the held message, which relies on that limit, is pinned on the accepted side as well as the refused one. Closes td-480 (fold-in).

### REQ-15: Each step's attempt cap is reported by status and read by the orientation

**When** status is asked for its JSON form
**the system** reports for every step the cap its attempts are counted against (the driver's attempt cap for an ordinary step, the step's own iteration budget for a goal step), and the post-compaction orientation renders a step's attempts against the cap status reports for that step
**so that** a goal step's attempts render against its own budget, and a change to the driver's cap shows in the orientation with no copy of the cap left to drift. Closes td-481.

### REQ-16: The flip gate's two readings of a run's standing agree on its shape

**When** the flip gate reads a cited run's standing from the run index and from the results files
**the system** accepts the same well-formed values and refuses the same malformed values, field by field, with the same reason, in both readings, and the gate's run readers still load with the standard library alone, no eval code and no third-party package
**so that** the two readings cannot drift apart, and the gate stays runnable under a bare interpreter. Closes td-482.

### REQ-17: A cited run with an unreadable results file is refused naming that file

**When** a run that a switched record cites is a continued run (its results file records that it continues an earlier run, as the adherence entry records a continuation, so its lineage holds earlier parts the record does not itself cite)
**and** the results file of one of those earlier parts cannot be read or parsed (not text, or not JSON)
**the system** refuses the record with a finding that names that earlier part's results file and why it could not be read, and never reports the run as a lineage disagreement because that part is missing; a cited run whose own results file cannot be read or parsed is still refused naming that file, as at the base commit
**so that** whoever repairs the record knows which file to fix, rather than chasing a lineage that only looks different because one part was dropped. Closes td-483.

### REQ-18: The gate's judging of cited runs reads no file

**When** the flip gate judges the runs switched records cite
**the system** gathers every results file those runs need before judging begins and judges from what was gathered, reading no file during judging, so the same gathered evidence always gives the same findings
**so that** the judging stays pure and can be tested without a filesystem. Closes td-485.

### REQ-19: The orientation acceptance test type-checks clean without changing what it proves

**When** pyright checks the orientation acceptance test
**the system** reports no error in it, and each of its scenarios asserts what it asserted at the base commit and keeps its outcome, the change made by the test-engineer and never by the implementer
**so that** the outer loop's typing debt closes without weakening a scenario or breaking acceptance independence. Closes td-484.

### REQ-20: Every agent reaps its background work before its final message

**When** a Praxion agent, the implementer and the test-engineer among them, has started background work (a test run, a watcher, any process it left running)
**the system** requires of it, through every agent definition and every role text generated from the same source, identically, that it stop or await every such job before writing its final message, and that every watcher it starts carry a bound (a timeout or an iteration cap), a watcher that matches processes by name excluding shells
**so that** an agent's own leftover job never marks its return possibly interim, nor keeps looping after the agent ends. Closes td-465.

### REQ-21: The acceptance-design commit may carry the scanner allowlist entry its fixtures need

**When** a fixture the acceptance designer writes would be flagged by the secret scanner
**the system**'s acceptance-design procedure lets the designer add, in the acceptance-design commit, an allowlist entry anchored inside the outer-loop test directories (with comments), and the path classes read such a change as part of the outer loop, decidable from the commit alone; any other change to the scanner configuration (a rule, an entry reaching another path, a wildcard or alternation reaching beyond those directories, a removed entry) stays production; the verifier's commit-order audit applies the same classes by name
**so that** acceptance independence holds as written when a fixture trips the scanner, and the allowance cannot become a route for production changes ahead of the scenarios. Closes td-486.

### Row coverage

| Row | Requirements |
|---|---|
| td-463 | REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07 |
| td-465 | REQ-20 |
| td-478 | REQ-09, REQ-10, REQ-11 |
| td-479 | REQ-08 |
| td-480 | REQ-12, REQ-13, REQ-14 |
| td-481 | REQ-15 |
| td-482 | REQ-16 |
| td-483 | REQ-17 |
| td-484 | REQ-19 |
| td-485 | REQ-18 |
| td-486 | REQ-21 |

## Acceptance Criteria

Standing constraints, cited below as NN-1 to NN-8. They bind every requirement.

- **NN-1** No semantics of Praxion's philosophy or process is lost: no rule, kernel, skill, agent or procedure text loses meaning; text this change adds is added, and nothing is reworded away.
- **NN-2** Nothing is cut to meet a number. No text is trimmed and no test is dropped to fit a footprint bound or a time bound; a bound that cannot be met is reported, never met by cutting.
- **NN-3** The process reaches sessions and spawns through artifacts (rules, kernels, agent definitions, hooks, gates, the driver's own records), never through memory. No requirement relies on a memory index or on an orchestrator note a prompt depends on.
- **NN-4** Gates stay deterministic: each gate's outcome is a function of the tree, the recorded files and the commands' output. In test selection, widening stays the safe direction: a narrower selection never hides a test the change can break.
- **NN-5** An absent, failing or timed-out hook falls back to today's behaviour: the Stop proceeds, and an orientation that cannot read the driver says so.
- **NN-6** The Codex agent export and the Cursor rule export differ from the base only where intended; the Codex hooks bridge is checked if a hook's registration changes.
- **NN-7** Claims are bounded non-regression only: every existing suite and gate passes, and each footprint stays within its stated bound; no claim of improvement beyond what is measured.
- **NN-8** No paid run, push or release in this pipeline. No artifact prints, quotes or records the subscription token.

Checklist (each item names the requirements and constraints it discharges):

- [x] **AC-01** For a change confined to `eval/src/praxion_evals/adherence/cli.py`, and separately for one confined to `eval/src/praxion_evals/adherence/lineage.py`, the resolver at the final head selects no root-pocket test whose only connection to the changed file is its bare name (a mention of `cli.py` or `lineage.py` with no directory part, or a test named after that file that sits in another pocket), and none through an import that cannot load the changed file; every test it still selects in another pocket is connected by import statements present in the files, by a mention that includes a directory part, or by a declared dependency. (REQ-01, REQ-02)
- [x] **AC-02** A test in one pocket that imports a file of another pocket, names it by a path with a directory part, or declares it as a dependency is still selected when that file changes (an eval-pocket test importing a root script is selected when that script changes); a changed file that no remaining connection ties to a test still widens its pocket or the whole suite and is named as widened; the selection audit passes at the final head; FC-04 holds. (REQ-01 to REQ-03; NN-4)
- [x] **AC-03** A step whose derived scope includes a pocket whose selected tests pass but take longer than 540 seconds passes the gate on its counts, with no person running the scope by hand; a record call cut off at the step-loop skill's ten-minute ceiling and run again completes without re-running a pocket run that had already finished. (REQ-04)
- [x] **AC-04** A pocket run that exceeds the time bound the gate allows it is cut off; the gate is red, never passed and never "no failures"; the result block states the bound applied. (REQ-05)
- [x] **AC-05** In a gate where one pocket's run is cut off after its output showed two failing tests and another pocket's run finished with one failing test and its counts, the step's result block names the pocket that ran out of time and the bound, lists all three failing tests, and carries the finished pocket's counts. (REQ-06)
- [x] **AC-06** The next attempt's prompt for that step carries those three failing tests and the name of the pocket that ran out of time, taken from the driver's own record of the earlier gate; with more failures than the prompt's bound allows, it carries the newest that fit and a marker naming where the full record is; nothing the orchestrator writes is needed for this. (REQ-07; NN-3)
- [x] **AC-07** A green gate block for a derived scope of more than 100 test files across two pockets is at most 1,024 bytes as `python3 scripts/check_test_results_shape.py` measures it, and names each pocket run with its test-file count, its test count and whether its selection was narrow or widened. (REQ-08)
- [x] **AC-08** A [CONFLICT] return whose check passes leaves HEAD where it was, the step's progress line unticked, every file the attempt edited byte-identical in the working tree, one iteration-ledger record with no commit, and a stop for a person naming the step, the marker and each uncommitted file; the same holds for a [BLOCKED] return (SQ-01). (REQ-09)
- [x] **AC-09** After that stop, next stops again with the same cause until the step's block is revised in the plan; after the revision, next issues attempt 1 of a fresh series whose prompt names the uncommitted files the conflicting attempt left; the loop's iteration count includes the conflicting attempt. (REQ-10)
- [x] **AC-10** For every state a step can be in (verified, verified then revised, marked by a conflict or a blocker, running, failed, exhausted, done outside the loop, not yet started), the state status reports for that step equals the state next acts on, over the same task files and tree. (REQ-11)
- [x] **AC-11** With a stale task whose unrecorded request was issued long before the session's other agents and a session holding many transcripts, one Stop's guard work stays within its count, size and time bounds and lets the stop through when a bound is reached; with no step loop in the checkout it imports nothing beyond its own file and reads no transcript; with a recent agent of this session ended unrecorded it holds the stop once, with the record command, as today. (REQ-12, REQ-13; NN-5)
- [x] **AC-12** A task named with exactly 64 characters is read by the guard and its ended request held; a name of 65 characters is not read as a task. (REQ-14)
- [x] **AC-13** Status in its JSON form gives each step's attempt cap (the driver's attempt cap for an ordinary step, the iteration budget for a goal step); the post-compaction orientation renders a goal step's attempts against its own budget and an ordinary step's against the driver's cap; with the driver's cap changed, the orientation follows with no edit to the orientation. (REQ-15)
- [x] **AC-14** For each typed field of a run's standing, the run-index reading and the results-file reading accept the same well-formed values and refuse the same malformed values with the same reason; the gate's run readers load in an interpreter where neither the eval package nor any third-party package can be imported. The verifier finds one definition of a standing and one set of typed-read helpers serving both readers (structural, verifier-judged). (REQ-16)
- [x] **AC-15** A switched record citing a continued run, whose earlier part (one the record does not cite) has a results file that is not text or not JSON, is refused by `python3 scripts/check_kernel_manifest.py` with a finding naming that earlier part's file and why it could not be read, and with no lineage-disagreement finding; a record citing a run whose own results file is not text or not JSON is still refused naming that file, as at the base commit. (REQ-17)
- [x] **AC-16** The gate's judging of cited runs, given gathered evidence and then denied every file read, gives the same findings as with the files present; gathering reads each results file a cited run needs before judging begins. (REQ-18)
- [x] **AC-17** pyright reports no error in `tests/acceptance/test_compaction_orientation_follows_the_driver.py`; each of its scenarios asserts what it asserted at the base commit and keeps its outcome; the change lands in a test-engineer commit. (REQ-19)
- [x] **AC-18** Every agent definition, `agents/implementer.md` and `agents/test-engineer.md` among them, and the role texts generated from the same source carry, identically, the obligation to stop or await every background job the agent started before its final message and to bound every watcher by a timeout or an iteration cap, a watcher matching processes by name excluding shells; `python3 scripts/check_agent_shared_blocks.py` and `python3 scripts/generate_kernels.py --check` pass. The residual is stated: a gate proves the text is present, not that an agent complies. (REQ-20; NN-1, NN-3)
- [x] **AC-19** An acceptance-design commit whose change to `.gitleaks.toml` only adds allowlist entries anchored inside the outer-loop test directories, plus comments, is read by the commit-order audit as earlier than the first production commit; one that adds an entry reaching any other path, adds or edits a rule, widens an entry beyond those directories with a wildcard or alternation, or removes an entry is production and fails the audit when it precedes the scenarios; the acceptance designer's procedure lets it write such an entry and name it in its return; `agents/verifier.md` cites the class by name, with that golden bad case and good case. (REQ-21; NN-1)
- [x] **AC-20** Health guards: `python3 scripts/generate_kernels.py --check`, `python3 scripts/check_kernel_manifest.py`, `python3 scripts/check_agent_shared_blocks.py`, `python3 scripts/sync_canonical_blocks.py --check` and the agent-crafting validator on each edited definition pass; the root suite and the eval pocket pass on their CI commands; ruff and pyright are clean on every touched file; the hook-registration gates pass; `codex/config/export-codex-agents.py` (roots normalised before diffing) and `cursor/config/export-cursor-rules.py` differ from the base only where intended. (NN-4 to NN-7)
- [x] **AC-21** Each decision the design records is categorised by the architectural test (a new shared definition for td-482 or a responsibility moved for td-485 and td-463 is architectural, with a Disconfirmation section); an earlier decision this change narrows (dec-463, dec-464, dec-465, dec-410) is related by the protocol that fits. (NN-1)
- [x] **AC-22** FC-01 to FC-05 hold, each with its recorded measurement; no paid run, push or release happened; no artifact contains the subscription token. (NN-2, NN-7, NN-8)

### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | always-loaded-tokens | governed always-loaded total, in tokens, on the current ruler | at or below | 24,800 tokens | baseline: 24,800 tokens at the pipeline base (ruler claude-sonnet-5-5) | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | listing-tokens | skill and agent description listing, in tokens, on the current ruler | at or below | 14,268 tokens | baseline: 14,268 tokens at the pipeline base, the frozen listing ceiling | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | prompt-size | prompt-size findings across agent definitions, and the line count of each edited definition | at or below | no new finding (2 warn, 0 fail) and every edited definition below its warn ceiling (400 lines standard; the verifier's fixed pair) | baseline: 2 warn, 0 fail; implementer 226, test-engineer 356, verifier 490 lines | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-04 | test-selection-size | root pocket over the instrument's change sets: widened-run count, and narrow-run p90 in test files | at or below | widened count equal to the reference's; narrow p90 at or below the reference's | reference: the resolver at the pipeline base, run by the instrument over the same tree and change sets | `python3 scripts/measure_selection_size.py --compare-ref <args...>` |
| FC-05 | eval-pocket-gate-time | eval pocket whole-suite wall time on its CI shape, in seconds | below | the time bound the gate allows an eval-pocket run at the final head, with at least 20 percent headroom | reference: the gate's eval-pocket bound as built (540 s today, when the pocket ran 822 s unbounded) | `/usr/bin/time -p uv run --directory eval pytest -q` |

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| spawn-startup-tokens | its only instrument starts headless sessions billed to the user's subscription, which this pipeline forbids (NN-8); always-loaded content is bounded by FC-01 and each definition's growth by FC-03 (the context review measured one added sentence, about 59 tokens per spawn); the orchestrator asks the user before any such run (SQ-03) |
| hook-latency | no instrument exists; the Stop guard's own per-Stop bound is a behavioural requirement (REQ-12) proven on planted inputs, and the orientation hook keeps its existing subprocess bound |
| spawn-count | the only spawn-count command counts a pipeline that has already run, not a change; the path-class edit changes no spawn |

## Traceability Matrix

Rendered from `traceability.yml` at archival (reconciled at the final step). `Status` is the re-verification's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 8 -- `scripts/test__python_selection.py` (test_a_layout_pairing_never_crosses_a_pocket, test_a_layout_pairing_inside_one_pocket_still_selects, test_a_layout_pairing_picks_among_candidates_of_its_own_pocket_only, test_a_bare_name_literal_never_crosses_a_pocket, test_a_bare_name_literal_inside_one_pocket_still_selects, test_a_slash_literal_still_crosses_a_pocket, test_a_glob_literal_still_crosses_a_pocket, test_a_declared_dependency_still_crosses_a_pocket) | 6 -- `tests/acceptance/test_selection_ignores_bare_names_across_pockets.py` (test_a_root_test_tied_only_by_the_bare_name_is_not_selected_for_an_eval_change, test_an_eval_test_tied_only_by_the_bare_name_is_not_selected_for_a_root_change, test_a_recorded_eval_file_selects_no_root_test_by_its_name_alone, test_a_root_test_naming_the_file_with_a_directory_part_is_selected, test_a_root_test_declared_for_an_eval_file_is_selected, test_inside_one_pocket_the_same_connections_still_select) | `scripts/_python_selection.py` | met |
| REQ-02 | 4 -- `scripts/test__python_selection.py` (test_a_short_name_import_never_reaches_a_shared_name_in_another_pocket, test_a_short_name_import_reaches_every_match_in_its_own_pocket, test_a_short_name_import_reaches_a_name_only_one_file_in_the_repository_bears, test_a_dotted_multi_segment_import_still_crosses_a_pocket) | 4 -- `tests/acceptance/test_selection_ignores_bare_names_across_pockets.py` (test_a_short_name_import_that_loads_a_sibling_is_not_tied_to_another_pockets_file, test_an_eval_test_loading_a_root_script_by_import_is_selected_when_the_script_changes, test_this_repositorys_eval_test_importing_a_root_script_is_still_selected, test_the_eval_pockets_own_importer_is_still_selected) | `scripts/_python_selection.py` | met |
| REQ-03 | 1 -- `scripts/test__python_selection.py` (test_a_path_whose_last_connection_was_cross_pocket_widens) | 1 -- `tests/acceptance/test_selection_ignores_bare_names_across_pockets.py` (test_a_change_only_a_bare_name_reached_widens_naming_the_path) | `scripts/_python_selection.py` | met |
| REQ-04 | 4 -- `scripts/test__step_loop_pocket_shell.py` (test_a_run_that_exits_is_read_as_finished_with_its_output_and_code, test_a_finished_run_is_read_again_never_run_again, test_attaching_to_a_run_in_progress_starts_no_second_process, test_a_run_still_inside_its_bound_when_the_caller_gives_up_is_still_running) | 1 -- `tests/acceptance/test_step_loop_gate_keeps_its_evidence.py` (test_a_record_call_cut_off_and_run_again_never_repeats_a_finished_pocket_run) | `scripts/_step_loop_io.py`, `scripts/_step_loop_pocket_runs.py`, `scripts/_step_loop_record.py`, `scripts/_step_loop_record_gate.py`, `scripts/test__step_loop_pocket_shell.py`, `scripts/test_loop_cli_record_caps.py`, `scripts/test_loop_cli_record_gate.py`, `scripts/test_loop_io_vcs.py` | met |
| REQ-05 | 7 -- `scripts/test__step_loop_pocket_runs.py` (test_a_pocket_with_no_override_and_no_declaration_gets_the_default, test_an_override_for_the_pocket_beats_its_declaration, test_a_malformed_override_entry_is_skipped_with_a_warning_naming_it, test_a_bound_of_no_positive_finite_seconds_cannot_be_built); `scripts/test__step_loop_pocket_shell.py` (test_a_run_past_its_bound_is_killed_with_its_whole_group_and_read_as_cut_off, test_the_bound_runs_from_the_recorded_start_not_from_the_call_that_attaches, test_a_run_that_exited_but_took_longer_than_its_bound_is_cut_off_all_the_same) | 1 -- `tests/acceptance/test_step_loop_gate_keeps_its_evidence.py` (test_a_pocket_run_past_its_bound_is_cut_off_and_the_gate_is_red) | `scripts/_step_loop_io.py`, `scripts/_step_loop_pocket_runs.py`, `scripts/_step_loop_record_gate.py`, `scripts/test_loop_cli_record_gate.py`, `scripts/test_loop_io_vcs.py` | met |
| REQ-06 | 4 -- `scripts/test__step_loop_pocket_runs.py` (test_the_failed_and_error_ids_of_a_plain_verbose_log_come_back_in_log_order, test_the_failed_and_error_ids_of_an_xdist_log_come_back_in_log_order, test_an_id_shown_twice_is_kept_once_at_its_first_place); `scripts/test__step_loop_pocket_shell.py` (test_a_run_past_its_bound_is_killed_with_its_whole_group_and_read_as_cut_off) | 1 -- `tests/acceptance/test_step_loop_gate_keeps_its_evidence.py` (test_a_cut_off_block_names_the_pocket_the_bound_and_every_failure_seen) | `scripts/_step_loop_pocket_runs.py`, `scripts/_step_loop_record_gate.py`, `scripts/test__step_loop_pocket_runs.py`, `scripts/test_loop_cli_record_gate.py` | met |
| REQ-07 | 1 -- `scripts/test_loop_gate_evidence.py` ((module)) | 3 -- `tests/acceptance/test_step_loop_gate_keeps_its_evidence.py` (test_the_next_prompt_carries_the_cut_off_gates_failures_and_its_pocket, test_the_next_prompt_names_the_failing_test_of_a_red_gate, test_more_failures_than_the_prompt_holds_are_cut_with_a_pointer_to_the_full_record) | `scripts/_step_loop_files.py`, `scripts/_step_loop_gate.py`, `scripts/_step_loop_render.py`, `scripts/step_loop.py` | met |
| REQ-08 | 5 -- `scripts/test_loop_cli_record_gate.py` (test_each_pocket_that_finished_gets_a_line_with_its_files_tests_and_how_it_was_selected, test_a_widened_pocket_names_no_files_so_they_are_counted_from_its_log, test_a_green_block_summarises_the_scope_and_keeps_only_the_checks_own_command, test_a_scope_that_did_not_resolve_still_says_what_it_was_derived_from); `scripts/test__step_loop_pocket_runs.py` (test_the_test_files_of_a_plain_and_an_xdist_log_are_counted_once_each) | 3 -- `tests/acceptance/test_step_loop_gate_keeps_its_evidence.py` (test_a_green_block_for_a_wide_scope_stays_within_the_section_ceiling, test_a_green_block_names_each_pocket_run_with_its_file_and_test_counts, test_a_green_block_says_when_a_pocket_run_was_widened) | `scripts/_step_loop_pocket_runs.py`, `scripts/_step_loop_record_gate.py` | met |
| REQ-09 | 5 -- `scripts/test_loop_marked_return.py` (test_only_a_verified_attempt_that_did_not_call_its_scope_incomplete_commits, test_a_marked_return_whose_check_passes_commits_nothing_and_ticks_nothing, test_a_marked_return_is_one_ledger_record_with_no_commit); `scripts/test_loop_marked_stop_files.py` (test_a_marked_stop_names_the_step_the_marker_and_each_uncommitted_file, test_no_step_that_is_not_marked_has_an_entry) | 5 -- `tests/acceptance/test_step_loop_conflict_keeps_its_edits.py` (test_a_marked_return_whose_check_passes_commits_nothing, test_a_marked_return_leaves_every_edit_byte_for_byte_and_the_step_unticked, test_a_marked_return_is_one_ledger_record_with_no_commit, test_a_marked_return_stops_naming_the_step_the_marker_and_each_uncommitted_file); `tests/acceptance/test_step_loop_stops.py` (test_a_blocked_return_whose_work_verified_commits_nothing_before_the_stop) | `scripts/_step_loop_record.py` | met |
| REQ-10 | 3 -- `scripts/test_loop_one_state.py` (test_a_conflicting_attempt_counts_as_one_attempt_of_a_marked_series, (module)); `scripts/test_loop_state_review.py` ((module)) | 3 -- `tests/acceptance/test_step_loop_conflict_keeps_its_edits.py` (test_a_conflicted_step_stops_with_the_same_cause_until_its_block_is_revised, test_after_the_revision_the_step_restarts_at_attempt_one_naming_the_kept_edits, test_the_conflicting_attempt_counts_as_one_iteration_of_the_loop) | `scripts/_step_loop_action.py`, `scripts/_step_loop_state.py`, `scripts/step_loop.py` | met |
| REQ-11 | 4 -- `scripts/test_loop_one_state.py` (test_a_series_state_reads_as_its_one_word, test_the_reconciler_word_never_reaches_the_series_word, test_a_marked_step_stops_the_loop_with_a_cause_that_names_the_marker_status_shows); `scripts/test_loop_cli_status.py` (test_a_step_done_outside_the_loop_shows_verified_complete) | 1 -- `tests/acceptance/test_step_loop_conflict_keeps_its_edits.py` (test_status_reports_the_state_next_acts_on) | `scripts/_step_loop_cli.py`, `scripts/_step_loop_state.py` | met |
| REQ-12 | 2 -- `scripts/test_loop_outstanding.py` ((module)); `hooks/test_guard_step_loop_stop.py` ((module)) | 2 -- `tests/acceptance/test_stop_guard_work_is_bounded.py` (test_a_stale_request_in_a_busy_session_reads_a_bounded_number_of_transcripts, test_a_stale_request_in_a_busy_session_lets_the_stop_through_well_inside_the_timeout) | `scripts/_step_loop_outstanding.py` | met |
| REQ-13 | 2 -- `scripts/test_loop_outstanding.py` ((module)); `hooks/test_guard_step_loop_stop.py` ((module)) | 3 -- `tests/acceptance/test_stop_guard_work_is_bounded.py` (test_with_no_step_loop_the_guard_imports_nothing_beyond_its_own_file, test_with_every_request_recorded_the_guard_imports_nothing_beyond_its_own_file, test_a_recent_ended_agent_in_a_busy_session_is_still_held_with_its_record_call) | `scripts/_step_loop_outstanding.py` | met |
| REQ-14 | 1 -- `scripts/test_loop_outstanding.py` ((module)) | 2 -- `tests/acceptance/test_stop_guard_work_is_bounded.py` (test_a_task_named_with_exactly_64_characters_has_its_ended_request_held, test_a_directory_named_with_65_characters_is_not_read_as_a_task) | `scripts/_step_loop_outstanding.py` | met |
| REQ-15 | 2 -- `hooks/test_orientation_loop_mode.py` ((module)); `scripts/test_loop_cli_status.py` ((module)) | 3 -- `tests/acceptance/test_orientation_reads_each_steps_cap.py` (test_status_reports_the_drivers_attempt_cap_for_an_ordinary_step, test_status_reports_a_goal_steps_own_iteration_budget_as_its_cap, test_the_orientation_renders_a_goal_steps_attempts_against_its_own_budget) | `hooks/inject_compaction_orientation.py`, `scripts/_step_loop_cli.py` | met |
| REQ-16 | 1 -- `scripts/test_kernel_run_standing.py` ((module)) | -- | `scripts/kernel_run_evidence.py`, `scripts/kernel_run_index.py`, `scripts/kernel_run_standing.py` | met |
| REQ-17 | 4 -- `scripts/test_kernel_run_evidence_unreadable.py` (test_an_unreadable_earlier_part_is_refused_naming_its_file_and_why_and_nothing_else, test_a_cited_run_whose_own_file_is_unreadable_is_refused_naming_that_file, test_a_file_that_is_not_json_text_is_kept_by_name_with_why, test_the_chain_of_a_continuation_reaches_its_unreadable_earlier_part) | 3 -- `tests/acceptance/test_flip_gate_names_an_unreadable_results_file.py` (test_an_unreadable_uncited_earlier_part_is_refused_naming_its_file_not_a_lineage_disagreement, test_a_record_citing_a_continued_run_whose_earlier_part_reads_cleanly_passes, test_a_cited_run_with_an_unreadable_results_file_is_refused_naming_the_file) | `scripts/kernel_ledger_checks.py`, `scripts/kernel_run_evidence.py` | met |
| REQ-18 | 2 -- `scripts/test_kernel_ledger_checks_purity.py` (test_judging_gathered_evidence_gives_the_same_findings_with_every_file_read_denied, test_the_judging_uses_the_files_it_was_handed_not_the_directory) | -- | `scripts/check_kernel_manifest.py`, `scripts/kernel_ledger_checks.py` | met |
| REQ-19 | -- | 1 -- `tests/acceptance/test_compaction_orientation_follows_the_driver.py` ((module)) | `tests/acceptance/test_compaction_orientation_follows_the_driver.py` | met |
| REQ-20 | 2 -- `tests/acceptance/test_kernels_are_generated.py` ((module)); `scripts/test_check_agent_shared_blocks.py` ((module)) | 3 -- `tests/acceptance/test_agents_reap_their_background_work.py` (test_each_agent_definition_requires_reaping_background_work_and_bounding_watchers, test_the_reaping_duty_reads_the_same_in_every_agent_definition, test_the_shared_text_gates_pass) | `claude/kernels/core-blocks.md`, `claude/kernels/core.md`, `claude/kernels/index.json`, `claude/kernels/src/return-contract.md`, `skills/software-planning/references/agent-pipeline-details.md` | met |
| REQ-21 | 1 -- `scripts/test_check_agent_shared_blocks.py` ((module)) | 3 -- `tests/acceptance/test_agents_reap_their_background_work.py` (test_the_path_classes_place_an_outer_loop_scanner_allowlist_entry_in_the_outer_loop, test_the_verifiers_commit_order_audit_cites_the_allowlist_class_with_its_cases, test_the_acceptance_designer_may_write_the_allowlist_entry_and_name_it_in_its_return) | `agents/test-engineer.md`, `agents/verifier.md`, `skills/software-planning/references/coordination-details.md` | met |

## Key Decisions

- `dec-467`: the gate runs each resolver invocation detached under the pocket's own declared bound (environment override, the pocket's `pyproject.toml`, else 540 s), re-attaches across `record` calls with a `gate-running` refusal, kills only a group its launcher owns, and keeps every failure seen, pocket-named, for the next prompt; a hung run is killed only when a later `record` attaches (td-492).
- `dec-468`: a [CONFLICT] or [BLOCKED] return commits and ticks nothing and keeps its edits, for ordinary and goal steps; a marked series is never done; `status` and `next` read one state; only revising the step's block clears it.
- `dec-471`: bare names, layout pairings and single-segment stems connect only within one pocket, a stem exactly one file bears still crossing; slash literals, globs, dotted imports and declared dependencies cross as before.
- `dec-466`: one stdlib standing leaf for both flip-gate readers; gather reads the results files once and judging opens none; an unreadable earlier part of a continued run is refused by name.
- `dec-469`, `dec-470`, `dec-472`, `dec-473`: the allowlist path class (the whole `.gitleaks.toml` change, `^`-anchored entries), the reaping return contract, the per-step attempt cap, the Stop guard's bounds (64 transcripts, 16 MiB, 5 s).

## Footprints

- FC-01 always-loaded tokens: 24800 at baseline and final.
- FC-02 listing tokens: 14268 at baseline and final.
- FC-03 agent prompt size: 2 warn, 0 fail at both; edited definitions unchanged in lines (implementer 226, test-engineer 356, verifier 490).
- FC-04 test-selection size (root pocket, 50 change sets): widened 3 against 3; narrow p90 241.2 against 260.2 test files.
- FC-05 eval-pocket time: 242 s against the declared 1,200 s bound.

## Deferred

td-488 (the selection audit's 540 s suite bound; no verdict since 2026-10-05, pre-existing), td-490 (the driver's commit subject drops bracketed words), td-491 (the implementer's id-citation pre-check), td-492 (a hung gate run is killed only on attach), td-494 (a cut-off run in a `-q` pocket shows no failures), td-495 (the marked stop's preview crowded by state files), td-496 (the gate-probe test that fails when another session writes the real observation log).
