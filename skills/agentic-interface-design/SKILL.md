---
name: agentic-interface-design
description: >
  Interface design for the model as consumer: MCP tools, function-calling schemas,
  A2A contracts (Agent Cards). Human-vs-agent ergonomics, tool naming, error grammar,
  fat-vs-thin decomposition, progressive disclosure (lazy loading), idempotency
  (request_id), response pagination (next_cursor, has_more), JSON-schema craft.
  Triggers: designing/reviewing MCP tools, tool descriptions, function-calling schemas,
  agent error ergonomics, A2A contracts. Not for web/CLI (web-ui-design, tui-design)
  or REST/GraphQL quality (api-design-craft).
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "The Token Economy Problem"
  - "A2A Contract Design"
---

# Agentic Interface Design

Interface design craft for one specific consumer: the language model. When the consumer is a model rather than a human, the ergonomics of the interface change fundamentally — and most API design instincts don't transfer.

Start with the shared canon in `references/design-fundamentals.md` — the Bloch principles apply directly here (minimal surface area, names matter, hard-to-misuse, fail-fast). Then apply the agentic-specific lens this skill provides.

**Satellite files** (loaded on-demand):

- [references/design-fundamentals.md](references/design-fundamentals.md) -- durable design canon (Rams, Norman, Nielsen, Bloch) — the first-principles foundation
- [references/tool-design-for-models.md](references/tool-design-for-models.md) -- tool naming, description writing, parameter naming, granularity decisions
- [references/mcp-primitives-as-design-surfaces.md](references/mcp-primitives-as-design-surfaces.md) -- when to use tool vs resource vs prompt; the do-not-mix rule
- [references/agent-error-ergonomics.md](references/agent-error-ergonomics.md) -- error grammar, idempotency patterns, Stripe-style request_id
- [references/progressive-disclosure-of-tools.md](references/progressive-disclosure-of-tools.md) -- token economy problem, meta-tool pattern, domain bundles, 85–100× reduction
- [references/agent-contracts.md](references/agent-contracts.md) -- JSON-schema design, response structure, pagination, A2A contracts
- [references/design-review-checklist.md](references/design-review-checklist.md) -- audit checklist for MCP servers, tool surfaces, A2A contracts

## The Central Principle: Names and Descriptions ARE the Interface

A human reads documentation once and builds a mental model. A model reads the tool name and description **on every single call**, re-reasons over them each time, and cannot accumulate domain knowledge across sessions. The description is not documentation — it is the executable interface. It is the primary lever for correcting model behavior.

Consequence: a description change fixes broken model behavior. This is not a metaphor. When Anthropic's web search tool was causing Claude to append "2025" to queries, the fix was a description update, not a code change. The description told the model to stop, and it stopped.

Write tool descriptions as if onboarding a new team member who has never seen the system. Include what the tool does, what it does NOT do, its preconditions, and what the return value means.

## Human-vs-Agent Ergonomics

The design decisions that follow from this distinction are not obvious without a side-by-side comparison:

| Dimension | Human consumer | Agent (LLM) consumer |
|-----------|---------------|----------------------|
| **Learning** | Reads docs once; builds mental model | Re-reads description every invocation; no persistent learning |
| **Error handling** | Reads message, searches docs, asks for help | Must self-recover from the error alone, in the same turn |
| **Context budget** | Unlimited working memory | Fixed window; large responses displace reasoning tokens |
| **Discovery** | Browses API reference, tries curl | Works only with what is in its context at call time |
| **Consistency** | Prefers consistency | Inconsistency causes tool selection failures |
| **Response size** | Bigger is often more helpful | Smaller is better; paginate aggressively |

## Fat Tool vs. Many Thin Tools

LLM decision quality degrades measurably when presented with more than **~20–25 tools** at once. Two design philosophies address this at the decomposition level:

**Consolidate (fat tool)** when the agent would almost always call the tools in sequence with no intermediate reasoning. `schedule_meeting(participants, time, duration, title)` combines availability check, conflict resolution, and creation in one call. Reduces round-trips and keeps the tool count down.

**Keep separate (thin tools)** when the agent needs to branch based on intermediate results. `check_availability`, `create_event`, `send_invite` can be combined or omitted depending on what check_availability returns.

Decision rule: if the steps always occur together and the combined semantics are clear → fat tool. If the agent might do step A without step B → thin tools.

## Progressive Disclosure of Tools

Token cost of tool schemas is significant. Production benchmarks:
- A typical 400-tool enterprise MCP server consumes >400K tokens in schema definitions alone — exceeding a 200K context window.
- LLM decision quality degrades measurably past ~20–25 tools presented at once.
- Lazy schema loading (serve schemas on demand) achieves **85–100× token reduction** while maintaining selection accuracy.

If the surface has more than ~20 tools, it needs progressive disclosure. No exceptions. See `references/progressive-disclosure-of-tools.md` for patterns.

## Agent Error Grammar

Errors must be actionable by the model in the same turn with no human intervention:

```
"Column 'user_id' not found in table 'orders'.
Available columns: id, order_id, customer_id, created_at."
```

The grammar: **X failed because Y. To fix this: Z.**

Never: a stack trace. Never: an error code alone. Never: "Internal server error." The model needs to know what to try next with the information currently in its context window. See `references/agent-error-ergonomics.md` for full patterns.

## Tool Result Pagination Rules

Paginate every list tool result. The model's context window is a shared resource:
- Default page size: **10–20 items** (not 100, not unlimited)
- Always include: `next_cursor` (or `next_page_token`), `total_count`, `has_more`
- Return only what the agent needs for the next step — verbose results displace reasoning tokens

## When to Reach for Which Reference

| Task | Reference file |
|------|---------------|
| Tool naming, description writing, parameter naming | `tool-design-for-models.md` |
| Deciding which MCP primitive (tool/resource/prompt) | `mcp-primitives-as-design-surfaces.md` |
| Error design, idempotency for retries | `agent-error-ergonomics.md` |
| Progressive disclosure, token economy | `progressive-disclosure-of-tools.md` |
| JSON-schema design, response structure, A2A contracts | `agent-contracts.md` |
| Reviewing an existing tool surface or MCP server | `design-review-checklist.md` |
| Shared design principles (Bloch, Rams, Nielsen) | `design-fundamentals.md` |

## Related Skills

- **[`api-design-craft`](../api-design-craft/SKILL.md)** — the same taste/quality lens applied to REST/GraphQL/gRPC APIs; when an interface serves both human and model consumers, both skills apply.
- **[`mcp-crafting`](../mcp-crafting/SKILL.md)** — MCP server construction (FastMCP, transport config, Inspector testing); this skill covers design quality, `mcp-crafting` covers how to build it.
- **[`agentic-sdks`](../agentic-sdks/SKILL.md)** — wiring tools to the agent loop, framework selection, multi-agent orchestration; this skill covers design craft, `agentic-sdks` covers SDK mechanics.
- **[`communicating-agents`](../communicating-agents/SKILL.md)** — Agent Card structure, A2A task lifecycle, interaction patterns; this skill covers contract design, `communicating-agents` covers protocol mechanics.
- **[`llm-prompt-engineering`](../llm-prompt-engineering/SKILL.md)** — when a tool description is long enough to be a mini-prompt (few-shot examples, chain-of-thought cues).
