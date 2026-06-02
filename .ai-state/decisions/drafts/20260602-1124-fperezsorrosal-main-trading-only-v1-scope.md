---
id: dec-draft-26b721f3
title: v1 scope is trading-only PoC with a payments-ready contract
status: proposed
category: architectural
date: 2026-06-02
summary: v1 implements only the trading path (Space B) behind the Provider contract; the contract is designed to span payments (Space A) too, but payment providers and the pay-for-service composition are designed-for, not built. Honors a locked user decision.
tags: [agentic-transactions, scope, v1, trading-only, payments-ready, simplicity-first]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: full
affected_files:
  - skills/agentic-transactions/SKILL.md
affected_reqs: [REQ-04, REQ-05]
re_affirms: ""
---

## Context

The user locked the scope decision: v1 is a **trading-only PoC** with a **payments-ready contract**. Research confirms the two spaces are distinct (Nevermined cannot place an equity order; Robinhood is a brokerage, not a payment rail) and that a full "agent buys stock and pays for the service" flow would *compose* a payment provider (Space A) with a brokerage (Space B). The contract (`dec-draft-7a508928`) is built to span both, but the question is what v1 *implements*.

## Decision

v1 **implements only the trading path** with a single brokerage provider (Robinhood — see `dec-draft-f2bfc5c1`). The `Provider` contract is designed to span both spaces, but payment providers (x402 / Nevermined / Stripe) and the pay-for-service composition are **designed-for, not built**. The skill and contract make the payment path a future drop-in (a new plugin behind the same core + a `references/<provider>.md`).

## Considered Options

### Option 1 — Trading-only v1, payments-ready contract (chosen; locked user decision)
- Pros: smallest blast radius; the contract is exercised by exactly one real provider before generalizing; cheapest validation of the seam.
- Cons: the pay-for-service composition demo is deferred.

### Option 2 — Payments-only v1
- Pros: exercises the higher-churn Space A first.
- Cons: contradicts the user's stock-trading PoC goal; no brokerage execution.

### Option 3 — Both spaces on day one (compose Nevermined + Robinhood)
- Pros: showcases the full composition immediately.
- Cons: doubles the v1 surface; validates neither space deeply; over-engineers a nascent feature against the simplicity-first directive.

## Consequences

- **Positive:** the contract is validated against one real provider before generalizing (REQ-04); guardrails for live-only execution are exercised concretely (REQ-05).
- **Negative / accepted:** a contract validated against one provider may over-fit — mitigated by recommending Alpaca paper-trading as a conformance double (exercises the same contract against a second, sandbox-capable provider during dev). The composition demo is deferred, not designed away — the contract supports it.
