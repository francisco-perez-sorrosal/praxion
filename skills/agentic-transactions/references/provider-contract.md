# Provider Contract

Formal specification of the `Provider` contract — the language-independent,
provider-pluggable seam every agentic transaction implementation must satisfy.
Back-link: [../SKILL.md](../SKILL.md)

Conceptual overview lives in the skill body. This file carries the formal typed spec,
the complete error grammar, and a Python binding shape for PoC implementers.

---

## Formal Pseudotype Specification

```
Provider (common core — all six verbs required):
  resolve_identity()
      → AgentIdentity {
            principal   : str            # human-readable agent name / role
            agent_id    : str            # stable unique identifier for this agent
            credential  : str | bytes    # JWT / API key / on-chain address / MCP grant
            issuer      : str            # issuing authority (broker / chain / IdP / network)
            trust_root  : str            # root of the trust chain (CA / chain-id / wallet)
        }

  create_mandate(scope: MandateScope)
      → Mandate {
            max_amount     : Decimal        # spending ceiling (currency or asset units)
            currency_or_asset : str         # ISO 4217 code, ticker symbol, or on-chain asset ID
            constraints    : dict[str, Any] # provider-specific guardrails (e.g., symbol allowlist)
            time_window    : DateTimeRange  # validity window: { start: datetime, end: datetime }
            human_present  : bool           # whether a human approved this mandate interactively
            signature      : str | bytes    # provider-signed proof of mandate issuance
        }

  get_quote(target: QuoteTarget)
      → Quote {
            amount       : Decimal          # quoted price / cost in currency_or_asset units
            asset        : str             # what is being priced (ticker, USDC, item SKU…)
            expiry       : datetime        # quote validity deadline (UTC)
            transport    : str             # delivery mechanism hint (e.g., "MCP", "on-chain")
            instructions : dict[str, Any]  # provider-specific execution params for this quote
        }

  authorize(mandate: Mandate, quote: Quote, *, idempotency_key: str)
      → Approval {
            mode        : "autonomous" | "human_gate"
            decision    : "approved" | "denied"
            policy_ref  : str | None        # identifier of the policy / HITL record that decided
        }
  # idempotency_key: client-generated UUID; provider returns the same Approval on retry
  # HITL interceptor fires when mode == "human_gate" — provider surfaces a preview for
  # the user to approve before returning the Approval

  execute(authorization: Approval, *, idempotency_key: str)
      → Execution {
            status       : "pending" | "submitted" | "partial" | "filled" | "rejected" | "canceled"
            ref          : str              # provider-assigned execution reference (order ID / tx hash)
            finality     : "immediate" | "async" | "t+1" | "on-chain"
            rail_detail  : RailDetail | None    # present for payment-rail providers
            venue_detail : VenueDetail | None   # present for trading-venue providers
        }
  # idempotency_key: same key as authorize; provider returns same Execution on retry

  get_receipt(ref: str)
      → Receipt {
            execution_ref : str             # mirrors Execution.ref
            mandate_ref   : str             # mirrors Mandate.signature or a provider-assigned ID
            signed_proof  : str | bytes     # provider-signed proof of execution (tx hash / order confirm)
            timestamp     : datetime        # execution timestamp (UTC)
        }
```

**Security — enforce `Mandate.max_amount` and `constraints` at the tool/transport boundary, not in the prompt.** The provider plugin (or its MCP-tool wrapper) MUST reject any `execute()` whose amount or target violates the signed mandate *before* the order/payment reaches the venue — a deterministic check outside the model. Treat the LLM's grasp of the spend limit as advisory only: adversarial "limit-bypass" via semantic manipulation succeeds against weaker models at high rates (FinVault, arXiv:2601.07853, 2026-01). `authorize()` decides; the boundary check is what actually enforces.

---

## TransactionError Grammar
<!-- last-verified: 2026-06-02 -->

A **closed** set of error codes. Every provider raises only errors from this set; no
provider-specific additions are permitted at the grammar level. Rail-specific or
venue-specific decline / revert detail is carried in `rail_detail` / `venue_detail`.

