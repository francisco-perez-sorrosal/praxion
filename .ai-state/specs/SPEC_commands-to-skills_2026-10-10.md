# Spec: commands-to-skills (the 44 slash workflows become skills; the command artifact family is retired)

**Task slug**: `commands-to-skills`
**Feature**: Every Praxion slash workflow, the 44 user- or model-invoked workflows that lived as files in `commands/`, becomes a skill at `skills/<name>/SKILL.md` under the same name and with unchanged behavior, and the slash/custom command artifact family leaves Praxion: its directory, its plugin-manifest registration, its authoring skill, the Cursor and Codex command exporters, its architecture-model element and every process artifact that teaches the concept.
**Tier**: Full (cross-cutting: about 290 files, 24 requirements). Budget 32 spawns; 18 charged (38 raw, 4 heavy resumes) plus 24 step-loop iterations.
**Pipeline branch**: `worktree-commands-to-skills` (base 542f63f1; fast-forwarded to main as 46b1d23e)
**Start date**: 2026-10-10
**End date**: 2026-10-11
**Archived**: 2026-10-11 (post-merge; merged to main as `46b1d23e`, released as v0.49.0; the file name carries the design date)
**Status**: completed -- final verification PASS WITH FINDINGS after three rounds (round 1 FAIL on a record gap, rounds 2 and 3 0 FAIL, 7 WARN); all 24 requirements pass, REQ-23 by user attestation; all eleven Spec Questions closed and ratified
**ADRs**: `dec-449` (architectural -- retire the command artifact family), `dec-448` (architectural -- merge command-crafting into skill-crafting), `dec-446` (architectural -- delete the Cursor and Codex command exporters), `dec-447` (behavioral -- gates, dev-link, arguments and the pull-request rule scope follow the workflows into skills). Re-affirmed: `dec-173`, `dec-340`, `dec-434`, `dec-437`.
**Evidence base**: 43 commits 542f63f1 .. 3f353ab5; the root pocket's full run at 0a8d10e6 (12,051 passed, 0 failed) and the merged-main run after c13273b6; the 683-node outer loop under `tests/acceptance/`; `MEASUREMENTS.md`; the verifier's three reports; the calibration row dated 2026-10-11; the release run for v0.49.0.

## Feature Summary

Move all 44 workflows into the skills tree without changing what any of them does, then delete the command family everywhere it was carried, so that a person or a model that used a workflow before uses it the same way after (same slash name under the plugin namespace, same invocation mode, arguments, tools, procedure and side effects), and so that no agent or author is taught that Praxion has, or should grow, a command artifact family. The user's constraint: "Remember to preserve all the semantics when moving commands to skills".

## Goal

Every Praxion slash workflow — the 44 user- or model-invoked workflows that live today as files in `commands/` — becomes a skill at `skills/<name>/SKILL.md` under the same name and with unchanged behavior, and the "slash/custom command" artifact family leaves Praxion entirely: its directory, its plugin-manifest registration, its authoring skill, the Cursor and Codex command exporters, its architecture-model element, and every process artifact that teaches the concept.

### Goal Notes — interpretation, assumptions, objections

