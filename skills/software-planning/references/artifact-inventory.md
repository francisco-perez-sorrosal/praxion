# Artifact Inventory — Directory Trees and Per-Artifact Writers, Readers, Shape & Lifetime

Back-link: [`rules/swe/agent-intermediate-documents.md`](../../../rules/swe/agent-intermediate-documents.md) — the always-loaded rule that owns the `.ai-work` vs `.ai-state` split, the task-slug convention, the lifecycle-state vocabulary, the tech-debt-ledger writer contract, and cleanup conventions. This reference carries the canonical **directory trees** and the verbose per-artifact detail that does not need to be always-loaded; read it on demand when authoring or consuming a specific artifact.

## Directory Trees

The canonical list of what exists and where. The inventory tables below add the per-artifact **writer/updater**, **reader**, **shape**, and **lifetime** detail, plus the per-row **lifecycle state**.

### `.ai-work/<task-slug>/` — ephemeral pipeline documents

```
<project-root>/
  .ai-work/
    <task-slug>/
      IDEA_PROPOSAL.md
      TASK_BRIEF.md
      RESEARCH_FINDINGS.md
      CONTEXT_REVIEW.md
      INTERFACE_DESIGN.md
      TRANSACTIONS_DESIGN.md
      CONSULT_<discipline>.md
      SYSTEMS_PLAN.md
      PRE_REFACTOR_PLAN.md
      SPEC_DELTA.md
      IMPLEMENTATION_PLAN.md
      WIP.md
      LEARNINGS.md
      TEST_BASELINE.md
      TEST_RESULTS.md
      traceability.yml
      VERIFICATION_REPORT.md
      REWORK_MANIFEST.md
      PROGRESS.md
```

`PROGRESS.md` is an append-only journal written by **the orchestrator alone, and only in hackathon mode** -- the record of skipped stages, mid-task movement, and creative blockers. The per-phase *agent* write mandate was retired: pipeline agents report through their terminal marker and `WIP.md` checkbox, which is what the recovery reconciler reads. Format: `[TIMESTAMP] [WRITER] <event> -- [summary] #label1 #key=value`

- Dot-prefixed — hidden by default in file browsers and `ls`
- **Task-scoped** — each run uses its own `<task-slug>/` subdirectory, preventing collisions between concurrent pipelines
- **Worktree-scoped** — `.ai-work/` is gitignored, so each worktree holds its own copy; under `EnterWorktree` the pipeline's `.ai-work/` lives inside the worktree, isolated from other sessions
- Created on first use — agents create `.ai-work/<task-slug>/` when writing their first document

Scope: **exclusively for agent coordination pipeline documents** — the outputs defined in the SWE agent coordination protocol rule. Not stored here: command scratch files or skill working files; project documentation or ADRs; build artifacts or tool caches.

### `.ai-state/` — persistent project intelligence

```
<project-root>/
  .ai-state/
    calibration_log.md
    observations_summary.jsonl
    token_budget_baseline.json
    DESIGN.md
    SYSTEM_DEPLOYMENT.md
    TEST_TOPOLOGY.md
    TECH_DEBT_LEDGER.md
    CONSULT_LEDGER.md
    CONSULT_COSTS.md
    CONSULT_PRIORS.md
    decisions/
      <NNN>-<slug>.md
      DECISIONS_INDEX.md
    specs/
      SPEC_<name>_YYYY-MM-DD.md
    sentinel_reports/
      SENTINEL_REPORT_*.md
      SENTINEL_LOG.md
    skill_genesis_reports/
      SKILL_GENESIS_REPORT_*.md
      SKILL_GENESIS_LOG.md
    metrics_reports/
      METRICS_REPORT_*.{md,json}
      METRICS_LOG.md
    idea_ledgers/
      IDEA_LEDGER.md
    eval_ledger/
      EVAL_LOG.md
    project_profile.yaml
```