```
TransactionError {
    code              : ErrorCode       # one of the eight codes below (closed enum)
    message           : str            # human-readable explanation
    retriable         : bool           # True = safe to retry with same idempotency_key
    step_up_required  : bool           # True = human approval needed before retrying
    detail            : dict[str, Any] # provider-supplied context (rail_detail / venue_detail on error)
}

ErrorCode (closed enum):
    identity_failed               # resolve_identity() could not authenticate the agent
    mandate_denied                # create_mandate() rejected — policy violation or limit exceeded
    quote_expired                 # get_quote() result is past its expiry; call get_quote() again
    approval_required             # HITL gate intercepted authorize(); human must approve
    insufficient_funds_or_buying_power   # execute() rejected — account balance / buying power too low
    execution_rejected            # execute() rejected by provider (order type, market rules, etc.)
    finality_pending              # async execution has not settled; call get_receipt() later
    provider_unavailable          # provider is unreachable or in maintenance; retriable after backoff
```

**Error-handling contract:**
- `retriable: True` + `step_up_required: False` → retry with exponential backoff using
  the **same** `idempotency_key`.
- `retriable: True` + `step_up_required: True` → surface `approval_required` to the
  human-in-the-loop before retrying.
- `retriable: False` → do not retry; log and surface to the orchestrator.

**`provider_unavailable` and MCP connection failures:** this code maps to MCP transport
failures — connection timeout, auto-reconnect exhaustion (5 attempts × exponential backoff
≈ 30 seconds), or circuit-open state. For `retriable: True` on the MCP client side,
apply a **bounded exponential backoff** (e.g. base 1s, factor 2×, max 5 attempts, jitter)
before declaring the provider unavailable. Do not retry indefinitely — set an outer timeout
budget proportional to your strategy's latency tolerance. On exhaustion, surface
`provider_unavailable` with `retriable: False` to the orchestrator.

---

## Declared Optional Capabilities

A provider's plugin descriptor declares which optional capabilities it supports. The
common core never calls an optional operation without first checking the capability flag.

```
CapabilityDescriptor {
    supports_sandbox      : bool    # paper-trading / testnet / dry-run mode available
    supports_market_data  : bool    # get_market_data() is implemented
    supports_positions    : bool    # list_positions() is implemented
    approval_mode         : "autonomous" | "human_gate" | "hybrid"   # provider CAPABILITY: which modes it supports ("hybrid" = supports per-call choice). NOT a per-call value — each Approval.mode is only "autonomous" or "human_gate".
    transport_kind        : "mcp-client" | "http-sdk-client"
}

Optional operations (implement only when declared in CapabilityDescriptor):
    get_market_data(symbol, timeframe?)  → MarketSnapshot { bid, ask, last, volume, bars? }
    list_positions()                     → list[Position]  { symbol, qty, cost_basis, unrealized_pnl }
    list_orders(status?)                 → list[Order]     { ref, symbol, side, qty, status, fills }
    cancel(ref)                          → CancelResult    { ref, status }
    replace(ref, updates)               → Execution        # same shape as execute()
```

---

## Transport Strategies

Two strategies govern how the agent reaches the provider at runtime.

**`mcp-client`** — the agent calls the provider's own MCP server via the MCP protocol.
No REST SDK needed. The provider exposes its operations as MCP tools. Robinhood is
MCP-only; Alpaca, Visa, PayPal, Stripe, and Nevermined also ship MCP servers.

```python
# MCP-client wiring — official `mcp` Python SDK (pip install mcp>=1.26.0, Python >=3.10).
# Streamable HTTP is the current transport; do NOT copy older HTTP+SSE examples.
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    provider_config.mcp_endpoint,                      # e.g. https://agent.robinhood.com/mcp/trading
    headers={"Authorization": f"Bearer {token}"},      # remote-server auth (OAuth/bearer)
) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()                     # REQUIRED before any list/call
        tools = await session.list_tools()             # introspect the provider's tool surface
        result = await session.call_tool(
            "execute", {"authorization": auth, "idempotency_key": key},
        )
# Confirm exact tool names/args against the live tools/list — they are provider-defined.
```

