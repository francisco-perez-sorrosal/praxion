---
title: Praxion Generated Artifact Lifecycle Audit
type: independent-analysis
audience: architect / context-engineer / implementation-planner / maintainer
status: analysis (no implementation)
date: 2026-06-24
author: Francisco Perez-Sorrosal (analysis drafted with Cursor agent)
verification: claims tagged VERIFIED / INFERRED / RISK / RECOMMENDATION
---

> **Scope of this document.** This is an analysis, not an implementation. It audits the generated
> artifacts Praxion uses to run projects and pipelines: ephemeral `.ai-work/<task-slug>/...`
> process documents, persistent `.ai-state/...` traceability/state documents, and adjacent
> permanent docs that are generated or maintained by the pipeline. It identifies creators,
> consumers, lifecycle intent, process/philosophy coherence, and remediation candidates with
> effort/cost estimates.

---

## 0. Executive Summary

Praxion's artifact model is directionally strong. The central split is right:

- `.ai-work/<task-slug>/` holds in-flight coordination state, scoped to one task and deleted after
  downstream consumption.
- `.ai-state/` holds project intelligence that should survive sessions, branches, worktrees, and
  merges.
- `docs/architecture.md` and selected root documents are permanent human-facing projections of
  state, not scratchpads.

That model is coherent with Praxion's process and philosophy because it makes context explicit,
keeps the orchestrator lean through pointer-based handoffs, preserves decisions in git, and enables
worktree-local isolation for concurrent pipelines.

The problem is not the model. The problem is **contract drift**. Praxion has evolved quickly, and
several inventories, validators, dashboards, hooks, and human docs no longer describe the same
artifact set. The highest-leverage fixes are:

1. ~~Finish the `.ai-state/ARCHITECTURE.md` -> `.ai-state/DESIGN.md` migration across remaining
   rule, validator, dashboard, docs, and spec references.~~ **Done (2026-06-24)** — F-01/F-02
   remediation applied to rules, agents, CI, commands, skills, and templates; historical ADRs/specs
   intentionally unchanged per dec-132.
2. Update all canonical `.ai-work` artifact manifests from a hand-maintained partial list to a
   single generated or schema-backed registry. (VERIFIED / RECOMMENDATION)
3. Fix compaction recovery: `PIPELINE_STATE.md` path semantics, stale `remember()` guidance, and
   incomplete artifact snapshot coverage. (VERIFIED)
4. Harden cleanup: `/clean-work` should not delete active or unarchived task directories based only
   on a `LEARNINGS.md` warning. (VERIFIED / RISK)
5. Remove stale memory-subsystem references from process docs and human docs now that dec-225
   removed `remember()` / `memory-mcp`. (VERIFIED)

---

## 1. Methodology

This audit used the repository as source of truth, with emphasis on:

- Always-loaded lifecycle rules: `rules/swe/agent-intermediate-documents.md`,
  `rules/swe/swe-agent-coordination-protocol.md`, `rules/swe/adr-conventions.md`,
  `rules/swe/agent-behavioral-contract.md`.
- Pipeline agent definitions: `agents/{promethean,researcher,systems-architect,implementation-planner,implementer,test-engineer,verifier,doc-engineer,context-engineer,interface-designer,agentic-transactions-architect,sentinel,skill-genesis,architect-validator,roadmap-cartographer}.md`.
- Planning/spec references: `skills/software-planning/references/*`,
  `skills/spec-driven-development/SKILL.md`, `skills/goal-disambiguation/*`.
- Command surfaces: `/onboard-project`, `/new-project`, `/clean-work`, `/resume-pipeline`,
  `/resume-rework`, `/dispatch-reworks`, `/eval-praxion`, `/check-experiment`.
- Script surfaces: `hooks/precompact_state.py`, `scripts/reconcile_ai_state.py`,
  `scripts/reconcile_pipeline_state.py`, `scripts/finalize_adrs.py`,
  `scripts/build_doc_manifest.py`, `eval/src/praxion_evals/harness/task_manifest.py`,
  `dashboard_app/src/server/artifacts/files.ts`.
- Actual project state: existing `.ai-state/` files, live `.ai-work/` task-slug directories, and
  current architecture docs.

Evidence labels:

- **VERIFIED**: directly observed in the repo.
- **INFERRED**: reasoned from multiple observed references; future implementation should verify.
- **RISK**: failure mode that follows from drift or missing enforcement.
- **RECOMMENDATION**: proposed direction, not a current fact.

---

## 2. Difficulty / Cost Rubric

Use these estimates for planning. They assume a future agent has this report plus repo access.

| Effort | Typical time | Typical cost | Fit |
| --- | ---: | ---: | --- |
| XS | 30-90 min | direct edit + one focused test | One stale doc/reference, no behavior change |
| S | 2-4 hours | one agent session + focused tests | Small cross-reference cleanup or single validator update |
| M | 0.5-1 day | context-engineer or implementer + tests | Several files, one artifact family, clear contract |
| L | 1-3 days | planner + implementer + verifier | Cross-cutting contract migration, dashboard/eval updates |
| XL | 3-7 days | standard pipeline | New registry/schema, migration tests, docs, dashboard/eval consumers |

Severity:

- **Critical**: can cause wrong pipeline behavior, silent data loss, or a validator missing a class
  of defects.
- **Important**: degrades reliability, traceability, or future-agent comprehension.
- **Suggested**: cleanup, clarity, or drift prevention.

---

## 3. Artifact Taxonomy

### 3.1 Ephemeral Task-Slug Artifacts

These live under `.ai-work/<task-slug>/`. They are task-local, worktree-local, gitignored, and
should be deleted only after their useful content is merged into permanent surfaces.

Status legend for both artifact tables: ✅ active producer-consumer tie; ◐ active only under an
explicit trigger/optional extension or partially drifted; ❌ stale/deprecated/no active tie.

| Artifact | Maintained? | Rationale | Primary creator | Primary consumers | Role | Coherence assessment |
| --- | --- | --- | --- | --- | --- | --- |
| `TASK_BRIEF.md` | ✅ | Producer/reader wiring is explicit in the intake gate, researcher, architect, planner, test-engineer, and verifier prompts. | Main orchestrator via intake clarity gate / `goal-disambiguation` | `researcher`, `systems-architect`, `implementation-planner`, `test-engineer`, `verifier` | Captures user intent, key success signals, health guards, uncertainty before pipeline commitment | Strong. It operationalizes Surface Assumptions and criteria-first work. Needs manifest/dashboard coverage. |
| `IDEA_PROPOSAL.md` | ✅ | Promethean output and downstream pipeline input are both active in the coordination protocol. | `promethean` | `researcher`, `systems-architect` | Validated idea feeding research/design | Strong. Prevents ideation from leaking into architecture as ungrounded context. |
| `RESEARCH_FINDINGS.md` | ✅ | Researcher writes it and architect/planner consume it as a standard pipeline handoff. | `researcher` | `systems-architect`, `implementation-planner`, specialist sub-architects | Evidence base: internal codebase findings, external docs, comparison, divergence map | Strong. Fits context-before-plan. |
| `CONTEXT_REVIEW.md` | ✅ | Context-engineer shadow mode owns the file, and downstream planners/architects are instructed to read it. | `context-engineer` | `systems-architect`, `implementation-planner` | Context-artifact health/placement review, cumulative by stage | Strong. The single-writer exemption is coherent; keep it in manifests. |
| `INTERFACE_DESIGN.md` | ◐ | Agent and consumers are active, but dashboard/precompact/eval manifests under-discover it. | `interface-designer` | `systems-architect`, `implementation-planner`, `implementer`, `verifier` | Interface-layer design decisions plus `## Architecture Challenges` loop-back | Strong. It gives boundary specialists standing without making them full architects. Manifest coverage is stale. |
| `TRANSACTIONS_DESIGN.md` | ◐ | Specialist producer/consumer contract exists, but it activates only for transaction-shaped work and is missing from some generic manifests. | `agentic-transactions-architect` | `systems-architect`, `implementation-planner`, `implementer`, `verifier` | Transaction-domain decisions and safety challenges for agentic payments/trading | Strong for high-stakes work. Needs explicit validator/dashboard discovery. |
| `SYSTEMS_PLAN.md` | ✅ | Core architect output and required Standard/Full input for planner, test-engineer, and verifier. | `systems-architect` | `implementation-planner`, `test-engineer`, `verifier` | Architecture, acceptance criteria, behavioral spec, risk and readiness | Core artifact. Very coherent with process. |
| `PRE_REFACTOR_PLAN.md` | ◐ | Active only when pre-refactor activation fires; producer and validator prompts exist but orchestration parsing remains mostly manual. | `systems-architect` | Orchestrator, `implementation-planner`, `test-engineer`, `verifier` | Pre-feature refactor mini-pipeline activation artifact | Coherent but complex. Needs cleanup and schema validation guardrails. |
| `SPEC_DELTA.md` | ◐ | Active under SDD/brownfield conditions; not expected for every pipeline. | `systems-architect` | `implementation-planner`, `verifier` | Brownfield behavioral delta from archived specs | Strong. It prevents silent requirement drift. |
| `IMPLEMENTATION_PLAN.md` | ✅ | Planner output and execution-agent input are central to the three-document model. | `implementation-planner` | Main orchestrator, `implementer`, `test-engineer`, `doc-engineer`, `verifier` | Approved step decomposition and assignment plan | Core artifact. Coherent when plan changes require approval. |
| `WIP.md` | ✅ | Planner initializes it, execution agents update it, and recovery tooling reads it. | `implementation-planner`, then step agents update owned fields | Main orchestrator, `/resume-pipeline`, all step agents | Live execution position | Core but fragile if stale; recovery loop correctly demotes it to a cache validated by ground truth. |
| `LEARNINGS.md` | ✅ | All pipeline agents write learnings, and cleanup/skill-genesis/spec archival treat it as the durable-learning bridge. | All pipeline agents | `skill-genesis`, end-of-feature archival, future agents via specs/ADRs/docs | In-flight learning capture | Strong. It is the bridge from temporary experience to durable intelligence. |
| `TEST_BASELINE.md` | ✅ | Planner/verifier contract is active, even though generic manifests lag. | `implementation-planner` | `verifier` | Pre-pipeline failing-test snapshot | Strong. It prevents unverifiable "pre-existing failure" claims. Manifest coverage is stale. |
| `TEST_RESULTS.md` | ✅ | Implementer/test-engineer produce it and verifier/recovery use it as evidence. | `test-engineer` or `implementer` | `verifier`, spec archival, evals | Test execution evidence | Strong. Required for verification credibility. |
| `traceability.yml` | ✅ | Planner initializes, implementer/test-engineer update, and verifier/spec archival consume it. | `implementation-planner`, `test-engineer`, `implementer` | `verifier`, spec archival, SDD coverage tools | In-flight REQ -> tests -> implementation mapping | Strong. It keeps REQ IDs out of source code. |
| `VERIFICATION_REPORT.md` | ✅ | Verifier output drives user disposition, rework, and learning harvest. | `verifier` | User, orchestrator, `skill-genesis`, rework loop | Quality gate report against criteria/conventions | Strong. It enforces proof-before-done. |
| `REWORK_MANIFEST.md` | ◐ | Verifier and rework commands are wired, but cleanup enforcement is not mechanical enough. | `verifier` | Main orchestrator, `dispatch-reworks`, `/resume-rework` | Clustered remediation worktree manifest | Strong but cleanup-sensitive. Parent cleanup must be gated on rework completion. |
| `VERIFIER_FINDINGS.md` | ◐ | Active inside rework worktrees, but not part of the main canonical artifact inventory. | Main orchestrator in each rework worktree | `/resume-rework`, `systems-architect` | Rework intake artifact derived from one manifest row | Strong. It avoids dumping entire verifier reports into rework sessions. |
| `parent-VERIFICATION_REPORT.md` | ◐ | The provenance need is active, but filename conventions conflict with `VERIFICATION_REPORT.snapshot.md`. | Main orchestrator in rework worktree | Rework agents | Snapshot of parent verifier context | Strong intent, but filename is unsettled against `VERIFICATION_REPORT.snapshot.md`. |
| `ARCHITECTURE_VALIDATION.md` | ◐ | Architect-validator actively produces it; path triggers now include `**/DESIGN.md` (F-02 fixed). | `architect-validator` | User, CI, tech-debt ledger | Code <-> DSL <-> ADR drift report | Strong conceptually; stale path triggers remediated 2026-06-24. |
| `RECOVERY_LOG.md` | ◐ | `/resume-pipeline` owns it, but inventories/dashboard/precompact do not treat it as first-class yet. | `/resume-pipeline` | User, orchestrator, future recovery | Audit trail for auto-recovery actions | Strong. It makes automation accountable. Needs cleanup guard. |
| `PIPELINE_STATE.md` | ◐ | The hook writes it and agents read it, but root-vs-slug path docs and snapshot coverage are inconsistent. | `PreCompact` hook | Main agent after compaction | Snapshot for post-compaction orientation | Important but currently stale/incomplete. |
| `ROADMAP_DRAFT.md`, `AUDIT_<lens>.md`, `CONTRADICTION_MAP.md` | ◐ | Active in roadmap-cartographer runs, but outside the main `.ai-work` registry and generic workshop consumers. | `roadmap-cartographer` and spawned researchers | `roadmap-cartographer` | Project audit fragments and synthesis draft | Strong for multi-lens roadmap generation. Needs manifest/dashboard coverage if workshops should render them. |
| `TRAINING_RESULTS.md` | ◐ | Active for ML workflows only; core SWE inventories do not clearly classify the extension family. | `/run-experiment` / ML workflow | `/check-experiment`, `verifier` Phase 3a, archival | ML run metrics and budget/eval evidence | Strong for ML projects. Adjacent to SWE pipeline; needs explicit family classification. |

