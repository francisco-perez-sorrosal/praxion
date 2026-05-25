# Context-Engineering Foundations

The shared "why" behind every `*-crafting` skill. Authoring agents, skills, rules,
commands, hooks, and MCP tools are all the same act — deciding which tokens occupy a
finite attention budget. This file is the canonical statement of that discipline;
the six crafting skills cite it instead of restating it. Back-link: [`../SKILL.md`](../SKILL.md).

## Contents

- [The north star](#the-north-star) — the one sentence everything reduces to
- [Context rot: the empirical floor](#context-rot-the-empirical-floor) — why "more context" is not free
- [The four failure modes](#the-four-failure-modes) — vocabulary for auditing what you load
- [Progressive disclosure](#progressive-disclosure-the-master-mitigation) — the master mitigation
- [The right altitude](#the-right-altitude) — specificity matched to fragility
- [Evaluation-first authoring](#evaluation-first-authoring) — build the test before the prose
- [How each crafting skill applies this](#how-each-crafting-skill-applies-this)
- [Sources](#context-engineering-sources)

## The north star

> Find **the smallest set of high-signal tokens that maximize the likelihood of the
> desired outcome.**

Context engineering is the natural successor to prompt engineering: less about *the
right words* and more about *what configuration of context* most reliably produces the
behavior you want. Every line you put in an always-loaded surface (a `SKILL.md`
description, a rule without `paths:`, a tool schema, an agent system prompt) is paid on
every relevant turn, forever. The discipline is curation, not accumulation.

## Context rot: the empirical floor
<!-- last-verified: 2026-05-25 -->

"Keep it small" is no longer a style preference — it is a measured constraint. A
controlled study across 18 frontier models (Chroma, 2025-07) showed that model
reliability **degrades as input length grows, well before the context window fills** —
a 200K-token model can show significant degradation by ~50K tokens, even on simple
retrieval tasks. The transformer's n² pairwise attention means context is a finite
resource with diminishing marginal returns: an **attention budget**, not a storage
budget.

Operational consequences:

- **Treat the window size as a ceiling, not a target.** Headroom is not an invitation to fill it.
- **Position is not a reliable lever.** The older "lost in the middle" / U-shaped
  advice (put key facts at the start and end) does **not** hold reliably — in the study,
  shuffled context sometimes beat logically ordered context. Engineer by *removing
  irrelevant tokens*, not by *reordering* them.
- **Semantic near-misses hurt.** Accuracy drops when the answer is phrased differently
  from the query, and a single topically-related distractor measurably degrades recall.
  Filter for high relevance; do not trust the model to ignore plausible-looking noise.

## The four failure modes

A checklist for auditing what any artifact loads. Ask of each block of context: is it
at risk of —

1. **Poisoning** — wrong or outdated information that pollutes downstream reasoning.
2. **Distraction** — irrelevant information that dilutes focus.
3. **Confusion** — similar-looking information the model cannot tell apart.
4. **Clash** — contradictory information that leaves the model unsure what to trust.

If a section, field, or reference cannot be tied to preventing one of these, or to
enabling a needed behavior, it has not earned its tokens.

## Progressive disclosure: the master mitigation

The single pattern that recurs across skills (metadata → body → references), MCP
(names → schemas → results), rules (`paths:`-scoped loading), and agents (summary
returns): **load lightweight identifiers first; fetch full content only when needed.**
Assemble understanding layer by layer, keeping only what working memory requires.

- **Names and descriptions are always-loaded; bodies are on-demand; bundled files are
  on-access.** Each tier costs strictly more, so push content down a tier whenever you can.
- **Pass references, not payloads.** A file path, a query, a `dec-NNN` id, a `next_cursor`
  — a pointer the consumer can resolve on demand beats inlining the whole object.
- **Sub-agents are progressive disclosure for whole tasks.** A specialized agent may burn
  tens of thousands of tokens internally and return a 1–2k-token distilled summary. The
  orchestrator keeps the conclusion, not the transcript.

## The right altitude

Match an artifact's specificity to the fragility and variability of the work — the
Goldilocks zone between two failure modes:

- **Too specific** → brittle, hardcoded logic that shatters on the first unforeseen case.
- **Too vague** → "falsely assumes shared context" and gives the model nothing to grip.
- **Right altitude** → specific enough to guide behavior, flexible enough to be a strong
  heuristic.

This maps to **degrees of freedom**: high-freedom guidance (prose heuristics) when many
approaches are valid; low-freedom guidance (an exact script, "run this, do not modify
the command") when the path is fragile and consistency is critical. A narrow bridge gets
guardrails; an open field gets a direction.

## Evaluation-first authoring

Anthropic's guidance for both Skills and tools now leads with evaluation, not prose:

1. **Establish the gap.** Run the model *without* the artifact; see where it fails.
2. **Write ≥3 realistic scenarios** grounded in real use (not toy sandboxes); include
   **negative** cases that must *not* trigger the artifact — these define the boundary and
   are what stop over-firing.
3. **Baseline, then write the minimal instructions** that close the gap. Iterate.
4. **Use the two-Claude loop.** One instance helps author (Claude A); a fresh instance
   tests on real tasks (Claude B). Watch where Claude B explores unexpectedly, misses a
   connection, or ignores a section — bring that back to Claude A.
5. **Test on a held-out set** and across target model tiers (what an Opus handles, a
   Haiku may need spelled out). "The larger the effect size, the smaller the sample you
   need" — start with 3–5 cases.

The artifact is "done" when it passes real usage, not when it reads well.

## How each crafting skill applies this

| Crafting skill | The same principle, applied |
|---|---|
| `skill-crafting` | Three-tier progressive disclosure; lean `SKILL.md`; description as the only always-loaded, high-signal trigger |
| `command-crafting` | A command/skill description costs listing budget every session; `disable-model-invocation` keeps side-effect actions out of the model's attention |
| `agent-crafting` | One job per agent; clean context window; **pointer-not-payload** summary returns; tool allowlist = fewer distractors |
| `rule-crafting` | Always-loaded budget discipline; `paths:`-scoped just-in-time loading; promote non-negotiables to hooks rather than bloating advisory context |
| `hook-crafting` | The narrowest event + matcher; `additionalContext` is injected tokens — keep it minimal and high-signal |
| `mcp-crafting` | Fat workflow tools over primitive wrappers; token-aware responses (`concise`/`detailed`); natural-language identifiers over UUIDs; lazy tool loading |

## Context-Engineering Sources
<!-- last-verified: 2026-05-25 -->

Primary (Anthropic-official):

- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — 2025-09-29 — attention budget, right altitude, just-in-time retrieval, compaction, sub-agent summary returns, "smallest set of high-signal tokens."
- [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — 2025-09-11 — tool design, response shaping, error grammar, evaluation-driven iteration.
- [Agent Skills best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — progressive disclosure, degrees of freedom, evaluation-first, the two-Claude loop.

Empirical / practitioner (corroborating, named authors):

- [Context Rot: How Increasing Input Tokens Impacts LLM Performance](https://www.trychroma.com/research/context-rot) — Hong, Troynikov, Huber (Chroma), 2025-07-14 — the 18-model controlled study; the citable basis for degradation-below-the-limit and the deprecation of positional engineering.
- The four failure-mode vocabulary (poisoning / distraction / confusion / clash) is widely used in 2025–2026 context-engineering write-ups synthesizing the above.
