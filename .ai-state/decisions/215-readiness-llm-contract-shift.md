---
id: dec-215
title: The agent-readiness LLM enrichment runs outside the metrics collect pass — a conditional network dependency entering a previously pure-offline package
status: accepted
category: architectural
date: 2026-06-04
summary: Default-on LLM-judged readiness criteria introduce a conditional network+auth dependency into the previously pure-offline scripts/project_metrics package. To preserve the collector determinism contract, the non-deterministic LLM call runs in a cli.py enrich_readiness step AFTER the runner's deterministic collect pass, not inside ReadinessCollector.collect(); CollectionContext is NOT widened.
tags: [agent-readiness, project-metrics, determinism, collector-protocol, contract-shift, llm, graceful-degradation]
made_by: agent
agent_type: systems-architect
branch: worktree-factory-agent-readiness-research
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/cli.py
  - scripts/project_metrics/collectors/readiness_collector.py
  - scripts/project_metrics/collectors/base.py
---

## Context

Two contracts of the `scripts/project_metrics` package are in tension with the user's "default-on LLM readiness" decision:

1. **Pure-offline nature.** Every collector to date runs offline against the working tree (git, scc, uvx-launched tools, coverage-artifact reads). No collector makes a network call. The package's value proposition includes "runs read-only against the working tree; never installs dependencies."
2. **The collector determinism contract.** `collectors/base.py`'s `CollectionContext` is a frozen dataclass with **exactly three fields** (`repo_root`, `window_days`, `git_sha`). Its docstring is explicit: *"`collect()` MUST produce byte-identical output given the same context, so any new axis of variance … is an ADR-amendment-level decision — it widens the variance surface and the test suite guards the field set against drift."* `collect(ctx)`'s docstring repeats: *"Must be deterministic given the same context."* Golden-file tests assert byte-identical collector output.

A default-on LLM judge is inherently **non-deterministic** (model output varies run-to-run) and **network/auth-dependent**. Placing it inside `ReadinessCollector.collect()` would violate both the determinism contract and the offline assumption, and would break the collector's golden tests.

## Decision

**The LLM enrichment runs outside the runner's collect pass.**

- `ReadinessCollector.collect(ctx)` computes only the **deterministic mechanical criteria** and scoring, and sets a placeholder `readiness.data.llm = {"status": "pending"}`. It remains byte-identical given the same `CollectionContext`, honoring the contract unchanged.
- A new `enrich_readiness(report, repo_root, args)` step in `cli.py` runs **after** `Runner.run()` (step 4) and **before** `_write_report()` (step 5). It performs the non-deterministic, network-dependent work: auth detection, grounding on the prior report, the `urllib` judge calls (`dec-214`), merging verdicts into the `readiness` block, and recomputing the level over (mechanical ∪ scored-LLM) criteria.
- **`CollectionContext` is NOT widened.** No `llm_enabled`/auth axis is added — that would expand the variance surface for *every* collector and break the field-set drift guard. The flag/auth state is threaded through `cli.py`'s `args`, never through the collector context.

**The contract shift is acknowledged and bounded:** the metrics package now has a *conditional* network+auth dependency, exercised only when (a) the readiness collector is registered, (b) `--mechanical-only` is not set, and (c) auth is present. Graceful degradation preserves keyless/offline/CI runs — they still produce a mechanical readiness score and exit 0. `--require-readiness-ai` is the sole path that hard-fails when the LLM tier is unavailable.

## Considered Options

### Option 1 — Call the judge inside `ReadinessCollector.collect(ctx)`

- **Pros**: single mutation site; the readiness block is fully assembled in one place.
- **Cons**: breaks the byte-identical determinism contract and the collector golden tests; injects a network call into the offline collect pass; conflates deterministic and non-deterministic work. Rejected.

### Option 2 — Widen `CollectionContext` with an `llm_enabled`/auth axis

- **Pros**: keeps the call inside the collector while signaling intent.
- **Cons**: the base docstring explicitly calls a new context field "an ADR-amendment-level decision … the test suite guards the field set against drift." Widening the context affects *all* collectors and weakens the determinism guarantee globally for a single collector's need. Rejected on Stay-Surgical grounds.

### Option 3 — Separate `enrich_readiness` step in `cli.py` after collect, before render (chosen)

- **Pros**: the deterministic collect pass and its golden tests are untouched; the non-deterministic half is isolated in one testable function; mirrors the existing `_maybe_refresh_coverage` pre-pipeline-step precedent (a side-effecting step bracketing the pure pipeline); `CollectionContext` stays frozen at three fields.
- **Cons**: the readiness block is mutated in two places (collector shape + cli enrichment). Mitigated by the `llm.status:"pending"` placeholder, which makes the two-phase contract explicit in the data itself; the collector owns all mechanical fields, enrichment fills only pre-declared `llm:true` slots and re-scores.

## Consequences

**Positive:**
- Collector determinism contract preserved; existing golden tests unaffected (verified design intent).
- Non-determinism is segregated and unit-testable in isolation (mock the transport).
- Offline/keyless/CI runs still succeed with a mechanical score (graceful degradation); `--require-readiness-ai` opts into strict enforcement.
- `CollectionContext` stays frozen at three fields — no cross-collector variance-surface widening.

**Negative / accepted:**
- The readiness block has a two-phase assembly (collector + enrichment). The `llm.status:"pending"→scored|llm_skipped|llm_error` lifecycle documents this; a future maintainer who moves the call into `collect()` is guarded by the determinism golden test.
- The metrics package's "pure-offline" property becomes "offline-by-default, conditionally networked" — a real, documented contract shift the user accepted in exchange for default-on scoring.

## Prior Decision

This draft revises the metrics-researcher's proposed single opt-in `--score-readiness` flag (off by default), recorded in `RESEARCH_METRICS_PIPELINE.md §(c)`. It is a sibling of `dec-214` (judge transport), not a supersession — the two together define the LLM tier. The user overrode "opt-in, off by default" with "default-on, gracefully degrading." This ADR records the reconciliation: default-on LLM + the determinism-preserving execution boundary + graceful degradation, rather than an opt-in flag gating an in-collector call.