### 3.1.1 Live `.ai-work` State Observed During Audit

The live disk audit found `.ai-work/` is not merely a theoretical workspace. It currently contains
21 task slugs and roughly 76 files, including completed Standard pipelines, research-only runs,
abandoned or broken slugs, and one empty orphan directory. That is a lifecycle problem because
`.ai-work/` is gitignored and intended to contain active or recently resumable task state, not a
long-term archive.

Representative cleanup groups:

- **High-confidence completed cleanup candidates:** `l3-readiness-config`, `healthcheck-baseline`,
  `finalize-consumer-bugs`, `agentic-reliability-integration`, `head-milestone-verify`,
  `skills-conformance`, `nebius-neocloud`.
- **Cleanup after explicit rework disposition:** `agent-truncation-recovery`, because it contains a
  `REWORK_MANIFEST.md` with advisory rework.
- **Likely safe deletion after quick review:** `codex-onboarding-bridge/` (empty), plus
  `api-documentation`, `factory-agent-readiness`, `self-improving-skills`, and `sia-praxion-fit`
  where `PROGRESS.md` cites missing output artifacts.
- **Review before delete:** `ci-autofix-research`, `praxion-competitive-eval`,
  `crafting-skills-refresh`, `frontier-practices-scan`, `task-intake-disambiguation`,
  `process-governance-study`, `hackathon-skill-loop`, `skills-coherence-pass`.

### 3.2 Persistent Project-State Artifacts

These live in `.ai-state/` or permanent docs and are committed to git.

| Artifact | Maintained? | Rationale | Primary creator/updater | Consumers | Role | Coherence assessment |
| --- | --- | --- | --- | --- | --- | --- |
| `.ai-state/DESIGN.md` | ✅ | Current file exists and active agents, sentinel, verifier, and dashboard all consume it. | `systems-architect`, `implementation-planner`, `implementer` | `researcher`, `promethean`, `roadmap-cartographer`, `verifier`, `sentinel`, dashboard | Architect-facing design target, includes planned/designed/built/deprecated components | Strong. Filename aligned with dec-132; active-surface rename completed 2026-06-24 (F-01). |
| `docs/architecture.md` | ✅ | Active developer-facing pair to `DESIGN.md`, validated by docs/architecture checks and consumed by dashboard/humans. | `systems-architect`, `implementer`, `doc-engineer` | Developers, dashboard, verifier, sentinel | Code-verified developer navigation guide | Strong. The subset-of-DESIGN rule is coherent. |
| `.ai-state/DESIGN_CHANGELOG.md` | ◐ | Intended as a living companion, but update frequency is lower and less central than `DESIGN.md`. | Architecture-maintenance agents | Maintainers | Verification/change history for design doc | Useful if maintained. Lower priority than main DESIGN.md freshness. |
| `.ai-state/SYSTEM_DEPLOYMENT.md` | ✅ | Deployment surface reconciled with dec-225 (2026-06-24); no active `memory-mcp` listing. | `systems-architect`, `implementer`, `cicd-engineer` | `verifier`, `sentinel`, deployment agents | Deployment topology/config/runbook state | Strong. Diagram L1 may still show removed memory MCP — prose is authoritative until regen. |
| `.ai-state/decisions/drafts/*.md` | ◐ | Active only during pipelines; empty drafts directory is healthy when no draft ADR is in flight. | `systems-architect`, `implementation-planner`, `interface-designer`, transaction architect | `finalize_adrs.py`, sentinel, agents in-flight | Pre-finalize ADR fragments with `dec-draft-<hash>` ids | Strong. It solves concurrent ADR numbering and is active only during pipelines. |
| `.ai-state/decisions/<NNN>-*.md` | ✅ | Finalized ADRs are the active rationale spine and are consumed by agents, indexes, hooks, and docs. | `finalize_adrs.py`, direct-tier human authors | All planning/research agents, docs, sentinel | Finalized ADRs | Core persistent traceability surface. |
| `.ai-state/decisions/DECISIONS_INDEX.md` | ✅ | Generated index is actively maintained by ADR finalization/index regeneration and consumed by agents/dashboard. | `regenerate_adr_index.py` via finalize | Research, architecture, dashboard, sentinel | Scannable ADR index | Strong but generated; should never be hand-merged. |
| `.ai-state/specs/SPEC_*.md` | ✅ | Spec archival is active in SDD flow, though live audit suggests at least one missed archive to investigate. | `implementation-planner` end-of-feature | `researcher`, `systems-architect`, `verifier`, sentinel | Archived behavioral specs and traceability matrices | Strong. SDD's durable counterpart, though at least one completed pipeline may have missed archival. |
| `.ai-state/calibration_log.md` | ◐ | Consumer checks exist, but producer append behavior is weakly enforced and under-sampled. | Main orchestrator | sentinel, future calibration | Tier-selection accuracy history | Conceptually strong; producer enforcement is weak. |
| `.ai-state/observations.jsonl` | ✅ | Hooks actively append it and recovery/metrics/dashboard consume it as WAL/observability. | hooks | metrics, dashboard, recovery, chronograph-like analysis | Append-only WAL of session/tool events | Strong as observability. Must not be described as curated memory. |
| `.ai-state/TECH_DEBT_LEDGER.md` | ✅ | Multiple active producers write grounded rows and execution agents consume/update status. | verifier, sentinel, orchestrator, architect-validator | reader agents, roadmap/planning | Active grounded debt rows | Strong. Persistent debt is better than buried warnings. |
| `.ai-state/TECH_DEBT_RESOLVED.md` | ✅ | Post-merge finalization actively moves terminal rows here for durable history. | `finalize_tech_debt_ledger.py` | agents, users | Terminal debt history | Strong. Keeps active ledger small. |
| `.ai-state/sentinel_reports/*` | ✅ | Sentinel produces timestamped reports/logs and multiple agents consume them for health context. | sentinel | promethean, context-engineer, users | Ecosystem audit reports and log | Strong. Timestamped + append-only log pair fits persistent intelligence. |
| `.ai-state/skill_genesis_reports/*` | ◐ | Current path is correct after dec-186, but directory is lazy-created and stale `.ai-work` consumers remain. | skill-genesis and `/skill-genesis-review` | users, context-engineer | Learning-harvest proposals and disposition log | Strong after dec-186; lazy-created and stale consumers still expect `.ai-work/SKILL_GENESIS_REPORT.md`. |
| `.ai-state/idea_ledgers/*` | ✅ | Promethean writes them and future ideation/roadmap agents consume them. | promethean | promethean, skill-genesis, roadmap work | Timestamped idea history | Useful, but carry-forward semantics can conflict across worktrees. |
| `.ai-state/metrics_reports/*` | ✅ | `/project-metrics` produces paired reports/logs and dashboard/sentinel consume them. | `/project-metrics` | dashboard, sentinel, readiness views | Health metrics reports and logs | Strong. Timestamped report pairs are easy to merge. |
| `.ai-state/praxion_eval_reports/*` | ◐ | Active on explicit `/eval-praxion` runs, but not part of every normal pipeline. | `/eval-praxion` | maintainers | Out-of-band pipeline/artifact quality evals | Strong. Opt-in by design, not hook-driven. |
| `.ai-state/doc_manifest.yaml` | ◐ | Generator and dashboard tie is active, but freshness and `.ai-work` artifact coverage lag. | `scripts/build_doc_manifest.py` | dashboard documentation surface | Documentation discovery spine | Useful but artifact list is stale for `.ai-work`; freshness semantics are weak. |
| `.ai-state/TEST_TOPOLOGY.md` | ◐ | Producer/consumer contract exists behind adoption thresholds; absent is acceptable in Praxion today. | systems-architect, test-engineer, planner | planner, implementer, verifier, sentinel | Test group topology for scoped runs | Coherent, optional. Absence alone should not warn. |
| `.ai-state/principles.yaml` | ◐ | Loader/consumer path exists, but file is optional and user-authored rather than actively produced by Praxion. | no active baseline producer in current Praxion | planner, verifier | Optional project principle gates | Coherent as optional; needs absent-behavior clarity. |
| `.ai-state/project_profile.yaml` | ❌ | Designed as a future/lazy surface, but no active producer exists today. | no active producer yet | downstream archetype-aware tooling | Optional machine-readable profile | Coherent future seam, but no active producer-consumer tie today. |
| `.ai-state/LANDSCAPE_WATCHLIST.md` | ◐ | Producer/consumer flow exists, but refresh cadence is aging and the artifact should remain optional. | landscape refresh workflow | promethean, roadmap-cartographer | External-source watchlist | Useful and active, but aging and should remain optional/freshness-aware. |
| `.ai-state/UPSTREAM_ISSUES.md` | ✅ | `/report-upstream` appends entries and stewardship/research workflows consume them. | `/report-upstream` | researcher/verifier/upstream stewardship | Upstream issue ledger | Useful adjacent state. |
| `.ai-state/training_runs/*.md`, `gpu_budget.yaml`, `neo_cloud_backend.yaml` | ◐ | Active only for ML/AI training workflows; not a universal Praxion project-state family. | ML workflow | `/check-experiment`, verifier, ML skills | ML run/budget/backend state | Coherent for ML projects; should be clearly separate from SWE core. |