- **Interpretation (from the brief's Task Intent, user's words).** "Transparently provide the same functionality for the llms/agents using them" means: a person or a model that used a workflow before uses it the same way after — same slash name under the plugin namespace, same invocation mode (user-only versus model-invocable), same argument meaning, same permitted tools, same procedure, same scripts invoked, same files written and side effects. Form may change only within the normalization bound the user chose at intake ("normalize during migration", qualified by "preserve all the semantics").
- **Assumption A1 — how semantics preservation is graded.** Byte equality of bodies is not required (the user chose normalization). Preservation is graded two ways: per-field mechanical checks against the frozen before-state manifest, and a human-judgment light review of each move batch's body diff. The manifest's body digests serve the reviewer; they are not an equality assertion.
- **Assumption A2 — the only permitted behavior changes** are the three restorations the brief names (S3): positional arguments read from the first token (two workflows), the dashboard honoring a supplied project root, and literal dollar amounts in one workflow's cost text no longer being read as argument placeholders; and a fourth accepted after verification (SQ-07, user-delegated decision 2026-10-11): the dashboard resolves its launcher from the checkout's scripts directory, the PATH, or the plugin's scripts directory, where the old form named only the checkout-local path and so could never start the dashboard in a managed project. Each restores what the old form intended and failed to deliver. The user later added one deliberate narrowing outside the workflows themselves (D1, REQ-17).
- **Assumption A3 — "frozen history" and the named exceptions.** Requirements about references to the retired directory or the retired authoring skill exclude: (a) frozen history — finalized and draft decision records, archived specs, sentinel, metrics and skill-harvest reports, the changelog, the dated independent-analysis and comparison documents, tech-debt ledger rows and the calibration log's past rows, recorded eval fixture streams; (b) the frozen before-state manifest and tests whose purpose is to assert that a retired surface stays absent; (c) installer legacy-cleanup logic and its tests, which name the old Cursor and Codex projection locations precisely in order to remove them; (d) the conversion recipe in the user-invoked-skills reference, which names the legacy file shape as the input of a conversion; (e) Claude Code platform vocabulary — its own built-in slash commands, its project-level commands directory, and its disable-slash-commands launch option. The living state documents (`.ai-state/DESIGN.md`, the deployment document, the footprint registry) are in scope, not frozen.
- **Objection O1 — S10's ratchet clause is time-dependent. Resolved by the user, 2026-10-10.** The token ratchet compares today's always-loaded byte count with the oldest sample in a trailing 30-to-35-day window; on an unchanged tree it turns red from 2026-10-13 (oldest sample 65,505 bytes against 65,708 today) and needs about 848 fewer bytes from 2026-10-18. User decision: "I want explicitly to circumvent the rule for this session and the next ones." Before this pipeline's first production commit, the orchestrator adds on main an explicit, dated operator suspension of the ratchet's governed-byte half; the listing-ceiling half stays enforced and the gate prints the suspension on every commit. Consequence for this spec: the ratchet's governed-byte half is not an acceptance criterion while suspended; FC-02 (bytes at or below the pre-change baseline of 65,708) is the byte bound the verifier grades, and FC-03 (listing at or below 9,243) stays. The attribution rule proposed in the first spec pass is dropped.
- **Assumption A4 — where the always-loaded measurement reads the global guidelines.** The token instrument reads the installed global guidelines file, which on this machine resolves to the main checkout's rendered copy (absent from the worktree), not the worktree's template. During the pipeline, the template edit's effect is therefore read from a rendered copy of the edited template; the final always-loaded reading is taken from the canonical checkout after merge, once the template is re-rendered there. The planner places both measurements.
- **Assumption A5 — the user dogfood (S13) is user-run.** It cannot be driven by a test inside this pipeline (a skill built on a worktree branch is invisible to the building session); it is recorded as a user attestation, and the mechanical requirements carry everything a test can reach.
- **Assumption A6 — Cursor argument passing.** Whether Cursor passes text typed after a skill's name into the skill is undocumented. No requirement constrains Cursor argument substitution; the old Cursor export performed none either. Cursor parity means each workflow appears once in Cursor's picker and invokes the skill.
- **Decision D1 — the pull-request rule's path scope is narrowed deliberately (user, 2026-10-10).** That rule's scope today matches any workflow file whose name merely contains "pr" or "merge" (the project, praxion and scaffolding workflows among them), and a mechanical move to the skills tree would extend the over-match to unrelated skills such as `project-exploration`, `llm-prompt-engineering`, `python-prj-mgmt` and `onboard-project`, injecting a 6.7k-character rule whenever one is read. The user decided against preserving the over-match: the semantics constraint protects the workflows, not the accidental loading of a rule. REQ-17 therefore names exactly the review-pr, merge-worktree and release skills (plus the rule's existing GitHub-docs and git-conventions entries). This is the one deliberate behavior change besides the three restorations: the rule no longer loads when, for example, the project-metrics workflow is read.
- **Assumption A8 — default discovery.** Claude Code scans a plugin's `commands/` location by default when the manifest does not declare one, so removing the registration alone would not stop a re-created file from loading; REQ-02 therefore asks the suite to fail if a workflow file reappears there.
- **Out of scope (deferred, each to a tech-debt row):** renaming any workflow or merging it with a near-pair skill; the skill-crafting refresh (a second pipeline after this one releases); renaming the `tests/commands/` test package; a Codex implicit-invocation policy file for user-only skills; a mechanical skills-catalog completeness test; the 36 pre-existing hook-quoting validator warnings.
- **Prior decisions.** Several finalized decisions name commands as one half of a composition (dec-014, dec-015, dec-029, dec-055, dec-153) and dec-173 fixes the no-positional-argument contract of the resume-rework workflow; dec-340, dec-437 and dec-434 are the precedents for workflow-shaped skills. The design phase disposes each (supersede in part, re-affirm); this spec contradicts none of them, and dec-173's contract is preserved by the semantics requirement.
- **Brownfield baseline.** No archived spec covers the command family (the ralph-lite and step-loop specs cover only precedent skills), so no spec delta is expected.
- **Spec Questions — all resolved by the user, 2026-10-10.** (Q1) Ratchet: suspended by an explicit dated operator suspension; FC-02 and FC-03 are the graded bounds (O1). (Q2) Named exceptions: confirmed as written in Terms: draft decision records are frozen history, installer legacy-cleanup logic and its tests may name the old Cursor and Codex locations, and the conversion recipe may name the legacy file shape. (Q3) Pull-request rule scope: narrowed to the three named skills (D1).
- **Research-stage context review folded in (second spec pass).** The exact form of the user-only invocation line, the tool list on one line, the quoted argument hint, byte-identical model-invocable descriptions and a Codex export probe over the migrated skills (REQ-04); argument-use evidence that no longer accepts a harness path variable alone, and the description check kept and re-scoped to skills rather than retired (REQ-16); the rendered-copy and post-merge readings for the template edit (FC-02 notes, A4); the hackathon block's commit carrying its recorded block history (REQ-19).

## Acceptance Criteria

Terms (workflow, frozen history, named exceptions, normalization, deferrals) are defined in the Terms subsection of the Behavioral Specification. Each criterion names the requirements that carry it.

- [ ] `commands/` is gone, `.claude-plugin/plugin.json` neither registers nor mentions commands, and `claude plugin validate .` passes with only the pre-existing warnings (hook quoting, the root `CLAUDE.md`, `agents/README.md`, `agents/CLAUDE.md`) and none mentioning `commands/`, at the final commit and at every commit boundary of the pipeline (REQ-02)
- [ ] The frozen before-state manifest exists before any workflow moves and is the only before-state source the acceptance tests read (REQ-01)
- [ ] Each of the 44 workflows in the manifest is a skill whose name, invocation mode, tool set, argument hint and placeholder discipline match the manifest (REQ-03, REQ-04)
- [ ] Each workflow behaves as before; the only behavior changes are the four restorations (A2), each observable on its own, and the deliberate narrowing of the pull-request conventions' scope (REQ-05, REQ-06, REQ-07, REQ-08, REQ-17)
- [ ] The two commit-process workflows carry the canonical commit-process text byte for byte, and `python3 scripts/sync_canonical_blocks.py --check` passes at every commit boundary (REQ-09)
- [ ] Authoring guidance for user-invoked skills lives in `skills/skill-crafting/references/user-invoked-skills.md`, and `skills/command-crafting/` is gone with no live reference left to it (REQ-10)
- [ ] No tracked file outside frozen history and the named exceptions refers to `commands/` as a live location, and `python3 skills/skill-crafting/scripts/validate_references.py --all --strict` is clean (REQ-11)
- [ ] Cursor and Codex installs export no commands, sweep their stale projections, and complete their dry runs (REQ-12, REQ-13)
- [ ] Live-linked development installs serve skills from the checkout (REQ-14)
- [ ] The gates watch skill bodies where they watched workflow files, no gate or hook names the retired directory, and the sentinel catalog describes the same scope (REQ-15, REQ-16)
- [ ] The pull-request conventions load for exactly the review-pr, merge-worktree and release skills and for no other skill (REQ-17)
- [ ] The architecture model, design document and developer guide carry no commands element, and their projection and render checks pass (REQ-18)
- [ ] The always-loaded set, the agents and the shipped canonical blocks no longer describe a command artifact family, and the footprint bounds below hold (REQ-19)
- [ ] The skills catalog has a row for every skill directory and the top-level readme's counts match disk (REQ-20)
- [ ] Editing a moved workflow yields a narrow test selection, not a widening to the whole suite, that contains every test that guarded its old file and still exists, deliberate deletions excepted (REQ-21)
- [ ] The full suite is green under the bare CI invocation on Python 3.11 or later, and `pre-commit run --all-files` is clean (REQ-22)
- [ ] The user's dogfood session confirms the listed invocations behave as before and one model-invocable workflow triggers by natural phrasing; recorded as a user attestation (REQ-23)
- [ ] Decision records, deferral rows and the calibration row exist (REQ-24)
- [ ] Token ratchet (user decision, 2026-10-10): while the user's dated ratchet suspension is in force, the governed-byte half of `python3 scripts/check_token_ratchet.py --check` is not an acceptance criterion; FC-02 is the byte bound graded in its place, and the listing-ceiling half stays enforced and is graded through FC-03

### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | always-loaded-tokens | always-loaded token count (the reading's tokens figure, tokenizer basis) | below | 25000 tokens | reference: the published always-loaded budget | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | always-loaded-tokens | always-loaded byte count (the reading's bytes figure) | at or below | the baseline byte count | baseline: measured before the first change to any always-loaded file (65,708 bytes at the Base commit) | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | listing-tokens | listing token count of model-visible descriptions (the reading's listing tokens figure, tokenizer basis) | at or below | 9243 tokens | reference: the frozen listing ceiling in the token baseline | `python3 scripts/measure_token_budget.py --json` |
| FC-04 | prompt-size | fail-severity line-count findings over skill bodies, skill references and agent definitions | at or below | 0 findings | reference: the fail ceilings the instrument applies | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-05 | prompt-size | warn-severity line-count findings over skill bodies, skill references and agent definitions | at or below | the baseline count | baseline: measured before the first change to a skill or agent file (3 warn findings at the Base commit) | `python3 scripts/check_agent_prompt_size.py --json` |

Footprint notes:

- FC-02 and the global guidelines template: the instrument reads the installed global guidelines file, which on this machine is the main checkout's render, not the worktree's template. While the pipeline runs, the template edit's effect is read from a rendered copy of the edited template; the final FC-01 and FC-02 readings are taken from the canonical checkout after merge, once the template is re-rendered there.
- FC-03: the model-invocable descriptions stay byte-identical (REQ-04), so the listing moves only by the retired authoring skill's description leaving and the skill-authoring description changing.

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| test-selection-size | the instrument replays the change sets of recent commits over the current tree; none of them can name a moved workflow's new location, so the remap this change makes is invisible to it, while old locations that no longer exist widen to the full suite by design, so the reading would measure the move rather than selection quality; the selection obligation is carried behaviorally by REQ-21 |
| hook-latency | the registry declares no instrument for it; the hook edits in scope drop a retired path pattern and reword a docstring |
| spawn-count | the only spawn-count command counts a pipeline that has already run, not a change; the edits in scope repoint paths and vocabulary in the coordination rule and its reference |

## Requirements

### Terms

- **Workflow** — one of the 44 slash workflows recorded in the frozen before-state manifest (REQ-01). The readme and guidance file inside `commands/` are not workflows.
- **Frozen history** — finalized and draft decision records, archived specs, sentinel, metrics and skill-harvest reports, the changelog, the dated independent-analysis and comparison documents, tech-debt ledger rows, past calibration-log rows, dated eval reports, `.ai-state/DESIGN_CHANGELOG.md`, and eval fixtures including recorded eval streams. Living state documents (`.ai-state/DESIGN.md`, the deployment document, the footprint registry) are not frozen.
- **Named exceptions** — (a) everything under `tests/acceptance/`, whose tests and fixtures (the frozen before-state manifest and selection record among them) name the old locations on purpose, and any other test whose purpose is to assert that a retired surface stays absent; (b) installer legacy-cleanup logic and its tests, which name the old Cursor and Codex projection locations in order to remove them; (c) the conversion recipe in the user-invoked-skills reference, which names the legacy file shape as a conversion input; (d) Claude Code platform vocabulary: its built-in slash commands, its project-level commands directory and its disable-slash-commands launch option; (e) the `tests/commands/` test package, which keeps its name.
- **Normalization** — the form-only changes the user allowed during the move: the name field added; a user-only workflow's description reshaped to one plain line within the bounds of REQ-04, while a model-invocable workflow's description stays byte-identical; the argument hint quoted and completed; arguments read through the whole-argument placeholder; relative-link depth corrected; prose that names the artifact kind saying "skill" instead of "command"; the tool set written as a list. Procedure steps, script invocations, tables and tone otherwise stay.
- **Deferrals** — renaming any workflow or merging it with a near-pair skill; the skill-crafting refresh (a second pipeline after this one releases); renaming the `tests/commands/` package; a Codex implicit-invocation policy for user-only skills; a mechanical skills-catalog completeness test; the pre-existing hook-quoting validator warnings.

### REQ-01: The before-state is frozen before anything moves

**When** the acceptance designer prepares the outer-loop tests at the Base commit, before any workflow file has moved
**the system** holds a frozen before-state manifest at `tests/acceptance/fixtures/command_migration/manifest.json`, generated from the 44 workflow files in `commands/`, with one entry per workflow recording at least: its frontmatter keys; its description text; its argument hint, if any, and the type that hint parses as; its tool set as a list (a single scalar tool becomes a one-item list); its invocation mode; a content digest and the line count of its body; the argument placeholders its body uses; its relative link targets; its literal references to other workflow files; whether it carries the canonical commit-process text; whether it references the plugin-root variable; the repository scripts its body invokes; and its heading outline; the totals read 44 entries, 33 user-only and 11 model-invocable, 37 declaring an argument hint
**so that** every later check of semantic equivalence reads a fixed record rather than repository history, which matters because the source files are gone after the move and a shallow CI clone lacks the Base commit.

### REQ-02: The command family is no longer registered

**When** the plugin is validated or loaded after the change
**the system** has no `commands/` directory, its `.claude-plugin/plugin.json` carries no commands registration, keyword or description mention, and `claude plugin validate .` reports no error and no warning outside the pre-existing set, which is the hook-quoting warnings and the missing-frontmatter warnings for the root `CLAUDE.md`, `agents/README.md` and `agents/CLAUDE.md`; no warning mentions `commands/`, and there is no phantom entry for the old directory's readme or guidance file; the same validation passes at every commit boundary of the pipeline, because the registration and the directory change together; and a workflow file later placed back into a `commands/` directory makes the test suite fail instead of being silently registered, since Claude Code scans that location by default once the manifest stops naming it
**so that** Claude Code discovers every Praxion workflow through the skills registration alone, no session ever loads a manifest that points at a missing directory, and the creation of new commands stays retired.

### REQ-03: Every workflow is a skill with the same name and invocation mode

**When** a session lists or invokes Praxion's workflows
**the system** provides, for each of the 44 workflows in the manifest, a skill at `skills/<name>/SKILL.md` whose `name` equals its directory name and whose `disable-model-invocation` value equals the manifest's invocation mode (the 33 user-only workflows stay user-only, the 11 model-invocable workflows stay model-invocable), invocable as `/praxion:<name>`
**so that** a user types the same slash name as before, and a model can reach exactly the workflows it could reach before and no others.

### REQ-04: Each skill's declared contract matches its old file

**When** a migrated skill's frontmatter and body are read
**the system** shows an `allowed-tools` list written on one line, whose set equals the manifest's tool set; an `argument-hint` present exactly when the manifest recorded one, written as a single quoted value on one line, and then a body that reads its arguments through `$ARGUMENTS` or an indexed form of it; for each user-only workflow, the line `disable-model-invocation: true` exactly, unquoted, on a line of its own with nothing else on it; for each of the 11 model-invocable workflows, a description byte-identical to the manifest's; for every workflow, a non-empty description of at most 1024 characters with no angle brackets; no body text the harness could take for an argument placeholder by accident, meaning no unescaped literal dollar amount and no shell-style default attached to an argument placeholder; and running `codex/config/export-codex-skills.py` over the migrated skills into a scratch directory completes without error
**so that** the contract a user or model sees for each workflow is the one its old file declared, no stray dollar sign or shell default silently changes what text reaches the model, the model-visible listing neither re-counts a user-only description nor drifts, and the Codex export of the whole skill set cannot be broken by one skill's frontmatter shape.

### REQ-05: Behavior is preserved across the move

**When** a user or model invokes any migrated workflow by its former slash name with the same input as before
**the system** performs the same workflow as before: the same argument meaning, the same permitted tools, the same procedure steps in the same order, the same scripts invoked (compared as resolved targets), the same files written, the same side effects, the same help text where a workflow had one, and every relative link resolving to the same target document as before, a link to a sibling workflow now resolving to that workflow's new location; the only behavior changes are the three restorations in REQ-06, REQ-07 and REQ-08, plus the user's deliberate narrowing of which skills load the pull-request conventions (REQ-17); wording changes stay within normalization; and each move batch's body changes are reviewed against this requirement before the batch is accepted
**so that** the user's constraint, "preserve all the semantics when moving commands to skills", holds for every workflow, and nothing that relied on a workflow's behavior notices the move.

### REQ-06: Positional arguments are read from the first token

**When** a user invokes `create-simple-python-prj` or `document-api` with arguments
**the system** treats the first token typed after the workflow's name as the first argument: for `create-simple-python-prj`, the project name, then the description, the package manager and the target directory in that order; for `document-api`, the target path; and when a later token is absent it applies the documented default: the description "A simple Python project scaffolding", the package manager pixi, the target directory `$HOME/dev`, and for `document-api` the current working directory; the project name stays required
**so that** `/praxion:create-simple-python-prj probe "desc" uv /tmp` creates a project named probe, described as desc, managed by uv, under the temporary directory, restoring the meaning the old `$1` form intended and missed because the harness numbers arguments from `$0`.

### REQ-07: The dashboard honors a supplied project root

**When** a user invokes `dashboard` with a project root
**the system** starts the dashboard for that root, or reports the one already running for it, and with no root supplied it uses the current directory, finding the launcher in the checkout's scripts directory, on the PATH, or in the plugin's scripts directory (amended after verification, SQ-07)
**so that** the documented argument takes effect, which the old `${ARGUMENTS:-$(pwd)}` form never allowed: it always fell back to the current directory; and the dashboard starts in a managed project too, where the old form's single checkout-local path never existed.

### REQ-08: Literal dollar amounts read as money

**When** `eval-praxion` presents its cost guidance (a run-level spend cap of $50 by default; roughly $15 to $40 for a full canary run)
**the system** shows those amounts literally, as an escaped form such as `\$15` renders, never as substituted argument text
**so that** the cost guidance a user reads before a paid run is the guidance the workflow's author wrote.

### REQ-09: Commit-process text stays canonical

**When** the `co` or `cop` skill is read, or the canonical-block sync check runs
**the system** finds the commit-process fence in each of the two skills byte-identical to `claude/canonical-blocks/commit-process.md`, and `python3 scripts/sync_canonical_blocks.py --check` passes at every commit boundary, including the commit that moves `co` and `cop`
**so that** the commit procedure shared with managed projects keeps one source, and the move never leaves the sync check unable to find its consumers.

### REQ-10: Authoring guidance for user-invoked skills lives with skill authoring

**When** an author looks for how to write a workflow a user invokes by slash name
**the system** provides `skills/skill-crafting/references/user-invoked-skills.md`, reachable from `skill-crafting`, covering description length by consumer (user-only versus model-invocable); argument-hint rules (omit when there are no arguments, list every option the body reads, always quote); arguments and dynamic context, namely `$ARGUMENTS`, its indexed forms with the live-probed numbering in which `$0` is the first argument, named arguments with the gotcha that declaring them suppresses the automatic argument append unless the body carries a placeholder, command output injected before the body renders, and the skill-directory and plugin-root variables; runtime and permissions; debugging frontmatter that fails to parse silently; and a recipe for converting a legacy command file into a skill; while `skills/command-crafting/` no longer exists and no tracked file outside frozen history refers to `command-crafting`
**so that** there is one place to learn how to author any skill, user-invoked or model-invoked, and no guidance teaches authors to create commands.

### REQ-11: Nothing points at the retired location as live

**When** every tracked file is searched for a reference to a workflow file under `commands/`, or to that directory as a place Praxion keeps or reads workflows
**the system** returns no match outside frozen history and the named exceptions, and `python3 skills/skill-crafting/scripts/validate_references.py --all --strict` reports no finding
**so that** no reader, agent or tool follows a reference into a directory that no longer exists.

### REQ-12: Cursor reaches workflows as skills, and stale exports are swept

**When** Praxion is installed or reinstalled for Cursor
**and** a previous install left exported workflow files in the Cursor commands directory, for example `.cursor/commands/co.md`
**the system** exports no workflow files there any more (`cursor/config/export-cursor-commands.py` and its tests are gone), removes each file in that directory that is an export those releases wrote, that is one of the 44 workflow names whose first line is the description header the exporter prepended, or the guidance page the exporter copied under the Claude guidance file name (amended twice after verification, orchestrator, ratification pending), leaves every other file there untouched, a user's own file included even when it is named after a workflow, removes the directory only when it is left empty, reports how many files it removed, and completes the Cursor dry run without error and without writing
**so that** each workflow appears once in Cursor's picker, through the skills Cursor already loads, and a user's own Cursor commands survive the upgrade.

### REQ-13: Codex reaches workflows as skills, and stale wrappers are pruned

**When** Praxion is installed or reinstalled for Codex into a project
**and** a previous install left command-wrapper skills there, for example a `praxion-command-co` wrapper carrying the legacy wrapper marker
**the system** generates no command wrappers any more (`codex/config/export-codex-command-skills.py` and its tests are gone), prunes every legacy command wrapper, provides every migrated workflow through the regular Praxion skill wrapper named after the skill and pointing at the skill's definition as its authoritative source, produces those wrappers without a parse error for any migrated skill's frontmatter, and completes the Codex dry run without error and without writing
**so that** a Codex user invokes each workflow once, by its skill name, with no stale duplicate left behind.

### REQ-14: Live-linked development serves skills from the checkout

**When** a developer installs with `--dev-link`
**the system** links the installed plugin's skills to the working checkout together with hooks and scripts, links no commands tree, restores the fetched copy on `--dev-link=off`, and `scripts/test_install_dev_link.py` passes
**so that** an edit to any workflow is live in the developer's next session without a reinstall, as edits to workflow files were before.

### REQ-15: Gate liveness watches skill bodies

**When** a skill body runs a repository script through the ambient interpreter
**the system** has its gate-liveness check, `python3 scripts/check_gate_liveness.py`, count that call as an invocation site for the uninvoked-gate check (GL04) and inspect that script in the ambient-import check (GL05) exactly as it does for an agent definition: a skill that runs a script needing a package the ambient interpreter lacks produces a GL05 finding, and a gate script whose only caller is a skill body produces no GL04 finding
**so that** the ambient script calls that move from workflow files into skill bodies stay under the same liveness discipline instead of going unchecked.

### REQ-16: Argument-hint conformance covers skills, and no gate names the retired directory

**When** the artifact-conformance check, `python3 scripts/check_artifact_conformance.py`, runs
**the system** reports under S04 any skill that declares an argument hint but whose body never reads its arguments, and stays silent for a skill that declares a hint and reads them; a body whose only dollar-brace text is a harness path variable such as `${CLAUDE_PLUGIN_ROOT}` or `${CLAUDE_SKILL_DIR}` counts as not reading its arguments; the description check C04 stays an active check, now over skills, so a skill whose description is empty or a placeholder is reported under C04; no gate, hook or pre-commit pattern names `commands/` as a scanned location; and the sentinel catalog's row for every check whose scope changed describes the scope that check scans, so `tests/test_sentinel_check_triangle.py` and `tests/test_sentinel_row_contract.py` pass
**so that** the argument-hint and description discipline the old files were held to follows them into skills, a path variable can no longer pass for argument use, and the audit catalog never describes a scope the checks no longer have.

### REQ-17: The pull-request conventions load for exactly the pull-request, merge and release skills

**When** an agent reads a skill
**the system** loads `rules/swe/vcs/pr-conventions.md` when that skill is `skills/review-pr/SKILL.md`, `skills/merge-worktree/SKILL.md` or `skills/release/SKILL.md`, and does not load it for any other skill, for example `project-exploration`; the rule's path scope names exactly those three skills plus its existing `.github/**/*.md` and `rules/swe/vcs/git-conventions.md` entries; and the generated `rules/_manifest.yaml` records the same scope
**so that** moving the pull-request, merge and release workflows keeps the conventions that govern them, while reading an unrelated skill no longer pulls a large rule into context, a deliberate narrowing the user decided (the old scope also caught any workflow whose name merely contained "pr" or "merge").

### REQ-18: The architecture model has no commands element

**When** the architecture model, `.ai-state/DESIGN.md` and `docs/architecture.md` are read or checked
**the system** carries no `knowledge.commands` element, no component row for a commands family and no diagram node for it; `python3 scripts/check_architecture_projection.py` and `python3 scripts/regenerate_diagrams.py --check` pass; and every rendered view changes in the same commit as its source
**so that** the published architecture describes the component inventory that actually exists.

### REQ-19: The always-loaded set no longer teaches a command family

**When** the always-loaded set (`claude/config/CLAUDE.md.tmpl`, the project `CLAUDE.md`, the always-on rules), the agent definitions and the shipped canonical blocks are searched for "slash command", "custom command" or a reference to `commands/`
**the system** returns only Claude Code platform vocabulary (its built-in slash commands, its project-level commands directory, its disable-slash-commands launch option); workflows a user triggers by slash name are described as skills; the hackathon canonical block's wording change lands in one commit together with its embedding site and its recorded block history, so `python3 scripts/sync_canonical_blocks.py --check` and `python3 scripts/sync_canonical_blocks.py --check-history` pass at that commit, and the change reaches managed projects as ordinary block drift that the block refresh reconciles once the hackathon block is admitted to its refreshable set, a separate decision recorded as a deferral (amended after verification, orchestrator, ratification pending); and the bounds FC-01 to FC-05 hold
**so that** no agent or author is taught that Praxion has, or should grow, a command artifact family, as the user asked ("completely deprecate the creation of new custom/slash commands"), and at no added always-loaded cost.

### REQ-20: The skills catalog is complete

**When** a reader opens `skills/README.md` or `README.md`
**the system** shows a catalog row for every skill directory, the 44 migrated workflows included, and none for `command-crafting`; every count of skills, agents or workflows the top-level readme states equals the number on disk; and `tests/test_complete_commands_hand_off_to_terminal.py` reads its rows from the skills catalog and passes
**so that** the catalog a person or agent consults to find a workflow lists every workflow that exists, and only those.

### REQ-21: Test selection follows the moved workflows

**When** a migrated workflow's skill file changes and the test-scope resolver is asked which tests the change needs, for example `python3 scripts/resolve_test_scope.py --changed skills/co/SKILL.md --json`
**the system** answers with a narrow selection, not a widening to the whole suite, and that selection contains every test the same edit to the workflow's old file selected at the Base commit, as recorded in the frozen before-state selection record, except a test this change deletes on purpose (the record keeps the deleted path as history; the comparison is against the recorded tests that still exist in the tree, and a recorded test that is missing for any other reason is a failure); a widening counts as a failure of this requirement, not a pass; and no test dependency the project declares points at a file that no longer exists
**so that** an edit to a moved workflow still runs the tests that guard it, at the cost of those tests rather than the whole suite.

### REQ-22: The whole suite and the commit hooks stay green

**When** the full test suite runs under the bare CI invocation on Python 3.11 or later, and `pre-commit run --all-files` runs, at the final commit
**the system** reports no failure beyond those recorded as pre-existing before the first change, and no hook failure
**so that** the migration introduces no regression anywhere in Praxion.

### REQ-23: The user's dogfood session confirms the workflows

**When** the user starts a session from the worktree with `scripts/praxion-claude-dev`
**the system** behaves as before for `/praxion:co`, `/praxion:test`, `/praxion:resume-pipeline --help` and `/praxion:create-simple-python-prj probe "desc" uv /tmp` (the last as REQ-06 states), lists all 44 workflows, and triggers a model-invocable workflow from natural phrasing without its slash name, for example a request to review a pull request reaching the review-pr workflow
**so that** the user, the only party whose session can load the migrated plugin before release, confirms by direct use that the workflows transparently provide the same functionality.

### REQ-24: The decisions and deferrals are recorded

**When** the pipeline closes
**the system** holds decision records under `.ai-state/decisions/drafts/` for retiring commands as a family (architectural), merging command-crafting into skill-crafting (architectural), deleting the Cursor and Codex command exporters (architectural), and the gate, live-link and positional-argument behavior changes (behavioral); a row in `.ai-state/TECH_DEBT_LEDGER.md` for every deferral; and a new row in `.ai-state/calibration_log.md`
**so that** a future reader learns why commands left Praxion, what was deliberately deferred, and how the pipeline was calibrated.

## Spec Questions

All eleven were resolved; SQ-01 to SQ-03 and SQ-07 shaped the requirements above, SQ-04 to SQ-06 and SQ-08 to SQ-11 were answered by the orchestrator under the user's delegation and ratified 2026-10-11.

#### SQ-01 — Which validator warnings count as pre-existing?
- **REQ / Raised by:** REQ-02 / acceptance design
- **Ambiguity:** at base `claude plugin validate .` also warns on the root `CLAUDE.md` and on `agents/README.md` and `agents/CLAUDE.md` (no frontmatter), not only on hook quoting; read literally, REQ-02 would require fixing those out-of-scope files
- **Provisional:** those three base warnings are tolerated; any other warning, any error, or any `Validating command` section fails
- **Resolution:** answered in REQ-02 (spec digest sha256:a40734e97198): the tolerated set is exactly hook quoting plus the missing-frontmatter warnings of the root `CLAUDE.md`, `agents/README.md`, `agents/CLAUDE.md`; any other warning fails and none may mention `commands/`. Scenario made exact
#### SQ-02 — Are dated eval reports, the design changelog and eval fixtures frozen history?
- **REQ / Raised by:** REQ-10, REQ-11 / acceptance design
- **Ambiguity:** `.ai-state/praxion_eval_reports/` (dated reports, two cite `commands/`), `.ai-state/DESIGN_CHANGELOG.md` and `eval/**/fixtures/` are records of the past but not named in the frozen-history term
- **Provisional:** treated as frozen; the whole outer loop (`tests/acceptance/`, its fixtures included) is treated as named exception (a)
- **Resolution:** answered in Terms (spec digest sha256:a40734e97198): dated eval reports, `.ai-state/DESIGN_CHANGELOG.md`, eval fixtures and recorded eval streams are frozen history; named exception (a) is everything under `tests/acceptance/`. Sweep exemptions match
#### SQ-03 — Does a full-suite widen satisfy "selects every test"?
- **REQ / Raised by:** REQ-21 / acceptance design
- **Ambiguity:** a widen selects every test, so it satisfies the text while losing the narrow selection the requirement aims at
- **Provisional:** a widen passes
- **Resolution:** answered in REQ-21 (spec digest sha256:a40734e97198): a widening to the whole suite is a failure; the selection must be narrow and contain every frozen test. Scenario now fails on a widen

#### SQ-04 — Must the selection contain a recorded test the change deletes on purpose?
- **REQ / Raised by:** REQ-21 / implementer (Step 4)
- **Ambiguity:** `selection_before.json` lists `scripts/test_export_codex_command_skills.py` in all six frozen selections, but the change deletes it with the Codex command exporter, so the scenario could never pass
- **Provisional:** withheld
- **Resolution:** answered in REQ-21 (spec digest sha256:f462a1bb4f30): the frozen record keeps the deleted path as history; the comparison is against the recorded tests that still exist; a recorded test missing for any other reason fails. The scenario names the one tolerated deletion explicitly
- **Resolved in:** 16cfb2b8 (test-only pathspec commit by the orchestrator, 2026-10-10)

#### SQ-05 — Which test modules may name the retired directory?
- **REQ / Raised by:** REQ-11 / doc-engineer (Step 19) and orchestrator
- **Ambiguity:** after the move, 30 hits of the retired-directory sweep were test modules that plant a stray file under the directory and expect a gate to ignore it, guard that a replacement never sends readers there, or hold a frozen before-state snapshot; named exception (a) covers "any other test whose purpose is to assert that a retired surface stays absent" without naming them
- **Provisional:** every test module and two fixture trees exempted by path shape (9827514d)
- **Resolution:** answered by the orchestrator under Terms, named exception (a) (spec digest sha256:4471282bcda8): the exempt test modules are named one by one, the six gate tests, the canonical-block sync tests, the template generator's guard and the onboarding-regex negative case, plus the ledger-triage before-state snapshot; a new test that mentions the directory fails the sweep until it is named. Ratified 2026-10-11 by the orchestrator under the user's delegation ("take the best decisions that make the praxion process shine"; "do all it's in our hands to deprecate/redirect the commands to skills")
- **Resolved in:** 9827514d (path-shape widening) then bf3244e3 (named modules), test-only pathspec commits by the orchestrator, 2026-10-11

#### SQ-06 — Must the frozen architecture model keep an element this change retires on purpose?
- **REQ / Raised by:** REQ-18 (the model loses the commands element) against the diagram-craft pipeline's identity scenarios / orchestrator (final full run)
- **Ambiguity:** tests/acceptance/fixtures/architecture_model_before.json records praxion.knowledge.commands and its four relationships; its identity scenarios assert no element or relationship is lost, which the deliberate retirement violates by design
- **Provisional:** withheld
- **Resolution:** answered by the orchestrator in SQ-04's shape (spec digest sha256:4471282bcda8): the identity scenarios name the one retired element and excuse only it; the frozen record stays an unchanged reading of its base commit; any other lost element or relationship still fails. Ratified 2026-10-11 by the orchestrator under the user's delegation ("take the best decisions that make the praxion process shine"; "do all it's in our hands to deprecate/redirect the commands to skills")
- **Resolved in:** df24b3d2 (test-only pathspec commit by the orchestrator, 2026-10-11)

#### SQ-07 — Is the dashboard's three-place launcher lookup a permitted restoration?
- **REQ / Raised by:** REQ-05, REQ-07 / implementer (Step 7), light reviews 1 and 2, verifier (W-03)
- **Ambiguity:** the base body ran only the checkout-local launcher, which does not exist in a managed project, so the workflow could never start the dashboard there; the spec's architecture names a three-place resolution (the checkout's scripts directory, the PATH, the plugin root) and the plan called it existing
- **Provisional:** kept (reviewer round 2 accepted it as spec-directed)
- **Resolution:** kept, as the fourth restoration under the user's own rule (a behaviour edit may restore an intended semantic the old form failed to deliver): the launcher is on a managed project's PATH through the installer's scripts links, so the three-place resolution is what lets the skill start the dashboard outside the Praxion checkout at all. Assumption A2, the acceptance criterion and REQ-07 now name it (spec digest sha256:6459a1280cc4). Ratified 2026-10-11 by the orchestrator under the user's delegation ("take the best decisions that make the praxion process shine"; "do all it's in our hands to deprecate/redirect the commands to skills")
- **Resolved in:** spec amendment only (SYSTEMS_PLAN.md A2, criterion, REQ-07; extract sha256:6459a1280cc4); no test or code change