**`http-sdk-client`** — direct REST or language-SDK call. Suitable when the provider
has a mature SDK and no MCP server, or when the SDK exposes capabilities the MCP server
does not.

```python
# HTTP/SDK-client wiring sketch — Alpaca example shape
client = TradingClient(api_key=key, secret_key=secret, paper=provider.supports_sandbox)
order = await client.submit_order(OrderRequest(...))
```

The `transport_kind` capability flag declares which strategy the plugin uses. The agent
must not assume a transport; it must read the provider's `CapabilityDescriptor`.

---

## `rail_detail` and `venue_detail` Extension Fields

These typed fields on `Execution` and `Receipt` localize all divergence that cannot be
represented in the common core. The core never encodes finality semantics; they ride here.

```
RailDetail {                          # payment-rail providers (Space A)
    finality      : "immediate" | "t+1" | "on-chain" | "async"
    reversibility : bool              # False = irreversible (on-chain, Lightning)
    chain_params  : dict | None       # present for on-chain rails: chain_id, gas, tx_hash
    decline_code  : str | None        # card-network or issuer decline code
}

VenueDetail {                         # trading-venue providers (Space B)
    market_hours  : str               # "regular" | "extended" | "closed"
    order_type    : str               # "market" | "limit" | "stop" | "stop_limit" | …
    partial_fills : bool              # True if this execution is a partial fill
    fills_async   : bool              # True if additional fills may arrive asynchronously
    filled_qty    : Decimal | None    # quantity filled in this execution event
    avg_price     : Decimal | None    # average fill price (None for pending orders)
}
```

**Design rationale:** a future provider that differs from Robinhood only in order types
or chain parameters requires no change to the common core — only a new plugin descriptor
and a new `references/<provider>.md`.

---

## Python Binding Shape

> **Label: Python binding shape — implement in PoC.**
> This is a structural sketch, not production code. Implement it in the downstream PoC
> using `alpaca-py`, `httpx`, or an MCP SDK as appropriate. Load `mcp-crafting` and
> `agentic-sdks` skills for runtime wiring patterns.

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime
from typing import Any, Literal

# -- value types (replace with Pydantic models in the PoC) --

class AgentIdentity:
    principal: str; agent_id: str; credential: str | bytes
    issuer: str; trust_root: str

class MandateScope:
    max_amount: Decimal; currency_or_asset: str
    constraints: dict[str, Any]; time_window: tuple[datetime, datetime]
    human_present: bool

class Mandate:
    max_amount: Decimal; currency_or_asset: str
    constraints: dict[str, Any]; time_window: tuple[datetime, datetime]
    human_present: bool; signature: str | bytes

class QuoteTarget:
    symbol_or_item: str; quantity: Decimal; side: str  # "buy" | "sell" | "pay"

class Quote:
    amount: Decimal; asset: str; expiry: datetime
    transport: str; instructions: dict[str, Any]

class Approval:
    mode: Literal["autonomous", "human_gate"]
    decision: Literal["approved", "denied"]
    policy_ref: str | None

class Execution:
    status: Literal["pending","submitted","partial","filled","rejected","canceled"]
    ref: str; finality: str
    rail_detail: dict | None; venue_detail: dict | None

class Receipt:
    execution_ref: str; mandate_ref: str
    signed_proof: str | bytes; timestamp: datetime

class TransactionError(Exception):
    code: str; message: str; retriable: bool
    step_up_required: bool; detail: dict[str, Any]

# -- provider contract (ABC) --

class Provider(ABC):
    """Abstract base — every provider plugin implements these six methods."""

    @abstractmethod
    async def resolve_identity(self) -> AgentIdentity: ...

    @abstractmethod
    async def create_mandate(self, scope: MandateScope) -> Mandate: ...

    @abstractmethod
    async def get_quote(self, target: QuoteTarget) -> Quote: ...

    @abstractmethod
    async def authorize(
        self, mandate: Mandate, quote: Quote, *, idempotency_key: str
    ) -> Approval: ...

    @abstractmethod
    async def execute(
        self, authorization: Approval, *, idempotency_key: str
    ) -> Execution: ...

    @abstractmethod
    async def get_receipt(self, ref: str) -> Receipt: ...
```
