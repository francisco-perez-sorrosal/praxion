# Spec: Sentinel Phase B -- Family-Dispatch Envelope Consolidation

**Task slug**: `sentinel-phase-b`
**Tier**: Standard
**Created**: 2026-09-14T07:00:20Z
**Pipeline run**: 2026-09-13 to 2026-09-14
**Archived**: 2026-09-13
**Status**: completed
**Complexity**: large
**ADRs**: `dec-draft-34af7f36` (family envelope additive; AC10 stays sentence-dispatched; DH01/DH06 registered A rows; EC07 Invocation string)

## Requirements

Seventeen requirements. IDs are stable; the implementation-planner orders them.

**REQ-01** — When the sentinel dispatches the DH dimension, and `.ai-state/decisions/` and `scripts/adr_health.py` are
present, the system emits DH01, DH02, DH04, DH05 and DH06 as keyed-envelope findings from one
`adr_health.py --json` run, **so that** five rows and five sentence fragments collapse into one table row and one
subprocess call.

**REQ-02** — When the sentinel dispatches the GL dimension, and `scripts/check_gate_liveness.py` is present, the system
emits GL02, GL04, GL05 and GL06 as keyed-envelope findings whose `check` field carries the **GL id** (the
`forbidden-pattern`/`uninvoked-gate`/`ambient-import`/`discarded-verdict` classification moving to a `kind` field),
**so that** the runner aggregates them under the ids the sentinel report uses rather than under detector-internal
class names.

**REQ-03** — When `.ai-state/DESIGN.md` and `.ai-state/decisions/` both exist, the system reports AC14 from a flat
envelope emitted by `check_design_checkpoint.py --json`, advisory on `len(unfolded)` and FAIL only on a
`malformed`/`absent` checkpoint state, **so that** the un-folded count never reads as a gate.

**REQ-04** — When `.ai-state/metrics_reports/` is present, the system reports TD06 from a flat envelope emitted by
`check_metrics_freshness.py --json`, WARN on `stale` or a non-empty `withheld`, with `hotspots_touched` surfaced in
`examined`, **so that** TD01 filing can still read the barred-path list from the one digest.

**REQ-05** — When `.ai-state/metrics_reports/` is present, the system reports RD01 from a flat envelope emitted by
`check_readiness_feedback.py --json`, Important when `below_threshold`, annotated when `mechanical_only`, **so that**
the readiness verdict arrives with its own confidence qualifier attached.

**REQ-06** — When `.ai-state/specs/` holds spec files, the system reports SH08 from a flat envelope emitted by
`check_spec_archival_gap.py --json`, Important when `gap: true`, **so that** the archival gap is one digest row rather
than a separate call and a separate sentence.

**REQ-07** — When `.ai-work/` is present, the system reports P06 from a flat envelope wrapping
`check_p06_task_brief.py`'s existing JSON **list** (each element already carries `check: "P06"`), **so that** the
runner — which calls `payload.get(...)` and would raise on a bare list — can consume it.

**REQ-08** — When `scripts/check_aac_golden_rule.py` exists, the system reports EC07 from a flat envelope wrapping the
audit-mode JSON list, dispatched as `python3 scripts/check_aac_golden_rule.py --mode=audit --json`, **so that** the
only mode that emits JSON is the one the table invokes.

**REQ-09** — When `.ai-work/` is present, the system reports P08 from an envelope **added to**
`clean_work_safety.py --json`'s existing object, with the "≥3 SAFE dirs idle ≥14 days" predicate evaluated in the
script, **so that** the threshold lives in code with a canary instead of in a row of sentinel prose, while
`/clean-work`'s existing readers of `task_dirs`/`summary` keep working byte-for-byte.

**REQ-10** — When the sentinel measures the always-loaded budget, the system reports T02 from an envelope **added to**
`measure_token_budget.py --json`'s existing object, FAIL when `over_by > 0` or the listing exceeds its ceiling, with
`examined` naming the `basis` (`tokenizer` vs `ratio`), **so that** an unmeasured (ratio-derived) reading can never be
mistaken for a governed FAIL.

**REQ-11** — When the sentinel evaluates AC10, and ≥1 in-scope architecture markdown file exists, the system continues
to invoke `python3 scripts/aac_fence_validator.py <file>` per file and map its exit code to the AC10 verdict, **so
that** `.github/workflows/architecture.yml`'s `xargs`-driven per-file invocation and the architect-validator's
`Bash(python3 scripts/aac_fence_validator.py:*)` allowlist (dec-275) keep the single-file contract they depend on.

