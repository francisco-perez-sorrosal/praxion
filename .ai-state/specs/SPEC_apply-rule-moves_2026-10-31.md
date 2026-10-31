# Spec: apply-rule-moves (the ADR rule loads by path scope beside a one-line resident, and a deterministic gate refuses the decision records the late-arriving rule let through)

**Task slug**: `apply-rule-moves`
**Feature**: Applies the `adr-conventions` move that paired run `20261030T153351Z-632ecb` measured (instrument and baseline: archived specs `SPEC_main-session-adherence_2026-10-28.md` and `SPEC_adr-move-readiness_2026-10-29.md`). `rules/swe/adr-conventions.md` becomes the measured lean arm's rule byte for byte, path-scoped to `.ai-state/decisions/**`; a new resident file, `rules/swe/adr-conventions-resident.md` (declaring `resident_of`), keeps the title and one sentence always loaded; the kernel tooling, the Cursor exporter and the Codex bridge learn the resident; and a deterministic decision-record gate (write, edit and read hooks behind a shell fast path, the commit gate, Praxion's pre-commit hook) refuses the misplaced, self-numbered, malformed or uncategorised records the late-arriving rule let through, plus a whole read of `DECISIONS_INDEX.md`. The instrument also refuses to build the move's lean arm against the landed tree. The git-conventions half of the intake was dropped (`td-526`). FC-01 fell from 23,652 to 20,273 tokens.
**Tier**: Full (from intake: 22 requirements over 80 files across rules, the install manifest, kernel tooling, two exporters, a three-adapter gate, the move instrument and documentation). Budget 32 spawns, charged 12 by the calibration row; 38 of 38 step-loop iterations spent; the verifier's retrospective reads `correct` with no mid-task re-tier.
**Pipeline branch**: `apply-rule-moves` (from `main` at `3a85719e`, pushed)
**Start date**: 2026-10-30
**End date**: 2026-10-31
**Archived**: 2026-10-31 (pre-merge, on branch apply-rule-moves; to be merged to main with --no-ff)
**Status**: completed -- delta verdict PASS WITH FINDINGS at `9115beb2`, after a first pass at `a61bb800` that read FAIL (two record-only FAILs on the acceptance-independence records, F-1 and F-2, and ten WARNs, the consequential two being a false refusal of a stale-local-main merge and a duplicate `category:` key that landed); one in-place rework closed every finding but a partly closed W-2, and the delta's four residuals (D-1 to D-4) were then closed in `dcd4bfee` and `a9f5ab73` with canaries that bite, which no verifier has re-read; no paid session ran
**ADRs**: `dec-480` (category: architectural -- the ADR rule is path-scoped with a declared resident projection: a `resident_of` file joins the rules layer, read by the kernel tooling and checked by the two exporters) and `dec-481` (category: architectural -- the decision-record gate is a new component: a pure core, a refusal renderer, three adapters and two registrations). Finalize rewrites both ids to `dec-NNN` at merge to main.
**Evidence base**: the two ADR drafts above; the spec digest `sha256:2cfd9a42f109` of `SPEC_EXTRACT.md` (the design phase read `335b8eda8f50`; the outer-loop amendment SQ-05 accounts for the change); the branch's commits from base `3a85719e` (intake log `0cb27592`, acceptance design `60ae3ce2`, ADR drafts `3074eaa4`, first production commit `bd039c2f`, first verified head `a61bb800`, delta-verified head `9115beb2`, final head `a9f5ab73`); the suites named in the matrix below (outer-loop scenarios in `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py`, `test_adr_rule_move_keeps_every_other_reach.py`, `test_decision_record_gate.py`, the amended `test_resident_text_is_moved_not_cut.py`, designed from the extract alone; gate, kernel, exporter and parity unit tests beside the code); the paired-run results `.ai-state/eval_ledger/adherence/moves/20261030T153351Z-632ecb.json` (the arm measured) and `20261031T054616Z-f494d2.json` (the git half, not covered); the completion row in `.ai-state/calibration_log.md` dated 2026-10-31; ledger rows `td-526` to `td-528` (and `td-501`, carried); the verifier's `VERIFICATION_REPORT.md` (first pass and delta), `CHECKPOINT_DIGEST.md`, `MEASUREMENTS.md`, `REWORK_MANIFEST.md` and `LEARNINGS.md` (under `.ai-work/`, deleted at cleanup, their substance carried below).

## Feature Summary

The `adr-conventions` move measured in paired run `20261030T153351Z-632ecb` is applied: the rule now loads by path scope on `.ai-state/decisions/**` beside a one-line resident, and a deterministic gate refuses the decision records the late-arriving rule let through.

That run (24 pairs, 48 opus sessions) covered both governed checks within the 10-point margin, but the lean arm's path-scoped rule arrived after the session's first creating write in 4 of 24 sessions, and one of them failed placement and category unrepaired. The rule cannot arrive before the write that triggers it, so shipping the arm alone would trade 3,379 always-loaded tokens for records a late rule cannot stop. The pipeline therefore ships the measured arm and adds the gate that refuses, at the creating write, what the late rule cannot prevent. The git-conventions half of the intake was dropped: its paired run `20261031T054616Z-f494d2` (48 opus sessions, $20.20) could not be covered on commit message form, because the full arm itself broke the 50-character subject limit in 15 of 24 sessions (lean 11 of 24, floor 8 of 8), so no channel move can be bounded on that check until a deterministic gate or a reliably moved check part is chosen (`td-526`).

The rule pair. The moved rule is the kit's lean-arm file byte for byte: its body is the base's body, and its frontmatter differs from the base's only by the path scope `.ai-state/decisions/**`, the path-scoped load value and a Codex always-on override. A session therefore receives the whole rule on its first read, write or edit of a decision file. The resident file is the arm's 187-byte body under 94 bytes of frontmatter (`core: true`, `load: always_on`, `install: symlink`, `resident_of: rules/swe/adr-conventions.md`). `resident_of` is a new key naming the rule a file projects: the kernel tooling reads it so every resident line must be a line of the parent and the parent stays in the total source set (no audience entry, no role kernel changes); the Cursor exporter and the Codex bridge each check the key themselves, held equal to the shared reader by parity tests, so both assistants keep today's reach (Codex keeps the full rule always-on, Cursor exports it as before).

The gate. One stdlib-only, Python 3.9-safe rules module in three files: a pure core (`scripts/_decision_records.py`) that judges parsed values, a refusal renderer (`scripts/_decision_record_refusal.py`) that quotes the rule's own governing lines read from the rule file (about 700 characters at most; a fixed message when the rule cannot be read, so the verdict never depends on reading it), and the command with its git edge (`scripts/check_decision_records.py`). Thin adapters reach it: a shell fast path (`hooks/decisions_gate.sh`) so a write or read of any other path starts no interpreter, `hooks/guard_decision_records.py` for Write, Edit and Read (PreToolUse deny, fail-open on its own errors), the commit gate (`commit_gate.sh --blocking`) for `git commit` in managed projects with no onboarding step, and a `decision-records` pre-commit hook for Praxion itself. It refuses a new record that is misplaced, self-numbered, a draft with a malformed name or id, or without a valid `category`; an edit that removes or invalidates a valid `category`; a commit off `main`/`master` carrying such a record; and a whole read of `DECISIONS_INDEX.md`, the one Discovery Protocol instruction that otherwise arrives with the read it forbids. Existing debt never blocks: an edit of an existing record is judged only for a lost `category`, and a numbered record the default branch already holds passes.