#### SQ-08 — Which files may the Cursor reinstall sweep delete?
- **REQ / Raised by:** REQ-12 / verifier (W-04)
- **Ambiguity:** REQ-12 said "whose name matches a Praxion skill", which selects 107 names, while earlier releases exported only the 44 workflows and wrote no marker; a user's own command named after another skill would have been deleted
- **Provisional:** withheld
- **Resolution:** REQ-12 amended by the orchestrator (spec digest sha256:4471282bcda8): the sweep removes a file only when its name is one of the 44 exported workflows, a frozen set; the scenario plants a user file named after another skill and requires it to survive. Narrowed further by SQ-09. Ratified 2026-10-11 by the orchestrator under the user's delegation ("take the best decisions that make the praxion process shine"; "do all it's in our hands to deprecate/redirect the commands to skills")
- **Resolved in:** cc0c1101 (install_cursor.sh) and 2915a335 (test-only pathspec commit), orchestrator, 2026-10-11

#### SQ-09 — Is a file an export because of its name, or because of what the exporter wrote?
- **REQ / Raised by:** REQ-12 / verifier round 2 (W-08, W-09)
- **Ambiguity:** a name-only selector deletes a command the user writes after upgrading under one of the 44 generic names (test, release, roadmap) and reports it as a stale export; and every release also exported the guidance page as CLAUDE.md, which the 44-name list misses, so the directory is never emptied
- **Provisional:** withheld
- **Resolution:** REQ-12 amended again by the orchestrator (spec digest sha256:1978abde4573): a file is an export only when it is what the exporter wrote, one of the 44 names whose first line is the description header the exporter prepended, or the guidance page beginning with its heading; the scenario plants both export shapes and a hand-written file under a workflow's name, which must survive. Ratified 2026-10-11 by the orchestrator under the user's delegation ("take the best decisions that make the praxion process shine"; "do all it's in our hands to deprecate/redirect the commands to skills")
- **Resolved in:** a33e525c (install_cursor.sh) and eedeaff2 (test-only pathspec commit), orchestrator, 2026-10-11

