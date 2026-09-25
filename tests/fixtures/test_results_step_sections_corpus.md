# TEST_RESULTS -- process-economy-p3-5

## Step 1


## Step 1: RED — pipeline_slug shared-helper agreement test

Command: `python3 -m pytest hooks/test_capture_session.py --no-cov -q -p no:cacheprovider`

```
FAILED hooks/test_capture_session.py::TestPipelineSlugSharedHelper::test_summary_pipeline_slug_matches_the_wal_rows_project_field
1 failed, 126 passed in 0.46s
```

Result: pass=126 fail=1 skip=0

### Failures

- `hooks/test_capture_session.py::TestPipelineSlugSharedHelper::test_summary_pipeline_slug_matches_the_wal_rows_project_field`
  — `KeyError: 'pipeline_slug'` at the assertion `observation["project"] == summary["pipeline_slug"]`.
  `build_session_summary` does not yet emit a `pipeline_slug` key (function exists, key does not) — RED, not
  `ImportError`. This is the shared-helper agreement test the implementer's Step 2 must turn green.

### Note — companion baseline test, not itself RED

`TestPipelineSlugSharedHelper::test_legacy_payload_without_cwd_still_has_no_pipeline_slug_key` **passes today**
(126 of the 127 total includes it). It pins the additive-only contract for a `session_id`-only payload matching
a real pre-existing committed row's shape (no `cwd`, no slug concept) — `"pipeline_slug" not in summary` is
trivially true before any implementation exists. It is included as the RED step's baseline deliverable, not as
a second failing case; see `LEARNINGS_step1.md` for the interpretive note on why this is not itself asserted to
fail.

## Step 3


## Command

```
python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider
```

```
19 failed, 3 passed in 0.39s
```

Result: pass=3 fail=19 skip=0

## Failures

All 19 failures are `ModuleNotFoundError: No module named 'scripts.project_metrics.collectors.cost_collector'`
— the expected RED mode, since `cost_collector.py` does not exist yet (deferred-import convention, one
`ModuleNotFoundError` per test rather than a single collection-time failure). The 3 passing tests
(`TestCostFixtureIntegrity`) assert only against the committed fixture files and import no production code, so
they are correctly green before the implementer's step.

Failing node ids (19):

- `TestClassifyProvenance::test_classifies_subagent_transcript_row_as_attributed`
- `TestClassifyProvenance::test_classifies_synthesized_parent_transcript_row_as_parent_sourced`
- `TestClassifyProvenance::test_classifies_key_absent_row_with_tokens_as_pre_attribution`
- `TestClassifyProvenance::test_classifies_key_absent_row_with_no_tokens_as_unparsed`
- `TestClassifyProvenance::test_provenance_has_exactly_four_members`
- `TestAttributedFromRow::test_builds_attributed_row_with_every_field_populated`
- `TestAttributedFromRow::test_returns_none_for_pre_attribution_row`
- `TestAttributedFromRow::test_returns_none_for_unparsed_row`
- `TestAttributedFromRow::test_returns_none_for_synthesized_parent_sourced_row`
- `TestAttributedFromRow::test_coerces_null_token_fields_to_zero_at_construction`
- `TestDiscoverSources::test_dedupes_when_repo_root_is_the_main_checkout`
- `TestDiscoverSources::test_includes_both_repo_root_and_main_when_they_differ`
- `TestDiscoverSources::test_git_rev_parse_failure_degrades_to_repo_root_only`
- `TestReadAgentStopRows::test_reads_only_agent_stop_rows_from_a_well_formed_file`
- `TestReadAgentStopRows::test_missing_file_degrades_to_zero_rows_with_named_issue`
- `TestReadAgentStopRows::test_malformed_file_degrades_to_zero_rows_without_raising`
- `TestDedupAttributedRows::test_last_in_file_wins_for_an_intra_file_duplicate`
- `TestDedupAttributedRows::test_first_across_files_wins_and_repeat_is_recorded`
- `TestDedupAttributedRows::test_no_duplicates_leaves_every_row_and_reports_empty`

