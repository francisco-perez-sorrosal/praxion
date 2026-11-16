---
schema_version: 1
report_id: skill-genesis-2026-11-15_17-19-00
generated_at: 2026-11-15T17:19:00
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "11 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 7, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 17:19:00

## Summary

3 queue sources analyzed (each LEARNINGS.md plus VERIFICATION_REPORT.md; no CONSULT fragments exist), 31 items extracted, 7 proposals generated (5 skill/reference updates, 1 claude.md, 1 skill update seedling), 24 deduplicated or skipped. The ten earlier reports of this run were read first (proposal headings); no lesson below repeats one of their proposals, and two extend earlier ones (named in Overlap). Review status: pending.

Interpretation and assumptions: "searched" means a `grep -rIil` over `skills/`, `rules/`, `agents/`, `docs/`, `scripts/CLAUDE.md`, `CLAUDE.md`, `dashboard_app/README.md` and the earlier reports; a lesson is "present" only when a hit states it, not when it merely shares a word. `.ai-state/TEST_TOPOLOGY.md` no longer exists (derived scope replaced it), so the topology lessons are skipped as stale.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| process-economy-k (LEARNINGS + VERIFICATION) | `.ai-work/_harvest/process-economy-k/process-economy-k/` | 11 | Read |
| process-economy-p3-3-lane2 (LEARNINGS + VERIFICATION) | `.ai-work/_harvest/process-economy-p3-3-lane2/` | 9 | Read (LIGHT_REVIEW_STEP2.md not read; its findings are re-checked in the verification report) |
| dashboard-overview (LEARNINGS + VERIFICATION) | `.ai-work/_harvest/dashboard-overview/` | 11 | Read |
| SENTINEL_REPORT / IDEA_LEDGER | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not consulted for content (no overlap found) |
| ADRs | `.ai-state/decisions/` | 0 | Not matched; no decision-pattern candidates |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (no source slug names a cell) |
| Consult fragments | `CONSULT_*.md` | 0 | Not found |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Bare-name call resolves via the defining module's globals; keep a patched callee's callers in the patched module; probe `co_names` | k LEARNINGS + VR patch-seam check | Skill (Proposal 1) | Searched `skills/refactoring/SKILL.md`, `rules/swe/coding-style.md`, `testing-conventions.md`, `python-testing.md`: no hit. Report 16-58-47 covers only mutmut trampolines |
| 2 | Fixture used by 2+ split test files must land in `conftest.py`; node-id identity cannot see it | k LEARNINGS | Skill (Proposal 1) | Searched `testing-conventions.md`, `python-testing.md`: layering only |
| 3 | Module split sized by measured line counts; a 2-file split can miss the ceiling | k LEARNINGS | Skip | Task-specific decision, no recurrence |
| 4 | Survivor dispositions must be probed, not "likely"; a false reason is not a disposition; refuted dispositions do not carry over | k VR #fail-1, #warn-1, #warn-2 | Skill (Proposal 2) | Extends 16-51-16 Proposal 2 (survivor triage) |
| 5 | A documented output object (`wal`) is pinned by one full-equality assertion, not a spot-check | k VR #fail-1 | Skill (Proposal 2) | Same |
| 6 | Mutation sandbox is flat and `.py`-only; a test reading a non-Python fixture dir makes the run `run-failed` | k LEARNINGS | Skill (Proposal 2) | `scripts/mutation_sensor.py` line 413 and `decomposition-guide.md` cover the hook-subprocess case only; the fixture-read case is absent |
| 7 | Bare `KS-N` and `<PIPELINE_DOC>.md` in code evade the id checker; review catches them | k VR #fail-2 | Skip | Present: `rules/swe/id-citation-discipline.md` Identifier Lifecycle Table (the verifier applied it); the checker gap is a tool change, not a lesson |
| 8 | Docstring claims ("every name is imported back", "three callers" then four) must be true | k VR #warn-4 | Skip | `coding-style` Reading Order already the cited criterion |
| 9 | `launched` writer drift vs golden fixture | k LEARNINGS | Skip | Fixed in place; golden-journal tests carry it |
| 10 | Doc pointers must resolve (PROVENANCE names wrong test file) | k VR #warn-3 | Skip | `readme-style` structural integrity |
| 11 | Pre-existing >800-line test file: add new tests in sibling files | k LEARNINGS | Skip | `coding-style` § File Size |
| 12 | `all rostered transcripts None` raises `transcripts-missing`: need two agents to test one empty file | k LEARNINGS | Skip | Narrow, module-specific edge case |
| 13 | Nested `setup-bun` in `claude-code-action` saves a shared cache after the secret-bearing step; pre-install with `no-cache: true` and pass `path_to_bun_executable` | p3-3 VR W-1 | Skill (Proposal 3) | Searched `skills/cicd/references/patterns-and-examples.md` § claude-code-action (pins, triage only): absent |
| 14 | `persist-credentials: false` is undone by the action's agent mode (rewrites `remote.origin.url`) | p3-3 VR F2/W-8 | Skill (Proposal 3) | Same search; only checkout hits |
| 15 | The action's execution file is a pretty-printed JSON array, not JSONL; read the pinned writer before parsing | p3-3 VR W-2 | Skill (Proposal 3) | `grep 'execution.file'`: no hit in skills or rules |
| 16 | Step outputs reach `run:` only through `env:`; a report named with shell metacharacters stays inert | p3-3 VR F7 | Skill (Proposal 3) | Not in `github-actions.md` |
| 17 | `cmd \| head -n 5 \|\| echo fallback` never fires under `bash -e` without `pipefail`; `head` picks the wrong rows | p3-3 VR R-1 | Skill (Proposal 3) | Searched `\|\| echo`: only unrelated hits |
| 18 | Several new report files: orphaned earlier one; `tail -n 1` keeps the completed one | p3-3 VR W-3 | Skip | `agents/sentinel.md` line 421 already states the orphaning; the workflow-specific fix is not reusable |
| 19 | Invariant tests pin the exact expression value and payload shape, not truthiness; one canary per control | p3-3 VR R-2, W-4 | Skill (Proposal 4) | `grep 'truthy\|exact value'`: no equivalent for workflow tests |
| 20 | Predicate/mutator design proven falsifiable on a synthetic known-good parse before the implementation exists | p3-3 LEARNINGS test-engineer | Skip | Instance of the canary discipline in `gate-liveness.md`; folded into Proposal 4 as a one-line example |
| 21 | Read tool grant live from `agents/sentinel.md` frontmatter, not a second constant | p3-3 LEARNINGS | Skill (Proposal 4) | One-line example |
| 22 | Unverifiable runtime risks go to a post-merge checklist, not plan steps | p3-3 LEARNINGS | Skip | Decision of this plan, no recurrence yet |
| 23 | ADR fragment left untracked is lost on merge | p3-3 VR | Skip | `adr-conventions.md` governs fragments; no recurrence |
| 24 | Equal-specificity modifier rules must follow the base rule (defaults first) | dashboard LEARNINGS Steps 6, 8 | claude.md (Proposal 5) | `grep 'equal.specificity'`: none |
| 25 | React recovery from a hydration error strips `<html>` attributes; a server layout cannot import a value from a `"use client"` module; `cache()` memoizes on `Object.is` of arguments | dashboard LEARNINGS Steps 5, 10 | claude.md (Proposal 5) | `grep 'client reference\|Object.is'`: none |
| 26 | Zone-less local stamps: date the page by mtime, label by filename text; pin `TZ` in `vitest.config.ts` with a guard test | dashboard LEARNINGS Steps 10, 13; VR n5 | claude.md (Proposal 5) | `grep 'process.env.TZ'`: none |
| 27 | Build for a browser check from an APFS clone (`cp -cR`) since Turbopack refuses a symlinked `node_modules` | dashboard LEARNINGS Steps 6, 13 | claude.md (Proposal 5) | Only the vitest symlink is in `dashboard_app/README.md:118` |
| 28 | `next dev` hydrates only on `localhost`; free a port with `lsof` | dashboard LEARNINGS | Skip | Present: `dashboard_app/README.md:116` |
| 29 | Rename a key when its meaning splits (tsc enumerates consumers); a rule mirrored to save I/O needs one function; dead fields attract tests | dashboard VR "Merge to LEARNINGS" | Skill (Proposal 6) | `grep 'meaning splits\|one home'`: none in skills |
| 30 | Close a finding by every part of its criterion, not its topic (n8 half, n9 trimmed size) | dashboard VR | Skill (Proposal 7) | `grep 'criterion, not its topic'`: none |
| 31 | `sed -i ''` on macOS; hand-written `section-card` regresses when CSS layer changes; label scanner treats a table wrapper as a count holder; 1.1 MB eval report | dashboard LEARNINGS | Skip | Narrow, one-off or acceptance-driver specific |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Splitting a module that tests patch — keep each patched callee's callers in the patched module, and re-check fixture reach

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-k LEARNINGS (Gotchas: `discover_sources` second patch seam; test-engineer Step 5 `calibration_log_excerpt_path`; Decisions: `_attributed_from_row`) and VERIFICATION_REPORT "Patch-seam completeness" (structural `co_names` probe).
- **Description**: Add a short section to the refactoring guidance. Python resolves a bare-name call through the calling function's own module globals, so after a split a test that patches `module.callee` bites only if every caller of `callee` still lives in `module`; move the callee, keep the callers. Enumerate the callers with an AST walk over `co_names` of every function and nested code object, not by reading the plan's table. For test-file splits, a fixture used by tests landing in two or more files goes to the shared `conftest.py`; a node-id identity diff cannot see a `fixture not found` failure.
- **Rationale**: One pipeline found two such seams that the plan's own table missed, and a verifier built the probe that proves completeness. The failure is silent for isolation-only patches (real git runs). It recurs wherever a large module with patched helpers is split.
- **Estimated scope**: one reference file or a section of `skills/refactoring/SKILL.md`
- **Overlap check**: `skills/refactoring/SKILL.md`, `rules/swe/coding-style.md`, `skills/testing-strategy/references/python-testing.md` (conftest layering only). Earlier report 16-58-47 Proposal 2 covers mutmut trampolines, a different seam.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/refactoring/references/` (new file) or `skills/refactoring/SKILL.md`

### Proposal 2: Mutation survivors — probe the mutant before writing the reason; pin a documented output object whole; keep fixture-dir readers out of the sensor run

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-k VERIFICATION_REPORT #fail-1, #warn-1, #warn-2 (probe table showing five `wal` fields survive); LEARNINGS test-engineer (sandbox flat and `.py`-only, `run-failed: _fixture_sha256_matches_its_recorded_provenance`).
- **Description**: Extend the Mutation Sensor section of `python-testing.md` with three lines. A survivor disposition states the mutant's actual reason after a probe (replace the extraction with `None`, run the tests); "likely" is an unsurfaced assumption and a refuted prior disposition ("unobservable by contract") is not carried over. A field in a documented output envelope is pinned by one full-equality assertion on the object. A test that reads a non-Python fixture directory at run time makes the whole sensor run `run-failed`: put it in its own file and leave it out of `--tests`.
- **Rationale**: The verifier proved the stated residual was wrong and that a one-assertion remedy killed 25 survivors. The sandbox refusal was found live and would recur for any fixture-backed test beside a sensor-tagged step.
- **Estimated scope**: three lines in one reference section
- **Overlap check**: extends 16-51-16 Proposal 2 (survivor triage: equivalent spelling, in-process stand-in); `decomposition-guide.md` line 142 (hook subprocess `run-failed`); `scripts/mutation_sensor.py` docstring. Fold into that proposal at disposition if accepted.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md` § Mutation Sensor