---

## 4. Major Findings

### F-01 — `.ai-state/ARCHITECTURE.md` References Survived the Rename

**Status:** Done (2026-06-24)

**Severity:** Critical
**Effort:** M
**Estimated time/cost:** 0.5-1 day; context-engineer + focused tests for validators/docs/dashboard
**Evidence:** `dec-132` accepted the rename to `.ai-state/DESIGN.md`; actual file exists as
`.ai-state/DESIGN.md`; remaining old references appear in `rules/swe/agent-intermediate-documents.md`,
`skills/software-planning/references/agent-pipeline-details.md`, `agents/architect-validator.md`,
`README_DEV.md`, `docs/getting-started.md`, historical specs, and some sentinel carry-forward text.

**Why it matters.** Dec-132 says the rename had to be atomic across 71 reference sites. It was mostly
done, but not fully. Remaining old references create three classes of bugs:

- Validators and CI triggers may scan `**/ARCHITECTURE.md` and miss `.ai-state/DESIGN.md`.
- Human docs teach new users the wrong source of truth.
- Artifact inventories contradict the actual project state and confuse future agents.

**Coherence judgment.** The rename itself is philosophically coherent: it improves information
architecture and Diátaxis clarity. The leftover drift is incoherent because it leaves two names for
one concept.

**Recommended fix.**

- Update active references to `.ai-state/DESIGN.md`.
- Preserve old names only in historical ADRs/reports where dec-132 explicitly says history should
  not be rewritten.
- Add a regression check that no active prompt/rule/command/validator refers to
  `.ai-state/ARCHITECTURE.md` except in historical migration context.

**Remediation (2026-06-24).** Updated active guidance across rules, agents, skills, commands, CI, and templates to use `**/DESIGN.md` only. **Historical layer preserved:** pre-dec-132 ADRs, archived specs' narrative/commit tables, and sentinel reports keep `ARCHITECTURE.md` where it reflects decision-time facts; dec-132 is the sole rename authority. `SPEC_diagrams` traceability matrix already used `.ai-state/DESIGN.md` for REQ-DIAGRAM-05 (path resolution on disk).

### F-02 — `architect-validator` Still Uses `ARCHITECTURE.md` as an Architectural Touch Path

**Status:** Done (2026-06-24)

**Severity:** Critical
**Effort:** M
**Estimated time/cost:** 0.5-1 day; update agent definition, CI trigger docs, tests, and possibly
workflow filters
**Evidence:** `agents/architect-validator.md` triggers on `**/ARCHITECTURE.md` and validates markdown
fences in `**/ARCHITECTURE.md` plus `docs/architecture.md`. It does not name `.ai-state/DESIGN.md`
as an input.

**Risk.** A PR can modify `.ai-state/DESIGN.md` or its generated regions without activating the
structural validation path that is supposed to guard code <-> DSL <-> ADR drift.

**Recommended fix.**

- Replace `**/ARCHITECTURE.md` triggers with the current design-doc substrate:
  `.ai-state/DESIGN.md`, `**/DESIGN.md` if managed projects use the same convention, and
  `docs/architecture.md`.
- Keep `**/ARCHITECTURE.md` only as a backward-compatible managed-project legacy path if needed,
  explicitly labeled as legacy.
- Update sentinel AC10 and AaC fence checks if they share the same old trigger.

**Remediation (2026-06-24).** `agents/architect-validator.md` triggers on `**/DESIGN.md`; sentinel AC10 updated; `.github/workflows/architecture.yml` and `claude/aac-templates/architecture.yml.tmpl` path filters and fence `find` commands use `DESIGN.md` only. No legacy `ARCHITECTURE.md` path retained.

### F-03 — The Canonical Artifact Inventory Mixes Active, Optional, Future, Historical, and Renamed Surfaces

**Status:** Done (2026-06-25) — also closes P12 (lifecycle-state labels).

**Severity:** Important
**Effort:** L
**Estimated time/cost:** 1-2 days; context-engineer + doc-engineer + sentinel/eval updates
**Evidence:** `rules/swe/agent-intermediate-documents.md` is presented as the canonical tree but
contains `.ai-state/ARCHITECTURE.md`, optional/no-active-producer files (`project_profile.yaml`,
`eval_ledger/EVAL_LOG.md`), historical `token_budgeting/`, and active files in one flat list.

**Why it matters.** The inventory is always-loaded. Future agents treat it as source of truth. Mixing
artifact states without lifecycle labels causes false expectations: "missing" may mean not adopted,
not activated, optional, future-designed, or deprecated.

**Recommended fix.**

- Split the inventory into states:
  - Required onboarding skeleton.
  - Created lazily by active producer.
  - Optional adoption-threshold artifacts.
  - Future-designed / no active producer.
  - Historical retained.
  - Deprecated / migration-only.
- Move the full per-artifact table out of the always-loaded rule into a reference file, leaving a
  compact decision table in the rule. Sentinel already reported token budget pressure, so this also
  improves token efficiency.

**Remediation (2026-06-25).** Moved both verbose tables — the per-artifact inventory and the
`## Document Lifecycle` table (the latter the sentinel's named target) — out of the always-loaded
`rules/swe/agent-intermediate-documents.md` into a new on-demand reference
`skills/software-planning/references/artifact-inventory.md` (the `td-018` progressive-disclosure
pattern). The rule keeps the canonical file trees and now carries a **compact lifecycle-state decision
table** with the five state labels (`active` / `optional-lazy` / `threshold-lazy` / `future-designed`
/ `historical-retained`) so "absent" is unambiguous — **this closes P12**. Both sentinel-validated
anchors (`#task-slug-convention`, `#tech_debt_ledger-summary`) preserved; no inbound anchor links to
the moved sections. The rule dropped **14,658 → 7,742 chars (~6,900 chars / ~1,900 tokens freed)**,
moving the always-loaded budget from the sentinel's urgent **0.9% headroom** to ~5.7%. The reference
cross-links the machine counterpart `scripts/artifact_registry.py` (F-04), closing the human-inventory
/ machine-inventory loop. `ARCHITECTURE.md` was already removed by F-01. Rules manifest regenerated;
software-planning skill validates.

### F-04 — Dashboard and Documentation Manifest Recognize a Stale Partial `.ai-work` Set

**Status:** Done (2026-06-25) — closed together with its dependent cluster P7/P8/P9/P15.

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5-1 day; TypeScript + Python manifest updates + tests
**Evidence:** `scripts/build_doc_manifest.py` and `dashboard_app/src/server/artifacts/files.ts`
recognize only a subset of workshop artifacts and still include `SKILL_GENESIS_REPORT.md` as an
ephemeral artifact. They miss `TASK_BRIEF.md`, `INTERFACE_DESIGN.md`, `TRANSACTIONS_DESIGN.md`,
`PRE_REFACTOR_PLAN.md`, `TEST_BASELINE.md`, `REWORK_MANIFEST.md`, `VERIFIER_FINDINGS.md`,
`ARCHITECTURE_VALIDATION.md`, `RECOVERY_LOG.md`, `TRAINING_RESULTS.md`, `ROADMAP_DRAFT.md`,
`AUDIT_<lens>.md`, and `CONTRADICTION_MAP.md`.

**Risk.** The dashboard/documentation surface becomes a partial truth. It may hide the most important
artifacts for challenge loops, rework, recovery, and ML verification.

**Recommended fix.**

- Introduce one machine-readable artifact registry consumed by:
  - `rules/swe/agent-intermediate-documents.md` generated excerpt or check.
  - `scripts/build_doc_manifest.py`.
  - dashboard workshop discovery.
  - eval task manifest.
  - compaction snapshot hook.
- If a registry is too large for now, at minimum update the four current hard-coded lists together
  and add a test that fails when they diverge.

**Remediation (2026-06-25).** Built the canonical registry (`scripts/artifact_registry.py`) as the
single source of truth: one `Artifact` per `.ai-work/<slug>/` doc with per-consumer membership flags
(`dashboard`, `snapshot`, `eval_tier`/`eval_required`) plus projection helpers. The four hard-coded
lists are now **checked** against the registry by `scripts/test_artifact_registry.py` — which parses
each consumer from source (no imports; uniform across Python, the hook, the eval package, and the TS
dashboard module) and asserts agreement, with gate-liveness canaries proving it bites on the
historical drift (stale `SKILL_GENESIS_REPORT.md`; a dropped required artifact; eval missing
`LEARNINGS.md`). Corrected all three drifted consumers to the registry: `build_doc_manifest._AI_WORK_FILES`
and the dashboard's `CANONICAL_WORKSHOP_ARTIFACTS` to the 19-artifact dashboard set (dead
`SKILL_GENESIS_REPORT.md` dropped — **closes P9**; `TASK_BRIEF`/`INTERFACE_DESIGN`/`TRANSACTIONS_DESIGN`/
`PRE_REFACTOR_PLAN`/`TEST_BASELINE`/`REWORK_MANIFEST`/`RECOVERY_LOG` added — **closes P7 and P15**);
`task_manifest._STANDARD_REQUIRED` gained the always-produced `LEARNINGS.md` (**closes P8**). `precompact`
already matched (batch 2). **Deferred (noted, not done):** wiring consumers to *read* from the registry
(vs. checked-against); conditional eval specs for tests-/SDD-only artifacts (needs activation conditions
on `ArtifactSpec`); the roadmap/ML/rework specialty artifacts are registered but not enforced into the
four core consumers. The always-loaded rule was intentionally **not** expanded (F-03 wants it smaller);
enforcement lives in the drift test + in-code pointers, not always-loaded prose.

