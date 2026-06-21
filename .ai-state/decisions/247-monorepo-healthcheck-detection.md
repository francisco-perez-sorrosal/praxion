---
id: dec-247
title: Make readiness healthcheck detection monorepo-aware (subdir-service + route-handler signals)
status: accepted
category: architectural
date: 2026-06-20
summary: Extend _detect_healthcheck beyond the root Dockerfile/package.json to a bounded subtree scan that recognizes a subdir Dockerfile HEALTHCHECK, a subdir package.json health signal, or a route.* handler inside a health/healthz/healthcheck directory.
tags: [readiness, healthcheck, observability, monorepo, metrics, detector]
made_by: agent
agent_type: orchestrator
branch: feat-healthcheck-baseline
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/collectors/readiness/checks.py
  - scripts/project_metrics/tests/test_readiness_checks.py
dissent: A subtree scan adds per-run cost and false-positive surface (any route.* in a health-named dir counts, even a non-deployed example or a fixture); the root-only detector plus the readiness_config pillar-weight escape hatch already handles non-service repos without changing detection semantics for every project.
---

## Context

The agent-readiness `c.observability.healthcheck` criterion is satisfied by `_detect_healthcheck`, which read **only** the repository-root `Dockerfile` (for a `HEALTHCHECK` instruction) and the root `package.json` text (for `healthz`/`/health`). This is a blind spot for **monorepos** whose deployable service lives in a subdirectory: the service can carry a perfectly good health surface and the detector never sees it. Praxion is exactly this shape — the root is plugin/philosophy infrastructure with no `Dockerfile` or root `package.json`, while the real runtime service (the dashboard) lives under `dashboard_app/`. A dashboard health route was therefore invisible to readiness.

## Decision

Extend `_detect_healthcheck` with a **bounded, deterministic subtree scan** (in addition to the preserved root signals). A health signal is recognized when any non-excluded subdirectory contains: a `Dockerfile` with `HEALTHCHECK`; a `package.json` mentioning `healthz`/`/health`; or a `route.*` handler inside a `health`/`healthz`/`healthcheck` directory (the modern app-router convention). The scan prunes the standard noise directories (`node_modules`, `.venv`, `.git`, `.ai-state`, …), is depth-capped, and sorts its walk for byte-identical determinism (the readiness collector's contract). Root signals are unchanged, so existing single-service detection is preserved.

## Considered Options

### Option 1 — Monorepo-aware subtree scan (chosen)
- **Pros:** detects real healthchecks wherever the service actually lives; benefits every monorepo managed project, not just Praxion; recognizes route-based health endpoints (the dominant modern pattern the package.json-substring heuristic missed).
- **Cons:** an extra (bounded) filesystem walk per facts-derivation; a wider match surface that could in principle count a non-deployed example.

### Option 2 — Leave the detector root-only; use the pillar-weight escape hatch
- **Pros:** zero detection-semantics change; no scan cost; non-service repos already down-weight observability in `readiness_config.json`.
- **Cons:** a genuinely healthchecked subdir service still scores zero on the criterion — the detector stays wrong for monorepos; weighting hides the gap rather than measuring reality.

### Option 3 — Require a root-level signal (root Dockerfile/compose) to satisfy as-is
- **Cons:** forces root containerization a repo may not need just to satisfy a detector; least honest.

## Consequences

**Positive:** the detector now reflects reality for monorepos; Praxion's dashboard healthcheck (a real `/api/health` route returning 503 when its data root is unreachable) is correctly recognized; the change is covered by tests (root-preserved, subdir-Dockerfile, subdir-package.json, route-handler, absent, excluded-dir-ignored). **Negative:** a small per-run scan cost (measured ~8–50ms on this repo, short-circuiting on first match) and a wider match surface — mitigated by directory exclusions, a depth cap, and the deterministic sort.

## Disconfirmation

- **Falsifier:** evidence that the subtree scan produces false positives in practice (a repo scoring a healthcheck it does not actually deploy) or material per-run cost on a large monorepo — either would mean the root-only detector plus weighting was the better trade.
- **Steelmanned runner-up:** Option 2. The root-only detector has zero false-positive surface and the `readiness_config` weight already lets a non-service repo opt out of the observability pillar honestly; one could argue detection should stay conservative and let humans weight, rather than widening what counts as a "healthcheck" for every project. It loses because a *deployed subdir service with a real health route* genuinely has a healthcheck, and a detector that scores it zero is simply wrong — weighting cannot fix a wrong measurement, only hide it.
- **Reversal trigger:** revisit if false positives or scan cost surface in real managed-project runs, or if a declared service-manifest (`project_profile.yaml` services) becomes available — at which point detection should target *declared* service dirs rather than scanning the whole subtree.