- Committed to git — versioned, shareable, accumulates value over time
- **Worktree-aware** — in a worktree, `.ai-state/` changes are committed on the pipeline branch and reconciled at merge (see [.ai-state/ Reconciliation](agent-pipeline-details.md#ai-state-reconciliation-for-worktree-merges))
- Created on first use — agents create `.ai-state/` when writing their first persistent document

The trees are the canonical file list; the inventory is derivable from the filesystem.

## Lifecycle States

| State | Meaning when the artifact is absent (examples: `active` — `WIP.md`, `SYSTEMS_PLAN.md`, `VERIFICATION_REPORT.md`, `DESIGN.md`, `decisions/`, `calibration_log.md`, `specs/`, sentinel/metrics/idea/skill-genesis reports; `optional-lazy` — `principles.yaml`, `LANDSCAPE_WATCHLIST.md`, the ML `training_runs/` family, `eval_ledger/EVAL_LOG.md`; `threshold-lazy` — `TEST_TOPOLOGY.md` (M2+ adoption); `future-designed` — `project_profile.yaml`) |
|---|---|
| `active` | A real gap — the artifact should exist for this project/pipeline. |
| `optional-lazy` | The feature was not adopted; absence is expected and fine. |
| `threshold-lazy` | The project has not crossed the growth threshold that activates it yet. |
| `future-designed` | The producer is designed but not yet wired; absent on essentially all projects today. |

## `.ai-state/` Persistent Artifacts

The tree above is the canonical list. Per-artifact detail:

| Artifact | State | Writers / updaters | Shape · lifecycle · reference |
|---|---|---|---|
| `idea_ledgers/IDEA_LEDGER.md` | active | promethean | Single living file; promethean updates it **in place** per run (sentinel baseline, implemented/pending/discarded ideas, future paths). Prior timestamped per-run files were consolidated into it (Wave 4a); their history is in git. |
| `sentinel_reports/SENTINEL_REPORT_*.md` + `SENTINEL_LOG.md` | active | sentinel | Timestamped audit reports + an append-only run-summary table (timestamp, report file, health grade, finding counts, coherence grade), co-located. |
| `skill_genesis_reports/SKILL_GENESIS_REPORT_*.md` + `SKILL_GENESIS_LOG.md` | active | skill-genesis (writes both); `/skill-genesis-review` (updates report frontmatter + Disposition Log; updates log Review Status column) | Per-run report + append-only run log; frozen aggregate-block column contract; co-located. |
| `metrics_reports/METRICS_REPORT_*.{md,json}` + `METRICS_LOG.md` | active | `/project-metrics` | Per-run JSON+MD report pairs + an append-only aggregate row per run, co-located. |
| `eval_ledger/EVAL_LOG.md` | optional-lazy | the project's eval loop (appends per kept run) via `append_eval_log_row()` in `skills/agent-evals/scripts/append_eval_log.py` — **no onboarding producer**: onboarding does not create this file; the eval loop invokes the helper lazily on the first kept run | Append-only one-row-per-kept-run leaderboard (agentic/eval archetype). Schema: `skills/agent-evals/references/run-ledger-schema.md`. |
| `discipline_registry_overlay.md` | optional-lazy | user / managed project (hand-authored opt-in — no onboarding producer) | Project-local consulting-discipline roster overlay, unioned with the shipped registry at consult time; a duplicate key is a named `[BLOCKED]` error, never an override. |
| `project_profile.yaml` | future-designed | **no active producer yet** — the archetype-detection scaffold that would create it is designed but not yet wired into `/onboard-project`; downstream agents MUST treat it as optional (absent on most projects) and fall back to live detection | YAML project profile (paradigm, archetype, run_store_root/backend, eval_framework); machine-consumable when present. |
| `specs/SPEC_<name>_YYYY-MM-DD.md` | active | implementation-planner | Archived behavioral spec + traceability matrix; created at end-of-feature for medium/large tasks. |
| `calibration_log.md` | active | main agent (append-only) | Tier-selection log (timestamp, task, signals, recommended/actual tier, source, retrospective); consumed by sentinel for calibration-trend analysis. |
| `decisions/drafts/<fragment>.md` (fragment) → `decisions/<NNN>-<slug>.md` (finalized) + `DECISIONS_INDEX.md` | active | systems-architect, implementation-planner, interface-designer, orchestrator, user (write fragments); index auto-generated from ADR frontmatter | Numbered ADR files (YAML frontmatter + MADR body). Format in [`adr-conventions.md`](../../../rules/swe/adr-conventions.md). |
| `SYSTEM_DEPLOYMENT.md` | active | systems-architect (creates); implementer (configs), cicd-engineer (CI/CD); verifier + sentinel validate | Living single file; section ownership prevents conflicts. Template: `skills/deployment/assets/SYSTEM_DEPLOYMENT_TEMPLATE.md`. |
| `DESIGN.md` | active | systems-architect (creates); implementation-planner / implementer on structural changes; verifier + sentinel validate | Living single file at `.ai-state/DESIGN.md`; section ownership; architect-facing design-target (abstracts above concrete code to define the space of valid implementations). Template: `skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md`. Dev-facing counterpart: `docs/architecture.md` (below). |
| `TEST_TOPOLOGY.md` | threshold-lazy | systems-architect (Subsystems table), test-engineer (per-group definitions), implementation-planner (per-pipeline `integration_boundaries`) | Per-project test-group topology; populated at M2+ via `/refresh-topology --init` once a project grows past the adoption thresholds; the pipeline agents author and honor it (M2 behavioral wiring). Praxion itself does not populate its own (pilot deferral). Schema: `skills/testing-strategy/references/test-topology.md`. |
| `docs/architecture.md` *(in `docs/`, not `.ai-state/`)* | active | systems-architect (creates alongside `.ai-state/DESIGN.md`); implementation-planner (planning-stage structural gaps), implementer (Post-implementation updates: update developer architecture guide); doc-engineer at pipeline checkpoints | Dev-facing architecture navigation guide; every component name + file path verified against the codebase; derived from `.ai-state/DESIGN.md` filtered to Built components. Template: `skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md`. |

Optional/adoption-gated persistent artifacts not in the tree above (created only when a project opts in): `principles.yaml` (`optional-lazy` — optional project principle gates), `LANDSCAPE_WATCHLIST.md` (`optional-lazy` — external-source watchlist), `UPSTREAM_ISSUES.md` (`active` once `/report-upstream` is used), and the ML/training family `training_runs/*.md` / `gpu_budget.yaml` / `neo_cloud_backend.yaml` (`optional-lazy` — ML/AI training projects only).

## Document Lifecycle Full Table

| Tier | Location | Documents | Lifetime |
|------|----------|-----------|----------|
| Ephemeral | `.ai-work/<task-slug>/` | `TASK_BRIEF.md` — writer: orchestrator at the Intake Clarity Gate (before any agent spawn); readers: researcher + systems-architect (first input — authoritative Intent / Key Signals), implementation-planner (Key Signals → step acceptance tests; Uncertainty Flags → spikes), test-engineer (signals → test nodes), verifier (Key Signals = primary rubric, Health Guards = regression checklist). Captured at Lightweight+ when success is non-obvious; skipped at Direct. Shape + template: `goal-disambiguation` skill | Single pipeline run — Key Signals merged into the archived SPEC / `VERIFICATION_REPORT.md`, then deleted with `.ai-work/` |
| Ephemeral | `.ai-work/<task-slug>/` | `IDEA_PROPOSAL.md`, `RESEARCH_FINDINGS.md`, `CONTEXT_REVIEW.md`, `INTERFACE_DESIGN.md`, `TRANSACTIONS_DESIGN.md`, `SYSTEMS_PLAN.md`, `SPEC_DELTA.md`, `VERIFICATION_REPORT.md`, `REWORK_MANIFEST.md`, `PROGRESS.md` (hackathon mode only) | Single pipeline run — delete after downstream consumption (merge `VERIFICATION_REPORT.md` patterns into `LEARNINGS.md` first). `INTERFACE_DESIGN.md` (interface-designer pipeline output: interface architecture, framework/paradigm decisions, UI/API sketches, trade-offs, `## Architecture Challenges`) is consumed by planner, implementer, and verifier. `TRANSACTIONS_DESIGN.md` (agentic-transactions-architect pipeline output: provider-contract analysis, mandate/settlement/HITL decisions, trade-offs, `## Architecture Challenges`) is consumed by planner, implementer, and verifier. `REWORK_MANIFEST.md` — writer: verifier (Phase 12.5); reader: main agent; cleanup gated on rework completion. |
| Ephemeral | `.ai-work/<rework-slug>/` | `VERIFIER_FINDINGS.md` — writer: main agent; reader: `/resume-rework` + spawned session | Worktree-local ephemeral. |
| Ephemeral | `.ai-work/<task-slug>/` | `PRE_REFACTOR_PLAN.md` — writer: systems-architect (Phase 2.5 outcome `emit-PRE_REFACTOR_PLAN`); readers: orchestrator (parses `## Verifier Bypass Criteria` + `## Loop-Back Conditions`), implementation-planner (steps tagged `[Phase: Refactoring]`), test-engineer (sources characterization-tests from `## Behavior Preservation Contract`), verifier (sources acceptance criteria from `## Acceptance Criteria` in pre-refactor mode) | Single pipeline run — receives a `[CONSUMED]` marker at architect's `post-refactor-adaptation` re-entry; deleted with `.ai-work/` at cleanup |
| Ephemeral | `.ai-work/<task-slug>/` | `TEST_BASELINE.md` — implementation-planner's pre-pipeline failing-test snapshot (failing node IDs + base commit SHA), captured before any code change; verifier Phase 10 reads it to separate regressions from pre-existing failures | Single pipeline run — delete with `.ai-work/` |
| Ephemeral | `.ai-work/<task-slug>/` | `TEST_RESULTS.md` — implementer (or test-engineer) test-run handoff artifact (canonical schema in `skills/software-planning/references/agent-pipeline-details.md`) | Single pipeline run — merge into `VERIFICATION_REPORT.md`, then delete |
| Ephemeral | `.ai-work/<task-slug>/` | `traceability.yml` — REQ-to-test/implementation mapping (canonical source of truth during the pipeline; rendered into the archived SPEC's matrix at feature end per [`id-citation-discipline.md`](../../../rules/swe/id-citation-discipline.md)) | Single pipeline run — rendered into archived SPEC matrix, then deleted with `.ai-work/` |
| Session-persistent | `.ai-work/<task-slug>/` | `IMPLEMENTATION_PLAN.md`, `WIP.md`, `LEARNINGS.md` | Across sessions — merge learnings into permanent locations at feature end |
| Permanent | `.ai-state/` | `idea_ledgers/IDEA_LEDGER_*.md`, `sentinel_reports/{SENTINEL_REPORT_*.md, SENTINEL_LOG.md}`, `skill_genesis_reports/{SKILL_GENESIS_REPORT_*.md, SKILL_GENESIS_LOG.md}`, `metrics_reports/{METRICS_REPORT_*.{md,json}, METRICS_LOG.md}`, `specs/SPEC_*.md`, `calibration_log.md`, `decisions/<NNN>-<slug>.md`, `SYSTEM_DEPLOYMENT.md`, `DESIGN.md`, `TEST_TOPOLOGY.md`, `TECH_DEBT_LEDGER.md` (active) + `TECH_DEBT_RESOLVED.md` (terminal), `eval_ledger/EVAL_LOG.md`, `observations_summary.jsonl` (one committed rollup row per session, written atomically at Stop; the raw `observations.jsonl` WAL and `praxion_eval_reports/judge_cache.jsonl` are local-only and gitignored -- the judge cache is content-addressed and a fresh clone re-judges (`td-189`)), `token_budget_baseline.json` (dated always-loaded measurements + the frozen listing ceiling read by `measure_token_budget.py --ratchet`), `project_profile.yaml` | Project lifetime — committed to git, timestamped per run or living document |
| Permanent | `docs/` | `architecture.md` | Project lifetime — committed to git, derived from `.ai-state/DESIGN.md`, maintained by pipeline agents |

The machine-readable counterpart for the `.ai-work/<slug>/` set (consumed by the doc manifest, dashboard, eval manifest, and precompact hook) is [`scripts/artifact_registry.py`](../../../scripts/artifact_registry.py); drift between its consumers is caught by `scripts/test_artifact_registry.py`.

## ML/AI Training Extension Artifacts

A **conditional extension family** — present only on ML/AI **training** projects (those onboarded with the training archetype: `train.py`/`prepare.py`/`program.md` present). All are `optional-lazy`: absent on every non-training project, and absence is never a defect. They are *adjacent* to the core SWE pipeline, not part of it — a SWE-shaped pipeline neither produces nor expects them, and they should not be generalized onto non-training projects.

| Artifact | Location | State | Producer / consumers | Activation |
|---|---|---|---|---|
| `TRAINING_RESULTS.md` | `.ai-work/<slug>/` | optional-lazy | `/run-experiment` (writer); `/check-experiment`, verifier Phase 3a, archival (readers) | A training-dispatch step ran. Canonical schema: `skills/llm-training-eval` |
| `training_runs/*.md` | `.ai-state/` | optional-lazy | ML workflow | Per-run training records on a training project |
| `gpu_budget.yaml` | `.ai-state/` | optional-lazy | ML workflow / `/check-experiment` | Compute-budget tracking for owned/rented GPU modes |
| `neo_cloud_backend.yaml` | `.ai-state/` | optional-lazy | ML workflow; read by the `neo-cloud-abstraction` skill | A training-job dispatch backend is configured (local / SkyPilot / RunPod / Nebius) |

Owning skills: `ml-training`, `llm-training-eval`, `neo-cloud-abstraction`, `experiment-tracking`. The verifier reads `TRAINING_RESULTS.md` under Phase 3a only when it is present; its absence on a SWE task is expected, not a missing deliverable.