### F-05 — `PIPELINE_STATE.md` Compaction Recovery Is Stale and Incomplete

**Status:** Done (P4 2026-06-24; P3 + P5 2026-06-25). Registry-driven snapshot (F-04/Phase 3) remains the durable follow-up, but the hard-coded list is now correct and complete.

**Severity:** Critical
**Effort:** M
**Estimated time/cost:** 0.5-1 day; hook update + tests
**Evidence:** `hooks/precompact_state.py` writes `.ai-work/PIPELINE_STATE.md`, while
`claude/canonical-blocks/compaction-guidance.md` says `.ai-work/<slug>/PIPELINE_STATE.md`. The hook
also writes a "Memory Obligation" telling agents to call `remember()`, but dec-225 removed the
in-house memory subsystem and project guidance says no memory tools exist. The hook snapshots only a
partial document list and includes obsolete `SKILL_GENESIS_REPORT.md`.

**Risk.**

- After compaction, an agent may look in the wrong path.
- It may follow a stale `remember()` instruction and waste time or violate the current no-memory
  contract.
- It may miss the very artifacts that explain why a pipeline is in a challenge/rework/refactor state.

**Recommended fix.**

- Decide whether `PIPELINE_STATE.md` is root-scoped (multi-task snapshot) or task-scoped. Update all
  references to match.
- Remove `remember()` guidance; replace with current durable-learning path:
  `LEARNINGS.md` -> ADR/spec/docs/skill-genesis/sandbook future seam.
- Snapshot all active artifacts or use the central registry from F-04.
- Include a compact "active task slug(s)" index at the top when multiple task directories exist.

**Remediation (2026-06-24, P4).** Replaced the PreCompact "Memory Obligation" block in
`hooks/precompact_state.py` with a "Durable Learning Reminder" that points at `LEARNINGS.md` and
`.ai-state/` promotion paths and explicitly states no `remember()`/`recall()` tools exist after
dec-225.

**Remediation (2026-06-25, P3 — path mismatch).** Resolved in favor of the **root-scoped** layout
the hook actually implements: `hooks/precompact_state.py` scans *all* task-slug subdirectories and
writes one consolidated `.ai-work/PIPELINE_STATE.md` with a per-slug `## <slug>/<doc>` section per
active pipeline (a single active slug cannot be inferred when concurrent pipelines exist, so a
task-scoped path is unsound). The drift was a three-surface fork in the synced canonical block:
`claude/canonical-blocks/compaction-guidance.md` (source) plus its two consumers
`commands/onboard-project.md` and `commands/new-project.md` said `.ai-work/<slug>/PIPELINE_STATE.md`,
while every other surface (Praxion `CLAUDE.md`, `AGENTS.md`, `AGENTS.md.tmpl`,
`skills/software-planning/SKILL.md`, the hook-safety contract, and `test_export_codex_rules_bridge.py`)
already used root. Corrected the source block and re-ran `scripts/sync_canonical_blocks.py --write`;
`--check` reports all 8 blocks in sync. Managed projects onboarded after this fix now teach the path
the hook actually writes.

**Remediation (2026-06-25, P5 + F-09 — snapshot coverage).** Rewrote the hook's `PIPELINE_DOCS`
list: removed the dead `SKILL_GENESIS_REPORT.md` (dec-186 moved it to
`.ai-state/skill_genesis_reports/`; a `.ai-work/<slug>/` copy is never produced — this also closes
the precompact half of F-09/P9), and added the orientation-critical artifacts that explain *why* a
pipeline is mid-flight: `TASK_BRIEF.md`, `INTERFACE_DESIGN.md`, `TRANSACTIONS_DESIGN.md` (challenge
state per F-16), `PRE_REFACTOR_PLAN.md`, `TEST_RESULTS.md`, `REWORK_MANIFEST.md`, `RECOVERY_LOG.md`.
The list is now ordered by pipeline flow. Absent docs are skipped (`if not doc_path.exists()`), so
listing specialist artifacts costs nothing for pipelines that never produce them. Smoke-tested with a
two-slug fixture: one root snapshot, per-slug sections, dead genesis report excluded, no slug-scoped
file written, exit 0.

### F-06 — `/clean-work` Can Delete Valuable or Gated State Too Easily

**Status:** Done (2026-06-25) — closed together with F-15/P14 and F-22/P22 (all three converge on `/clean-work`)

**Severity:** Critical
**Effort:** M
**Estimated time/cost:** 0.5-1 day; command update + dry-run tests
**Evidence:** `commands/clean-work.md` only warns when `LEARNINGS.md` exists before deleting a task
directory. The current artifact ecosystem has additional cleanup gates:
`traceability.yml` must be rendered into archived specs, `REWORK_MANIFEST.md` gates parent cleanup,
`RECOVERY_LOG.md` is an audit trail, `TEST_RESULTS.md` feeds verification/spec archival,
`VERIFICATION_REPORT.md` patterns should merge to `LEARNINGS.md`, and `PRE_REFACTOR_PLAN.md` may
carry unresolved tech-debt transitions.

**Risk.** A user can accidentally delete unarchived verification, traceability, rework, recovery, or
pre-refactor state. That undermines Praxion's proof-before-done and accountability philosophy.

**Recommended fix.**

- Turn `/clean-work` into a state-aware cleanup command:
  - Detect active/incomplete `WIP.md`.
  - Detect `REWORK_MANIFEST.md` and require explicit override if rework worktrees are still open.
  - Detect unarchived `traceability.yml` when a behavioral spec exists.
  - Detect `VERIFICATION_REPORT.md` not merged to `LEARNINGS.md`.
  - Detect `RECOVERY_LOG.md` and preserve or summarize it.
- Add `--dry-run` output listing blockers/warnings per task slug.

