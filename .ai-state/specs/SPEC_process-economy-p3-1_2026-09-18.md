# Spec: P3.1 -- Intentional Compaction (Phase-Boundary Handoff with Continuity Guarantees + a Compaction Safety Net)

**Task slug**: `process-economy-p3-1`
**Tier**: Standard
**Created**: 2026-09-19T05:39:27Z
**Pipeline run**: 2026-09-17 to 2026-09-18
**Archived**: 2026-09-18
**Status**: completed
**Complexity**: large
**ADRs**: `dec-draft-3695d2e9` (category: architectural; amended at the user's pre-mortem-gate decision 2026-09-18 --
no Praxion-set band, §4 user-operating-constraints section, DS-1b readiness gate; draft id shown -- finalize rewrites
to `dec-NNN` at merge)

## Requirements

Twelve requirements. IDs are stable; REQ-02b and REQ-05b were added mid-pipeline (REQ-02b at the pre-mortem-gate
architecture amendment; REQ-05b alongside REQ-05 in the original architecture pass) and are ordered next to the base
requirement they extend, matching `SYSTEMS_PLAN.md`'s own ordering.

**REQ-01** -- When the operator invokes the handoff command for a task slug at a phase boundary, and the pipeline has
an `IMPLEMENTATION_PLAN.md`/`WIP.md` or an upstream artifact on disk, the system writes `.ai-work/<slug>/HANDOFF.md`
carrying the mechanical sections (preflight, state, next action) derived from disk and git plus placeholders for the
judgement sections, **so that** the outgoing window's knowledge is captured in one file instead of being re-derived
by the next window.

**REQ-02** -- When a handoff is composed for a slug that already has a `HANDOFF.md` from an earlier boundary, the
system carries the previous `§4 Operating constraints from the user`, `§5 Corrections in force` and `§6 Do not
re-inherit` section bodies forward **verbatim** and records the superseded boundary in a one-line history, **so
that** the user's standing instructions and the accumulated process corrections are never lost by advancing a
boundary -- the stitches survive the window, not just the plan.

**REQ-02b** -- When a handoff is requested and the WAL shows a spawn started in this session with no matching stop,
or the current step's declared files carry uncommitted changes, the system refuses to write, exits non-zero, and
names which condition fired and what to do about it, **so that** a handoff never freezes a half-finished state as if
it were a boundary -- the next window inherits a committed, quiescent tree or an explicit `--force` override recorded
in the artifact. (Added mid-pipeline at the pre-mortem gate; the shipped readiness gate carries a **third** reason,
`wal-unreadable`, decided at a light review and folded into the architecture -- see Key Decisions.)

**REQ-03** -- When `/resume-pipeline <slug>` runs and `.ai-work/<slug>/HANDOFF.md` exists, the system reads the
handoff first for orientation, then runs the reconciler and acts only on the reconciler's per-step verdicts, **so
that** a fresh window starts oriented without inheriting an unverified claim about what is done.

**REQ-04** -- When the handoff's stated position disagrees with the reconciler's verdict for a step, the system
follows the reconciler and reports the disagreement to the operator as part of the resume summary, **so that** a
stale handoff can never mark unfinished work complete.

**REQ-05** -- When a session (main or subagent) starts with `source: "compact"` -- the state the harness enters
after auto *or* manual compaction -- and its working tree holds an in-flight `.ai-work/` pipeline, the system injects
a role-neutral orientation block naming the task slug, the current `WIP.md` step, the next action, and the pointer
set to re-read on demand, **so that** the window resumes work at the right step without re-reading every pipeline
document.

**REQ-05b** -- When a compaction completes in any session, the system appends one `compaction` row to the
observations WAL carrying the trigger (`manual`/`auto`) and the size of the harness's own summary, **so that** "did a
compaction happen, how often, and on whose trigger" is answerable from telemetry instead of by scraping transcripts.

**REQ-06** -- When the restore block is composed, whatever the size or number of the pipeline documents on disk, the
system emits at most 1,024 bytes of `additionalContext`, truncating with an explicit marker, **so that** the restore
never becomes a context cost of the kind it exists to avoid.

