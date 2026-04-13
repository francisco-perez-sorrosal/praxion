---
id: dec-040
title: Eval framework is out-of-band only (/eval command + CI, never hook-driven)
status: accepted
category: architectural
date: 2026-04-13
summary: Eval framework runs only via user-invoked /eval command or opt-in CI job; never from a hook, never during a pipeline
tags: [eval, quality, hooks, latency, architecture]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - eval/
  - commands/eval.md
  - .github/workflows/test.yml
  - hooks/hooks.json
affected_reqs:
  - REQ-EV-01
  - REQ-EV-02
  - REQ-EV-04
  - REQ-EV-05
---

## Context

Phase 3.1 of the ROADMAP tasks the systems-architect with overhauling the eval framework (Inspect AI-style behavioral + regression + cost + decision-quality tiers). The user added an explicit constraint:

> "Extreme care that everything becomes smoother and we don't impact latencies nor block anything."

Evals can be expensive — Phoenix client imports take 500 ms-2 s (pandas + arize-phoenix), LLM-as-judge calls are seconds-to-minutes and cost API credits, and trace-based regression tests read potentially thousands of spans. If any of these runs synchronously inside an agent pipeline, they would degrade pipeline latency, add failure modes to production agent work, and violate the stated constraint.

Three viable invocation models exist:
1. **Hook-driven** — PostToolUse or SubagentStop fires evals after pipeline events.
2. **Background worker** — a long-running daemon watches `.ai-work/` and evaluates completed task-slug directories asynchronously.
3. **Out-of-band only** — user invokes `/eval [tier]` explicitly; CI runs on schedule or on workflow_dispatch.

## Decision

Use **Option 3**. The eval framework is strictly out-of-band:

- Invocation is via the new `/eval` slash command (user-initiated) OR a CI job on `main` (opt-in, workflow_dispatch or schedule).
- No eval code is invoked from any Claude Code lifecycle hook (PreToolUse, PostToolUse, SubagentStart, SubagentStop, Stop, SessionStart, PreCompact).
- Evals read completed artifacts (`.ai-work/<slug>/`, `.ai-state/`, Phoenix traces) — they never mutate live pipeline state, never start agents, never run during a pipeline.
- The architectural constraint is binding on all future eval work: adding a new eval tier in Phase 4+ must preserve the out-of-band invocation pattern.

## Considered Options

### Option 1 — Hook-driven evals

Wire evals into PostToolUse or SubagentStop so quality is measured continuously without user action.

- Pros: Continuous feedback; no chance the user forgets to evaluate.
- Cons: Every hook firing pays import cost (Phoenix + pandas, 500 ms-2 s); LLM-judge calls add unbounded latency; a failing eval could block an agent's progress; violates the user's explicit latency constraint; creates a dependency chain where eval bugs crash pipelines.

### Option 2 — Background worker

A daemon watches `.ai-work/` and evaluates finished task-slugs asynchronously.

- Pros: Continuous evaluation without blocking pipelines.
- Cons: Adds a new always-running process to the Praxion install surface; requires process management, log rotation, failure recovery; complicates the install story; not justified by Phase 3's single-host, single-developer use case.

### Option 3 — Out-of-band only (chosen)

Evals run only when the user invokes `/eval` or when CI does.

- Pros: Zero latency impact on pipelines; eval failures never break agent work; clean separation of concerns (eval reads, pipeline writes); simple install footprint.
- Cons: Drift can accumulate between runs if the user forgets. Mitigation: add a scheduled CI run to catch drift; include a `/eval` reminder in the verifier's output as a future enhancement.

## Consequences

**Positive**:
- Pipeline latency is unchanged.
- Eval code has zero failure mode reaching agent work.
- `eval/` directory can evolve freely without hook-contract concerns.
- Claude-as-judge / LLM-judge additions (future) inherit the same isolation automatically.
- Scheduled CI runs cover the drift concern without user action.

**Negative**:
- Requires explicit user action (or CI schedule) to evaluate — drift risk exists.
- Developers must learn the `/eval` command.
- A "demo" scenario where evals always run needs an explicit user or CI trigger.

**Binding constraint for future work**: Any Phase 4+ eval addition (new tier, new judge, cost analysis) must respect this invocation pattern. Adding hook-triggered evals is a supersession requiring a new ADR.
