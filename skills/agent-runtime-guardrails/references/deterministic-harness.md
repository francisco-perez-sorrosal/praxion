# The Deterministic Harness

The harness pattern for long-running and autonomous agents. Reference material for the [Agent Runtime Guardrails](../SKILL.md) skill.

A **deterministic harness** is the runtime scaffold around an agent loop that makes a non-deterministic model behave like a system with deterministic *bounds*. The model proposes the next action; the harness validates, authorizes, executes, and logs it. This file describes the harness *shape and techniques* — for how to wire any of it into a specific SDK's agent loop, see the `agentic-sdks` skill (this file never re-documents SDK APIs).

## The action loop

Around every model-proposed action:

```
propose (model)  →  validate  →  authorize  →  execute  →  log  →  observe
                      │             │            │          │
                   schema /      permission   sandboxed   trajectory
                   input rail    + budget +    effect      span
                                 approval gate
```

The four checks are the four parts of the runtime layer (see the SKILL). The loop is deterministic even though the proposal is not — every path through it is one the harness author chose.

## Techniques for long-running agents

Anthropic's harness guidance for agents that run for many steps, distilled to the discipline (not tied to any SDK):

- **Initializer phase.** Before the agent loop proper, establish a known baseline: a setup step (`init.sh`-style), a progress/decision log the agent appends to, and a **git baseline commit** so every later checkpoint has a clean origin.
- **One feature/task at a time.** Bound the agent's working scope to a single unit. Breadth-first sprawl is where long-running agents lose the thread; the harness enforces the narrow front.
- **Mandatory self-verification before "done."** An agent may not mark a unit complete without running its own verification (tests, schema checks, the acceptance criteria). "I think it's done" is not a completion signal; "verification passed" is. This is the single highest-leverage harness rule.
- **Checkpoint / recovery via git.** Commit at each verified unit so a bad step rolls back to the last good state instead of corrupting the run. The harness owns the checkpoint cadence, not the model.
- **Pre-session orientation.** Re-establish context cheaply at the start of each working session (read the progress log, the plan, the current state) rather than re-deriving it — saves budget and prevents drift.

## Harness-side budget enforcement

Budgets are a first-class part of the harness, not an afterthought. This is the **runtime** side of budget enforcement; the **eval-CI** side (thresholds as PR gates) lives in the `agent-evals` skill. Both mirror the same proven discipline in `rules/ml/gpu-budget-conventions.md`:

> **Declare a budget → the harness enforces it → exhaustion is a NORMAL, checkpoint-preserving termination (`status: budget_exhausted`), not a failure.**

Apply it to agentic cost / latency / turn budgets:

- **Declare** per-run cost, latency, and turn budgets. Open-ended runs are prohibited — an agent with no budget is an agent with no stop condition.
- **Inject remaining budget into context** so the agent can *tier its behavior* — do the cheap-and-safe thing when budget is low, the thorough thing when it is ample.
- **Halt cleanly at exhaustion.** Reaching a budget limit ends the run at the last checkpoint with state preserved. It is an expected outcome, reported as termination, never as an error or a quality failure — exactly as the gpu-budget discipline treats `budget_exhausted` for training runs.

Treating exhaustion as normal (not as failure) is what keeps budgets *usable* as a control: if hitting the budget were a failure, authors would over-provision to avoid red builds, defeating the purpose.

## Why determinism around non-determinism works

The model's output distribution is unbounded; the harness's *response* to that output is finite and authored. By constraining what the system does with any given proposal — reject off-schema, refuse out-of-scope tool calls, halt at budget, require approval for high-impact actions — the harness collapses an unbounded behavior space into a bounded one without making the model itself deterministic. That is the whole reliability mechanism: bound the effects, not the thoughts.
