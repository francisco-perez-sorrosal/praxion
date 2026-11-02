# Spec: eval-kit-repairs (the adherence eval's implementer and verifier kits run their prescribed shell work inside the harness's OS sandbox, and the partial-title checks tell a finished capped report from an unfinished one stripped of its marker)

**Task slug**: `eval-kit-repairs`
**Feature**: Repairs the two defects the adherence eval's recorded runs exposed (ledger rows `td-544` and `td-545`), at $0. First, the implementer and verifier kits ran under a read-only shell grant, so every prescribed test run, formatter run and Praxion script was refused: all 48 sessions of implementer run `20261031T194025Z-257479` lost their test run, and 30 of 48 verifier returns of run `20261031T203813Z-47ce6d` report a denied Bash. The checks that read those results then bound on a refusal both arms shared. Those two kits ("confined kits") now run their shell work inside Claude Code's own OS sandbox, built by one new pure module, `eval/src/praxion_evals/adherence/confinement.py`, and delivered as a `--settings` JSON string in the session's argv. The copy's `scripts/` leads the session's program order, both fixtures declare `pythonpath`, each session record names the commands the harness refused, and the first session that shows a broken confinement stops the run. Second, the write-early check and C5 contradicted each other on a capped session (14 of 15 stopped verifier sessions passed exactly one). The write-early check now judges the closing title only on a session that ended on its own, C5 credits an unmarked capped title only for a finished verifier report, and a run's measured identity gains a digest of the runner's grading sources so no run can be continued under changed checks. Modifies the prior archived spec `SPEC_adherence-eval_2026-10-12.md` (its REQ-05 and REQ-15; see Delta Against the Prior Spec).
**Tier**: Standard (planned 22 steps in `WIP.md`; the spawn tally reads `spawns=34, charged=8, budget 16`; the verifier's calibration verdict reads under-calibrated: 56 files over 21 requirements and 16 production source files under `eval/src` are Full-sized signals, though the Standard envelope held operationally)
**Pipeline branch**: `worktree-eval-kit-repairs` (from `main` at `1dd63cf5`)
**Start date**: 2026-10-31
**End date**: 2026-11-01
**Archived**: 2026-11-01 (pre-merge, on branch worktree-eval-kit-repairs; to be merged to main with --no-ff)
**Status**: completed -- delta verdict PASS WITH FINDINGS at `e02d302d` (the final head `6e45c72a` adds only the ledger rows td-554 and td-555 and the sandbox ADR draft's exception paragraph), after a first pass at `99f5f122` that read PASS WITH FINDINGS with twelve WARN and no FAIL; two in-place rework rows (rw-82e3833d, rw-61ff60fe) closed #warn-1, #warn-2, #warn-4, #warn-5 and #warn-6, and #warn-3 was accepted with a recorded exception; no model session ran, spend was $0, and the sandbox's enforcement is unproven until the first paid run
**ADRs**: `dec-487` (category: architectural -- confine the implementer and verifier kits' shell with the harness's OS sandbox, delivered as `--settings` JSON, with a first-breach run stop that is its own rule rather than a `StopRule`) and `dec-486` (category: behavioral -- read a capped report by how the session ended, and set grader changes apart in a run's identity with a digest of the runner's grading sources). Finalize rewrites both ids to `dec-NNN` at merge to main.
**Open findings**: `td-554` (suggested; a $0 acceptance check that the printed settings are accepted, not dropped) and `td-555` (suggested; three residuals of the breach reading). Both open on this branch; neither blocks the merge.
**Evidence base**: the two ADR drafts above (under `.ai-state/decisions/drafts/`); the spec digest `sha256:183e8c149591` of `SPEC_EXTRACT.md` (the verifier read the extract fresh; the acceptance design recorded the extract file's own sha256 `bff3345eb61d`); the branch's 28 commits from base `1dd63cf5` (acceptance design `949d1ae0`, driver binding `04b03ab0`, first production commit `bdd7c8b9`, first verified head `99f5f122`, rework `ea7d3a98` and `c8b0818a`, delta-verified head `e02d302d`, final head `6e45c72a`), 56 files and +7155/-112 lines; the eight outer-loop files named in the matrix below (designed from the extract alone, with base fixtures frozen at `1dd63cf5`); `TEST_RESULTS.md` (Step 18: eval suite 3923 passed; root derived scope 4264 passed and 8 skipped, then 5242 passed and 32 skipped, 0 failed; `Audit: missed=0 flaky=0`); `ACCEPTANCE_TESTS.md`, `LIGHT_REVIEW_step-10.md`, `LIGHT_REVIEW_step-11.md`, `LIGHT_REVIEW_step-14.md`, `LIGHT_REVIEW_step-15.md`, `PRE_VERIFICATION_DIGEST.md`, `TASK_BRIEF.md`, `REWORK_MANIFEST.md`, `SPEC_DELTA.md` and `VERIFICATION_REPORT.md` (first pass and delta), all under `.ai-work/eval-kit-repairs/` and deleted at cleanup, their substance carried below; ledger rows `td-544` and `td-545` (resolved on this branch), `td-554` and `td-555` (open), and `td-535` (the pre-existing flaky interrupt test).

## Feature Summary

The next paired runs of the implementer and the verifier measure the protocol their kernel trials need: the shell work each definition prescribes runs in the task's sandbox, and the partial-title checks tell a finished report cut off before its return from an unfinished one stripped of its marker.

The shell grant (`td-544`). A narrow allow pattern is unrestricted execution under another name: pytest runs code the implementer just wrote, so narrowing the pattern narrows nothing that runs, and the forms the definitions prescribe (absolute paths into a per-run copy, `python3 -c` for `compute_row_id`, `git -C`, env-prefixed runs) defeat any pattern. Scoring the vacuous checks not applicable on a denied run would have left the kernel trials measuring none of the shell protocol. The decision is the harness's own OS-level sandbox (Seatbelt on macOS, bubblewrap on Linux) with commands auto-approved inside it, so writes are bounded by the OS and not by the command text. The sandbox is required, with no unconfined fallback and no unsandboxed retry. The plugin copy is write-denied. The real home is read-denied except the runner's venv, its uv interpreter, the copy and the run root. The session token file and 14 real-home credential locations are read-denied. The three session credential variables are unset before each sandboxed command, and the hooks keep their environment. Every other kit keeps today's read-only grant byte for byte.

Three enabling repairs ship with it. The copy's `scripts/` leads the program order, so a bare script name runs the checkout under test and never the operator's own install; `check_test_results_shape.py` and `rework_manifest.py`, which did not resolve at all, are now executable. Both fixtures declare `[tool.pytest.ini_options] pythonpath = ["src"]`, because a bare `python -m pytest` exited 2 at collection. And each session record names the shell commands the harness refused, redacted and clipped to 300 characters, so the first paid run proves or disproves the grant from its own record.

The self-verifying first run. There is no separate smoke session: the first session of a confined kit that shows its confinement inactive (a startup exit naming the sandbox, the `Sandbox is required but failed to initialize` refusal, or an `Operation not permitted` result on a prescribed command) or a prescribed command refused stops the run on infrastructure, with no retry and no further session, and the finished pairs stay on the record. That is a separate stop rule, not an `infra_stop.StopRule`: the guard refuses counts below 3 because it exists for transient channel failures, and a refused grant is deterministic. One exception: a refused prescribed command that carries a leading `VAR=value` assignment is recorded but does not stop the run (see the note under REQ-16 and `dec-487`).

The capped-report reading (`td-545`). `title_marker_first_unmarked_last` judges the opening half on every session, skips the closing half on a session stopped at its cap, withholds on an unknown ending when the opening passes, and applies the closing half only when the session ended on its own. C5 gains a finished-form table with the verifier alone in it: an unmarked capped title passes only when no section is still `[pending]` (a section reading `[not reached]` counts as closed) and the `## Verdict` names `PASS`, `PASS WITH FINDINGS` or `FAIL`. Any other role keeps today's reading. The write-early check carries two further canaries, and C5 two. `MeasuredIdentity.checks` digests the runner's grading modules, because `tree` digests the checkout under test and the checkout and the runner can differ; older results files decode with `checks` absent, so a pre-change run is set apart and its continuation refused. Nothing under `.ai-state/eval_ledger/` changed.

The measured result. Every acceptance criterion and every health guard is met on the evidence: the eval suite passed 3923, the root derived scope passed with 0 failed, all eight outer-loop files are green with 61 nodes each listed under some requirement, `sync_canonical_blocks.py --check` is clean, no file under `codex/` or `cursor/` changed, `.ai-state/kernel_adoption.yaml` is unchanged, and no model session started. The dry run, driven through the acceptance driver's path at $0, prints `--settings`, `places` and `program_order` for every confined session and starts none. What $0 cannot show is whether Seatbelt or bubblewrap enforces the printed settings (see Assumptions Only the First Paid Run Can Settle).

Shape of the delivery: 22 plan steps. Steps 1 to 4 bound the outer loop's drivers (driver files only, done by the orchestrator outside the step loop in `04b03ab0`); Steps 5 to 18 are implementer steps, the last the integration checkpoint; Step 19 reconciled the traceability fragments and Step 20 closed the ledger rows (orchestrator, outside the loop for 19); Steps 21 and 22 are the in-place rework after the first verification. Steps 10, 11, 14 and 15 carried a forced light review, and Steps 8, 10, 11 and 14 carried `mutation: on` (each sensor read `not-flat-layout`, the declared refusal for the src layout, so the sensor never mutated the confinement module).

The verifier's most consequential findings. The run-stop classified the redacted, 300-character-clipped command, so a clip that split a quote made `shlex` raise, the parse yield nothing, and the prescribed refusal go unseen (a 527-character `cd <abs> && python -m pytest -k "..."` classified `True` raw and `False` clipped); wrappers and `python <opt> <arg> -m` were also missed. The risk table claimed an `Operation not permitted` result would be read as evidence while no code read it, so an over-tight read allow-list would have failed every test run in both arms as role behaviour. And a finished report whose prose quotes `[pending]` failed C5 as unfinished. The rework closed these; the residuals are `td-555`.

## What Was Built

| Part | Files | Notes |
|---|---|---|
| Confinement module | `eval/src/praxion_evals/adherence/confinement.py` | new, 455 lines at the final head; frozen `Confinement` whose invariants (every path absolute, no `allowRead` entry covering a credential) are enforced in `__post_init__`; `confinement_for`, `settings_of`, `CREDENTIAL_LOCATIONS` (14 real-home names), `SESSION_CREDENTIAL_VARIABLES`, `PRESCRIBED_COMMANDS`, `refused_prescribed`, `confinement_breach`, `BLOCKED_BY_SANDBOX = "Operation not permitted"`. The fixed flags are constants, so a "confined but optional" state is unrepresentable. After the rework `settings_of` also emits `sandbox.network.strictAllowlist: true` and the top-level `permissions.blockReadsOutsideWorkingDirectories: true` |
| Live session | `eval/src/praxion_evals/live/session.py` | `SessionSpec.settings`; `build_argv` appends `--settings <compact sorted JSON>` when set; `build_env(..., path_first=)` prepends directories; both additive, so every live scenario's argv and environment stay byte-identical |
| Launch and dry run | `eval/src/praxion_evals/adherence/tasks.py`, `cli.py`, `session_launch.py` | `session_spec` sets the settings for confined roles only (`allowed_tools` and `READ_ONLY_BASH` unchanged); `session_launch.session_confinement` reads the operator inputs in one place; the dry run prints `--settings`, `places` and `program_order` per confined session; `--session-oauth-token-file` is made absolute at the argparse boundary; `_planned_copy` spells the copy as `session_loop._build_copy` does, a parity test pins the two |
| Record | `adherence/model.py`, `model_codecs.py`, `results.py`, `transcript.py`, `session_launch.py` | `SessionRecord.refused_commands` (from the result event's `permission_denials` unioned with the role transcript's refusal wording); `ErrorKind` value `confinement_broken`, not counting and never retried; older files decode with the fields absent |
| Breach stop | `adherence/infra_stop.py`, `session_launch.py`, `confinement.py` | `session_launch._assessed` replaces a confined session's assessment with `Errored("confinement_broken", evidence)` before any retry decision, classifying the raw command (the clip is record-only); `infra_stop.step` ends the run on the first such record with `scope="both-arms"` so `lineage` reads it as continuable subject to the identity diff; evidence is redacted through the public `infra_stop.redacted` (the former private `_redact`, folded in) |
| Write-early check | `adherence/checks_roles.py`, `model.py` | `title_marker_first_unmarked_last` reads `evidence.role_ending`; a check may carry several `violations`, with `violation` kept as the first, and the catalog canary runner proves each |
| C5 | `adherence/checks_common.py`, `output_forms.py` | `FINISHED_FORMS = {"verifier": FinishedForm(...)}`; `_unfinished` treats a section as open when its body is the `[pending]` marker (a prose mention does not open it, a half-filled section keeping a bare `[pending]` line does); the verdict is read from the first non-blank line of `## Verdict`, emphasis stripped and word-bounded (`PASSED` fails) |
| Run identity | `adherence/run_identity.py` | `MeasuredIdentity.checks`, a sha256 over the runner's installed grading sources (`checks_*.py`, `catalog*.py`, `grade.py`, `output_forms.py`, `transcript.py`); the confinement settings are deliberately outside it |
| Fixtures | `eval/src/praxion_evals/adherence/fixtures/repos/ledger-cli/pyproject.toml.tmpl`, `.../notes-service/pyproject.toml.tmpl` | `[tool.pytest.ini_options] pythonpath = ["src"]`; no dependency added |
| Praxion scripts | `scripts/check_test_results_shape.py`, `scripts/rework_manifest.py` | mode bit only for the first; the second also gained a shebang and still has no `__main__`, so running it by name proves only that it resolves |
| Design and ledger | `.ai-state/DESIGN.md`, `docs/architecture.md`, `.ai-state/TECH_DEBT_LEDGER.md`, two ADR drafts under `.ai-state/decisions/drafts/` | an "Adherence confinement" component row, `Built (td-544; eval-kit-repairs)`, and an updated stop-machinery row; `docs/architecture.md` last verified against code 2026-11-01; `td-544` and `td-545` flipped to `resolved` (Step 20) with a placeholder `resolved-by`; `td-554` and `td-555` opened |
| Outer loop | `tests/acceptance/test_a_run_stops_on_its_first_broken_confinement.py`, `test_capped_reports_are_judged_on_their_opening.py`, `test_confined_kits_run_their_shell_work.py`, `test_confined_kits_stay_inside_their_sandbox.py`, `test_finished_verifier_report_passes_c5.py`, `test_other_kits_keep_their_grant.py`, `test_recorded_runs_keep_their_outcomes.py`, `test_relaxed_checks_keep_their_canaries.py`; drivers `tests/acceptance/drivers/confined_kits.py`, `confinement_runs.py`, `capped_reports.py`, `adherence_runs.py`, `adherence_eval.py`, `implementer_kit.py`, `stand_in_claude.py`; frozen `tests/acceptance/fixtures/eval_kit_grants_before.json`, `eval_ledger_before.json`, `kernel_trial_verdicts_before.json` | designed from the extract alone; the five unbound Boundary Assumptions were bound by the driver-binding steps (`04b03ab0`) before any production commit |

Shipped versus measured. The sandbox's enforcement was not exercised: the acceptance driver runs the prescribed forms in a materialized sandbox under plain `/bin/sh`, not Seatbelt or bubblewrap, and `ACCEPTANCE_TESTS.md` declares REQ-02, REQ-14 and REQ-21 partly not black-box testable. What the dry run proves is the exact settings JSON and argv each confined session would receive; it cannot prove that Claude Code accepts or enforces them, because print mode silently drops settings that fail validation. That is why `td-554` exists and why the stop watches the first paid session.

## Assumptions Only the First Paid Run Can Settle

None of these can be proven at $0, and no smoke session was run. The first paired run of a confined kit settles them, or the stop ends it after one session. Each is recorded in the pre-verification digest as load-bearing.

| # | Assumption | What shows it false | What the run does about it |
|---|---|---|---|
| 1 | A subagent's Bash runs inside the sandbox | The sandboxing page's Scope section says subagents share the parent's sandbox configuration, so the docs settle it; no per-command flag in the stream shows a command ran unsandboxed, and the observable proxies are the startup exit, the refusal text and the refusal record | A prescribed command refused, or the `Sandbox is required but failed to initialize` text, stops the run |
| 2 | Auto-approval works in print mode (`autoAllowBashIfSandboxed` under `acceptEdits` and `--permission-prompts none`) | Any prescribed command refused by the harness while the sandbox was active. A silently dropped `--settings` shows up the same way, since without it only the read-only grant applies | Stops the run on the first such session. The ADR names the reversal: auto-allow off with explicit patterns inside the sandbox |
| 3 | `denyWrite` over the copy beats the copy's `--add-dir` write grant | Only exercised if a role writes the copy. The post-session copy digest (`verify_copy_diff`) shows the copy intact either way, and the on-disk read-only mode is a second layer | A write into the copy draws `Operation not permitted`, which since the rework counts as a breach on a prescribed command and stops the run (residual 2 of `td-555`). If a sandboxed command ever writes outside the sandbox, the ADR says to withdraw the grant |
| 4 | The startup refusal wording | The docs say Claude Code "exits with an error at startup" under `failIfUnavailable` but do not quote the text. `confinement_breach` matches `sandbox` case-insensitively in the stderr of a session that produced no `init` event under a confined launch | The first real occurrence is recorded verbatim in the evidence, for re-binding the startup-exit driver |

Also riding on the first run, from Step 21: the Read tool's working directories are the session's cwd plus the plugin copy's `--add-dir`, and the run root is reached through the cwd, so only the run proves that the copy stays readable by the file tools under `blockReadsOutsideWorkingDirectories`. The interpreter's read allow-list (the venv, the uv base prefix) looks sufficient on this machine; an `Operation not permitted` on a prescribed `python`, `pytest` or `ruff` now stops the run instead of failing both arms silently. Credential and real-home denials (REQ-18 to REQ-21) are declared at $0 and accepted on the documented `credentials` and `denyRead` semantics; nothing in a run proves them unless a role tries one.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (digest `sha256:183e8c149591`), with one archival note under REQ-16. REQ ids are pipeline-local and appear nowhere in code, tests or docstrings. Complexity: Standard (see the calibration note in the header). Brownfield: the prior archived spec `SPEC_adherence-eval_2026-10-12.md` covers the eval these requirements modify.

### Observable Surface

- `praxion-evals-adherence` -- the adherence eval's command line; its dry run and its results files are observable without a model session
- the launch specification of a task's session -- the tool grant, permission settings, working directory, environment and plugin copy a session for a given task and arm is started with
- a materialized task sandbox -- a scratch fixture repository, a sandbox home and temp directory, and the read-only plugin copy, built for a task without starting a session
- the grade of a session -- one outcome per catalog check (passed, failed, not applicable, withheld, errored) for a session's evidence, including synthetic evidence
- a check's canary -- the violation evidence the catalog pairs with a check, which the check must fail
- a results file -- one run's committed JSON record under the eval ledger, with schema `adherence/1`, and the report rendered from it
- `python -m pytest` -- the fixture's test runner, also invoked as `pytest` or `python3 -m pytest`
- `ruff check` -- the linter; `ruff format` -- the formatter
- `git diff` -- with `git log`, `git status` and `git show`, the git reads
- `extract_spec.py` -- a Praxion script the verifier definition names
- `check_test_results_shape.py` -- a Praxion script the verifier definition names
- `check_state_ledgers.py` -- a Praxion script the verifier definition names
- `rework_manifest.py` -- the Praxion module whose row-id function the verifier definition names; it has no command line
- `check_id_citation_discipline.py` -- a Praxion script the implementer definition names
- `resolve_test_scope.py` -- a Praxion script the implementer definition names
- `VERIFICATION_REPORT.md` -- the verifier's durable report
- `TEST_RESULTS.md` -- the implementer's test-run handoff
- `[PARTIAL]` -- the title marker of an unfinished document
- `[pending]` -- a report section not yet filled
- `[not reached]` -- a report section the verifier closed without reaching it
- `## Verdict` -- the verifier report's verdict section, naming one of `PASS`, `PASS WITH FINDINGS`, `FAIL`
- `Sandbox is required but failed to initialize` -- the refusal the harness gives a shell command when required confinement failed after startup
- `--session-oauth-token-file` -- the eval's option naming the operator's session token file, which lives under the real home
- `CLAUDE_CODE_OAUTH_TOKEN` -- with `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`, the session credentials a session's environment may carry
- a confined kit -- the implementer's and the verifier's kits, whose shell commands run inside the harness's confinement
- the real home -- the operator's own home directory, as distinct from the sandbox home a session is given

### REQ-01: A covered role's prescribed shell work runs in its sandbox

**When** a session is launched for an implementer or a verifier task
**and** the role issues a shell command its definition prescribes for that task: the fixture's test runner, the formatter or the linter over the fixture, a git read, or a Praxion script its definition names, written as a bare name, with an absolute path into the plugin copy, as an inline interpreter call into that module, chained with other commands, or with its output redirected into the task's directory
**the system** runs the command in the task's sandbox with no permission denial
**so that** the checks that read the role's test results, return and handoff bind on what the role did, not on a refusal both arms share.

### REQ-02: The shell grant cannot reach past the sandbox

**When** a shell command of an implementer or verifier session tries to write a path outside the task's sandbox, to modify any file of the plugin copy under test, or to open a network connection
**the system** refuses that write or connection while the rest of the command's work inside the sandbox proceeds
**so that** a grant wide enough for test runs never becomes unrestricted execution on the operator's machine, and both arms run the copy they were built from.

### REQ-03: No unconfined fallback

**When** the confinement that bounds a covered role's shell commands cannot be established for a session
**the system** starts no shell command of that session unconfined: the session ends before the role works and is recorded as an infrastructure error naming the cause
**so that** no measured session ever ran with a broad grant and nothing bounding it.

### REQ-04: Scripts resolve to the copy under test

**When** a covered role runs a Praxion script its definition names by its bare name, or runs the test runner, formatter or linter
**the system** resolves the Praxion script from the plugin copy under test before any copy installed on the operator's machine, resolves every script either definition names (none is missing), and resolves the test runner, formatter and linter from the runner's own environment
**so that** a session measures the checkout under test, never the operator's own installed version of it.

### REQ-05: The fixtures' own tests run

**When** the test runner runs with no arguments at the root of either fixture repository as committed in a task's sandbox
**the system** collects every test in the fixture and they pass
**so that** a red test run in a session reflects the role's change, never the fixture's layout.

### REQ-06: Other kits keep their grant

**When** a session is launched for a role other than the implementer and the verifier
**the system** grants it the same read-only shell commands as before this change, with no added confinement setting
**so that** the kits outside the kernel trials keep the conditions their recorded runs were measured under.

### REQ-07: A refused command is on the record

**When** the harness refuses a shell command the role issued in a session
**the system** names that command in the session's record in the results file
**so that** a reader can tell a role that skipped its shell work from one the harness stopped, without the session's transcript.

### REQ-08: The write-early opening binds on every session

**When** a verifier or sentinel session is graded
**and** the first recorded write of its report came after the window its definition sets (the verifier's first three tool calls), was an edit rather than a write, or opened without [PARTIAL] in the title
**the system** fails the write-early check, however the session ended
**so that** the opening half still measures "write early" on every task, a capped one included.

### REQ-09: A capped session is not judged on its closing title

**When** a forced-stop verifier or sentinel session stopped at its turn cap
**and** its report's opening satisfies the write-early check
**the system** passes the write-early check whether or not the report's title still carries [PARTIAL] at the end; and when the forced-stop session's ending is unknown, it withholds the check instead, with the reason, unless the opening already fails
**so that** no capped session is failed for the very title C5 requires of it.

### REQ-10: A session that ended on its own must close its title

**When** a verifier or sentinel session ended on its own, or ran a task with no lowered turn cap
**and** its report's title still carries [PARTIAL] at the end, or the report is missing or empty at the end
**the system** fails the write-early check, as before this change
**so that** "finish last" is still measured wherever the role had the turns to finish.

### REQ-11: A finished verifier report cut off before its return passes C5

**When** a verifier session stopped at its turn cap
**and** the title of `VERIFICATION_REPORT.md` does not carry [PARTIAL]
**the system** passes C5 only when no section of the report still reads [pending] (a section reading [not reached] counts as closed) and the `## Verdict` section names one of `PASS`, `PASS WITH FINDINGS` or `FAIL`; otherwise it fails C5, naming the sections still [pending] or the missing verdict
**so that** C5 tells a report the verifier finished on its last allowed turn from an unfinished one stripped of its marker.

### REQ-12: The marked partial form still passes

**When** a session of any role stopped at its turn cap
**and** its durable output's title carries [PARTIAL] together with the progress lines its definition states
**the system** passes C5, as before this change
**so that** the partial form the completion handshake reads keeps its meaning for every role.

### REQ-13: Roles with no finished form keep today's reading

**When** a session of a role other than the verifier stopped at its turn cap
**and** its durable output's title does not carry [PARTIAL]
**the system** fails C5, as before this change
**so that** a role whose definition states no finished form is never credited for removing its marker.

### REQ-14: Every new case has a canary that bites

**When** the eval suite proves its checks against their canaries
**the system** finds the write-early check failing a session that ended on its own with [PARTIAL] still in the title, failing a capped session whose report opened late or unmarked, and C5 failing a capped verifier report with an unmarked title and a section still [pending], and one with an unmarked title and no verdict
**so that** each relaxed reading is shown still to bite on the violation it must catch.

### REQ-15: Recorded runs keep their outcomes

**When** a results file recorded before this change is read, rendered into a report, compared with a later run, or offered for continuation
**the system** shows the outcomes it recorded, rewrites nothing in the eval ledger, and sets it apart from runs recorded after the change by its measured identity, refusing to continue it under the changed checks
**so that** no verdict already on the record changes, and no run mixes the old and new readings of a check.

### REQ-16: The first paired run verifies its own confinement

**When** a session of a confined kit ends
**and** its record shows the confinement inactive (the session exited at startup because confinement was unavailable, or a shell command drew the `Sandbox is required but failed to initialize` refusal), or shows a shell command its definition prescribes refused by the harness (the refusal record that REQ-07 keeps)
**the system** records that session as an infrastructure error naming the evidence, takes no retry of it, launches no further session of the run, keeps every pair already finished on the record for reuse, and reports the run stopped on infrastructure
**so that** the first paired run proves the grant without a separate smoke session, and one broken setting never costs more than one session.

> **Archival note (2026-11-01).** The first-breach stop has one exception, added at rework (verifier #warn-3). A refused prescribed command that carries a leading `VAR=value` assignment stays on the session record (REQ-07) but does not stop the run. The sandboxing docs send such commands through the regular permission flow even inside the sandbox, which under `--permission-prompts none` is a refusal by design, not a broken confinement, and the fixtures now declare `pythonpath`, so no prescribed form needs the prefix. The exception is stated in `dec-487` (`confined-kits-os-sandbox-grant`), section "Exception to the first-breach stop", and `td-555` tracks its cost: a role that prefixes every test run yields a run that continues but measures nothing of its shell work. `env X=1 pytest` is the `env` wrapper, not a prefix, and still stops the run.

### REQ-17: The dry run shows the confinement each session would get

**When** the dry run plans a run that includes a confined kit
**the system** shows, for each planned session of that kit, the confinement settings the session would be started with: confinement required with no unconfined fallback and no unconfined retry, commands inside it approved without a prompt, writes to the plugin copy refused, the read and environment protections of REQ-18 to REQ-21, and the order the session resolves programs in; it starts no model session
**so that** the operator can inspect, at no cost, exactly what the first paid session will receive.

### REQ-18: The session token file is unreadable

**When** a shell command of a confined kit reads the file the eval was given through `--session-oauth-token-file`, by any path that reaches it
**the system** refuses the read
**so that** no role can recover the operator's session token from disk.

### REQ-19: The operator's credential locations are unreadable

**When** a shell command of a confined kit reads one of the operator's credential locations in the real home (the SSH directory, cloud and package-manager credential files, the code-hosting command line's stored login, the network login file, and the operator's own Claude Code configuration and its credentials store), named by their real-home paths and not by the sandbox home
**the system** refuses the read
**so that** an injected instruction cannot have a confined command read a credential and hand it to a tool that reaches the network.

### REQ-20: The real home is unreadable beyond what a session needs

**When** a shell command of a confined kit reads a path under the real home
**the system** allows the read only inside the runner's own environment, the interpreter that environment runs on, the plugin copy and the run root, and refuses every other path under the real home
**so that** the shell reaches no more of the operator's files than running the session requires.

### REQ-21: Session credentials never reach a confined command's environment

**When** a shell command of a confined kit runs
**the system** starts it with none of the session credentials in its environment (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`), while the session itself and its hooks keep the environment they have today
**so that** printing the environment or an inline interpreter call cannot reveal the session's token, and the hooks under test run as before.

## Delta Against the Prior Spec

`SPEC_DELTA.md` (ephemeral, deleted with `.ai-work/`) shows the before and after text. This feature's ids are fresh; the cross-feature mapping to `SPEC_adherence-eval_2026-10-12.md` is kept here. Baseline confidence was formally Low (the prior spec's SH03 check was not reached by the 2026-10-31 sentinel pass); no drift is known. No prior requirement is removed.

| This feature | Prior spec counterpart | Relation |
|---|---|---|
| REQ-04 | REQ-05 (sessions see only the checkout under test) | Modified |
| REQ-11, REQ-12, REQ-13 | REQ-15 (C5, a forced early stop leaves the role's own partial form) | Modified (REQ-12 and REQ-13 restate what stays) |
| REQ-08, REQ-09, REQ-10 | REQ-17 Role Check Table, verifier and sentinel rows (write early, end unmarked) | Modified |
| REQ-17 | REQ-03 (a dry run spends nothing) | Extended |
| REQ-03, REQ-16 | REQ-19 (one outcome per check; errors never count against a role) and the one-retry policy it cites | Extended |
| REQ-14 | REQ-24 (every check is proven to bite) | Extended |
| REQ-07, REQ-15 | REQ-25 (every session carries its setup) and REQ-06 (one results file per run) | Extended |
| REQ-01, 02, 03, 05, 06, 07, 16, 18 to 21 | none (REQ-03, 07 and 16 also extend the prior requirements named above) | Added (see below) |

The two modifications of substance. Prior REQ-05 isolated the session's configuration, plugin and environment but said nothing of how a bare script name resolves, and the session `PATH` appended the ambient `PATH`, so four named scripts ran the operator's own install and two did not resolve at all; REQ-04 here makes the copy's `scripts/` lead. Prior REQ-15 passed C5 only on `[PARTIAL]` plus the role's progress lines, so a verifier that finished its report on its last allowed turn and removed the marker failed; REQ-11 here credits that for the verifier alone, while REQ-12 and REQ-13 restate what stays. Also changed, recorded as verifier #warn-11: the dry run's printed plugin-copy path went from `{arm}-copy{cap}` to `{arm}-cap{cap}` or `{arm}` for every kit, to match what `session_loop._build_copy` builds, so the 15 unconfined roles' dry-run lines differ from before. A test pins the two together.

## Acceptance Criteria at Close

Status is the verifier's: the first pass at `99f5f122` and the delta at `e02d302d`. "Green" rests on `TEST_RESULTS.md` Step 18; the verifier ran no suite.

| Criterion | Requirement | Status | Evidence at close |
|---|---|---|---|
| AC-01 | REQ-01 | PASS | The dry run prints `--settings` for every implementer and verifier session; five acceptance nodes run the prescribed forms in a materialized sandbox (plain `/bin/sh`). Residual: env-prefixed forms are refused by design (`td-555`) |
| AC-02 | REQ-02 | PASS | `denyWrite` covers the copy in both spellings, no `allowedDomains`, and since the rework `strictAllowlist: true` makes the network refusal independent of prompt denial. Enforcement is the harness's and is not drivable at $0 |
| AC-03 | REQ-03 | PASS | `failIfUnavailable: true`, `allowUnsandboxedCommands: false`; a startup exit with `sandbox` in stderr becomes `Errored("confinement_broken")` |
| AC-04 | REQ-04 | PASS | Program order `<copy>/scripts`, the runner bin, the ambient PATH; both verifier scripts made executable (`25b01367`) |
| AC-05 | REQ-05 | PASS | Both `pyproject.toml.tmpl` declare `pythonpath = ["src"]`; Spec Question SQ-01 resolved at `2930fce1` |
| AC-06 | REQ-06 | PASS | The researcher's dry-run line has no `--settings`; green against the frozen `eval_kit_grants_before.json` |
| AC-07 | REQ-07 | PASS | `ResultInfo.denied_commands`, `transcript.refused_commands` and the redacted, clipped `SessionRecord.refused_commands` |
| AC-08 | REQ-08 | PASS | `title_marker_first_unmarked_last` always judges the opening, however the session ended |
| AC-09 | REQ-09 | PASS | Skips the closing half on `StoppedAtCap`; `Withheld(reason)` on `Unknown` when the opening passes |
| AC-10 | REQ-10 | PASS | Applies the closing half on `EndedOnItsOwn` or no ending |
| AC-11 | REQ-11 | PASS | `FINISHED_FORMS["verifier"]` and `_unfinished`; the prose-quote case reads closed since `c8b0818a`, a half-filled section keeping a bare `[pending]` line stays open since `e02d302d`. Info only: a section holding both `[not reached]` and a bare `[pending]` line reads open, a pair the definition's skeleton never produces |
| AC-12 | REQ-12 | PASS | `_partial_problems` keeps the marked path unchanged |
| AC-13 | REQ-13 | PASS | A role absent from `FINISHED_FORMS` keeps the "title lacks [PARTIAL]" failure |
| AC-14 | REQ-14 | PASS | The write-early check carries two further canaries and C5 two; `test_relaxed_checks_keep_their_canaries.py` green; the eval suite's canary run is inside the 3923 |
| AC-15 | REQ-15 | PASS | `git diff --name-only 1dd63cf5..HEAD -- .ai-state/eval_ledger/` is empty; old files decode `checks` to `None` and continuation is refused |
| AC-16 | REQ-16 | PASS | The stop returns before any retry decision with a `both-arms` reason and keeps finished pairs. Since the rework it classifies the raw command, unwraps `timeout`, `bash -c`, `sh -c` and `env -i`, and counts `Operation not permitted` on a prescribed command. Exception: a leading `VAR=value`. Residuals: `td-555` |
| AC-17 | REQ-17 | PASS | `started_sessions 0`; each confined line carries `--settings`, `places` and `program_order` |
| AC-18 | REQ-18 | PASS | `credentials.files` deny on the given path and its realpath; the option is made absolute |
| AC-19 | REQ-19 | PASS | 14 absolute real-home entries, `mode: deny`, with `denyRead` over the whole real home as the first layer |
| AC-20 | REQ-20 | PASS | `denyRead` on the real home; `allowRead` the venv, the uv base prefix, the copy and the run root; `blockReadsOutsideWorkingDirectories: true` closes the Read-tool exposure the plan had assumed closed |
| AC-21 | REQ-21 | PASS | `credentials.envVars` deny for the three names; the hooks' environment is untouched (no `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`) |
| AC-22 | health guards | PASS | Eval and root suites green per Step 18; `sync_canonical_blocks.py --check` exit 0; no `codex/` or `cursor/` file changed; `kernel_adoption.yaml` unchanged; no model session started |

### Outer-loop amendments

One Spec Question was raised, SQ-01: an earlier pipeline's kit pin compared every implementer fixture file, so the new test-collection block made 40 tasks read as changed. The driver `implementer_kit.py::without_instruction_file` now compares `pyproject.toml` with exactly that block removed, only when it is the file's trailing suffix; resolved at `2930fce1`. Boundary Assumption BA-06 (the pre-change results shape lacks `checks`) held as provisionally bound. Three later test edits were made by the orchestrator outside their steps' `Files:`, each load-bearing and disclosed in the pre-verification digest: `eead8e44` (pin the fixtures' collection block), `3a281c37` (the report tests follow the launch seam's shapes) and `4060af25` (the kind pin admits `confinement_broken`). The verifier ruled them not `[NON-SURGICAL]`.

SQ-02 was raised after close, by the orchestrator, for `td-554`. A paid run now asks `claude doctor`, before a confined kit's run writes anything, whether the kit's sandbox settings are taken as written. Both stand-in `claude` executables (`stand_in_claude.py` and the fake in `adherence_eval.py`) answered `doctor` as a session launch, so 14 confined-kit scenarios (4 acceptance, 10 end-to-end) saw a launch that never happened or no results file. Resolution: a stand-in plays the harness's settings check as well as its sessions. Both hand `doctor` to a new driver, `harness_doctor.py`, which answers from the 13 sandbox settings the real doctor recognized on Claude Code 2.1.316: it names a known setting of another type, passes over an unknown key, and is never logged as a launch. No scenario's assertion changed. Resolved in: `f4fd454e`.

### Footprint at Close

The scope touches no path in `.ai-state/FOOTPRINTS.md`. `check_footprint_criteria.py eval-kit-repairs --stage verify --base-ref 1dd63cf5 --json` exits 0 with `active: true`, `moved: []`, `criteria: []` and `findings: []`.

## Traceability

Rendered from `traceability.yml` at archival (the planner's Step 19 reconciled the fragments into one canonical file). `Status` is the verifier's reading across the first pass and the delta. Every listed unit, acceptance and implementation entry resolves to a file and symbol in the tree at the final head, after two maintenance corrections for names the rework changed (annotated in place). Counts: all 21 requirements carry both unit and acceptance evidence, and the 61 outer-loop nodes equal the union of the `acceptance:` entries exactly. The matrix lists the implementation units each requirement names.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 7 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_live_session.py` (test_build_argv_without_settings_has_no_settings_flag, test_build_argv_carries_the_settings_as_one_compact_sorted_json_value); `eval/tests/test_adherence_confinement_wiring.py` (test_a_confined_roles_spec_carries_settings_whose_copy_is_the_arms_copy, test_the_confinement_leaves_the_tool_grant_as_it_was, test_prepare_puts_the_launchs_home_and_token_file_into_the_sessions_settings) | 5 test(s) -- `tests/acceptance/test_confined_kits_run_their_shell_work.py` (test_every_prescribed_shell_command_is_granted_without_a_denial, test_a_prescribed_command_does_its_work_in_the_sandbox, test_the_redirected_test_run_leaves_its_log_in_the_tasks_directory, test_the_row_id_function_answers_an_inline_interpreter_call, test_the_linter_and_the_formatter_run_over_the_fixture) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/live/session.py` (build_argv); `eval/src/praxion_evals/adherence/tasks.py` (session_spec); `eval/src/praxion_evals/adherence/session_launch.py` (_prepare, session_confinement) | PASS (env-prefixed forms are refused by design: `td-555`) |
| REQ-02 | 6 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_write_is_denied_over_the_plugin_copy_in_both_spellings, test_the_fixed_flags_require_the_sandbox_and_allow_no_unconfined_command, test_no_network_domain_is_allowed_and_a_host_outside_the_empty_list_is_denied_not_asked <!-- maintenance correction 2026-11-01: was test_no_network_domain_is_allowed (renamed at rework, ea7d3a98) -->, test_the_rendered_key_set_is_pinned) | 4 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_a_write_inside_the_sandbox_is_let_through, test_a_write_into_the_plugin_copy_is_refused, test_a_write_outside_the_sandbox_is_refused, test_a_network_connection_is_refused) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (confinement_for, settings_of) | PASS (enforcement is the harness's; not drivable at $0) |
| REQ-03 | 9 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_the_fixed_flags_require_the_sandbox_and_allow_no_unconfined_command, test_every_other_role_gets_none, test_a_confined_role_gets_a_confinement); `eval/tests/test_adherence_confinement_breach.py` (test_every_form_of_an_implementers_prescribed_command_is_read_as_prescribed, test_every_form_of_a_verifiers_prescribed_command_is_read_as_prescribed, test_chaining_env_prefixes_redirects_cd_and_git_c_do_not_hide_a_prescribed_command); `eval/tests/test_adherence_confinement_stop.py` (test_the_first_session_with_a_broken_confinement_stops_the_run_in_both_arms) | 2 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_the_confinement_is_required_with_no_unconfined_fallback_or_retry); `tests/acceptance/test_a_run_stops_on_its_first_broken_confinement.py` (test_a_session_that_exits_at_startup_without_its_confinement_stops_the_run) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (settings_of, CONFINED_ROLES, PRESCRIBED_COMMANDS, refused_prescribed); `eval/src/praxion_evals/adherence/session_launch.py` (_assessed); `eval/src/praxion_evals/adherence/infra_stop.py` (_confinement_stop) | PASS |
| REQ-04 | 8 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_programs_resolve_from_the_copys_scripts_then_the_runner_then_the_ambient_path); `eval/tests/test_live_session.py` (test_build_env_puts_path_first_directories_ahead_of_the_interpreter_and_ambient_path, test_build_env_without_path_first_is_the_interpreter_directory_then_the_ambient_path); `eval/tests/test_adherence_confinement_wiring.py` (test_the_copys_scripts_lead_the_program_order_and_only_absolute_path_entries_follow, test_a_launched_sessions_environment_is_built_with_the_confinements_program_order, test_a_session_environment_resolves_the_given_directories_first) | 4 test(s) -- `tests/acceptance/test_confined_kits_run_their_shell_work.py` (test_a_named_script_resolves_to_the_plugin_copy_before_an_operator_install, test_a_named_script_runs_by_its_bare_name, test_the_toolchain_resolves_from_the_runners_own_environment); `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_programs_resolve_from_the_plugin_copy_before_the_operators_path) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (confinement_for); `eval/src/praxion_evals/live/session.py` (build_env); `eval/src/praxion_evals/adherence/session_launch.py` (attempt); `eval/src/praxion_evals/adherence/session_loop.py` (session_env) | PASS |
| REQ-05 | 1 test(s) -- `eval/tests/test_adherence_tasks.py` (test_a_fixture_repository_puts_its_source_on_the_test_path) | 2 test(s) -- `tests/acceptance/test_confined_kits_run_their_shell_work.py` (test_the_fixtures_tests_run_with_no_arguments_at_its_root_and_pass, test_the_fixtures_tests_are_every_one_collected) | `eval/src/praxion_evals/adherence/fixtures/repos/ledger-cli/pyproject.toml.tmpl` ((module)); `eval/src/praxion_evals/adherence/fixtures/repos/notes-service/pyproject.toml.tmpl` ((module)) | PASS |
| REQ-06 | 6 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement_wiring.py` (test_a_spec_built_with_no_confinement_carries_no_settings, test_a_role_that_is_not_confined_gets_no_confinement, test_prepare_gives_a_role_that_is_not_confined_no_confinement, test_a_session_environment_with_no_directories_given_is_as_it_was) | 3 test(s) -- `tests/acceptance/test_other_kits_keep_their_grant.py` (test_another_kits_tool_grant_is_the_one_it_had, test_another_kits_shell_grant_stays_read_only, test_another_kits_session_carries_no_added_option_or_variable) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/tasks.py` (session_spec); `eval/src/praxion_evals/adherence/session_launch.py` (session_confinement) | PASS |
| REQ-07 | 11 test(s) -- `eval/tests/test_adherence_results.py` (test_a_records_refused_commands_round_trip_through_the_results_file, test_an_errored_record_keeps_its_refused_commands_through_the_results_file, test_a_record_without_refused_commands_stores_no_key_and_an_older_file_decodes_with_none, test_the_committed_results_files_still_decode_and_render_with_no_refused_commands); `eval/tests/test_adherence_model.py` (test_a_refused_command_needs_a_command_and_a_known_source); `eval/tests/test_adherence_refused_commands.py` (test_a_denial_in_the_result_event_is_a_refused_command, test_a_non_bash_denial_is_not_a_refused_command, test_a_sandbox_refusal_in_a_tool_result_is_a_refused_command, test_the_same_command_in_both_surfaces_appears_once_with_the_denial_as_its_source, test_a_credential_in_a_command_is_redacted_before_it_is_committed, test_an_overlong_command_is_clipped_to_the_bound) | 1 test(s) -- `tests/acceptance/test_a_run_stops_on_its_first_broken_confinement.py` (test_a_command_the_harness_refused_is_named_in_the_sessions_record) | `eval/src/praxion_evals/adherence/model.py` (RefusedCommand, SessionRecord); `eval/src/praxion_evals/adherence/results.py` (_session_to_json, _session_from_json); `eval/src/praxion_evals/live/session.py` (_denied_commands); `eval/src/praxion_evals/adherence/transcript.py` (refused_commands); `eval/src/praxion_evals/adherence/session_launch.py` (redacted_refusals, clipped <!-- maintenance correction 2026-11-01: was recorded_refusals (split into redacted_refusals and clipped at rework, ea7d3a98) -->, attempt) | PASS |
| REQ-08 | 1 test(s) -- `eval/tests/test_adherence_checks_roles.py` (test_a_bad_opening_fails_however_the_session_ended) | 3 test(s) -- `tests/acceptance/test_capped_reports_are_judged_on_their_opening.py` (test_a_verifier_report_first_written_after_its_third_call_fails_however_the_session_ended, test_a_report_opened_without_the_partial_marker_fails_however_the_session_ended, test_a_report_first_recorded_as_an_edit_fails_however_the_session_ended) | `eval/src/praxion_evals/adherence/checks_roles.py` (title_marker_first_unmarked_last, _opening_problems) | PASS |
| REQ-09 | 2 test(s) -- `eval/tests/test_adherence_checks_roles.py` (test_a_capped_session_is_not_judged_on_its_closing_title, test_a_session_whose_ending_cannot_be_told_is_withheld_with_the_reason) | 3 test(s) -- `tests/acceptance/test_capped_reports_are_judged_on_their_opening.py` (test_a_capped_session_that_opened_in_time_passes_with_partial_still_in_its_title, test_a_capped_session_that_opened_in_time_passes_with_its_title_unmarked, test_a_session_whose_ending_cannot_be_told_is_withheld_with_its_reason) | `eval/src/praxion_evals/adherence/checks_roles.py` (title_marker_first_unmarked_last) | PASS |
| REQ-10 | 2 test(s) -- `eval/tests/test_adherence_checks_roles.py` (test_a_session_with_the_turns_to_finish_is_judged_on_its_closing_title, test_a_session_that_closed_its_title_passes_whatever_it_ended_on) | 3 test(s) -- `tests/acceptance/test_capped_reports_are_judged_on_their_opening.py` (test_a_session_with_the_turns_to_finish_fails_when_its_title_keeps_partial, test_a_session_with_the_turns_to_finish_fails_when_its_report_ends_empty, test_a_session_with_the_turns_to_finish_passes_when_it_opened_in_time_and_closed) | `eval/src/praxion_evals/adherence/checks_roles.py` (title_marker_first_unmarked_last, _closing_problems) | PASS |
| REQ-11 | 2 test(s) -- `eval/tests/test_adherence_checks_common.py` (test_an_unmarked_verifier_report_with_every_section_closed_and_a_verdict_passes, test_a_section_closed_as_not_reached_counts_as_closed) | 6 test(s) -- `tests/acceptance/test_finished_verifier_report_passes_c5.py` (test_a_capped_verifier_report_finished_and_unmarked_passes, test_a_section_closed_as_not_reached_counts_as_finished, test_an_unmarked_report_with_a_section_still_pending_fails_naming_that_section, test_an_unmarked_report_without_a_verdict_section_fails_naming_the_missing_verdict, test_an_unmarked_report_whose_verdict_names_no_outcome_fails, test_an_unmarked_skeleton_stripped_of_its_marker_fails) | `eval/src/praxion_evals/adherence/output_forms.py` (FinishedForm, FINISHED_FORMS); `eval/src/praxion_evals/adherence/checks_common.py` (_unfinished) | PASS (prose-quote case and half-filled section fixed at rework) |
| REQ-12 | 2 test(s) -- `eval/tests/test_adherence_checks_common.py` (test_an_unmarked_report_with_a_pending_section_fails_naming_it, test_an_unmarked_report_whose_verdict_is_missing_or_names_no_outcome_fails) | 1 test(s) -- `tests/acceptance/test_finished_verifier_report_passes_c5.py` (test_a_capped_report_carrying_partial_and_its_progress_line_passes) | `eval/src/praxion_evals/adherence/checks_common.py` (_partial_problems, _names_outcome) | PASS |
| REQ-13 | 2 test(s) -- `eval/tests/test_adherence_checks_common.py` (test_a_marked_verifier_report_passes_with_its_progress_line_whatever_its_sections, test_a_role_with_no_finished_form_keeps_the_reading_that_an_unmarked_title_fails) | 1 test(s) -- `tests/acceptance/test_finished_verifier_report_passes_c5.py` (test_a_capped_report_of_another_role_fails_unmarked_even_when_finished) | `eval/src/praxion_evals/adherence/checks_common.py` (_partial_problems) | PASS |
| REQ-14 | 6 test(s) -- `eval/tests/test_adherence_model.py` (test_a_check_built_without_extras_has_one_violation, test_the_violations_are_the_first_canary_then_the_extras_in_order); `eval/tests/test_adherence_catalog.py` (test_a_mechanical_checks_planted_violation_is_flagged_failed); `eval/tests/test_adherence_checks_roles.py` (test_every_canary_of_the_marker_check_fails_it); `eval/tests/test_adherence_checks_common.py` (test_an_unmarked_report_with_a_pending_section_fails_naming_it, test_an_unmarked_report_whose_verdict_is_missing_or_names_no_outcome_fails) | 4 test(s) -- `tests/acceptance/test_relaxed_checks_keep_their_canaries.py` (test_the_write_early_check_fails_its_canary_of_a_session_that_ended_with_partial_kept, test_the_write_early_check_fails_its_canary_of_a_capped_session_that_opened_badly, test_c5_fails_its_canary_of_an_unmarked_capped_verifier_report_with_a_pending_section, test_c5_fails_its_canary_of_an_unmarked_capped_verifier_report_with_no_verdict) | `eval/src/praxion_evals/adherence/model.py` (MechanicalCheck.violations); `eval/src/praxion_evals/adherence/checks_roles.py` (clause, title_marker_first_unmarked_last); `eval/src/praxion_evals/adherence/checks_common.py` (_unmarked_verifier_report_canary) | PASS |
| REQ-15 | 6 test(s) -- `eval/tests/test_adherence_run_identity.py` (test_editing_a_grading_source_changes_the_checks_digest, test_a_new_grading_source_changes_the_checks_digest, test_editing_an_unrelated_module_leaves_the_checks_digest, test_a_file_without_checks_reads_back_with_none_and_differs_from_a_digested_run, test_diff_names_each_way_two_identities_differ, test_a_new_run_records_what_it_was_measured_on_when_it_begins) | 3 test(s) -- `tests/acceptance/test_recorded_runs_keep_their_outcomes.py` (test_every_file_the_eval_ledger_held_keeps_its_bytes, test_a_kernel_trial_renders_the_verdicts_it_showed, test_a_stopped_run_recorded_before_the_change_is_refused_continuation) | `eval/src/praxion_evals/adherence/run_identity.py` (checks_digest, current_identity, measured_identity, diff); `eval/src/praxion_evals/adherence/cli.py` (identity_now) | PASS |
| REQ-16 | 11 test(s) -- `eval/tests/test_adherence_confinement_breach.py` (test_the_confinement_error_kind_is_an_errored_kind_that_neither_counts_nor_retries, test_a_session_that_never_started_and_whose_stderr_names_the_sandbox_is_broken, test_the_sandbox_refusal_in_a_tool_result_is_broken, test_a_refused_prescribed_command_is_broken_and_named, test_a_verifier_refused_curl_is_not_broken, test_a_researcher_refused_a_test_run_is_not_broken, test_a_role_outside_the_confined_kits_is_never_broken_by_any_signal); `eval/tests/test_adherence_confinement_stop.py` (test_the_first_session_with_a_broken_confinement_stops_the_run_in_both_arms, test_a_session_that_ran_stops_nothing_whatever_command_it_was_refused, test_the_stop_is_continuable_under_an_equal_identity, test_the_stop_is_refused_under_a_changed_checks_identity) | 6 test(s) -- `tests/acceptance/test_a_run_stops_on_its_first_broken_confinement.py` (test_the_first_session_showing_a_broken_confinement_is_the_only_one_launched, test_that_session_is_an_infrastructure_error_naming_its_evidence, test_the_run_is_reported_stopped_on_infrastructure, test_pairs_finished_before_the_stop_stay_on_the_record, test_a_refused_command_no_definition_prescribes_stops_nothing, test_a_role_outside_the_confined_kits_is_not_stopped_by_a_refusal) | `eval/src/praxion_evals/adherence/confinement.py` (confinement_breach); `eval/src/praxion_evals/adherence/model.py` (AdherenceErrorKind); `eval/src/praxion_evals/adherence/session_launch.py` (_assessed); `eval/src/praxion_evals/adherence/infra_stop.py` (step, _confinement_stop, redacted) | PASS (env-prefix exception; wrapper residuals: `td-555`) |
| REQ-17 | 2 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places) | 3 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_the_dry_run_shows_a_confinement_for_every_planned_session_of_a_confined_kit, test_the_dry_run_of_a_confined_kit_starts_no_model_session, test_commands_inside_the_confinement_run_without_a_prompt) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec) | PASS |
| REQ-18 | 5 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_read_is_denied_over_the_real_home_in_both_spellings, test_read_is_reopened_for_the_runner_the_copy_and_the_run_root, test_an_allow_read_entry_covering_a_credential_raises) | 1 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_the_session_token_file_is_unreadable_by_every_path_that_reaches_it) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (confinement_for, Confinement.__post_init__) | PASS (declared at $0; enforcement rests on the first paid run) |
| REQ-19 | 4 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_the_token_file_is_denied_in_both_spellings, test_no_credential_entry_sits_under_the_sandbox_home) | 1 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_an_operator_credential_location_in_the_real_home_is_unreadable) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (confinement_for) | PASS (declared at $0; enforcement rests on the first paid run) |
| REQ-20 | 4 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_each_credential_location_is_denied_under_the_real_home, test_every_acceptance_location_is_covered_by_a_credential_entry) | 3 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_the_real_home_is_readable_only_where_a_session_needs_it, test_the_real_home_beyond_what_a_session_needs_is_unreadable, test_a_sibling_of_the_runners_environment_in_the_real_home_is_unreadable) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (CREDENTIAL_LOCATIONS, confinement_for) | PASS (declared at $0; enforcement rests on the first paid run) |
| REQ-21 | 3 test(s) -- `eval/tests/test_adherence_cli.py` (test_a_dry_run_shows_a_confined_kits_confinement_places_and_program_order, test_a_dry_run_leaves_another_kits_line_without_confinement_or_places); `eval/tests/test_adherence_confinement.py` (test_the_three_session_credential_variables_are_dropped) | 2 test(s) -- `tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py` (test_a_confined_command_starts_with_no_session_credential, test_the_sessions_own_environment_is_the_one_it_had_before) | `eval/src/praxion_evals/adherence/cli.py` (_print_dry_run, _planned_spec); `eval/src/praxion_evals/adherence/confinement.py` (SESSION_CREDENTIAL_VARIABLES, settings_of) | PASS (declared at $0; enforcement rests on the first paid run) |

