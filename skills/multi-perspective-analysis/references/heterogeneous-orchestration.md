# Heterogeneous Orchestration

Reference for cost-efficient model assignment in multi-lens fan-out. Back to [SKILL.md](../SKILL.md).

## Purpose

When a fan-out is warranted (honest-uncertainty gate fires; see `SKILL.md § Activation Gate`), lens agents need not all run on the same model tier. Assigning proposer roles to smaller models and aggregator roles to larger models preserves ensemble quality while reducing cost by 60–80%.

## Haiku-Proposer / Opus-Aggregator Recipe

| Role | Model tier | Responsibility |
|---|---|---|
| **Proposer** (lens agent) | Haiku (or equivalent small model) | Runs one lens in isolation; produces a structured fragment; no cross-agent reads |
| **Aggregator** | Opus (or equivalent frontier model) | Reads all proposer fragments; identifies agreements, contradictions, blind spots; writes the consolidated artifact |

**Why this split works.** Proposers apply a single, well-defined lens (security, performance, simplicity, testability) to structured input. This is a low-diversity, high-precision subtask that smaller models handle reliably. Aggregation requires cross-fragment reasoning, contradiction detection, and nuanced judgment — the task where frontier models add measurable value. Sending all N proposers to the frontier model is waste without quality benefit (Haiku proposers hit equivalent per-lens precision on structured lenses at ~0.05× the token cost).

## Prompt-Caching Guidance

The ~1-hour window for Anthropic prompt caching is the relevant engineering constraint. Design the fan-out so that proposer calls share a long-prefix (task context, source materials, lens instructions) that can be cached across the N proposer calls within a single session.

Practical implication: fire all N proposers within 50–55 minutes of the first proposer call to stay within the cache window. If the task requires spreading proposers across a longer window (rare), accept the cache miss rather than compressing analysis time.

**Cache prefix anatomy:**
1. System prompt (always cached if identical)
2. Task framing (stable across proposers — good cache candidate)
3. Source materials (same across proposers — good cache candidate)
4. Lens-specific instruction (varies per proposer — not cached)

Items 1–3 can constitute 80–90% of the token input. Caching them across 3–5 proposers reduces total input cost by 60–70%.

## Cost Model References

Three empirical papers establish the cost/quality envelope for this recipe:

| Study | Finding | Relevance |
|---|---|---|
| **MoA (Mixture of Agents)** — Wang et al. 2024 | Ensemble of small proposers + single aggregator matches or exceeds frontier-only at lower cost | Validates the heterogeneous split |
| **PoLL (Panel of LLM Evaluators)** — Verga et al. 2024 | Heterogeneous panel (mix of model tiers) outperforms homogeneous panel at same or lower cost | Validates model-tier diversity as beneficial |
| **MasRouter** — Liu et al. 2025 | Dynamic routing based on query complexity reduces cost 40–60% vs. always-frontier | Validates proposer→small when the subtask complexity is bounded |

These papers justify the recipe but are not required reading for normal use. Cite them when a stakeholder questions why proposers don't run on the frontier model.

## Activation Constraint

Heterogeneous orchestration is only invoked when the fan-out itself is warranted (honest-uncertainty gate, `SKILL.md § Activation Gate`). It is not a general recommendation to always use small models for subtasks. The model assignment advice in this file applies only within a warranted multi-lens fan-out.

## References

- [`../SKILL.md`](../SKILL.md) — parent skill; activation gate; satellite table.
- [`lens-independence.md`](lens-independence.md) — isolation discipline that governs how proposers are separated.
- [`disconfirmation-tiers.md`](disconfirmation-tiers.md) — Tier-B cross-model challenge uses a different-model agent as external oracle (distinct from the proposer/aggregator recipe here).