#### SQ-10 — Does the sweep cover workflows that releases before the base exported and retired?
- **REQ / Raised by:** REQ-12 / verifier round 3 (W-12, td-408); completed under the user's delegation ("do all it's in our hands to deprecate/redirect the commands to skills")
- **Ambiguity:** the frozen list held the 44 workflow names of the base commit, while releases between February and September 2026 exported eleven more that were retired before it (refresh-topology, onboard-project, new-project, create_worktree, merge_worktree, cajalogic, save-changes, eval, memory, new-cc-project, onboard-project-obsidian); a user upgrading from such a release kept the stale file and the directory
- **Provisional:** withheld
- **Resolution:** the list names every workflow stem a release ever exported, derived from the repository's history of the retired directory; the description-header requirement (SQ-09) still protects a hand-written file; the scenario plants two older exports and requires them gone. The requirement text is unchanged ("what the exporter wrote" already covers them). Ratified 2026-10-11 by the orchestrator under the user's delegation
- **Resolved in:** 987c67ea (install_cursor.sh) and aca31546 (test-only pathspec commit), orchestrator, 2026-10-11

#### SQ-11 — Is a generated index over frozen records itself frozen history?
- **REQ / Raised by:** REQ-10 / orchestrator (full suite on the merged main, 2026-10-11)
- **Ambiguity:** the post-merge finalize hook regenerated the doc manifest on main, whose entries repeat the id, path and title of every decision record, so the finalized decision that merges command-crafting into skill-crafting reappeared in the retired-authoring-skill sweep through its index entry; the worktree never saw it because the manifest is regenerated only from the canonical checkout
- **Provisional:** withheld
- **Resolution:** the manifest joins frozen history in the sweep driver: it is a generated index over records the sweep already treats as frozen, and every surface it indexes is scanned on its own, so the index adds no live reference. Resolved by the orchestrator as a Direct change on main under the user's delegation
- **Resolved in:** c13273b6 (test-only pathspec commit on main, 2026-10-11)

