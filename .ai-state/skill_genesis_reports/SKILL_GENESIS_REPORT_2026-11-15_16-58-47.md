---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-58-47
generated_at: 2026-11-15T16:58:47
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "6 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:58:47

## Summary

3 queue sources analyzed (`test-refresh-rework`, `selection-gaps-dogfood`, `gate-liveness-prod`), 28 items extracted, 6 proposals generated, 22 deduplicated or skipped (present in an artifact, fixed in code, ledgered, or folded into a pending proposal of this run), 1 discipline-gap signal recorded. Review status: pending.

Interpretation: the five earlier reports of this run (`16-39-41` to `16-54-03`) already harvested `test-refresh-core`, the parent of `test-refresh-rework`; the rework's parent verification (`VERIFICATION_REPORT_parent.md`) was therefore not re-read, and its findings F1-F6, W1-W10 are covered by `16-54-03` rows 4, 10-13 and 21. Assumption: each proposal below is searched in the repository by the file named in its Overlap check, and by `grep` across `skills/`, `agents/`, `rules/`, `docs/`, `scripts/CLAUDE.md`, `README_DEV.md`.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (test-refresh-rework) | `.ai-work/_harvest/test-refresh-rework/LEARNINGS.md`, `LEARNINGS_implementer_R1.md` | 6 | Read |
| VERIFICATION_REPORT.md (test-refresh-rework) | `.ai-work/_harvest/test-refresh-rework/VERIFICATION_REPORT.md` | 3 | Read; `VERIFICATION_REPORT_parent.md` not re-read (covered by `16-54-03`) |
| LEARNINGS.md (selection-gaps-dogfood) | `.ai-work/_harvest/selection-gaps-dogfood/LEARNINGS.md`, `LEARNINGS_implementer_lane1.md`, `LEARNINGS_implementer_s3_s4.md` | 7 | Read |
| VERIFICATION_REPORT.md (selection-gaps-dogfood) | `.ai-work/_harvest/selection-gaps-dogfood/VERIFICATION_REPORT.md` | 3 | Read |
| LEARNINGS.md (gate-liveness-prod) | `.ai-work/_harvest/gate-liveness-prod/LEARNINGS.md` (merged lane fragments) | 6 | Read |
| VERIFICATION_REPORT.md (gate-liveness-prod) | `.ai-work/_harvest/gate-liveness-prod/VERIFICATION_REPORT.md` | 3 | Read; `REWORK_MANIFEST.md` skimmed |
| CONSULT_*.md fragments | the three source directories | 0 | Not found |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not read (queue batch) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | 0 | Not read (queue batch) |
| ADRs | `.ai-state/decisions/` | 0 | Not consulted; the sources cite their own `dec-draft-*` decisions, which are design records |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_16-39-41.md` to `16-54-03.md` | n/a | Read (proposal titles and triage rows) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A planner tags `mutation: on` on a step the sensor cannot reach (reconciler imports `hooks/` by `sys.path`; the selection probe spawns sessions); the new REQ-10 rule then blocks the step and a user-approved amendment drops the tag | gate-liveness LEARNINGS Step 14, Decisions; VERIFICATION takeover (a), td-310 | Skill (update) | Proposal 1. `decomposition-guide.md:129-149` has no reach check |
| 2 | mutmut keys mutants by module name (a private-alias load stops the run `run-failed`); a trampolined function has no `__globals__` entry; stats phase fails any `cwd=` subprocess; a fresh interpreter on the mutated module as a script fails | gate-liveness LEARNINGS Steps 7-8, 9-10, 11 | CLAUDE.md (scripts) | Proposal 2. `mutation_sensor.py` docstring covers cwd, concurrent runs and in-process logic only; no alias, `__globals__` or script-run text |
| 3 | Disjoint files are not disjoint runtime: a driver that runs the resolver as a subprocess, two sensors on `scripts/`, a lane's uncommitted edit failing another lane's suite | selection-gaps LEARNINGS (planner); gate-liveness LEARNINGS lanes X, Y; test-refresh-rework R1 | Skill (update) | Proposal 3. `decomposition-guide.md:56-62` covers shared knowledge only |
| 4 | A late Spec Question leaves plan `Read-only`, `WIP.md`, and the ADR and design text stale | selection-gaps VERIFICATION warn-3/4/5, merge candidates; gate-liveness VERIFICATION warn-8, FAIL-1 | Skill (update) | Proposal 4. `coordination-details.md:228-230` records the question, not its propagation |
| 5 | A sentence stating a tool's behavior (exit code, process-group kill, adapter placement) shipped in a template, docstring or published contract unprobed | test-refresh-rework VERIFICATION #fail-1; gate-liveness VERIFICATION WARN-7; selection-gaps VERIFICATION `#warn-1` | Skill (update) | Proposal 5. `cross-agent-skill-conventions.md` covers external API docs only |
| 6 | `subprocess.run(timeout=)` kills the direct child, then waits on the pipe a forked grandchild holds; children in their own sessions survive a parent kill | gate-liveness LEARNINGS Steps 9-10, 13; VERIFICATION WARN-7 | Skill (update) | Proposal 6. `grep killpg\|start_new_session` finds nothing in `skills/`, `rules/`, `docs/` |
| 7 | Deletion canaries vacuous against the shared fixture (the declared list names the deleted test, so the run widens) | test-refresh-rework LEARNINGS_R1 | Skip | Class present: `skills/testing-strategy/references/gate-canaries.md:41-45` (watch a canary fail against the broken gate); the shape is one occurrence |
| 8 | Tool availability is not a `PATH` question for npm (`node_modules/.bin`) | test-refresh-core LEARNINGS Step 5 | Skip | Already a Skip row in `16-54-03` (21); fixed in code |
| 9 | Mutation-tag scan must end a step at any heading (FAIL-2) | gate-liveness VERIFICATION FAIL-2, merge candidate | Skip | Present: `agent-pipeline-details.md:328` (a level-2 non-step heading closes the block); fixed in code |
| 10 | A planned outer-loop re-mark still needs its Spec Question record (FAIL-1) | gate-liveness VERIFICATION FAIL-1 | Skip | Present: `coordination-details.md:230` (Orchestrator-made amendments) |
| 11 | Exit 5 never fires with a coverage floor (pytest exits 1) | test-refresh-rework VERIFICATION #fail-1 | Skip | Fixed: `claude/project-baseline/tests/test.yml.tmpl:50-67` runs `--collect-only` first; the general lesson is Proposal 5 |
| 12 | An acceptance-design driver naming a protected token broke the private-reader scan test; fix is an allowlist entry in Step 1 | gate-liveness LEARNINGS Gotchas | Skip | Same class as pending `16-51-16` Proposal 1 (a new file trips a repo-wide scan); plan-specific |
| 13 | A listed `Files:` entry that does not change keeps a step from `verified-complete` | gate-liveness LEARNINGS Gotchas; selection-gaps LEARNINGS Gotchas | Skip | Folds into pending `16-42-24` Proposal 1 (same `Files:` paragraph) |
| 14 | On Praxion the `unmapped-path` backstop never fires for a tracked file; test-held fixture literals map everything | selection-gaps VERIFICATION, Step 7 notes | Skip | Praxion measurement; td-296 note applied (`cc13bff4`) |
| 15 | Orchestrator absorbed four implementer-sized steps (and authored SQ-02) to save a spawn; verdict under-calibrated | gate-liveness VERIFICATION Calibration; selection-gaps VERIFICATION Calibration | Skip | Calibration verdict is already recorded; a sequencing judgement, two pipelines, no testable rule |
| 16 | Orchestrator amended a user-verbatim Key Signal (the 9 KB prompt shrink) | test-refresh-rework VERIFICATION `#warn-3` | Skip | One occurrence; surfaced by the verifier, which is the existing mechanism |
| 17 | `payload.get("cwd", ".")` drops the gate fire when the key is absent | gate-liveness VERIFICATION WARN-3 | Skip | Single call site; rework row 4 |
| 18 | A test that executes `sitecustomize` in-process installs a permanent audit hook that pollutes every later test on the xdist worker | gate-liveness LEARNINGS Step 13 | Skip | One occurrence, narrow to the tracer; fix named in the source |
| 19 | Three slug parsers diverge | selection-gaps LEARNINGS Tech-Debt Row Requests | Skip | Ledgered td-298 |
| 20 | Selection-size baseline method has no committed script | selection-gaps LEARNINGS | Skip | Ledgered td-299 |
| 21 | Ownership adapters (maven, gradle, nx, turbo, pants) unverified on deleted or non-module paths | selection-gaps; test-refresh-rework LEARNINGS_R1 | Skip | Ledgered td-297 |
| 22 | Reason-string survivors drop when the tests pin the full reason text | gate-liveness LEARNINGS Steps 9-10 | Skip | Same lesson as pending `16-42-24` Proposal 2 and `16-45-03` Proposal 2 |
| 23 | Harness worktree isolation refuses heredocs naming `git`/`github.token` | gate-liveness LEARNINGS; test-refresh-rework LEARNINGS_R1 | Skip | Present: `docs/claude-code-limitations.md:11` |
| 24 | Pre-commit pins an older ruff than the local one; format with the pinned version | selection-gaps LEARNINGS Gotchas | Skip | Present: `.pre-commit-config.yaml:65-70` |
| 25 | `\S+` truncates pytest ids with embedded spaces in a `-v` parser | test-refresh-rework LEARNINGS Step 13 | Skip | The equivalence guard was descoped with Step 14 |
| 26 | Hub sparse checkout inside the workspace is collected by pytest and widens the resolver | test-refresh-rework LEARNINGS Step 11 | Skip | Specific to `test-scheduled.yml.tmpl`; stated in the template |
| 27 | Seed-then-prune of `tests/declared-deps.toml`; glob engine crashed on arbitrary literals | test-refresh-rework LEARNINGS Steps 4, 7 | Skip | Dataset and code specific; fixed in code |
| 28 | Recurring need for a specialist who probes CI and runner-toolchain semantics | W10, WARN-7, `#warn-1` above | Discipline-gap | Recorded below, not acted on |