**REQ-07** -- When any failure occurs while composing the restore (no `.ai-work/`, unreadable or malformed document,
unexpected exception, empty or non-JSON payload on stdin), the system consumes stdin, prints nothing, and exits 0,
**so that** a broken hook can never block or corrupt a post-compaction turn.

**REQ-08** -- When an operator asks how Praxion keeps the orchestrator's window workable, the system answers from
one place: the measured baseline, the target (orchestrator context at spawn below 250k p50 over the next three
pipelines), the handoff as the means, and an explicit statement that the compaction threshold itself is the
operator's to lower -- with the four control names spelled correctly -- because Praxion cannot read utilisation and
does not set a threshold, **so that** the practice is honest about what is enforced (nothing), what is measured (the
target), and what is left to the human at the status line. (Reworded mid-pipeline at the pre-mortem gate from a
"documented, harness-enforced band" to this framing -- see Key Decisions D1.)

**REQ-09** -- When `scripts/context_baseline.py --json` runs on a machine holding the session transcripts, the
system reports per-agent-type peak/first-turn percentiles and per-pipeline-slug aggregates that reproduce
`BASELINE.md` §2-§3 within rounding, from a pure function over parsed transcript rows, **so that** the premise of
this work can be re-checked and the after-state measured with the same instrument.

**REQ-10** -- When `HANDOFF.md` is added to the pipeline artifact set, the system has it registered in
`scripts/artifact_registry.py` with its production gate and cleanup policy, present in
`precompact_state.PIPELINE_DOCS`, and listed in the artifact-inventory reference, **so that** the registry drift
test, the compaction snapshot, and the documented inventory cannot silently disagree.

## Traceability

Rendered from the merged `.ai-work/process-economy-p3-1/traceability.yml` (single canonical file throughout --
no fragments were ever produced; each parallel group's implementer/test-engineer wrote directly into the shared
file), cross-checked against `VERIFICATION_REPORT.md § Spec Conformance` and its `## Re-verification` addendum. Every
entry recorded against a requirement in the reconciled YAML is listed below -- no sampling. Cells group entries by
file: the leading count is the total number of individual YAML list items (tests or implementation symbols) for that
requirement; the parenthetical after each backtick-quoted path names every symbol/test recorded against that file.
Status reflects the **re-verified** state (`PASS WITH FINDINGS`, re-issued after rework `676b418a`, `85f1df67`,
`c2edeb22`), not the first-pass report's snapshot -- REQ-02b's first-pass status was **FAIL** (finding F1,
`dirty_paths()` corrupting the first porcelain path so the gate failed open on exactly one dirty file); the rework
resolved F1/F2/F3 at the root and REQ-02b is **PASS** below. No REQ carries `architectural_elements:`, so the
three-column back-compat format applies.

**Summary**: 10/12 REQs PASS, 2/12 UNTESTED-by-design (REQ-03: a prose-only implementation entry with nothing
executable to bind; REQ-08: a documentation requirement with no natural executable test), 0/12 FAIL. REQ-05b is PASS
at unit level with an explicitly unobserved live claim (AC-7, ruled a named post-merge obligation, not a gating
FAIL -- see `.ai-state/DESIGN.md` §3b.6, Status `Designed`).

