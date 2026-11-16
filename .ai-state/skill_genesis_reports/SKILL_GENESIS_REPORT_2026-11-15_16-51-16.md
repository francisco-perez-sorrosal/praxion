---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-51-16
generated_at: 2026-11-15T16:51:16
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "4 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:51:16

## Summary

5 queue sources analyzed (13 documents read), 31 items extracted, 5 proposals generated, 26 deduplicated or skipped. Earlier reports of this run (16-39-41, 16-42-24, 16-45-03) were read first; none of their 9 proposals is repeated (the nearest, the pending lesson-vs-tool check, is a different point from proposal 3 below). Review status: pending.

Interpretation and assumptions: the memory-to-artifacts and handoff batches moved about 160 process lessons into artifacts, so each candidate was grepped across `skills/`, `agents/`, `rules/`, `docs/`, `scripts/CLAUDE.md`, `README_DEV.md` and `claude/canonical-blocks/` before it was kept. The two Sep-26 `rework-*` dirs and `rework-p03` carry no VERIFICATION_REPORT with new content beyond what is listed; the `CONSULT_*` fragments do not exist in any source.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| memory-to-artifacts LEARNINGS | `.ai-work/_harvest/memory-to-artifacts/LEARNINGS.md` | 14 | Read |
| memory-to-artifacts VERIFICATION_REPORT | `.ai-work/_harvest/memory-to-artifacts/VERIFICATION_REPORT.md` | 5 | Sampled (Recommendations, Merge to LEARNINGS, Delta D6-D9; first-pass tables and the Memory Pass M1-M6 detail skipped; its merge candidates were already folded into LEARNINGS) |
| routing-facts LEARNINGS | `.ai-work/_harvest/routing-facts/LEARNINGS.md` | 4 | Read |
| routing-facts VERIFICATION_REPORT | `.ai-work/_harvest/routing-facts/VERIFICATION_REPORT.md` | 3 | Sampled (Recommendations, Merge candidates, Delta Re-verification) |
| rework-observation-log-adr-doc-accuracy | `.ai-work/_harvest/rework-observation-log-adr-doc-accuracy/LEARNINGS.md` | 3 | Read (VERIFIER_FINDINGS not in scope) |
| rework-observation-log-writer-truth-gate | `.ai-work/_harvest/rework-observation-log-writer-truth-gate/{LEARNINGS,VERIFICATION_REPORT}.md` | 3 | Read / Sampled (disarm table, merge candidate) |
| rework-p03-reader-unreachable | `.ai-work/_harvest/rework-p03-reader-unreachable/LEARNINGS.md` | 1 | Read |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_*.md` | n/a | Read (dedup) |
| SENTINEL / IDEA_LEDGER / ADRs / calibration log | n/a | 0 | Not consumed: queue mode, the sources are the parked directories |
| Consult fragments | `CONSULT_*.md` | 0 | Not found |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A repo-wide scan test (writer-importer inventory) went red on the scratch copies under `tmp/disarm/` the disarm procedure prescribes; bit the implementer and the verifier | writer-truth-gate LEARNINGS, VERIFICATION | Skill (update) | Proposal 1. `skills/testing-strategy/references/gate-canaries.md:41-45` prescribes the disarm but not this collision; grep `tmp/disarm`, `scratch cop` found only an unrelated python-development line |
| 2 | Hook modules share `sys.modules["_observation_log.writer"]`, not `hooks._observation_log.writer`; a patch on the package copy reached 0 of 3 writers | writer-truth-gate LEARNINGS | Skill (update) | Proposal 2. grep `sys.modules`, `patch target`, `monkeypatch` in `skills/hook-crafting`, `python-development`, `testing-strategy`: no match |
| 3 | Proof resting on a cited figure, grep or machine state: re-run as written, read with the command that sees the whole state, state a figure with its definition (13 of 61 citations moved; a grep that did not reproduce; `git config --global` missed an included file; "218" was 240/241) | memory-to-artifacts LEARNINGS (verifier + orchestrator), adr-doc-accuracy LEARNINGS | Skill (update) | Proposal 3. `merge-worktree/SKILL.md:32` carries `--show-origin` for rerere only; `evidence-appraisal` covers borrowed external claims, not our own records |
| 4 | A classifier that short-circuits on the common case: a green verdict over real data never exercises the secondary reader; print the parsed intermediates | routing-facts VERIFICATION (B-1, F-1) | Skill (update) | Proposal 4. grep `intermediate values`, `short-circuit` in `skills/`, `agents/verifier.md`: no match |
| 5 | An `affected_files` glob (`hooks/_observation_log/*`) reads dead; the directory-prefix form is live | adr-doc-accuracy LEARNINGS | Skill (update) | Proposal 5. Checked in code: `scripts/check_adr_frontmatter_promotion.py:265-274` `_is_live` resolves a trailing-slash entry as a directory and anything else with `exists()`. `adr-authoring-protocols.md:21` names ephemeral paths and placeholders, not globs |
| 6 | Consumer re-parses a producer's field grammar with a looser pattern and diverges both ways; use one reader | routing-facts VERIFICATION F-1 | Skip | Same lesson as 16-42-24 item 14, carried by the one-definition principle in `software-design-principles`; the fix was built (`_step_routing` uses `_plan_steps.parse_plan_steps`) |
| 7 | Footprint `final` row goes stale after a later commit; re-take at the head | memory-to-artifacts VERIFICATION, LEARNINGS | Skip | Present: `skills/spec-driven-development/references/footprint-criteria.md:54` |
| 8 | Orchestrator note in the spec must pass `extract_spec.py --check` (code-span sha is design vocabulary) | memory-to-artifacts VERIFICATION F-D2 | Skip | Present: `coordination-details.md:230` (orchestrator-made amendments) |
| 9 | Sha-keyed post-merge procedure must survive the rebase; record sha plus subject | memory-to-artifacts VERIFICATION | Skip | Plan-specific, fixed in the plan (step 5); one occurrence; `merge-worktree/SKILL.md` already covers rebase traps |
| 10 | Interim text written against an open ledger row must be re-checked when it lands (P-044) | memory-to-artifacts VERIFICATION W-D8a | Skip | Pending 16-45-03 Proposal 1 (interim text apart, date what was seen once) covers it; note the overlap there |
| 11 | rerere / updateRefs traps; scratchpad shared by concurrent pipelines; zsh no word-split | LEARNINGS Gotchas | Skip | Present: `merge-worktree/SKILL.md:32`, `agent-pipeline-details.md:131`; user memory carries the zsh point (pending 16-39-41 Proposal 3) |
| 12 | Bare `python3 -m pytest` fails without xdist; use `uv run pytest` | memory-to-artifacts LEARNINGS | Skip | The source says P-098 moved it into `README_DEV.md` |
| 13 | Lanes: one implementer per step in its own worktree; told "another gate run is using this machine", the lane ran only its Check | memory-to-artifacts LEARNINGS (orchestrator) | Skip | One pipeline, orchestrator practice; grep for load/contention wording in `skills/software-planning`, `skills/step-loop`, `agents/implementer.md` found nothing, so a seedling to watch for a second occurrence |
| 14 | `Files:` entry with `*?[` stops the driver `files-glob` | memory-to-artifacts LEARNINGS | Skip | Driver stop, carried by `skills/step-loop/references/stop-recoveries.md` |
| 15 | Text step's Check is the real-tree guards for its file class; no per-lesson presence test | memory-to-artifacts LEARNINGS | Skip | Decision of this plan (KS-09); no recurrence |
| 16 | Parallel waves do not commit inside a wave (pre-commit stash wipes a running agent's edits) | memory-to-artifacts LEARNINGS | Skip | Plan assumption; one occurrence |
| 17 | Edit the canonical block, not the fenced copy in `co`/`cop` | memory-to-artifacts LEARNINGS | Skip | Present: root `CLAUDE.md` (Update content shipped into managed projects) |
| 18 | Verifier-flagged: report green `TEST_RESULTS.md` sections under 1,024 bytes | routing-facts VERIFICATION C-6 | Skip | Ledgered td-353; the shape gate reports it |
| 19 | Reversal trigger names a reader (sentinel routing audit) that does not exist | routing-facts VERIFICATION D-1 | Skip | Covered by `gate-liveness.md` (a named consumer for every gate output); filed td-558 |
| 20 | `chmod 000` canaries run only as non-root; verified CI has no `container:` | rework-p03 LEARNINGS | Skip | One occurrence, the check was made and recorded; `grep geteuid\|as root` found no shipped note, a seedling for the next permission canary |
| 21 | Reader failure is skipped `reader-unreachable` (P03) vs `wal-unreadable` exit 2 (instruments); no shared strict helper | rework-p03 LEARNINGS | Skip | Design decisions of this change; dec-380's tagged union is the rationale |
| 22 | RED-first by patch round-trip instead of checking out an old commit | rework-p03 LEARNINGS | Skip | Covered in substance by `gate-canaries.md:41-45` (save bytes, break by script, restore) |
| 23 | Dropped a row-count assertion: redundant with the checker and masked the specific violation | writer-truth-gate LEARNINGS | Skip | One occurrence; ordinary test-design advice |
| 24 | Disarm outcomes reproduced as predicted; suspension `agent_stop` omits usage fields | writer-truth-gate LEARNINGS | Skip | Run record and design pin, not reusable |
| 25 | Verifier warns `TASK_BRIEF` absent on a Lightweight rework; the gate wording has no rework carve-out | writer-truth-gate VERIFICATION | Skip | Verifier-gate wording defect, not a skill; the tool-side fix belongs to a tech-debt row, not to genesis |
| 26 | Verifier corpus figure; `REWORK_MANIFEST` note contradicts `VERIFIER_FINDINGS` (findings authoritative) | adr-doc-accuracy LEARNINGS | Skip | The second half is a stale manifest note, specific; the first half is Proposal 3 |
| 27 | Index budget one owner `IndexSize(40, 5000)`; commit gate re-routes checker stdout to stderr | memory-to-artifacts LEARNINGS | Skip | dec-512 and code |
| 28-31 | Resident restated in list form, `DriverRequest.implied`, doc-engineer `model:` comment, step sequencing and ownership maps, FC-01 limits, td rows | routing-facts LEARNINGS | Skip | ADR draft `dec-draft-47003576`, code or plan-specific; generated-plan pattern is one occurrence |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: A disarm scratch copy under `tmp/` trips every repo-wide scan gate

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/rework-observation-log-writer-truth-gate/LEARNINGS.md` Implementer Notes ("`tmp/disarm/` scratch copies must be deleted before the final `hooks/` gate run"); same dir `VERIFICATION_REPORT.md` (reproduced: two totalising tests went red with the verifier's scratch copies under `tmp/`, green after cleanup; "bitten twice"; Merge candidate: "source gate inputs from git's view of the tree, not from the filesystem").
- **Description**: In the canary-vacuity procedure of `gate-canaries.md`, add one gotcha: a disarm run done in a scratch copy under the repository (`tmp/`, `.ai-work/`) is picked up by any gate that scans the whole tree (`rglob` totalising tests, writer-importer inventories); delete the copies before the final gate run, and when authoring such a gate take its file set from `git ls-files` (tracked files) rather than the filesystem.
- **Rationale**: Two independent hits in one rework (implementer, then verifier), and the cause is the very procedure the reference prescribes, so every canary author who disarms in a scratch copy meets it. The failure reads as a real gate finding, not a stray-file problem.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md:41-45` (disarm procedure; in-place break, no scratch-copy variant). Searched `skills/`, `agents/`, `rules/`, `docs/` for `tmp/disarm`, `scratch cop`, `git ls-files`: no match on this point.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 2: Patch the module object the hook loaded, not the dotted package name

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `rework-observation-log-writer-truth-gate/LEARNINGS.md` Assumptions ("The patch-target rule is confirmed by probe": the three hooks share `sys.modules["_observation_log.writer"]`, which is not `hooks._observation_log.writer`; a wrapper on the hooks' copy reached 3 of 3 writers, on the package copy 0 of 3); `VERIFICATION_REPORT.md` SC-4 and the retarget disarm (4 canaries went red).
- **Description**: A testing note for hook code that imports a sibling package by its bare name: tests must patch the object in `sys.modules` under the bare name the hook sees (and assert identity of that object across the hooks), because importing it under the dotted `hooks.` name makes a second module copy that no hook calls. A patch on the wrong copy passes silently and tests nothing.
- **Rationale**: The failure is silent and the dual-copy hazard is generic to the hook layout, not to the observation log. One pipeline, so seedling; the probe and the disarm give it an unusually firm evidence base.
- **Estimated scope**: a few lines in an existing reference (hook testing) or one gotcha line
- **Overlap check**: none. Searched `skills/hook-crafting`, `skills/python-development`, `skills/testing-strategy` for `sys.modules`, `patch target`, `monkeypatch`, `lazy import`: no match.
- **Recommended delegation**: context-engineer (placement: `hook-crafting` vs `testing-strategy`)
- **Suggested artifact path**: `skills/hook-crafting/references/` (an existing testing reference if one exists), alternative `skills/testing-strategy/references/python-testing.md`

### Proposal 3: A proof resting on our own record is re-derived as written, from the whole state, with its definition

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `memory-to-artifacts/LEARNINGS.md` Verification Patterns Merged: "A grep recorded as evidence must be re-run once as written" (four message pieces had no search, one did not reproduce); "A proof that rests on machine state is re-read with the command that sees the whole state" (`git config --global` missed an included file and one setting local to the repo; `git config --show-origin --get-regexp` showed both; two lessons wrongly called superseded); "A proof by cited line numbers decays" (13 of 61 citations moved by the pipeline's own batches; check the verified lines still exist word for word instead of re-opening each number). `rework-observation-log-adr-doc-accuracy/LEARNINGS.md` Gotchas: a verifier figure "218 share a token tuple" did not reproduce (240/241 by definition); "3,145 (+3)" only under one stated definition; cite figures with their definitions and re-derive with a real parser.
- **Description**: One short list for verifiers and orchestrators who take a figure, a grep result, a config reading or a line citation from an earlier record as evidence: re-run the grep as written once; read machine state with the command that follows includes and origins; check a cited line by its text, not its number; state each counted figure with its definition and re-derive it from the source with a real parser.
- **Rationale**: Four independent failures of one family across two pipelines, each of which nearly caused a wrong disposition (two live lessons almost deleted). The existing coverage is narrow: `--show-origin` appears only inside the rerere warning, and `evidence-appraisal` appraises borrowed external claims, not the project's own records.
- **Estimated scope**: one paragraph or short bullet list in an existing skill or reference
- **Overlap check**: `skills/merge-worktree/SKILL.md:32` (`--show-origin`, rerere context only); `skills/evidence-appraisal/SKILL.md` (external claims); pending 16-45-03 Proposal 1 (check a lesson against the tool when copying it) is adjacent: that one is about writing a lesson into an artifact, this one about trusting a record when verifying. Disposition both together. Searched `skills/`, `agents/`, `rules/` for `word for word`, `re-derive`, `with its definition`: no match on this point.
- **Recommended delegation**: context-engineer (placement: `evidence-appraisal` vs a verifier-facing reference) then implementer
- **Suggested artifact path**: `skills/evidence-appraisal/SKILL.md` (alternative: `skills/software-planning/references/` verifier reference)

### Proposal 4: A real-data proof prints the parsed intermediates when an earlier branch can decide the verdict

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `routing-facts/VERIFICATION_REPORT.md` Merge candidate ("When a classifier short-circuits on the common case, a green verdict over real data never exercises the secondary reader"), B-1 (future real-transcript proofs print the parsed values, not only verdicts), and F-1 (11 of 13 real driver requests misread because step prose quoted `tier: H`; the fix added a real-shape test with an unhinted step whose prose quotes the marker). The delta confirmed it by printing `implied` on real data.
- **Description**: In the testing strategy for classifiers and parsers: a proof over real data is only as strong as the branch it reaches. When an earlier branch can return the verdict (a `floor` default), print the parsed intermediate value and add a fixture shaped like the real input that tempts the secondary reader (prose quoting the field it parses).
- **Rationale**: The defect hid behind a green real-data run and was found only by the verifier. One pipeline, so seedling, but the verifier named it as a pattern and the remedy is two lines.
- **Estimated scope**: two to three lines in an existing reference
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md` ("Measure the thing, not a proxy", adjacent: canary and break act on the judged quantity). Searched `skills/`, `agents/verifier.md` for `intermediate values`, `short-circuit`, `real-shape`: no match.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 5: `affected_files` takes a directory prefix, never a glob

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `rework-observation-log-adr-doc-accuracy/LEARNINGS.md` Gotchas: an entry `hooks/_observation_log/*` reads as a dead path in `adr_health.py` and `check_adr_frontmatter_promotion._is_live`; the form `hooks/_observation_log/` is live and matches every module in the package.
- **Description**: Add one sentence to the `affected_files` paragraph: to name a whole directory, write it with a trailing slash; a glob is a literal path to every resolver and reads as a dead reference.
- **Rationale**: Verified in code: `scripts/check_adr_frontmatter_promotion.py:265-274` resolves a trailing-slash entry as a directory and any other entry with `exists()`. The paragraph already says "an entry that cannot resolve is worse than no entry" but names only ephemeral paths and placeholders, so an author who reaches for a glob gets no warning before `adr_health.py` flags it.
- **Estimated scope**: one sentence in an existing reference
- **Overlap check**: `skills/software-planning/references/adr-authoring-protocols.md:21` (ephemeral and placeholder entries; no glob case); `rules/swe/adr-conventions.md` carries the field list only. Searched `skills/`, `rules/`, `docs/`, `scripts/CLAUDE.md` for `glob.*affected_files`, `directory-prefix`: no match.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/adr-authoring-protocols.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Skill update; load `skill-crafting`; dispose with the pending Proposal 3 of 16-39-41 (same reference family) |
| 2 | context-engineer | Decide placement first (`hook-crafting` vs `testing-strategy`) |
| 3 | context-engineer then implementer | Dispose together with the pending Proposal 1 of 16-45-03 |
| 4 | context-engineer then implementer | Can ride Proposal 1's edit to `gate-canaries.md` |
| 5 | context-engineer then implementer | One sentence; no new file |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals.
- After approval, invoke `context-engineer` for the skill edits; proposals 1 and 4 touch the same file and can ship in one commit.
- Re-run `/skill-genesis` after the next harvest batch; seedlings 2 and 4 and the skipped items 13 and 20 are worth re-checking for a second occurrence.