## Discipline-Gap Signals

Recorded for human disposition only -- this agent never proposes a discipline, drafts a registry row, or instantiates one.

| # | Signal (what specialist voice was missing) | Decision it would have changed | Where it recurred | Times seen |
|---|---|---|---|---|
| 1 | Runner and CI toolchain semantics: what pytest-cov, pnpm/vitest, `subprocess` and the Maven/Gradle/nx/turbo/pants adapters actually do under a flag combination | Whether the template's exit-5 branch, the `pnpm test --` junit step, the adapter-placement sentence and the CLI's timeout docstring shipped as written | test-refresh-rework (`test.yml.tmpl`), selection-gaps (`test-selection.md` Widening), gate-liveness-prod (`check_gates_bite.py`); `16-54-03` row 11 (`pnpm test --`) | 4 |

Proposal 5 is the process remedy available without a new discipline (probe the tool once). The registry (`skills/multi-perspective-analysis/references/discipline-registry.md`) carries `statistician`, `evidence-appraiser` and `data-structure-specialist`; none fires on a local tool's runtime behavior.

## Proposals

### Proposal 1: Check that the sensor can reach a target before tagging a step `mutation: on`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: gate-liveness-prod `LEARNINGS.md` Step 14 ("Step 14 is BLOCKED by its own rule": the reconciler does `sys.path.insert(0, SCRIPT_DIR.parent / "hooks")`, so the sensor's flat copy raises `ModuleNotFoundError`, `run-failed`); Decisions and `VERIFICATION_REPORT.md` takeover (a) (Step 13 dropped to `off` by a user-approved amendment, td-310); Step 7 ("Whether mutmut can mutate package modules that import siblings is unproven").
- **Description**: In `decomposition-guide.md § mutation: on / mutation: off`, add a pre-tag reach check the planner runs: the target and its test sit in one directory; the target imports nothing by `sys.path` into a sibling tree (`hooks/`); no test starts the target as a subprocess or from another working directory; a slow target gets `--timeout` in the plan. A target that fails the check is tagged `off` with the reason written in the plan, or its logic moves into a leaf module the sensor reaches.
- **Rationale**: `python-testing.md:229` now blocks a tagged step on any refusal but `not-flat-layout`, so a `run-failed` on a tagged step costs a plan amendment and, here, a user approval. The planner field is the only point where the cost is nil. Four pipelines have hit a structural `run-failed` (this one, plus the step-schema and process-principles rows in `16-45-03`).
- **Estimated scope**: one paragraph in one reference
- **Overlap check**: `skills/software-planning/references/decomposition-guide.md:129-149` (tag criteria, no reach check); `skills/testing-strategy/references/python-testing.md:221-233` (consequence of a refusal, not the pre-check). None duplicates it.
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 2: Tests written for the mutation sensor load the module by its real name and start no process

