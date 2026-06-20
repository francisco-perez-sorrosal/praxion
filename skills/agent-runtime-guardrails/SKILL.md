---
name: agent-runtime-guardrails
description: >
  The un-bypassable runtime-enforcement layer for agentic apps: input validation,
  structured-output enforcement, tool-call gating, and budget/permission enforcement, via
  the deterministic-harness pattern. Triggers: design, build, or verify guardrails that
  enforce model I/O and gate tool calls regardless of model output. Prevention — not SDK
  mechanics (agentic-sdks), not failure classification (agent-failure-taxonomy).
allowed-tools: [Read, Glob, Grep]
compatibility: Claude Code
---

# Agent Runtime Guardrails

**The model proposes; the harness disposes.** An agent's model output is a *proposal*, not a command. Between the proposal and any real effect sits a **deterministic runtime layer the model cannot bypass** — it validates, authorizes, executes, and logs every action. Reliability comes from *enforcement, not hope*: "the model usually behaves" is not a guarantee; an un-bypassable layer is.

This skill is the **process discipline + design checklist** for that layer. It cross-references the `agentic-sdks` skill for *how to wire* a guardrail primitive in a specific SDK (OpenAI Agents SDK, Claude Agent SDK) and **never re-documents SDK APIs** — the discipline (what to validate, what to gate, the harness shape) lives here; the SDK mechanics live there.

## The core principle: enforce, don't hope

Treat every model-proposed action as untrusted until the harness has checked it. The harness — not the model — owns schemas, permissions, budgets, and safety. The model's job is to propose; the harness's job is to refuse anything outside the envelope. This is what turns a non-deterministic model into a system with deterministic *bounds*.

## The four-part runtime layer

A complete guardrail layer has four parts. Design each as present-or-consciously-omitted; a silent gap is the failure surface (the `agent-failure-taxonomy` rubric names what slips through each gap).

### 1. Input validation (input rails)

Validate and sanitize everything entering the model's instruction context — **both** the user input **and** tool/external output (web pages, documents, other agents' output). External/tool output is the higher-risk channel: it is the vector for cross-domain prompt injection.

- [ ] User input validated against expected shape before it reaches the model.
- [ ] Tool/external output treated as untrusted and validated before it re-enters the instruction context.
- [ ] Instruction/data separation enforced at runtime (distinct from *author-side* delimiter hardening — that is the `llm-prompt-engineering` skill; this is runtime validation of what actually arrives).

### 2. Structured-output enforcement

Constrain model output to a schema and reject or repair off-schema output *before* anything acts on it. Never parse free text and hope it is well-formed.

- [ ] Output bound to a schema (e.g. a Pydantic / JSON-schema model).
- [ ] Off-schema output is rejected or repaired, not best-effort-parsed.
- [ ] The schema is enforced by the harness, not merely requested in the prompt.

### 3. Tool-call gating

Between a proposed tool call and its execution, the harness authorizes, validates, gates, and logs.

- [ ] **Authorize** — the call is within the tool's least-privilege scope for this agent.
- [ ] **Validate args** — arguments are checked before execution.
- [ ] **Gate high-impact calls** — consequential/irreversible actions require an explicit approval *event* the harness checks for (an un-bypassable human-in-the-loop primitive), not the model's say-so.
- [ ] **Log** — every call and its outcome is recorded (the trajectory; see the `observability` skill's agent-span model).

### 4. Budget & permission enforcement

Declare cost/latency/turn budgets and a permission boundary; the harness enforces both. This **reuses the proven `gpu-budget-conventions.md` discipline** (`rules/ml/gpu-budget-conventions.md`): *declare a budget → the harness/verifier enforces it → budget exhaustion is a NORMAL, checkpoint-preserving termination (`status: budget_exhausted`), not a failure.* Apply the same discipline to agentic cost/latency/turn budgets.

- [ ] Per-run cost/latency/turn budgets declared (open-ended runs are prohibited).
- [ ] Remaining budget injected into context so the agent can tier its behavior.
- [ ] Exhaustion halts cleanly and preserves state — treated as expected termination, not an error.
- [ ] The permission boundary is immutable at runtime — the agent cannot grant itself new scope (guards against autonomy escalation).

The *eval-CI* side of budgets (cost/latency/turn thresholds as PR gates) lives in the `agent-evals` skill's budget-gate section; this part is the *harness-runtime* side. Both mirror the same gpu-budget discipline.

## The deterministic-harness pattern

The four parts compose into a harness that wraps the agent loop: **validate → authorize → execute → log** around every model-proposed action, plus the long-running-agent techniques (initializer phase, self-verification-before-complete, git checkpoint/recovery, one-feature-at-a-time). See [references/deterministic-harness.md](references/deterministic-harness.md).

## Where this sits in the pipeline

- **`systems-architect`** — produces a *runtime-guardrails section* in the plan (`.ai-work/<task-slug>/SYSTEMS_PLAN.md`): which of the four parts the agent being built needs, and which are consciously N/A.
- **`implementer`** — builds the layer (wiring per `agentic-sdks`).
- **`verifier`** — confirms the un-bypassable layer *exists*, rather than accepting "the model usually behaves."
- **Pre-mortem gate** (planner→implementer): *"assume this agent shipped and did something it shouldn't — why?"* is exactly the guardrail-gap question. This skill gives that checkpoint teeth.

## Tooling selection

Guardrails AI, NVIDIA NeMo Guardrails, and the OpenAI Agents SDK's native guardrails/approvals primitive are the main options. Treat the choice as a *selection trade-off*, single-source-per-vendor, **never as a benchmark**. See [references/guardrail-tooling.md](references/guardrail-tooling.md).

## Boundaries

- **vs `agentic-sdks`** — that skill owns the agent-loop and SDK guardrail *mechanics* (how to register a guardrail/approval in a given SDK). This skill owns the *discipline* (what to validate/gate, the harness checklist). **Cross-reference, never re-document SDK APIs.**
- **vs `llm-prompt-engineering`** — that owns *author-side* injection hardening (how you construct the prompt — delimiters, instruction-after-data). This owns *runtime* I/O validation and tool-call gating (what the harness does with what actually arrives).
- **vs `agent-failure-taxonomy`** — prevention (build the layer) vs classification (name a failure once observed). The taxonomy's mitigation column points here; this skill is where those mitigations are constructed.

## Sources

- [Anthropic — Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — the deterministic harness (validate/authorize/execute/log), self-verification-before-complete, checkpoint/recovery, budgets-as-gates. **[VERIFIED — Anthropic primary]**
- [OpenAI — Guardrails and human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals) — SDK-native guardrails/approvals primitive (mechanics in `agentic-sdks`). **[VERIFIED — OpenAI primary]**
