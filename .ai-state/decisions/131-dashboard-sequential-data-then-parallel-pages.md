---
id: dec-131
title: Pipeline Dashboard — sequential data layer before parallel page steps
status: retired
retired_by:
  - dec-134
category: implementation
date: 2026-05-07
summary: Data layer (discovery, parsers, cache) must complete before any page step begins; pages themselves are fully parallel.
tags: [pipeline-dashboard, step-ordering, parallelism, implementation]
made_by: agent
agent_type: implementation-planner
pipeline_tier: full
affected_files:
  - streamlit_app/data/discovery.py
  - streamlit_app/data/parsers.py
  - streamlit_app/data/cache.py
  - streamlit_app/pages/architecture.py
  - streamlit_app/pages/workshops.py
  - streamlit_app/pages/adrs.py
  - streamlit_app/pages/sentinel.py
  - streamlit_app/pages/roadmap.py
  - streamlit_app/pages/metrics.py
---

## Context

The pipeline dashboard has a four-layer architecture (launcher / data / pages / widgets). Page modules call data layer functions. The step decomposition must decide whether to run data-layer implementation in parallel with page implementation, or sequentially.

## Decision

Run data layer steps (Phases 3–4: `data/discovery.py`, `data/parsers.py`, `data/cache.py`, shared widgets) sequentially before the six page steps (Phase 5). Page steps within Phase 5 are fully parallel (all file sets disjoint).

## Considered Options

### Option A: Full parallelism from day one

Data layer and pages all parallel. Page test-engineers design tests using stubs/mocks for the data layer.

**Pros**: Maximum concurrency; shorter wall time.
**Cons**: Page implementers cannot call real data layer functions; tests must mock data layer; integration surprises at Step 13 checkpoint; mock-vs-real delta is the primary failure mode identified in Praxion's testing memory (`gotcha_xterm_attachaddon_intercept.md` analogue).

### Option B: Sequential data layer, then parallel pages (chosen)

Data layer completes (Phases 3–4) and turns green before any page step starts. Pages share the same parallel group (G1–G6) and run concurrently.

**Pros**: Page implementers call real data layer code; tests use real fixtures (not mocks); no mock/real divergence at integration checkpoint; page test-engineers design tests from actual data shapes returned by the real layer.
**Cons**: Slightly longer wall time if data layer takes several sessions (unlikely — 3 small modules).

### Option C: Sequential everything

All steps run in strict sequence.

**Pros**: Simplest supervision.
**Cons**: 6 page steps that are fully disjoint take 6× longer than needed. Unjustified for fully independent modules.

## Consequences

**Positive**: Integration checkpoint (Step 13) validates real data flows, not mock contracts. No mock/real divergence risk. Each page's test-engineer writes tests using the same fixture shapes the real data layer produces.

**Negative**: Data layer must complete before Phase 5 parallelism begins. Estimated 3–5 sessions for data layer (3 paired steps with checkpoints); acceptable given the parallelism gain in Phase 5.

## Prior Decision

Retired by `dec-134`, which replaced the Streamlit dashboard runtime with the Next.js app. This decision was a step-ordering constraint over a specific set of Streamlit modules — a data layer of `discovery`/`parsers`/`cache` feeding six page modules. That module structure no longer exists, and `dec-134` proposed no ordering of its own; it changed what was being built rather than the sequence in which to build it.

Sibling dashboard decisions from the same pipeline were **not** retired, because their substance outlived the runtime: the per-project sha256 port derivation, the bash-ctl process model, the dedicated dashboard home, and the 15-second poll default with its environment override all survive in the Next.js implementation, and `dec-134` explicitly names them as preserved. Only the build-ordering constraint was specific to the runtime that went away.

This decision matters again if a dashboard rewrite reintroduces a shared data layer that page modules depend on — the reasoning (integrate against real data flows rather than mock contracts) is not Streamlit-specific.