- **Disposition**: pending
- **Type**: claude.md (subdirectory `scripts/CLAUDE.md`)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: gate-liveness-prod `LEARNINGS.md` Step 8 and 12 lane X ("mutmut keys mutants by module name": a `spec_from_file_location("tracer_under_test", ...)` alias stops the run `run-failed` with "tests recorded trampoline hits but none match any mutant key"; `rts.derive.__globals__["Graph"]` is a `KeyError` because the function is a trampoline; the stats phase reads the cwd's `pyproject.toml`, so a subprocess with `cwd=<temp>` fails); Steps 7-8 lane C-D (a fresh interpreter on the mutated module as a script fails: use `runpy.run_path(..., run_name="__main__")`; `multiprocessing` spawn children fail the same way); Steps 9-10 lane Y (flat target beside a subpackage: sibling modules by package name, run with `PYTHONPATH=<repo>/scripts`).
- **Description**: Add four lines to the `mutation_sensor.py` bullet group in `scripts/CLAUDE.md`: load the module under test by its real name, never a private alias; patch a class attribute, not a trampolined function's `__globals__`; pass no `cwd=` to a subprocess in a test and address everything by absolute path; run a script entry point in-process with `runpy`. Add the sibling-import form with `PYTHONPATH`.
- **Rationale**: Each cost a `run-failed` read as a tooling fault, the same diagnosis trap as the parent-counting bullet already there. Single pipeline but five independent observations by three lanes; any new `scripts/` module with a tagged step meets them.
- **Estimated scope**: CLAUDE.md edit (about five lines)
- **Overlap check**: `scripts/CLAUDE.md:102-103` (imports of another test module, parent counting); pending `16-39-41` Proposal 4 (source-reading meta-tests), same bullet group, apply together; deferred 2026-10-10 Proposal 4 (script-run subprocesses and `__file__` lookups, "fold into the R7P3 edit if built"); `scripts/mutation_sensor.py:15-23` (cwd limit only).
- **Recommended delegation**: user (claude.md), context-engineer to confirm placement
- **Suggested artifact path**: `scripts/CLAUDE.md`

### Proposal 3: Disjoint files are not disjoint runtime — serialize lanes that run or scratch the same thing

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: selection-gaps-dogfood `LEARNINGS.md` Decisions (planner: resolver steps serialized because "the acceptance driver runs the whole resolver as a subprocess, and every resolver-file step widens its inner loop to the full suite"); gate-liveness-prod `LEARNINGS.md` lanes X and Y ("both lanes point the sensor at `scripts/`: two runs at once refuse `pyproject-present` / `mutants-dir-present`"; the long run's `scripts/mutants/` turned two registry tests red in the shared checkout; a transient `scripts/gate_probes/pyproject.toml` read as a pocket root gave 30 phantom differences in a resolver measurement); test-refresh-rework `LEARNINGS_implementer_R1.md` (three suite failures belonged to a concurrent implementer's uncommitted edit, `preexisting=3`).
- **Description**: In `decomposition-guide.md § Shared Contracts Before Parallel Lanes`, add a second family beside shared knowledge: two parallel lanes must not share a runtime. Name the cases: a lane whose gate runs a component the other lane edits (an outer-loop driver that executes the system under change; a selector that widens the inner loop to the full suite), and a lane that writes a transient tree the other's scans read (a sensor on one directory, a scratch copy). Remedy: serialize those steps, or give each lane its own target directory.
- **Rationale**: Three pipelines paid for it in red runs that read as regressions. The existing section stops at shared contracts; the planner has no prompt to ask "what does each lane's gate execute".
- **Estimated scope**: one paragraph and a golden bad-case line
- **Overlap check**: `decomposition-guide.md:56-62` (shared contracts), `agent-pipeline-details.md:52` (one committer at a time, commits only), `skills/test/SKILL.md:26` (leave the files a run reads alone while it runs, single lane). Pending `16-51-16` Proposal 1 covers a scratch copy tripping scan gates, adjacent.
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 4: A late Spec Question updates the records that restate the changed rule

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: selection-gaps-dogfood `VERIFICATION_REPORT.md` `#warn-3`, `#warn-4`, `#warn-5` and its merge candidate ("A late Spec Question has to update four records together: plan `Read-only`, `WIP` Blockers, `traceability.yml`, and the ADR/SYSTEMS_PLAN design text"); gate-liveness-prod `VERIFICATION_REPORT.md` WARN-8 (`WIP.md` narrative at "Step 1 of 26" after 27 steps) and WARN-9.
- **Description**: Extend the `Late path` bullet in `coordination-details.md` with the propagation list: the plan's `Read-only` ownership of removed and added nodes (98 owned, 99 existing), `WIP.md` Blockers and current position, `traceability.yml` (the planner already re-syncs `acceptance:`), and the ADR draft and `SYSTEMS_PLAN.md` text that restate the changed rule. The ADR draft is the durable one: it carried the pre-amendment rule to the merge.
- **Rationale**: The existing text records the question and its commit, then stops. Two pipelines left stale records, and one left a durable ADR contradicting the code; the verifier found them only at the end.
- **Estimated scope**: two sentences in one bullet
- **Overlap check**: `coordination-details.md:228-230`; `agents/implementation-planner.md:242` (re-sync of `acceptance:` only). Triage row 30 of `16-51-16` skipped the general "documents drift after late commits"; this is the Spec Question case with a named list.
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 5: A tool behavior written into a template, docstring or published contract is probed first

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: test-refresh-rework `VERIFICATION_REPORT.md` `#fail-1` (a template comment says an empty project exits 5; with a coverage floor pytest exits 1; reproduced with pytest-cov 7.1.0; no test referenced the template); gate-liveness-prod `VERIFICATION_REPORT.md` WARN-7 (a docstring says a timeout kills the probe "together with whatever it started", false for children in their own sessions); selection-gaps-dogfood `VERIFICATION_REPORT.md` `#warn-1` (the published Widening paragraph says nx, turbo and Pants "place a deleted path by its directory", true only for Maven and Gradle).
- **Description**: Add a short section to `cross-agent-skill-conventions.md` beside the external-docs rule: a sentence that states how a local tool behaves (an exit code, a flag interaction, a kill scope, where an adapter places a path) is run once before it ships, in the case the sentence is about (empty project, flag pair, forked child), and the command stays in the nearby comment or the step's results. Without a run, the sentence says "not probed" or is left out.
- **Rationale**: Three verifiers tagged the same `[UNSURFACED-ASSUMPTION]` in three pipelines, each in text a reader trusts (a template comment, a docstring, the published contract). The existing section handles documentation drift for external APIs; a local tool's runtime behavior is not covered.
- **Estimated scope**: one section, about six lines
- **Overlap check**: `skills/software-planning/references/cross-agent-skill-conventions.md` (external API docs, library versions); pending `16-45-03` Proposal 1 (a copied lesson can be false; a different artifact and file); pending `16-51-16` Proposal 3 (re-derive a proof as written). Dispose with `16-45-03` Proposal 1, they share a test: "did anyone run it".
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/software-planning/references/cross-agent-skill-conventions.md`

### Proposal 6: A bounded subprocess that may fork runs in its own session and is killed by group

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: gate-liveness-prod `LEARNINGS.md` Steps 9-10 ("a forking `sh -c` kept the output pipe open and stalled `subprocess.run` for the child's whole life"; each command now runs in its own process group); Step 13 (the selection probe's children run in their own sessions); `VERIFICATION_REPORT.md` WARN-7 (a CLI-level SIGKILL orphans the traced suite, the td-310 shape; mitigated only by the probe's own shorter limit).
- **Description**: Add a short note to the python-development scripting reference: `subprocess.run(timeout=)` kills the direct child and then waits on the pipe, so a forked grandchild stalls it; start such a command with `start_new_session=True` and kill the group (`os.killpg`). State in the docstring which processes a timeout reaches, because children in another session survive a parent kill.
- **Rationale**: The gotcha cost a stalled probe and an orphaned suite in one pipeline and a false docstring in its CLI. One pipeline, two sites, so seedling; it may be deferred until a second occurrence.
- **Estimated scope**: one reference paragraph
- **Overlap check**: `scripts/CLAUDE.md:101` (background list ignores SIGINT; shell supervision, not Python `subprocess`); `skills/python-development/references/libraries-scripting.md:8` (a thin wrapper, no timeout text). `grep -rn "killpg\|start_new_session"` over `skills/`, `rules/`, `docs/`, `agents/` finds only unrelated lines.
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/python-development/references/libraries-scripting.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Skill update; load `skill-crafting`; same file as Proposal 3, one edit pass |
| 2 | user (claude.md), context-engineer review | Apply with pending `16-39-41` Proposal 4; measure the token delta only if root `CLAUDE.md` is touched (it is not) |
| 3 | context-engineer then implementer | Same file as Proposal 1 and pending `16-51-16` Proposal 1 |
| 4 | context-engineer then implementer | Same bullet as the late-path text; one paragraph |
| 5 | context-engineer then implementer | Dispose with pending `16-45-03` Proposal 1 |
| 6 | context-engineer then implementer | Seedling; may be deferred until a second occurrence |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals.
- Proposals 1 and 3 edit the same file (`decomposition-guide.md`); apply them in one pass, with pending `16-51-16` Proposal 1.
- Review the discipline-gap signal (runner and CI toolchain semantics) as a human decision; no registry row was drafted.
- Not harvested here: the unread `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `RESEARCH_FINDINGS.md` and light reviews of the three sources (design records, covered by their `dec-draft-*` ADRs).
