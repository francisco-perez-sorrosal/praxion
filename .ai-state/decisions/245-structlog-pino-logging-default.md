---
id: dec-245
title: Sharpen the observability logging default to structlog (Python) and pino (TypeScript)
status: accepted
category: architectural
date: 2026-06-20
summary: Adopt structlog as the #1 Python service-logging default (loguru relegated to CLI/prototyping) and pino as the #1 TypeScript default (winston migration-only), superseding the prior parity framing.
tags: [observability, logging, structlog, pino, defaults]
made_by: agent
agent_type: systems-architect
branch: feat-l3-readiness-config
pipeline_tier: full
affected_files:
  - skills/observability/SKILL.md
  - pyproject.toml
  - scripts/praxion_logging.py
dissent: loguru's lower setup friction and the user's prior positive experience make it a defensible Python default for a small-team CLI-heavy codebase; structlog's medium setup cost is a real tax.
---

## Context

The `observability` skill's Service Observability Baseline currently frames the Python logging choice as "structlog (or loguru)" parity and gives no TypeScript logging-library recommendation at all (`typescript-observability.md` has an explicit gap). A dedicated research pass (RESEARCH_FINDINGS.md) evaluated structlog/loguru/stdlib (Python) and pino/winston/tslog (TS) across structured output, performance, ecosystem maturity, OTel integration, and DX. Praxion also needs to declare a logging dependency to pass its own `c.observability.logging_config` L3 check, and the `observability` skill is the canonical home for the per-stack default.

## Decision

Adopt **structlog** as the #1 Python service-logging default; relegate **loguru** to CLI/prototyping only (it is not library-safe and is feature-frozen at 0.7.3 with no release in >12 months); keep stdlib `logging` mandatory for library code. Adopt **pino** as the #1 TypeScript/Node service default; restrict **winston** to migration-only (existing codebase with measured no-perf-issue, or a needed winston transport); avoid **tslog** for OTel-integrated services (no instrumentation package). Update the `observability` skill's make-it-pass table accordingly with OTel-integration notes (structlog stdlib-bridge zero-per-call; pino `@opentelemetry/instrumentation-pino` + `pino-opentelemetry-transport`). Praxion's own root `pyproject.toml` declares `structlog>=26.1.0` with one canonical config module (`scripts/praxion_logging.py`).

## Considered Options

### Option 1 — structlog (Python) / pino (TS) as sharpened defaults (chosen)
- Pros: structlog is fastest in the published benchmark, composable processor chain, cleanest OTel path via stdlib bridge, async-safe (contextvars), library-safe; pino is fastest by architecture (async stdout + workers), two clean OTel paths, Nearform-backed and actively maintained.
- Cons: structlog has medium setup complexity (explicit `configure()`); pino's object-first API is a minor DX adjustment; pino's perf advantage rests on single-source (Pino-published) benchmarks.

### Option 2 — Keep structlog/loguru parity (status quo)
- Pros: no skill change; loguru's zero-config DX suits CLIs.
- Cons: leaves the TS gap unfilled; treats a feature-frozen, non-library-safe library as a co-equal service default; gives future services no clear guidance.

## Consequences

- Positive: every future managed service gets a single, justified per-stack default with an OTel path; the TS gap closes; Praxion passes `logging_config`; loguru's maintenance risk is documented rather than silently inherited.
- Negative: structlog's setup cost lands on small Python services that might have shipped faster with loguru (mitigated: loguru stays the explicit CLI/prototyping recommendation); the pino perf claim is not independently benchmarked (mitigated: architectural mechanism is Tier-1 documented; teams with strict perf needs benchmark locally).

## Disconfirmation

- **Falsifier:** if an independent benchmark shows structlog/pino do NOT outperform their runner-ups in realistic workloads, the performance leg of the recommendation weakens (the OTel-integration and maintenance legs still hold).
- **Steelmanned runner-up:** for a CLI-heavy, small-team Python codebase, loguru's zero-config DX and the user's own positive experience are a real productivity win; structlog's explicit `configure()` is a tax paid on every service. loguru loses as a *service* default on three durable axes — not library-safe, feature-frozen (0.7.3, >12 months no release), and an extra OTel indirection layer — but it remains the right CLI/prototyping call, which this decision preserves.
- **Reversal trigger:** revisit if loguru resumes active releases and adds a native OTel path and library-safe mode; or if pino's maintenance/perf posture regresses; or if structlog ships a breaking 27.x that complicates the canonical module.