## Lint / format

`python3 -m ruff check scripts/project_metrics/tests/test_cost_collector.py` — clean.
`python3 -m ruff format --check scripts/project_metrics/tests/test_cost_collector.py` — clean.

## Step 2


## Command

```
python3 -m pytest hooks/test_capture_session.py --no-cov -q -p no:cacheprovider
```

```
127 passed in 0.34s
```

Result: pass=127 fail=0 skip=0

## Scoped group run (Tests: groups=[hooks-lifecycle] tier=step selector=auto)

Command: `python3 -m pytest hooks/ tests/test_notify_bg_session_state.py --no-cov -q -p no:cacheprovider`

```
901 passed in 50.26s
```

Result: pass=901 fail=0 skip=0

Tier: step
Groups: hooks-lifecycle

## Lint / format

`ruff format hooks/capture_session.py` — 1 file left unchanged.
`ruff check hooks/capture_session.py --fix` — all checks passed.

## Other gates

`python3 scripts/check_id_citation_discipline.py --files hooks/capture_session.py` — scanned 1 code file(s); 0
id-citation violations.

## Step 4


## Command

```
python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider
```

```
22 passed in 0.10s
```

Result: pass=22 fail=0 skip=0

## Lint / format

`python3 -m ruff format scripts/project_metrics/collectors/cost_collector.py` — 1 file left unchanged.
`python3 -m ruff check scripts/project_metrics/collectors/cost_collector.py` — all checks passed.

## Id-citation discipline

`python3 scripts/check_id_citation_discipline.py` — zero findings in `cost_collector.py` (26 pre-existing
findings elsewhere in the repository, unrelated to this step).

## Scope confirmation