**Remediation (2026-06-25).** Replaced the single-`LEARNINGS.md` warning with a deterministic,
testable safety gate (the audit's stated verification — "fixture `.ai-work` directories… tests show
cleanup refuses"). New read-only classifier `scripts/clean_work_safety.py` scans each task directory
and returns `BLOCK` (active `WIP.md` with an unchecked step; open `REWORK_MANIFEST.md`), `WARN`
(`LEARNINGS.md`; `VERIFICATION_REPORT.md` without a `### Verification Patterns Merged` marker in
`LEARNINGS.md`; `traceability.yml` / REQ-bearing `SYSTEMS_PLAN.md`; `RECOVERY_LOG.md`; unconsumed
`PRE_REFACTOR_PLAN.md`), or `SAFE`; exit 1 when any directory is BLOCK. The scanner mutates nothing —
`commands/clean-work.md` (rewritten) drives it, supports `--dry-run` and per-slug `--force` for BLOCK
override, and confirms WARN deletions via `AskUserQuestion`. Per `gate-liveness`, the gate ships
canaries proving it bites on known-bad inputs (open rework manifest; unchecked WIP step) in
`scripts/test_clean_work_safety.py` (22 tests). Installed on `PATH` by `install_claude.sh` so the
shipped command works in managed projects. **F-15/P14** (verification-report merge marker) and
**F-22/P22** (spec-archival gate) are subsumed: the `unmerged-verification` and
`unarchived-traceability`/`unarchived-spec` WARN reasons implement them directly.

### F-07 — Memory Removal Is Not Fully Reflected in Process Docs

**Status:** Partial (2026-06-25). The audit-named active surfaces are fixed; grounding revealed the
stale-memory surface is **wider than this finding enumerated** — two new clusters are tracked as
backlog items **P26** (Codex memory bridge) and **P27** (roadmap `remember()` persistence) in §9, plus
a list of deliberately-retained vestigial references below.

**Remediation (2026-06-25).** Updated the active surfaces this finding named, plus two more found via
grounding: removed the curated-memory row from `docs/getting-started.md` (added a one-line note that
the backend is none / `sandbook` planned); deleted the `memory.json` reconciliation row from
`skills/software-planning/references/agent-pipeline-details.md`; corrected the stale Phase 5 toggle
description in `docs/existing-project-onboarding.md` (observability only — `/onboard-project` itself
was already clean); and removed `.ai-state/memory.json` from the retired-merge-driver references in
`rules/swe/vcs/pr-conventions.md` (active path-scoped rule) and `commands/merge-worktree.md`. History
(`.ai-state/decisions/`, idea ledgers, `TECH_DEBT_RESOLVED.md`, metrics reports) left untouched.

**Deliberately retained (vestigial / illustrative / guarded — not active wrong guidance):**
`skills/tui-design` (`memory-mcp start` as a generic CLI-UX *example*); `skills/versioning/references/commitizen.md`
(`memory-mcp/pyproject.toml` version-pin example); and the defensive *sanitization/scan* patterns for
`.ai-state/memory.json` in `skills/upstream-stewardship`, `skills/context-security-review`, and
`skills/id-decontamination` (guarded by "if present" — harmless on memory-free projects). These teach patterns
rather than assert Praxion ships memory; revisit only if they cause confusion.

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5-1 day; cross-reference cleanup
**Evidence:** Dec-225 removed `memory-mcp`, `memory.json`, `remember()`/`recall()` surfaces, and the
memory gate. Stale references remain in `skills/software-planning/references/agent-pipeline-details.md`
(`memory.json` reconciliation), `docs/getting-started.md` (curated memory table), historical metrics
reports, and some older ADRs/reports. *(PreCompact hook fixed 2026-06-24 — P4.)*

**Clarification.** Historical ADRs and reports should not be rewritten unless they are current
guidance. Active docs, hooks, rules, and commands should be updated.

**Recommended fix.**

- Add a "historical memory references are allowed only under `.ai-state/decisions/`, old reports,
  and migration docs" exception.
- Update active docs to say "memory backend: none; sandbook planned; observations remain active".
- Update `agent-pipeline-details.md` reconciliation table to remove `memory.json` or mark it
  historical/managed-project legacy only.

### F-08 — `reconcile_ai_state.py` Documentation and Reconciliation Contracts Lag Current State

**Status:** Done (2026-06-25). The script is intentionally narrow and its docstring already says so
(handles only `observations.jsonl` dedup + ADR renumber/index — verified: zero `memory` references in
`scripts/reconcile_ai_state.py`). The drift was entirely in the *callers* overstating its contract.

**Remediation (2026-06-25).** Aligned the callers to the script's actual narrow contract:
`commands/merge-worktree.md` no longer claims it "resolves memory.json" (now: `observations.jsonl` +
ADR renumber + index regen); the `agent-pipeline-details.md` `.ai-state/` reconciliation table dropped
its `memory.json` row (the script never handled it post-dec-225). The stale `ARCHITECTURE.md` reference
in that table was already removed by the F-01 migration. The remaining table rows match what the script
and git semantics actually do.

**Severity:** Important
**Effort:** S-M
**Estimated time/cost:** 2-6 hours depending on whether behavior changes
**Evidence:** `scripts/reconcile_ai_state.py` header says it handles observations and ADR sequence
renumbering. Other docs still say `/merge-worktree` runs it for memory and broader `.ai-state`
reconciliation. `agent-pipeline-details.md` still includes `memory.json`, old `ARCHITECTURE.md`, and
several manual reconciliation procedures not obviously implemented by the script.

**Risk.** Maintainers may believe merge reconciliation is broader than it is.

**Recommended fix.**

- Decide whether `reconcile_ai_state.py` is intentionally narrow or should grow.
- Rename or document it as narrow if it only handles observations + ADR legacy safety.
- Move non-implemented reconciliation policies into a "manual post-merge checklist" section.
- Ensure `/merge-worktree` text accurately describes what the script actually does.

### F-09 — Skill-Genesis's Permanent-Report Migration Is Incompletely Propagated

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5 day
**Evidence:** Dec-186 moved skill genesis reports from `.ai-work/<slug>/SKILL_GENESIS_REPORT.md` to
`.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_<timestamp>.md` plus log. Stale ephemeral
references remain in `hooks/precompact_state.py`, `scripts/build_doc_manifest.py`,
`dashboard_app/src/server/artifacts/files.ts`, and tests mention the old path.

**Risk.** The dashboard and compaction hook search for a file that new runs will not produce, while
the persistent report/log pair may be under-discovered.

**Recommended fix.**

- Remove `SKILL_GENESIS_REPORT.md` from `.ai-work` manifests.
- Add `.ai-state/skill_genesis_reports/` discovery to dashboard/doc manifest if not already complete.
- Keep fixture references only where they test migration or old-surface rejection.

### F-10 — Eval Harness Manifest Is Too Small for the Current Pipeline Contract

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5-1 day; update manifest + tests
**Evidence:** `eval/src/praxion_evals/harness/task_manifest.py` expects Standard pipelines to
produce only `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `WIP.md`, and `VERIFICATION_REPORT.md`.
Full adds optional recency checks for `.ai-state/DESIGN.md` and `docs/architecture.md`.

**Missing from the check.** It does not check `LEARNINGS.md`, `TEST_RESULTS.md`, `traceability.yml`,
`TASK_BRIEF.md`, `TEST_BASELINE.md`, `SPEC_DELTA.md`, or newer challenge/recovery/rework artifacts
when their activation conditions apply.

**Risk.** `/eval-praxion --task-slug` can return a healthy verdict for an incomplete pipeline
workshop.

**Recommended fix.**

- Make the manifest conditional rather than flat:
  - Required always for Standard/Full.
  - Required when behavioral spec exists.
  - Required when interface/transaction/pre-refactor/rework/recovery/ML markers exist.
  - Optional/info for one-off specialty docs.
- Reuse the central artifact registry proposed in F-04.

### F-11 — Calibration Log Is Required by Philosophy but Weakly Produced

**Status:** Done (2026-06-25).

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5-1 day
**Evidence:** `swe-agent-coordination-protocol.md` says all tiers append a row to
`.ai-state/calibration_log.md` on task completion. Existing sentinel reports show periods where the
file was missing or below analysis threshold. No dedicated command or hook appears to enforce the
append; it relies on main-agent behavior.

**Risk.** Calibration accuracy becomes aspirational. If rows are not consistently appended, sentinel
cannot assess over/under-processing trends.

**Recommended fix.**

- Add a lightweight `/record-calibration` helper or orchestrator checklist snippet.
- Consider a best-effort hook that reminds but does not block.
- Add a sentinel finding when recent completed pipelines have no corresponding calibration row.

**Remediation (2026-06-25).** Added the audit's primary recommendation — a **sentinel `CA03`**
coverage check (`agents/sentinel.md` § Calibration Accuracy) that compares the calibration log's
newest `Timestamp` against recent pipeline activity in `git log` and flags **Important** when recent
Standard/Full pipeline work has no corresponding row (with a golden bad-case per `gate-liveness`). The
CA dimension's activation was clarified so `CA03` runs whenever the file exists (few rows + much
activity *is* the under-logging signal), not only at the 5-entry `CA02` threshold. Detection — not a
new command surface — is the right enforcement: there is no "task-complete" hook event to gate on, and
the audit itself ranks the sentinel finding as the "add" (the `/record-calibration` helper and the
reminder hook are its "or"/"consider" options). The append obligation already lives in
`swe-agent-coordination-protocol.md`; CA03 closes the loop (instruction + detection) without expanding
the always-loaded budget (the check lives in `agents/sentinel.md`, which is not always-loaded).

### F-12 — `TECH_DEBT_LEDGER.md` Is Conceptually Strong but Producer/Consumer Boundaries Need a Single Schema Anchor

**Status:** Done (2026-06-24)

**Severity:** Suggested
**Effort:** S-M
**Estimated time/cost:** 2-6 hours
**Evidence:** The ledger schema is described in `rules/swe/agent-intermediate-documents.md`,
`skills/software-planning/references/tech-debt-ledger.md`, `agents/verifier.md`,
`agents/architect-validator.md`, and sentinel. Some descriptions say 14 fields + `dedup_key`;
`docs/architecture.md` says 15-field schema, which is mathematically the same but worded
differently.

**Risk.** Multiple schema narrations can drift.

**Recommended fix.**

- Keep the full schema in `skills/software-planning/references/tech-debt-ledger.md`.
- Everywhere else should link to it and name only writer/consumer boundaries.
- Add a tiny schema self-test if one does not already exist.

**Remediation (2026-06-24).** Closed in two passes:

**Pass 1 — single schema anchor + wording.** Canonical schema lives in
`skills/software-planning/references/tech-debt-ledger.md` § Schema (`14 row fields + 1 structural
`dedup_key` field`). Active surfaces that previously said `15-field` or mixed `14 fields +
dedup_key` now use the canonical phrase and link to the skill reference instead of re-explaining
enums or formulas: `docs/architecture.md`, `docs/existing-project-onboarding.md`,
`rules/swe/agent-intermediate-documents.md`, `.ai-state/DESIGN.md`, `commands/onboard-project.md`,
`agents/sentinel.md`, `scripts/finalize_tech_debt_ledger.py` (generated ledger headers). Pre-dec-132
ADRs and `DESIGN_CHANGELOG.md` left unchanged (historical “15 fields” narrative preserved).

**Pass 2 — producer overlays (strict “link only” in agents).** Operational finding→field mapping
moved out of agent prompts into the same skill reference § **Producer overlays**:
- **`verifier (Phase 5 / 5.5)`** — when to write, severity tiers, class mapping from tags/ceilings,
  Phase 5.5 survivor override, report-vs-ledger split, shared dedup rule.
- **`architect-validator (Phase 7)`** — drift-specific defaults for FAIL rows.

`agents/verifier.md` and `agents/architect-validator.md` now link to § Schema + § Producer overlays
only (no per-field bullet lists). `agents/systems-architect.md` consumer pointer updated from the
rule summary to the skill reference.

**Pass 3 — remaining writers (sentinel + orchestrator).** Completed the overlay set for all four
ledger writers:
- **`sentinel (TD01–TD04, TT04, EC07)`** — metrics/TT/EC signals, LLM-judgment gating, staleness
  policy, finding→class/severity/owner table. `agents/sentinel.md` TD/TT/EC check rows link to
  overlay keys instead of inline `class`/`owner-role` defaults.
- **`orchestrator (main agent)`** — explicit user direction, `defer-with-rationale` CIS filing,
  scope-gap exception; consumer-only rework/pre-refactor status flips documented separately from
  appends. `disposition-vocabulary.md` and `agents/researcher.md` link here.

**Verification.** `scripts/test_finalize_tech_debt_ledger.py` (`TestCanonicalSchemaAnchor`):
`FIELD_ORDER` = 14 row fields + `dedup_key`; skill reference declares canonical heading and all four
Producer overlays; active surfaces must not contain `15-field` wording; verifier/architect-validator
prompts must not duplicate field bullets; sentinel TD checks must reference overlay keys without
inline class/owner defaults.

### F-13 — `ROADMAP.md` Lifecycle Is Ambiguous Between Managed Projects and Praxion Itself

**Status:** Done (2026-06-24)

**Severity:** Suggested
**Effort:** S
**Estimated time/cost:** 2-4 hours
**Evidence:** `roadmap-cartographer` describes `ROADMAP.md` as a living root document, while
Praxion guidance says dec-092 means Praxion itself does not carry a living `ROADMAP.md` and regenerates
on demand.

**Interpretation.** This is probably not a contradiction if the distinction is:

- Managed projects may carry `ROADMAP.md`.
- Praxion itself intentionally does not carry a standing roadmap instance.

**Recommended fix.** Add that distinction wherever the cartographer output contract is summarized.

**Remediation (2026-06-24).** Added a managed-project vs Praxion-metaproject lifecycle subsection to
`agents/roadmap-cartographer.md` (Output Contract) and a lifecycle table to `commands/roadmap.md`,
and softened the cartographer's general output-contract line from "living document" to "audit output
document" so the managed-vs-Praxion distinction reads cleanly.

**Correction (2026-06-25).** An earlier draft of this note claimed both files "cite dec-032 and
dec-092." They do **not**, and they **must not**: `agents/` and `commands/` are *shipped* surfaces,
and `rules/swe/shipped-artifact-isolation.md` forbids embedding specific `dec-NNN` ids in shipped
artifacts (a `dec-NNN` dangles once the plugin lands in another project; `scripts/check_shipped_artifact_isolation.py`
enforces this at the commit gate). The committed fix correctly **inlines** the rationale instead of
pointing at ADR numbers — exactly what the isolation rule prescribes. Verified clean: the isolation
checker reports 0 violations on both files. For the record (this audit lives under `docs/`, which is
isolation-exempt): the underlying chain is **dec-032** (established the project-root living-document
model) **superseded by dec-092** (`status: superseded`/`superseded_by: dec-092`), which retires only
the *Praxion-instance* living document while preserving the on-demand regeneration capability — so a
future remediation must not "fix" this by adding the citations to the shipped files.

### F-14 — Pre-Refactor Plan Schema Has a Section-Ordering Inconsistency

**Status:** Done (2026-06-24)

**Severity:** Important
**Effort:** S
**Estimated time/cost:** 2-4 hours
**Evidence:** `systems-architect.md` lists an "8-section schema" and says `## Affected td-NNN rows`
is implied inside Scope or its own subsection, while sentinel PR01 expects `## Affected td-NNN rows`
as a canonical anchor and ordered required section.

**Risk.** A conforming architect can write a plan that the sentinel later fails, or a sentinel can
enforce stricter structure than the writer prompt.

**Recommended fix.** Make `## Affected td-NNN rows` an explicit required top-level section in both
producer and validator docs, with one canonical order.

**Remediation (2026-06-24).** Aligned `agents/systems-architect.md` Phase 2.5 schema with sentinel
`PR01` and `tests/fixtures/pre_refactor_plan_wellformed.md`: Goal → Behavior Preservation Contract →
Acceptance Criteria → Scope → Affected td-NNN rows → Verifier Bypass Criteria → Loop-Back Conditions
→ Resolved Tech Debt. Removed the erroneous top-level `## Steps` section (optional `### Steps` under
Scope only). Updated `agents/implementation-planner.md` pre-refactor decomposition source and
clarified `PR01` producer/validator parity in `agents/sentinel.md`.

### F-15 — Cleanup / Archival Order for `VERIFICATION_REPORT.md` Is Underspecified

**Status:** Done (2026-06-25 — subsumed by the F-06 `/clean-work` safety gate). The `unmerged-verification`
WARN reason fires when `VERIFICATION_REPORT.md` exists without a `### Verification Patterns Merged`
marker in `LEARNINGS.md` — the marker-or-prompt option this finding recommended, made deterministic.

**Severity:** Important
**Effort:** S-M
**Estimated time/cost:** 2-6 hours
**Evidence:** `verifier.md` includes a reminder to merge recurring patterns and systemic quality
issues into `LEARNINGS.md` before deleting the report. `clean-work` only checks `LEARNINGS.md`, not
whether this merge happened.

**Risk.** Verification insights can vanish when `.ai-work` is deleted.

**Recommended fix.** Add an explicit marker or checklist:

- `LEARNINGS.md ### Verification Patterns Merged` with verifier attribution, or
- `/clean-work` prompts specifically when `VERIFICATION_REPORT.md` exists.

### F-16 — Challenge-Loop Artifacts Need Stronger Manifest and Cleanup Semantics

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5 day
**Evidence:** `INTERFACE_DESIGN.md` and `TRANSACTIONS_DESIGN.md` are critical forward-only inputs
that can trigger orchestrator-mediated loop-backs via `## Architecture Challenges`. They are absent
from several artifact manifests.

**Risk.** If hidden from dashboard/eval/compaction, future agents may miss a challenge that should
have been routed back to the architect before planning.

**Recommended fix.**

- Add a structural check: if either file has a non-empty `## Architecture Challenges`, the orchestrator
  must record disposition in `SYSTEMS_PLAN.md`, `WIP.md`, or `LEARNINGS.md`.
- Include both files in compaction snapshots and dashboard workshop views.

### F-17 — ML Training Artifacts Are Adjacent but Not Clearly Partitioned From SWE Pipeline Artifacts

**Severity:** Suggested
**Effort:** M
**Estimated time/cost:** 0.5 day
**Evidence:** `TRAINING_RESULTS.md` appears in ML commands and verifier Phase 3a, but not in the
core `.ai-work` canonical tree. Persistent ML surfaces like `.ai-state/training_runs/`,
`gpu_budget.yaml`, and `neo_cloud_backend.yaml` are described by commands/skills, not by the main
artifact inventory.

**Risk.** Future agents may either ignore ML evidence in SWE-like pipelines or over-generalize ML
artifacts into every project.

**Recommended fix.** Add an "ML/AI training extension artifacts" subsection to the artifact
inventory with conditional activation rules.

### F-18 — Historical Specs Can Preserve Broken Paths Without a Repair Policy

**Severity:** Suggested
**Effort:** S-M
**Estimated time/cost:** 2-6 hours
**Evidence:** Sentinel reports carried forward a stale spec path issue:
`.ai-state/ARCHITECTURE.md` and old diagram paths in `.ai-state/specs/SPEC_diagrams_2026-04-30.md`.
Dec-132 says historical reports should not be rewritten; specs are different because they are
persistent baselines used for future deltas.

**Risk.** A future `SPEC_DELTA.md` may baseline against stale implementation paths.

**Recommended fix.** Define a spec path-repair policy:

- Historical requirements prose remains immutable.
- Traceability paths may be updated with a "maintenance correction" note.
- Sentinel SH checks should distinguish historical narration from live traceability fields.

### F-19 — `doc_manifest.yaml` Is Generated but Its Own Freshness Semantics Are Understated

**Severity:** Suggested
**Effort:** S
**Estimated time/cost:** 2-4 hours
**Evidence:** `commands/document-api.md` warns not to hand-edit API-spec entries because
`scripts/build_doc_manifest.py` clobbers them. The manifest records `generated_at` and many surfaces,
but consumers need to know when it is stale.

**Risk.** Dashboard/doc navigation can lag code/docs after a commit if the builder was not run.

**Recommended fix.** Add a freshness check in sentinel/doc-engineer:

- Compare `generated_at` or manifest mtime to changed docs/API spec files.
- Warn when stale, but do not block normal work.

### F-20 — Persistent Optional Artifacts Need "Absent Means OK" Language Everywhere

**Severity:** Suggested
**Effort:** M
**Estimated time/cost:** 0.5 day
**Evidence:** `TEST_TOPOLOGY.md`, `principles.yaml`, `project_profile.yaml`, `eval_ledger/EVAL_LOG.md`,
and some ML artifacts are intentionally absent in many projects. Some agent prompts handle absence
well; the canonical tree still makes them look like expected project-state files.

**Risk.** Agents may create optional artifacts prematurely, violating Simplicity First.

**Recommended fix.** Add a standard absent-behavior annotation:

- `optional-lazy`: absent means feature not adopted.
- `threshold-lazy`: absent until growth threshold.
- `future-designed`: absent because producer not wired.
- `historical-retained`: present only in old projects or history.

### F-21 — `.ai-work/` Contains Many Completed, Broken, or Orphaned Task Slugs

**Severity:** Important
**Effort:** M
**Estimated time/cost:** 0.5-1 day; doc-engineer/context-engineer plus cleanup gate
**Evidence:** Live audit found 21 `.ai-work/` task slugs and 76 files, including completed pipelines
with promoted ADRs, research-only fragments, broken `PROGRESS.md` references to missing outputs, and
an empty `codex-onboarding-bridge/` directory.

**Risk.** The workspace no longer communicates "active work". Future agents may treat stale reports
as current, or delete them without first merging useful `LEARNINGS.md`/verification patterns into
durable state.

**Recommended fix.**

- Run a gated cleanup pass rather than bulk deletion.
- Promote useful learnings from completed slugs before deletion.
- Explicitly dispose advisory rework in `agent-truncation-recovery` before parent cleanup.
- Delete empty/broken orphan slugs after confirming they do not carry unique learnings.
- Add a sentinel or dashboard advisory when `.ai-work` has stale slugs older than a threshold.

### F-22 — Completed Standard Pipelines May Miss Spec Archival

**Status:** Partial (2026-06-25). The **cleanup-gating half is done** (subsumed by the F-06 safety
gate): `/clean-work` now WARNs (`unarchived-traceability` / `unarchived-spec`) when a task directory
has `traceability.yml` or a REQ-bearing `SYSTEMS_PLAN.md`, requiring archived-spec confirmation before
deletion. The **one-off investigation** of whether `l3-readiness-config` actually missed its archive
(and any backfill) remains a separate manual task.

**Severity:** Important
**Effort:** S-M
**Estimated time/cost:** 2-6 hours for investigation; more if backfilling specs
**Evidence:** Live audit flagged `l3-readiness-config` as a completed Standard pipeline with rich
artifacts and promoted ADRs but no obvious matching `.ai-state/specs/SPEC_*.md` archive.

**Risk.** The behavior-to-proof chain can end in a verifier report that later gets deleted with
`.ai-work`, rather than a durable behavioral baseline.

**Recommended fix.**

- Investigate whether that pipeline had SDD activation conditions requiring a spec archive.
- If yes, backfill or record why archival was intentionally skipped.
- Add cleanup gating: if `traceability.yml` exists or `SYSTEMS_PLAN.md` has REQ IDs, `/clean-work`
  should require archived spec confirmation.

### F-23 — `SYSTEM_DEPLOYMENT.md` Still Describes Removed Memory Infrastructure

**Status:** Done (2026-06-24)

**Severity:** Important
**Effort:** S
**Estimated time/cost:** 2-4 hours
**Evidence:** Persistent-state audit found `.ai-state/SYSTEM_DEPLOYMENT.md` still lists `memory-mcp`
as deployed infrastructure even though dec-225 removed the in-house memory subsystem.

**Risk.** Deployment state is supposed to be the operational truth. Stale removed infrastructure here
can mislead agents doing install, deployment, MCP, or observability work.

**Recommended fix.** Update `SYSTEM_DEPLOYMENT.md` to reflect observations-only state, ADR injection,
and "memory backend: none / sandbook future seam".

**Remediation (2026-06-24).** Updated `.ai-state/SYSTEM_DEPLOYMENT.md` Overview and Service Topology
to list only `task-chronograph-mcp` as the active MCP; documented dec-225 removal of curated memory,
`observations.jsonl` WAL, standalone `inject_decisions.py`, and the planned `sandbook` seam; added
dec-225 to §9 Decisions; noted L1 diagram may still depict removed memory MCP until regen.

### F-24 — `capture_memory.py` Is a Misnamed Observability Hook After Memory Removal

**Severity:** Suggested
**Effort:** M
**Estimated time/cost:** 0.5 day if renaming; XS if documenting
**Evidence:** Persistent-state audit found `hooks/capture_memory.py` writes observations/WAL events,
not curated memory, after dec-225.

**Risk.** The name reinforces the stale memory mental model and complicates future sandbook
integration.

**Recommended fix.** Either rename to an observations-oriented name with compatibility shims/tests,
or explicitly document it as a legacy filename retained for hook compatibility.

### F-25 — CI and Path-Scoped Rules May Miss `DESIGN.md`-Only Architecture Changes

**Status:** Done (2026-06-24) — remediated alongside F-02

**Severity:** Critical
**Effort:** M
**Estimated time/cost:** 0.5-1 day
**Evidence:** Persistent-state audit found active path filters/rules still targeting
`**/ARCHITECTURE.md`, including architecture CI and AaC/DAC path scoping, while `.ai-state/DESIGN.md`
is the current architect-facing file.

**Risk.** A PR that changes only `.ai-state/DESIGN.md` may skip architecture validation or fail to
load the relevant path-scoped conventions.

**Recommended fix.** Update workflow path filters, path-scoped rules, and validator activation paths
to include `.ai-state/DESIGN.md`, keeping `**/ARCHITECTURE.md` only as a legacy managed-project
compatibility path when intentionally needed.

---

## 5. Deprecated / Cleanup Candidates

These are not necessarily files to delete immediately. They are concepts or references that should
be retired from active guidance.

| Candidate | Current status | Recommendation |
| --- | --- | --- |
| `.ai-state/ARCHITECTURE.md` | Renamed by dec-132; removed from active guidance (2026-06-24) | Keep only historical references in ADRs/specs/reports |
| `.ai-state/ARCHITECTURE_CHANGELOG.md` | Renamed to `DESIGN_CHANGELOG.md` | Same as above |
| `memory.json`, `memory-mcp`, `remember()` as active Praxion behavior | Removed by dec-225; stale active references remain | Remove from active guidance; preserve only historical/migration context |
| `.ai-work/<slug>/SKILL_GENESIS_REPORT.md` | Moved to `.ai-state/skill_genesis_reports/` by dec-186 | Remove from `.ai-work` manifests and compaction/dashboard lists |
| Legacy ADR NNN-at-create path for agent-authored ADRs | Deprecated by fragment-name-at-create scheme | Keep only as direct-tier human fallback; ensure agents never suggest it |
| `ROADMAP.md` as standing Praxion repo artifact | Dec-092 says Praxion regenerates on demand | **Done (2026-06-24)** — F-13 clarifies managed-project vs Praxion-self in cartographer + `/roadmap` |
| `token_budgeting/TOKEN_BUDGETING_*.md` | Historical retained, no active producer | Label historical, not active state |

---

## 6. Coherence With Praxion Process

### What Is Coherent

- **Artifact split by lifecycle.** `.ai-work` vs `.ai-state` is exactly the right process boundary.
  It prevents uncommitted scratch from polluting git while preserving durable intelligence.
- **Task slug propagation.** A shared slug makes multi-agent coordination tractable and prevents
  concurrent pipelines from colliding.
- **Pointer-not-payload handoffs.** Subagents returning paths instead of full reports protects the
  orchestrator's context window.
- **Fragment files in parallel execution.** `WIP_<agent>.md`, `LEARNINGS_<agent>.md`,
  `PROGRESS_<agent>.md`, and traceability fragments are a pragmatic concurrency design.
- **ADR draft fragments.** Draft IDs solve concurrent numbering without forcing up-front NNN
  allocation.
- **Spec archival.** Rendering `traceability.yml` into `.ai-state/specs/SPEC_*.md` before cleanup
  is the correct transition from in-flight to durable traceability.
- **Recovery loop.** `reconcile_pipeline_state.py` correctly treats `WIP.md` and `PROGRESS.md` as
  agent-authored claims, not truth. The git/test/WAL hierarchy is philosophically aligned with
  "proof before done".
- **Tech-debt ledger pair.** Active/resolved split prevents transient verifier warnings from being
  lost and keeps debt grounded.

### What Is Incoherent

- **Multiple partial artifact lists.** A process that relies on artifacts cannot afford four or five
  divergent manifests.
- **Stale memory instructions.** A removed capability should not remain in compaction/recovery text.
- **Cleanup based on one file.** The process now has many irreversible handoff surfaces; cleaning only
  by checking `LEARNINGS.md` is too weak.
- **Renamed architecture doc not fully migrated.** ~~Naming clarity was the point of dec-132; dual
  naming reverses that benefit.~~ Active-surface migration completed 2026-06-24 (F-01/F-02); only
  dec-132 retains before/after rename narrative.
- **Optional/future artifacts in the canonical tree without state labels.** This pressures agents to
  create documents "because the tree says so" instead of because the project has adopted the
  capability.

---

## 7. Coherence With Praxion Philosophy

### Context Engineering

The artifact model is one of Praxion's best expressions of context engineering. It makes context
durable, scoped, and discoverable. The drift findings are therefore high leverage: stale artifact
contracts poison future context.

### Behavior-Driven Development

`TASK_BRIEF.md`, `SYSTEMS_PLAN.md`, `traceability.yml`, `TEST_RESULTS.md`, and
`VERIFICATION_REPORT.md` form a coherent behavior-to-proof chain. The risk is that eval/dashboard
manifests do not check the whole chain.

### Incremental Evolution

The pipeline's small-step model is coherent, but artifact sprawl needs an incremental consolidation
step: do not invent a heavy metadata database; start with one registry or generated manifest to stop
hard-coded list drift.

### Structural Beauty

The artifact names increasingly tell the right story (`DESIGN.md` vs `docs/architecture.md`,
`TECH_DEBT_LEDGER.md` vs `TECH_DEBT_RESOLVED.md`). Remaining old names and stale references are
structural ugliness with real cognitive cost.

### Root Causes Over Workarounds

The root cause is not "docs need updating"; it is **no single artifact registry / lifecycle schema**.
Updating lists by hand will help briefly, but the durable fix is a canonical registry with generated
projections or consistency tests.

---

## 8. Recommended Remediation Plan

### Phase 1 — Stop Active Wrong Guidance

**Effort:** M
**Owner:** context-engineer + implementer
**Goal:** Remove highest-risk stale instructions.

Fix:

- ~~`ARCHITECTURE.md` active references in rules/agents/validators/docs.~~ **Done (2026-06-24)**
- ~~`remember()` active references in compaction hook and current docs.~~ **PreCompact hook done
  (2026-06-24 — P4);** remaining active-doc cleanup tracked under F-07/P10.
- ~~`SKILL_GENESIS_REPORT.md` from `.ai-work` lists.~~ **PreCompact hook done (2026-06-25);** `build_doc_manifest.py` + dashboard `files.ts` remain (F-04/P7).
- ~~`PIPELINE_STATE.md` path mismatch.~~ **Done (2026-06-25 — P3);** resolved to root-scoped, canonical block re-synced.

Verification:

- Grep active surfaces for `.ai-state/ARCHITECTURE.md`, `remember()`, and
  `.ai-work/<slug>/SKILL_GENESIS_REPORT.md`.
- Run relevant tests for compaction hook and doc manifest/dashboard artifact discovery.

### Phase 2 — Harden Cleanup and Recovery

**Effort:** M
**Owner:** implementation-planner + implementer
**Goal:** Make `.ai-work` deletion safe.

Fix:

- Add `/clean-work --dry-run`.
- Add gates for active WIP, rework manifests, unarchived traceability, verifier reports, recovery logs,
  and pre-refactor tech-debt transitions.

Verification:

- Fixture `.ai-work` directories for each gate.
- Tests show cleanup refuses or requires explicit override.

### Phase 3 — Build a Canonical Artifact Registry

**Effort:** L-XL depending on scope
**Owner:** systems-architect + implementation-planner
**Goal:** Stop manifest drift permanently.

Registry fields should include:

- `name`
- `path_pattern`
- `location`: `ai-work`, `ai-state`, `docs`, root
- `lifecycle`: ephemeral, session-persistent, permanent, historical, optional-lazy, threshold-lazy,
  future-designed
- `producer_roles`
- `consumer_roles`
- `activation_condition`
- `cleanup_policy`
- `dashboard_renderer`
- `eval_manifest_policy`
- `compaction_snapshot_policy`

Consumers:

- `agent-intermediate-documents.md` generated/checked summary.
- `build_doc_manifest.py`.
- dashboard workshop discovery.
- eval task manifest.
- `precompact_state.py`.
- sentinel EC/GL checks.

Verification:

- A consistency test that fails when any hard-coded artifact list diverges.

### Phase 4 — Repair Persistent State Baselines

**Effort:** M
**Owner:** context-engineer / doc-engineer
**Goal:** Correct stale live persistent baselines without rewriting history.

Fix:

- Repair archived spec traceability paths where sentinel identified stale live paths.
- Update docs/getting-started and README_DEV active guidance.
- Decide whether `LANDSCAPE_WATCHLIST`, `UPSTREAM_ISSUES`, ML artifacts, and readiness config should
  appear in the canonical registry or a secondary extension registry.

Verification:

- Sentinel SH/AC checks.
- Cross-reference validator over docs.

---

## 9. Backlog of Problems With Estimates

| ID | Problem | Severity | Effort | Likely owner | Suggested next action |
| --- | --- | ---: | ---: | --- | --- |
| P1 | ~~Active `.ai-state/ARCHITECTURE.md` references after dec-132~~ | Critical | M | context-engineer | **Done** — F-01 remediation 2026-06-24 |
| P2 | ~~`architect-validator` misses `.ai-state/DESIGN.md`~~ | Critical | M | architect-validator / cicd-engineer | **Done** — F-02 remediation 2026-06-24 |
| P3 | ~~`PIPELINE_STATE.md` path mismatch~~ | Critical | S | implementer | **Done (2026-06-25)** — resolved to root-scoped; canonical block + onboarding pair re-synced |
| P4 | ~~`precompact_state.py` tells agents to call removed `remember()`~~ | Critical | XS | implementer | **Done** — P4/F-05 remediation 2026-06-24 |
| P5 | ~~Precompact snapshot misses many current artifacts~~ | Important | M | implementer | **Done (2026-06-25)** — list updated (added brief/interface/transactions/pre-refactor/test-results/rework/recovery); registry (F-04) remains the durable follow-up |
| P6 | ~~`/clean-work` unsafe deletion semantics~~ | Critical | M | implementation-planner | **Done (2026-06-25)** — deterministic `clean_work_safety.py` BLOCK/WARN/SAFE gate + `--dry-run` + canary tests |
| P7 | ~~Dashboard/doc manifest stale `.ai-work` list~~ | Important | M | implementer | **Done (2026-06-25)** — both corrected to the registry's 19-artifact dashboard set; drift-guarded (F-04) |
| P8 | ~~Eval task manifest too small~~ | Important | M | test-engineer / implementer | **Done (2026-06-25)** — `LEARNINGS.md` added to `_STANDARD_REQUIRED`; conditional eval specs (TEST_RESULTS/traceability) noted as a follow-up (needs ArtifactSpec activation conditions) |
| P9 | ~~Skill-genesis old ephemeral path remains in consumers~~ | Important | S | context-engineer | **Done (2026-06-25)** — `SKILL_GENESIS_REPORT.md` removed from `build_doc_manifest.py` + dashboard `files.ts` (precompact done batch 2); registry drift test prevents re-introduction |
| P10 | Memory subsystem stale active docs | Important | M | doc-engineer | **Partial (2026-06-25)** — audit-named active surfaces fixed; new clusters split to P26/P27; vestigial refs retained with reasons |
| P11 | ~~`reconcile_ai_state.py` contract overstated in docs~~ | Important | S-M | implementer | **Done (2026-06-25)** — callers aligned to the script's narrow observations+ADR contract |
| P26 | ~~Codex memory bridge still ships memory hooks/gates post-dec-225~~ | Important | M | implementer | **Done (2026-06-25)** — verified the generator (`export-codex-rules-bridge.py`) no longer emits memory hooks (stale `.codex/hooks/` files were gitignored leftovers, deleted); purged stale memory descriptions from `codex/config/README.md`, `README_DEV.md`, `AGENTS.md.tmpl`. Codex-native memory etiquette + the observability hook retained |
| P27 | ~~Roadmap `remember()` persistence cluster is broken~~ | Important | M | context-engineer | **Done (2026-06-25)** — renamed "Memory Candidates" → "Learning Candidates" across `roadmap-cartographer`, `/roadmap`, `roadmap-synthesis` (assets + refs); rerouted persistence to LEARNINGS.md / ADR / idea ledger / surface-to-user; no `remember()` referenced. Inline rationale only (shipped-artifact isolation) |
| P12 | ~~Optional `.ai-state` artifacts lack state labels~~ | Suggested | M | context-engineer | **Done (2026-06-25)** — five-state vocabulary (`active`/`optional-lazy`/`threshold-lazy`/`future-designed`/`historical-retained`) in the rule's compact table + the inventory reference's `State` column (via F-03) |
| P13 | ~~Pre-refactor schema producer/validator mismatch~~ | Important | S | systems-architect / sentinel | **Done** — F-14 remediation 2026-06-24 |
| P14 | ~~Verification report archival before cleanup underspecified~~ | Important | S-M | implementation-planner | **Done (2026-06-25)** — `unmerged-verification` WARN keys on a `### Verification Patterns Merged` marker (F-06 gate) |
| P15 | ~~Interface/transaction challenge artifacts under-discovered~~ | Important | M | interface-designer / dashboard | **Done (2026-06-25)** — `INTERFACE_DESIGN.md` + `TRANSACTIONS_DESIGN.md` now in precompact (batch 2) AND the dashboard/doc manifest (F-04 registry); drift-guarded |
| P16 | ML artifacts not clearly separated as extension family | Suggested | M | systems-architect | Add ML extension artifact subsection |
| P17 | Spec path-repair policy missing | Suggested | S-M | context-engineer | Define immutable-vs-maintained spec fields |
| P18 | `doc_manifest.yaml` freshness not surfaced | Suggested | S | doc-engineer | Add sentinel/doc freshness check |
| P19 | ~~Calibration log append weakly enforced~~ | Important | M | implementation-planner | **Done (2026-06-25)** — sentinel `CA03` coverage check flags under-logging (newest row vs recent pipeline commits); detection over a bypassable command surface |
| P20 | ~~Tech-debt schema duplicated in prose~~ | Suggested | S | context-engineer | **Done** — F-12 remediation 2026-06-24 |
| P21 | Stale `.ai-work` slugs accumulated on disk | Important | M | doc-engineer / context-engineer | Run gated cleanup and add stale-slug advisory |
| P22 | Completed pipeline may be missing spec archival | Important | S-M | implementation-planner | **Partial (2026-06-25)** — cleanup-gating done (F-06 `unarchived-spec` WARN); `l3-readiness-config` investigation remains |
| P23 | ~~`SYSTEM_DEPLOYMENT.md` still lists removed memory infrastructure~~ | Important | S | systems-architect / doc-engineer | **Done** — F-23 remediation 2026-06-24 |
| P24 | `capture_memory.py` name conflicts with observations-only architecture | Suggested | M | implementer | Rename with compatibility or document legacy name |
| P25 | ~~CI/path-scoped architecture filters may miss `DESIGN.md` changes~~ | Critical | M | cicd-engineer / context-engineer | **Done** — F-02/F-25 remediation 2026-06-24 |

---

## 10. Suggested Acceptance Criteria for Future Remediation

A future cleanup pipeline should not call itself complete until:

- [x] No active guidance references `.ai-state/ARCHITECTURE.md`. *(Done 2026-06-24 — F-01; dec-132 rename ADR retains historical before/after narrative only)*
- [x] `architect-validator` and AaC validators inspect `.ai-state/DESIGN.md` where appropriate. *(Done 2026-06-24 — F-02/F-25)*
- [x] `precompact_state.py`, dashboard artifact discovery, doc manifest discovery, and eval task manifest
  agree on the active `.ai-work` artifact registry. *(Done 2026-06-25 — F-04: `scripts/artifact_registry.py`
  is the single source of truth; `scripts/test_artifact_registry.py` fails when any of the four consumers
  diverges. The root cause behind P5/P7/P8/P9/P15 is closed; only the consumers-read-from-registry and
  conditional-eval refinements remain as noted follow-ups.)*
- [x] `/clean-work --dry-run` reports blockers for in-progress WIP, rework manifests, unarchived
  traceability, verifier reports, and recovery logs. *(Done 2026-06-25 — F-06; `clean_work_safety.py`
  BLOCK/WARN classifier + canary tests)*
- Existing stale `.ai-work` task slugs are either cleaned, promoted, or explicitly retained with a
  reason.
- Completed Standard/Full pipelines with REQ IDs or `traceability.yml` have archived specs or a
  recorded exception before cleanup.
- [x] PreCompact hook no longer instructs agents to call `remember()`. *(Done 2026-06-24 — P4/F-05)*
- [x] Active docs no longer describe `remember()` or `memory-mcp` as available Praxion behavior. *(Done 2026-06-25 across the active surfaces — precompact (P4); getting-started/onboarding/agent-pipeline-details/merge-worktree/pr-conventions (P10); reconcile contract (P11); Codex memory bridge (P26); roadmap `remember()` cluster (P27). Vestigial/illustrative/guarded refs and the global-CLAUDE.md philosophy mirror in `AGENTS.md.tmpl` are deliberately retained.)*
- [x] `SYSTEM_DEPLOYMENT.md` reflects the post-dec-225 observations-only state. *(Done 2026-06-24 — F-23)*
- Sentinel or a dedicated test catches hard-coded artifact-list drift.
- Historical artifacts are explicitly exempted from migration sweeps.

---

## 11. Final Judgment

Praxion's generated artifacts are not accidental clutter. Most of them are meaningful coordination
or traceability surfaces, and the lifecycle split is well aligned with the project's philosophy.

The project should not "simplify" by deleting core artifacts like `WIP.md`, `LEARNINGS.md`,
`traceability.yml`, `VERIFICATION_REPORT.md`, ADRs, specs, or the tech-debt ledger. Those artifacts
earn their keep.

The cleanup should instead target **obsolete names, stale producers/consumers, incomplete manifests,
and unsafe deletion paths**. The most reusable future improvement is a canonical artifact registry
that makes lifecycle, producer, consumer, activation, and cleanup policy explicit and testable.
