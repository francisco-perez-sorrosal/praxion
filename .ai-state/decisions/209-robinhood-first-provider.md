---
id: dec-209
title: Robinhood (MCP transport) is the first Provider plugin; supports_sandbox=false is first-class with HITL + capital-segregated budget as real-money guardrails
status: accepted
category: architectural
date: 2026-06-02
summary: The v1 provider plugin is Robinhood Agentic Trading over MCP transport. Because Robinhood has no documented sandbox and undocumented auth/order-types/rate-limits, supports_sandbox=false is a first-class capability flag, the HITL approval interceptor and the capital-segregated agentic-account budget mandate are the real-money guardrails, and all volatile specifics are re-fetched via external-api-docs at use time.
tags: [agentic-transactions, robinhood, provider, mcp-transport, hitl, no-sandbox, external-api-docs, churn]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: full
affected_files:
  - skills/agentic-transactions/references/robinhood.md
  - skills/agentic-transactions/SKILL.md
affected_reqs: [REQ-05, REQ-06]
---

## Context

The user locked Robinhood as the PoC provider anchor (its Agentic Trading MCP surface, launched 2026-05-27). Research caveats this heavily: Robinhood has **no documented sandbox**, and its auth scopes, order types, and rate limits are **publicly undocumented as of 2026-06-02** (the surface is 5 days old). The MCP servers *are* the integration surface — there is no REST Trading API or published SDK for the agentic surface. Robinhood's own disclaimer transfers risk explicitly: it "does not control, supervise, monitor, recommend, or audit these AI agents." The contract must make the live-only, real-money nature safe by construction.

## Decision

The v1 `Provider` plugin is **Robinhood, transport = MCP-client**, implementing the required core verbs against Robinhood's MCP surface. Specifically:

- **`supports_sandbox: false` is a first-class capability flag.** The onboarding flow and skill warn when a provider is live-only.
- **HITL approval interceptor is the primary real-money guardrail** — an optional-per-operation seam in the contract, made *mandatory* in the skill's guidance when `supports_sandbox: false`. Maps to Robinhood's "for some trades, agents show a preview the user must approve."
- **Capital-segregated agentic-account budget is the spend ceiling** — expressed as the `create_mandate` scope (`max_amount` + `time_window` + constraints), mapping to Robinhood's firewalled "agentic account."
- **Volatile specifics are NOT frozen.** `references/robinhood.md` marks auth scopes, order types, and rate limits as "verify at use time via `external-api-docs`"; the implementer re-fetches the current Robinhood agentic surface before writing concrete values.

## Considered Options

### Option 1 — Robinhood (MCP) first, sandbox-absent guardrails first-class (chosen; locked user decision)
- Pros: honors the user's marquee-provider choice; MCP-only validates the most consequential transport axis; guardrails are exercised against the hardest case (live-only).
- Cons: no sandbox makes dev iteration costly and risky; thin docs force re-fetch discipline.

### Option 2 — Alpaca first (sandbox-capable), Robinhood second
- Pros: paper trading on by default → zero-financial-risk dev iteration; mature `alpaca-py` SDK; automation-friendly ToS.
- Cons: contradicts the locked user decision that Robinhood is the PoC anchor.

## Consequences

- **Positive:** the live-only, real-money path is safe by construction — the contract cannot silently wire an autonomous agent to execution without the HITL gate and budget ceiling (REQ-05); nascent specifics stay current via `external-api-docs` rather than going stale in the artifact (REQ-06).
- **Negative / accepted:** dev iteration against a sandbox-less live broker is costly — **recommend** (not impose) Alpaca paper-trading as a conformance test double to exercise the same contract at zero financial risk during dev, then flip to Robinhood for the demo. The undocumented auth/order-type/rate-limit surface is a standing re-fetch obligation, not a one-time lookup.

## Prior Decision

None superseded. `supports_sandbox: false` and the HITL interceptor are realizations of capability flags and the optional-per-operation approval seam defined in `dec-208` (Provider contract shape).