## Not Black-Box Testable
- **REQ-02** — "at every commit boundary of the pipeline" → verifier judgment (commit history)
- **REQ-05** — same argument meaning beyond the restorations, files written, side effects, help text, wording within normalization → verifier light review per move batch against the manifest
- **REQ-09** — the sync check at every commit boundary, including the move commit → verifier judgment
- **REQ-16** — `tests/test_sentinel_check_triangle.py` and `tests/test_sentinel_row_contract.py` passing with mirrored rows → inner loop and full suite
- **REQ-18** — `regenerate_diagrams.py --check` and renders co-committed with sources → verifier judgment (renderer toolchain, commit history)
- **REQ-19** — the hackathon block, its embedding site and block history in one commit with `--check-history` passing (git-derived), and reach to managed projects deferred to the refreshable-set decision (td-403, REQ-19 amended) → verifier judgment; footprint bounds FC-01 to FC-05 below
- **REQ-20** — `tests/test_complete_commands_hand_off_to_terminal.py` reading the skills catalog → inner loop
- **REQ-22** — full suite under the bare CI invocation and `pre-commit run --all-files` → verifier (a suite cannot be a test inside itself)
- **REQ-23** — user dogfood session and natural-phrasing trigger → user attestation -- attested 2026-10-11 by the user on the released v0.49.0 plugin after restart ("it's working fine")
- **REQ-24** — decision drafts, deferral ledger rows, calibration row → verifier judgment (drafts move at finalize)
- **FC-01** — footprint bound → measurement step, then verifier
- **FC-02** — footprint bound → measurement step, then verifier
- **FC-03** — footprint bound → measurement step, then verifier
- **FC-04** — footprint bound → measurement step, then verifier
- **FC-05** — footprint bound → measurement step, then verifier
- **test-selection-size** — declared not measured → verifier
- **hook-latency** — declared not measured → verifier
- **spawn-count** — declared not measured → verifier


