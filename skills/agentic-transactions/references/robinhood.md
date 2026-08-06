# Robinhood Trading Provider

v1 plugin shape for the Robinhood Agentic Trading provider — MCP transport (HTTP),
**long equities and options**, **no sandbox**.
Back-link: [../SKILL.md](../SKILL.md)

> **State of knowledge (verified 2026-08-05 against Robinhood's official support docs).**
> The connection surface is public: the MCP endpoint URL, the HTTP transport, the connect
> command, and the desktop-only onboarding/auth flow are all documented (below). **Tool
> *names* are published** — but this document deliberately states no count, because the one it
> stated last time was wrong within the re-verification window. **Options trading is live.**
> What is **still not published**: the MCP **tool input schemas / parameter names**, the
> **order-type enum**, **rate limits**, and the OAuth/token internals. The way to resolve
> those is **operational, not documentary** — connect an MCP client to the live endpoint
> and **introspect its tool list** (`tools/list`), then read the linked order-types doc.
> Re-run `chub_search({ query: "robinhood trading" })` via `external-api-docs` before
> coding in case curated docs have since appeared.
>
> **This surface moves fast** — 10 → ~50 tools plus a whole asset class in ~64 days. No
> re-verification cadence tracks that: the surface moved *inside* the 60-day threshold meant
> to catch it. So this document asserts no inventory at all — it gives you a classification
> rule and tells you to introspect. Shortening the threshold would have been the comfortable
> fix and would have changed nothing.

---

## Provider Identity

| Field | Value |
|---|---|
| **Provider name** | Robinhood Agentic Trading |
| **Status** | Beta — launched 2026-05-27; staged rollout via email invite; Gold members prioritized |
| **Transport kind** | `mcp-client` over **HTTP** (streamable HTTP MCP) |
| **MCP endpoint** | `https://agent.robinhood.com/mcp/trading` |
| **Asset class** | **Long equities and options** — options shipped since the v1-beta notes; still no shorts, crypto, or futures. Verbatim: "You currently can use your agent to place long equities and options orders" |
| **`supports_sandbox`** | **`false`** — no paper-trading or testnet environment (confirmed absent) |
| **Geographic scope** | US-only (implied); desktop required for onboarding |
| **Access gate** | Primary individual investing account in good standing; up to 10 self-directed individual accounts incl. the Agentic account; email-invite rollout |
| **Official docs** | `robinhood.com/us/en/support/agentic-trading` and the `agentic-trading-overview` support article |

---

## Connection & Onboarding (verified 2026-08-05)

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

**First step for any implementer:** after `mcp add`, run an MCP `tools/list` against the endpoint to enumerate the actual tool **input schemas** and parameter names. That one call gives you both the names and the schemas; this document classifies what it returns rather than listing it (see "Tool Surface" below). Cross-check against the community reference implementation [`Open-Agent-Tools/open-stocks-mcp`](https://github.com/Open-Agent-Tools/open-stocks-mcp) (multi-broker Robinhood/Schwab MCP) for shape, but verify against the live first-party endpoint.

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

## Tool Surface — classification, not inventory
<!-- last-verified: 2026-08-05 -->

> **This section deliberately does not enumerate the tool surface.** It once listed 10 tools
> and named `place_equity_order` as the only write-side placement tool. In about 64 days the
> surface grew roughly 5× and options trading shipped, making `place_option_order` a second
> capital-moving tool outside every gate derived from that list. An inventory of a beta
> vendor surface is wrong faster than any re-verification cadence can catch, and it is not
> even actionable on its own: input schemas, parameter names and the order-type enum are
> unpublished, so **you must introspect the live server regardless**.

**Resolve the surface operationally — `tools/list` against the live endpoint after `mcp add`.**
That is the only authoritative answer, and it is current by construction.

What this document keeps instead is the part that does not rot: **how to classify whatever
`tools/list` returns.** A classification is a rule for sorting, so a tool added tomorrow is
sorted by it rather than falsifying it. When this surface last moved, every negative claim
here held and every positive enumeration went stale — that asymmetry is the reason for the
split.

### The classification — apply it to whatever `tools/list` returns

Sort by **what a call can cost you**, not by read-vs-write. Robinhood's naming has been
consistent across every surface change so far, so the class is derivable from the name:

| Name pattern | Class | Gate |
|---|---|---|
| `place_<asset>_order` | **Capital-moving** — executes | Requires human approval. Never callable directly by the agent loop |
| `cancel_<asset>_order` | **Capital-moving** — changes execution outcome | Requires human approval; leaving an order open or cancelling it are both money decisions |
| `review_<asset>_order` | **Simulate** — pre-trade warnings | The HITL gate primitive. Safe to call unattended; it is what you show the human |
| `get_*`, `search` | Read | Unrestricted |
| any other mutating verb (`create_*`, `update_*`, `add_*`, `remove_*`, `follow_*`, `unfollow_*`, `run_*`) | **State-mutating, non-capital** | Allow deliberately, not by default — see below |

**Gate on the pattern, never on an enumerated pair.** This is the lesson the options launch
taught at cost: a gate written as "`place_equity_order` and `place_option_order`" is correct
until the next asset class ships, and then it is silently incomplete — the failure mode is
real money moving through an ungated path, and nothing in the system announces it. A gate
written against `place_*_order` covers the next asset class on the day it appears. Same for
`cancel_*_order` and `review_*_order`.

**The canonical two-step HITL gate**, stated the durable way:

> `review_<asset>_order` → human approval → `place_<asset>_order`, for **every** `<asset>`
> the live surface exposes — enumerate `<asset>` from `tools/list` at wiring time, not from
> this document.

That pair is the tool-level implementation of the `authorize()` → `execute()` contract verbs.

**The non-capital mutators are the class most allow-lists miss.** They are not reads, so a
rule built as "everything that isn't a `place_*`" silently authorizes them. They move no
money, but they change account state the user did not ask the agent to touch.

**Crypto is not in the tool surface** (as of the last verification). Press coverage has
reported crypto agentic trading; the primary source lists no crypto *trading* tool — crypto
appears only in watchlist tools — and says only "we'll be adding support for more assets
soon." Do not encode crypto support. Note that this is a **negative** claim, the durable
kind: if it ever becomes false, a `place_crypto_order` will appear in `tools/list` and the
pattern gate above will already cover it.

---

## Claude Code Integration
<!-- last-verified: 2026-08-05 -->

### Scope Guidance

Use **`local` scope (default)** for Robinhood — the OAuth grant is personal and per-installation, so a per-user entry is the right default. The `project` scope commits only the server *config* to `.mcp.json` (URL, flags) — **not** the OAuth token, which Claude Code keeps in the system keychain. So a committed Robinhood entry leaks no credential; the actual security rule is *never commit a static token* (e.g. a static `Authorization` header or a `headersHelper` that emits one). See "Connection & Onboarding" above for the `claude mcp add` command.

### Permission Block (`settings.json`)

**State the policy as a rule, not as an enumeration.** On a surface that grew 5× in two
months, any hand-listed allow-list is stale on arrival. The rule that survives
expansion:

> Every `place_*` and `cancel_*` tool goes in `ask`. Everything else may be allowed — but
> re-check new `create_*` / `update_*` / `run_*` tools before adding them, because those
> mutate account state even though they move no capital.

```json
{
  "permissions": {
    "ask": [
      "mcp__robinhood-trading__place_equity_order",
      "mcp__robinhood-trading__place_option_order",
      "mcp__robinhood-trading__cancel_equity_order",
      "mcp__robinhood-trading__cancel_option_order"
    ],
    "allow": [
      "mcp__robinhood-trading__get_accounts",
      "mcp__robinhood-trading__get_portfolio",
      "mcp__robinhood-trading__get_equity_positions",
      "mcp__robinhood-trading__get_equity_quotes",
      "mcp__robinhood-trading__get_equity_orders",
      "mcp__robinhood-trading__get_equity_tradability",
      "mcp__robinhood-trading__review_equity_order",
      "mcp__robinhood-trading__review_option_order",
      "mcp__robinhood-trading__search"
    ]
  }
}
```

Rule evaluation order: `deny` → `ask` → `allow`. Deny rules win unconditionally, and a
matching `ask` prompts even when a more specific `allow` also matches — so listing the four
capital-moving tools under `ask` holds regardless of what else is allowed.

**An unlisted tool is safe by default but the block is not self-documenting.** Claude Code
prompts for any tool matching no rule, so an omitted `place_option_order` would still ask —
the failure direction is safe. The hazard is a wildcard: `mcp__robinhood-trading__get_*` in
`allow` reads as harmless but pairs badly with a surface where new mutators keep appearing.
If you wildcard anything, keep the four `ask` entries explicit.

The maximum-caution alternative — `ask` on `mcp__robinhood-trading__*` — is now considerably
more attractive than it was at 10 tools.

**Maximum-caution alternative** (PoC / testing — asks on every call):
```json
{ "permissions": { "ask": ["mcp__robinhood-trading__*"] } }
```

### `alwaysLoad: true` — Load the Whole Tool Surface at Session Start

By default, Claude Code uses Tool Search: MCP tools are deferred and loaded on demand. For a trading agent, this deferral adds latency at the moment of order placement. Adding `alwaysLoad: true` in `.mcp.json` loads the Robinhood tools into context at session start:

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

**Requires Claude Code v2.1.121+.**

**The cost judgment that justified this has expired.** It read "10 tool schemas consume
context tokens at every session; with only 10 tools this is acceptable." After a 5× expansion
that is roughly 5× the cost, and it now cuts against the docs' own guidance: use `alwaysLoad` "for a
small number of tools that Claude needs on every turn, since each upfront tool consumes
context that would otherwise be available for your conversation." Fifty schemas is not a
small number.

Two further properties to weigh, both against the latency argument that motivates it:

- **`alwaysLoad: true` blocks startup until the server connects**, capped at the standard
  5-second connect timeout. For a trading agent that is a real availability trade, not just a
  token cost — you are trading order-placement latency for session-start latency.
- Per-tool always-loading (`"anthropic/alwaysLoad": true` in a tool's `_meta`) is
  **server-side**, so a Robinhood consumer cannot select a subset. The choice is all-or-defer.

Given that, prefer the default (deferred) unless you have measured the placement latency and
found it unacceptable.

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

All six contract verbs are required. Tool names verified 2026-08-05; input schemas/params still require live `tools/list` introspection.

**This table maps the equities path.** Options are live and follow the same shape with the
parallel tool family — substitute `get_option_quotes` → `review_option_order` →
`place_option_order` → `get_option_orders`, with `cancel_option_order` for cancels and
`get_option_chains` / `get_option_instruments` for contract discovery. Note
`get_option_level_upgrade_info` has no equities analogue: options trading requires an
approval level on the account, so check it before assuming an options order can be placed.

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

**Canonical two-step pattern:** `review_*_order` (simulate, surface warnings) → human approval
→ `place_*_order` (execute). Never call a `place_*` tool without first calling its matching
`review_*` tool and obtaining explicit human approval. This holds per asset class: the
equities pair does not gate options, and vice versa.

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
<!-- last-verified: 2026-08-05 -->

**Now known (verified 2026-08-05):** MCP endpoint URL, HTTP transport, connect command, desktop-only onboarding/auth flow, read/write access scope, no-sandbox, eligibility, HITL-is-not-system-enforced. Reflected above.

**No longer asserted here:** the tool inventory. It was recorded as 10 tools, was ~50 about
64 days later, and is now resolved operationally via `tools/list` — see "Tool Surface" above
for the classification that replaced it.

> **Note which claims rotted, and why this document is shaped the way it is.** Both *positive*
> assertions in this section went stale ("all 10 tools", "options on roadmap") while **every**
> "still undocumented" row below held. Negative claims about this surface are cheap and
> durable; positive enumerations decay fast and cannot be rescued by a shorter re-verification
> cadence — the surface moved inside the threshold that was supposed to catch it. The response
> was to stop asserting the decaying thing rather than to re-verify it more often: keep the
> negative claims, keep the classification rule, and derive the inventory at wiring time.

**Still undocumented — resolve operationally (introspect the live MCP server) before coding:**

| Specific | Status | Action |
|---|---|---|
| **MCP tool input schemas / parameter names** | Not published | `tools/list` against the live endpoint after `mcp add`; cross-ref `open-stocks-mcp` |
| **Order-type enum for `place_equity_order`** | "Different available order types" referenced, not enumerated | Read the linked order-types doc + confirm via the place-order tool schema from `tools/list` |
| **Rate limits** | Not published | Discover empirically / watch for MCP error responses; re-check docs |
| **OAuth scopes / token format** | Onboarding handles it; internals opaque | Inspect the client's stored MCP credential post-onboarding |
| **HITL triggering conditions** | User-configured, not system-enforced | Enforce `human_gate` in your own loop; do not depend on Robinhood |
| **Extended-hours trading** | Not documented in beta | Default `market_hours: "regular"`; verify |
| **Asset classes** | Equities and long options shipped; "we'll be adding support for more assets soon" | Do not enumerate. Gate `place_*_order` / `cancel_*_order` by pattern so the next asset class is covered on arrival — this row is expected to go stale and is designed not to matter when it does |
| **Crypto support** | **Not in the tool surface.** Primary source lists no crypto trading tool; "we'll be adding support for more assets soon". Press reports of crypto agentic trading are not primary-confirmed | Do not encode crypto support; re-check the support article directly |

---

## Composition Notes

| Skill | Purpose |
|---|---|
| [`mcp-crafting`](../../mcp-crafting/SKILL.md) | MCP **client** wiring — HTTP transport config, `tools/list` introspection, MCP Inspector testing against `https://agent.robinhood.com/mcp/trading` |
| [`agentic-sdks`](../../agentic-sdks/SKILL.md) | Agent-loop integration — HITL interceptor wiring (enforced client-side), tool registration |
| [`agentic-interface-design`](../../agentic-interface-design/SKILL.md) | Tool-schema design quality — evaluate the introspected Robinhood tools' naming/error grammar |
| [`external-api-docs`](../../external-api-docs/SKILL.md) | Re-fetch current Robinhood docs before coding — the beta surface is churning |

**Explicit risk transfer:** Robinhood's docs state "Robinhood does not control, supervise, monitor, recommend, or audit these AI agents," and "You are ultimately responsible for the trades your AI agent places." The capital-segregated account + client-enforced HITL interceptor are the implementation-level mitigations — they **bound** this risk, they do not eliminate it.