| Requirement | Test(s) | Implementation | Status |
|---|---|---|---|
| REQ-01 | 2 test(s) -- `scripts/test_compose_handoff.py` (test_absent_input_writes_all_eight_sections_with_placeholders, test_invalid_boundary_is_rejected_and_writes_nothing) | 11 symbol(s) -- `scripts/compose_handoff.py` (compose(), _render(), _render_preflight(), _render_state(), _render_next_action(), _render_start_here(), _require_known_boundary(), main(), _read_render_context(), _section_bodies()); `commands/handoff.md` | PASS |
| REQ-02 | 2 test(s) -- `scripts/test_compose_handoff.py` (test_earlier_boundary_carries_sections_4_through_6_byte_for_byte, test_same_boundary_recompose_preserves_decisions_section) | 5 symbol(s) -- `scripts/compose_handoff.py` (_classify_input(), _parse_prior(), _judgement_bodies(), _boundary_history(), _read_existing()) | PASS |
| REQ-02b | 5 test(s) -- `scripts/test_compose_handoff.py` (test_blocks_on_unstopped_spawn, test_blocks_on_dirty_step_files, test_force_stamps_overridden_and_records_reasons_in_state_section, test_ready_when_no_conditions_fire, test_recent_log_mtime_is_advisory_only_and_never_blocks) | 20 symbol(s) -- `scripts/compose_handoff.py` (readiness(), _unstopped_agent_ids(), _session_wal_rows(), _dirty_paths(), _current_step_files(), _report_refusal(), _recent_log_note(), _wal_identifies_a_session(), gather(), _read_recent_log()); `scripts/_handoff_readiness.py` (readiness(), _identifies_a_session(), _unstopped_agent_ids(), session_wal_rows(), dirty_paths(), parse_porcelain_z()); `scripts/_handoff_inputs.py` (step_file_scope(), first_unfinished(), declared_files(), recent_log()) | PASS (was **FAIL** first-pass -- F1/F2/F3 resolved by rework `85f1df67`) |
| REQ-03 | 2 test(s) -- `scripts/test_compose_handoff.py` (test_unparseable_existing_refuses_to_write, test_oversized_judgement_sections_report_a_byte_warning_but_still_write) | 4 symbol(s) -- `scripts/compose_handoff.py` (_parse_prior(), _report(), _read_existing()); `commands/resume-pipeline.md` | **UNTESTED (for the stated behavior)** -- the two listed tests exercise refusal-to-overwrite and the byte advisory, neither exercises resume; the implementation entry is prose with nothing executable to bind. Not routed to rework; an accepted coverage boundary. |
| REQ-04 | 1 test(s) -- `scripts/test_compose_handoff.py` (test_reports_disagreement_when_reconciler_contradicts_stale_handoff) | 7 symbol(s) -- `scripts/compose_handoff.py` (_find_conflicts(), _render_state(), _resolve_base_ref(), _base_ref_candidates()); `scripts/_handoff_inputs.py` (resolve_base_ref(), _base_ref_candidates()); `commands/resume-pipeline.md` | PASS |
| REQ-05 | 4 test(s) -- `hooks/test_inject_compaction_orientation.py` (test_emits_orientation_naming_slug_and_current_step, test_emits_nothing_for_non_compact_sources, test_handoff_named_first_and_overridden_readiness_noted_inline, test_pointer_set_omits_handoff_when_absent) | 6 symbol(s) -- `hooks/inject_compaction_orientation.py` (main(), _compose_orientation(), _pointer_lines(), _next_action_line(), _current_step()); `hooks/hooks.json` (SessionStart[matcher=compact]) | PASS |
| REQ-05b | 8 test(s) -- `hooks/test_capture_session.py::TestPostCompactTelemetry` (test_appends_one_compaction_row_with_trigger_and_summary_length_only[manual], [auto], test_compaction_row_appends_through_the_shared_wal_path_without_disturbing_existing_rows, test_emits_no_stdout, test_malformed_payload_shape_never_raises_and_still_appends_a_row[non-string-summary], [null-summary], [null-trigger-and-summary], test_missing_trigger_key_resolves_to_an_explicit_unknown_value) | 4 symbol(s) -- `hooks/capture_session.py` (build_compaction_observation(), _resolve_ai_state_dir(), main()); `hooks/hooks.json` (PostCompact) | PASS (unit); **unobserved live** -- see AC-7 |
| REQ-06 | 1 test(s) -- `hooks/test_inject_compaction_orientation.py::TestByteCeiling` (test_orientation_stays_within_byte_ceiling_with_truncation_marker) | 3 symbol(s) -- `hooks/inject_compaction_orientation.py` (_truncate(), MAX_CONTEXT_BYTES, TRUNCATION_MARKER) | PASS |
| REQ-07 | 4 test(s) -- `hooks/test_inject_compaction_orientation.py::TestSilentFailurePaths` (test_silent_when_no_ai_work_tree_exists, test_silent_when_wip_has_no_recognizable_current_step, test_silent_on_empty_or_malformed_stdin_payload, test_silent_when_reading_a_pipeline_document_raises) | 2 symbol(s) -- `hooks/inject_compaction_orientation.py` (main(), _payload_source()) | PASS |
| REQ-08 | `[]` (by design) | 1 symbol(s) -- `docs/context-economy.md` | **UNTESTED** (accepted -- a "one document says these things and claims no enforcement" requirement has no natural executable test; the falsifiable half was checked by hand, a manual grep for `AUTO_COMPACT_WINDOW=<number>` returning zero matches) |
| REQ-09 | 9 test(s) -- `scripts/test_context_baseline.py` (test_report_shape_matches_ds3_exactly, test_band_key_absent_without_band_argument, test_band_key_present_with_exact_shape_and_no_pct_field, test_by_agent_type_percentiles_use_floor_indexed_formula, test_main_peak_percentiles_use_floor_indexed_formula, test_by_pipeline_aggregates_sum_and_threshold_counts, test_unknown_and_multi_agent_types_are_reported_as_their_own_rows, test_generated_at_and_source_root_echo_back_unchanged, test_compute_source_contains_no_filesystem_or_clock_calls) | 2 symbol(s) -- `scripts/context_baseline.py` (load(), compute()) | PASS |
| REQ-10 | 2 test(s) -- `scripts/test_artifact_registry.py` (test_precompact_matches_registry_snapshot_set, test_every_consumer_filename_is_registered) | 2 symbol(s) -- `scripts/artifact_registry.py` (ARTIFACTS -- HANDOFF.md row); `hooks/precompact_state.py` (PIPELINE_DOCS -- HANDOFF.md entry) | PASS |

