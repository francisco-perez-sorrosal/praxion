---
schema_version: 1
report_id: skill-genesis-2026-11-15_17-16-03
generated_at: 2026-11-15T17:16:03Z
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@main
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "10 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 17:16:03

## Summary

3 queue sources analyzed (process-economy-c5, process-economy-d, process-economy-td102), 26 items extracted, 4 proposals (all skill updates), 22 skipped or deduplicated. Review status: pending. Each lesson was grepped against `skills/`, `rules/`, `agents/`, `docs/`, `scripts/CLAUDE.md`, `README_DEV.md` and `CLAUDE.md`, and against the nine earlier reports of this run.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| c5 LEARNINGS + VERIFICATION | `.ai-work/_harvest/process-economy-c5/` | 9 | Read (LEARNINGS gotchas/decisions; VERIFICATION findings and merge candidates) |
| d LEARNINGS + VERIFICATION | `.ai-work/_harvest/process-economy-d/` | 11 | Read |
| td102 LEARNINGS + VERIFICATION | `.ai-work/_harvest/process-economy-td102/process-economy-td102/` | 6 | Read (LEARNINGS; VERIFICATION findings scanned) |
| CONSULT_*.md fragments | the three sources | 0 | Not found |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_*.md` | n/a | Read for dedup |
| Sentinel, idea ledger, ADRs, calibration log | — | 0 | Not consulted (queue mode; sources carry the evidence) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Adding a column to an append-only ledger rewrites every row's bytes; the gate reasons about bytes, so use a boundary header plus a derived property | td102 LEARNINGS Gotchas | Skill (update) | Not in repo (searched `skills/software-planning/references/coordination-details.md`, `artifact-inventory.md`, `skills/consult/SKILL.md`, `agents/discipline-consultant.md`); only the gate test carries it. Proposal 1 |
| 2 | `str.lstrip("./")` / `strip("[]\`")` strip a character set, not a prefix; fixture used a relative path while capture rows carry absolute ones; once-marker written under cwd, read at git toplevel | d VERIFICATION F2/F3; c5 test-engineer `_split_files` note | Skill (update) | Two pipelines; not in repo (searched `skills/testing-strategy/`, `skills/python-development/`, `skills/hook-crafting/references/testing-guide.md`). Proposal 2 |
| 3 | Verbatim recorded rows inherit host state (CLI default `~/.claude/projects` sized the resume) and history (retired namespace tripped a repo-wide invariant) | d LEARNINGS (pair B close, root suite) | Skill (update) | Not in repo (grep `host-dependent`, `projects-dir`, `retired namespace` empty). Proposal 3 |
| 4 | Paid before/after measured nothing: the live sandbox disables observability, the remedy's input; read the dry-run's env keys against the remedy's preconditions first | d LEARNINGS Gate O2 | Skill (update) | Not in repo (`skills/eval-praxion/SKILL.md:129-160` has dry-run, cost, isolation; no precondition check). Proposal 4 |
| 5 | A test that passes on HEAD proves nothing about the fix (td-214 fixture under the byte ceiling) | c5 LEARNINGS Gotchas | Skip | Present: `skills/testing-strategy/references/gate-canaries.md:39` (Prove the canary bites) |
| 6 | Mutant sandbox copied `hooks/` only; every mutant crashed and fail-open read as silence; run an unmutated control | d LEARNINGS verifier rework | Skip | Same family as pending 17-04-31 Proposal 2 (assert the scene before reading a verdict); one pipeline |
| 7 | Silence-case tests are vacuous until the handler exists | d LEARNINGS pair B | Skip | Same family as item 6 and `testing-strategy/SKILL.md:100` (GREEN anchors) |
| 8 | Shell guard refuses commands whose text names `eval`; heredoc script "too complex" | c5 LEARNINGS Gotchas | Skip | Present: `docs/claude-code-limitations.md:11` (refusal by command text) |
| 9 | Corpus embedded in a test trips the id-citation checker; move to a fixture file | c5 test-engineer Gotchas | Skip | Present: `rules/swe/id-citation-discipline.md` (ignore marker, exempt paths); earlier item 10 of 16-42-24 |
| 10 | `Files:` glob vacuous via `fnmatch(basename)`; shared files sequenced by step id | c5 Assumptions/Gotchas | Skip | Pending: 16-39-41 Proposal 1 (`Files:` attribution); fixed in code |
| 11 | Stop-hook `additionalContext` forces one continuation turn; exit-0 stderr never reaches the model | d LEARNINGS | Skip | Present: `skills/hook-crafting/SKILL.md` (Stop/additionalContext), `references/event-reference.md` (verbose mode) |
| 12 | `startswith("fix:")` misses scoped commit types | d Probe results | Skip | Fixed in the hook; instrument-specific |
| 13 | Spawn-budget overrun by a read-only docs-lookup agent; prefer a tool call | d LEARNINGS Gate O2 | Skip | Covered: `coordination-details.md:257-262` (every first start counts); one occurrence |
| 14 | Consumer sweep before deleting a field; frozen records left untouched | d LEARNINGS Step 2 | Skip | Present: `decomposition-guide.md:39` (grep with no include filter) |
| 15 | Second top-level YAML key silently overwrites the first in `traceability.yml` | d LEARNINGS Step 3 | Skip | One occurrence; ordinary YAML behaviour; the fragment-merge step already re-parses |
| 16 | Re-scope stated when LLM readers restate a changed model (`agents/test-engineer.md`, planner) | d LEARNINGS Step 6 | Skip | Same lesson as pending 16-58-47 Proposal 1 (search every agent definition for old phrasing) |
| 17 | Agent stopped at turn cap: orchestrator re-derives the block from ground truth | d LEARNINGS pair B | Skip | Present: completion handshake in `swe-agent-coordination-protocol.md` |
| 18 | Spec's example table narrowed silently; tests covered only the narrowed subset | c5 VERIFICATION fail-1 | Skip | Behavioral contract (`[UNSURFACED-ASSUMPTION]`) covers it; one occurrence |
| 19 | Module-level PEP 604 alias breaks bare `python3` (3.9) | c5 VERIFICATION | Skip | Present per 16-58-47 item 13 |
| 20 | Line-ceiling at 800/800: a DRY sentinel can cost lines; measure `wc -l` | c5 LEARNINGS Gotchas | Skip | Ordinary advice; one occurrence |
| 21 | Blind-classification check uses `.findall` uniqueness, stricter than `.search` sibling | td102 Edge Cases | Skip | Design decision of this change |
| 22 | Verifier overstated "identical mechanism" across four protocol sites; omissions behind pointers | td102 VERIFICATION | Skip | Pipeline-specific; covered by 17-08-36 Proposal 1 theme (check lesson against the artifact) |
| 23 | `[draft-adr-id]` in code; ADR mis-categorised | td102 VERIFICATION F1/F2 | Skip | Present: `id-citation-discipline.md`, `adr-conventions.md` |
| 24 | Remedy for td-253 inert for five independent causes (channel, trigger, threshold, matcher, substrate) | d Probe results | Skip | Findings of this task, recorded in its ADR and ledger |
| 25 | Resume emits `agent_start` with the same `agent_id`; `spawns_by_agent_type` counts rows | d Probe results | Skip | Documented in `scripts/spawn_count.py` and the ledger |
| 26 | Rule-body token delta must be net <= 0 in tokens and bytes (ratchet compares bytes) | d Probe results | Skip | Present: `rules/CLAUDE.md` token notes; ratchet error states it |

## Proposals

### Proposal 1: A schema change to an append-only ledger adds a boundary header, never a backfill

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: td102 LEARNINGS Gotchas ("Backfilling a new cell into every existing row of an append-only ledger is not a safe operation"); Patterns That Worked (read the gate's implementation, not its docstring)
- **Description**: Add a short block to the consult-ledger section of `coordination-details.md`. A gate over an append-only markdown ledger compares bytes, so a column backfill that changes 39 rows fails it even though the schema change is additive; rewording a row inside a pipe-delimited `## Column Definitions` grid fails it too. Introduce a regime distinction as a dated header line (as `**Blind classification begins**:` does) and derive the property from `timestamp` against it; non-pipe lines can be added anywhere.
- **Rationale**: the planner's first design backfilled 39 rows and was caught only by reading `fitness/tests/test_consult_append_only.py`. The same trap awaits any later ledger-schema change, and no shipped document states it.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: none (searched `coordination-details.md`, `artifact-inventory.md`, `skills/consult/SKILL.md`, `agents/discipline-consultant.md`, `tech-debt-ledger.md`; the last carries "append-only at write" for producers only)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (consult ledger section, near line 449)

