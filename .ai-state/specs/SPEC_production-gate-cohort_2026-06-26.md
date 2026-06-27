# SPEC: Wave 3 — Production-Gate Cohort + Registry Declarative Spine

**Task slug**: `production-gate-cohort`
**Feature**: Add five missing production gates (R3/R4/R5/R9/R13 + A6 producer tail) and grow `artifact_registry.py` into a declarative spine naming, per artifact, the gate that makes it exist
**Tier**: Full
**Pipeline branch**: `main` (in-worktree pipeline)
**Start date**: 2026-06-25
**End date**: 2026-06-26
**Archived**: 2026-06-26
**Status**: Shipped — all acceptance criteria verified; AC8 dogfood (R3 on fresh spec) passes at pipeline end
**ADRs**: `dec-draft-41f7a888` (registry declarative spine — inline string convention), `dec-draft-b8b54821` (gate cohort membership — Full tier, parallel decomposition)

## Feature Summary

Turned the analysis's central theme — "designed obligation without a production mechanism" — into reality by adding five missing production gates and growing `artifact_registry.py` into a declarative spine. Each artifact now declares `production_gate` (the mechanism that makes it exist) and `cleanup_policy` (the declarative lifecycle). Two new detector scripts (`check_spec_archival_gap.py`, `check_calibration_coverage.py`) provide CODE-gate liveness proofs; four new/rewired sentinel checks (SH08, CA03-rewire, P07, P08) surface findings in audits without false-firing on legitimate absent substrate. The verifier gained a LEARNINGS-harvest clause for technical-debt promotion with dedup-key collapse. `architecture-documentation.md` gained a standing `DESIGN_CHANGELOG.md` producer instruction (A6). The cohort is entirely additive — no existing behavior was modified destructively; all pre-existing tests pass unchanged.

## Requirements

- **REQ-01 — registry gate field.** When an `Artifact` row declares `production_gate="<kind>:<ref>"` and `<kind>` is not in `_GATE_KINDS`, the registry self-test fails; when `<kind>` requires a ref and `<ref>` is empty, the self-test fails — so the field cannot silently hold a malformed pointer.
- **REQ-02 — registry back-compat.** When the two new fields are added, all six pre-existing consumer drift assertions still pass, so the four consumers (doc-manifest, dashboard, precompact, eval) remain in sync without source edits.
- **REQ-03 — cleanup policy field.** When an `Artifact` declares a `cleanup_policy` not in `_CLEANUP_POLICIES`, the registry self-test fails — so the declarative lifecycle policy stays well-formed.
- **REQ-04 — spec-archival gap detection.** When the newest `SPEC_*` is more than N days older than ≥K finalized ADRs sharing a tag, `check_spec_archival_gap.py` reports a gap; when specs are fresh, or zero specs exist, it reports none — so a feature shipped without archiving its spec is flagged and a healthy/spec-less project is not.
- **REQ-05 — spec-archival sentinel surfacing.** When `check_spec_archival_gap.py` reports a gap, sentinel SH08 emits WARN; when `.ai-state/specs/` is absent, SH08 skips with an INFO note — so the gap surfaces in the audit without false-firing on absent substrate.
- **REQ-06 — calibration coverage detection.** When Standard/Full pipeline work has merged since the newest `calibration_log.md` row, `check_calibration_coverage.py` reports under-coverage and exits non-zero; when the log is current, it exits zero — and it produces this verdict without invoking the sentinel.
- **REQ-07 — calibration sentinel wiring.** When sentinel CA03 runs, it invokes `check_calibration_coverage.py` for the mechanical verdict (CA01 format + CA02 trend LLM judgment unchanged).
- **REQ-08 — LEARNINGS technical-debt promotion.** When `LEARNINGS.md` carries a `### Technical Debt` entry at pipeline end, the verifier promotes each warranted entry to a `td-NNN` ledger row; duplicate entries (same `dedup_key`) collapse rather than double-file.
- **REQ-09 — ledger-contract preservation.** When the planner or implementer records a debt observation, it is written to `### Technical Debt` in `LEARNINGS.md` and never as a new ledger row — the four-writer contract holds.
- **REQ-10 — honest promotion documentation.** When a reader consults `agent-intermediate-documents.md` on cleanup, it states that prose LEARNINGS sections are `/skill-genesis`-harvested-or-lost and does not claim an automatic merge.
- **REQ-11 — stale-slug advisory.** When `clean_work_safety.py --json` reports `summary.stale_safe ≥ N`, sentinel P08 emits an advisory; when `.ai-work/` is empty or below threshold, P08 passes — so accumulated stale slugs surface without false-firing.
- **REQ-12 — challenge-disposition gate.** When an `INTERFACE_DESIGN.md`/`TRANSACTIONS_DESIGN.md` carries a non-empty `## Architecture Challenges` with no recorded disposition, sentinel P07 emits WARN; when the section is absent or a disposition is recorded, P07 passes.
- **REQ-13 — changelog producer.** When the architect/implementer updates `.ai-state/DESIGN.md`, the `architecture-documentation.md` producer instruction directs deep history into `DESIGN_CHANGELOG.md` — so the file has a standing writer.