## Key Decisions

Two ADR drafts carry the architectural and behavioral decisions; the entries below are from `LEARNINGS.md § Decisions Made`, the plan, the pre-verification digest and the verifier's rulings.

**[systems-architect] Confine the implementer and verifier kits with the harness's OS sandbox (architectural; `dec-487`)**: Claude Code's Bash sandbox, `enabled` and `failIfUnavailable`, `allowUnsandboxedCommands: false`, `autoAllowBashIfSandboxed`, `denyWrite` over the copy, `denyRead` over the real home with `allowRead` for the runner's environment, `credentials` deny for files and variables, no `allowedDomains`; `READ_ONLY_BASH` stays in the tool grant and every other kit is unchanged. **Why**: command-text patterns cannot bound what pytest runs, and every prescribed form defeats them; the OS bounds writes at the root. **Alternatives**: narrow per-role allow patterns (rejected: they narrow nothing that runs and miss the prescribed forms); no grant with the vacuous checks scored not applicable (rejected: the kernel trials would measure none of the shell protocol); `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` (rejected: it also strips the hooks' environment and `CLAUDE_CONFIG_DIR`, the layer under test); the sandbox's user `settings.json` (rejected for `--settings`). The steelmanned runner-up is narrow patterns plus the sandbox with auto-allow off, the right choice if auto-allow turns out not to approve under print mode. Reversal trigger: the first paired run stops `confinement_broken` on a prescribed command refused while the sandbox was active; withdraw the grant entirely if a sandboxed command ever writes outside the sandbox.