### Proposal 3: Secret-bearing `claude-code-action` jobs — five traps the pinned action sets

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-p3-3-lane2 VERIFICATION_REPORT W-1, F2/W-8, W-2, F7, R-1 (re-verified against the pinned sources).
- **Description**: Add a "secret-bearing job" subsection after "claude-code-action pins". (1) The action's nested `setup-bun` saves `~/.bun/bin/bun` to a cache key shared with other jobs after the agent step: add a pinned `oven-sh/setup-bun` step with `no-cache: true` and pass `path_to_bun_executable: ${{ steps.bun.outputs.bun-path }}`; likewise `enable-cache: false` for `setup-uv`. (2) `persist-credentials: false` does not keep the token out of `.git/config`: agent mode rewrites `remote.origin.url`. (3) The execution file is a pretty-printed JSON array: read the pinned writer before parsing. (4) Pass step outputs to `run:` only via `env:`. (5) `cmd | head || echo fallback` never falls back under `bash -e` without `pipefail`, and `head -n 5` over a patch may drop the row you want: read the row directly and test emptiness explicitly.
- **Rationale**: Each trap was reproduced or read from the pinned source by the verifier, and each passed a green structural test suite. The section already exists for this action, so the fit is exact.
- **Estimated scope**: one subsection (about 20 lines) in an existing reference
- **Overlap check**: `skills/cicd/references/patterns-and-examples.md` § claude-code-action pins and failure triage (pin freshness, cryptic errors only); `skills/cicd/references/github-actions.md` (generic outputs syntax).
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/cicd/references/patterns-and-examples.md`

### Proposal 4: Workflow invariant tests — pin exact values and payload shape, one canary per control

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: process-economy-p3-3-lane2 VERIFICATION_REPORT R-2 (typo `bun_path` passed 38 tests), W-4 (`permissions.allow` inside `--settings` passed 34 tests); LEARNINGS test-engineer (predicate/mutator pairs proven falsifiable on a synthetic good parse; tool grant read live from `agents/sentinel.md`).
- **Description**: A short checklist for tests over a workflow YAML: assert the exact expression for an input that must resolve (not that it is non-empty), assert a JSON payload's key set (`{"env"}` and a subset of the kill-switch names), assert step order and `id`, give each security control a mutator canary, and read a paired list (the agent's tool grant) from its source at test time.
- **Rationale**: Two verifier probes defeated suites that looked complete; the fixes were small and general. One source only, hence sapling.
- **Estimated scope**: one section in a reference
- **Overlap check**: `rules/swe/gate-liveness.md` (canary principle, generic); earlier report 17-16-03 proposals on harness-observable claims. No workflow-specific text.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/cicd/references/patterns-and-examples.md` (next to Proposal 3) or `skills/testing-strategy/references/`

