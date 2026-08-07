# SPEC: Pre-Implementation Design-Synthesis Capability (H1-wide)

**Task slug**: `design-dialectic`
**Tier**: Full
**Archived**: 2026-04-17
**Status**: Shipped
**Commits**: `845ee31` (dec-050 budget revision) + `e4dc7eb` (dec-051 H1-wide capability)
**ADRs**: [dec-050](../decisions/050-always-loaded-budget-revision.md), [dec-051](../decisions/051-pre-impl-design-synthesis.md)

## Feature Summary

Adds an activation-gated pre-implementation design-synthesis capability across four pipeline stages — S1 (promethean ideation), S2 (researcher option exploration), S3 (systems-architect design), S5 (refactoring) — as a composition layer over existing Praxion skills, with **zero always-loaded token delta**.

The capability is invoked on demand when a 5-dimension activation formula fires: `tier ∈ {Standard, Full} AND (blast_radius ≥ 5_files OR spans ≥ 2_subsystems OR reversibility == "one-way-door" OR novelty == "no-precedent" OR stakes ∈ {security, user-visible-breaking}) AND uncertainty == "multiple_plausible_paths"`. Convergence is established via mechanical signals only (REQ-ID stability, risk-budget satisfaction, blast-radius bound, user acceptance) — no LLM-as-judge confidence scalars.

## Behavioral Specification (REQ-DDL-01 through REQ-DDL-15)

**Implementation-time requirements** (satisfied by the landed changelist):

- **REQ-DDL-03**: Phase 9 Stakeholder Review adds Security/Performance/Simplicity/Testability lenses to Dev/Test/Ops under fired activation, each citing an existing Praxion artifact.
- **REQ-DDL-07**: Architect follows refactoring cross-link and scores decompositions against four pillars when 2+ valid layouts exist.
- **REQ-DDL-08**: `design-synthesis.md` reuses existing skills for every lens; zero newly invented lenses.
- **REQ-DDL-09**: Convergence signals are mechanical only; no LLM-as-judge confidence scalars.
- **REQ-DDL-10**: Always-loaded token surface unchanged (sentinel T02 measurement same pre/post).
- **REQ-DDL-11**: `skills/software-planning/SKILL.md` satellite-files list includes `references/design-synthesis.md`.
- **REQ-DDL-12**: `skills/spec-driven-development/SKILL.md` contains `## Convergence via REQ-ID Stability` section; cross-linked from `design-synthesis.md`.
- **REQ-DDL-13**: ADR `.ai-state/decisions/051-pre-impl-design-synthesis.md` exists (accepted, architectural, consolidated).

**Runtime requirements** (constraints made explicit; verifier-phase observation in future pipelines):

- **REQ-DDL-01**: Architect reads `design-synthesis.md` before writing Phase 7 `### Decision` when activation fires (Standard/Full).
- **REQ-DDL-02**: Phase 7 `### Decision` contains ≥2 fleshed-out options under fired activation (honest-uncertainty gate; inventing strawmen to meet a count is itself a violation).
- **REQ-DDL-04**: ADR body records REQ-ID stability across ≥2 design sweeps when activation fires.
- **REQ-DDL-05**: Researcher re-runs coverage-critic pass when comparative matrix has <3 options OR architect flags incomplete axes.
- **REQ-DDL-06**: Promethean applies three-lens pre-shortlist pass when impact-to-effort spread is narrow.
- **REQ-DDL-14**: Invoking agent appends row to `.ai-state/calibration_log.md` when activation fires at S1/S2/S3/S5 (schema: `[timestamp, task-slug, stage, triggered-signals, lens-set-used, convergence-outcome]`).
- **REQ-DDL-15**: Phase 7 ADR body records an `Activation:` line (fired outcome or `no — <reason>`) in Standard/Full pipelines.

## Traceability Matrix

**Verification column added retroactively 2026-08-07.** As shipped, this matrix carried only `REQ-DDL | Satisfying artifact(s) | Kind` — `Kind` records *when* a requirement applies, and nothing recorded *what verifies it*. The omission was invisible to sentinel SH04, whose scan for `UNTESTED` markers cannot match a matrix that has no verification column to hold one. Cells cite greps, scripts, and sentinel check IDs rather than REQ-tagged tests for two reasons: `rules/swe/id-citation-discipline.md` forbids REQ IDs in code, and this feature's `VERIFICATION_REPORT.md` was ephemeral (see Research Lineage). Ten of the fifteen requirements have no mechanical gate — nine are prose-and-pointer obligations discharged per pipeline, and REQ-DDL-08 is judgmental; their cells state `no test — <reason>` explicitly rather than leave a blank. Greps and paths below were re-run against HEAD on 2026-08-07. Nothing else in this spec was altered.