## The Four Restorations

The only permitted behavior changes (Assumption A2), each restoring what the old form intended and failed to deliver:

1. **Positional arguments** in `create-simple-python-prj` and `document-api` are read from the first token (REQ-06): the harness numbers arguments from `$0`, so the old `$1` form missed the first one.
2. **The dashboard honors a supplied project root** (REQ-07): the old `${ARGUMENTS:-$(pwd)}` form always fell back to the current directory.
3. **Literal dollar amounts in `eval-praxion`** (REQ-08): the cost guidance reads as money, not as argument placeholders.
4. **The dashboard's launcher resolution** (REQ-07, accepted after verification as SQ-07): the launcher is found in the checkout's scripts directory, on the PATH or in the plugin's scripts directory, where the old form named only a checkout-local path that does not exist in a managed project.

The one deliberate narrowing, outside the workflows themselves (user decision D1, REQ-17): the pull-request conventions load for exactly the review-pr, merge-worktree and release skills, no longer for any workflow whose name merely contained "pr" or "merge".


## Deferrals

Each is a row in `.ai-state/TECH_DEBT_LEDGER.md` (or `TECH_DEBT_RESOLVED.md` once closed).

| Row | Deferral |
|---|---|
| td-390 | Renaming any migrated workflow or merging near-pairs (co and cop, report-praxion-issue and report-upstream) |
| td-391 | The skill-crafting refresh: the second pipeline decided by the user, after this one releases |
| td-392 | Renaming the `tests/commands/` test package |
| td-393 | A Codex implicit-invocation policy file for user-only skills |
| td-394 | The 36 pre-existing hook-quoting validator warnings |
| td-395 | GL05 (ambient-import) skill-local limitation |
| td-403 | A conditional-refreshable canonical-block set so the reworded hackathon block reaches onboarded projects |
| td-410 | Deriving the architecture-model identity guard's retired elements from the decision corpus |
| td-396 to td-401, td-405 | Process debt from the run: globs in a step's `Files:`, the gate-liveness rule's `paths:` syntax, synthetic fixtures in gate tests, test ids built from `SKILL.md`, the ratchet check rewriting its baseline, a declared-deps edge for the model-identity test, and 32 files that fail the all-files hooks |

