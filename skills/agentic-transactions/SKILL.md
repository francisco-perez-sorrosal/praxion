---
name: agentic-transactions
description: >
  Provider contract, decision rubric, and composition guidance for implementing
  agentic transactions in a managed project — covering both Space A (agentic payments:
  mandate-based payment rails, stablecoin/card/crypto settlement) and Space B (agentic
  trading: brokerage order placement, market data, portfolio positions).
  Triggers: agentic payment, agentic trading, Provider contract, mandate, settlement
  finality, HITL spend-gating, brokerage agent, MCP trading, order execution, payment
  rail, idempotency key, TransactionError, supports_sandbox. Activate when a managed
  project needs to implement agentic payments or stock trading behind a provider-pluggable
  contract. Language modules not applicable — the contract is language-independent;
  a Python binding sketch is in references/provider-contract.md.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Provider Transport Strategies"
  - "Robinhood Provider Specifics"
staleness_threshold_days: 60
---

# Agentic Transactions

Design and implementation guidance for agentic transactions — any flow where a language
model autonomously initiates a payment or places a trade on a live financial provider.

**The two adjacent spaces this skill covers:**

- **Space A — Agentic payments**: an agent *pays* for something (HTTP-native stablecoin
  rails such as x402, card-network mandate flows like AP2/ACP/Visa/Mastercard, crypto
  smart-account policies). The common currency is signed *mandates*.
- **Space B — Agentic trading**: an agent *places an equity or crypto order* via a
  brokerage API (Robinhood MCP, Alpaca, IBKR). The common currency is *orders*, with
  async partial fills and market-hours constraints.

Both spaces share one `Provider` contract with a common core and declared optional
capabilities. The contract is the subject of this skill.

**Satellite files** (loaded on-demand):

- [references/provider-contract.md](references/provider-contract.md) — formal contract spec: six required verbs, typed return shapes, `TransactionError` grammar, Python binding sketch
- [references/robinhood.md](references/robinhood.md) — v1 Robinhood trading-provider plugin shape (MCP transport); `supports_sandbox: false` guardrails; volatile specifics flagged for re-fetch
- [references/_provider-template.md](references/_provider-template.md) — blank-slate template for adding a new provider behind the contract
- [references/design-review-checklist.md](references/design-review-checklist.md) — transaction-design audit checklist for both spaces (PASS/FAIL/WARN)

---

## Decision Rubric — Where Are You?

Answer these three questions before loading any reference file.

| Question | Space A (payments) | Space B (trading) |
|---|---|---|
| **What is the agent doing?** | Paying for a service or good | Placing/managing an equity or crypto order |
| **Which provider?** | x402, AP2, ACP/Stripe, Visa, Nevermined, Circle… | Robinhood (v1 beta), Alpaca, IBKR, Tradier… |
| **Is a sandbox available?** | Provider-dependent (many have testnets) | Alpaca: yes (paper trading on by default). Robinhood: **no** — `supports_sandbox: false` |

**Load on demand:**
- Building or reviewing a Robinhood provider → `references/robinhood.md`
- Adding a new provider → copy `references/_provider-template.md` → fill all bracketed fields
- Formal pseudotype spec, Python binding → `references/provider-contract.md`
- Reviewing a transaction design or provider integration → `references/design-review-checklist.md`

**Key composition note:** Robinhood (Space B — trades equities) and Nevermined/x402 (Space A — pays for services) are orthogonal layers. A "pay-for-the-service, then trade" flow *composes* the two; neither replaces the other. Note: Robinhood also ships a separate **Banking MCP server (Agentic Credit Card — Space A, payments)**, orthogonal to the Trading MCP (Space B). The Banking MCP endpoint URL is not yet publicly documented; when documented it becomes a second Robinhood provider on the payments side.

---

## Provider Contract — Conceptual Overview

The `Provider` contract has three layers. The formal spec with typed return shapes lives in `references/provider-contract.md`.

### Common Core (six required verbs — all providers implement all six)

```
resolve_identity()          → AgentIdentity
create_mandate(scope)       → Mandate
get_quote(target)           → Quote
authorize(mandate, quote)   → Approval            # idempotency_key required
execute(authorization)      → Execution           # idempotency_key required
get_receipt(ref)            → Receipt
# normalized TransactionError across all calls
```

`idempotency_key` is required on every `authorize` and `execute` call. Networks fail;
clients retry; duplicate side-effects are silent bugs.

### Declared Optional Capabilities

Capabilities are declared by the provider in its plugin descriptor, never assumed by
the core:

| Flag / Operation | Meaning |
|---|---|
| `supports_sandbox: bool` | Whether a test/paper-trading mode is available. **Always check before wiring a live provider.** |
| `supports_market_data` | Provider exposes `get_market_data()` |
| `supports_positions` | Provider exposes `list_positions()` |
| `approval_mode` | `autonomous`, `human_gate`, or `hybrid` — per-operation HITL interceptor support |
| `transport_kind` | `mcp-client` or `http-sdk-client` |
| `OrderLifecycle` | `list_orders()`, `cancel()`, `replace()` — trading-only |

### Provider Transport Strategies
<!-- last-verified: 2026-08-05 -->

Transport is the most consequential pluggability axis. Two strategies:

- **MCP-client** — the agent calls the provider's own MCP server. Robinhood is MCP-only;
  Alpaca and Stripe ship first-party MCP servers (both actively maintained). Three carry
  caveats worth knowing before you plan around them: **Visa**'s `visa/mcp` is framed largely
  as developer-integration tooling for Visa APIs rather than a settlement transport;
  **PayPal**'s `paypal/paypal-mcp-server` has been dormant since 2025-10 and active work
  moved to `paypal/AI-Toolkit`; **Nevermined** ships a library for *monetizing* MCP servers
  (`mcp-payments-library`), not a first-party provider MCP server — grouping it with the
  others implies a parity that does not exist. No REST SDK needed for the MCP-client path.
- **HTTP/SDK-client** — direct REST or language SDK call. Alpaca REST + `alpaca-py`,
  IBKR `ibapi`, Stripe Python SDK. Suitable when the provider has a mature SDK and no
  MCP server, or when the SDK offers capabilities the MCP server does not.

A provider's `transport_kind` capability flag declares which strategy it uses.

### Extension Fields — `rail_detail` / `venue_detail`

All rail- or venue-specific divergence rides in two typed extension fields on `Execution`
and `Receipt`. The common core never leaks finality semantics:

- `rail_detail` — payment-rail divergence: `finality`, `reversibility`, `chain_params`
- `venue_detail` — trading-venue divergence: `market_hours`, `order_types`, `partial_fills`, `fills_async`

Adding a new provider that differs only in these fields requires no change to the core —
only a new `references/<provider>.md` and its plugin descriptor.

### Normalized Error Grammar

A closed set of `TransactionError` codes, each carrying `retriable: bool` and optional
`step_up_required: bool`. See `references/provider-contract.md` for the full set.
No provider adds codes outside this grammar — rail-specific decline detail rides in
`rail_detail`/`venue_detail`.

---

## Churn-Resilience Stance

This is a fast-moving domain (x402 Linux Foundation move: 2026-04-02; Robinhood beta
launch: 2026-05-27). The design is deliberately thin at the core and volatile at the
edges:

- **Stable core** — the six verbs, the error grammar, and the capability-flag contract
  change slowly (they are the seam).
- **Volatile edges** — auth scopes, rate limits, order types, MCP endpoint URLs live in
  `references/<provider>.md` and are explicitly marked "verify at use time via
  `external-api-docs`". Do not bake frozen values into production code.
- **Provider transport strategies** and **Robinhood specifics** are flagged as
  `staleness_sensitive_sections` in this skill's frontmatter. Run `/refresh-skill
  agentic-transactions` when those sections feel stale.
- Use the `external-api-docs` skill to fetch current provider documentation before
  writing any integration code. See that skill's retrieval protocol.

---

## Composition Map

Load these skills alongside `agentic-transactions` as the task requires:

| Skill | When to reach for it |
|---|---|
| [`mcp-crafting`](../mcp-crafting/SKILL.md) | Building the MCP client transport layer — FastMCP config, tool schema design, Inspector testing |
| [`agentic-sdks`](../agentic-sdks/SKILL.md) | Wiring the provider to an agent loop — SDK patterns, multi-agent orchestration, tool registration |
| [`agentic-interface-design`](../agentic-interface-design/SKILL.md) | Designing the tool surface the model sees — tool naming, error grammar ergonomics, fat-vs-thin decomposition |
| [`external-api-docs`](../external-api-docs/SKILL.md) | Fetching current provider API docs before writing integration code — mandatory for any undocumented or fast-moving surface |
| [`api-design-craft`](../api-design-craft/SKILL.md) | Reviewing the quality of the provider contract or any REST/GraphQL surface the provider exposes |

**Curated reference docs (fetch via `external-api-docs` at use time):** Context Hub carries the *plumbing* — `mcp/package` (the official Python MCP **client** over Streamable HTTP + OAuth — this is the Robinhood transport: `ClientSession` → `initialize()` → `list_tools()` → `call_tool()`), `fastmcp/package` (higher-level MCP client/server), and `stripe/package` (Python Stripe SDK, for a future Stripe payment provider). The novel protocols (x402, AP2, Nevermined, Coinbase AgentKit) and the brokers (Robinhood, Alpaca) are **not** in Context Hub — fetch those from the live web and introspect the provider's MCP server directly.

### Robinhood Provider Specifics
<!-- last-verified: 2026-08-05 -->

When the target provider is Robinhood: load `references/robinhood.md` immediately.
Key pre-flight facts:

- `supports_sandbox: false` — every test iteration runs against the live brokerage.
  A capital-segregated agentic account and a HITL approval interceptor are **mandatory**
  guardrails, not optional.
- **Gate capital-moving tools by name pattern, never by enumeration.** `place_*_order` and
  `cancel_*_order` are capital-moving; `review_*_order` is the HITL primitive. Options
  trading went live *after* a gate was written around equities alone, leaving real-money
  placement ungated — a pattern gate covers the next asset class on the day it ships.
- **The tool surface is large and fast-moving** — it grew ~5× in about two months, and this
  skill deliberately states no count. Resolve it via a live `tools/list`.
- Auth scopes, order types, and rate limits remain **undocumented** — re-fetch via
  `external-api-docs` before implementing. (The **MCP endpoint URL is documented**:
  `https://agent.robinhood.com/mcp/trading`. An earlier revision listed it as undocumented,
  contradicting this skill's own `references/robinhood.md` at the same verification date.)
- Robinhood's agentic surface is MCP-only (no REST SDK for agentic flows).
- HITL is **not system-enforced** on Robinhood's side: "if you've asked your agent to take
  action without asking your approval, it can place trades without your confirmation," and
  "Robinhood does not control, supervise, monitor, recommend, or audit these AI agents." The
  gate must be yours.

See `references/robinhood.md` for the full plugin shape, HITL wiring, and budget mandate
requirements.