## Acceptance Criteria

- [ ] **AC1 (KS gate-liveness):** every new gate ships its proof — CODE gates have a pytest canary; PROMPT/sentinel gates have a documented golden bad-case the check must flag.
- [ ] **AC2 (KS registry fields):** `production_gate` and `cleanup_policy` populated for every core artifact; extended `test_artifact_registry.py` self-consistency tests; six pre-existing drift assertions still pass unchanged.
- [ ] **AC3 (KS grep-amenable + scoped):** R3/R9/R13 sentinel checks are deterministic; skip-with-INFO on absent substrate; no false-positive on healthy/spec-less/empty-`.ai-work/`/absent-`INTERFACE_DESIGN.md` projects.
- [ ] **AC4 (KS R4 mechanical):** `check_calibration_coverage.py` detects coverage lapses standalone; sentinel CA03 rewired to invoke it.
- [ ] **AC5 (KS R5 honest + non-duplicating):** verifier promotes `### Technical Debt` LEARNINGS entries to `td-NNN` rows; dedup_key collapse prevents double-filing; four-writer ledger contract intact; `agent-intermediate-documents.md` documents prose sections as `/skill-genesis`-harvested-or-lost.
- [ ] **AC6 (KS A6 producer):** `DESIGN_CHANGELOG.md` has a named producer instruction — `grep -rl DESIGN_CHANGELOG skills/` returns ≥1.
- [ ] **AC7 (KS no budget regression):** the only always-loaded edit (R5's `agent-intermediate-documents.md`) is net-neutral-or-negative in byte count.
- [ ] **AC8 (dogfood R3):** Wave 3 archives its own behavioral spec to `.ai-state/specs/SPEC_production-gate-cohort_YYYY-MM-DD.md` at pipeline end — the first archived spec since 2026-05-11, exercising the R3 gate against a fresh-spec state (`gap: false`).

## Traceability Matrix

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 — registry gate field | `scripts/test_artifact_registry.py::test_production_gate_kind_is_known`; `::test_production_gate_ref_required_when_kind_demands_it`; `::test_canary_bogus_gate_kind_is_rejected` | `scripts/artifact_registry.py` (`Artifact.production_gate`, `_GATE_KINDS`, `ARTIFACTS`) | PASS |
| REQ-02 — registry back-compat | `scripts/test_artifact_registry.py::test_build_doc_manifest_matches_registry_dashboard_set`; `::test_dashboard_workshop_matches_registry_dashboard_set`; `::test_doc_manifest_and_dashboard_agree`; `::test_precompact_matches_registry_snapshot_set`; `::test_eval_standard_required_matches_registry`; `::test_eval_standard_conditional_matches_registry` | `scripts/artifact_registry.py` (`ARTIFACTS`, `dashboard_artifacts`, `snapshot_artifacts`, `eval_required`, `eval_conditional`) | PASS |
| REQ-03 — cleanup policy field | `scripts/test_artifact_registry.py::test_cleanup_policy_is_known`; `::test_core_artifacts_have_a_gate` | `scripts/artifact_registry.py` (`Artifact.cleanup_policy`, `_CLEANUP_POLICIES`, `ARTIFACTS`) | PASS |
| REQ-04 — spec-archival gap detection | `scripts/test_check_spec_archival_gap.py::test_reports_gap_when_specs_stale_against_adr_cluster`; `::test_no_gap_when_spec_is_fresh`; `::test_skips_when_no_specs_directory`; `::test_no_gap_below_adr_cluster_threshold`; `::test_canary_known_gap_fixture_flags_gap` | `scripts/check_spec_archival_gap.py` | PASS |
| REQ-05 — spec-archival sentinel surfacing | `tests/fixtures/sentinel/spec_archival_gap/` (golden bad-case: stale SPEC + ADR cluster → `gap: true`; no-false-positive control: fresh spec → `gap: false`) | `agents/sentinel.md::SH08` | PASS |
| REQ-06 — calibration coverage detection | `scripts/test_check_calibration_coverage.py::test_reports_under_coverage_when_pipeline_merged_since_last_calibration`; `::test_no_warning_when_log_is_current`; `::test_no_warning_on_docs_or_chore_only_merges`; `::test_runs_to_verdict_without_sentinel`; `::test_canary_stale_log_bites`; `::test_exits_zero_when_no_calibration_log_present` | `scripts/check_calibration_coverage.py` | PASS |
| REQ-07 — calibration sentinel wiring | `tests/fixtures/sentinel/` (golden bad-case: stale log vs. recent pipeline merges → `covered: false`) | `agents/sentinel.md::CA03` (rewired to invoke `check_calibration_coverage.py --json`) | PASS |
| REQ-08 — LEARNINGS tech-debt promotion | Prose verification: verifier LEARNINGS harvest clause applies dedup_key check against ledger before emitting row | `agents/verifier.md` (LEARNINGS harvest section) | PASS |
| REQ-09 — ledger-contract preservation | Prose verification: planner/implementer guidance routes observations to `### Technical Debt` in `LEARNINGS.md`, not ledger rows | `rules/swe/agent-intermediate-documents.md` | PASS |
| REQ-10 — honest promotion documentation | Prose verification: `grep "skill-genesis" rules/swe/agent-intermediate-documents.md` returns the harvested-or-lost clause | `rules/swe/agent-intermediate-documents.md` | PASS |
| REQ-11 — stale-slug advisory | `tests/fixtures/sentinel/stale_slug_advisory/clean_work_safety_stale.json` (golden bad-case: `stale_safe=3` → advisory); `clean_work_safety_clean.json` (no-false-positive: `stale_safe=0` → no advisory) | `agents/sentinel.md::P08` | PASS |
| REQ-12 — challenge-disposition gate | `tests/fixtures/sentinel/challenge_no_disposition/INTERFACE_DESIGN.md` (golden bad-case: non-empty challenges, no disposition → flag); `INTERFACE_DESIGN_no_challenge.md` (no-false-positive: no section → no flag) | `agents/sentinel.md::P07` | PASS |
| REQ-13 — changelog producer | Prose verification: `grep -rl DESIGN_CHANGELOG skills/` returns `skills/software-planning/references/architecture-documentation.md` | `skills/software-planning/references/architecture-documentation.md` (DESIGN_CHANGELOG producer instruction) | PASS |

## Decisions Made

Two ADR drafts authored by the systems-architect formalize the load-bearing design choices.

| ADR | Title | Category | Key Decision |
|-----|-------|----------|--------------|
| `dec-draft-41f7a888` | Registry declarative spine — inline string convention over nested dataclass / StrEnum | architectural | `production_gate` and `cleanup_policy` are plain `str` fields with `_GATE_KINDS` / `_CLEANUP_POLICIES` constant sets; populated-not-projected avoids touching four consumer projection helpers; self-tests are the enforcement seam |
| `dec-draft-b8b54821` | Gate cohort — Full tier, parallel-group decomposition, registry spine lands first | architectural | 7 behaviors + ~14 files + cross-cutting exceeds Standard ceiling; parallel groups B/C after the spine (Group A) are safe because their file sets are disjoint except for the single serialized sentinel.md owner; Group D finalizes with spec archival (AC8 dogfood) |

Additional implementation-planner decisions (from `LEARNINGS.md`):

- **R4 = detector script + CA03 rewire (not `/record-calibration` command):** the detector is the missing load-bearing half; a command artifact over-builds a single-row append.
- **R5 = verifier-owned (four-writer contract decides it):** only the verifier reads LEARNINGS *and* writes ledger rows; planner/implementer adding rows would violate the contract.
- **R13 = sentinel grep, R3 = tested script:** R13 is grep-amenable and rare ("script only if frequent"); R3's date-math + tag-grouping warrants a tested, reusable detector matching GL02/EC07/AC10 precedent.
- **`agents/sentinel.md` single-owner serialization:** all four catalog edits (SH08, CA03-rewire, P07, P08) owned by one implementer in Step 10 to prevent fragment collision; scripts/tests/fixtures parallelized in Group B.

## Known Issues / Tech Debt

No new technical debt introduced by this pipeline. The R4 detector flags Praxion itself as uncalibrated (Waves 1/2/3 unlogged) — this is correct gate behaviour, not a bug; the orchestrator must append `calibration_log.md` rows as a separate producer step. Pre-existing tech debt entries (td-002 through td-021 and beyond) are unrelated to this pipeline.

## Implementation Summary

**New files created**: 8
- `scripts/check_spec_archival_gap.py`
- `scripts/test_check_spec_archival_gap.py`
- `scripts/check_calibration_coverage.py`
- `scripts/test_check_calibration_coverage.py`
- `tests/fixtures/sentinel/spec_archival_gap/` (directory + fixture files)
- `tests/fixtures/sentinel/stale_slug_advisory/` (directory + fixture files)
- `tests/fixtures/sentinel/challenge_no_disposition/` (directory + fixture files)
- `.ai-state/specs/SPEC_production-gate-cohort_2026-06-26.md` (this file)

**Existing files modified**: 8
- `scripts/artifact_registry.py` — `production_gate`/`cleanup_policy` fields + `_GATE_KINDS`/`_CLEANUP_POLICIES` + ARTIFACTS rows populated
- `scripts/test_artifact_registry.py` — 5 self-consistency tests + 1 canary added
- `agents/sentinel.md` — SH08 row added; CA03 rewired; P07 row added; P08 row added
- `agents/verifier.md` — LEARNINGS harvest clause added (LEARNINGS → td-NNN with dedup-key collapse)
- `rules/swe/agent-intermediate-documents.md` — honest-model documentation (prose sections are `/skill-genesis`-harvested-or-lost); updated always-loaded byte count ≤ baseline
- `skills/software-planning/references/architecture-documentation.md` — DESIGN_CHANGELOG standing producer instruction added (A6)
- `skills/software-planning/references/coordination-details.md` — calibration producer nudge added (R4 checklist)
- `.github/workflows/test.yml` — `check_calibration_coverage.py` wired as non-blocking push advisory

**Parallel execution**: 3 parallel groups (A → {B ∥ C} → D); Group B (B-R3, B-R4, B-fixtures, B-sentinel) and Group C (C1 R5, C2 A6) ran concurrently on disjoint file sets after Group A completed.

**Test results**: Group A integration checkpoint (Step 3) passed all `test_artifact_registry.py` tests. Full suite (Step 11 gate) passed. AC8 dogfood: `check_spec_archival_gap.py --json` returns `gap: false` after this archival, confirming R3 operates on a fresh-spec state. See `TEST_RESULTS.md` for evidence trail.
