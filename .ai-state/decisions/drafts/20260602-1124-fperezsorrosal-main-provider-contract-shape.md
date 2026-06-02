---
id: dec-draft-7a508928
title: Provider contract = thin required core + declared optional capabilities + pluggable transport + typed rail_detail/venue_detail extension
status: proposed
category: architectural
date: 2026-06-02
summary: One language-independent Provider contract spans agentic payments and trading via a six-verb required core, declared optional capabilities, a pluggable transport strategy, and a typed extension that localizes all rail/venue divergence.
tags: [agentic-transactions, provider-contract, payments, trading, progressive-disclosure, language-independent, abstraction]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: full
affected_files:
  - skills/agentic-transactions/SKILL.md
  - skills/agentic-transactions/references/provider-contract.md
affected_reqs: [REQ-04, REQ-05, REQ-06]
---

## Context

Praxion is adding a capability to onboard managed projects onto the "agentic transactions" stack (agentic payments + agentic trading). Research (`RESEARCH_FINDINGS.md` §4) identified two adjacent but distinct problem spaces — Space A (let an agent *pay*) and Space B (let an agent *trade*) — that must be composed, not merged, behind one provider abstraction. The domain is nascent and fast-moving (x402 → Linux Foundation 2026-04-02; Robinhood agentic trading launched 2026-05-27, 5 days before research). The design must make later providers cheap to add without redesign, while not over-modeling protocols Praxion has not committed to.

## Decision

The `Provider` contract is **language-independent** (conceptual; Python binding first) and composed of:

- A small **required common core** every provider implements: `resolve_identity`, `create_mandate`, `get_quote`, `authorize` (HITL-capable), `execute`, `get_receipt`, an `idempotency_key` required on `authorize`/`execute`, and one normalized `TransactionError` grammar.
- **Declared optional capabilities** (never assumed): `supports_sandbox`, `supports_market_data`, `supports_positions`, `approval_mode`, `transport_kind`; plus optional ops `get_market_data()`, `list_positions()`, and `OrderLifecycle` (`list_orders`/`cancel`/`replace`).
- A pluggable **`transport`** strategy — `MCP-client` vs `HTTP/SDK-client` — abstracting how the agent reaches the provider (the most consequential pluggability axis: Robinhood is MCP-only).
- A typed **`rail_detail` / `venue_detail`** extension that localizes *all* rail/venue-specific divergence (settlement finality, reversibility, chain params, market hours, order types, partial fills), keeping the core stable.

## Considered Options

### Option 1 — Thin core + capabilities + transport + typed extension (chosen)
- Pros: later providers are a plugin + reference file, not a redesign; volatile specifics live outside the core, surviving churn; transport pluggability handles MCP-only providers cleanly.
- Cons: cross-provider features needing uniform finality semantics would require a future core extension.

### Option 2 — Fat unified contract modeling all of payments + trading
- Pros: one place models everything (market data, order lifecycle, refunds, disputes).
- Cons: violates simplicity-first for a nascent feature; over-fits to protocols not committed to; high churn surface.

### Option 3 — Two separate contracts (one per space, no shared core)
- Pros: each space modeled independently.
- Cons: no reuse; the "agent buys stock and pays for the service" composition becomes two unrelated integrations; duplicates identity/mandate/idempotency/error concerns.

## Consequences

- **Positive:** Adding Alpaca, x402, Nevermined, or Stripe later is a new plugin behind the same core + a `references/<provider>.md` (REQ-04). The finality "leak" identified in research §4.1 is localized to the typed extension, not forced into the core. The artifact stays language-independent and token-lean.
- **Negative / accepted risk:** A contract validated against one provider (Robinhood, v1) may have over-fit seams — mitigated by recommending Alpaca paper-trading as a conformance double. A future uniform-finality feature is a known, un-pre-built seam in the core.
