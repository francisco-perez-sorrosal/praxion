# Low-Latency Interface Ergonomics

The latency-conscious API designer models specific costs and minimizes them. This file covers the concrete toolkit: payload design, N+1 elimination, caching, connection reuse, streaming decisions, and round-trip cost modeling. Back to [SKILL.md](../SKILL.md).

## Payload Shape and Size

**Never return unbounded collections.** Every list endpoint must be paginated with a small default page size. "Works fine in dev, OOMs in prod" is the most common API failure mode.

Default page sizes:
- Human-facing: 20–50 items
- Agentic tools: 10–20 items (preserve reasoning budget)

**Sparse fieldsets / field masks.** Allow callers to request only the fields they need:

| API style | Mechanism | Example |
|-----------|-----------|---------|
| REST | Query parameter | `?fields=id,name,email,created_at` |
| GraphQL | Native (field selection) | `{ users { id name email } }` |
| gRPC | `google.protobuf.FieldMask` | `read_mask.paths = ["id", "name"]` |

A user list endpoint that returns 40 fields per user when the consumer needs 3 wastes bandwidth and CPU on every request.

**Compression.** Enable `gzip`/`brotli` for payloads over 1KB. Negotiate via `Accept-Encoding`. Worth enabling by default — the compression overhead is minimal compared to the bandwidth savings for text-based APIs.

**Binary formats.** For internal high-throughput services: Protocol Buffers or MessagePack beat JSON by:
- 2–5x on payload size
- 5–10x on parse time

Not worth the complexity for public APIs or human-readable responses. Absolutely worth it at 10K+ requests/second over internal networks.

## N+1 Elimination

N+1 is the most common API latency antipattern. The API *designer* is responsible — not just the backend engineer. N+1 most often happens because the API shape forces multiple requests to assemble a view.

### The Expansion Pattern (Stripe Model)

```
# Without expansion: caller makes N+1 requests
GET /orders → [{ id: "ord_1", customer_id: "cus_abc" }, ...]
GET /customers/cus_abc → { name, email, address }
GET /customers/cus_def → ...
(N customer fetches for N orders)

# With expansion: one request
GET /orders?expand[]=customer
→ [{ id: "ord_1", customer: { name, email, address } }, ...]
```

Implementation: the `expand[]` parameter triggers a JOIN or secondary fetch in the handler. The default response stays lean; expansion is opt-in.

### The Includes Pattern (JSON:API)

```
GET /orders?include=customer,items

Response:
{
  "data": [{ "type": "order", "id": "ord_1", "relationships": { "customer": {...}, "items": {...} } }],
  "included": [
    { "type": "customer", "id": "cus_abc", ... },
    { "type": "item", "id": "itm_1", ... }
  ]
}
```

Related resources in a top-level `included` array — avoids duplication when the same resource is referenced by multiple primary resources.

### DataLoader Pattern (GraphQL)

The schema structure encourages N+1 but the execution layer batches:

```javascript
const customerLoader = new DataLoader(async (ids) =>
  db.customers.findManyByIds(ids)
    .then(cs => ids.map(id => cs.find(c => c.id === id)))
)
// DataLoader collects all customer IDs from a single query execution
// and resolves them in one database round-trip
```

**Design rule**: if your schema allows fetching nested resources from a list, you must plan DataLoader from the start. Adding it after launch is expensive.

## Caching

Every `GET` endpoint needs an explicit caching policy. "Default browser cache" is not a policy.

### Caching Decision Table

| Resource type | Caching approach | Cache-Control value |
|---------------|-----------------|---------------------|
| Static reference data (country list, config) | Long-lived CDN cache | `public, max-age=86400, stale-while-revalidate=3600` |
| User-specific data | Short-lived private cache + validation | `private, max-age=60, must-revalidate` |
| Frequently changing data | Validation only (ETag) | `private, no-cache` + `ETag` header |
| Sensitive data (PII, financial) | Never cache | `no-store, private` |

### ETag + Conditional GET

The most important caching pattern for changing resources:

```
# First request
GET /orders/123
← 200 OK
← ETag: "etag_abc123"
← Cache-Control: private, no-cache

# Subsequent request (client sends the ETag)
GET /orders/123
→ If-None-Match: "etag_abc123"
← 304 Not Modified  (if unchanged — zero response body)

# If changed
← 200 OK
← ETag: "etag_xyz789"  (new ETag)
```

The 304 response has no body — saves the full payload transfer cost when the resource hasn't changed. Essential for polling patterns.