`git diff --stat -- scripts/project_metrics/runner.py` — no output (untouched, per Step 4's Done-when).
`git status --short scripts/project_metrics/` — only `cost_collector.py` is new/untracked.

## Step 4 (post-review addendum, orchestrator)

After the light-review fixes: `hooks/test_capture_session.py` -> `128 passed` (Step 2, one regression test added); `scripts/project_metrics/tests/test_cost_collector.py` -> `23 passed` (Step 4, one regression test added).
Command: `python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider`
Raw pytest summary: `23 passed in 0.06s`
Result: pass=23 fail=0 skip=0

## Step 5


## Step 5

## Command

```
python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider
```

```
25 failed, 24 passed in 0.47s
```

Result: pass=24 fail=25 skip=0

Log: `.ai-work/process-economy-p3-5/logs/step5.log`

### Failures

All 25 new failures are `ImportError`/`AttributeError` -- the expected RED mode, since none of the aggregate-pass
names (`TierResolved`, `TierAmbiguous`, `TierUnknown`, `parse_calibration_log`, `resolve_tier`, `PipelineBucket`,
`build_pipeline_buckets`, `unresolved_agent_type_share`, `Coverage`, `summary_row_slug`,
`summary_row_is_rollup_unattributed`, `_audit_totals`, `compute_f12_cell`, `CostCollector`) exist yet in
`scripts/project_metrics/collectors/cost_collector.py`. The 24 passing tests are the Step 3/4 read-pass suite
(23, unmodified) plus the one new fixture-integrity test
(`TestAggregatePassFixtureIntegrity::test_summary_rollup_fixture_carries_the_measured_token_total`), which reads
only the committed fixture file and imports no production code, so it is correctly green before Step 6.

Failing node ids (25):

- `TestCostCollectorResolve::test_registers_as_the_cost_collector_at_tier_zero`

- `TestParseCalibrationLog::test_normalizes_the_actual_tier_cells_leading_alphabetic_token`
- `TestResolveTier::test_resolves_a_single_agreeing_slug_to_its_tier[process-economy-p3-2-adopt]`
- `TestResolveTier::test_resolves_a_single_agreeing_slug_to_its_tier[process-economy-p3-6-adopt]`
- `TestResolveTier::test_resolves_a_disagreeing_slug_to_ambiguous_with_every_tier_listed[sentinel-fanout-audit-expected_tiers0]`
- `TestResolveTier::test_resolves_a_disagreeing_slug_to_ambiguous_with_every_tier_listed[process-economy-phase1-expected_tiers1]`
- `TestResolveTier::test_resolves_a_disagreeing_slug_to_ambiguous_with_every_tier_listed[process-economy-p2-residual-expected_tiers2]`
- `TestResolveTier::test_resolves_a_slug_absent_from_the_calibration_log_to_unknown`
- `TestBuildPipelineBuckets::test_folds_same_slug_rows_into_one_bucket_carrying_the_resolved_tier`
- `TestBuildPipelineBuckets::test_an_unjoinable_slug_still_gets_its_own_bucket_marked_unknown`
- `TestBuildPipelineBuckets::test_per_tier_and_per_agent_type_totals_never_disagree_with_the_grand_total`
- `TestUnresolvedAgentTypeShare::test_reports_the_unresolved_share_of_attributed_rows`
- `TestUnresolvedAgentTypeShare::test_zero_attributed_rows_reports_a_zero_share_without_dividing_by_zero`
- `TestSummaryRowCensusHelpers::test_a_summary_row_without_pipeline_slug_reads_as_unknown`
- `TestSummaryRowCensusHelpers::test_a_summary_row_carrying_pipeline_slug_reads_its_real_slug`
- `TestSummaryRowCensusHelpers::test_the_measured_14_billion_token_rollup_is_counted_as_quarantined`
- `TestSummaryRowCensusHelpers::test_a_summary_row_with_no_token_rollup_is_not_quarantined`
- `TestAuditTotals::test_consistent_counts_produce_no_issues`
- `TestAuditTotals::test_a_bucket_sum_mismatched_with_coverage_names_the_invariant`
- `TestAuditTotals::test_a_quarantine_census_mismatched_with_the_total_names_the_invariant`
- `TestCostCollectorFaultInjection::test_a_misclassified_row_reaching_a_total_is_rejected_with_no_totals_published`
- `TestCostCollectorResolve::test_resolves_available_when_the_wal_exists`
- `TestCostCollectorResolve::test_resolves_not_applicable_when_no_observability_artifacts_exist`
- `TestComputeF12Cell::test_renders_na_with_a_reason_when_one_tier_has_zero_attributed_rows`
- `TestComputeF12Cell::test_renders_the_ratio_with_both_sample_sizes_and_basis_when_both_tiers_qualify`

## Lint / format

`ruff format scripts/project_metrics/tests/test_cost_collector.py` -- 1 file left unchanged.
`ruff check --fix scripts/project_metrics/tests/test_cost_collector.py` -- all checks passed.

## Id-citation discipline

`python3 scripts/check_id_citation_discipline.py --files scripts/project_metrics/tests/test_cost_collector.py scripts/project_metrics/tests/fixtures/cost/calibration_log_excerpt.md scripts/project_metrics/tests/fixtures/cost/summary_rollup_unattributed.jsonl`
-- scanned 1 code file(s); 0 id-citation violations (six findings from an earlier draft -- `REQ-`/`Step N`
references in docstrings and comments -- fixed by rephrasing to describe behavior instead).

## Step 6


## Step 6

## Command

```
python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider
```

```
49 passed in 0.22s
```

## Step 6 (post-review addendum, F1 fix)

RED confirmed against the pre-fix code: the new test
`TestCostCollectorFaultInjection::test_a_miscounted_dedup_drop_is_rejected_with_no_totals_published` failed with
`ValueError: not enough values to unpack (expected 3, got 2)` at `_lying_dedup`'s call into the (pre-fix,
2-tuple-returning) `_dedup_by_agent_id` -- confirming the test exercises code that did not yet exist. After the
fix (`_dedup_by_agent_id` returns its own `len(items) - len(deduped)` as a third value; `Coverage` gains
`duplicates_dropped: int = 0`; `total_agent_stop_rows` is now sourced from `SourceRef.agent_stop_rows`, summed
over the read pass's own per-source counts, never from the census; `_audit_totals` check-1 reconciles
`attributed_rows + quarantine + duplicates_dropped` against that read-side total):

