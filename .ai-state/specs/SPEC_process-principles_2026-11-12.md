# Spec: process-principles (a ninth principle, and small debt fixed after the feature instead of filed)

**Task slug**: `process-principles`
**Created**: 2026-11-12
**Pipeline run**: 2026-11-12 (the last readings are stamped 2026-11-13T04:52Z, UTC). The stages:
- intake and spec, with four Spec Questions answered by the orchestrator;
- acceptance design, with four early Spec Questions, answered in the requirement text;
- design (two decision drafts) and an 18-step plan;
- 10 of the 18 steps through the step loop, and the other 8 by the orchestrator (readings, re-pins, driver binding, documentation, traceability, integration);
- final verification;
- a follow-up pass over 14 items, a re-pin of the guards its one shipped-text change moved, and a ledger close-out.

**Archived**: 2026-11-12 (pre-merge, on branch `feat/process-principles`)
**Status**: completed -- final verdict PASS WITH FINDINGS (36 PASS, 15 WARN, 0 FAIL). Every WARN was fixed in the follow-up pass or became a ledger row, except one advisory finding on an ephemeral artifact (see Key Decisions, Verification). td-645 is resolved by `3979aeab`; td-646 to td-650 are open.
**Tier**: Standard (the calibration verdict reads `correct`: two behaviours with behaviour-bearing code, a parser, a gate reason, a generator change and a registry entry, so the spec, the acceptance stage and the re-pin discipline were all needed, and nothing called for Full's research or multi-perspective stages)
**Complexity**: medium: 12 requirements, 67 files changed over 32 commits (2,522 insertions and 620 deletions, `git diff --stat c703f481..38dd2d74`), 1 new parser module, 1 new kernel module, 1 generator change, 11 frozen-guard fixtures re-pinned.
**Base commit**: `c703f481`. Further commits:
- acceptance design `e8a993b0`, design `f42eb1d4`, driver binding `bb48ceab`;
- the plan steps `bf2f84e2` to `538c6e69` (10 driven steps through the step loop, 20 of 29 iterations, three forced reviews accepted);
- two frozen-guard re-pins, `a3d6a2f9` and `649ecc7f`;
- documentation `fc4d600a`;
- the follow-up pass `51aee623` to `4418740c` (nine items fixed, four ledgered, one dropped), its re-pin `6d22fb2f`, and state commits `e1b62abc` and `38dd2d74`.

**Pipeline branch**: `feat/process-principles`
**ADRs (promoted at merge)**: both are drafts today and take their `dec-NNN` ids at the merge:
- `dec-draft-d170480e` (architectural): the kernels' principles pointer takes its count and names from the template's headings through the generator, and a prior-art kernel module delivers the new principle to the three choosing roles;
- `dec-draft-66ca6b02` (architectural): small debt goes to a per-task follow-up record the cleanup gate blocks on, and the orchestrator closes it after the feature.

**Related specs**: `SPEC_audience-split_2026-11-09.md` (the kernel modules and the spawn split this change adds a module to), and `SPEC_apply-rule-moves_2026-10-31.md`, `SPEC_model-routing-move_2026-11-01.md`, `SPEC_routing-facts_2026-11-02.md`, `SPEC_project-gating_2026-11-06.md` (the earlier pipelines whose frozen guards were re-pinned here).

## Feature Summary

Two process rules now reach every session through artifacts: a ninth principle, and small debt fixed after the feature instead of filed.

Before this:
- The philosophy template listed eight principles. The kernels' principles pointer named them in a hand-written sentence, one test kept a hand constant of eight and another sliced the first eight headings, so a ninth principle, a removal or a rename needed hand edits that could drift silently.
- Small debt found while solving a task went to the tech-debt ledger as a row. The ledger reference told the orchestrator to file adjacent debt from a Direct-tier fix as one.

Now, the principle:
- The template carries "Standing on the Shoulders of Giants" between Data Structures First and Incremental Evolution, in the user's decided text. The verifier found it byte-identical, so no wording change is listed.
- A new kernel module, `principles-prior-art`, delivers its full text to the promethean, the systems architect and the researcher only. The largest kernel string per role stays under the 10,000-character cap (roadmap-cartographer 9,153, researcher 9,008).
- The pointer's count and names are filled by the kernel generator from the template's headings. A tenth principle, a removal or a rename needs no hand edit, and the freshness check fails while the committed kernels lag.
- The Codex project baseline mirrors the principle. The follow-up pass also added Balanced Coupling, which the mirror never had, with a parity test on its heading list.

Now, small debt:
- The ledger reference defines *small* once, as seven conditions that are all required, and files a row only for debt that is not small or could not be finished this session, with the reason in the row. One always-loaded sentence in the intermediate-documents rule says so, scoped to a task.
- During a pipeline the verifier and the orchestrator record small debt as an `open` line of `FOLLOW_UPS.md` in the task directory. The implementer reports it on a `Follow-ups:` line of its return. The sentinel and the architect-validator, which have no task at hand, keep filing a row for every finding.
- After the verifier, the orchestrator closes every open item before the merge or the session's close: it fixes the item test-first in its own commit (`fixed <sha>`), files a ledger row (`ledgered td-NNN`), or drops it with a reason. No extra verifier spawn runs, and the closing digest names each outcome. At Direct and Lightweight tiers the session's task list holds the items.
- `scripts/clean_work_safety.py` (behind `/clean-work`) classifies a task directory with an open follow-up as `BLOCK`, with a reason that names the record and each open item. An unreadable item, or a final state whose argument is missing or misshapen, counts as open.
- The record is a registered pipeline artifact (`block-if-active`), listed in the dashboard's workshop list, the compaction snapshot and the inventory tree.

## What Was Built

- **The principle:**
  - `claude/config/CLAUDE.md.tmpl`: the new section.
  - `rules/_audience.yaml`: the module `principles-prior-art` for exactly the three roles, and the template heading classified `scope: role`, `form: verbatim`.
  - `claude/kernels/principles-prior-art.md` (new), with `core.md`, `principles.md`, `index.json` and `spawn_split.json` regenerated by the generator, never by hand.
- **The derived names:**
  - `scripts/generate_kernels.py`: `principle_headings` and `fill_principle_markers` share one extent reader.
  - `claude/kernels/src/principles-pointer.md` keeps two markers, `@@PRINCIPLE_COUNT@@` and `@@PRINCIPLE_NAMES@@`. A missing, repeated or unfilled marker raises.
  - `scripts/test_kernel_authored_texts.py` drops its hand constant and reads the rendered pointer.
- **The Codex baseline:** `codex/config/AGENTS.md.tmpl` and the root `AGENTS.md` (the principle by the compile, the reading order refreshed in the follow-up pass), and a parity test in `scripts/test_install_codex.py`.
- **The follow-up record:**
  - `scripts/_follow_ups.py` (new): the line grammar as a normative docstring, and the parser. The items are a closed sum type (`Open`, `Fixed`, `Ledgered`, `Dropped`, `Unreadable`); `parse_record` is the only constructor, and `is_open` is an exhaustive match.
  - It stays stdlib-only and Python 3.9-safe, because managed projects run the cleanup check from `~/.local/bin` under a bare `python3`.
  - `scripts/clean_work_safety.py`: the `open-follow-ups` reason, read through `open_items`.
  - `scripts/artifact_registry.py`, `dashboard_app/src/server/artifacts/files.ts`, `hooks/precompact_state.py` and `skills/software-planning/references/artifact-inventory.md`: the registration and its three consumers. The eval task manifest builds its set from the registry and needed no edit.
- **The texts:**
  - `rules/swe/agent-intermediate-documents.md`: the summary sentence.
  - `claude/kernels/src/ledger-writer.md`: the condensation changed only the orchestrator clause. Both pins in `rules/_audience.yaml` moved with it, and the rules manifest was regenerated.
  - `claude/kernels/src/ledger-writer-verifier-overlay.md`: the verifier-only routing, so the sentinel and the architect-validator receive no new filing instruction.
  - `agents/verifier.md`, `agents/implementer.md`.
  - `skills/software-planning/references/tech-debt-ledger.md`: the seven conditions, the filing rule, the record, who writes each transition, the task list at Direct and Lightweight tiers.
  - `agent-pipeline-details.md § Exit` (the follow-up pass, step 2.5) and `coordination-details.md` (one linking sentence under the worktree lifecycle, one under tier scaling).
- **The documentation:** `.ai-state/DESIGN.md`, `docs/architecture.md`, `scripts/CLAUDE.md` and `docs/lean-spawn-kernels.md`.
- **The tests:**
  - Five new outer-loop files under `tests/acceptance/` (`test_the_giants_principle_reaches_its_readers.py`, `test_principle_names_follow_the_philosophy.py`, `test_small_debt_is_fixed_not_filed.py`, `test_cleanup_refuses_open_follow_ups.py`, `test_follow_up_record_is_a_registered_artifact.py`) with three drivers (`principle_names.py`, `follow_ups.py`, `registry_drift.py`). The design sized them as 50 test nodes from about 30 scenarios, per the user's instruction that verification effort be proportional to risk: scenario sets for the four behaviour-bearing requirements, one presence check per surface for the text requirements.
  - Unit tests: `scripts/test__follow_ups.py` (new), `scripts/test_clean_work_safety.py`, `scripts/test_kernel_authored_texts.py`, and the generator's tests, split in the follow-up pass by subject into `scripts/test_generate_kernels.py`, `scripts/test_generate_kernels_definitions.py`, `scripts/test_generate_kernels_live.py` and `scripts/_generate_kernels_testkit.py`.
  - Eleven frozen-guard fixtures re-pinned in three rounds (see the Spec Question answers).

## Footprint Readings

| Id | Baseline | Final | Limit | Reading |
|---|---|---|---|---|
| FC-01 always-loaded tokens, scratch-home method | 19914 tokens (`f42eb1d4`) | 20300 tokens (`38dd2d74`); 20297 at `649ecc7f` | at or below 20400 | measured (tokenizer) |
| FC-02 skill and agent description listing tokens | 13335 tokens (`f42eb1d4`) | 13335 tokens (`38dd2d74`) | at or below 13335 | measured |
| FC-03 prompt-size findings | 3 warn (`f42eb1d4`) | 3 warn, none at fail (`38dd2d74`) | at most 3, none at fail | measured |

Notes on the readings:
- **FC-01** is read with `HOME` pointed at a scratch home holding the checkout's own render of the template, at the base and at the head, because the installed `~/.claude/CLAUDE.md` links to the main checkout's render and cannot see a worktree's change (SQ-02). The rise is +386 over the base at the head: +316 the principle, +67 the summary sentence, and +3 from the follow-up pass's rewording of that sentence (`3979aeab`, the only always-loaded file the pass changed). The installed reading (19,918 at the base) moves only after the user's relink, which stays on the user's ask-first list and is named in the merge request.
- **Not measured, declared with a reason:** spawn-startup tokens (the only instrument runs a paid headless session per role; the free kernel check bounds every kernel string at 10,000 characters instead), spawn count (the only command counts a pipeline that has already run), hook latency (no instrument exists).
- `check_footprint_criteria.py process-principles --stage verify --base-ref c703f481` reports 0 fail, 0 warn, 0 info (run at archival, at `38dd2d74`).

Health readings:
- Integration at `fc4d600a` (before the follow-up pass): root suite 18,651 passed and 5 skipped; shell suite exit 0; the eval package's format, lint and pyright clean and 4,301 passed; nine health gates exit 0. `TEST_RESULTS.md` closes that block with `pass=22952 fail=0 skip=5`. The baseline `TEST_BASELINE.md` was clean (18,508 passed, 37 skipped at `f42eb1d4`, this pipeline's own outer-loop files excluded).
- After the follow-up pass's last re-pin (`6d22fb2f`) the eleven guard files ran at 295 passed. A new full-suite reading after the pass is not part of this archive.