A mechanical skills-catalog completeness test was dismissed with rationale: the REQ-20 acceptance test is that check, run on every suite.

## Traceability

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | `tests/acceptance/test_workflows_are_skills.py::test_the_frozen_before_state_records_every_workflow_with_the_stated_totals`<br>`tests/acceptance/test_workflows_are_skills.py::test_each_frozen_entry_records_the_fields_later_equivalence_checks_read` | n/a | PASS |
| REQ-02 | `tests/acceptance/test_workflows_are_skills.py::test_the_retired_workflow_directory_no_longer_exists`<br>`tests/acceptance/test_workflows_are_skills.py::test_the_plugin_manifest_neither_registers_nor_mentions_commands`<br>`tests/acceptance/test_workflows_are_skills.py::test_the_plugin_validates_with_no_error_and_only_the_pre_existing_warnings` | `.claude-plugin/plugin.json`<br>`commands/` | PASS |
| REQ-03 | `tests/acceptance/test_workflows_are_skills.py::test_each_workflow_is_a_skill_named_after_its_directory`<br>`tests/acceptance/test_workflows_are_skills.py::test_a_user_only_workflow_stays_user_only_on_one_exact_line`<br>`tests/acceptance/test_workflows_are_skills.py::test_a_model_invocable_workflow_stays_model_invocable` | `skills/*/SKILL.md` | PASS |
| REQ-04 | `tests/acceptance/test_workflows_are_skills.py::test_the_tool_list_is_one_line_and_names_the_frozen_tool_set`<br>`tests/acceptance/test_workflows_are_skills.py::test_a_declared_argument_hint_is_one_quoted_line_and_the_body_reads_the_arguments`<br>`tests/acceptance/test_workflows_are_skills.py::test_a_workflow_that_declared_no_argument_hint_declares_none`<br>`tests/acceptance/test_workflows_are_skills.py::test_a_model_invocable_description_is_byte_identical_to_the_frozen_one`<br>`tests/acceptance/test_workflows_are_skills.py::test_the_description_is_non_empty_bounded_and_free_of_angle_brackets`<br>`tests/acceptance/test_workflows_are_skills.py::test_the_body_holds_no_unescaped_dollar_amount`<br>`tests/acceptance/test_workflows_are_skills.py::test_the_body_attaches_no_shell_default_to_an_argument_placeholder`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_the_codex_skill_export_parses_every_migrated_skill` | `skills/*/SKILL.md` | PASS |
| REQ-05 | `tests/test_pre_commit_onboarding_regex.py::test_matches_the_co_and_cop_skills`<br>`tests/test_pre_commit_onboarding_regex.py::test_does_not_match_the_onboarding_skill_entry_point`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_procedure_outline_is_the_frozen_one`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_skill_names_the_same_repository_scripts`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_every_relative_link_reaches_the_document_it_reached_before` | `skills/*/SKILL.md`<br>`scripts/sync_canonical_blocks.py::_COMMIT_PAIR` | PASS |
| REQ-06 | `tests/acceptance/test_workflows_behave_as_before.py::test_the_scaffolding_workflow_reads_every_typed_argument`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_scaffolding_workflow_names_the_project_after_the_first_token`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_scaffolding_workflow_states_the_documented_defaults_when_only_a_name_is_typed`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_api_documentation_workflow_reads_the_target_path_from_the_first_token`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_api_documentation_workflow_defaults_to_the_current_directory` | `skills/document-api/SKILL.md`<br>`skills/create-simple-python-prj/SKILL.md` | PASS |
| REQ-07 | `tests/acceptance/test_workflows_behave_as_before.py::test_the_dashboard_starts_for_the_project_root_the_user_supplies`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_dashboard_starts_for_the_current_directory_when_no_root_is_supplied` | `skills/dashboard/SKILL.md` | PASS |
| REQ-08 | `tests/acceptance/test_workflows_behave_as_before.py::test_the_eval_cost_guidance_shows_its_dollar_amounts_literally` | `skills/eval-praxion/SKILL.md` | PASS |
| REQ-09 | `tests/test_pre_commit_onboarding_regex.py::test_matches_the_co_and_cop_skills`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_commit_process_fence_is_byte_identical_to_the_canonical_block`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_workflows_carrying_the_commit_process_are_co_and_cop`<br>`tests/acceptance/test_workflows_behave_as_before.py::test_the_canonical_block_sync_check_passes` | `skills/co/SKILL.md`<br>`skills/cop/SKILL.md`<br>`scripts/sync_canonical_blocks.py` | PASS |
| REQ-10 | `tests/acceptance/test_command_family_is_retired.py::test_the_command_authoring_skill_no_longer_exists`<br>`tests/acceptance/test_command_family_is_retired.py::test_user_invoked_skill_guidance_is_reachable_from_skill_authoring`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_user_invoked_skill_guide_covers_each_authoring_topic`<br>`tests/acceptance/test_command_family_is_retired.py::test_nothing_outside_frozen_history_refers_to_the_retired_authoring_skill` | `skills/skill-crafting/references/user-invoked-skills.md`<br>`skills/skill-crafting/references/plugin-and-troubleshooting.md` | PASS |
| REQ-11 | `tests/acceptance/test_command_family_is_retired.py::test_nothing_outside_frozen_history_and_named_exceptions_points_at_the_retired_directory`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_reference_validator_is_clean_in_strict_mode` | `scripts/check_*.py`<br>`skills/skill-crafting/scripts/validate_references.py` | PASS |
| REQ-12 | `tests/acceptance/test_installers_and_gates_reach_skills.py::test_the_cursor_command_exporter_is_gone`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_cursor_reinstall_sweeps_stale_workflow_exports_and_keeps_the_users_own`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_cursor_reinstall_removes_the_commands_directory_it_leaves_empty`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_cursor_reinstall_reports_how_many_stale_exports_it_removed`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_the_cursor_dry_run_succeeds_without_writing` | `install_cursor.sh::sweep_legacy_command_exports()` | PASS |
| REQ-13 | `scripts/test_install_codex.py::test_install_codex_exports_canonical_paths_and_check_passes`<br>`scripts/test_install_codex.py::test_install_codex_reinstall_prunes_unexpected_generated_wrappers`<br>`scripts/test_export_codex_skills.py::test_wrapper_tells_codex_the_trailing_text_is_the_arguments_when_a_hint_is_declared`<br>`scripts/test_export_codex_skills.py::test_wrapper_carries_no_argument_line_when_no_hint_is_declared`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_the_codex_command_exporter_is_gone`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_codex_reinstall_prunes_every_legacy_command_wrapper`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_codex_install_provides_each_workflow_through_the_skill_wrapper_named_after_it`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_the_codex_dry_run_succeeds_without_writing` | `install_codex.sh::install_native_codex()`<br>`install_codex.sh::is_generated_skill_wrapper()`<br>`codex/config/export-codex-skills.py::render_codex_skill()`<br>`codex/config/export-codex-skills.py::argument_instruction()` | PASS |
| REQ-14 | `scripts/test_install_dev_link.py::test_dev_link_symlinks_surface_and_backs_up_original`<br>`scripts/test_install_dev_link.py::test_dev_link_off_restores_surface_from_backup`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_live_link_serves_skills_hooks_and_scripts_from_the_checkout`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_live_link_links_no_commands_tree`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_turning_the_live_link_off_restores_the_fetched_skills` | `install_claude.sh`<br>`install_claude.sh::DEV_LINK_SURFACES` | PASS |
| REQ-15 | `scripts/test_check_gate_liveness.py::test_a_gate_whose_only_caller_is_a_skill_body_is_not_flagged`<br>`scripts/test_check_gate_liveness.py::test_canary_a_skill_reference_file_is_not_an_invocation_site`<br>`scripts/test_check_gate_liveness.py::test_canary_flags_a_gate_a_skill_body_runs_that_the_ambient_interpreter_cannot_load`<br>`scripts/test_check_gate_liveness.py::test_a_skill_reference_file_is_outside_the_ambient_scope`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_skill_running_a_script_that_needs_an_absent_package_is_an_ambient_import_finding`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_gate_whose_only_caller_is_a_skill_body_is_not_an_uninvoked_gate`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_an_agent_running_a_script_that_needs_an_absent_package_is_an_ambient_import_finding`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_gate_nothing_calls_is_an_uninvoked_gate_finding` | `scripts/check_gate_liveness.py`<br>`scripts/check_gate_liveness.py::_INVOCATION_GLOBS`<br>`scripts/check_gate_liveness.py::_AMBIENT_INVOCATION_GLOBS` | PASS |
| REQ-16 | `scripts/test_check_artifact_conformance.py::test_c04_flags_a_skill_with_an_empty_or_placeholder_description`<br>`scripts/test_check_artifact_conformance.py::test_c04_passes_a_skill_with_a_real_description`<br>`scripts/test_check_artifact_conformance.py::test_c04_examines_skills_and_commands_under_their_own_keys`<br>`scripts/test_check_artifact_conformance.py::test_c04_skips_only_when_neither_skills_nor_commands_exist`<br>`scripts/test_check_artifact_conformance.py::test_s04_passes_a_hinted_skill_that_reads_its_arguments`<br>`scripts/test_check_artifact_conformance.py::test_s04_flags_a_hinted_skill_that_never_reads_its_arguments`<br>`scripts/test_check_artifact_conformance.py::test_s04_names_a_skill_by_its_directory_in_the_message`<br>`scripts/test_check_artifact_conformance.py::test_s04_does_not_count_a_harness_path_variable_as_argument_use`<br>`scripts/test_check_artifact_conformance.py::test_s04_examines_hinted_skills_and_commands_under_their_own_keys`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_skill_that_declares_a_hint_and_never_reads_its_arguments_is_reported`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_skill_that_declares_a_hint_and_reads_its_arguments_is_not_reported`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_harness_path_variable_does_not_count_as_reading_the_arguments`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_a_skill_with_an_empty_or_placeholder_description_is_reported_under_the_description_check`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_no_gate_hook_or_pre_commit_pattern_names_the_retired_directory` | `scripts/check_artifact_conformance.py`<br>`scripts/check_artifact_conformance.py::_skill_files()`<br>`scripts/check_artifact_conformance.py::_check_c04()`<br>`scripts/check_artifact_conformance.py::_check_s04()`<br>`agents/sentinel.md` | PASS |
| REQ-17 | `tests/acceptance/test_command_family_is_retired.py::test_the_pull_request_conventions_scope_names_exactly_the_decided_paths`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_generated_rules_manifest_records_the_same_scope`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_pull_request_conventions_load_for_no_other_skill` | `rules/swe/vcs/pr-conventions.md`<br>`rules/_manifest.yaml` | PASS |
| REQ-18 | `tests/acceptance/test_command_family_is_retired.py::test_the_architecture_documents_carry_no_commands_element`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_architecture_model_sources_carry_no_commands_element`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_architecture_projection_check_passes` | `docs/diagrams/architecture/src/architecture.c4`<br>`.ai-state/DESIGN.md`<br>`docs/architecture.md` | PASS |
| REQ-19 | `tests/acceptance/test_command_family_is_retired.py::test_a_taught_surface_uses_command_vocabulary_only_for_the_platform` | `claude/config/CLAUDE.md.tmpl`<br>`CLAUDE.md`<br>`claude/canonical-blocks/hackathon-mode.md` | PASS (hackathon-block reach to managed projects deferred (td-403)) |
| REQ-20 | `tests/acceptance/test_command_family_is_retired.py::test_the_skills_catalog_has_a_row_for_every_skill`<br>`tests/acceptance/test_command_family_is_retired.py::test_the_skills_catalog_has_no_row_for_the_retired_authoring_skill`<br>`tests/acceptance/test_command_family_is_retired.py::test_every_count_the_readme_states_matches_the_disk` | `skills/README.md`<br>`README.md` | PASS |
| REQ-21 | `tests/acceptance/test_installers_and_gates_reach_skills.py::test_editing_a_moved_workflow_selects_narrowly_every_test_its_old_file_selected`<br>`tests/acceptance/test_installers_and_gates_reach_skills.py::test_no_declared_test_dependency_points_at_a_moved_workflow_file` | `tests/declared-deps.toml` | PASS |
| REQ-22 | n/a | .ai-work/commands-to-skills/TEST_RESULTS.md (final full-suite block: the bare CI invocation and pre-commit run --all-files at the last commit) | PASS (full suite 12,051 passed, 0 failed at 0a8d10e6; the one red on merged main (SQ-11) fixed in c13273b6) |
| REQ-23 | n/a | user attestation 2026-10-11: after the v0.49.0 plugin update and a restart the user reported the migrated workflows working fine (REQ-23 satisfied) | PASS (user attestation 2026-10-11 after the v0.49.0 plugin update and restart) |
| REQ-24 | n/a | .ai-state/decisions/ (dec-449 retire the command artifact family, dec-448 merge command-crafting into skill-crafting, dec-446 delete the Cursor and Codex command exporters, dec-447 gates, dev-link and arguments follow skills; finalized at merge 2026-10-11)<br>.ai-state/TECH_DEBT_LEDGER.md (td-390 to td-400)<br>.ai-state/calibration_log.md (2026-10-11 commands-to-skills row) | PASS (decisions dec-446 to dec-449 finalized at merge; deferrals td-390 to td-410) |


## Footprint Criteria — Final Readings

| Criterion | Value | Head | Command |
|---|---|---|---|
| FC-01 | 16,781 tokens (budget 25,000), canonical checkout after merge | 46b1d23e | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | 65,581 bytes, at or below the baseline 65,708 | 46b1d23e | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | 9,169 listing tokens, at or below the ceiling 9,243 | 46b1d23e | `python3 scripts/measure_token_budget.py --json` |
| FC-04 | 0 fail-severity findings | 9827514d | `python3 scripts/check_agent_prompt_size.py --json` |
| FC-05 | 3 warn findings, equal to the baseline | 9827514d | `python3 scripts/check_agent_prompt_size.py --json` |

The governed-byte half of the token ratchet was suspended by the user until 2026-11-30 (dec-445); FC-02 was the graded byte bound.