```
python3 -m pytest scripts/project_metrics/tests/test_cost_collector.py --no-cov -q -p no:cacheprovider
```

```
50 passed in 0.13s
```

## Scoped group run (Tests: groups=[project-metrics] tier=step selector=auto)

Command: `python3 -m pytest scripts/project_metrics/tests/ --no-cov -q -p no:cacheprovider`

```
755 passed in 20.15s
```

Tier: step
Groups: project-metrics

## Lint / format

`python3 -m ruff format scripts/project_metrics/collectors/cost_collector.py scripts/project_metrics/tests/test_cost_collector.py` -- 2 files left unchanged.
`python3 -m ruff check scripts/project_metrics/collectors/cost_collector.py scripts/project_metrics/tests/test_cost_collector.py` -- all checks passed.

## Id-citation discipline

`python3 scripts/check_id_citation_discipline.py --files scripts/project_metrics/collectors/cost_collector.py scripts/project_metrics/tests/test_cost_collector.py`
-- scanned 2 code file(s); 0 id-citation violations (two findings from an earlier draft -- `REQ-10`/`REQ-14`
references in docstrings -- fixed by rephrasing to describe behavior instead).

## Scope confirmation

`git diff --stat -- scripts/project_metrics/schema.py scripts/project_metrics/runner.py` -- no output
(untouched). `git status --short scripts/` -- `scripts/project_metrics/collectors/cost_collector.py` and
`scripts/project_metrics/tests/test_cost_collector.py` modified (the test file is in scope for this fix per the
reviewer's explicit RED-first instruction; no other file touched).

## Mutation sensor

Command: `python3 scripts/mutation_sensor.py --targets scripts/project_metrics/collectors/cost_collector.py --tests scripts/project_metrics/tests/test_cost_collector.py`

`not-flat-layout: scripts/project_metrics/collectors/cost_collector.py -> .../collectors, scripts/project_metrics/tests/test_cost_collector.py -> .../tests` --
the expected, acceptable outcome per this plan's Pre-Mortem item 1 (the sensor's v1 flat-only limitation; every
`project_metrics` collector lives in this same nested two-directory shape). Re-confirmed unchanged after the F1
fix (the file layout did not change).

Mutation: unavailable reason=not-flat-layout

Result: pass=50 fail=0 skip=0

## Step 7 (orchestrator)

Command: `python3 -m pytest scripts/project_metrics/tests/ --no-cov -q -p no:cacheprovider`
Raw pytest summary: `755 passed in 9.71s` (runner file alone: `30 passed`)
Result: pass=755 fail=0 skip=0

## Step 9


Command: `python3 -m pytest scripts/project_metrics/tests/test_cost_report_section.py --no-cov -q -p no:cacheprovider`

Result: pass=0 fail=10 skip=0
Duration: 0.16s

### Failures

All 10 tests fail identically at collection-adjacent import time (deferred
`from scripts.project_metrics._report_sections import render_cost` inside
each test body), the expected RED signature — `render_cost` does not yet
exist:

```
ImportError: cannot import name 'render_cost' from 'scripts.project_metrics._report_sections'
(/Users/fperez/dev/praxion/.claude/worktrees/process-economy-p3-5/scripts/project_metrics/_report_sections.py)
```