**REQ-12** — When a script is dispatched from the Family table, the system carries no second dispatch instruction for
it in Phase-3 prose, **so that** the reader has one dispatch site per check. This includes deleting the **480-byte
`P03` sentence Phase A left behind** — `check_agent_lifecycle_pairing.py` is already a table row, so that sentence is
pure duplication today.

**REQ-13** — When the row/registry/script triangle runs, the system scopes Leg 1 over **every** row citing a registered
script with no exemption list, **so that** a conforming row can no longer be parked outside the guard. (Measured
precondition: DH01 and DH06 are the *only* rows citing a registered script without a registry entry — see
§ Judgement (b).)

**REQ-14** — When an implementer completes a step that ran tests and **no test-engineer was paired on that step**, the
system records the `tests:` entries for that step in `traceability.yml` and writes `TEST_RESULTS.md`, **so that** the
REQ→test layer has an owner in every pairing configuration rather than only when a test-engineer exists.

**REQ-15** — When `check_topology_conformance.py` runs, the system emits **TT07**: every `test_*.py` under `tests/`,
`scripts/`, `hooks/` and `fitness/` is claimed by exactly one `TEST_TOPOLOGY.md` group selector, FAIL per orphan, per
overlap and per dangling selector, **so that** a test file added without a topology group is caught by the sentinel
rather than by a hand-run instrument.

**REQ-16** — When a `SubagentStop` payload is enriched, and the subagent transcript
`<dirname(transcript_path)>/<session_id>/subagents/agent-<agent_id>.jsonl` exists, the system reads **that** file and
counts only assistant lines whose `agentId` equals the stop's `agent_id` — a line with **no** `agentId` does not
match — **so that** `agent_stop` rows carry the subagent's own tokens/model/duration instead of the parent session's
cumulative totals.

**REQ-17** — When neither the subagent file exists nor any payload-transcript line is tagged with the agent id, the
system degrades every enrichment field to `None`, **so that** an honest empty beats a plausible wrong number
(286/286 `agent_stop` rows since P0.4 carry the parent's figures — a Sonnet planner recorded as `claude-fable-5-1`
with 332,258 output tokens against its real 103,573).

## Traceability

Rendered from the merged `.ai-work/sentinel-phase-b/traceability.yml` (15 fragments: A1-A7, B1-B4, C1-C2, R1-R2), cross-checked against `VERIFICATION_REPORT.md § Spec Conformance`. Every entry recorded against a requirement in the reconciled YAML is listed below -- no sampling. Cells group entries by file: the leading count is the total number of individual YAML list items (tests or implementation symbols) for that requirement; the parenthetical after each backtick-quoted path names every symbol/test recorded against that file. Status is PASS for all 17 requirements per the verification report's Spec Conformance section (17 PASS, 0 UNTESTED, 0 FAIL). No REQ carries `architectural_elements:`, so the three-column back-compat format applies.

**Summary**: 17/17 REQs PASS (tests and implementation both populated). 0 UNTESTED, 0 FAIL.

