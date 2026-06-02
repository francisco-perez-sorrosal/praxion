# Robinhood Trading Provider

v1 plugin shape for the Robinhood Agentic Trading provider — MCP transport (HTTP),
equities only, **no sandbox**.
Back-link: [../SKILL.md](../SKILL.md)

> **State of knowledge (verified 2026-06-02 against Robinhood's official support docs).**
> The connection surface is now public: the MCP endpoint URL, the HTTP transport, the
> connect command, and the desktop-only onboarding/auth flow are documented (below).
> What is **still not published**: the exact MCP **tool names/schemas**, the **order-type
> enum**, **rate limits**, and the OAuth/token internals. The concrete way to resolve
> those is **operational, not documentary** — connect an MCP client to the live endpoint
> and **introspect its tool list** (`tools/list`), then read the linked order-types doc.
> Re-run `chub_search({ query: "robinhood trading" })` via `external-api-docs` before
> coding in case curated docs have since appeared.

---

## Provider Identity

| Field | Value |
|---|---|
| **Provider name** | Robinhood Agentic Trading |
| **Status** | Beta — launched 2026-05-27; staged rollout via email invite; Gold members prioritized |
| **Transport kind** | `mcp-client` over **HTTP** (streamable HTTP MCP) |
| **MCP endpoint** | `https://agent.robinhood.com/mcp/trading` |
| **Asset class (v1 beta)** | Equities only; options / crypto / event contracts / futures on roadmap |
| **`supports_sandbox`** | **`false`** — no paper-trading or testnet environment (confirmed absent) |
| **Geographic scope** | US-only (implied); desktop required for onboarding |
| **Access gate** | Primary individual investing account in good standing; up to 10 self-directed individual accounts incl. the Agentic account; email-invite rollout |
| **Official docs** | `robinhood.com/us/en/support/agentic-trading` and the `agentic-trading-overview` support article |

---

## Connection & Onboarding (verified 2026-06-02)

The MCP endpoint **is** the integration surface — there is no REST SDK for the agentic flow.

**Connect (Claude Code):**
```
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
```
**Connect (Claude Desktop):** Settings → Connectors → Add custom connector → `https://agent.robinhood.com/mcp/trading`. Any MCP-capable client works (Robinhood names Claude, ChatGPT, Codex / Codex CLI, Cursor).

**Authentication / onboarding:**
- **Desktop-only.** Connecting the MCP auto-opens an onboarding flow in a desktop browser; mobile users must copy the onboarding URL to a desktop.
- Onboarding prompts you to **open a dedicated Agentic account**.
- The published docs do **not** specify the OAuth grant type, token format, or scope names — treat the auth internals as opaque; the onboarding handles the grant. (Confirm by inspecting the client's stored MCP credential after onboarding.)

**First step for any implementer:** after `mcp add`, run an MCP `tools/list` against the endpoint to enumerate the actual tools + their input schemas. That introspection — not this file — is the source of truth for tool names, parameters, and order types. Cross-check against the community reference implementation [`Open-Agent-Tools/open-stocks-mcp`](https://github.com/Open-Agent-Tools/open-stocks-mcp) (multi-broker Robinhood/Schwab MCP) for shape, but verify against the live first-party endpoint.

**Programmatic connect + introspect** (official `mcp` Python SDK, `pip install mcp>=1.26.0`, Python ≥3.10; Streamable HTTP is the current transport — do not copy older HTTP+SSE examples):
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROBINHOOD_MCP = "https://agent.robinhood.com/mcp/trading"

async with streamablehttp_client(
    ROBINHOOD_MCP, headers={"Authorization": f"Bearer {token}"}
) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()                 # REQUIRED before any list/call
        tools = await session.list_tools()         # AUTHORITATIVE source of tool names/params
        print([t.name for t in tools.tools])
        # result = await session.call_tool("<tool-from-list>", { ... })
```
Higher-level alternative for agent loops: OpenAI Agents SDK `MCPServerStreamableHttp(params={"url": ROBINHOOD_MCP, "headers": {"Authorization": f"Bearer {token}"}}, cache_tools_list=True)`. Confirm exact tool names/args against the live `tools/list`; treat the `token`/auth mechanics as opaque until verified post-onboarding.

---

## Access Scope & Privacy (read this before granting the agent)

Robinhood's MCP grant is **asymmetric** — broad read, narrow write:

- **READ access spans ALL your Robinhood accounts**, not just the Agentic one. Per the docs, the agent can read: *all your Robinhood accounts including account numbers; all positions and balances; all transactions including order history.*
- **WRITE access is limited to the Agentic account only** — "Your agent can only place trades in your Robinhood Agentic account."

**Implication for `resolve_identity()`:** the identity grant is wider than the spend boundary. The capital-segregation firewall protects your *funds* (write side), but the agent — and any third-party AI provider it routes data to — sees your *entire account picture* on the read side. Surface this to the user at onboarding; do not treat the agentic account as a read isolation boundary, because it isn't.

---

## `supports_sandbox: false` — Real-Money Guardrails Are Mandatory

> **Critical:** with `supports_sandbox: false`, every integration-test iteration runs
> against the **live** Robinhood brokerage. There is no dry-run mode. The two guardrails
> below are required when this provider is used.

### 1. Capital-Segregated Agentic Account (Budget Mandate)
- Onboard a dedicated **Agentic account**, separate from the main portfolio; the agent can only place trades there.
- Fund it with only the capital you are willing to lose in testing/early operation — this is the spend ceiling.
- The contract's `create_mandate` verb maps to configuring/signing this budget on the Agentic account.

### 2. HITL Approval Interceptor — **Robinhood does NOT enforce this for you**
This is the most important correction from the live docs. The trade-preview gate is **user-configured, not system-enforced**:
- **Default:** "Before your agent takes action, you can review what it's about to do."
- **But:** "if you've asked your agent to take action without asking your approval, it **can place trades without your confirmation**." There is **no system-level mandatory preview**.
- Therefore the `approve(mode == "human_gate")` interceptor must be enforced in **your** agent loop / the provider plugin — do not rely on Robinhood to gate. For a PoC, default to `human_gate` on every `execute()` and only opt into `autonomous` behind an explicit, logged user decision.
- Load `agentic-sdks` for agent-loop / interceptor wiring patterns.
- **Make the gate durable, not a blocking prompt.** Do not gate with a bare `input()` — a process restart loses the pending approval. Use a durable interruption: e.g. the OpenAI Agents SDK marks the order tool `needs_approval=True`, surfaces `RunResult.interruptions`, and lets you serialize run state (`state.to_json()`) so the human can approve out-of-band and the run resumes from saved state. On rejection, discard the pending execution. This doubles as the boundary guard: the order tool is never reached until approval resolves.

---

## Core Verbs — Robinhood Implementation Shape

All six contract verbs are required. Mapping reflects the documented surface as of 2026-06-02; tool-level names/params come from live `tools/list` introspection.

| Contract verb | Robinhood MCP mapping | Notes |
|---|---|---|
| `resolve_identity()` | Desktop onboarding grant to the Agentic account | Broad read across all accounts, write only to the Agentic account; OAuth/scope internals opaque — inspect stored credential |
| `create_mandate(scope)` | Capital-segregated budget on the Agentic account | Spend ceiling = the funds deposited; the "firewall from main portfolio" |
| `get_quote(target)` | MCP tool for portfolio value / buying power / quote | Tool name + market-data granularity (bars, chains) from `tools/list` — not in docs |
| `authorize(mandate, quote)` | Returns `Approval`; **enforce HITL in your loop** | Robinhood does not auto-gate; design for both `autonomous` and `human_gate` |
| `execute(authorization)` | MCP tool to place the equity order | Order-type enum not enumerated in docs (links out); introspect/read the order-types doc |
| `get_receipt(ref)` | MCP tool for execution/order confirmation | Response shape from `tools/list` / live call |

**Venue detail defaults (until verified against the live surface):**
```python
VenueDetail(
    market_hours  = "regular",   # assume regular hours only until extended-hours confirmed
    order_type    = "market",    # "different order types" referenced but not enumerated; confirm via order-types doc
    partial_fills = True,        # equities frequently partially fill; assume True
    fills_async   = True,        # fills arrive asynchronously; do not block on execute()
)
```

---

## Volatile Specifics
<!-- last-verified: 2026-06-02 -->

**Now known (verified 2026-06-02):** MCP endpoint URL, HTTP transport, connect command, desktop-only onboarding/auth flow, read/write access scope, no-sandbox, eligibility, HITL-is-not-system-enforced. Reflected above.

**Still undocumented — resolve operationally (introspect the live MCP server) before coding:**

| Specific | Status | Action |
|---|---|---|
| **MCP tool names + input schemas** | Not published | `tools/list` against the live endpoint after `mcp add`; cross-ref `open-stocks-mcp` |
| **Order types** | "Different available order types" referenced, not enumerated | Read the linked order-types doc + confirm via the place-order tool schema |
| **Rate limits** | Not published | Discover empirically / watch for MCP error responses; re-check docs |
| **OAuth scopes / token format** | Onboarding handles it; internals opaque | Inspect the client's stored MCP credential post-onboarding |
| **HITL triggering conditions** | User-configured, not system-enforced | Enforce `human_gate` in your own loop; do not depend on Robinhood |
| **Extended-hours trading** | Not documented in beta | Default `market_hours: "regular"`; verify |
| **Options / crypto support** | On roadmap; not in v1 beta | Verify before expanding beyond equities |

---

## Composition Notes

| Skill | Purpose |
|---|---|
| [`mcp-crafting`](../../mcp-crafting/SKILL.md) | MCP **client** wiring — HTTP transport config, `tools/list` introspection, MCP Inspector testing against `https://agent.robinhood.com/mcp/trading` |
| [`agentic-sdks`](../../agentic-sdks/SKILL.md) | Agent-loop integration — HITL interceptor wiring (enforced client-side), tool registration |
| [`agentic-interface-design`](../../agentic-interface-design/SKILL.md) | Tool-schema design quality — evaluate the introspected Robinhood tools' naming/error grammar |
| [`external-api-docs`](../../external-api-docs/SKILL.md) | Re-fetch current Robinhood docs before coding — the beta surface is churning |

**Explicit risk transfer:** Robinhood's docs state "Robinhood does not control, supervise, monitor, recommend, or audit these AI agents," and "You are ultimately responsible for the trades your AI agent places." The capital-segregated account + client-enforced HITL interceptor are the implementation-level mitigations — they **bound** this risk, they do not eliminate it.