## Key Decisions

Four architect decisions landed under one ADR draft, `dec-draft-3695d2e9` (amended once, at the user's pre-mortem-gate
decision 2026-09-18), plus one implementer decision folded into the same architecture at a light review (full context
copied from `LEARNINGS.md § Decisions Made` and `§ Verification Stage`):

**[systems-architect] D1 -- Praxion sets no utilisation band; a documented target, a human trigger, and a measured
counterfactual (amended, user decision 2026-09-18)**: The original two design passes chose *which* control should
carry a 500,000-token value (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`, absolute-token, capped at the model window -- chosen
over the percentage-form `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` because a token threshold above a smaller window is inert
rather than aggressive). The user rejected the premise at the pre-mortem gate: **Praxion sets no threshold at all** --
no `env` entry, no `settings.json` edit, component C13 dropped entirely. `docs/context-economy.md` instead documents
the measured baseline, a **target** (orchestrator context at spawn < 250k p50 over three pipelines), and one
paragraph naming the four verified operator-side controls as theirs to lower, never Praxion's.
`context_baseline.py --band <tokens>` survives as the analysis flag that makes such a choice informed. **Why**: at
the moment of compaction the orchestrator's *judgement state* -- the user's standing instructions, corrections in
force, the pending checkpoint decision, spawns in flight -- is gambled on the harness summariser; the plan on disk
survives, the stitches do not. Forcing a compaction at a token count is not a Praxion event and does not address
context rot; the mechanism therefore has to be the human-triggered phase-boundary handoff (D2), not a machine
threshold. **Alternatives**: 500k via `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (the reversed decision); 200k via
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (rejected earlier -- reaches subagents); `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` (rejected
-- indiscriminate 200k clamp). **Accepted cost**: no mechanical backstop for an orchestrator that never hands off --
the top row of the Risk Assessment, mitigated only non-mechanically (status line, checkpoint pause, the 250k-p50
target measured over three pipelines).

**[systems-architect] D2 -- the handoff contract: one command over a deterministic composer, consumed by
`/resume-pipeline`, now with two guarantees added at the pre-mortem gate**: `commands/handoff.md`
(`disable-model-invocation: true`, 0 listing tokens) over `scripts/compose_handoff.py`, importing
`reconcile_pipeline_state.reconcile()` rather than reimplementing it. Two guarantees narrow the shape without
changing it: (1) a new verbatim-carry `§4 Operating constraints from the user` section (DS-1) holds the user's
ask-before list and session-scoped instructions -- the half of the state that lived nowhere else on disk before this
change; (2) a **readiness gate** (DS-1b, REQ-02b) that refuses to write while a spawn is in flight or the current
step's declared files are dirty, with `--force` stamping `readiness: overridden` into the artifact rather than
silently proceeding. **Why**: with no band (D1), the handoff carries the entire mechanism, so it has to be worth
trusting; a handoff composed over a half-finished state is worse than none. **Alternatives**: prose-only handoff
(rejected -- untestable, re-types the mechanical half into the closing window); a `--write-handoff` flag on
`/resume-pipeline` (rejected -- overloads `--dry-run`, makes one command both writer and reader).

**[systems-architect] D3 -- the restore is a `SessionStart(source=compact)` injection of position and pointers;
`PostCompact` is telemetry only**: The design-time assumption that `PostCompact` carries `additionalContext` was
falsified before implementation against the live harness docs (fetched 2026-09-18) -- it has no decision control.
The restore moved to `SessionStart` with `matcher: "compact"`, a documented `additionalContext` event, emitting a
role-neutral ≤1,024-byte block naming `HANDOFF.md` **first** when one exists for the slug (pointer order is part of
the contract, per DS-2). `PostCompact` is kept for one `compaction` WAL row (`trigger`, `len(compact_summary)`) --
the only honest use of an event with no decision control. **Why**: the restore is a safety net for an event Praxion
did not choose (the harness's own default, an operator-set threshold, or a manual `/compact`), never the band's
companion, since D1 removed the band. **Alternatives**: injecting `PIPELINE_STATE.md` as-is (rejected -- measured at
~9,600 tokens of mostly-stale snapshot); dropping `PostCompact` from the design entirely (rejected -- would leave
compaction unobservable, the reversal trigger AC-7 needs).

**[systems-architect] D4 -- leave the canonical compaction-guidance block alone**: The shipped `Compaction Guidance`
block in `CLAUDE.md`/`AGENTS.md`/`claude/canonical-blocks/compaction-guidance.md` is left untouched this pipeline. Its
current text remains true under the new design (`PreCompact` still writes `.ai-work/PIPELINE_STATE.md`; the
`SessionStart` injection is additive, not contradictory), and it is the only live restore path until AC-7 proves the
hook's output actually arrives. Trimming it is a follow-up gated on that evidence. **Why**: the block is priced
×(1+spawns) and any change forces `sync_canonical_blocks.py` across three surfaces and every managed project on next
onboard -- premature before the machinery's efficacy is verified. **Alternatives**: trim the block now that a hook
can do the restoring (rejected -- the machinery's efficacy is unverified at design time, and AC-7 remained unmet
through the whole pipeline, confirming the caution was warranted).

**[implementer] The readiness gate's reason set is three, not two -- `wal-unreadable` added at a light review**:
DS-1b's shipped design decides `spawn-in-flight` and `dirty-step-files` from data the composer can always read. The
implementation surfaced a third, genuinely distinct case: the session WAL itself may be unreadable, in which case the
gate cannot answer "is a spawn in flight" at all. Rather than a `None` sentinel signalling "couldn't check" back up
through the reader, `readiness()` decides `wal-unreadable` **from the rows themselves**, inside the pure function,
keeping the four-argument signature intact; it is mutually exclusive with `spawn-in-flight` (`if not trustworthy /
elif unstopped`) because "cannot answer" and "answered yes" are different states and reporting both would imply the
gate had looked when it had not. **Why**: a readiness gate that silently defaults to `Ready` when it cannot read its
own evidence is exactly the fail-open shape F1 later reproduced in a different function (`dirty_paths()`) -- naming
the unreadable case explicitly is the same discipline applied one condition earlier. **Alternatives**: a `None`
sentinel from the WAL reader (rejected -- pushes the "can I see?" question out of the gate that owns it); silently
treating an unreadable WAL as `Ready` (rejected outright -- the failure mode this whole gate exists to close).