| Requirement | Test(s) | Implementation | Status |
|---|---|---|---|
| REQ-01 | 15 test(s) — `scripts/test_adr_health.py` (test_check_ids_repoint_leaves_envelope_shape_unchanged, test_canary_dh01_removed_by_later_finding_is_family_tagged, test_canary_dh02_renamed_finding_is_family_tagged, test_canary_dh04_reopen_candidate_is_a_family_finding, test_canary_dh05_widening_verdict_is_a_suggested_family_finding, test_canary_dh05_discriminating_verdict_emits_no_family_finding, test_canary_dh06_status_edge_conflict_is_a_family_finding, test_family_findings_are_all_check_tagged_and_disjoint_from_decay_findings, test_canary_reopen_candidate_and_status_edge_conflict_each_print_exactly_once, test_class_filter_excludes_out_of_class_entries_from_both_streams, test_json_payload_carries_both_streams_with_decay_findings_the_larger_set, test_decay_findings_and_findings_key_names_are_the_public_contract); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 14 symbol(s) — `scripts/adr_health.py` (classify(), _dh01_dh02_findings(), _dh04_findings(), _dh05_findings(), _dh06_findings(), _family_skipped(), _family_examined(), main()); `agents/sentinel.md` (DH01, DH02, DH04, DH05, DH06); `commands/decisions.md` | PASS |
| REQ-02 | 8 test(s) — `scripts/test_check_gate_liveness.py` (test_flags_dead_grep_contradiction, test_canary_the_documented_golden_bad_case_fires, test_flags_a_gate_script_nothing_invokes, test_canary_flags_a_hook_guard_no_registration_names, test_canary_flags_a_hook_whose_findings_exit_cannot_block); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 3 symbol(s) — `scripts/check_gate_liveness.py` (_finding(), classify(), (module docstring citation fix)) | PASS |
| REQ-03 | 5 test(s) — `scripts/test_check_design_checkpoint.py` (test_canary_malformed_checkpoint_produces_an_ac14_fail_finding, test_unfolded_suffix_produces_a_warn_finding_never_a_fail); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 3 symbol(s) — `scripts/check_design_checkpoint.py` (_ac14_findings(), _ac14_withheld(), check_design_checkpoint()) | PASS |
| REQ-04 | 6 test(s) — `scripts/test_check_metrics_freshness.py` (test_canary_flags_hotspot_rewritten_after_the_report, test_canary_withheld_report_produces_a_td06_warn_finding, test_fresh_report_produces_no_findings); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 2 symbol(s) — `scripts/check_metrics_freshness.py` (_td06_findings(), evaluate_freshness()) | PASS |
| REQ-05 | 6 test(s) — `scripts/test_check_readiness_feedback.py` (test_canary_json_envelope_flags_rd01_finding, test_no_false_positive_envelope_findings_empty_at_floor, test_substrate_absent_envelope_reports_skipped_not_a_finding); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 2 symbol(s) — `scripts/check_readiness_feedback.py` (rd01_envelope(), _rd01_findings()) | PASS |
| REQ-06 | 6 test(s) — `scripts/test_check_spec_archival_gap.py` (test_canary_json_envelope_flags_sh08_finding, test_no_gap_envelope_findings_empty_when_spec_is_fresh, test_substrate_absent_envelope_reports_skipped_not_a_finding); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 2 symbol(s) — `scripts/check_spec_archival_gap.py` (sh08_envelope(), _sh08_findings()) | PASS |
| REQ-07 | 5 test(s) — `scripts/test_check_p06_task_brief.py` (test_canary_p06_fires_on_known_bad_input_json_mode, test_json_output_is_flat_envelope_not_bare_list); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 1 symbol(s) — `scripts/check_p06_task_brief.py` (_build_envelope()) | PASS |
| REQ-08 | 7 test(s) — `scripts/test_check_aac_golden_rule.py` (test_audit_mode_with_clean_history_no_findings, test_audit_mode_with_violations_emits_findings, test_audit_mode_with_overrides_no_findings, test_audit_json_output_is_flat_envelope_not_bare_list); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 2 symbol(s) — `scripts/check_aac_golden_rule.py` (_build_audit_envelope(), _emit_audit_findings()) | PASS |
| REQ-09 | 7 test(s) — `scripts/test_clean_work_safety.py` (test_envelope_keys_are_additive_beside_the_existing_payload, test_canary_three_stale_safe_dirs_trigger_the_advisory, test_below_threshold_stale_safe_count_produces_no_finding, test_missing_ai_work_root_skips_with_substrate_absent); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 3 symbol(s) — `scripts/clean_work_safety.py` (_p08_findings(), _p08_envelope(), render_json()) | PASS |
| REQ-10 | 10 test(s) — `scripts/test_measure_token_budget.py` (test_t02_envelope_keys_are_additive_beside_the_existing_payload, test_canary_tokenizer_basis_over_budget_produces_a_fail_finding, test_ratio_basis_over_budget_never_produces_a_fail_finding, test_tokenizer_basis_under_budget_has_no_findings, test_listing_over_frozen_ceiling_fails_on_matching_tokenizer_basis, test_missing_baseline_skips_the_listing_ceiling_check, test_basis_mismatch_against_the_frozen_ceiling_skips_the_comparison); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 3 symbol(s) — `scripts/measure_token_budget.py` (_t02_frozen_listing_ceiling(), _t02_findings(), _t02_envelope()) | PASS |
| REQ-11 | 1 test(s) — `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract) | 1 symbol(s) — `agents/sentinel.md` (AC10 catalog row (no-op preservation, verified byte-identical before/after via git diff)) | PASS |
| REQ-12 | 1 test(s) — `fitness/tests/test_gate_canary_coverage.py` (test_build_doc_manifest_reaches_canary_coverage_via_sentinel) | 1 symbol(s) — `agents/sentinel.md` (Phase 3 prose paragraph collapse (dead P03/P08/DH*-via-family sentences removed; F11's build_doc_manifest.py remedy phrase untouched)) | PASS |
| REQ-13 | 1 test(s) — `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 4 symbol(s) — `agents/sentinel.md` (DH01, DH06); `tests/test_sentinel_row_contract.py` (EXTRACTED_CHECKS); `tests/test_sentinel_check_triangle.py` (assert_check_registration_triangle) | PASS |
| REQ-14 | 1 test(s) — `fitness/tests/test_gate_canary_coverage.py` (test_every_declared_check_has_canary) | 1 symbol(s) — `agents/implementer.md` (step-5-write-traceability-entries) | PASS |
| REQ-15 | 9 test(s) — `scripts/test_check_topology_conformance.py` (test_tt07_flags_orphaned_test_file, test_tt07_flags_file_claimed_by_two_groups, test_tt07_flags_dangling_selector_arg, test_tt07_fully_covered_corpus_is_clean, test_check_ids_declares_the_five_topology_checks, test_no_topology_file_skips_tt01_tt02_tt05_tt07); `tests/test_sentinel_row_contract.py` (test_every_extracted_row_satisfies_the_contract, test_family_table_rows_column_matches_the_registry); `tests/test_sentinel_check_triangle.py` (test_every_extracted_check_is_bound_by_the_triangle) | 5 symbol(s) — `scripts/check_topology_conformance.py` (_tt07_corpus(), _tt07_selector_hits(), _tt07_examine(), _tt07_findings(), _check_tt07()) | PASS |
| REQ-16 | 3 test(s) — `hooks/test_capture_session.py` (TestSubagentTranscriptUsage::test_subagent_file_wins_over_untagged_parent_lines, TestSubagentTranscriptUsage::test_filters_to_matching_agent_id_when_agentid_is_present, TestSubagentTagCheckMutationProbe::test_removing_the_tag_equality_check_reintroduces_the_wrong_numbers) | 2 symbol(s) — `hooks/capture_session.py` (_subagent_own_transcript_path(), _sum_subagent_transcript()) | PASS |
| REQ-17 | 8 test(s) — `hooks/test_capture_session.py` (TestSubagentTranscriptUsage::test_lines_without_agentid_are_never_counted, TestSubagentTranscriptUsage::test_missing_transcript_path_degrades_every_field_to_none, TestSubagentTranscriptUsage::test_unreadable_transcript_degrades_every_field_to_none, TestSubagentTranscriptUsage::test_sums_usage_and_takes_model_and_duration_from_matching_lines, TestSubagentTranscriptUsage::test_malformed_line_is_skipped_not_fatal, TestSubagentTranscriptUsage::test_degraded_result_carries_usage_source_none, TestSubagentTranscriptUsage::test_build_observation_writes_transcript_fields_onto_agent_stop_row, TestSubagentTranscriptUsage::test_agent_start_rows_carry_no_transcript_fields) | 1 symbol(s) — `hooks/capture_session.py` (_sum_subagent_transcript()) | PASS |