### Proposal 5: `dashboard_app/CLAUDE.md` — dashboard gotchas that cost a verification round

- **Disposition**: pending
- **Type**: claude.md (subdirectory file, loads on demand when `dashboard_app/` is read)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: dashboard-overview LEARNINGS Steps 5, 6, 8, 10, 13 and VERIFICATION_REPORT n1, n4, n5, n7.
- **Description**: Five lines. CSS layers: a modifier that sets the same custom property at equal specificity must come after the base rule (defaults first, modifiers after); a hand-written `section-card` regresses when a later layer changes it. React: client-rendering recovery after a hydration error strips `<html>` attributes (re-apply stored theme on mount); a server layout cannot import a value from a `"use client"` module; `cache()` memoizes on `Object.is` of arguments, so pass primitives. Time: producer stamps are zone-less local text; date a page by file mtime, label by the filename text, and keep `process.env.TZ` pinned in `vitest.config.ts` with a guard test. Browser check: build in an APFS clone (`cp -cR dashboard_app`), because Turbopack refuses a symlinked `node_modules`.
- **Rationale**: Each cost a rework round (the zone and selector findings forced a second and third verification). `dashboard_app/README.md` carries only the dev-origin, port and vitest-symlink notes; these are developer gotchas, not README content. Subdirectory CLAUDE.md keeps them off the launch-time budget.
- **Estimated scope**: new subdirectory CLAUDE.md, about 15 lines
- **Overlap check**: `dashboard_app/README.md:116-118` (dev origin, lsof, vitest symlink: excluded here); `rules/writing/html-output-conventions.md` (architecture only, no CSS or time lessons).
- **Recommended delegation**: context-engineer (placement and token review), then implementer
- **Suggested artifact path**: `dashboard_app/CLAUDE.md`