### Proposal 2: Fixtures carry the shape the producer emits; `strip`/`lstrip` take a character set

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-d VERIFICATION F2 (`path.lstrip("./")` stripped every leading dot and slash; the fixture used a relative path while capture rows carry absolute ones) and F3 (marker written under the process cwd, read at the git toplevel); process-economy-c5 test-engineer Gotchas (`str.strip("[]\`")` leaves an interior backtick; fixed by tokenizing with a regex)
- **Description**: Two bullets for `python-testing.md`: (1) `strip`, `lstrip` and `rstrip` take a character set, not a prefix or suffix; use `removeprefix`/`removesuffix` or a regex when the intent is a prefix. (2) A fixture takes its values (absolute vs relative paths, the cwd a hook runs from, a subdirectory session) from a real producer row, because a fixture that is tidier than production passes while the code is wrong; add one case run from a subdirectory.
- **Rationale**: two independent pipelines, both caught late (a verifier FAIL and a test-engineer note), each with a test that encoded the bug. A 3-line bullet closes the gap without a new artifact.
- **Estimated scope**: two bullets in an existing reference
- **Overlap check**: none (grep `lstrip`, `character set`, `production path shape` in `skills/testing-strategy/`, `skills/python-development/`, `skills/hook-crafting/references/testing-guide.md` found nothing)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