Shape of the delivery: 20 plan steps (17 implementer, 1 doc-engineer, 2 orchestrator measurements); steps 2 to 16 and 19 ran through the step loop (38 of 38 iterations; step 19's whole-suite `Check:` can never verify inside the driver's fixed 540 s bound, `td-527`), steps 1, 18 and 20 were run by the orchestrator and step 17 by the doc-engineer; four forced light reviews (steps 3, 7, 10, 11; three took one revision); one in-place rework after the first verification.

The verifier's most consequential finding. The first pass read FAIL on record-only grounds: four post-design outer-loop amendments (and a changed extract digest) were in the checkpoint digest but not answered Spec Questions in `ACCEPTANCE_TESTS.md`. Its two gate-correctness WARNs were probe-proven: a legitimate merge of `origin/main` while local `main` lagged was refused at commit, and a duplicate `category:` key let an invalid value land because the gate read the first key where the index generator and PyYAML read the last. The rework closed both, and the delta then found two residuals in its own fixes: the remote-branch pattern let `.+` span slashes (so `origin/feature/main` counted as a default branch) and the key pattern did not tolerate whitespace before the colon.

## What Was Built

| Part | Files | Notes |
|---|---|---|
| Moved rule | `rules/swe/adr-conventions.md` | equal to the kit file `eval/src/praxion_evals/adherence/moves/kits/adr-conventions/rules__swe__adr-conventions.md` (sha256 `b0c7c366`, the results file's lean identity); `paths: .ai-state/decisions/**`, `load: path_scoped`, `codex: always_on` |
| Resident | `rules/swe/adr-conventions-resident.md` | body sha256 `540fef63` (the arm's 187 bytes); 94 bytes of frontmatter, no `codex` key (dropped in rework: no path read it) |
| Manifest | `rules/_manifest.yaml`, `scripts/regenerate_rules_manifest.py` | generated, never hand-edited; the resident id joins `EXPECTED_CORE_IDS`; both rows equal the measured rows on id, path, load, core, install and paths (`chars` and the generation stamp differ) |
| Kernel tooling | `scripts/_resident_of.py`, `scripts/kernel_sources.py`, `scripts/check_kernel_manifest.py`, `rules/_audience.yaml` (header comment) | a resident line that is no line of its parent is reported by text; the parent stays total; no kernel regenerates |
| Exporters | `cursor/config/export-cursor-rules.py`, `codex/config/rules_bridge_parsing.py` | each skips a `resident_of` file by its own check; parity tests hold both equal to the shared reader |
| Commit scope | `scripts/_commit_scope.py` | the same-call staging helpers extracted unchanged from `scripts/check_id_citation_discipline.py` before the second consumer |
| Gate | `scripts/_decision_records.py`, `scripts/_decision_record_refusal.py`, `scripts/check_decision_records.py` | pure core, refusal text, command line (exit 0 clean, 1 findings, 2 input error; `--staged`, `--json`, commit payload mode) |
| Adapters and registration | `hooks/decisions_gate.sh`, `hooks/guard_decision_records.py`, `hooks/hooks.json`, `.pre-commit-config.yaml` | three PreToolUse entries (Write and Edit, Read, and Bash through the commit gate) and one pre-commit hook |
| Instrument | `eval/src/praxion_evals/adherence/moves/arms.py`, `eval/tests/landed_move_support.py`, `eval/tests/test_decision_gate_parity.py` | the lean arm of a landed move is refused naming what the tree already holds; a parity test holds the gate and the eval grader to shared record fixtures |
| Reader texts | `CLAUDE.md`, `AGENTS.md`, `AGENTS.md.tmpl`, `rules/README.md`, `rules/CLAUDE.md`, `docs/rules-taxonomy.md`, `claude/config/praxion-rules.yaml.example`, `README_DEV.md`, `skills/rule-crafting/SKILL.md` | no text says the rule loads in full at session start; each names the path scope and the resident; Codex-facing text says Codex keeps it always-on |
| Design and catalogs | `.ai-state/DESIGN.md` (§3b gate row), `docs/architecture.md`, `docs/lean-spawn-how-to.md`, `scripts/CLAUDE.md`, `skills/context-security-review/references/hook-safety-contract.md`, `eval/EVAL_PLAN.md` | the plan's turn-capped DESIGN row was applied by a plan step |

Shipped versus measured. The rule and the resident body are byte-identical to the arm. The resident's 94 bytes of frontmatter are not in the measured arm (the measured resident had none; the harness is assumed to treat frontmatter as constant across arms, since every always-on rule in both arms carried it). The gate, the kernel tooling, the exporters and the documents are in neither arm. The paired verdicts on delivery therefore stand for the two measured channels, and the gate's own effect rests on canaries and a production-shape replay, not on a run. A paired run of the shipped tree would measure a different arm (lean plus gate); the move model already names that channel (`gate_refusal`), so it is declarable.

What the gate refuses and does not. Refused: a new `.md` under `.ai-state/decisions/` that is not directly in `drafts/` (other than `DECISIONS_INDEX.md` and a `CLAUDE.md` or `README.md` guide); a draft whose name is not a fragment finalize would promote or whose id is not `dec-draft-` plus eight lowercase hex characters; a new record without one of the four `category` values; an edit that loses a valid `category`; at commit time off `main`/`master`, a numbered record the default branch does not hold; a Read of the index with no line limit. Allowed with no message: a conforming draft, an edit of an existing numbered record that keeps its category, the index, directory guides, anything outside the tree. The refusal names the defect and the correct form and quotes the rule's lines for the defect family.

## Deferred at Close

- **`td-526`: the git-conventions half.** Its paired run did not cover commit message form (the full arm broke the 50-character subject 15 of 24), so the git move is not applied. Options recorded on the row: a deterministic commit-msg gate on subject length and trailing period beside the authorship gate (after which the check measures the gate, not the rule), or a check part the rule moves reliably; a new frozen tree is needed to re-measure.
- **Post-merge and release.** A real-HOME FC-01 reading after the merge (the dev-install links point at main's rules until then, so the pipeline read FC-01 under a scratch home). The gate reaches marketplace installs only after a release. `bash install.sh` was never run against the real home; every installer test uses a scratch home.
- **The shipped arm is unmeasured.** Lean plus gate, and the resident's 94 bytes of frontmatter, were never run in a paired session; no paid session ran in this pipeline. The instrument now refuses the ADR move as declared, so a future measurement needs a new declared arm. Two footprints are declared not measured: hook latency (no instrument; the acceptance tests bound the work a check does for a path outside the tree and for a command that is not a commit) and spawn-startup tokens (its only instrument starts billed sessions).
- **Declared limits of the gate.** Commits made outside a session in a managed project (the miss was measured in sessions; reaching outside them changes the onboarding contract). Hosts without plugin hooks (Codex, Cursor) keep today's text and no gate. Windows ignores user-scope `paths:`, so a Windows session gets the resident and the gate but not the path rule. `MultiEdit` is not matched (the memory-index gate's precedent). Commit spellings `bash -c`, a pipe, `&`, `$(...)`, `xargs`, a quoted env prefix and `git -C dir commit` are not seen by the session commit gate (`td-528`; Praxion's pre-commit still sees the true staged set). An unstaged tracked edit that `git add -u` would stage is not judged at all. A repository whose default branch is not named `main` or `master` is refused on every branch; any one remote's own `main`/`master` counts as the default. An architectural record with no Disconfirmation section is not refused (no session failed it). A record written outside `.ai-state/decisions/` is not judged. A top-level import failure of the gate modules exits 1, which PreToolUse reads as non-blocking. Sidecar writes addressed through the state mount's real path rather than the `.ai-state` shadow link are not matched.
- **Open ledger rows, none blocking the merge.** `td-526` (above); `td-527` (the step-loop driver bounds a step's `Check:` by a fixed 540 s, ignoring the pocket bounds it applies to gate runs; the root suite now takes 646 to 672 s, so an integration step whose Check is the whole suite can never verify); `td-528` (the commit-spelling blind spot above, shared with the id-citation gate's separator; filed by the verifier, its row uncommitted in the worktree at archival and committed by the orchestrator with the pipeline state); `td-501` (unquoted `${CLAUDE_PLUGIN_ROOT}` in `hooks/hooks.json`; the three new entries follow the current convention). `td-518`, the previous spec's deferred probe row, was resolved on main before this pipeline (`06c6e22b`).
- **Accepted with reason by the verifier, no action.** `README.md` guides are non-records beyond the requirement's wording (aligned below); two review notes (a loop in a test over a fixed shape table; the widened write filter starting Python for payloads that merely mention the tree, latency only); `skills/rule-crafting/SKILL.md` at 418 lines (warn ceiling 400, under the fail ceiling); `dec-draft-*` ids in `DESIGN.md` and `docs/architecture.md` (the finalize citation net covers both); the 94-byte unmeasured frontmatter (the ADR's reversal trigger covers it); FC-01 headroom of 27 tokens (this pipeline's criterion, not a standing ratchet; the standing budget has 4,716 headroom).

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (digest `sha256:2cfd9a42f109`). REQ ids are pipeline-local and appear nowhere in code, tests or docstrings. The git-conventions half is out of scope (`td-526`).

Directory guides, aligned at archive on the verifier's ruling. REQ-11, REQ-12 and REQ-14 name `CLAUDE.md` as the directory guide that is no decision record. The shipped gate also treats a `README.md` guide as a non-record (the design's Data Structures section and spec-phase decision (c) list it; the verifier accepted the exemption). Read each of the three requirements with "or a `README.md` directory guide" after "a `CLAUDE.md` directory guide"; the verbatim text below is otherwise unchanged.

Complexity: Full tier (rules, manifest, kernel tooling, two exporters, a new gate, docs). Brownfield: no prior archived spec covers this rule's delivery; prior decisions constrain it (core frontmatter is the single source of non-disableability; a write-time gate already guards memory indexes; role kernels are generated from one audience manifest; finalize assigns numbers at merge).

### Observable Surface

Names a test designer may use. Everything else in the requirements is plain words.

- `rules/swe/adr-conventions.md`: the moved rule (its body and frontmatter are the measured contract)
- `rules/swe/adr-conventions-resident.md`: the resident file the measured arm declares
- `rules/_manifest.yaml`: the generated install manifest
- `rules/_audience.yaml`: the audience manifest the kernels are cut by
- `.ai-state/decisions/**`: the moved rule's path scope
- `.ai-state/decisions/`: the decision records directory
- `.ai-state/decisions/drafts/`: the drafts directory
- `<NNN>-<slug>.md`: a numbered record's file name
- `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`: the fragment file name schema
- `dec-draft-<hash>`: a draft id (the hash is 8 lowercase hex characters)
- `dec-NNN`: a numbered id
- `category`: the record frontmatter field; its values `architectural`, `behavioral`, `implementation`, `configuration`
- `DECISIONS_INDEX.md`, `CLAUDE.md`: non-record files that may live in the decisions tree
- `.ai-state/decisions/DECISIONS_INDEX.md`: the decisions index
- `## ADR Conventions`: the rule's title line, the first line of the resident text
- `fragment`, `drafts`, `what exists or what connects`, `however consequential`: the governed phrases of the paired run's two checks
- `swe/adr-conventions`, `swe/adr-conventions-resident`: the two rule ids
- `~/.claude/rules/`: where the installer links rules
- `.claude/praxion-rules.yaml`: a project's rule disable list
- `.cursor/rules/`: the Cursor export directory
- `main`, `master`: the branches finalize treats as main
- `git commit`: the commit command a session runs
- `bash install.sh`: the installer
- `python3 scripts/regenerate_rules_manifest.py --check`, `python3 scripts/generate_kernels.py --check`, `python3 scripts/check_kernel_manifest.py`, `python3 scripts/sync_canonical_blocks.py --check`: the drift checks
- `scripts/measure_token_budget.py`, `python3 scripts/measure_token_budget.py --json`, `env <home-assignment> python3 scripts/measure_token_budget.py --json`, `python3 scripts/check_agent_prompt_size.py --json`: the footprint instruments
- `python3 -m pytest tests/ -q`, `cd eval && uv run pytest -q`: the root and eval suites

### REQ-01: The resident line is all of the rule at session start

When a Claude Code session starts in Praxion or in a managed project with the plugin's rules installed, and no file under `.ai-state/decisions/**` has been read, written or edited,
the system holds in the session's always-loaded context the resident text of `rules/swe/adr-conventions-resident.md` (the `## ADR Conventions` title and its one sentence) verbatim, and no other line of the body of `rules/swe/adr-conventions.md`,
so that the session-start surface that ships is the one the paired run measured.

### REQ-02: The full rule arrives with the first touch of a decision record

When a session reads, writes or edits any file under `.ai-state/decisions/**`,
the system delivers the full text of `rules/swe/adr-conventions.md` to that session,
so that the rule reaches its trigger by the path channel the move measured.

### REQ-03: No line of the moved rule is cut

When the shipped `rules/swe/adr-conventions.md` is compared with the measured lean arm's rule and with the rule at the pipeline base,
the system shows it byte-identical to the lean arm's rule, with a body byte-identical to the base's and a frontmatter that differs from the base's only by the path scope `.ai-state/decisions/**`, the path-scoped load value and the Codex always-on override,
so that every line of the rule is delivered by a declared channel and nothing is cut.

### REQ-04: The resident file and the manifest rows equal the measured arm, or each difference is named

When the shipped `rules/swe/adr-conventions-resident.md` and the generated `rules/_manifest.yaml` are compared with the measured arm's resident file and manifest,
the system shows the resident body byte-identical to the arm's, a frontmatter block as the resident's only difference, each of its keys named in this plan with its reason, and manifest rows for `swe/adr-conventions` and `swe/adr-conventions-resident` whose id, path, load, core, install and paths values equal the arm's rows (a row's character count and the manifest's generation stamp being the only other differences),
so that what ships is what was measured, and every departure is visible.

### REQ-05: Both files install, and both stay non-disableable

When the installer runs against the shipped tree, and a project's `.claude/praxion-rules.yaml` disable list names `swe/adr-conventions` or `swe/adr-conventions-resident` or matches either by glob,
the system links both files into `~/.claude/rules/`, keeps both loaded by their channels, and prints at session start the existing warning that a core rule cannot be disabled,
so that the move keeps the ADR rule non-disableable as it was.

### REQ-06: No role kernel changes

When the kernel generator and the kernel check run on the shipped tree,
the system reports clean, and the generated role kernels and their index are byte-identical to the pipeline base's,
so that no role's kernel gains a duplicate of the resident line and none loses its ADR text.

### REQ-07: The moved rule keeps its kernel guarantees

When a section is added to `rules/swe/adr-conventions.md` with no entry in `rules/_audience.yaml`, or when a line of `rules/swe/adr-conventions-resident.md` is not a line of the moved rule,
the system's kernel check reports that section as unclassified, or that line as text with no classification, and exits non-zero,
so that leaving the always-loaded set does not loosen the totality the rule had while it was always-loaded.

### REQ-08: The manifest is generated from the shipped files

When the manifest drift check runs on the shipped tree,
the system reports no drift, the manifest being what the generator emits from the shipped files and never a hand-edited copy,
so that the measured rows survive every later regeneration.

### REQ-09: Codex keeps today's reach

When the Codex rules bridge is exported from the shipped tree,
the system exports the same always-on rule set, with the same session-start pointer text, as an export from the pipeline base, keeps the full ADR rule always-on there, and exports no rule for the resident file,
so that an assistant with no path delivery for this rule keeps today's text and gains no duplicate.

### REQ-10: Cursor keeps today's reach

When the Cursor rules export runs from the shipped tree,
the system writes a `.cursor/rules/` directory byte-identical to the export from the pipeline base,
so that Cursor, which ignores path scopes, keeps the full rule as today and gains no resident-only rule.

### REQ-11: A misplaced or self-numbered record cannot be written

When a session's Write would create a new Markdown file under `.ai-state/decisions/` that is not directly inside `.ai-state/decisions/drafts/` (a `<NNN>-<slug>.md` record, a fragment-named file outside the drafts directory, a file in any other subdirectory, or any other name), and the file is neither `DECISIONS_INDEX.md` nor a `CLAUDE.md` directory guide,
the system refuses the write so the file is not created, and the refusal names the defect and the correct form (a fragment directly under `.ai-state/decisions/drafts/`, named by `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`, with a `dec-draft-<hash>` id, numbered only by finalize at merge to `main`),
so that the record a late-arriving rule let through in the paired run cannot land.

### REQ-12: A malformed draft cannot be written

When a session's Write would create a file in `.ai-state/decisions/drafts/` whose name does not follow `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` (a real date and time, then only lowercase letters, digits and hyphens, the shape finalize promotes), or whose frontmatter id is not a `dec-draft-<hash>` (including a self-picked `dec-NNN`), and the file is not a `CLAUDE.md` directory guide,
the system refuses the write and names the defect and the correct form,
so that no draft is written that finalize would strand or refuse at merge.

### REQ-13: A record cannot be left without a valid category

When a session's Write would create a decision record, draft or numbered, whose frontmatter has no `category` or a value other than `architectural`, `behavioral`, `implementation` or `configuration`, or a session's Write or Edit would remove or invalidate the `category` of an existing record that held a valid one,
the system refuses the write and names the four values and the rule's test for `architectural`; and when an existing record already lacked a valid `category` before the edit, the system does not refuse the edit for it,
so that the second measured miss cannot land, while old records never block a conforming edit.

### REQ-14: Conforming writes are never refused

When a session writes a conforming draft, edits an existing numbered record (a status flip, a cross-reference field, a body correction) without making its `category` invalid, writes `DECISIONS_INDEX.md` or a `CLAUDE.md` directory guide, or writes any file outside `.ai-state/decisions/`,
the system allows the write with no message,
so that authoring, supersession edits, index regeneration and all other work proceed as today.

### REQ-15: A commit cannot carry a refused record

When a session runs `git commit` on a branch other than `main` or `master` and the commit adds a `<NNN>-<slug>.md` record that the default branch does not hold, or adds or changes a record in a shape REQ-11, REQ-12 or REQ-13 refuses (including a record written by a shell command, which the write check never sees),
the system refuses the commit and names each offending path and its defect; and on `main` or `master` a numbered record added by promotion is allowed, as is a numbered record the default branch already holds (brought in by a merge or a rebase),
so that a refused shape that reached the tree by another route is caught before it is shared.

### REQ-16: The gate reaches managed projects, and its absence changes nothing else

When the plugin is installed in a managed project, and when a session runs with no plugin hooks (Codex, Cursor, or a Claude Code session without the plugin's hooks),
the system runs both checks in the managed project with no onboarding step; and without hooks it lets writes and commits proceed exactly as at the pipeline base, with each assistant's rule text unchanged by this pipeline except where REQ-01 and REQ-02 change it,
so that the gate is where the measured miss happens, and a host without it falls back to today's behavior.

### REQ-17: The gate is proven to bite in production shape

When each refused shape (a numbered record under `.ai-state/decisions/`, a fragment outside the drafts directory, a malformed draft name, a malformed draft id, a self-picked `dec-NNN` in a draft, a missing `category`, an invalid `category`, a numbered record committed on a feature branch) is replayed through the commands the plugin registers, delivered the way the harness delivers them,
the system refuses each, and allows each shape REQ-14 and REQ-15 allow,
so that the gate is shown to fire as installed, not only as a function.

### REQ-18: A refusal carries the rule's own lines

When the gate refuses a write or a commit,
the system includes in the refusal the lines of `rules/swe/adr-conventions.md` that govern the defect, read from the rule file so the text cannot drift from the rule (for placement the lines carrying `fragment` and `drafts`; for category the lines carrying `what exists or what connects` and `however consequential`); and when the rule file cannot be read, the system still refuses the same write with a fixed message naming the defect,
so that a session whose path rule arrived late receives the governing lines at the moment of the miss, and the decision to refuse never depends on reading the rule.

### REQ-19: The always-loaded token count falls by a measured, bounded amount

When the always-loaded budget is measured on the shipped tree under the FC-01 command,
the system reads at most 20,300 tokens against the 23,652-token baseline, and the reading's file list equals the baseline's with the moved rule replaced by `rules/swe/adr-conventions-resident.md`,
so that the saving is real tokens and no other governed source moved.

### REQ-20: No text describes the rule's old delivery

When a reader follows the agent reading order in `CLAUDE.md`, the rules catalog, the rules taxonomy guide, the disable-list example, the developer guide or the rule-crafting guidance,
the system states that the ADR rule loads in full when a file under `.ai-state/decisions/**` is touched and keeps a one-line resident at session start, that it stays core and non-disableable, and, in Codex-facing text, that Codex keeps it always-on,
so that no always-loaded or catalog statement contradicts the shipped delivery.

### REQ-21: The move instrument refuses to measure a landed move

When the adr-conventions move's lean arm is built against the shipped tree,
the system refuses before any session starts, with a reason naming what the shipped tree already holds,
so that no later paired run compares the shipped arm with itself.

### REQ-22: An unbounded read of the decisions index is refused

When a session's Read would read `.ai-state/decisions/DECISIONS_INDEX.md` whole (with no line limit),
the system refuses the read and names the retrieval-first alternatives the rule's Discovery Protocol gives (the ADR query script over the files at hand, or a keyword search of the index followed by a bounded read of the matching rows); and a Read of the index with a line limit, or a Read of any other file, is allowed with no message,
so that the one instruction of the moved rule whose behaviour precedes the rule's path-scoped arrival still holds on time, while the rule's stated exception (a deliberate whole read for a cross-cutting task) stays reachable as a bounded read.

## Acceptance Criteria at Close

Status is the verifier's: the first pass at `a61bb800`, then the delta re-verification at `9115beb2`; the four post-delta residuals are the implementer's evidence (canaries bite with the fixes reverted).

| Criterion | Requirements | Status | Evidence at close |
|---|---|---|---|
| AC-01 | REQ-01, REQ-02 | PASS | A session starts holding the resident title and sentence verbatim and no other body line of the rule; the installed rule's `paths:` scope takes a draft, a numbered record and the index; the rule a touch delivers is the whole rule. |
| AC-02 | REQ-03 | PASS | `cmp` with the kit file is identical; sha256 `b0c7c366` equals the results file's lean identity; the diff from base is frontmatter only. |
| AC-03 | REQ-04 | PASS | Body and manifest rows equal the measured arm. First pass WARN: the stated reason for the resident's `codex: {load: exclude}` was false (the bridge skips by `resident_of` before it reads `codex:`); the key was dropped in `37e896e4`, leaving 94 bytes of frontmatter. |
| AC-04 | REQ-05 | PASS | Scratch-home install links both files; a disable list naming or globbing either leaves both loaded and prints the cannot-disable-core warning; the expected core ids gain the resident and the session-start injection test stays green. |
| AC-05 | REQ-06, REQ-07, REQ-08 | PASS | Four drift checks exit 0; kernels and index digest equal the base; a foreign resident line and an unclassified section added to the moved rule are reported by text. |
| AC-06 | REQ-09, REQ-10 | PASS | Codex always-on set and pointer text equal the base's and export no resident rule; the Cursor export equals the base per file digest; both parity tables hold ten shapes after the rework. |
| AC-07 | REQ-11, REQ-12, REQ-13 | PASS | Every refused write shape denied through the registered hook command (a relative path; case-folded directory names; a self-picked `dec-500`; a quoted id or an id with a comment; an Edit that drops `category`). First pass hole W-2 (a duplicate `category:` landed) closed last-wins in `0cf01f37`, and its spaced-key residual (`category : bogus`) in `dcd4bfee`. |
| AC-08 | REQ-14 | PASS | A conforming draft and a status-flip Edit of a numbered record are allowed silently. |
| AC-09 | REQ-15 | PASS | A numbered record off `main` is refused naming each path; a promoted record on `main` and a merge bringing in a record main holds are allowed. First pass W-1 (a stale local `main` refused a legitimate merge) closed in `0cf01f37`; its over-match D-1 (`origin/feature/main`) closed in `dcd4bfee` with the remote segment anchored. |
| AC-10 | REQ-16, REQ-17 | PASS | Every refused and allowed shape replayed through the registered commands (`/bin/sh -c`, JSON on stdin, project cwd, scratch home); with no hooks, writes and commits behave as at the base. |
| AC-11 | REQ-18 | PASS | The refusal holds the rule's own lines for the four governed phrases; with the rule unreadable the same write is still refused; a replay under the ambient 3.9 interpreter refused correctly. |
| AC-12 | REQ-19 | PASS | FC-01 20,273 against the 20,300 limit; the file list differs from the base only by the resident replacing the rule. |
| AC-13 | REQ-20 | PASS | No reader text says the rule loads in full at session start; each names the path scope and the resident; the verifier judged the Codex-facing texts true for Codex. |
| AC-14 | REQ-21 | PASS | Building the move's lean arm over the shipped tree is refused before any session, naming why; a run is refused before any session starts. |
| AC-16 | REQ-22 | PASS | A whole read of the index (and an `offset`-only read) is denied naming the bounded alternatives; a `limit` read and a read of any other file land silently. |
| AC-15 | guards | PASS | Root suite 15,892 passed, 32 skipped (dashboard dependencies, as at the baseline), 0 failed at the integration checkpoint; the calibration row records the foreground root run after the rework at 15,907 plus 2 signal tests green; eval 3,667 passed; acceptance 165 passed (four new modules plus the amended guard); gate and exporter unit tests 693 passed at the delta; every drift and gate check exit 0; pre-commit over the branch exit 0. The dashboard suite was withheld (`node_modules` absent). The outer-loop amendments were ratified (below). |

### Footprint at Close

| Id | Limit | Baseline (`3074eaa4`) | Final | Within |
|---|---|---|---|---|
| FC-01 always-loaded tokens (scratch home) | at or below 20,300 | 23,652 | 20,273 (`9115beb2`; the verifier's own reading agrees; headroom 27) | PASS |
| FC-02 listing tokens | at or below 14,268 | 14,268 | 14,268 | PASS |
| FC-03 files over the fail ceiling | at or below 0 | 0 | 0 (warns only: `skills/rule-crafting/SKILL.md` at 418 lines, `agents/sentinel.md`, `agents/systems-architect.md`) | PASS |

FC-01 read 20,284 at `755e7ce2` before the dead `codex:` key was dropped (-11 tokens). The later commits `dcd4bfee` and `a9f5ab73` touch gate code, tests, one ADR draft and a catalog row, none an always-loaded source. `check_footprint_criteria.py --stage verify` exits 0 with no findings against both `3a85719e` and the acceptance base `0cb27592`. FC-01 is read with `count_tokens` (a metadata call, no inference), basis `tokenizer`.

## Traceability Matrix

Rendered from `traceability.yml` at archival. `Status` is the verifier's reading (first pass, delta, and the noted residual fixes). Implementation cells that begin "component map" come from the architecture's component table, because the traceability map records implementation units only for REQ-07, REQ-11 to REQ-15 and REQ-22; the verifier ran further unit and canary suites (693 passed at the delta) that the map does not attribute per requirement.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | (none recorded) | 3 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_a_session_starts_holding_the_resident_title_and_sentence_verbatim, test_a_session_starts_with_no_other_line_of_the_rule, test_no_instruction_file_a_praxion_or_managed_session_loads_carries_the_rule_body) | component map: `rules/swe/adr-conventions-resident.md`, `rules/swe/adr-conventions.md` | PASS |
| REQ-02 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_touching_a_decision_file_delivers_the_installed_rule_by_its_path_scope, test_the_rule_a_touch_delivers_is_the_whole_rule) | component map: `rules/swe/adr-conventions.md` | PASS |
| REQ-03 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_the_shipped_rule_is_the_measured_arms_rule_byte_for_byte, test_the_shipped_rules_body_is_the_bases_body_byte_for_byte) | component map: `rules/swe/adr-conventions.md` | PASS |
| REQ-04 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_the_shipped_resident_differs_from_the_measured_one_only_by_a_frontmatter_block, test_the_manifest_row_carries_the_measured_arms_values) | component map: `rules/swe/adr-conventions-resident.md`, `rules/_manifest.yaml`, `scripts/regenerate_rules_manifest.py` | PASS (first-pass WARN on the stale `codex:` key reason closed in rework) |
| REQ-05 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_the_installer_links_the_file_into_the_rules_directory, test_a_disable_list_naming_either_file_warns_it_is_core_and_keeps_both_loaded) | component map: `rules/swe/adr-conventions-resident.md`, `rules/_manifest.yaml`, `scripts/regenerate_rules_manifest.py` | PASS |
| REQ-06 | (none recorded) | 3 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_the_drift_check_passes_on_the_shipped_tree[generate_kernels.py], test_the_drift_check_passes_on_the_shipped_tree[check_kernel_manifest.py], test_the_generated_role_kernels_and_their_index_are_the_bases) | component map: `scripts/kernel_sources.py`, `scripts/_resident_of.py` | PASS |
| REQ-07 | 5 test(s) -- `scripts/test__resident_of.py` (test_the_declared_parent_path_is_returned); `scripts/test_kernel_sources.py` (test_the_rule_a_resident_names_stays_a_source_though_it_is_path_scoped, test_a_resident_line_that_is_no_line_of_the_rule_is_named); `scripts/test_check_kernel_manifest.py` (test_a_resident_line_that_is_no_line_of_its_rule_is_reported_by_its_text, test_a_section_added_to_a_path_scoped_rule_with_a_resident_is_reported) | 2 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_an_unclassified_section_added_to_the_moved_rule_is_reported, test_a_resident_line_that_is_no_line_of_the_moved_rule_is_reported) | `scripts/_resident_of.py` (resident_parent); `scripts/kernel_sources.py` (always_loaded_sources, resident_foreign_lines); `scripts/check_kernel_manifest.py` (foreign_line_findings) | PASS |
| REQ-08 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_the_drift_check_passes_on_the_shipped_tree[regenerate_rules_manifest.py], test_the_drift_check_passes_on_the_shipped_tree[sync_canonical_blocks.py]) | component map: `scripts/regenerate_rules_manifest.py`, `rules/_manifest.yaml` | PASS |
| REQ-09 | (none recorded) | 3 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_the_codex_bridge_keeps_the_bases_always_on_rule_set, test_the_codex_bridge_keeps_the_bases_session_start_pointer_text, test_the_codex_bridge_exports_no_rule_for_the_resident_file) | component map: `codex/config/rules_bridge_parsing.py`, `rules/swe/adr-conventions.md` | PASS |
| REQ-10 | (none recorded) | 1 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_the_cursor_export_is_the_bases_byte_for_byte) | component map: `cursor/config/export-cursor-rules.py` | PASS |
| REQ-11 | 1 test(s) -- `scripts/test__decision_records.py` ((module)) | 1 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_write_creating_a_refused_record_is_refused_naming_the_correct_form) | `scripts/_decision_records.py` (classify_path, judge_change) | PASS |
| REQ-12 | 1 test(s) -- `scripts/test__decision_records.py` ((module)) | 1 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_write_creating_a_refused_record_is_refused_naming_the_correct_form) | `scripts/_decision_records.py` (classify_name, parse_id, judge_change) | PASS |
| REQ-13 | 1 test(s) -- `scripts/test__decision_records.py` ((module)) | 3 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_write_creating_a_refused_record_is_refused_naming_the_correct_form, test_a_category_refusal_names_the_four_values, test_an_edit_removing_or_invalidating_a_records_category_is_refused) | `scripts/_decision_records.py` (parse_category, judge_change) | PASS (duplicate-key hole W-2 and residual D-2 closed; D-2 not re-read by a verifier) |
| REQ-14 | 1 test(s) -- `scripts/test__decision_records.py` ((module)) | 3 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_conforming_write_lands_with_no_message, test_an_edit_of_an_older_record_lacking_a_category_lands_with_no_message, test_an_edit_of_a_numbered_record_that_keeps_its_category_lands_with_no_message) | `scripts/_decision_records.py` (judge_change) | PASS |
| REQ-15 | 2 test(s) -- `scripts/test__decision_records.py` ((module)); `scripts/test_check_decision_records.py` ((module)) | 5 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_commit_on_a_feature_branch_adding_a_numbered_record_is_refused_naming_it, test_a_commit_carrying_records_a_shell_wrote_names_each_offending_path, test_a_commit_of_a_conforming_draft_on_a_feature_branch_is_allowed, test_a_commit_on_main_adding_a_promoted_numbered_record_is_allowed, test_a_merge_bringing_in_a_numbered_record_main_holds_is_allowed) | `scripts/_decision_records.py` (judge_change); `scripts/check_decision_records.py` (main) | PASS (W-1 closed at the delta; over-match D-1 closed after it, not re-read by a verifier) |
| REQ-16 | (none recorded) | 1 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_without_the_plugins_hooks_a_numbered_record_is_written_and_committed_as_before) | component map: `hooks/hooks.json`, `hooks/decisions_gate.sh`, `hooks/guard_decision_records.py` | PASS (the gate reaches marketplace installs only after a release) |
| REQ-17 | (none recorded) | 2 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_write_creating_a_refused_record_is_refused_naming_the_correct_form, test_a_commit_on_a_feature_branch_adding_a_numbered_record_is_refused_naming_it) | component map: `hooks/hooks.json`, `hooks/decisions_gate.sh` | PASS |
| REQ-18 | (none recorded) | 2 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_refusal_carries_the_rules_own_line_holding_the_governed_phrase, test_the_same_write_is_refused_when_the_rule_cannot_be_read) | component map: `scripts/_decision_record_refusal.py` | PASS |
| REQ-19 | (none recorded) | 1 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_the_always_loaded_reading_counts_the_resident_where_it_counted_the_rule) | component map: `rules/swe/adr-conventions-resident.md`, `rules/swe/adr-conventions.md` | PASS (FC-01 20,273 against 20,300) |
| REQ-20 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_move_keeps_every_other_reach.py` (test_no_reader_text_says_the_rule_loads_in_full_at_session_start, test_each_reader_text_names_the_rules_path_scope_and_its_resident) | component map: `CLAUDE.md`, `AGENTS.md.tmpl`, `rules/README.md`, `rules/CLAUDE.md`, `docs/rules-taxonomy.md`, `claude/config/praxion-rules.yaml.example`, `README_DEV.md`, `skills/rule-crafting/SKILL.md` | PASS (Codex truth judged by the verifier) |
| REQ-21 | (none recorded) | 2 test(s) -- `tests/acceptance/test_adr_rule_is_delivered_by_its_path.py` (test_building_the_moves_lean_arm_over_the_shipped_tree_is_refused_naming_why, test_a_run_of_the_landed_move_is_refused_before_any_session_starts) | component map: `eval/src/praxion_evals/adherence/moves/arms.py` | PASS |
| REQ-22 | 1 test(s) -- `scripts/test__decision_records.py` ((module)) | 2 test(s) -- `tests/acceptance/test_decision_record_gate.py` (test_a_whole_read_of_the_decisions_index_is_refused_naming_the_bounded_alternatives, test_a_bounded_read_of_the_index_or_a_read_of_any_other_file_lands_with_no_message) | `scripts/_decision_records.py` (judge_read) | PASS |

**Coverage**: all 22 requirements carry acceptance evidence, and 7 of 22 carry recorded unit evidence (REQ-07, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-22); the rest are proven by their acceptance nodes. No requirement is UNTESTED.

## Key Decisions

Two ADR drafts carry the architectural decisions (`dec-480`, `dec-481`); the entries below are from `LEARNINGS.md § Decisions Made`, `CHECKPOINT_DIGEST.md` and the verifier's rulings.

**[systems-architect] The ADR rule is path-scoped with a declared resident projection (architectural; `dec-480`)**: ship the kit's rule bytes; add `rules/swe/adr-conventions-resident.md` carrying `resident_of`, read as one fact by the kernel tooling and checked by the two exporters. **Why**: the measured arm ships with no kernel churn and the parent stays total. **Alternatives**: an audience entry `role/adr-author` (copies the title paragraph into four kernels and moves `kernel_version`); `orchestrator-only` or `no-actor` (fails the adr-author totality check); a name convention `*-resident.md` (implicit knowledge two readers would re-derive); a hand-kept manifest row (the generator rewrites it); an alias scope in the audience manifest (serves only the kernel tools).

**[systems-architect] The decision-record gate and the index read guard (architectural; `dec-481`)**: one rules module, write time primary, commit time as backstop. **Why**: the path rule arrives with the creating write's result while a refusal arrives before the file exists and can carry the rule's lines, so write time is the only layer on time; commit time catches records a shell wrote, which never trigger the path rule. **Alternatives**: grow the resident (about 150 to 250 tokens, an unmeasured arm); commit-only; write-only; a PostToolUse Bash check (starts Python on every Bash call, reports after the fact); finalize (too late, and it already strands bad drafts); the onboarding-installed pre-commit hook (changes the onboarding contract and its upgrade lock-step for commits outside a session, where the miss did not happen).

**[systems-architect] The resident is not grown (behavioral)**: the resident stays the measured title and sentence. **Why**: a larger kernel would be an unmeasured arm; the residual (4 of 24 late, 1 unrepaired) is closed deterministically by the gate instead. **Alternatives**: the context review's candidate lines (File Format paragraph, Finalized-ADRs line, Falsifier line).

**[systems-architect] Extract the commit scope helpers before reuse (implementation)**: `scripts/_commit_scope.py` takes the same-call staging helpers unchanged from the id-citation gate. **Why**: a gate importing another gate's internals couples two gates; the second consumer is the moment to extract. **Alternatives**: import from `scripts/check_id_citation_discipline.py` directly.

**[systems-architect, adopted from the context review] Refusal text quotes rule lines selected by heading and defect (behavioral)**: lines are chosen by rule heading and ordinal per defect family, capped near 700 characters, each shared line quoted once per commit refusal, with the four governed phrases kept as the test oracle only; a refused Read states the exact retry form. **Why**: a refused Read loads no path rule and a late rule has not arrived, so the refusal is the only on-time delivery of those lines at that moment, and it must stay short; a reworded heading or a shifted section falls back to a one-line message rather than quoting the wrong line. **Alternatives**: select lines by the governed phrases alone.

**[implementation-planner] The gate ships as one command with two private siblings (implementation)**: `check_decision_records.py` (command line, git edge), `_decision_records.py` (pure types, classifier, judge), `_decision_record_refusal.py` (refusal text). **Why**: one file would run about 600 lines and does not fit one implementer window; the split also puts the mutation sensor's targets on the pure judge and on the world-read edge separately. **Alternatives**: one file; a package directory (the flat `scripts/` sibling layout is the repository's pattern and the hook adapter imports siblings by location). No ADR: a private split inside one component moves no boundary.

**[implementation-planner] One architecture-documents step at the end, review tags by signal (implementation)**: step 16 folds the gate row and the resident pattern into `DESIGN.md` and `docs/architecture.md` once; `review: force` on steps 3, 7, 10, 11 (kernel sources, gate core, commit payload, hook adapters), with `mutation: on` on 7, 9, 10, 11. **Why**: one coherent entry beats ten partial edits to the same two files, and five reviews would put the worst case at the full 32-spawn budget. **Alternatives**: `[Architecture]` tags on steps 6 and 12; a review on step 8 or 9 (their output is graded directly by the governed-phrase nodes, or is a thin line over step 7).

**[implementer] Exporters check `resident_of` themselves, pinned to the shared reader by parity tests (implementation)**: step 4 replaced a shared-reader import into the Cursor exporter with a local check; the Codex bridge does the same. **Why**: the cross-tree import broke every narrowed checkout copy (the move instrument's arm builds copy only declared read sets); `cursor/config/` and `scripts/` are distant trees and the shared knowledge is one key's presence (Balanced Coupling). **Alternatives**: one shared reader imported across trees (the design's first reading).

**[implementer] Gate judging decisions (implementation)**: a fragment name needs finalize's token floor (stamp parses and at least three hyphen-separated tokens after it) with ASCII digits and `fullmatch`; numbered records excused by context (on `main`, or the default branch already holds the path) are not judged at all, since finalize-promoted and old records may lack a category and judging them would block promotion and merges; the path is anchored on its own `.ai-state/decisions` text and accepted only when the prefix holds a `.git` entry (a worktree holds it as a file); the default branch means a local or remote-tracking `main`/`master` (remote segment anchored); `category` is last-wins and tolerates whitespace before the colon, `id` stays first-wins. **Why**: each follows the reader that decides the outcome downstream (finalize's `re.search` for `id`; the index generator and PyYAML for `category`). **Alternatives**: first-wins for both; resolving each remote's `HEAD` symref; cwd-relative or symlink-resolved path anchoring (a worktree session's root may differ from the payload's).

**[implementer] The gate and the eval grader differ on purpose (implementation)**: the parity test uses only fixtures where `_decision_records.py` and the grader agree; they differ by design on the branch segment (the grader requires it in a fragment name; the gate needs three tokens), category case (grader casefolds; gate is exact) and quoted ids (grader reads YAML; gate reads the raw line). **Why**: the gate must be stdlib-only and refuse exactly what finalize would strand, while the grader scores what a model left. **Alternatives**: merging the two encodings.

**[implementer] Drop the resident's unread `codex:` key (implementation)**: removed in `37e896e4`; FC-01 20,284 to 20,273. **Why**: the Codex bridge skips a `resident_of` file before it parses `codex:`, so no path read the key and its documented reason was false. **Alternatives**: keep it as a declared fallback in the ADR text.

**[systems-architect] Assumptions taken (surfaced, revisable)**: A1, the harness treats a resident file's frontmatter as it does every always-on rule's (constant across arms; the 94 bytes are unmeasured, accepted as named); A2, plugin hooks fire for subagent tool calls; A3, "main" is `main` or `master`, the finalize chain's predicate; A4, no paid session ran, so delivery rests on the paired run and the gate on canaries. **[implementation-planner]** P2, `count_tokens` is a metadata call and allowed under the standing instruction of no paid inference (without it FC-01 would be an estimate wider than its 85-token headroom); P3, the adr-lean-arm eval tests could redden when the resident or the swap landed (they did build a landed move, so they carry a pre-move rule fixture, `eval/tests/fixtures/pre_move_adr_conventions.md`).

### Spec-phase questions (checkpoint digest, SQ-01 to SQ-07)

The user's go of 2026-10-30 delegated these to the orchestrator, who decided and recorded them; push, release and worktree removal stayed ask-first.

| SQ | Decision | Why |
|---|---|---|
| SQ-01 Discovery Protocol timing | Changed from the recommendation: a deterministic read guard (REQ-22, AC-16), not a ledger row | The index read the rule forbids happens before the path rule can arrive; accepting it would spend a measured saving on the costliest read in the corpus. A guard is cheaper than a resident sentence (an unmeasured arm) and keeps the rule's exception reachable as a bounded read. |
| SQ-02 numbered record on main | Refuse at write time on every branch; at commit time allow `main`/`master` | The rule reserves self-numbering for no-session manual records; finalize is a script, not a session write. |
| SQ-03 Disconfirmation section | Accept: not refused | Write-early skeletons would trip it; no session failed it. |
| SQ-04 commits outside a session | Accept: declared limit | The miss was measured in sessions; reaching outside them changes the onboarding contract. |
| SQ-05 agent definitions | Accept: no edit | Their links still resolve and the rule still owns the test. |
| SQ-06 footprint readings | Accept: FC-01 under a scratch home; a real-HOME reading post-merge; no startup-payload run without the user's go | The dev-install links point at main's rules until the merge. |
| SQ-07 amend earlier acceptance tests | Accept and ratified on the user's delegation | The earlier contracts that pin the ADR rule as always-loaded break on purpose; each amended node is listed below. |

Added constraint for every test: none runs `bash install.sh` or any installer against the real home (scratch home only).

### Outer-loop amendments (`ACCEPTANCE_TESTS.md` Spec Questions SQ-01 to SQ-05)

Raised after acceptance design (`60ae3ce2`), recorded as answered Spec Questions in the rework (the first verification read their absence as F-1 and F-2); the verifier judged each justified and minimal.

| SQ | Question | Resolution | Resolved in |
|---|---|---|---|
| SQ-01 | Which texts are "Codex-facing", and which phrasing states the old delivery? | The provisional answer stands (the six named reader texts; a stale statement names the ADR rule with always-on, always-loaded, "at session start" or "every session" and none of the decision path, resident, path-scoped or Codex); the verifier judged them true for Codex | `396b5184` |
| SQ-02 | May a later change remove a selection edge an earlier pipeline's guard froze? | A recorded contract change: a named set `UNREACHED_ON_PURPOSE` subtracts the one incidental edge to `scripts/test__git_runner.py` (a skill edit reached it only through the id-citation gate's `skills/` literal before the helpers moved); every other frozen edge stays pinned | `8d94e2d0` |
| SQ-03 | The move driver's restore wrote the base manifest row in an order the instrument cannot find | A driver repair, not a contract change: restore the row in the generator's key order | `efe89a9e` |
| SQ-04 | May the move reword the paragraph the no-rewording guard pins in `CLAUDE.md`? | A declared rewording pinned to its new wording byte for byte (further drift still fails); the commit also adds the eval fixture `eval/tests/fixtures/pre_move_adr_conventions.md` | `069bdf31` |
| SQ-05 | The FC-01 command's placeholder sat inside one token | Form-only: `env <home-assignment> python3 scripts/measure_token_budget.py --json`; the instrument, reading and limit are unchanged and no test reads the literal; spec digest `335b8eda8f50` to `2cfd9a42f109` | the amended criterion |

Also amended at acceptance design (ratified under SQ-07 above): the always-loaded pin for the ADR rule in `tests/acceptance/test_resident_text_is_moved_not_cut.py` became a node asserting the declared move, and `tests/acceptance/drivers/move_eval.py::move_checkout` gained `shipped: bool = False` so the earlier arm-building scenarios keep measuring an unlanded move (178 earlier nodes still pass).

### Execution record

- Step 2: attempts exhausted on an earlier pipeline's guard, resolved as SQ-02. Step 3: blocked by a plan defect (a Read-only node needed the resident file step 5 ships), node moved to step 5; light review accept. Step 4: attempts exhausted on the shared-reader import, resolved by the local checks above. Steps 7, 10, 11: each one revise and one accept in light review (a blank existing file judged as an edit and a refused-shape hole; common commit spellings read as non-commits; a hook wrapper that was not fail-open when the guard was missing, plus an Edit with an empty `old_string` and a write filter narrower than the judged path).
- Step 14: blocked, foreseen by the pre-mortem (the no-rewording guard pinned the reading order), resolved as SQ-04.
- Step 18: both honest FC-01 log rows read FP03 wrong-command until the command form was amended (SQ-05).
- Steps 19 and 20 left the loop at 38 of 38 iterations; step 19 was established by the implementer's own whole-suite runs (15,892 passed twice) and step 20 by the orchestrator (eval 3,667, every drift and gate check, pre-commit over the branch).
- Pre-mortem (accepted with one addition): eval sessions built from a checkout carrying the gate meet it in both arms equally, and the instrument refuses to measure the landed move, so no paired comparison is skewed.

### Verification and rework

First pass at `a61bb800` (27 commits, 77 files): FAIL, 2 FAIL and 10 WARN. Rework rows: (1) record the amendments as answered Spec Questions (done in the records); (2) gate edges: remote-tracking default branch, last-wins `category`, declared limits for `git add -u` and unseen commit spellings (`0cf01f37`); (3) the resident's dead `codex:` key, the two parity shapes (`non-md-value`, `longer-key`), the two ADR drafts' module names and `affected_files`, the `scripts/CLAUDE.md` catalog rows (`37e896e4`, `6b281c03`, `9115beb2`); a separate docs commit (`a558fd31`) records the git paired run and the landed move in `eval/EVAL_PLAN.md`. Delta at `9115beb2`: PASS WITH FINDINGS, 0 FAIL, 3 WARN (D-1 remote pattern spans slashes, D-2 spaced duplicate key, D-3 the resident ADR contradicted itself on FC-01), 2 INFO (D-4 a catalog row said "the one reader", D-5 the `td-528` row uncommitted). Row 4 closed D-1 and D-2 in `dcd4bfee` (anchored remote segment `refs/remotes/[^/]+/(main|master)`; `[ \t]*` before the colon; eight new canaries fail with the fixes reverted, 628 passed) and D-3 and D-4 in `a9f5ab73`; D-5 is the orchestrator's commit. No verifier has re-read row 4.

## Gotchas Worth Keeping

- **An outer-loop amendment needs an answered Spec Question, not only a digest line.** An edit to an acceptance file after acceptance design, and a changed extract digest, read as F-1 and F-2 when recorded only in the checkpoint digest. Record each as a Spec Question with `Resolved in: <sha>` and account for the digest change at the time.
- **A claimed agreement with another reader needs a probe of that reader's own grammar.** The gate's frontmatter reader claimed to agree with the index generator; the first probe covered duplicate order (W-2) and missed whitespace before the colon (D-2). Probe the key pattern, not only the semantics.
- **Anchor every segment of a widened ref pattern.** `refs/remotes/.+/main` let `origin/feature/main` count as a default branch; `[^/]+` is the remote. Local heads were anchored, remote-tracking refs were not.
- **A frontmatter key must name its reader.** The resident's `codex: {load: exclude}` was dead config once the Codex bridge skipped a `resident_of` file before parsing `codex:`; a maintainer would have relied on a key the ADR described differently.
- **A cross-tree import breaks narrowed checkout copies.** The move instrument's arm builds copy only declared read sets, so a `cursor/config/` exporter importing `scripts/` fails there; a parity-tested local check is the sound form when the shared knowledge is one key's presence.
- **ADR text drifts when the planner re-lays a component's files.** The architect's draft named `check_decision_records.py` as "the rules module"; the planner split it into three files, and the drafts needed a realignment pass (`affected_files`, Decision, Falsifier) in the rework. When a layout decision moves a named component's files, the drafts owe an update in the same step.
- **Hook adapter traps.** Forward payloads with `printf '%s\n'`, never `echo` (it mangles escapes); match the decisions directory case-insensitively (macOS); a worktree holds `.git` as a file; commit detection is a per-segment regex, since `shlex` fails on a heredoc message whose first line leaves a quote open; a top-level import failure exits 1, which PreToolUse treats as non-blocking.
- **Mutation-sensor limits for gate scripts.** A test that spawns the mutated script as a child must not set `cwd` away from the sensor's directory (the trampoline loads its config from the cwd and the child dies); mutmut counts only in-process hits and the test module must import the target by its file name; a copy of a guard runs one directory deeper, so locate `scripts/` by walking ancestors. A gate script also needs a test function named for rejection (`test_reject...`) for the gate-canary coverage check, and stays GL04-pending until it is registered.
- **Step-loop bounds.** A step's `Check:` is bounded by a fixed 540 s that ignores the pocket bounds applied to gate runs (`td-527`); the iteration budget scales with driven steps, so reassigning steps shrinks it; `pending=` and `pass>=` figures in `Check:` lines assume strictly sequential execution in plan order; a parametrized `Read-only:` entry owns by prefix at a `[` boundary (verify ownership by parsing the plan against the failing ids).
- **A footprint command's placeholder stands for one whole token.** `HOME=<scratch-home>` cannot match the grammar; `env <home-assignment> python3 scripts/measure_token_budget.py --json` does.

## Follow-up

On the user's go: merge `apply-rule-moves` to main with `--no-ff` (finalize promotes the two drafts to `dec-NNN` and rewrites their citations in the documents and in this spec; regenerate the specs index afterwards so the ADR column fills); the orchestrator commits the `td-528` row and the calibration row; take a real-HOME FC-01 reading; the gate reaches marketplace installs only after a release; choose the `td-526` path (a deterministic commit-msg gate or a reliably moved check part) before any new git paired run; fix `td-527` before the next whole-suite integration step; optionally spawn a verifier to re-read row 4 (D-1 to D-4).