Failing node ids:
- `TestCostHeading::test_renders_a_cost_markdown_heading`
- `TestTokenComponentTables::test_per_pipeline_table_row_carries_all_four_token_components_beside_the_total`
- `TestTokenComponentTables::test_per_tier_table_row_carries_all_four_token_components_beside_the_total`
- `TestTokenComponentTables::test_per_agent_type_table_row_carries_all_four_token_components_beside_the_total`
- `TestStandardVsLightweightCell::test_withheld_shape_names_the_reason_naming_the_missing_tier`
- `TestStandardVsLightweightCell::test_rendered_shape_prints_both_sample_sizes_and_the_basis`
- `TestUnresolvedAgentTypeShare::test_per_agent_type_section_states_the_unresolved_share`
- `TestCoverageLine::test_renders_the_attributed_over_total_coverage_line`
- `TestNoRegressionToSiblingContracts::test_aggregate_columns_stay_the_frozen_sixteen_column_golden_tuple`
- `TestNoRegressionToSiblingContracts::test_no_metrics_log_writer_references_a_cost_key`

Heading-collision grep (run before authoring the test file):
`grep -rn "## Cost" scripts/project_metrics/*.py` — zero matches in
`report.py`, `_report_sections.py`, `_report_deep_dive.py`. No collision.

Lint/format: `ruff format` clean (1 file unchanged), `ruff check --fix`
clean (all checks passed). `check_id_citation_discipline.py`: no findings
for this file.

## Step 10


## Scoped: test_cost_report_section.py

Command: `python3 -m pytest scripts/project_metrics/tests/test_cost_report_section.py --no-cov -q -p no:cacheprovider`

Duration: 0.04s

Tier: step
Groups: [project-metrics]

Result: pass=10 fail=0 skip=0

## Package: scripts/project_metrics/tests/

Command: `python3 -m pytest scripts/project_metrics/tests/ --no-cov -q -p no:cacheprovider`

One pre-existing regression surfaced and fixed before the final run below:
`TestGoldenMarkdownByteComparison::test_render_markdown_matches_golden_fixture_modulo_timestamp`
failed on first run because `golden_report.md` predates the `## Cost`
section — fixed by regenerating the fixture's byte range for the reference
report's (cost-collector-absent) input, not by changing the assertion.

### Dashboard build (consumer check, deferred from Step 8)

Command: `cd dashboard_app && ./node_modules/.bin/next build`