### Proposal 6: Representation design — rename a key when its meaning splits; give a mirrored rule one home

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: dashboard-overview VERIFICATION_REPORT "Merge to LEARNINGS" candidates and n1, N11, N13 (td-324, td-325); LEARNINGS Step 13 (`reportTimestamp` split into `fileTimestamp` and `runStamp`).
- **Description**: Three techniques for `data-structure-design`: when one field acquires two meanings, split it into two new names so the type checker lists every consumer (never redefine the old key); a rule duplicated in a light and a heavy reader to save I/O is extracted to one pure function rather than held by mirrored tests; before pinning a field in a test, grep for its renderer, since dead fields attract tests.
- **Rationale**: The rename cured an "old key, new meaning" bug class structurally; the other two are the verifier's repeat findings. Single source so far.
- **Estimated scope**: about 10 lines in an existing skill
- **Overlap check**: `skills/data-structure-design` (illegal-state and boundary parsing; not read in full here, grep found no match for the three phrases); `skills/software-design-principles`.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/data-structure-design/SKILL.md` or a reference

### Proposal 7: Dispositioning a verifier finding — quote every part of it into the disposition line

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: dashboard-overview VERIFICATION_REPORT Step 12 dispositions n8 (half-fixed) and n9 (size trimmed, declaration missing); process-economy-k VERIFICATION_REPORT #fail-1 (a false reason is not a disposition).
- **Description**: One line in the rework guidance: a disposition closes a finding by its criterion, not its topic. Copy each clause of the finding into the disposition and mark each closed or open; a two-part finding is half-closed until both parts are.
- **Rationale**: Two carried WARNs in one report were exactly this miss, and it costs a verification round each time.
- **Estimated scope**: one line in `coordination-details.md` or the verifier's rework section
- **Overlap check**: `skills/software-planning/references/coordination-details.md` rework text (not read in detail; grep for the phrase found nothing).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Load skill-crafting; refactoring reference |
| 2 | context-engineer | Consider merging with 16-51-16 Proposal 2 |
| 3 | context-engineer then implementer | cicd reference subsection |
| 4 | context-engineer | Place beside Proposal 3 or in testing-strategy |
| 5 | context-engineer then implementer | Check token cost with `scripts/measure_token_budget.py`; subdirectory file is not always-loaded |
| 6 | context-engineer | Read the skill first; seedling |
| 7 | context-engineer | Seedling |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 7 pending proposals.
- After approval, invoke `context-engineer` for skills and the dashboard CLAUDE.md.
- Proposals 2, 3 and 5 are the strongest; 6 and 7 are single-source seedlings.