**[systems-architect] Deliver the confinement as `--settings` JSON (inside `dec-487`)**: **Why**: it is a trusted scope for the `credentials` keys, the dry run already prints the planned argv so REQ-17 needs no materialization, and it leaves `install_user_scope`, which the live harness shares, untouched. **Alternatives**: the sandbox user `settings.json` written by `install_user_scope`. **Trade-off**: the argv grows by about 2 kB, visible in `ps`; it carries paths only, never a secret.

**[systems-architect] The confinement stop is its own rule, not a `StopRule` (inside `dec-487`)**: a per-record breach predicate with a non-counting, never-retried kind. **Why**: `StopRule` refuses counts below 3 on purpose, for transient channel failures, and a refused grant is deterministic configuration. It stops after the first such session, cheaper than finishing the pair, since the partner arm would hit the same settings. **Trade-off**: two stop paths in the loop, both ending as a `StopReason`, so the report and lineage read one shape.

**[coordinator, at rework] The first-breach stop has one exception, env-prefixed commands (recorded in `dec-487`)**: a refused prescribed command with a leading `VAR=value` is kept on the record but does not stop the run. **Why**: the sandboxing docs send such commands through the regular permission flow even inside the sandbox, which under `--permission-prompts none` is a refusal by design, not a broken confinement; the fixtures now declare `pythonpath`, so no prescribed form needs the prefix. **Cost**: a role that prefixes every test run yields a run that continues and measures nothing of its shell work; the refusals stay on the record and `td-555` tracks it. The exemption is per simple command (`PYTHONPATH=src pytest && ruff check .` still names `ruff`), `env X=1 pytest` is the `env` wrapper and still counts, and an `Operation not permitted` on a prescribed command counts even when env-prefixed, since the command ran and the block is the grant's.