Exit code: 1 — **not a metrics-JSON regression**. `dashboard_app/node_modules`
in this worktree is a symlink to
`/Users/fperez/dev/praxion/dashboard_app/node_modules` (outside this
worktree's filesystem subtree). Turbopack (Next.js 16.2.10) refuses to
resolve packages through a symlink it judges to point "out of the filesystem
root" and panics before touching any application code:

```
Error [TurbopackInternalError]: Symlink [project]/node_modules is invalid, it points out of the filesystem root
```

This is a worktree/Turbopack environment limitation, not a defect introduced
by the `cost` root JSON key, the new `tool_availability["cost"]` entry, or
the `## Cost` Markdown section — the failure occurs during Turbopack's own
entrypoint resolution, before any page or view-model referencing `report.json`
is reached. Per this step's instructions, not fixed here (out of scope: the
dashboard's build tooling, not the cost collector).

Duration: 9.36s

Result: pass=765 fail=0 skip=0

## Step 10 (orchestrator addendum -- dashboard build)

`pnpm install --offline --frozen-lockfile` (26.4 s, pnpm 11.0.9) then `./node_modules/.bin/next build` from `dashboard_app/` in the worktree: route table rendered (`/metrics` among the dynamic routes), `.next/BUILD_ID` written. Consumer-check build half: PASS.
Command: `python3 -m pytest scripts/project_metrics/tests/ --no-cov -q -p no:cacheprovider`
Raw pytest summary: `765 passed in 21.69s`
Result: pass=765 fail=0 skip=0

## Step 12 (doc-engineer)


No pytest invocation (documentation-only step; `Tests: none`).

## Validator outputs

```
$ python3 skills/skill-crafting/scripts/validate_references.py --file docs/architecture.md
scanned 1 file(s); no findings
no findings

$ python3 skills/skill-crafting/scripts/validate_references.py --file docs/metrics/README.md
scanned 1 file(s); no findings
no findings

$ python3 skills/skill-crafting/scripts/validate_references.py --file commands/project-metrics.md
scanned 1 file(s); no findings
no findings

$ python3 scripts/check_shipped_artifact_isolation.py
scanned 498 shipped file(s); 0 violations.
```

## Manual path verification (docs/architecture.md's Done-when criterion)

All nine paths cited in the new "Pipeline Cost Collector" row confirmed present via `[ -f ... ]`:
`scripts/project_metrics/collectors/cost_collector.py`, `scripts/project_metrics/runner.py`,
`scripts/project_metrics/_report_sections.py`, `scripts/project_metrics/report.py`,
`scripts/project_metrics/tests/test_cost_collector.py`,
`scripts/project_metrics/tests/test_cost_report_section.py`, `hooks/capture_session.py`,
`docs/metrics/README.md`, `commands/project-metrics.md` — all OK.

## Step 13 (health-guards gauntlet, orchestrator)

| Guard | Result |
|---|---|
| `measure_token_budget.py` | 16,606 / 25,000 (tokenizer basis) -- unchanged |
| `sync_canonical_blocks.py --check` | 9 blocks / 3 files in sync |
| `check_state_ledgers.py --check` | 0 blocking, 1 advisory (pre-existing) |
| `check_id_citation_discipline.py` (repo-wide) | findings in 8 files, none among this branch's 24 changed paths (all present at base `c934d256`) |
| `check_shipped_artifact_isolation.py` | 498 shipped files, 0 violations |
| `check_metrics_freshness.py --repo-root .` | STALE before Step 14 (`hooks/capture_session.py` ranked #6, modified by this pipeline); exit 0 after the Step 14 run regenerated the report |
| `check_adr_reciprocity.py --check` | no violations across 390 ADRs |
| `validate_references.py --file` (3 docs) | no findings |
| dashboard `next build` (worktree, offline pnpm install) | route table rendered, `.next/BUILD_ID` written |

Full suite: appended below when the detached run finishes.

## Step 14 (dogfood, orchestrator)

Worktree: `python3 -m scripts.project_metrics --mechanical-only` -> exit 0; report `METRICS_REPORT_2026-09-23_06-38-49`; `## Cost` present with `coverage: 58 attributed / 5351 total`; quarantine parent-sourced 0 / pre-attribution 286 / unparsed 4932 / summary-rollup-unattributed 42; duplicates_dropped 75; per-pipeline rows for process-economy-p3-5 (14, tier unknown), praxion (7, unknown), process-economy-p3-2-adopt (15, Standard), process-economy-p3-6-adopt (22, Standard); unresolved agent-type share 0 of 58; ratio cell `n/a -- no attributed rows at tier Lightweight`; JSON `cost.status: ok`, `issues: []`, nine sources (five WAL/archive, four summaries), `tool_availability.cost.status: available`. `check_metrics_freshness.py` -> exit 0.
Symmetry (collector rooted at the worktree vs at main, same code): status ok / ok; 58 / 5351 both; source sets equal (9 = 9), coverage equal.
Main-cwd full run: deferred to post-merge (main's package predates the collector); recorded as a deviation in `WIP.md` and `LEARNINGS.md`.

## Step 13 (full suite, orchestrator)

Command: `uv run --frozen pytest --cov-fail-under=80 -q` (bare CI invocation, detached: nohup + done-file, from the worktree at `012abffe`)
Raw pytest summary (before classification): `2 failed, 4906 passed, 1 warning in 572.64s (0:09:32)` -- the two red node ids are exactly the baseline's `td-162` / `td-222` rows (`TEST_BASELINE.md`); 4906 = baseline 4843 + this pipeline's 63 new tests.
Coverage: 83.66% (threshold 80% reached; baseline 83.60%); `coverage.xml` regenerated by this run.
Result: pass=4906 fail=0 skip=0 preexisting=2