## Key Decisions

- **A new kernel module for exactly the three roles, and a generator-derived pointer** (`dec-draft-d170480e`).
  - Delivery: a module whose audience equals the entry's own is the manifest's rule, following the `adr-reader` precedent. Widening `principles-digest` would have sent five unrequested principles to the researcher (about 1,300 tokens per spawn); putting the principle in `core` would push the cartographer's string past the cap, to about 10,200.
  - Names: markers in the authored pointer text, filled by the generator. The existing freshness check and manifest invariant I8 then guard against drift with no new invariant. A derived pointer file, or a hand list plus a comparison test, were rejected (the second still needs a hand edit per principle).
  - Cost: one more module file, and the researcher is left about 990 characters below the cap, recorded as a constraint in `.ai-state/DESIGN.md`.
- **Small debt through a per-task record with a closed state set** (`dec-draft-66ca6b02`).
  - One parser (`scripts/_follow_ups.py`), the existing cleanup gate reused, the registry policy `block-if-active`. A section in `LEARNINGS.md` (no closed states) and a new ledger status (persistent, and filling the ledger is what the rule stops) were rejected.
  - An unreadable or misshapen line counts as open, the safe direction. The gate does not check that a `fixed` sha is a real commit or that a `ledgered` row exists; the verifier judges that.
  - Only the orchestrator writes the three final states. This is writer discipline in the ledger reference, not checked mechanically.