### `Vary` Header

Signal which request headers affect the response — required for correct CDN behavior:

```
Vary: Accept-Encoding, Authorization
```

Without `Vary: Authorization`, a CDN might serve one user's authenticated response to another user.

## Connection Reuse
<!-- last-verified: 2026-05-12 -->

Each new TCP connection incurs a handshake cost (1–3 RTTs). Avoiding new connections is significant latency optimization.

| Protocol | Connection model | Design guidance |
|----------|-----------------|-----------------|
| HTTP/1.1 | Keep-alive by default | Ensure server doesn't close aggressively; max requests per connection matters |
| HTTP/2 | Multiplexed on one TCP connection | Multiple concurrent requests on one connection; no head-of-line blocking |
| gRPC | Persistent HTTP/2 channel | Pool channels for high-throughput; never create per-RPC channels |

**Client-side**: configure connection pool max-idle and max-total to match the load profile. Libraries: `httpx` (Python), `got`/`undici` (Node.js), `net/http` (Go).

**Server-side**: configure `keepalive_timeout` to be long enough for clients to reuse connections but short enough to avoid resource exhaustion.

## Streaming Responses

| Pattern | Use case | Latency characteristic |
|---------|----------|----------------------|
| Chunked transfer (HTTP/1.1) | Large exports, progressive rendering, log streaming | First-byte fast; total time = full operation |
| Server-Sent Events (SSE) | Server-to-client push, real-time updates, LLM token streaming | Persistent connection; first-event fast |
| gRPC server streaming | High-frequency updates, large data transfers | Lowest overhead for high-frequency events |
| WebSocket | Full-duplex real-time (chat, collaboration) | Persistent connection; first message fast |

**When streaming is right:**
- Producer generates data faster than the consumer can absorb (backpressure needed)
- Consumer wants to start processing before the response is complete (LLM tokens, progressive rendering)
- First-byte latency matters more than end-to-end latency (user sees progress)

**When streaming is wrong:**
- Response is small and bounded (chunked transfer adds protocol overhead for no benefit)
- Client needs the complete response before doing anything (atomic JSON operations)
- The added complexity isn't justified by the use case

## Chattiness Cost vs. Over-Fetch Cost

The latency designer models both costs and finds the minimum:

**Chattiness cost** = round-trip latency × number of requests

Each HTTP round-trip: 50–200ms (depending on geography, connection type). 

| Number of requests | Minimum latency from round-trips |
|-------------------|----------------------------------|
| 1 | 50–200ms |
| 5 | 250ms–1s |
| 10 | 500ms–2s |
| 20 | 1s–4s |

This is before any processing time. A mobile app that makes 20 sequential API calls has 1–4 seconds of round-trip overhead regardless of server speed.

**Over-fetch cost** = extra payload bytes × (transfer time + parse time)

Returning 100 fields when 3 are needed: wasted bandwidth, wasted CPU on serialization/deserialization, wasted context (especially for agentic consumers).

**The optimum**: fewer, slightly larger requests with field selection. This is why the expansion pattern, compound responses, and sparse fieldsets exist — they solve chattiness and over-fetch simultaneously.

## For Agentic Tools: Minimize Inference Turns

An agent's "latency" is measured in model inference turns, not milliseconds. Each tool call is a complete inference cycle (expensive in both time and tokens).

Design rule: **if the agent will almost always need X after getting Y, return X alongside Y in the first call.**

```python
# Without expansion: 2 inference turns
turn 1: get_order(order_id="ord_123")         → { order_id, customer_id, ... }
turn 2: get_customer(customer_id="cus_456")   → { name, email, address }

# With expansion: 1 inference turn
turn 1: get_order(order_id="ord_123", include_customer=True)
         → { order_id, customer: { name, email, address }, ... }
```

The expansion pattern applied to agentic tools reduces inference turns and token cost simultaneously. This is the highest-leverage latency optimization for agentic interfaces.

## Measurement

Latency ergonomics decisions should be verified against measurement, not just intuition. Key metrics to instrument:

- **p50/p95/p99 response time** by endpoint — find the actual slow paths
- **Payload size by endpoint** — identify over-fetching
- **Requests per page load / per agent task** — measure chattiness
- **Cache hit rate by endpoint** — validate caching policy effectiveness
- **Error rate by endpoint** — track 429s, 5xxs, client errors

"Optimize the hot path" is correct; knowing which path is hot requires measurement.
