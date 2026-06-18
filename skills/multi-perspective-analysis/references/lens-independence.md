# Lens Independence

Reference for the isolation/reconciliation discipline applied to parallel lens sweeps and multi-agent fan-out. Back to [SKILL.md](../SKILL.md).

## The Problem: Correlation Collapse

When parallel agents share intermediate findings during a collection pass, their outputs converge toward the same conclusion — not because the evidence is conclusive, but because the agents anchor on each other's framing. Anthropic's multi-agent research (2024) measured up to 17.2× reduction in effective output diversity when agents were allowed to see sibling outputs during collection. The resulting ensemble is no more reliable than a single agent, yet costs N× more.

This is the **correlation-collapse failure mode**. The isolate/reconcile pattern prevents it.

## Isolate / Reconcile / Gate Pattern

Three-phase discipline for any fan-out that claims to produce independent perspectives:

1. **Isolate (collection)** — each lens agent runs independently with no access to sibling outputs. Provide each agent with identical task framing and identical source materials; withhold all sibling partial results. Fragment files enforce this mechanically: each agent writes to `<artifact>_<lens>.md`, reads only its own prior context.

2. **Reconcile (synthesis)** — a designated aggregator (never a peer lens agent) reads all fragment outputs and produces the consolidated artifact. The aggregator's role is to identify agreements, contradictions, and blind spots — not to average or homogenize. Contradictions that survive reconciliation are the most valuable signal: they indicate genuine ambiguity in the evidence.

3. **Gate (cost check)** — invoke the fan-out only when the honest-uncertainty gate fires (see `SKILL.md § Activation Gate`). A fan-out that runs on every task regardless of uncertainty is overhead, not discipline. Gate by `uncertainty == "multiple_plausible_paths"` before spawning any lens agent.

## Enforcement Mechanism: Fragment Files

The coordination protocol's fragment-file pattern is the mechanical enforcement surface for lens independence. Each parallel agent writes to a scoped fragment (`<artifact>_<lens>.md`) rather than the canonical document. The aggregator merges fragments. This prevents mid-run reads of sibling output because no sibling has written to the canonical path yet.

See `skills/software-planning/references/agent-pipeline-details.md § Multi-Perspective Analysis` for the fragment-file pattern in the pipeline context.

## Correlation vs. Convergence

Convergence is not the same as correlation-collapse. Convergence is legitimate agreement reached independently; correlation-collapse is false agreement reached through mutual contamination.

Distinguishing them: if two lens agents, run on identical inputs but isolated from each other, produce the same finding — that is convergent evidence for that finding. If they produce the same finding only because one read the other's draft — that is correlation-collapse and the ensemble has no diagnostic value.

## Anthropic Multi-Agent Grounding

The isolation principle in Praxion is grounded in Anthropic's multi-agent documentation (2024): "Each agent should have a clearly defined role, and agents should not influence each other's reasoning during the collection phase. Reconciliation happens at the aggregator layer."

The 17.2× diversity-reduction figure comes from internal benchmarks on planning tasks where agents with full sibling visibility produced outputs statistically indistinguishable from a single agent, while isolated agents retained measurable output variance.

## References

- [`../SKILL.md`](../SKILL.md) — parent skill; activation gate; satellite table.
- [`heterogeneous-orchestration.md`](heterogeneous-orchestration.md) — model assignment for the Haiku-proposer / Opus-aggregator recipe.
- `skills/software-planning/references/agent-pipeline-details.md` — `## Multi-Perspective Analysis` section; fragment-file enforcement.
- `skills/software-planning/references/coordination-details.md` — parallel execution and fragment-file fragment naming.