- **The verifier's instruction stays in the verifier's overlay.** The shared `ledger-writer` text reaches the sentinel and the architect-validator, which have no task at hand. The condensation therefore changed only the orchestrator clause, and a presence check holds that the shared text never names the record.
- **The small bar also covers the verifier's harvested notes and pre-existing failures** (SQ-04). This widens the user's wording ("the verifier for a WARN that meets the bar") and is surfaced to the user at the merge request.
- **The Codex mirror gets the principle inside the first change** (SQ-01). Its missing Balanced Coupling was pre-existing drift and became the pass's first follow-up. Generating the mirror from the template stayed out of scope and is td-647.
- **Frozen guards are re-pinned entry by entry, never wholesale.** Each moved entry was re-pinned with its own guard's driver, diffed base against head with the repository roots normalised, and answered by its own Spec Question with `Resolved in:`. Where a guard offered a declared edit or a re-frozen reading, the declared edit was kept, so the frozen readings stay at base (AD-SQ-11, AD-SQ-25, AD-SQ-32).
- **Process:**
  - The step loop used 20 of 29 iterations: 10 first passes, 3 forced reviews accepted (steps 4, 9 and 10), and 7 attempts lost to causes outside the work. Those were the mutation sensor's refusal line (step 3), a frozen guard not listed as pending and a nested suite timing out under the orchestrator's own parallel load (step 4), a package-manager check on a linked dependency folder and a record launched from a background subshell, which ignores interrupts (step 8, three attempts), and an orchestrator note that listed a unit test of the step's own file as read-only (step 9).
  - The plan tagged steps 3 and 9 `mutation: on`. The sensor could not run over `scripts/generate_kernels.py` (step 3; the tag was then dropped from the step), and it left survivors in the cleanup check's world-read functions (step 9, td-646).
  - The follow-up pass worked its items as lanes: one implementer per item in its own worktree, the orchestrator reviewing and cherry-picking (`FOLLOW_UP_LANES.md`). The frozen guards the pass's one shipped-text change moved were re-pinned in one round after the lanes (`6d22fb2f`).
- **Verification:**
  - The final verdict is PASS WITH FINDINGS: all 12 requirements and all 3 footprint criteria are met, with REQ-07 graded WARN (meaning kept by inference, plus text residue). Counts: 36 PASS, 15 WARN, 0 FAIL. The calibration verdict reads `correct`.
  - Dispositions of the 15 WARN: REQ-07's unscoped clause became td-645 and is resolved by `3979aeab`, which scoped the sentence to a task. The verifier-text residue, the ledger reference's numbering and overlay trigger, the missing transcription instruction, the cleanup check's hand-built list, its missing severity test, the oversized test file and the two architecture-guide gaps were fixed in the follow-up pass. The parser's other bullet shapes and the unreadable record became td-649. The mutation survivors became td-646. The one advisory finding left unfiled is the test-results block shapes in `TEST_RESULTS.md`, an ephemeral artifact deleted with `.ai-work/`.
  - The record was closed by the follow-up pass: 14 items, 9 `fixed`, 4 `ledgered` (td-353 an existing row, td-648, and td-649 for two items), 1 `dropped` (already fixed on the default branch by `3aa7ac84`; the duplicate fix `e7eedc74` was reverted in `4418740c`). A fifteenth item, the answered UQ-01 below, was fixed after the pass (`02f88924`).
- **Out of scope, filed (open at archival):**
  - td-646: mutation survivors in the cleanup check's world-read functions (232 of 705 mutants over about 20 functions).
  - td-647: the Codex principles mirror is a hand copy of the template; generating it is the root fix.
  - td-648: the step loop reads a `Read-only` node entry two ways (the gate as the owner of one node, the commit as a whole outer-loop file), and nothing warns when such a path is also under a step's `Files`.
  - td-649 (severity `important`): the cleanup check passes a directory whose record holds an item under another list marker (`*`, a number, a hyphen without a space) or cannot be read. Both fail open against the record's own rule that a damaged item never passes as done.
  - td-650: nothing in the step loop's driver carries an implementer's `Follow-ups:` line into the record; the reference now tells the orchestrator to copy it.
  - td-353: an existing row, open since 2026-10-08, that one follow-up item pointed at; not edited here.
- **For the user, not ruled here:**
  - UQ-01, answered by the user on 2026-11-12 (fix it so it makes sense everywhere): the researcher's copy of the principle opened "With the representation chosen" with no antecedent, since its kernel carries the principle without Data Structures First. The opening now names its antecedent in the sentence, "Once a building block's data structures are chosen, the next choices of *how*", changed at the source so the philosophy, the three kernels and the Codex copy carry one text (`02f88924`; the frozen guards it moved are re-pinned in `cd6ed5ce`).
  - The widening of the verifier's bar (SQ-04) and the relink that moves the installed always-loaded reading (SQ-02).
  - A paid reading of the spawn-startup tokens of the three roles, offered with the release.
  - The CI-equivalent run on a trial merge with `main`, which the pipeline's pre-mortem placed before the merge is asked for.

## Requirements

Requirements are pipeline-local; never cite their ids in code, tests or docstrings. Each requirement says how it is verified: **outer-loop scenarios** for behaviour-bearing code, **presence check** for text the existing gates already guard.

### Observable Surface