**[systems-architect] Read a capped report by how the session ended, and set grader changes apart in the run's identity (behavioral; `dec-486`)**: the write-early check judges the closing title only on `EndedOnItsOwn`; C5 gains `FINISHED_FORMS` with the verifier alone; `MeasuredIdentity.checks` digests the runner's grading sources. **Why**: no capped session could pass both checks, and `tree` digests the checkout under test, not the grader. **Alternatives**: relax only C5 (rejected: a session stripping `[PARTIAL]` from an unfinished report would pass); drop the closing half of the write-early check (rejected: "finish last" would go unmeasured where the role had the turns); rely on `tree` (rejected); a hand-bumped catalog version (rejected: it is forgotten on the next semantic change, a digest cannot be). **Trade-off**: any edit to a grading module refuses continuation, even a cosmetic one, which is the conservative side.

**[implementation-planner] Decomposition into 20 steps, then 2 rework steps**: four driver bindings first (the five unbound Boundary Assumptions), then the `td-545` grader steps, then the `td-544` confinement steps, then the closing steps; no separate documentation step, because the two architecture documents are updated by the `[Architecture]` steps 10 and 17. **Why**: the instruction orders driver bindings before any production step, and the `td-545` steps are small, pure and independent of the confinement. The ledger flip is the last plan step by the coordinator's direction, though the architect had left it to the verifier PASS; if the verifier had failed the work, the two rows would have needed re-opening (verifier #warn-7).