| REQ-DDL | Satisfying artifact(s) | Kind | Test reference |
|---|---|---|---|
| REQ-DDL-01 | `agents/systems-architect.md` Phase 7 pointer + `skills/software-planning/references/design-synthesis.md` §When to Activate | Runtime (pointer enables compliance) | `grep -c 'design-synthesis.md#when-to-activate' agents/systems-architect.md` → 2 (Phase 7 + Phase 9); no test — the architect's read is unobservable, only the pointer is checkable |
| REQ-DDL-02 | `skills/software-planning/references/design-synthesis.md` §When to Activate (honest-uncertainty gate) | Runtime | `grep -c 'honest-uncertainty gate' skills/software-planning/references/design-synthesis.md` → 3; no test — option count lives in per-pipeline ADR bodies, which no gate reads |
| REQ-DDL-03 | `agents/systems-architect.md` Phase 9 pointer + `skills/software-planning/references/design-synthesis.md` §Lens Catalog | Runtime | `grep -c 'design-synthesis.md#lens-catalog' agents/systems-architect.md` → 1; no test — lens application is per-pipeline prose |
| REQ-DDL-04 | `skills/software-planning/references/design-synthesis.md` §Convergence Signals + `skills/spec-driven-development/SKILL.md` §Convergence via REQ-ID Stability | Runtime | no test — no gate reads an ADR body for a REQ-ID-stability record; the defining section is covered by REQ-DDL-12's check |
| REQ-DDL-05 | `agents/researcher.md` Phase 4 pointer + `skills/software-planning/references/design-synthesis.md` §S2 Research | Runtime | `grep -c 'design-synthesis.md#s2-research' agents/researcher.md` → 1; no test — the re-run trigger fires per pipeline |
| REQ-DDL-06 | `agents/promethean.md` Phase 5 pointer + `skills/software-planning/references/design-synthesis.md` §S1 Ideation | Runtime | `grep -c 'design-synthesis.md#s1-ideation' agents/promethean.md` → 1; no test — the three-lens pass runs per ideation session |
| REQ-DDL-07 | `skills/refactoring/SKILL.md` cross-link + `skills/software-planning/references/design-synthesis.md` §S5 Refactoring | Runtime | `grep -c 'design-synthesis.md#s5-refactoring' skills/refactoring/SKILL.md` → 1; no test — four-pillar scoring is per-refactor judgment |
| REQ-DDL-08 | `skills/software-planning/references/design-synthesis.md` §Lens Catalog (pointer-only) + §Anti-Patterns | Implementation-time | All 6 Lens Catalog target paths resolve on disk; no test — invented-lens drift is judgmental, guarded by sentinel T06 (redundancy) |
| REQ-DDL-09 | `skills/software-planning/references/design-synthesis.md` §Convergence Signals + §Anti-Patterns | Implementation-time | `grep -c 'LLM-as-judge confidence scalars' skills/software-planning/references/design-synthesis.md` → 3 (§Convergence Signals intro + Prohibited para + §Anti-Patterns) |
| REQ-DDL-10 | Measured post-merge: always-loaded surface unchanged at ~47,001 chars / ~13,429 tokens | Implementation-time | `scripts/test_measure_token_budget.py::test_canary_an_over_budget_corpus_exits_nonzero`; sentinel T02 runs `python3 scripts/measure_token_budget.py --json` (a ceiling guard, not a delta guard — it cannot reproduce the one-time 2026-04-17 measurement) |
| REQ-DDL-11 | `skills/software-planning/SKILL.md` satellite-list bullet for design-synthesis.md | Implementation-time | `grep -c 'references/design-synthesis.md' skills/software-planning/SKILL.md` → 1 |
| REQ-DDL-12 | `skills/spec-driven-development/SKILL.md` §Convergence via REQ-ID Stability (new section) | Implementation-time | `grep -c '^## Convergence via REQ-ID Stability' skills/spec-driven-development/SKILL.md` → 1 |
| REQ-DDL-13 | `.ai-state/decisions/051-pre-impl-design-synthesis.md` (frontmatter + body verified) | Implementation-time | `tests/test_adr_frontmatter_parseable.py::test_every_finalized_adr_frontmatter_parses` (globs `.ai-state/decisions/[0-9]*.md`); sentinel DL02/DL03; `python3 scripts/adr_health.py --json` for reference decay |
| REQ-DDL-14 | `skills/software-planning/references/design-synthesis.md` §Logging obligation (REQ-DDL-14) | Runtime | no test — the per-activation row schema is unenforced; `scripts/check_calibration_coverage.py` (sentinel CA03) checks only that the log stays current |
| REQ-DDL-15 | `skills/software-planning/references/design-synthesis.md` §ADR obligation (REQ-DDL-15) + architect Phase 7 pointer | Runtime | no test — no gate reads an ADR body for the `Activation:` line (`grep -rn 'Activation:' scripts/ tests/` → 0 hits) |