## Key Decisions

Four architect decisions landed under one ADR draft, `dec-draft-34af7f36`, plus one implementation-planner traceability-mapping judgement extending the same feature (full context copied from `LEARNINGS.md § Decisions Made`):

**[systems-architect] The family envelope is additive, so a dict-emitting tool needs no wrapper (dec-draft-34af7f36)**:
`run_check_families.py` reads exactly six keys from a family payload (`checks`/`check`, `findings`, `skipped`,
`examined`, `bound`, `withheld`), so those keys can be added beside a script's existing `--json` keys without breaking
any consumer. `clean_work_safety.py` (P08) and `measure_token_budget.py` (T02) therefore become in-place family
adapters. **Why**: a wrapper is a new component, a new canary and a new registry entry bought for one Bash call each,
while the additive envelope costs zero components and zero consumer churn — verified that `commands/clean-work.md`
reads `task_dirs`/`summary` by key and that `check_token_ratchet.py` / `apply_skill_description_diet.py` import the
module rather than its CLI JSON. **Alternatives**: a thin wrapper script per tool (rejected on price and component
count); leaving both as four-part sentence rows (rejected — together they cost 1,797 row bytes and two Bash calls).

**[systems-architect] AC10 stays sentence-dispatched (dec-draft-34af7f36)**: `aac_fence_validator.py` keeps its
per-file positional contract; no wrapper, no in-place `--json` corpus mode. **Why**: two surfaces outside the sentinel
depend on exactly that shape — `.github/workflows/architecture.yml:264`'s `xargs -r -I {} python3
scripts/aac_fence_validator.py {}` and dec-275's architect-validator allowlist entry — and AC10's value is the
smallest in the batch (a 333-byte row, the smallest of eighteen, over an in-scope corpus of exactly two files, so two
Bash calls). **Alternatives**: a wrapper family script (rejected: worst byte-and-call-per-step ratio in the batch); an
in-place corpus-walking mode (rejected: adds a second responsibility to a script two surfaces depend on).

**[systems-architect] DH01 and DH06 become registered A rows and `_LEGACY_CITING_ROWS` is deleted
(dec-draft-34af7f36)**: `adr_health.py` already computes both — DH01 is the `removed-by-later` decay class (line 752;
`--only removed-by-later` already filters it), DH06 is the top-level `status_edge_conflicts` list (line 571). **Why**:
leaving them to LLM judgment spends sweep turns on a question a script has already answered, and they are the two
largest single-row savings in the DH block (−353 B, −775 B). The exemption is deleted rather than emptied because a
measured probe shows DH01/DH06 are the *only* rows citing a registered script without a registry entry — Leg 1 then
becomes unconditional, which is strictly stronger than an exemption with a guard on the exemption.
**Alternatives**: keep both as L-tier prose and shrink the allowlist (rejected on evidence); empty the frozenset but
keep it and its staleness test (rejected on Simplicity First — ~25 lines of vacuously-green test).

**[systems-architect] EC07's table Invocation is `python3 scripts/check_aac_golden_rule.py --mode=audit --json`
(dec-draft-34af7f36)**: exactly 20 flag characters against `_INVOCATION_FLAGS_MAX_CHARS = 20`, quantifier `{0,20}`,
match confirmed by executing the contract's own regex. **Why**: bare `--json` prints nothing — `--help` states JSON is
audit-mode only — so `--mode=audit` is mandatory in the table row. **Alternatives**: `--json --mode=audit` (same 20
chars, also matches; the chosen order reads as mode-then-format and matches the existing EC07 row); leaving EC07 as a
sentence row (rejected — the flag fits).

**[implementation-planner] REQ-11/REQ-12/REQ-14 pin to existing guard tests, not new canaries**: `PLANNER_BRIEF.md` names three existing tests (`test_build_doc_manifest_reaches_canary_coverage_via_sentinel`, `test_every_declared_check_has_canary`, "row-contract tests") as the available pins for the three REQs that have no dedicated script/canary. Assigned by semantic fit rather than list order: REQ-11 (AC10 stays unchanged) → `test_every_extracted_row_satisfies_the_contract` (pins the legacy-row contract AC10's row must keep satisfying); REQ-12 (Phase-3 prose collapse) → `test_build_doc_manifest_reaches_canary_coverage_via_sentinel` (this is the exact test the Risk Assessment names for the "_delegated_gates regex loses canary coverage" risk); REQ-14 (implementer.md prose edit) → `test_every_declared_check_has_canary` (the broadest existing canary-completeness regression pin available, since no script reads implementer.md content at all — confirmed by `SYSTEMS_PLAN.md`'s own grep). **Why**: the verifier FAILs on an empty `tests:` array; inventing a new canary for a requirement the systems-architect explicitly judged canary-less (REQ-14) would be scope creep against `SYSTEMS_PLAN.md § Parallelisation`'s own judgment. **Alternatives**: leave `tests:` empty and let the verifier flag it (rejected — the brief is explicit that this must not happen); write a new no-op test asserting the prose string exists (rejected — ceremony, and the systems plan already concluded no canary is warranted for REQ-14).
