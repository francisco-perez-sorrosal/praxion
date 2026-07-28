---
id: dec-draft-f2d6c106
title: P6 self-healing-loop metrics baseline — on-demand gh-run-history collector in a distinct SELF_HEALING_* namespace, non-skipped attempts metric, deferred gate-verdict and in-place-fix detection
status: proposed
category: implementation
date: 2026-07-28
summary: P6 stands up a read-only, on-demand collector (`scripts/self_healing_metrics.py`) over the loop's GitHub Actions run history, emitting a SELF_HEALING_* report triple to `.ai-state/metrics_reports/` — a namespace deliberately distinct from the code-health METRICS_REPORT_* triple to avoid schema collision. It counts non-skipped autofix *attempts* (not raw runs, which skips dominate), flags fetch-limit saturation, and records credit-burn, gate-verdict classification, in-place-fix detection, and override rate as explicit deferred/operator-supplied nulls rather than fabricated zeros.
tags: [self-healing-loop, metrics, p6, observability, ci-cd, auditability, deferred-detection]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/self_healing_metrics.py
  - scripts/test_self_healing_metrics.py
  - commands/loop-metrics.md
  - .ai-state/metrics_reports/SELF_HEALING_LOG.md
---

## Context

The self-healing loop (Subsystems A/B/C) is live on main (dec-273..288). Brief §7's
auditability row and §8's P6 phase call for a metrics baseline — gate catch-rate vs
noise, credit burn, fix success, time-to-green, override rate, cost-per-fix — stood up
*now* so the 60–90d recalibration of the §9 ADR seeds' reversal triggers can accrue.
This is the baseline + first snapshot, not the recalibration itself. On a days-old loop
the first snapshot is intentionally sparse; the deliverable is the ready-to-accrue
collector.

Two constraints shaped the design. (1) The data lives in GitHub Actions run history,
reachable only via authenticated `gh` — a network/auth dependency the existing offline,
working-tree-only `scripts.project_metrics` code-health collector does not have. (2) The
mission's literal `.ai-state/metrics_reports/METRICS_REPORT_*.{md,json}` + `METRICS_LOG.md`
target **already names the code-health triple** — reusing those names would corrupt that
log's fixed SLOC/churn schema and expose the new files to its retain-last-N prune.

## Decision

Ship a **separate, read-only, on-demand** collector `scripts/self_healing_metrics.py`
(mirroring project_metrics' CLI-wrapper → report-triple → append-log shape) rather than
extending project_metrics. Emit to `.ai-state/metrics_reports/` under a **distinct
`SELF_HEALING_REPORT_<ts>.{json,md}` + `SELF_HEALING_LOG.md`** namespace. `gh` I/O is
isolated in `fetch_raw`; `compute_metrics` is pure and fixture-tested.

Metric-definition calls:

- **Fix success counts non-skipped *attempts*, not raw runs.** Every main push fires
  `workflow_run` → autofix → `skipped`, so skips dominate (first snapshot: 170/200
  skipped). `attempts` = runs whose conclusion ∉ {skipped, cancelled, null}; `failures`
  within attempts is surfaced (first snapshot: 12/17 — itself a health signal).
- **Fetch-limit saturation is flagged**, so a saturated count reads as a floor.
- **Deferred / operator-supplied fields are explicit `null` + `_note`, never a
  fabricated zero:** credit burn (Cursor pool, not GitHub-queryable — operator-supplied);
  gate-verdict classification (request-changes vs approve lives in the PR review comment,
  not the run conclusion — deferred until real gate comments exist to pattern-match);
  in-place P3a fixes (pushed to the *existing* PR branch with an `Autofix-Attempt:`
  trailer, not a `ci-autofix/` branch — `fix_prs_*` scope is new-branch-only, trailer-scan
  deferred); override rate and cost-per-fix (derive from the two deferred inputs above).

## Considered Options

### A. Separate SELF_HEALING_* collector (chosen)
Pro: decoupled from the offline code-health collector (different data source, auth,
failure mode); no schema collision; independent prune/limit policy. Con: a second
collector to maintain; some boilerplate overlap with project_metrics' triple/log shape.

### B. Extend `scripts.project_metrics` with a loop collector
Pro: one collector, DRY on the triple/log plumbing. Con: couples a network+auth-requiring
source into a currently offline, working-tree-only package (different volatility, per
Balanced Coupling); risks the code-health run failing when `gh` is unavailable; the
namespace collision remains unless sub-namespaced anyway.

### C. Reuse the literal METRICS_REPORT_* / METRICS_LOG.md names (mission's literal text)
Pro: matches the phrasing verbatim. Con: corrupts the code-health log's fixed schema and
subjects the new files to project_metrics' retain-last-N prune — rejected as unsafe.

## Consequences

Positive: the baseline immediately quantified a real health problem (12/17 autofix
attempts failing) and, via live dogfood, exposed the in-place-fix detection gap before it
silently undercounted. Deferred fields are honest and named, so the recalibration pass has
a punch-list. Negative: several headline metrics (gate catch-rate, override rate,
cost-per-fix) are null at baseline pending the deferred wiring; the first snapshot's
signal is thin.

## Disconfirmation

- **Falsifier:** if the recalibration pass finds the deferred fields (gate verdict, credit
  burn) are the *only* ones that matter and the baseline's attempt/failure counts add no
  decision value, the separate-collector overhead was unjustified.
- **Steelmanned runner-up:** Option B (extend project_metrics) — wins if the loop metrics
  turn out to need the same churn/ownership joins the code-health collector already
  computes, making shared plumbing worth the coupling.
- **Reversal trigger:** if a scheduled continuous-collection need emerges (the metrics must
  accrue without manual `/loop-metrics` runs), the on-demand script grows a workflow — at
  which point re-tier to Standard under the CI hard-constraints and revisit whether the
  collector belongs in a workflow-owned package.
