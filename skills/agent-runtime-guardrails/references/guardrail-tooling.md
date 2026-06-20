# Guardrail Tooling — Selection

How to *choose* a guardrail tool. Reference material for the [Agent Runtime Guardrails](../SKILL.md) skill.

This file is **selection guidance, not a benchmark**. Vendor feature-lists are single-source-per-vendor — each vendor describes its own tool. Use them to understand what *category* of capability exists and which tool fits a constraint, **never** as a performance ranking or a "best guardrail" claim. There is no neutral, reproducible benchmark across these tools; treat any "leaderboard" framing as marketing.

## The three main options

| Tool | Shape | Fits when… |
|---|---|---|
| **Guardrails AI** | Open-source declarative validators (Pydantic / RAIL): PII, JSON-schema, structured-output, regex, competitor checks; a Hub of reusable validators | You want composable, declarative output/structure validation in Python and a library of pre-built validators. |
| **NVIDIA NeMo Guardrails** | Colang-programmable rails (input / retrieval / dialog / execution / output / jailbreak) running as a proxy | You want programmable dialog/safety rails as a layer in front of the model, configured rather than hand-coded. |
| **OpenAI Agents SDK — native guardrails / approvals** | First-class `guardrails` + human-approval primitive inside the agent loop | You are already building on the OpenAI Agents SDK and want guardrails/approvals co-located with the loop. |

(Source tags from the research scan: the *category* is **VERIFIED** across multiple comparisons; each tool's specific feature-list is **SINGLE-SOURCE** — the vendor's own docs. Do not quote feature-lists as comparative benchmarks.)

## Selection heuristics

- **Match the tool to the layer you need.** Guardrails AI is strongest for the *structured-output enforcement* and *input-validation* parts; NeMo for *dialog/safety rails*; the SDK-native primitive for *tool-call gating / approvals* when you are on that SDK. Most real systems compose more than one.
- **Prefer the primitive already in your stack.** If you build on an SDK with a native guardrails/approvals primitive, reach for it before adding a third-party proxy — fewer moving parts, the guardrail lives next to the loop. The wiring for SDK-native primitives is in the `agentic-sdks` skill, not here.
- **Declarative over hand-rolled for structure/PII.** Schema, PII, and regex validation are solved problems — use a validator library rather than bespoke checks that rot.
- **The tool is not the discipline.** Adopting any tool does not by itself give you the four-part layer (SKILL). A tool enforces *what you configure*; the discipline is deciding *what to enforce*. A guardrail library with no tool-call gating configured guards nothing at the tool boundary.

## What this file does NOT cover

- **SDK API signatures / wiring** — see the `agentic-sdks` skill. This file selects a tool; that skill wires it.
- **Author-side prompt hardening** (delimiters, instruction-after-data) — see the `llm-prompt-engineering` skill. Tool selection here is about *runtime* enforcement.
- **Performance/quality rankings** — intentionally absent. No reproducible cross-tool benchmark exists; presenting one would be the marketing failure this file warns against.