- `claude/config/CLAUDE.md.tmpl` — the philosophy template: the source of the user's global instructions, whose Principles section holds one heading per principle
- `~/.claude/CLAUDE.md` — the user's global instructions, rendered from the template at install; never edited by hand
- `rules/_audience.yaml` — the audience manifest that classifies every heading of the template and the rules for kernel delivery
- `claude/kernels/src/principles-pointer.md` — the principles pointer every kernel carries; today it names the eight principles by hand
- `claude/kernels/principles.md` — the full principles text, generated verbatim from the template
- `python3 scripts/generate_kernels.py --check` — the kernel freshness check: fails when the committed kernels differ from what the sources generate
- `python3 scripts/check_kernel_manifest.py` — the kernel manifest check (I1 to I11, including I4, the 10,000-character cap per kernel string)
- `python3 scripts/check_kernel_manifest.py --liveness` — its liveness mode
- `codex/config/AGENTS.md.tmpl` — the Codex template whose project-baseline region carries a mirror of the principles into every Codex project's instructions
- `cursor/config/export-cursor-rules.py` — the Cursor exporter
- `tests/acceptance/fixtures/project_gating/base_exports.json` — frozen Codex export guard: one digest per exported file
- `tests/acceptance/fixtures/routing_facts/base_codex_agents.json` — frozen Codex export guard: one instructions digest per Codex agent
- `.ai-work/<task-slug>/` — a pipeline's ephemeral task directory
- `FOLLOW_UPS.md` — the follow-up record the user recommended, one per task directory
- `open` — the follow-up state of an item still to be fixed
- `fixed <sha>` — the state of an item fixed in the named commit
- `ledgered td-NNN` — the state of an item that became the named ledger row
- `dropped <reason>` — the state of an item abandoned, with the reason
- `.ai-state/TECH_DEBT_LEDGER.md` — the tech-debt ledger of active rows
- `rules/swe/agent-intermediate-documents.md` — the always-loaded rule that holds the tech-debt summary
- `skills/software-planning/references/tech-debt-ledger.md` — the ledger reference: schema and producer overlays
- `skills/software-planning/references/coordination-details.md` — the pipeline coordination reference, where the pipeline's exit is
- `agents/verifier.md` — the verifier's definition, with its ledger-writing phase
- `agents/implementer.md` — the implementer's definition
- `agents/sentinel.md` — the sentinel's definition
- `agents/architect-validator.md` — the architect-validator's definition
- `python3 scripts/clean_work_safety.py` — the cleanup safety check behind `/clean-work`: classifies each task directory as `BLOCK`, `WARN` or `SAFE`, and exits 1 when any is `BLOCK`
- `/clean-work` — the user's cleanup command
- `BLOCK` — the cleanup classification that refuses deletion
- `WARN` — the cleanup classification that asks for confirmation
- `SAFE` — the cleanup classification that allows deletion
- `--force` — the cleanup override of a `BLOCK`
- `--json` — the cleanup check's machine-readable verdicts
- `scripts/artifact_registry.py` — the registry of pipeline artifacts
- `scripts/test_artifact_registry.py` — the registry's drift test, which checks every consumer's list against the registry
- `HOME=<render-home> python3 scripts/measure_token_budget.py --json --repo-root <checkout>` — the instrument for the always-loaded and listing footprints, with the home pointed at a scratch directory holding the measured checkout's own render
- `python3 scripts/check_agent_prompt_size.py --json` — the instrument for the prompt-size footprint

### Terms

- **The principle** is the heading "Standing on the Shoulders of Giants" and its paragraph, in the user's decided text.
- **The three choosing roles** are the promethean, the systems architect and the researcher.
- **Small** debt meets all seven conditions: one commit touching at most two production files, plus their tests; no design decision and no decision record; no new dependency; no change to acceptance, end-to-end or frozen tests; nothing on the user's ask-first list; no change to a shipped contract (a command-line flag, a hook payload, a canonical block, an agent's return contract); it fits in the current session.
- **A follow-up** is one item of small debt found while solving a task, recorded instead of filed.
- **The follow-up record** is `FOLLOW_UPS.md` in the task directory: one item per line.

### REQ-01: The philosophy carries the principle

**When** the philosophy template is read
**the system** shows, in the Principles section of `claude/config/CLAUDE.md.tmpl`, the heading "Standing on the Shoulders of Giants" directly after Data Structures First and directly before Incremental Evolution, with the user's decided text (polished only for fit, every point kept, each wording change listed for the user), and the user's global instructions gain it only by rendering the template
**so that** the principle's first clause picks up Data Structures First and its stated-reason clause hands over to Incremental Evolution, from one source.

**Verification:** presence check (text; the kernel freshness check already ties the generated principles text to the template).

### REQ-02: The three choosing roles receive the principle through their kernels

**When** a promethean, systems architect or researcher spawn starts, the researcher included although the user's global instructions never reach it
**the system** delivers the principle's full text, verbatim, through that role's kernel; every heading of the template stays classified in `rules/_audience.yaml`; no role outside the three gains the principle's text; every kernel string stays under 10,000 characters; and `python3 scripts/check_kernel_manifest.py` and `python3 scripts/check_kernel_manifest.py --liveness` pass
**so that** the roles that choose techniques and libraries start from the principle without loading the user's file.

**Verification:** presence check on the committed kernels (text; the kernel manifest check and its liveness mode already guard classification, delivery and the cap).

### REQ-03: The principle names in every kernel follow the philosophy's headings

**When** a principle heading is added to, removed from or renamed in the template's Principles section and the kernels are regenerated
**the system** changes the count and the list of principle names in every kernel's principles pointer to match the template's principle headings, in their order, with no hand edit to any source; and while the committed kernels lag the template, `python3 scripts/generate_kernels.py --check` fails
**so that** a tenth principle, a removal or a rename can never drift silently from the names the spawns read.

**Verification:** outer-loop scenarios (behaviour-bearing code): at least an addition, a removal, a rename, and the lagging-kernels failure.

### REQ-04: The other assistants and the hooks-absent floor stay correct