## Key Decisions

1. **H1-wide chosen over H1-narrow (Option 1 alone), Option 2 (standalone skill), Option 3 (lens-subagent fan-out), Option 4 (reinforce-only)** — surgical footprint of a single reference file plus the one missing mechanical convergence signal (REQ-ID stability). See dec-051 §Considered Options.
2. **One consolidated ADR, not three separate ADRs** for capability + activation + convergence — the sub-decisions are logically one design. See dec-051 §Decision structure D1/D2/D3.
3. **Zero new lenses** — the reference is a composition layer, not a knowledge layer. Every lens points at an existing Praxion artifact (security, performance, simplicity, testability). REQ-DDL-08 + §Anti-Patterns enforce.
4. **Mechanical convergence signals only** — rejected LLM-as-judge confidence scalars (per `skills/agent-evals/SKILL.md:31` warning on uncalibrated judges). REQ-DDL-09 + §Anti-Patterns enforce.
5. **Always-loaded budget raised to 25K + reframed as guardrail** (dec-050) — enabled the on-demand reference without re-extraction pressure; reframe shifts authorial conversation from "minimize tokens" to "every always-loaded token must earn its attention share."
6. **Architecture docs skipped** (`.ai-state/ARCHITECTURE.md`, `docs/architecture.md`) — H1-wide is a composition layer, not a structural change. Architect explicitly deferred per lean-mode directive.
7. **REQ-DDL-02 tightened** from "≥3 fleshed options" to "≥2 fleshed options + strawmen-are-a-violation" — aligns with the honest-uncertainty gate's `multiple_plausible_paths` clause and prevents count-inflation traps.

## Post-Ship Follow-ups

1. **Measure activation firing rate** after 10 Standard/Full pipelines via REQ-DDL-14's `.ai-state/calibration_log.md` entries. If firing rate <20%, revisit activation thresholds in a supersession ADR — do not silently edit the reference.
2. **Revisit `blast_radius ≥ 5_files` threshold** if firing clusters suspiciously at the boundary. The threshold is a reasonable midpoint between Standard-tier scope (4–8) and Full-tier scope (9+), not empirically calibrated. See SYSTEMS_PLAN §Open Issues 6.
3. **Monitor reference-file drift**: REQ-DDL-08 forbids invented lenses, but incremental edits over time could erode the pointer-only posture. Sentinel check T06 (redundancy) is the existing mechanical guard; periodic review of the Lens Catalog table against lens-source artifacts is the judgmental complement.
4. **Lens-body quality follow-up**: two pre-flight `[MISSING-OBJECTION]` flags resolved favorably at time of shipping (`skills/performance-architecture/SKILL.md` and `agents/test-engineer.md` testability lens both citable). If either source skill is restructured, the Lens Catalog pointer may need update.
5. **False-claim propagation diagnostic**: during this pipeline, three agents (context-engineer → architect → verifier) serially reported `agents/sentinel.md:141` as stale-at-15K even though dec-050 had already updated it to 25K. None re-verified the live file. Capture as a process pattern in `LEARNINGS.md` for cross-pipeline awareness.

## Decisions Log Cross-Reference

- [dec-050](../decisions/050-always-loaded-budget-revision.md) — budget policy change that enabled this work's on-demand footprint
- [dec-051](../decisions/051-pre-impl-design-synthesis.md) — consolidated capability + activation + convergence ADR for this feature

## Research Lineage (ephemeral — consumed and distilled into ADRs)

The full research record lived in `.ai-work/design-dialectic/` (deleted post-merge per end-of-feature workflow):

- `RESEARCH_FINDINGS.md` — pre-impl synthesis design space survey (6 candidate patterns; multi-agent-debate literature review; 16 sections, 14 citations)
- `CONTEXT_REVIEW.md` — context-engineer verdict across 4 options (H1 hybrid chosen)
- `SYSTEMS_PLAN.md` — architect's consolidated design with 15 REQ-DDLs
- `IMPLEMENTATION_PLAN.md` — 8 sequential steps with REQ coverage map
- `VERIFICATION_REPORT.md` — PASS verdict, 15/15 REQ-DDLs satisfied, zero contract violations

Findings distilled into dec-051 §Context. The prior spike on `slior/dialectic-agentic` (`.ai-work/dialectic-comparison/RESEARCH_FINDINGS.md`, also ephemeral) established the baseline framing: pre-impl synthesis need is real, dialectic-specific mechanism is not.