**[implementation-planner] The breach stop must carry `scope="both-arms"`**: `lineage.continuable` reads an `InfraStopped` as continuable only then, and the architecture says the stop is continuable subject to the identity diff. The confinement digest lives on each session record, not in the identity, so a settings fix after a stop allows `--continue` and the finished pairs are reused, while a grader edit still refuses it.

**[implementer] Where the breach is read and what it reads**: the tool-result texts and stderr that `confinement_breach` reads exist only inside `attempt` (a measured record keeps neither), so the reading sits in `session_launch._assessed`. Proof sessions go through `attempt` too, so a broken confinement at proof reads as a failed proof (`NotBuilt`), not a run stop.

**Note on the ADR draft.** The rework added `sandbox.network.strictAllowlist: true` and `permissions.blockReadsOutsideWorkingDirectories: true` to the settings (`ea7d3a98`; keys checked against the sandboxing and settings-reference pages on 2026-11-01). `dec-487`'s Decision bullets, written before the rework, list neither; this spec's What Was Built row for the confinement module is the record until the draft is amended.

## Verification and Rework

The first pass over `1dd63cf5..99f5f122` (24 commits, +6767/-112) read PASS WITH FINDINGS: all 21 acceptance criteria and every health guard met, no FAIL, twelve WARN. Two rework rows followed (`REWORK_MANIFEST.md`), both executed in place as plan Steps 21 and 22 and delta-verified over `99f5f122..e02d302d` (8 files, +426/-43).