**When** the Codex and Cursor exports are produced, or a session starts with no Praxion hook running
**the system** carries the principle in the principles mirror of the project-baseline region of `codex/config/AGENTS.md.tmpl` (and so in each Codex project's compiled instructions); leaves the Cursor export's content unchanged apart from rule text this change edits, since it carries no principles list; and still gives a session with no hook running the constitution, which now includes the principle, plus the project's own instructions
**so that** no assistant Praxion supports loses the principle or its floor.

**Verification:** presence check (text; the export and hooks-absent tests already guard both surfaces).

### REQ-05: Frozen guards move only where the change moved what they pin

**When** the frozen guards of earlier pipelines, the two frozen Codex export guards among them, are compared after the change with what they pinned at the base
**the system** keeps every pinned digest and every pinned frozen text that this change did not alter at its base value; and holds a new value for one the change altered only where it is re-pinned minimally (that entry alone, nothing beside it), with that guard's own driver, under an answered Spec Question that names the guard, the moved entry and the change that moved it, with base and head compared with their repository roots normalised
**so that** every guard is re-pinned for exactly the changes this pipeline made and keeps biting on everything else.

**Verification:** the existing guards themselves, plus one presence check per moved entry that its answered Spec Question exists.

### REQ-06: Small is defined once and decides what is filed

**When** an agent reads the tech-debt summary in `rules/swe/agent-intermediate-documents.md`, or the ledger reference `skills/software-planning/references/tech-debt-ledger.md`
**the system** states, in one sentence of the summary, that small debt found while solving a task is fixed after the feature rather than filed; and states, in the ledger reference, the seven conditions of *small* (all required) and the rule that a row is filed only for debt that is not small or whose fix could not be finished this session, with the reason in the row, replacing the reference's instruction to file adjacent debt from a Direct-tier fix as a row when that debt is small
**so that** every reader meets one definition and one filing rule, where it decides what to file.

**Verification:** presence check (text; the kernel condensation pin and the rule drift checks already guard the summary).

### REQ-07: The finder records small debt instead of filing it

**When** during a pipeline the verifier finds a debt finding of WARN severity that meets the bar (including a debt note it harvests from the task's learnings), the orchestrator finds small debt, or the implementer meets small debt outside its step
**the system** records it as an `open` follow-up instead of a ledger row: the verifier and the orchestrator add the item to the follow-up record; the implementer reports it in its return, never fixing or filing it, and the orchestrator records it; a FAIL finding, a finding the user overrode and debt that is not small keep their row; and the sentinel and the architect-validator, which find debt with no task at hand, keep filing a row for every finding, their definitions and the instructions they receive unchanged in meaning
**so that** small debt reaches the follow-ups, never the ledger, and the ledger keeps what cannot be fixed now.

**Verification:** presence check in `agents/verifier.md` (its ledger-writing phase) and the instructions its kernel carries, `agents/implementer.md` and the ledger reference; `agents/sentinel.md` and `agents/architect-validator.md` show no change of meaning (text; the kernel and drift gates guard delivery).

### REQ-08: The orchestrator closes every follow-up before the merge or the session's close

**When** a pipeline's feature has its last commit and the merge or the session's close is next
**the system** has the orchestrator take each `open` follow-up in turn and either fix it test-first in its own conventional-typed commit, then run the change's derived test scope, and mark it `fixed <sha>`; or, when it turns out not to be small, file a ledger row with the reason and mark it `ledgered td-NNN`; or mark it `dropped <reason>`; with no extra verifier spawn, and with each follow-up and its outcome named in the closing digest; the orchestrator alone writes these three transitions; a follow-up that would change the feature's behaviour was never small
**so that** small debt is paid in the session that found it, in separate named commits, while the feature's own commits stay surgical.

**Verification:** presence check in `skills/software-planning/references/coordination-details.md` at the pipeline's exit (text).

### REQ-09: Tiers without a task directory keep the same flow

**When** a Direct or Lightweight session finds small debt while solving its task
**the system** holds each follow-up as an item of the session's task list instead of a follow-up record, fixes or files it by the same flow before the session's close, and names each item's outcome in the closing digest
**so that** small debt is fixed rather than filed at every tier.

**Verification:** presence check in the ledger reference and the coordination reference (text).

### REQ-10: Every follow-up is in exactly one of four states

**When** the follow-up record is read
**the system** reads each item line as exactly one of `open`, `fixed <sha>`, `ledgered td-NNN` or `dropped <reason>`, where `open` is the only state an item leaves and the other three are final; an item line it cannot read as one of the four counts as `open`, and so does a final state whose argument is missing or has the wrong shape: an item marked fixed without a commit id in a commit id's shape, an item marked ledgered without a ledger row id in a row id's shape, or an item marked dropped without a reason
**so that** an unfinished or damaged follow-up can never pass as done.

**Verification:** outer-loop scenarios (behaviour-bearing code), through the cleanup check of REQ-11: each of the four states, an unreadable item line, a final state missing its argument, and a final state whose argument has the wrong shape.

### REQ-11: The cleanup check refuses a task directory with an open follow-up

**When** `python3 scripts/clean_work_safety.py` (or `/clean-work`) classifies a task directory under `.ai-work/<task-slug>/`
**and** that directory's follow-up record holds at least one `open` item
**the system** classifies the directory as `BLOCK`, with a reason that names the follow-up record and carries each open item's own description, shows it in the text and `--json` verdicts, and exits 1; a record whose items are all final adds no reason of its own; a directory with no follow-up record is classified exactly as before; and `--force` still overrides a `BLOCK`
**so that** a task directory cannot be cleaned while work found during the task is left undone.

**Verification:** outer-loop scenarios (behaviour-bearing code): one open item among final ones, all final, no record, an open item beside other reasons, and the override.

### REQ-12: The follow-up record is a registered pipeline artifact

**When** the registry's drift test `scripts/test_artifact_registry.py` runs
**the system** finds the follow-up record registered in `scripts/artifact_registry.py` with a cleanup policy that agrees with REQ-11, lists it in every consumer the registry checks (the dashboard's workshop list, the compaction snapshot's document list, the inventory tree in the artifact inventory, and the eval task manifest where the registry places it), passes, and its canaries still fail on an unknown or missing artifact
**so that** the record is discoverable, survives compaction, and no consumer drifts from the registry.

**Verification:** outer-loop scenarios (behaviour-bearing code): the drift test passing with the record, and failing while one consumer omits it.

## Spec Question Answers

The spec phase's four questions use the architect's numbers (SQ-01 to SQ-04). The acceptance design's numbers are written AD-SQ-01 to AD-SQ-32 here (they are SQ-01 to SQ-32 in that stage's `ACCEPTANCE_TESTS.md`). Each answer is the orchestrator's, under the user's standing delegation of 2026-11-06, dated 2026-11-12.

### SQ-01: Does the Codex project baseline get the principle? (REQ-04)

- **Kind:** specification.
- **Evidence:** `codex/config/AGENTS.md.tmpl` carries a hand-kept mirror of the principles in its project-baseline region, which `install_codex.sh` compiles into every Codex project's `AGENTS.md`, Praxion's own root file included. The mirror held seven of the eight principles: Balanced Coupling never reached it.
- **Answer:** yes, the mirror gains the principle inside the first change (the user asked for this check, and the mirror is the constitution a Codex session gets with no hook running). The missing Balanced Coupling is pre-existing drift and becomes the pipeline's first follow-up, with a parity test that binds the mirror's headings to the template's. Generating the mirror from the template stays out of scope. No requirement text changes.

### SQ-02: The always-loaded instrument cannot see a worktree's template change (FC-01)

- **Kind:** specification (footprint measurement).
- **Evidence:** `scripts/measure_token_budget.py` reads `~/.claude/CLAUDE.md`, a link to the main checkout's render. With `HOME` pointed at a scratch home holding a render of the worktree's own template it reads 19,914 (the 4-token gap to 19,918 is the renderer's default profile URL).
- **Answer:** FC-01 is read by the scratch-home method at the base and at the head. The installed reading moves only after the relink, which stays on the user's ask-first list and is named in the merge request. A breach of the 20,400 limit would be a Spec Question, never a cut. No requirement text changes.

### SQ-03: The spawn-startup footprint is declared, not measured

- **Kind:** specification (footprint measurement).
- **Evidence:** the kernels of the three choosing roles grow by 1,066 bytes, which moves the registered spawn-startup-tokens footprint. Its only instrument runs a paid headless session per role.
- **Answer:** declared in Footprints Not Measured; the free 10,000-character kernel cap bounds it. No paid probe is run. A reading of the three roles is offered to the user with the release.

### SQ-04: Do the verifier's harvested debt notes follow the bar? (REQ-07)

- **Kind:** scope.
- **Evidence:** the user names "the verifier for a WARN that meets the bar". The verifier also files rows from the task's `LEARNINGS.md ### Technical Debt` entries at pipeline end and from pre-existing test failures. Left out, these would keep filing small debt and defeat the rule's purpose.
- **Answer:** yes, and surfaced to the user as a widening of their wording. The rule is about debt found while solving a task, whichever phase of the verifier finds it. A FAIL, an overridden survivor and debt that is not small keep their row.

### AD-SQ-01: Frozen guards beyond the two the spec names pin texts this change edits (REQ-04, REQ-05)

- **Raised by:** acceptance design. A probe with a stand-in change turned red the Cursor and kernel fixtures of three earlier pipelines, the resident-text guard and the managed-session guards, none of them named in the spec.
- **Answer:** REQ-05 now applies to every frozen guard of an earlier pipeline that the change moves: each moved entry is re-pinned minimally, that entry alone, with its own driver, under an answered question. No test changed. Requirement text amended: REQ-05.

### AD-SQ-02: The two named Codex guards go red by design (REQ-05)

- **Raised by:** acceptance design.
- **Answer:** both guards stay as they are until the change moves them; then each moved entry is re-pinned alone with the guard's own driver, under its own answered question. No test changed.

### AD-SQ-03: What "a reason that names the open follow-ups" names (REQ-11)

- **Raised by:** acceptance design.
- **Answer:** the reason names the follow-up record and carries each open item's own description. Requirement text amended: REQ-11.

### AD-SQ-04: Whether a final state with an argument of the wrong shape is "missing its argument" (REQ-10)

- **Raised by:** acceptance design. `fixed soon` and `ledgered row-seven` carry an argument that is not a commit id or a ledger row id.
- **Answer:** such an item counts as open, as do a missing argument and a missing reason. Requirement text amended: REQ-10.

### AD-SQ-05 to AD-SQ-32: the frozen guards the change moved (REQ-05)

Each row is one moved entry, re-pinned alone by a test-engineer with the guard's own driver, with the base and head compared with their repository roots normalised. The key-by-key diffs are in the pipeline's re-pin tables (`REPIN_step-6.md`, `REPIN_step-14.md`, `REPIN_follow-ups.md`, deleted with `.ai-work/`).

**Round 1, re-pinned in `a3d6a2f9` (48 entries over nine questions): moved by `4d104cba`, the ninth principle. The generator rewrote the pointer sentence in `core.md`, added the paragraph to `principles.md`, added the module file and re-indexed `index.json`.**

| Id | What moved | Resolved in |
|----|------------|-------------|
| AD-SQ-05 | The generated kernels' digests in `adr_rule_move/base_kernels.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-06 | The generated kernels' digests in `model_routing_move/base_kernels.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-07 | The generated kernels' digests in `project_gating/base_kernels.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-08 | The Codex agent wrappers' digests in `base_exports.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-09 | The Codex agents' instructions in `base_codex_agents.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-10 | The lean spawn's frozen delivery in `base_readings.json` moved with the ninth principle | `a3d6a2f9` |
| AD-SQ-11 | The declared edits gain the new principle's paragraph and the kernel pointer paragraph | `a3d6a2f9` |
| AD-SQ-12 | The lean-spawn guard compares with a commit, not a fixture | `a3d6a2f9` |
| AD-SQ-13 | The principle headings the pointer test checks were sliced by a count | `a3d6a2f9` |

**Round 2, re-pinned in `649ecc7f` (21 entries over thirteen questions): moved by the small-debt change, mainly `191a307d` (the summary sentence and its condensation) and `039a813c` (the verifier's and the implementer's routing).**

| Id | What moved | Resolved in |
|----|------------|-------------|
| AD-SQ-14 | The Cursor export of the intermediate-documents rule in `adr_rule_move/base_cursor.json` moved with the small-debt summary sentence | `649ecc7f` |
| AD-SQ-15 | The Cursor export of the intermediate-documents rule in `model_routing_move/base_cursor.json` moved with the small-debt summary sentence | `649ecc7f` |
| AD-SQ-16 | The Cursor export of the intermediate-documents rule in `routing_facts/base_cursor.json` moved with the small-debt summary sentence | `649ecc7f` |
| AD-SQ-17 | The Cursor export of the intermediate-documents rule in `kernel_pilot/cursor_export.json` moved with the small-debt summary sentence | `649ecc7f` |
| AD-SQ-18 | The generated kernels' digests in `adr_rule_move/base_kernels.json` moved with the small-debt change | `649ecc7f` |
| AD-SQ-19 | The generated kernels' digests in `model_routing_move/base_kernels.json` moved with the small-debt change | `649ecc7f` |
| AD-SQ-20 | The generated kernels' digests in `project_gating/base_kernels.json` moved with the small-debt change | `649ecc7f` |
| AD-SQ-21 | The Cursor export of the intermediate-documents rule in `project_gating/base_exports.json` moved with the small-debt summary sentence | `649ecc7f` |
| AD-SQ-22 | The Codex wrappers of the three ledger-writer roles in `project_gating/base_exports.json` moved with the small-debt change | `649ecc7f` |
| AD-SQ-23 | The Codex instructions of the three ledger-writer roles in `routing_facts/base_codex_agents.json` moved with the small-debt change | `649ecc7f` |
| AD-SQ-24 | The lean spawn's frozen delivery in `base_readings.json` moved with the kernel index | `649ecc7f` |
| AD-SQ-25 | The declared edits gain the small-debt sentence | `649ecc7f` |
| AD-SQ-26 | The summary paragraph of the ledger pair gained a sentence | `649ecc7f` |

**Round 3, re-pinned in `6d22fb2f` (six entries over six questions): moved by `3979aeab`, which scoped the summary sentence to a task.**

| Id | What moved | Resolved in |
|----|------------|-------------|
| AD-SQ-27 | The Cursor export of the intermediate-documents rule moved again in `adr_rule_move/base_cursor.json` | `6d22fb2f` |
| AD-SQ-28 | The Cursor export of the intermediate-documents rule moved again in `model_routing_move/base_cursor.json` | `6d22fb2f` |
| AD-SQ-29 | The Cursor export of the intermediate-documents rule moved again in `routing_facts/base_cursor.json` | `6d22fb2f` |
| AD-SQ-30 | The Cursor export of the intermediate-documents rule moved again in `kernel_pilot/cursor_export.json` | `6d22fb2f` |
| AD-SQ-31 | The Cursor export of the intermediate-documents rule moved again in `project_gating/base_exports.json` | `6d22fb2f` |
| AD-SQ-32 | The declared edit for the small-debt sentence names the reworded sentence | `6d22fb2f` |

### Interpretations taken (stated, not asked)

- **A-01 (REQ-10):** `FOLLOW_UPS.md` is the record's user-fixed name. The line grammar beyond the four state words was the design phase's, and the acceptance designer stated it as a boundary assumption.
- **A-02 (REQ-10):** an unreadable item, or a final state whose argument is missing or misshapen, counts as `open`. The cleanup check fails safe, as it already does for an unknown cleanup policy.
- **A-03 (REQ-11):** a record whose items are all final adds no cleanup reason of its own. Other artifacts in the directory keep their own reasons.
- **A-04 (FC rows):** the test-selection-size footprint is not touched. If a step had changed the test selector's files, the planner would have raised it as a Spec Question.

## Traceability

Rendered from the reconciled `traceability.yml` (single file, no fragments), with the requirement titles from the spec above. Each row lists the unit tests first, then the outer-loop acceptance nodes, then the implementation paths. REQ-05 is held by the existing frozen guards themselves, and its implementation paths are the eleven fixtures the re-pins changed. The requirement-by-requirement status combines the listed nodes with the integration run at `fc4d600a` (`fail=0`) and the guard files' run after the last re-pin (295 passed). REQ-07 was graded WARN by the verifier (meaning kept by inference); the sentence was then scoped to a task in `3979aeab` and the guards it moved were re-pinned at `6d22fb2f`.

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01: The philosophy carries the principle | `tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_the_principle_sits_between_data_structures_first_and_incremental_evolution` | `claude/config/CLAUDE.md.tmpl` | PASS |
| REQ-02: The three choosing roles receive the principle through their kernels | `tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_a_choosing_role_receives_the_principles_full_text_at_spawn[promethean]`<br>`tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_a_choosing_role_receives_the_principles_full_text_at_spawn[systems-architect]`<br>`tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_a_choosing_role_receives_the_principles_full_text_at_spawn[researcher]`<br>`tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_the_audience_manifest_delivers_the_principle_verbatim_to_the_three_roles_alone`<br>`tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_the_kernel_manifest_check_passes_on_this_checkout` | `rules/_audience.yaml`<br>`claude/kernels/principles-prior-art.md` | PASS |
| REQ-03: The principle names in every kernel follow the philosophy's headings | `scripts/test_generate_kernels.py::test_the_principle_headings_are_the_templates_level_three_headings_in_order`<br>`scripts/test_generate_kernels.py::test_the_pointer_in_a_generated_kernel_names_the_templates_principles`<br>`scripts/test_generate_kernels.py::test_a_pointer_whose_markers_are_missing_repeated_or_unfilled_is_refused`<br>`scripts/test_kernel_authored_texts.py::test_the_delivered_pointer_leads_to_a_file_holding_every_principle_it_names`<br>`tests/acceptance/test_principle_names_follow_the_philosophy.py::test_an_added_principle_heading_reaches_every_pointer_in_place_with_the_new_count`<br>`tests/acceptance/test_principle_names_follow_the_philosophy.py::test_a_removed_principle_heading_leaves_every_pointer_with_the_smaller_count`<br>`tests/acceptance/test_principle_names_follow_the_philosophy.py::test_a_renamed_principle_heading_is_named_by_its_new_name_in_every_pointer`<br>`tests/acceptance/test_principle_names_follow_the_philosophy.py::test_the_freshness_check_fails_while_the_committed_kernels_lag_an_added_principle` | `scripts/generate_kernels.py::principle_headings`<br>`scripts/generate_kernels.py::fill_principle_markers`<br>`claude/kernels/src/principles-pointer.md` | PASS |
| REQ-04: The other assistants and the hooks-absent floor stay correct | `tests/acceptance/test_the_giants_principle_reaches_its_readers.py::test_the_codex_project_baseline_carries_the_principle_among_its_principles` | `codex/config/AGENTS.md.tmpl`<br>`AGENTS.md` | PASS |
| REQ-05: Frozen guards move only where the change moved what they pin | `tests/acceptance/test_exports_stay_byte_identical.py::test_every_codex_and_cursor_export_file_is_byte_identical_to_todays`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_every_codex_agents_instructions_but_the_l_tier_agents_are_the_bases` | `tests/acceptance/fixtures/adr_rule_move/base_cursor.json`<br>`tests/acceptance/fixtures/adr_rule_move/base_kernels.json`<br>`tests/acceptance/fixtures/kernel_pilot/cursor_export.json`<br>`tests/acceptance/fixtures/model_routing_move/base_cursor.json`<br>`tests/acceptance/fixtures/model_routing_move/base_kernels.json`<br>`tests/acceptance/fixtures/project_gating/base_exports.json`<br>`tests/acceptance/fixtures/project_gating/base_kernels.json`<br>`tests/acceptance/fixtures/project_gating/base_readings.json`<br>`tests/acceptance/fixtures/project_gating/declared_edits.json`<br>`tests/acceptance/fixtures/routing_facts/base_codex_agents.json`<br>`tests/acceptance/fixtures/routing_facts/base_cursor.json` | PASS |
| REQ-06: Small is defined once and decides what is filed | `tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_the_always_loaded_summary_says_small_debt_is_fixed_rather_than_filed`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_the_ledger_reference_states_all_seven_conditions_of_small`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_the_ledger_reference_files_a_row_only_for_debt_that_is_not_small` | `rules/swe/agent-intermediate-documents.md`<br>`claude/kernels/src/ledger-writer.md`<br>`skills/software-planning/references/tech-debt-ledger.md` | PASS |
| REQ-07: The finder records small debt instead of filing it | `tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_text_that_routes_small_debt_names_the_follow_up_record[agents/verifier.md]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_text_that_routes_small_debt_names_the_follow_up_record[agents/implementer.md]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_text_that_routes_small_debt_names_the_follow_up_record[skills/software-planning/references/tech-debt-ledger.md]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_the_verifiers_kernel_routes_small_debt_to_the_follow_up_record`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_finder_with_no_task_at_hand_is_never_told_to_record_a_follow_up[sentinel]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_finder_with_no_task_at_hand_is_never_told_to_record_a_follow_up[architect-validator]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_ledger_writer_with_no_task_at_hand_gets_no_follow_up_routing_in_its_kernel[sentinel]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_ledger_writer_with_no_task_at_hand_gets_no_follow_up_routing_in_its_kernel[architect-validator]` | `claude/kernels/src/ledger-writer-verifier-overlay.md`<br>`agents/verifier.md`<br>`agents/implementer.md`<br>`skills/software-planning/references/tech-debt-ledger.md` | PASS |
| REQ-08: The orchestrator closes every follow-up before the merge or the session's close | `tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_text_that_routes_small_debt_names_the_follow_up_record[skills/software-planning/references/coordination-details.md]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_the_pipeline_exit_names_every_final_state_a_follow_up_closes_in` | `skills/software-planning/references/agent-pipeline-details.md`<br>`skills/software-planning/references/coordination-details.md` | PASS |
| REQ-09: Tiers without a task directory keep the same flow | `tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_reference_keeps_follow_ups_in_the_task_list_at_the_tiers_without_a_task_directory[skills/software-planning/references/tech-debt-ledger.md]`<br>`tests/acceptance/test_small_debt_is_fixed_not_filed.py::test_a_reference_keeps_follow_ups_in_the_task_list_at_the_tiers_without_a_task_directory[skills/software-planning/references/coordination-details.md]` | `skills/software-planning/references/tech-debt-ledger.md`<br>`skills/software-planning/references/coordination-details.md` | PASS |
| REQ-10: Every follow-up is in exactly one of four states | `scripts/test__follow_ups.py`<br>`scripts/test_clean_work_safety.py`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_lone_follow_up_is_classified_by_its_state[open]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_lone_follow_up_is_classified_by_its_state[fixed <sha>]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_lone_follow_up_is_classified_by_its_state[ledgered td-NNN]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_lone_follow_up_is_classified_by_its_state[dropped <reason>]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_an_item_in_no_known_state_counts_as_open`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_final_state_missing_its_argument_counts_as_open[fixed without a commit]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_final_state_missing_its_argument_counts_as_open[ledgered without a row id]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_final_state_missing_its_argument_counts_as_open[dropped without a reason]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_final_state_missing_its_argument_counts_as_open[fixed with no commit sha]`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_final_state_missing_its_argument_counts_as_open[ledgered with no td row id]` | `scripts/_follow_ups.py` | PASS |
| REQ-11: The cleanup check refuses a task directory with an open follow-up | `scripts/test_clean_work_safety.py`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_one_open_follow_up_among_final_ones_blocks_the_directory`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_the_blocking_reason_names_the_record_and_every_open_follow_up`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_the_text_verdict_shows_the_block_and_the_open_follow_up`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_an_open_follow_up_beside_an_unfinished_plan_adds_its_own_reason`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_record_whose_items_are_all_final_adds_no_reason`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_directory_with_no_record_and_unmerged_learnings_is_warned_as_before`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_a_directory_with_no_record_and_an_unfinished_plan_is_blocked_as_before`<br>`tests/acceptance/test_cleanup_refuses_open_follow_ups.py::test_the_cleanup_command_still_lets_force_override_a_block` | `scripts/clean_work_safety.py` | PASS |
| REQ-12: The follow-up record is a registered pipeline artifact | `tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_registry_places_the_follow_up_record_in_the_task_directory`<br>`tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_follow_up_records_cleanup_policy_is_the_one_a_refusal_agrees_with`<br>`tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_drift_test_passes_on_this_checkout`<br>`tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_drift_test_fails_while_a_consumer_leaves_the_follow_up_record_out[artifact inventory tree]`<br>`tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_drift_test_fails_while_a_consumer_leaves_the_follow_up_record_out[compaction snapshot list]`<br>`tests/acceptance/test_follow_up_record_is_a_registered_artifact.py::test_the_drift_test_fails_while_a_consumer_leaves_the_follow_up_record_out[dashboard workshop list]` | `scripts/artifact_registry.py`<br>`dashboard_app/src/server/artifacts/files.ts`<br>`hooks/precompact_state.py`<br>`skills/software-planning/references/artifact-inventory.md` | PASS |
