# [PROVIDER NAME] Trading/Payment Provider

> **Instructions:** Copy this file to `references/<new-provider>.md` and fill in all
> bracketed fields before adding the provider. Remove all instruction blocks (lines
> beginning with `>`). Consult `references/provider-contract.md` for the formal
> pseudotype spec before filling in the Core Verbs table.
>
> Before writing any integration code, run `chub_search({ query: "[PROVIDER NAME]" })`
> via the `external-api-docs` skill. Fetch any available curated docs; mark every
> volatile field "VERIFY AT USE TIME" regardless of search outcome.

Back-link: [../SKILL.md](../SKILL.md)

---

## Provider Identity

| Field | Value |
|---|---|
| **Provider name** | [PROVIDER NAME] |
| **Status** | [STATUS — e.g., GA / beta / alpha; launch date if known] |
| **Transport kind** | [TRANSPORT KIND — `mcp-client` or `http-sdk-client`] |
| **Asset class** | [ASSET CLASS — e.g., equities, crypto, stablecoins, general payments] |
| **Space** | [SPACE — `A` (payments) or `B` (trading)] |
| **`supports_sandbox`** | [`true` or `false`] |
| **Geographic scope** | [GEOGRAPHIC SCOPE] |
| **Access gate** | [ACCESS GATE — e.g., API key, OAuth, waitlist, paid tier] |

---

## `supports_sandbox` Guardrails

> Fill this section based on the value of `supports_sandbox` above.

### If `supports_sandbox: false` (live-only provider)

> Copy the guardrails block from `robinhood.md` and adapt it. The two mandatory
> guardrails are: (1) capital-segregated agentic account / budget mandate, and
> (2) HITL approval interceptor. Both are required when the provider is live-only.

**[DESCRIBE THE CAPITAL-SEGREGATED BUDGET MANDATE FOR THIS PROVIDER]**

**[DESCRIBE THE HITL APPROVAL INTERCEPTOR WIRING FOR THIS PROVIDER]**

### If `supports_sandbox: true`

**Sandbox / paper-trading:** [DESCRIBE HOW TO ENABLE — e.g., set `paper=True`, use
testnet API endpoint, configure sandbox API keys separately.]

---

## Core Verbs — [PROVIDER NAME] Implementation Shape

| Contract verb | [PROVIDER NAME] mapping | Notes |
|---|---|---|
| `resolve_identity()` | [HOW THIS PROVIDER AUTHENTICATES THE AGENT] | [AUTH SCOPES / TOKEN FORMAT — verify at use time if undocumented] |
| `create_mandate(scope)` | [HOW THIS PROVIDER REPRESENTS THE SPENDING MANDATE] | [MANDATE CONSTRAINTS] |
| `get_quote(target)` | [HOW THIS PROVIDER RETURNS A QUOTE] | [QUOTE EXPIRY / VOLATILITY] |
| `authorize(mandate, quote)` | [HOW APPROVAL WORKS; NOTE HITL IF APPLICABLE] | [`autonomous` or `human_gate` mode] |
| `execute(authorization)` | [HOW ORDERS / PAYMENTS ARE PLACED] | [ASYNC BEHAVIOR, PARTIAL FILLS IF TRADING] |
| `get_receipt(ref)` | [HOW EXECUTION CONFIRMATIONS ARE RETRIEVED] | [RECEIPT FORMAT] |

**Extension defaults:**

> Fill whichever extension applies (trading → `venue_detail`; payments → `rail_detail`).
> Delete the inapplicable block.

```python
# Trading-venue (Space B) defaults
VenueDetail(
    market_hours = "[regular | extended | 24h — verify]",
    order_type   = "[market | limit | stop — verify]",
    partial_fills = [True | False],
    fills_async   = [True | False],
)

# Payment-rail (Space A) defaults
RailDetail(
    finality      = "[immediate | t+1 | on-chain | async — verify]",
    reversibility = [True | False],
    chain_params  = [None | { "chain_id": "...", ... }],
)
```

---

## Declared Optional Capabilities

> Check the box for each capability this provider implements. Remove unchecked rows.

| Capability | Supported | Notes |
|---|---|---|
| `supports_market_data` | [ ] Yes / [ ] No | [If yes: describe `get_market_data()` shape] |
| `supports_positions` | [ ] Yes / [ ] No | [If yes: describe `list_positions()` shape] |
| `OrderLifecycle` | [ ] Yes / [ ] No | [If yes: describe `list_orders()` / `cancel()` / `replace()` support] |

---

## Volatile Specifics
<!-- last-verified: [YYYY-MM-DD] -->

> **VERIFY AT USE TIME via `external-api-docs` skill** — mark every item below with its
> current documentation status. Use the boilerplate phrase "undocumented as of [DATE]"
> for items with no public docs. Never bake frozen values from this file into production
> code.

| Specific | Status | Action |
|---|---|---|
| **Auth scopes / token format** | [documented / undocumented as of YYYY-MM-DD] | Verify at use time via `external-api-docs` |
| **Rate limits** | [documented / undocumented as of YYYY-MM-DD] | Verify at use time via `external-api-docs` |
| **API / MCP endpoint URL** | [documented / undocumented as of YYYY-MM-DD] | Verify at use time via `external-api-docs` |
| **Order types** (trading) | [documented / undocumented as of YYYY-MM-DD] | Verify at use time via `external-api-docs` |
| **Settlement finality** (payments) | [documented / undocumented as of YYYY-MM-DD] | Verify at use time via `external-api-docs` |
| [ADD MORE ROWS AS NEEDED] | | |

---

## Composition Notes

| Skill | Purpose |
|---|---|
| [`mcp-crafting`](../../mcp-crafting/SKILL.md) | MCP client wiring (if `transport_kind: mcp-client`) |
| [`agentic-sdks`](../../agentic-sdks/SKILL.md) | Agent loop integration and HITL wiring |
| [`agentic-interface-design`](../../agentic-interface-design/SKILL.md) | Tool-schema design quality |
| [`external-api-docs`](../../external-api-docs/SKILL.md) | Fetch current provider documentation |
