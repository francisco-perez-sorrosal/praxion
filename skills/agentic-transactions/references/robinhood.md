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
| **Asset class (v1 beta)** | **Long equities only** — no shorts, options, crypto, or futures in v1 beta |
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

**Authentication / onboarding — PRIMARY path (Claude Code managed OAuth):**
- **Desktop-only.** Connecting the MCP auto-opens an onboarding flow in a desktop browser; mobile users must copy the onboarding URL to a desktop.
- Onboarding prompts you to **open a dedicated Agentic account**.
- For the Claude Code path, **OAuth is managed by Claude Code** — the `/mcp` browser flow stores tokens in the system keychain (macOS) and **auto-refreshes** them. You do **not** supply a static `Authorization: Bearer` header; Claude Code handles the token lifecycle. Setting a static Bearer header alongside the OAuth flow causes Claude Code to report connection failed if the header is rejected by Robinhood's auth server — do not configure both.
- If a token expires mid-session (401/403 response), Claude Code marks the server as needing re-authentication in `/mcp` → follow the browser flow again. "Clear authentication" in the `/mcp` menu revokes stored tokens.
- The OAuth grant type, scope names, and token format are opaque — the onboarding handles the grant; inspect the client's stored MCP credential post-onboarding if needed.

**Scope guidance (Claude Code):** use **`local` scope** (the default) for Robinhood — the OAuth grant is personal and per-installation, so a per-user local entry is the right default. OAuth tokens live in Claude Code's system keychain, **never in `.mcp.json`** — so a committed server entry leaks no token; the rule that matters is *never commit a static token* (e.g. an `Authorization` header).
```bash
# Correct (local scope — default)
claude mcp add --transport http robinhood-trading https://agent.robinhood.com/mcp/trading
# Equivalent explicit form
claude mcp add --transport http --scope local robinhood-trading https://agent.robinhood.com/mcp/trading
```