| Finding | Subject | Disposition at close |
|---|---|---|
| #warn-1 | Network refusal rested on prompt denial, not the proxy | Resolved: `strictAllowlist: true` |
| #warn-2 | The role's Read tool is outside the sandbox | Resolved: `blockReadsOutsideWorkingDirectories: true`; the `--settings` `allowRead` for the venv and the uv prefix still re-opens them for sandboxed commands |
| #warn-3 | Env-prefixed commands are not auto-approved, so a prescribed refusal would stop the first paid run | Accepted with a recorded exception (REQ-16 note, ADR draft); `td-555` |
| #warn-4 | A too-narrow read allow-list was invisible to the stop | Resolved: `BLOCKED_BY_SANDBOX`, `confinement_breach(shell_runs)`. Residual: a prescribed command that hits a deny by design stops the run, failing closed at the cost of one session (`td-555`) |
| #warn-5 | The stop classified the clipped command and missed wrappers | Resolved: raw classification, `timeout`, `bash -c`, `sh -c`, `env -i` unwrap. Residual: `python -W ignore -m pytest`, `python3 -X dev <script>`, `nice pytest`, `time pytest` (`td-555`) |
| #warn-6 | C5 read a finished report quoting `[pending]` as unfinished | Resolved |
| #warn-7 | `td-544` and `td-545` flipped before the verdict, with a placeholder `resolved-by` | Open: set `resolved-by` to the merge commit at finalize |
| #warn-8 | Six `green-over-ceiling` sections in `TEST_RESULTS.md` | Advisory |
| #warn-9 | `test_an_interrupt_inside_a_run_takes_the_runner_down_with_it` failed once under load | Already tracked as `td-535`; the clean rerun passed |
| #warn-10 | The acceptance design over-read the bodies of `tasks.session_spec` and `tasks.allowed_tools` | Accepted with its disclosure; no scenario's oracle traces to those bodies |
| #warn-11 | The dry-run copy path changed for every kit | Recorded in the delta section above; no changelog exists to carry it |
| #warn-12 | No `SPEC_DELTA.md` | Closed by this archival |

