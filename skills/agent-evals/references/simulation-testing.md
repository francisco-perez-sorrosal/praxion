# Simulation Testing — User-Simulator Pattern

Multi-turn agent evaluation via a simulated user. Reference material for the [Agent Evals](../SKILL.md) skill.

> **Scope: multi-turn / conversational agents only.** Single-shot agents (one input → one output) get nothing from this — their failures surface in the offline suite ([eval-design-patterns.md](eval-design-patterns.md)). The payoff is concentrated in agents that hold a *conversation*, where failures emerge *across* turns: dropped context, contradiction, goal drift, looping. If the agent under test is not multi-turn, skip this reference.

## Why multi-turn needs simulation

A fixed-trajectory eval scripts the exact turns in advance, so it can only test conversations the author imagined. Real multi-turn failures appear when the *user* says something unanticipated on turn 3 given what the agent did on turn 2. You cannot enumerate those paths by hand — you need a **counterparty that reacts to the agent**, which is what a user-simulator provides.

## The user-simulator pattern

Three roles in a loop:

1. **Simulator (plays the user).** An LLM given a **goal** (what this user wants), a **persona** (how they communicate — terse, confused, adversarial), and **constraints** (what they know / won't reveal). It converses turn-by-turn with the agent under test, reacting to each agent response rather than following a script.
2. **Agent under test.** The real agent, in its real harness, responding to the simulated user.
3. **Judge (evaluates the conversation).** A judge-agent scores the *whole transcript* against the goal: was the goal met, and how? It logs failure shapes — hallucination, dropped context, contradiction across turns, failure to terminate.

The simulator and judge are themselves LLMs, so they need the same rigor as any grader: **calibrate the judge-agent** against human-labeled transcripts (see [eval-rigor.md](eval-rigor.md)) before trusting its scores, and run multiple trials (the conversation is non-deterministic on both sides).

## The target metric: 1:1 sim-to-prod failure mapping

The goal of a simulation suite is not a high simulated pass rate — it is **predictiveness**: the simulated failure rate should map ~1:1 onto the production failure rate. A simulation suite that never fails while production does is mis-calibrated (too-easy personas, too-lenient judge); one that fails constantly while production is fine is over-adversarial. Tune personas and judge until the two rates track. This is the multi-turn analogue of the offline↔production grounding loop in [online-evals.md](online-evals.md), and simulated failures are high-value feed for the living dataset.

## Two simulation modes

| Mode | The "user" is… | Fits |
|---|---|---|
| **Scripted** | A fixed sequence of user turns (no LLM reaction) | Regression on a *known* conversation that must keep working |
| **Judge-agent (generative)** | An LLM reacting turn-by-turn to the agent | Capability discovery — surfacing *unscripted* multi-turn failures |

Scripted simulations are cheap and deterministic-ish; use them as regression guards. Generative simulations explore; use them to *find* new failure shapes, then freeze the ones that matter into scripted regressions (the promotion path of [eval-rigor.md](eval-rigor.md)).

## Tooling

- **[langwatch/scenario](https://langwatch.ai/scenario/)** — open-source simulation/scenario testing; multi-language (Python / TS / Go); integrations for LangGraph, CrewAI, Pydantic AI, OpenAI, Google ADK; supports both scripted and judge-agent simulations plus red-teaming. **[VERIFIED — maintainer docs + corroborating coverage]**
- **SAGE** (arXiv 2510.11997) — a knowledge-grounded top-down/bottom-up user simulator for scalable multi-turn evaluation. **[SINGLE-SOURCE — preprint; research-only, no production-adoption claim]**. Useful for the *idea* (structured simulator grounding), not as an adoptable dependency.

**Reference the *pattern*, not just the tool.** `langwatch/scenario` is pre-1.0-ish OSS and may churn; the user-simulator pattern (goal+persona+constraints simulator, agent under test, calibrated judge, 1:1 mapping target) is stable and tool-agnostic. Build against the pattern so a tool change is a swap, not a rewrite.

## When to use / when to skip

- **Use** when the agent is conversational/multi-turn and its failures are turn-dependent (support agents, assistants, negotiators, anything stateful across turns).
- **Skip** for single-shot agents, or when fixed-trajectory trajectory matching ([eval-design-patterns.md](eval-design-patterns.md)) already covers the behavior — adding a simulator there is cost with no new signal.

## Cross-references

- [eval-rigor.md](eval-rigor.md) — calibrate the judge-agent; promote found failures into the frozen regression suite.
- [online-evals.md](online-evals.md) — simulated failures feed the dataset; the 1:1 mapping target mirrors the production-grounding loop.
- [eval-design-patterns.md](eval-design-patterns.md) — § Conversational Agents (the one-line "multi-turn simulation" pointer this file develops).

## Sources

- [LangWatch — Scenario](https://langwatch.ai/scenario/) — OSS user-simulator framework. **[VERIFIED]**
- [Confident AI — Multi-Turn LLM Evaluation in 2026](https://www.confident-ai.com/blog/multi-turn-llm-evaluation-in-2026) — user-simulator multi-turn methodology. **[VERIFIED]**
- [SAGE (arXiv 2510.11997)](https://arxiv.org/pdf/2510.11997) — knowledge-grounded user simulator. **[SINGLE-SOURCE — research-only]**
