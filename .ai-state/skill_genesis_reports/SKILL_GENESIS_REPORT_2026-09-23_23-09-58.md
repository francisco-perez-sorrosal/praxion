---
schema_version: 1
report_id: skill-genesis-2026-09-23_23-09-58
generated_at: 2026-09-24T06:11:53Z
task_slug: skill-genesis-2026-09-23
agent_version: skill-genesis@bfebf639
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest", batch: "10 of 13", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-09-23 23:09:58

## Summary

1 learning source analyzed (`.ai-work/_harvest/process-economy-p3-6-adopt/`, the *implementation* pipeline
that adopted the P3.6 mutation-sensor spike harvested in batch 9), 15 discrete items extracted, 4 proposals
generated, 11 deduplicated/skipped (most already shipped to `scripts/mutation_sensor.py`'s own docstring,
`skills/testing-strategy/references/python-testing.md`, `docs/architecture.md`, and the open tech-debt
ledger rows td-213/214/218/221/238). Review status: pending.

**Key dedup finding**: this pipeline's own doc-engineer step already shipped a "when/why" section
(`python-testing.md § Mutation Sensor (Per-Step)`) that deliberately declines to duplicate the mutmut
recipe in prose, pointing instead at the runner's own module docstring — which does carry the full
eight-plus-one-point recipe (verified: `scripts/mutation_sensor.py` lines 22-90+). This **narrows** batch
9's pending Proposal 1 (`skills/testing-strategy/references/mutation-testing.md`, a new reference file
duplicating the recipe): most of what it would contain is now redundant with code that already exists and
that the project's own single-source-of-truth convention says not to duplicate. The genuinely new content
this batch found — a diagnostic *methodology* for reading real mutant diffs once black-box guessing
plateaus — is not covered anywhere. Proposal 1 below is an **update** to the already-shipped
`python-testing.md` section rather than a new file, and explicitly recommends the reviewer fold or narrow
batch 9's Proposal 1 alongside it.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (current task) | `.ai-work/skill-genesis-2026-09-23/LEARNINGS.md` | 0 | Not found (queue mode; no local task LEARNINGS.md) |
| VERIFICATION_REPORT.md (current task) | `.ai-work/skill-genesis-2026-09-23/VERIFICATION_REPORT.md` | 0 | Not found |
| Queue source: process-economy-p3-6-adopt | `.ai-work/_harvest/process-economy-p3-6-adopt/LEARNINGS.md` | 13 | Read in full (852 lines) |
| Queue source: process-economy-p3-6-adopt | `.ai-work/_harvest/process-economy-p3-6-adopt/VERIFICATION_REPORT.md` | 2 | Sampled — headings scanned; findings already resolved in-pipeline or dedup'd against ledger |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not consulted (no ecosystem-audit overlap risk for this batch's technical content) |
| Latest IDEA_LEDGER_*.md | `.ai-state/idea_ledgers/` | 0 | Not consulted |
| ADRs | `.ai-state/decisions/` | 0 | `dec-387`/`dec-388`/`dec-390` already cited in source; no new ADR overlap search needed |
| Sibling reports of this harvest run | 9 reports (22-35-25 … 23-05-46) | — | Grepped for `mutation`/`mutmut`; batch 9 (23-05-46) Proposal 1 identified as the overlapping pending proposal, extended rather than duplicated per dispatch note |
| Harness memory (dedup) | `~/.claude/projects/-Users-fperez-dev-praxion/memory/project_process_economy_roadmap.md` + `feedback_p3_6_pipeline_corrections.md` | — | Read (per dispatch note). Neither memory file captures this batch's technical content (diagnostic methodology, `uv --project`/`--no-project` gotcha, YAML fragment quoting) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Diagnostic method: 3 consecutive zero-movement test additions is a stop-guessing signal; switch to a real `mutmut run` + `mutmut show <id>` inspection to get ground-truth diffs | LEARNINGS.md § Step 10 (test-engineer) | Skill (update) | Procedural, reusable across any future mutation-sensor dogfood step; not in docstring or python-testing.md; directly extends batch-9 Proposal 1 |
| 2 | Survivor taxonomy with worked proof method: mathematically-equivalent mutants (invariant-based proof) vs. environment-dependent artifacts (differential verification on a case-sensitive filesystem image) vs. real gaps | LEARNINGS.md § Step 10 | Skill (update) | Same reference section; the *proof technique* (not just the two-category list already shipped) is new and reusable |
| 3 | `uv run --project <dir>` refuses "No project table found" when `<dir>` is both the git toplevel AND the freshly-written `[tool.mutmut]`-only `pyproject.toml`'s location; fix is a conditional `--no-project` | LEARNINGS.md § Implementation Stage (Steps 1,3) Gotchas | Skip | Already fully documented in `scripts/mutation_sensor.py` docstring point 9, verified live this pass — genuinely zero gap remaining |
| 4 | Bootstrap probe (`mutmut --version`) before `mutmut run` to distinguish `toolchain-missing` from `run-failed` | LEARNINGS.md § Implementation Stage Gotchas | Skip | Shipped in runner code + covered by verifier's Phase 10 enumerated reason codes; not reusable prose knowledge beyond this one script |
| 5 | Timeout-budget-as-remaining-share pattern (one wall-clock budget charged across 4 subprocess stages, not per-call) | LEARNINGS.md § Implementation Stage / Step 3 rework | Skip | Shipped in runner docstring + code; narrow to this script's own concurrency model |
| 6 | `re` treats U+01C1 (`ǁ`) as a word character; anchor the mutant-key regex on the literal `__mutmut_\d+:` boundary, not `\w+` | LEARNINGS.md § Gotchas (Step 3 rework) | Skip | Shipped in runner docstring/code; a one-off regex fact specific to mutmut 3.8.0's internal naming, not broadly reusable |
| 7 | A gitignored fixture under the repo's own `tmp/` still inherits the repo's ancestor `pyproject.toml` via pytest's `rootdir` walk, breaking a real mutmut invocation; build such fixtures in the session scratchpad instead | LEARNINGS.md § Gotchas (Step 3 rework) | Rule candidate (flagged, ambiguous) | Overlaps `testing-conventions.md § Fixtures Under Gitignored Paths` territory but is about pytest config-inheritance during *manual/live* validation, not automated test fixtures — see Proposal 2 |
| 8 | `traceability_implementer-prose.yml` fragment shipped malformed YAML: a bare scalar containing `Foo (Bar: Baz)` parses as an unintended nested mapping under `yaml.safe_load`; any producer-agent prose fragment with a colon-plus-space parenthetical must be quoted | LEARNINGS.md § Checkpoint Review Gotchas | Rule candidate (flagged, ambiguous) | Declarative constraint on fragment-authoring agents, narrow scope (one field shape); see Proposal 3 |
| 9 | Review loop should be budgeted by finding *class*, not count — stop looping once remaining findings are boundary-message quality, not reading-correctness | LEARNINGS.md § Step 3 — review loop closed | Skip | Already the harness memory's `feedback_p3_6_pipeline_corrections.md` lesson set (process corrections 41-49 from a related P3.6 phase) plausibly overlaps; and `intra-step-review.md` already frames the light-review loop around finding severity — too close to existing guidance to formalize as a new rule without a clearer gap |
| 10 | AC-1 threshold amendment precedent: a fixed integer survivor-count threshold is a category error when some survivors are environment-dependent (filesystem case-folding); the fix was a qualitative "every survivor carries a proven argument" criterion, decided at the pre-verification checkpoint, not unilaterally | LEARNINGS.md § Checkpoint Review Decisions | Skip (discipline-appropriate, but too narrow to formalize) | This is a good instance of the existing pre-verification-checkpoint mechanism working as designed, not a new pattern to encode; noting it as evidence the checkpoint mechanism works, not a gap |
| 11 | `check_test_results_shape.py`'s 1,024-byte green ceiling reproduced a second time (`td-213`'s own prediction confirmed) | LEARNINGS.md § Checkpoint Review Gotchas | Skip | Already an open, actively-tracked ledger row (`td-213`); this is evidence for that row, not a new learning item |
| 12 | `scripts/test_compose_handoff.py` / `scripts/test_mutation_sensor.py` file-size ceiling growth | LEARNINGS.md multiple sections | Skip | Already tracked (`td-218`, `td-221`) |
| 13 | Register Objection instances (test-engineer flagging Step 2's "GREEN once Step 1 lands" claim vs. REQ-05's structural dependency on Step 3; the "tests never invoke real mutmut" vs. Step 4's explicit real-fixture ask) | LEARNINGS.md § Testing Stage | Skip | Correctly-functioning instances of the existing behavioral-contract mechanism, not a new pattern; resolved in-pipeline by the documented "more detailed and more authoritative document wins" convention, which is itself not novel |
| 14 | Discipline-gap signal check | — | None found | No recurring "needed a specialist voice" signal in this source; the pipeline's decisions were resolved by architect/planner/test-engineer/user, none flagged an unmet discipline |
| 15 | `git worktree`/scratch-worktree replay pattern (`trap`-wrapped create/replay/remove for AC-2's `913d87d8` foreign-checkout test) | LEARNINGS.md § Step 12 | Skip | One-off measurement-step technique already scoped to this feature's AC-2; not observed recurring elsewhere in this harvest run |

## Discipline-Gap Signals

None recorded for this batch — no recurring "needed a specialist voice" observation surfaced in this source.

## Proposals

### Proposal 1: python-testing.md § Mutation Sensor (Per-Step) — diagnostic workflow for survivor triage

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-6-adopt/LEARNINGS.md` § Implementation Stage (Step 10 — td-220 dogfood, test-engineer) — the full guess-and-measure-plateau → real-mutmut-diagnosis → survivor-taxonomy-with-proof narrative
- **Description**: Add a "Diagnostic workflow" subsection under the already-shipped `## Mutation Sensor (Per-Step)` § "Reading survivors" in `skills/testing-strategy/references/python-testing.md`. Content: (1) the stop-signal — three consecutive test additions producing zero survivor-count movement means black-box guessing has plateaued; switch to ground truth rather than adding a fourth guess. (2) The ground-truth technique — build the exact `pyproject.toml` `mutation_sensor.py` would generate (or invoke the sensor directly), run `mutmut results` + `mutmut show <id>` on each remaining survivor to read the actual mutated line, then delete the scratch `pyproject.toml`/`mutants/` immediately after inspection. (3) How to *prove* (not just assert) each of the two accepted survivor categories already named in the doc: mathematically-equivalent mutants are proven via an explicit invariant argument (e.g., "the input always contains at least one `/`, so `rsplit(s, "/", 1)[-1]` and `rsplit(s, "/")[1]` coincide for every reachable input"); environment-dependent artifacts are proven via a differential run on the *other* environment (e.g., a case-sensitive filesystem image), not merely asserted as "probably fine here."
- **Rationale**: This is the one piece of the source pipeline's mutation-testing experience genuinely absent from all shipped artifacts (docstring, `python-testing.md`, ledger). It took a real dogfood pass (49 → 7 survivors across 9 measured iterations) to discover that black-box guessing plateaus predictably and that a proof standard exists distinguishing "acceptable" from "argued." Without this, the next agent facing a stubborn survivor set will either keep guessing past the point of returns, or accept survivors on unverified hand-waving — precisely the failure the AC-1 pre-verification-checkpoint amendment (this same pipeline) had to correct for after the fact.
- **Estimated scope**: edit to one existing reference file (`python-testing.md`), ~25-35 new lines under the existing `## Mutation Sensor (Per-Step)` heading; no new file.
- **Overlap check**: Directly overlaps and **narrows** batch 9's pending Proposal 1 (`SKILL_GENESIS_REPORT_2026-09-23_23-05-46.md`, "testing-strategy — mutation-testing recipe for Praxion's flat `scripts/` layout", proposing a *new* `skills/testing-strategy/references/mutation-testing.md`). That proposal's rationale (the mutmut recipe is undocumented) no longer holds — the recipe now lives, in full, in `scripts/mutation_sensor.py`'s own docstring (verified this pass), and `python-testing.md`'s own "Producer / consumer contract" paragraph explicitly declines to duplicate it. **Recommend the reviewer disposition batch 9's Proposal 1 as `rejected` or `refined-to-scope`** (the recipe half is redundant; only the diagnostic-methodology half — this proposal — remains a real gap) rather than approving a full new reference file.
- **Recommended delegation**: context-engineer (review scope against batch 9's Proposal 1 first) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md` (existing file, existing `## Mutation Sensor (Per-Step)` section)

### Proposal 2: testing-conventions — pytest rootdir config inheritance during manual/live validation outside the automated suite

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-6-adopt/LEARNINGS.md` § Gotchas (Step 3 rework) — the `pyproject.toml`/`tmp/` rootdir-inheritance gotcha
- **Description**: A gotcha note (2-4 sentences) for `rules/swe/testing-conventions.md`'s existing "Fixtures Under Gitignored Paths" territory: a gitignored fixture directory placed under the *repo's own* `tmp/` is still inside the repo's git toplevel, so pytest's `rootdir`/`inifile` discovery walks up past the fixture and picks up the repo's own `pyproject.toml` `addopts` (e.g. `--cov`) when the fixture's own generated config carries no `[tool.pytest.ini_options]` section — breaking any tool (like a live mutmut invocation) that assumes the fixture is config-isolated. Automated tests using `tmp_path` don't hit this (that fixture lives under the system temp dir, outside any repo). Remedy: build config-isolation-sensitive fixtures for *manual/live* validation in the session scratchpad, never the project's own `tmp/`.
- **Rationale**: This is a real, non-obvious footgun distinct from the existing "Fixtures Under Gitignored Paths" guidance (which is about *automated* test fixtures referencing gitignored source data, not about pytest's own config-discovery walking past a manually-built fixture directory). Low priority because it only bites during ad hoc manual validation, not automated CI runs — but it cost real debugging time in the source pipeline and would recur for any future agent hand-building a fixture for live tool validation.
- **Estimated scope**: single rule file edit, one short paragraph appended to the existing section.
- **Overlap check**: `rules/swe/testing-conventions.md § Fixtures Under Gitignored Paths` covers a related but distinct concern (gitignored *source* fixtures, not pytest config-discovery scope) — extends rather than duplicates.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/testing-conventions.md`

### Proposal 3: agent-intermediate-documents — YAML-fragment quoting discipline for parenthetical colon shapes

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `.ai-work/_harvest/process-economy-p3-6-adopt/LEARNINGS.md` § Checkpoint Review Gotchas — the `traceability_implementer-prose.yml` malformed-YAML incident
- **Description**: A declarative constraint for producer agents writing `traceability.yml` (or any YAML) fragment fields: a bare scalar containing a literal colon-plus-space inside a parenthetical cross-reference (e.g. `"...Reconciliation (Mutation: line shape)"`) must be explicitly quoted, or `yaml.safe_load` silently reads it as an unintended nested mapping rather than a plain string — with no parse error to catch it. Caught only by hand-verifying every merged fragment item is a plain string during this pipeline's reconciliation pass.
- **Rationale**: This is a genuine silent-corruption class (no exception, no lint failure) that would recur for any producer agent writing a cross-reference parenthetical into a YAML scalar field. The learning item itself flags that "a fragment-shape check for this class of error does not currently exist" — the durable fix is arguably a mechanical script check, not a rule, but recording the constraint declaratively gives producer agents a chance to avoid it in the interim while that script gap is separately tracked (not this agent's scope to create).
- **Estimated scope**: single rule file edit, one short bullet.
- **Overlap check**: none found — no existing rule addresses YAML fragment-field quoting for traceability/prose fragments specifically.
- **Recommended delegation**: context-engineer (may recommend a script-side mechanical check instead of/in addition to a rule bullet — ambiguous placement, flagged per Phase 4's ambiguous-case guidance)
- **Suggested artifact path**: `rules/swe/agent-intermediate-documents.md` (or context-engineer's judgment — could also be a one-line addition to `skills/spec-driven-development/references/spec-format-guide.md`'s traceability section)

### Proposal 4: Mechanical fragment-shape check for YAML colon-in-scalar corruption (tooling gap, not an artifact)

- **Disposition**: pending
- **Type**: claude.md _(flagged as out-of-artifact-type; recorded per Phase 4 leaf 5 discipline — not a skip, because the underlying constraint (Proposal 3) is real, but the most durable fix named by the source itself is a script, which this agent cannot propose to build)_
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: same as Proposal 3
- **Description**: The source LEARNINGS.md item explicitly states "a fragment-shape check for this class of error does not currently exist" — i.e., a mechanical validator (parse each fragment's YAML, assert every `implementation:`-style list item is a plain string, not a dict) would catch this class at fragment-write time rather than at reconciliation. This is not a skill/rule/CLAUDE.md proposal — it names a tooling gap for a human or `implementation-planner` to scope as a future small feature, most naturally as an extension to whatever script already validates `traceability.yml` shape (if one exists) or a new lightweight check alongside `check_id_citation_discipline.py`'s sibling scripts.
- **Rationale**: Recorded so the observation is not lost between Proposal 3 (the interim rule-level mitigation) and an eventual mechanical fix — consistent with this agent's constraint against proposing script/tooling work itself, but the source material is explicit enough about the gap that silently dropping it would lose a real, low-cost future improvement.
- **Estimated scope**: N/A — not an artifact proposal; recorded for user awareness only.
- **Overlap check**: none.
- **Recommended delegation**: user (to scope as a small implementation task if desired; outside skill-genesis's and context-engineer's remit)
- **Suggested artifact path**: N/A

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer (scope review against batch-9 Proposal 1 first), then implementer | Update `python-testing.md`; context-engineer should first disposition batch 9's overlapping Proposal 1 |
| 2 | context-engineer | Rule update; load `rule-crafting` |
| 3 | context-engineer | Rule update, ambiguous placement — context-engineer's placement judgement call per Phase 4 |
| 4 | user | Not a craftable artifact — tooling/script gap for a future planning pass, not context-engineer's remit |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals in this report — and, because Proposal 1 directly narrows it, review batch 9's pending Proposal 1 (`SKILL_GENESIS_REPORT_2026-09-23_23-05-46.md`) in the same pass.
- After approval, invoke `context-engineer` for the rule/skill updates; the agent will pick up the recommended delegations table.
- Proposal 4 is not an artifact — surface it to the user directly as a small future tooling task, independent of `/skill-genesis-review`.