The calibration verdict reads under-calibrated. The delta also asked, as PM-3, whether `claude doctor --settings <json>` could prove the settings are accepted at $0; it has no `--settings` option, so a variant (write the dry run's JSON to a scratch `CLAUDE_CONFIG_DIR/settings.json` and fail on any validation error `claude doctor` reports) was filed as `td-554` and not built.

## Deferred at Close

- **The sandbox is unproven in a real session.** See Assumptions Only the First Paid Run Can Settle. Read the first paid run's refused-command records before widening any breach reading (`td-555`).
- **Other kits.** Widening the grant to the sentinel or the test-engineer is out of this scope; a follow-up ledger row is the verifier's or the orchestrator's call, and none was filed.
- **Cosmetic and minor.** `report._ending_lines` words the stop as "N <arm> sessions in a row ended in confinement_broken"; for this stop N is 1. The broken session is still graded (a judge, when configured, may be called for it) and the result then discarded: one session at most. Step 15's review note O1 (`expanduser` on `~nosuchuser`) remains.
- **Mutation coverage.** The sensor refused `not-flat-layout` on every `mutation: on` step, so the confinement module's survivors are unmeasured.

## Open Findings

| Ledger id | Severity | Class | Owner | Finding |
|---|---|---|---|---|
| `td-554` | suggested | coverage-gap | implementer | The dry run proves the confined kits' `--settings` JSON is declared, not accepted: `claude -p` silently drops invalid entries (pre-mortem PM-3). `claude doctor` reports settings-file validation errors without a session but has no `--settings` option, so a $0 check must write the JSON to a scratch `CLAUDE_CONFIG_DIR/settings.json` (user scope honors `credentials` and `strictAllowlist` as `--settings` does) and fail on any reported drop. This closes the dropped-key half of PM-3, not enforcement. Verify `doctor`'s output for a user-scope file before building. |
| `td-555` | suggested | other | unassigned (proposed: implementer) | The breach reading has three known residuals, each accepted for the first paid run: (1) wrappers it does not unwrap, `python -W ignore -m pytest`, `python3 -X dev <script>`, `nice` and `time`, whose refusal does not stop the run; (2) an `Operation not permitted` on a prescribed command counts as a breach even when it hit a deliberate deny (a write into the plugin copy or the sandbox home), failing closed at the cost of one session; (3) a refused env-prefixed command is recorded but never stops the run, so a role that prefixes every test run produces a run that measures nothing of its shell work. |

Also open and not ledgered as new rows: #warn-7 (the `resolved-by` placeholder on `td-544` and `td-545`), and `td-535` (pre-existing, tracked). Both rows are `suggested`, so neither blocks the merge.

## Gotchas Worth Keeping

- **A detector fed a display-clipped form of its input.** The run-stop classified the redacted, 300-character record text, so a clip that split a quote made the parser see no command. Classify the raw input, then clip for the record (verifier #warn-5).
- **A marker test that matches prose.** Testing for `[pending]` anywhere in a section body fails any report that explains the marker. Match the section whose body is the marker, the shape the definition's skeleton writes (verifier #warn-6).
- **A risk-table mitigation with no code behind it.** The plan said an `Operation not permitted` result would be recorded as evidence; `grep` found nothing reading it, and an over-tight allow-list would have silently zeroed the kernel trials (verifier #warn-4). Confirm the mitigation's code exists before leaning on it.
- **A permission rule never matches past an assignment.** An env-prefixed command goes through the regular permission flow even inside the sandbox, which under `--permission-prompts none` is a denial. The prescribed forms must be written so no prefix is needed; the fixtures' `pythonpath` is why `PYTHONPATH=src` is no longer one.
- **`~` names the sandbox home.** The session's `HOME` is the sandbox home, so every read, write and credential path in the settings must be absolute and real-home.

## Follow-up

- At merge, finalize rewrites the two draft ids in the header and Key Decisions to `dec-NNN`; set `td-544` and `td-545` `resolved-by` to the merge commit (#warn-7).
- Before finalize, amend `dec-487`'s Decision to list `strictAllowlist` and `blockReadsOutsideWorkingDirectories`, and consider recording the dry-run copy-path change there (#warn-11).
- The first paired run of a confined kit is the proof; start it with the stop in mind and read its refusal records before widening anything.
- When this spec was archived, `.ai-state/token_budget_baseline.json` and `.ai-state/observations_summary.jsonl` were modified and uncommitted in the worktree. Neither is part of this change; inspect or revert them before committing.

Verification path: `cd eval && uv run pytest -q`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright src/` from `eval/`; `python3 -m pytest tests/acceptance/test_a_run_stops_on_its_first_broken_confinement.py tests/acceptance/test_capped_reports_are_judged_on_their_opening.py tests/acceptance/test_confined_kits_run_their_shell_work.py tests/acceptance/test_confined_kits_stay_inside_their_sandbox.py tests/acceptance/test_finished_verifier_report_passes_c5.py tests/acceptance/test_other_kits_keep_their_grant.py tests/acceptance/test_recorded_runs_keep_their_outcomes.py tests/acceptance/test_relaxed_checks_keep_their_canaries.py -q` and `python3 scripts/resolve_test_scope.py | sh -e` from the repository root; and `praxion-evals-adherence --dry-run` with a stand-in `claude` first on `PATH` to read the confinement each session would receive, at no cost.