### Proposal 3: A verbatim recorded fixture inherits the host and the history it was recorded in

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: process-economy-d LEARNINGS (pair B close: a CLI test sized a resume from the host's real `~/.claude/projects`, `unsized` read 0; root-suite run: a verbatim 2026-08-13 WAL row carried the retired namespace and tripped `test_no_live_surface_carries_the_retired_namespace`)
- **Description**: One bullet for the same reference: a test over rows copied verbatim from a real log pins every default that reaches outside `tmp_path` (here `--projects-dir`) and normalizes any field that predates a rename (with a comment, never an allowlist entry). Run the repo-wide invariant tests, not only the step's scoped tests, before calling a verbatim-fixture file done.
- **Rationale**: two failures in one pipeline, both invisible to the scoped run. Seedling because the host-dependence half is recorded in one pipeline only; hold for a second occurrence or fold into Proposal 2 at review.
- **Estimated scope**: one bullet
- **Overlap check**: none (grep `host-dependent`, `projects-dir`, `retired namespace` empty); adjacent to Proposal 2
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

### Proposal 4: Before a paid before/after run, read the dry-run's environment against the remedy's preconditions

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: process-economy-d LEARNINGS "Gate O2 — paid after measurement, and why it measured nothing" (the sandbox sets `PRAXION_DISABLE_OBSERVABILITY`, the Stop gate reads the observation log, so the hook could never fire; about $3.1 spent, the O1 dry run had printed the env keys)
- **Description**: In the live-runner section of `skills/eval-praxion/SKILL.md`, add: compare the `--dry-run` environment keys with the inputs the remedy under test reads (a WAL-gated hook cannot be measured while the sandbox disables observability); otherwise declare the remedy unmeasured and say so in the baseline. Also state the power note: k=5 cannot tell 80% from 100%, so a before/after is read as a direction against the pooled rate.
- **Rationale**: the source names it a correction candidate and the cost is real money. `eval-praxion/SKILL.md:129-160` documents dry-run, cost and isolation but no precondition check.
- **Estimated scope**: two bullets in an existing skill
- **Overlap check**: none (`eval/README.md` and `docs/observability.md` mention the env key only as a setting)
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/eval-praxion/SKILL.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill update; load `skill-crafting`; one paragraph |
| 2 | context-engineer | Skill update; dispose with Proposal 3 and the pending `python-testing.md` proposals of 16-39-41 and 17-12-36 |
| 3 | context-engineer | Skill update; may fold into Proposal 2 |
| 4 | context-engineer | Skill update; keep to two bullets |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- Proposals 2 and 3 share a file with pending proposals from earlier reports; review them together.
- Re-run `/skill-genesis` after the remaining batch (11 of 11) completes.
