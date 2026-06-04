---
id: dec-draft-1f4628c3
title: Agent-readiness output embeds as a `readiness` block in the metrics JSON, not a sibling readiness_reports/ artifact
status: proposed
category: architectural
date: 2026-06-04
summary: Readiness is produced by the same /project-metrics run as the other collectors, so its output is a `readiness` collector namespace flattened to the metrics JSON root (schema_version 1.0.0→1.1.0, additive) rather than a separate .ai-state/readiness_reports/ directory; this inherits path security, latest-report selection, and the dashboard type chain at a ~5-file dashboard cost vs ~7 for a sibling.
tags: [agent-readiness, project-metrics, schema, dashboard, storage-layout, embed]
made_by: agent
agent_type: systems-architect
branch: worktree-factory-agent-readiness-research
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/schema.py
  - scripts/project_metrics/report.py
  - dashboard_app/src/server/view-models/metrics.ts
  - dashboard_app/src/lib/metrics.ts
---

## Context

Agent readiness needs a persistence and surfacing model. The early proposal (§6) imagined a standalone `/readiness` command writing `READINESS_REPORT_*.md` into `.ai-state/readiness_reports/`, mirroring sentinel/metrics. The grounded v2 design (§II) folds readiness into `/project-metrics` instead: readiness is computed in the same run as the other collectors and shown on the dashboard's Metrics page. The user confirmed the embed direction (decision 1, 2026-06-04).

Two production/storage models were on the table:
- **Embed** — readiness is a collector namespace (`readiness`) that `render_json()` flattens to the metrics JSON root, living inside the existing `METRICS_REPORT_*.json`.
- **Sibling** — readiness has its own `.ai-state/readiness_reports/READINESS_REPORT_*.json` lifecycle with an independent producer cadence.

## Decision

**Embed.** The readiness output is the `readiness` collector namespace, flattened to the metrics JSON root by `render_json()` alongside `git`, `scc`, `coverage`, etc. The metrics `schema_version` bumps **minor** (`1.0.0` → `1.1.0`, additive); `trends.status` stays `"computed"`. `readiness` is treated as an ordinary collector key — it is **not** added to `_RESERVED_ROOT_KEYS`. No new `.ai-state/` directory, no new report-file convention, no new path-allowlist entry.

The dashboard reads the block through the existing metrics type chain: `RawMetricsReport.readiness` (loose) → `buildReadiness()` → typed `ReadinessSnapshot` on `MetricsSnapshot` → an `AgentReadinessSection` `<section>`.

## Considered Options

### Option 1 — Embed in the metrics JSON (chosen)

- **Pros**: inherits path security automatically (`assertAllowedArtifactPath` already covers `.ai-state/metrics_reports/`); inherits "latest report" selection (lexicographic filename sort); inherits the existing type chain; readiness is always time-aligned with the metrics run that produced it; dashboard cost ≈ 5 files; no new state directory for `/onboard-project` to scaffold.
- **Cons**: readiness cannot have an independent producer cadence — it only updates when `/project-metrics` runs.

### Option 2 — Sibling `.ai-state/readiness_reports/` directory

- **Pros**: independent lifecycle; a future dedicated `/readiness` command could update readiness without a full metrics run.
- **Cons**: needs a new `isReadinessReport` filename regex, a new entry in `ALLOWED_ARTIFACT_ROOTS`, a second server-side read in `MetricsPage`, and a second `listDirectory`/"latest" selection path; dashboard cost ≈ 7 files; readiness timestamps could diverge from metrics-run timestamps. The user dropped the standalone `/readiness` command (the `agent-readiness` skill is the standalone entry), removing the independent-producer justification. Rejected.

## Consequences

**Positive:**
- Minimal blast radius on the dashboard (≈5 files) and zero new persistence surface.
- Readiness and the rest of the metrics snapshot are always consistent (one run → one report → one readiness block).
- `/onboard-project` needs no new directory scaffold — readiness embeds in the already-installed `metrics_reports/` artifacts.

**Negative / accepted:**
- Readiness updates are coupled to `/project-metrics` invocations. Accepted — readiness is a per-metrics-run signal by design; there is no requirement for an independent cadence in v1.
- The metrics report grows by one block. Negligible (the readiness block is small relative to per-file complexity payloads already in the JSON).

## Prior Decision

This draft revises the standalone-artifact model in `INTEGRATION_PROPOSAL.md §6` (which proposed `.ai-state/readiness_reports/` + a `/readiness` command). §II superseded §6's standalone-command architecture; this ADR records the storage-layout half of that supersession (embed over sibling). A future supersession would require a concrete need for an independent readiness producer cadence decoupled from `/project-metrics`.
