# Agent Runtime Guardrails

The un-bypassable runtime-enforcement layer for agentic apps, as a design discipline and harness checklist. *The model proposes; the harness disposes.*

## When to Use

- Designing, building, or verifying the guardrail layer of an agentic app — input validation, structured-output enforcement, tool-call gating, budget/permission enforcement.
- Designing a deterministic harness for a long-running or autonomous agent (checkpointing, self-verification, budgets).
- Giving the **Pre-mortem gate** teeth: "assume this agent did something it shouldn't — why?" is the guardrail-gap question.

Not for: SDK API mechanics (that is `agentic-sdks`), classifying a failure after the fact (`agent-failure-taxonomy`), or author-side prompt hardening (`llm-prompt-engineering`).

## Activation

Description-match on prevention/enforcement language — "enforce model I/O," "gate tool calls," "guardrail layer," "deterministic harness," "structured-output enforcement," "budget enforcement." Partitioned from `agent-failure-taxonomy` (which triggers on classify/diagnose) by verb.

## Skill Contents

- `SKILL.md` — the core principle (enforce, don't hope), the four-part runtime layer with per-part checklists, pipeline placement, and the boundaries vs `agentic-sdks` / `llm-prompt-engineering` / `agent-failure-taxonomy`.
- `references/deterministic-harness.md` — the harness action loop, long-running-agent techniques, and harness-side budget enforcement (mirroring the gpu-budget discipline).
- `references/guardrail-tooling.md` — tool *selection* (Guardrails AI / NeMo / SDK-native), single-source-per-vendor, never benchmarks.

## Related Skills

- `agentic-sdks` — how to wire a guardrail/approval primitive into a specific SDK's agent loop (the mechanics this skill defers to).
- `agent-failure-taxonomy` — the failures this layer prevents (classification; its mitigation column points here).
- `agent-evals` — the eval-CI side of budget gates (this skill owns the harness-runtime side).
- `observability` — the agent-span trajectory the "log" step of the harness emits.