**First step for any implementer:** after `mcp add`, run an MCP `tools/list` against the endpoint to enumerate the actual tool **input schemas** and parameter names. Tool names are now confirmed (see "Tool Surface" below), but schemas still require live introspection. Cross-check against the community reference implementation [`Open-Agent-Tools/open-stocks-mcp`](https://github.com/Open-Agent-Tools/open-stocks-mcp) (multi-broker Robinhood/Schwab MCP) for shape, but verify against the live first-party endpoint.

**ADVANCED / standalone path** (official `mcp` Python SDK, `pip install mcp>=1.26.0`, Python ≥3.10; Streamable HTTP is the current transport — do not copy older HTTP+SSE examples). Use this when driving the Robinhood MCP outside of Claude Code (e.g. a headless agent loop). The `token` here comes from the OAuth flow — Robinhood exposes no documented static API-key/bearer path for the first-party endpoint yet:
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROBINHOOD_MCP = "https://agent.robinhood.com/mcp/trading"

# token is acquired from the OAuth flow — NOT a static API key
async with streamablehttp_client(
    ROBINHOOD_MCP, headers={"Authorization": f"Bearer {token}"}
) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()                 # REQUIRED before any list/call
        tools = await session.list_tools()         # AUTHORITATIVE source of tool schemas/params
        print([t.name for t in tools.tools])
        # result = await session.call_tool("<tool-from-list>", { ... })
```
Higher-level alternative for agent loops: OpenAI Agents SDK `MCPServerStreamableHttp(params={"url": ROBINHOOD_MCP, "headers": {"Authorization": f"Bearer {token}"}}, cache_tools_list=True)`. Confirm exact tool names/args against the live `tools/list`; treat the auth mechanics as opaque until verified post-onboarding.

---

## Tool Surface (10 official MCP tools, confirmed 2026-06-02)
<!-- last-verified: 2026-06-02 -->

The Robinhood Trading MCP exposes exactly these 10 tools (names verbatim from the official support article "Trading with your agent"). Tool **input schemas / parameter names / order-type enum** are still not published and require live `tools/list` introspection.

| Tool name | Category | Notes |
|---|---|---|
| `get_accounts` | Read | All Robinhood accounts (ALL accounts, not just the Agentic one) |
| `get_portfolio` | Read | Portfolio value by asset class + buying power |
| `get_equity_positions` | Read | Open positions: quantity, cost basis |
| `get_equity_quotes` | Read | Real-time quotes; up to 20 symbols per call |
| `get_equity_orders` | Read | Order status + history — use to poll after placement |
| `get_equity_tradability` | Read | Symbol tradability + fractional share eligibility |
| `review_equity_order` | Simulate | **Simulate** order; returns pre-trade warnings — the canonical HITL gate primitive |
| `place_equity_order` | Write | Execute the equity order — the **only** write-side placement tool |
| `cancel_equity_order` | Write | Cancel an open order |
| `search` | Read | Find company names or ticker symbols |

**Summary:** 8 read/simulate tools, 1 place tool, 1 cancel tool.

**Canonical two-step HITL gate:** always call `review_equity_order` first → surface returned warnings to the human → only call `place_equity_order` after explicit human approval. This is the tool-level implementation of the `authorize()` → `execute()` contract verbs.

---

## Claude Code Integration
<!-- last-verified: 2026-06-02 -->

### Scope Guidance

Use **`local` scope (default)** for Robinhood — the OAuth grant is personal and per-installation, so a per-user entry is the right default. The `project` scope commits only the server *config* to `.mcp.json` (URL, flags) — **not** the OAuth token, which Claude Code keeps in the system keychain. So a committed Robinhood entry leaks no credential; the actual security rule is *never commit a static token* (e.g. a static `Authorization` header or a `headersHelper` that emits one). See "Connection & Onboarding" above for the `claude mcp add` command.

### Permission Block (`settings.json`)

Configure Claude Code permissions to auto-allow the 8 read/simulate tools and require explicit human approval for the 2 write tools. This enforces HITL at the transport layer — **defense in depth complementary to the agent-loop gate**:

```json
{
  "permissions": {
    "allow": [
      "mcp__robinhood-trading__get_accounts",
      "mcp__robinhood-trading__get_portfolio",
      "mcp__robinhood-trading__get_equity_positions",
      "mcp__robinhood-trading__get_equity_quotes",
      "mcp__robinhood-trading__get_equity_orders",
      "mcp__robinhood-trading__get_equity_tradability",
      "mcp__robinhood-trading__review_equity_order",
      "mcp__robinhood-trading__search"
    ],
    "ask": [
      "mcp__robinhood-trading__place_equity_order",
      "mcp__robinhood-trading__cancel_equity_order"
    ]
  }
}
```

Rule evaluation order: `deny` → `ask` → `allow`. Deny rules win unconditionally.

**Maximum-caution alternative** (PoC / testing — asks on every call):
```json
{ "permissions": { "ask": ["mcp__robinhood-trading__*"] } }
```

### `alwaysLoad: true` — Load All 10 Tools at Session Start

By default, Claude Code uses Tool Search: MCP tools are deferred and loaded on demand. For a trading agent, this deferral adds latency at the moment of order placement. Add `alwaysLoad: true` in `.mcp.json` to load all 10 Robinhood tools into context at session start:

```json
{
  "mcpServers": {
    "robinhood-trading": {
      "type": "http",
      "url": "https://agent.robinhood.com/mcp/trading",
      "alwaysLoad": true
    }
  }
}
```

**Requires Claude Code v2.1.121+.** The tradeoff: 10 tool schemas consume context tokens at every session; with only 10 tools this is acceptable.

> **Safe to commit:** this `.mcp.json` block is **token-free** (URL + `alwaysLoad` only) — Robinhood's OAuth token lives in the keychain, not here — so sharing it leaks nothing. This does not contradict the `local`-scope default above: that default is about the per-user OAuth grant, not about hiding a secret.

### Auto-Reconnect Behavior

HTTP MCP connections can drop during long agent sessions. Claude Code auto-reconnects: up to 5 attempts, starting at 1 second, doubling each attempt (~30 seconds total before marking the server failed). During reconnect the server shows as `pending` in `/mcp`.

**Design implication:** multi-step order strategies should detect the `pending`/reconnect window and retry after reconnect rather than failing the whole sequence. An `Execution.status == "pending"` from `get_equity_orders` may indicate either an in-flight order or a reconnect in progress — distinguish by re-polling.

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
- Therefore the human-gate interceptor — `authorize()` returns `Approval{mode: "human_gate"}`, and your loop must block `execute()` until a human approves — has to be enforced in **your** agent loop / the provider plugin; do not rely on Robinhood to gate. For a PoC, default to `human_gate` on every `execute()` and only opt into `autonomous` behind an explicit, logged user decision.
- Load `agentic-sdks` for agent-loop / interceptor wiring patterns.
- **Make the gate durable, not a blocking prompt.** Do not gate with a bare `input()` — a process restart loses the pending approval. Use a durable interruption: e.g. the OpenAI Agents SDK marks the order tool `needs_approval=True`, surfaces `RunResult.interruptions`, and lets you serialize run state (`state.to_json()`) so the human can approve out-of-band and the run resumes from saved state. On rejection, discard the pending execution. This doubles as the boundary guard: the order tool is never reached until approval resolves.

---

## Core Verbs — Robinhood Implementation Shape

All six contract verbs are required. Tool names are now confirmed (2026-06-02); input schemas/params still require live `tools/list` introspection.

| Contract verb | Robinhood MCP tool(s) | Notes |
|---|---|---|
| `resolve_identity()` | `get_accounts` | Desktop onboarding grant to the Agentic account; broad read across ALL accounts, write only to the Agentic account; OAuth/scope internals opaque — inspect stored credential |
| `create_mandate(scope)` | (account setup, not an MCP tool) | Capital-segregated budget on the Agentic account; spend ceiling = the funds deposited; the "firewall from main portfolio" |
| `get_quote(target)` | `get_equity_quotes` + `review_equity_order` | Two-step: `get_equity_quotes` for market price (up to 20 symbols); `review_equity_order` for final pre-trade simulation and warnings before committing |
| `authorize(mandate, quote)` | `review_equity_order` | **Simulate the order; returns pre-trade warnings. Surface warnings to the human. Only proceed to `place_equity_order` after explicit approval.** This is the canonical HITL gate tool. Robinhood does not auto-gate — enforce `human_gate` in your own loop. |
| `execute(authorization)` | `place_equity_order` | Execute after human approval of `review_equity_order`; order-type enum not enumerated (introspect via `tools/list`) |
| `get_receipt(ref)` | `get_equity_orders` | Poll for order status + history after placement; fills arrive asynchronously |
| *(pre-check)* | `get_equity_tradability` | Verify symbol tradability + fractional eligibility before quoting |
| *(portfolio)* | `get_portfolio`, `get_equity_positions` | Portfolio value/buying power; open positions with quantity and cost basis |
| *(discovery)* | `search` | Find company name → ticker symbol |
| *(cancel)* | `cancel_equity_order` | Cancel an open order |

**Canonical two-step pattern:** `review_equity_order` (simulate, surface warnings) → human approval → `place_equity_order` (execute). Never call `place_equity_order` without first calling `review_equity_order` and obtaining explicit human approval.

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

**Now confirmed (2026-06-02):** MCP tool names (all 10 — see "Tool Surface" section above).

**Still undocumented — resolve operationally (introspect the live MCP server) before coding:**

| Specific | Status | Action |
|---|---|---|
| **MCP tool input schemas / parameter names** | Not published | `tools/list` against the live endpoint after `mcp add`; cross-ref `open-stocks-mcp` |
| **Order-type enum for `place_equity_order`** | "Different available order types" referenced, not enumerated | Read the linked order-types doc + confirm via the place-order tool schema from `tools/list` |
| **Rate limits** | Not published | Discover empirically / watch for MCP error responses; re-check docs |
| **OAuth scopes / token format** | Onboarding handles it; internals opaque | Inspect the client's stored MCP credential post-onboarding |
| **HITL triggering conditions** | User-configured, not system-enforced | Enforce `human_gate` in your own loop; do not depend on Robinhood |
| **Extended-hours trading** | Not documented in beta | Default `market_hours: "regular"`; verify |
| **Options / crypto support** | Long equities only in v1 beta; options on roadmap | Verify before expanding beyond long equities |

---

## Composition Notes

| Skill | Purpose |
|---|---|
| [`mcp-crafting`](../../mcp-crafting/SKILL.md) | MCP **client** wiring — HTTP transport config, `tools/list` introspection, MCP Inspector testing against `https://agent.robinhood.com/mcp/trading` |
| [`agentic-sdks`](../../agentic-sdks/SKILL.md) | Agent-loop integration — HITL interceptor wiring (enforced client-side), tool registration |
| [`agentic-interface-design`](../../agentic-interface-design/SKILL.md) | Tool-schema design quality — evaluate the introspected Robinhood tools' naming/error grammar |
| [`external-api-docs`](../../external-api-docs/SKILL.md) | Re-fetch current Robinhood docs before coding — the beta surface is churning |

**Explicit risk transfer:** Robinhood's docs state "Robinhood does not control, supervise, monitor, recommend, or audit these AI agents," and "You are ultimately responsible for the trades your AI agent places." The capital-segregated account + client-enforced HITL interceptor are the implementation-level mitigations — they **bound** this risk, they do not eliminate it.
