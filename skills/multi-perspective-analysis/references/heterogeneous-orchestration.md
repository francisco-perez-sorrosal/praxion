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
<!-- last-verified: 2026-07-29 -->

The relevant Anthropic engineering constraints are the TTL window and **breakpoint placement**, not just window duration. Design the fan-out so that proposer calls share a long, byte-identical prefix (task context, source materials, lens instructions) with the `cache_control` breakpoint placed on the *last block common to all proposers* — not on anything that varies per proposer.

**Cache prefix anatomy (breakpoint after item 3, not item 4):**
1. System prompt (always cached if identical)
2. Task framing (stable across proposers — good cache candidate)
3. Source materials (same across proposers — good cache candidate) **← breakpoint goes here**
4. Lens-specific instruction (varies per proposer — never cached; a breakpoint placed here or after it never hits, since the block above it changes on every proposer call)

Items 1–3 can constitute 80–90% of the token input. Caching them across 3–5 proposers reduces total input cost by 60–70%.

**TTL choice:** the default 5-minute tier (1.25x write premium) suffices for most fan-outs completing within a few minutes; only step up to the 1-hour tier (2x write premium) if proposers are deliberately staggered beyond ~5 minutes — the extra premium isn't free. Fire all N proposers within the chosen TTL window (5 minutes by default, up to ~55 minutes if using the 1-hour tier) to avoid a fresh write per proposer. If the task requires spreading proposers across a longer window than the chosen tier covers, accept the cache miss rather than compressing analysis time. See `claude-ecosystem`'s [platform-services.md § Prompt Caching](../../claude-ecosystem/references/platform-services.md#prompt-caching) for the current TTL/premium table and the 20-block lookback mechanics that make breakpoint placement load-bearing.

**Caveat on dynamic tool results (arXiv:2601.06007, "Don't Break the Cache," Jan 2026, cross-provider study, 500+ agent sessions):** naively caching everything, including dynamic tool-call results, can *increase* latency in some conditions. The paper found caching only the system prompt and stable source materials — excluding dynamic tool results from the cached prefix — gave the most consistent savings (41–80% across providers). Heterogeneous fan-out is exactly the long-horizon agentic pattern this paper studied; if a proposer's lens instruction pulls in per-call tool output, keep that output out of the cached prefix rather than assuming "cache everything" is strictly better.

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
