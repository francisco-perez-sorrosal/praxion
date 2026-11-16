---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-45-03
generated_at: 2026-11-15T16:45:03Z
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "3 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 2, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:45:03

## Summary

3 queue sources (`refactoring-delivery`, `process-principles`, `handoff-lessons`), 41 learning items extracted, 2 proposals, 39 deduplicated or skipped. Interpretation: the 2026-11-12 to 2026-11-15 text batches already wrote most process lessons into `skills/`, `rules/`, `README_DEV.md` and `scripts/CLAUDE.md`, so only a lesson with no carrier is proposed, and each skip names the file searched. Two assumptions I took and surfaced: (1) a lesson rejected on 2026-11-01 as "tool-side gap, ledgered" (mutation-sensor reach limits) or "below-bar prose checklist from one pipeline" (planner `Files:` checklists) is skipped here, not re-proposed; (2) the third source is the second batch's own record, so its verifier findings are read as evidence about writing lessons into artifacts, not as lessons about the code. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| refactoring-delivery LEARNINGS.md | `.ai-work/_harvest/refactoring-delivery/LEARNINGS.md` | 22 | Read in full (273 lines) |
| refactoring-delivery VERIFICATION_REPORT.md | `.ai-work/_harvest/refactoring-delivery/VERIFICATION_REPORT.md` | 3 | Read (LEARNINGS Harvest, Recommendations; headings of the rest) |
| process-principles LEARNINGS.md | `.ai-work/_harvest/process-principles/LEARNINGS.md` | 12 | Read in full (105 lines) |
| process-principles VERIFICATION_REPORT.md | `.ai-work/_harvest/process-principles/VERIFICATION_REPORT.md` | 1 | Read (Recommendations, merge block; headings of the rest) |
| handoff-lessons LEARNINGS.md | `.ai-work/_harvest/handoff-lessons/LEARNINGS.md` | 3 | Read in full, with FOLLOW_UPS.md and BATCH_INSTRUCTIONS.md (the batch's own protocol) |
| handoff-lessons VERIFICATION_REPORT.md | `.ai-work/_harvest/handoff-lessons/VERIFICATION_REPORT.md` | 4 | Read (verdict, check 7, Recommendations, merge candidates; headings of the rest) |
| CONSULT_*.md | the three directories | 0 | Not found |
| Other files (PROMPT_*, REPIN_*, SYSTEMS_PLAN, PLACEMENT_PLAN, logs) | same | 0 | Not read (outside the contract) |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_16-39-41.md`, `..._16-42-24.md` | n/a | Read; pending 2026-11-05 and the 2026-10-10 / 2026-10-31 dispositions checked |
| SENTINEL / IDEA_LEDGER / calibration log | `.ai-state/` | 0 | Not consulted (queue mode) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A lesson copied from a handoff or note can be false (4 of 34 sentences contradicted by the tool: commitizen `incremental`, `gtimeout --help`, a path::node claim, a moved symlink remedy); check against the tool first | handoff-lessons VERIFICATION merge block, Check 2 | Skill (update) | No carrier: searched `skills/skill-crafting/`, `skills/rule-crafting/`, `agents/context-engineer.md`, `rules/`; Proposal 1 |
| 2 | An interim sentence belongs in a paragraph of its own so its removal needs no edit inside the schema | handoff-lessons LEARNINGS, Check 7 item 4 | Skill (update) | Folded into Proposal 1 (`document-templates.md:73` is the instance, not the rule) |
| 3 | One name per thing, in the reader's vocabulary (default branch vs `main`; cap vs count; step-loop words in the release skill) | handoff-lessons LEARNINGS, Check 7 items 2, 9 | Skill (update) | Folded into Proposal 1 |
| 4 | A fact seen once carries its date and "not re-probed" | handoff-lessons LEARNINGS | Skill (update) | Folded into Proposal 1; `rules/swe/staleness-policy.md` covers `last-verified` section markers, not a once-seen tool observation |
| 5 | After changing a rule, search every agent definition, reference and golden bad-case for the old phrasing (3 of 8 convention findings) | process-principles VERIFICATION merge block | Skill (update) | Folded into Proposal 1; searched `skills/software-planning/`, `agents/verifier.md`, `rules/`: no carrier |
| 6 | Folding two lessons into one paragraph moved one lesson's scope onto the other (L-49) | handoff-lessons VERIFICATION merge candidates | Skill (update) | Folded into Proposal 1 |
| 7 | `"utf-8"` to `"UTF-8"` codec-name variants survive and are equivalent (six steps, five functions) | refactoring-delivery LEARNINGS steps 10, 11, 12, 15, 25a, 28b | Skill (update) | `python-testing.md:233-238` names classes in the abstract; pending 16-42-24 Proposal 2 names the `encoding=` cluster but not the codec spelling; Proposal 2 |
| 8 | A survivor killed only by a subprocess test is invisible to the sensor; kill it in-process (swap `Path.read_text` for one defaulting to ASCII; wrap `open` and assert the read size) | refactoring-delivery LEARNINGS steps 25a, 28b | Skill (update) | Folded into Proposal 2; related deferred 2026-10-10 Proposal 3 (caller environments) |
| 9 | Test file puts live `scripts/` first with `sys.path.insert(0, ...)` and shadows the sensor's mutated copy; code run only at import (module table) cannot be mutated | refactoring-delivery LEARNINGS steps 15, 25b | Skip | Tool-side reach limits; 2026-10-31 Proposal 6 (sensor recipe additions) was rejected "ledgered: tool-side gaps are open rows"; `scripts/CLAUDE.md:101-102` and the `mutation_sensor.py` docstring already carry the neighbouring limits |
| 10 | Sensor run over a scratch copy: chain with `&&` only (a `;` after a failed chain ran a mutant of `--check` in the checkout) | refactoring-delivery LEARNINGS step 25b | Skip | One occurrence; nothing written; operator care |
| 11 | Tests importing another test module are refused by the sensor; keep world-read tests in a file of their own | refactoring-delivery step 28b, VERIFICATION W-08 | Skip | Present: `scripts/CLAUDE.md:101` |
| 12 | Parent-counting fixtures and `generate_kernels.py` imports of `hooks/` fail the sensor baseline (`run-failed`) | process-principles step 3 | Skip | Present: `scripts/CLAUDE.md:102`, `mutation_sensor.py` docstring |
| 13 | Hook modules run on the user's `python3` (3.9): ruff UP rewrites `Optional`/`Union` runtime aliases to `X \| Y`; `assert_never` is 3.11+ | refactoring-delivery steps 8, 13, 14; process-principles (3.9 floor) | Skip | Carried by the module comments (`hooks/_skill_delivery.py:139`), `hooks/_interpreter_floor.py`, and `pyproject.toml:182-185` (the per-file ignore with its reason); two pipelines but the floor has a declared home |
| 14 | A registration step reddens the registry-against-detector drift test until the step that adds the other half; a tightened purity guard blocks a wiring step; `LIVE_MODULES` pin breaks | refactoring-delivery step 4 (`[BLOCKED]`); process-principles steps 4, 8, 9 | Skip | Corroborates pending 16-39-41 Proposal 1 (check every test that pins the contract); 2026-10-31 Proposal 4 (list consumers in `Files:`) was rejected below-bar; disposition 16-39-41 Proposal 1 with this evidence |
| 15 | `Read-only:` with a `path::node` entry withholds the whole file from every step's commit | process-principles Gotchas (orchestrator) | Skip | Present: `skills/software-planning/references/document-templates.md:73`, `stop-recoveries.md:62` |
| 16 | Two not-done steps must not own the same guard file; one re-pin step; frozen guard owned before the first gate | both LEARNINGS | Skip | Present: `coordination-details.md`, `agent-pipeline-details.md:331` (`pending=`); prior report item 11 |
| 17 | Plan reader takes any prose line starting `tier`, `review`, `read-only`, `assignee`, `change type` + colon as a field | refactoring-delivery Gotchas | Skip | One pipeline; a parser quirk whose fix is tool-side; not carried in prose (`document-templates.md`), wait for a second occurrence |
| 18 | The follow-up pass is not a numbered step (it would stop the loop reporting `complete`) | process-principles Assumptions | Skip | Present in substance: `coordination-details.md:95`, `agent-pipeline-details.md` Exit 2.5 |
| 19 | A held last step owns every text that states the interim (scripts catalog, developer guide, design document) | refactoring-delivery VERIFICATION W-05 | Skip | One pipeline, prose planner checklist (2026-10-31 Proposal 5 precedent); wait for a second held-move plan |
| 20 | A plan can build every piece and wire none; ask what calls each built piece | refactoring-delivery LEARNINGS Merged | Skip | Present: `decomposition-guide.md:170` |
| 21 | Orchestrator `( cmd & )` starts with SIGINT ignored; a test that passes alone and fails under a runner is not a flake | process-principles Gotchas (orchestrator) | Skip | Present: `scripts/CLAUDE.md:99`, `skills/test/SKILL.md:24` (prior report item 9) |
| 22 | Linked `dashboard_app/node_modules` and pnpm 11 verify-deps; run the vitest runner directly in a worktree | process-principles Gotchas; handoff-lessons Gotchas | Skip | Present: `dashboard_app/README.md:118` |
| 23 | Derived scope of a prose or kernel change is wide (16,788 root tests, 21 + 8 min; 28 min full root); raise the pocket bound | handoff-lessons Gotchas; process-principles Test baseline | Skip | Present: `README_DEV.md:510` (`PRAXION_STEP_LOOP_POCKET_TIMEOUTS`), `skills/test/SKILL.md:24` (detach) |
| 24 | The test helper keeps the session's `CLAUDE_PLUGIN_ROOT` and writes rows into the real log | refactoring-delivery step 14, 25a | Skip | Present: `README_DEV.md:513` (root `conftest.py` drops it) |
| 25 | A section delivered verbatim to a role must read standing alone | process-principles After the merge request | Skip | Present: `rules/_audience.yaml:16` |
| 26 | A gate that fails safe must fail safe on every path that cannot read; reuse the module's own reader | process-principles VERIFICATION merge block | Skip | Present: `rules/swe/gate-liveness.md` (totalising check, "emit a well-formed result on every path"); `software-design-principles` one-definition |
| 27 | Measure with the method that can see the change (scratch-home) | process-principles VERIFICATION, FC-01 | Skip | Covered by pending 2026-11-05 Proposal 4 (footprint measurement) |
| 28 | Value read from a file refused where read; container shape checked before its fields | refactoring-delivery VERIFICATION W-06 | Skip | One occurrence; `data-structure-design` already says parse at the boundary |
| 29 | Test support grows long under many rework steps; split under a Spec Question | refactoring-delivery VERIFICATION W-09 | Skip | Filed as td-663 |
| 30 | Pipeline documents drift from the head after late commits (digest line, merge provision, traceability lists) | refactoring-delivery VERIFICATION W-01, W-02, W-04 | Skip | Ephemeral documents; low cost; one pipeline |
| 31 | Planner decisions: lettered steps, pool outside `kit_for`, one re-pin step, `mutation: on` only where the sensor can reach | refactoring-delivery Decisions | Skip | Plan-level, recorded in the plan and the architect's ADR drafts |
| 32 | Root `AGENTS.md` stale at the base; compile from the main checkout with `PRAXION_PERSONAL_INFO_ENV` and keep only the principle hunk | process-principles step 5 | Skip | One occurrence, transient repository state; recorded follow-up (td-647 generates the mirror) |
| 33 | Heavy runs beside a gate cost the gate; a returned step is recorded at once | process-principles Gotchas (orchestrator) | Skip | Present: `skills/step-loop/SKILL.md:15`; load timing is an environment fact |
| 34 | Eval pool design: grader data inside a template leaks to the session; stand-in reads proofs by slug; early-stop tasks grade `NotApplicable` | refactoring-delivery steps 20, 23a, 24d | Skip | Eval-framework internals; fixed in code (step 23a) and recorded in the eval README |
| 35-41 | Step-local assumptions, line ceilings, import allow-lists, survivor counts, boy-scout edits, td rows, spawn tallies | refactoring-delivery, process-principles LEARNINGS | Skip | Recorded in ADRs, the ledger, code or the plan; transient or too narrow |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Writing a lesson into an artifact — check it against the tool, keep interim text apart, date what was seen once

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/handoff-lessons/VERIFICATION_REPORT.md` Check 2 and the merge block ("a source lesson can be wrong about a tool": L-30 against commitizen's incremental bump, L-12 against `gtimeout --help`; "folding two lessons into one paragraph can move one lesson's scope onto the other", L-49); Check 7 items 2, 4, 9 (interim sentences folded into a 330-word schema paragraph; "the default branch" and `main` in one bullet; step-loop words in the release skill); `handoff-lessons/LEARNINGS.md` § Verification Patterns Merged (four patterns); `process-principles/LEARNINGS.md` § Verification Patterns Merged ("a routing change leaves residue in the text that held the old rule", 3 of 8 convention findings).
- **Description**: Add a short block to the Gotchas of `skills/skill-crafting/references/content-and-development.md`, with a one-line pointer from `skills/rule-crafting/SKILL.md` § Content Guidelines. Five points: (1) before a lesson from a note, a handoff or memory becomes a sentence in an artifact, check each tool-behaviour claim against the tool's code or `--help`, even when the source is your own note; (2) a workaround for an open defect goes in a paragraph of its own, worded "until that is fixed", so removing it never means editing inside a schema paragraph; (3) a fact observed once carries its date and "not re-probed"; (4) one name per thing, in the reader's vocabulary (no pipeline words in a skill for another domain), and never fold two lessons into one paragraph without re-reading whose scope each sentence now carries; (5) after changing a rule, search every agent definition, reference and golden bad-case for the old phrasing, not only the file that states the rule.
- **Rationale**: Measured in the batch that wrote 34 pieces: 4 pieces (12%) asserted what the code or tool contradicts, each with a concrete failure scenario, and one convention finding in three was residue of the old wording. The five points recur across two pipelines' verifiers and no shipped authoring guidance carries them; they are the cheapest checks at the moment of writing and apply to every `*-crafting` author, not only this repository.
- **Estimated scope**: SKILL.md only is unchanged; one block of about 8 lines in one reference, one pointer line in a second file.
- **Overlap check**: `rules/swe/staleness-policy.md` (`last-verified` markers on drift-prone sections; not a once-seen observation or a tool-claim check); `skills/evidence-appraisal` (borrowed external claims, not an internal lesson); `skills/skill-crafting/references/content-and-development.md` Gotchas (format, not these points). Searched `skills/skill-crafting/`, `skills/rule-crafting/`, `agents/context-engineer.md`, `rules/`, `agents/verifier.md` for "contradicted", "interim", "old phrasing", "one name", "not re-probed": no carrier. `.ai-state/specs/SPEC_memory-to-artifacts_2026-11-15.md` holds P-044 (interim text re-checked against its row), a requirement of that batch, not guidance.
- **Recommended delegation**: context-engineer (loads `skill-crafting`)
- **Suggested artifact path**: `skills/skill-crafting/references/content-and-development.md` (pointer in `skills/rule-crafting/SKILL.md`)

### Proposal 2: Survivor triage — the codec-name spelling is equivalent, and a survivor only a subprocess kills needs an in-process stand-in

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `refactoring-delivery/LEARNINGS.md` steps 10, 11, 12, 15 (three codec aliases), 25a, 28b: `"utf-8"` read as `"UTF-8"` survives in `preload_state`, `body_digest`, `_read_body_unbounded`, the definition reader, the writer and the restore, each time argued equivalent by hand; and the kills that worked: `encoding=None` killed by a test that swaps `Path.read_text` for one defaulting to ASCII (the locale subprocess test was blind to the sensor), `read(None)` and `read(MAX + 2)` killed by a test that wraps `open` and asserts the one read handed out exactly the limit plus one byte.
- **Description**: Under "Reading survivors" in `skills/testing-strategy/references/python-testing.md`, add a third equivalent cluster beside the abstract classes: a codec name in a different case (`"utf-8"` / `"UTF-8"`), equivalent because Python resolves codec names case-insensitively, so argue it in one line. Add one sentence to the survivor remedy: when only a subprocess test (a locale, an environment, a daemon flag) kills a survivor, the sensor cannot see that kill; write an in-process test with a stand-in for the call (a `read_text` that defaults to ASCII, an `open` wrapper that records the size asked) and re-run.
- **Rationale**: The codec spelling appeared in six steps of one pipeline, each spending a retry on the same written argument; the in-process kill is the concrete remedy for the blind spot that the deferred 2026-10-10 Proposal 3 and the 2026-10-31 sensor-recipe reports name without a technique. Seedling-to-sapling because the evidence is one pipeline but repeated.
- **Estimated scope**: two to three lines in an existing section
- **Overlap check**: `skills/testing-strategy/references/python-testing.md:233-238` (abstract classes); pending 16-42-24 Proposal 2 (`encoding=` on ASCII, keyword equal to default; same paragraph) and pending 2026-11-05 Proposal 6 (survivor ids, stale bytecode; next paragraph): disposition the three together in one edit pass. Deferred 2026-10-10 Proposal 3 (caller environments) is a different point.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Load `skill-crafting`; one block plus one pointer line; check the pointer against `rules/CLAUDE.md` token notes (rule-crafting is a skill, so no always-loaded cost) |
| 2 | context-engineer then implementer | Same file and paragraph as 16-42-24 Proposal 2 and 2026-11-05 Proposal 6; one edit pass |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 2 pending proposals.
- Proposal 2 edits the paragraph that 16-42-24 Proposal 2 and 2026-11-05 Proposal 6 also edit; disposition the three together.
- Triage row 14 is evidence for pending 16-39-41 Proposal 1 (a tightened contract; registry and detector halves split across steps); raise its maturity when dispositioning.
- Remaining batches (4 to 11) should check this report's headings before proposing a lesson on writing lessons into artifacts or on survivor triage.
