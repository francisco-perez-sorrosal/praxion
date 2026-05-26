# API Canon

The exemplary APIs and specifications worth studying. Each entry is an existence proof of a principle — not a tutorial but a reference for "this works; here's why." Back to [SKILL.md](../SKILL.md).

## The Canonical APIs

### Stripe: API as Product

Stripe was one of the first companies to treat its API as a revenue-bearing interface with developer ergonomics as a core quality dimension. Its design decisions have been adopted across the industry.

**Resource modeling**: Stripe uses clean business-concept nouns (`PaymentIntent`, `Customer`, `Subscription`) — not implementation artifacts. The 2019 shift from `Charge` to `PaymentIntents` was an acknowledgment that "charge" was an implementation concept, not a business concept. When your resource names don't map to business concepts your customers understand, the API is wrong.

**Idempotency keys**: Every `POST` request accepts an `Idempotency-Key` header. The server stores the result for 24 hours, keyed by that value — including 500 errors. Retry logic is always safe. The 24-hour window with 500-result storage is the critical detail: most implementations expire on success, breaking the guarantee for error paths. Store 500 results too.

**Expandable objects**: Related objects appear as IDs by default (`customer: "cus_abc123"`). Pass `expand[]=customer` to get the full object inlined. This is caller-controlled selective expansion — the caller gets what they need without a separate endpoint or a massive response they have to filter.

**Date-header versioning**: Every account is pinned to the API version at account creation. `Stripe-Version` header allows per-request override for testing. Version changes are encapsulated as transformation modules — the server applies them transparently. Old versions add only minimal maintenance cost. This is the best versioning model for long-lived public APIs.

**Error objects**: `type` (error category: `card_error`, `invalid_request_error`, `api_error`), `code` (machine-readable), `message` (human-readable), `param` (which field caused it), `decline_code` (for card declines). Fully actionable without string parsing.

**Predictable list envelope**: Every list has exactly: `object: "list"`, `data: []`, `has_more: boolean`, `url`. Consistent across all 100+ resource types. The model can write generic pagination code once.

**Durable lesson**: Design the error object first. Design the list envelope first. Treat consistency across endpoints as a product invariant.

Reference: [Stripe Engineering Blog — API Versioning](https://stripe.com/blog/api-versioning), [Idempotency](https://stripe.com/blog/idempotency)

---

### GitHub REST v3 + GraphQL v4: Parallel Evidence

GitHub ran REST and GraphQL simultaneously for years. Their transparency about the trade-offs is the clearest published record of what each paradigm is actually for.

**REST v3** is stable, broadly cached, consumed by everything from curl to enterprise CI tooling. The right choice when reach and caching breadth matter.

**GraphQL v4** was introduced to solve GitHub's specific problem: REST endpoints returned far more data than most clients needed, and they had N+1 round-trip issues in client code. Client-driven field selection solved their real problem. Not "REST is bad" — "over-fetch was expensive at GitHub's scale, and we had the engineering capacity to maintain both."

**Durable lesson**: Don't choose GraphQL to be modern. Choose it when client-driven field selection is the actual bottleneck, and you have the capacity to maintain it.

---

### AWS S3: 20-Year Stability

S3's API has been stable for approximately 20 years with almost no breaking changes. It is the existence proof that minimal, resource-oriented design survives decades.

**Design**: flat namespace, object as the resource, HTTP verbs on objects (GET, PUT, DELETE, HEAD), consistent header semantics. The simplicity IS the stability. There is no clever trick — there is only a small, clear surface area that maps directly to its domain.

**Durable lesson**: Minimal surface area ages well. Complexity accrues maintenance debt indefinitely. When you're unsure whether to add a feature, ask what the 10-year maintenance cost of that decision is.

---

### Twilio: Taming a Complex Domain

Twilio popularized "API-as-product" before Stripe (circa 2008), with API keys mailed on physical cards. Their REST API for telephony made PSTN routing, call state machines, and SMS delivery approachable through resource modeling.

**Design**: telephony is genuinely complex (carrier interconnects, call routing, state machines, DTMF handling). Twilio hides this behind business-concept nouns: `Call`, `Message`, `Conference`, `Recording`. The API expresses what you want to accomplish, not how the PSTN handles it.

**Durable lesson**: A complex domain can be tamed by aggressive resource modeling that hides protocol complexity behind business-concept nouns. The complexity doesn't disappear — it becomes the API's problem, not the caller's.

---

### Linear: GraphQL Done with Taste

Linear's GraphQL API shows what a schema-first, developer-centric GraphQL design looks like.

**Schema-first**: the schema is the contract. Linear's schema is documented, typed, and stable.

**Relay connections**: standard pagination shape — `edges`/`node`/`cursor`/`pageInfo`/`first`/`after`/`last`/`before`. The Relay spec is the right default for GraphQL pagination; don't invent a bespoke shape.

**Errors in the type system**: `union { Success | Error }` return types from mutations — not just HTTP error codes, not just runtime exceptions. The type system encodes failure modes. The client gets a typed error it can pattern-match on.

**Durable lesson**: GraphQL errors belong in the type system. HTTP error codes are insufficient for mutations. Return typed error variants.

---

### Resend: Simplicity as Differentiation

Resend launched in 2023 with a commodity service (email delivery) and won developer adoption through API quality alone, competing with incumbents that had more features and more market share.

**Design**: clean resource model, minimal required parameters, sane defaults, good documentation. Nothing novel in the implementation. The differentiation is that it was designed with developer ergonomics as a first-class concern, not as an afterthought.

**Durable lesson**: Simplicity is a competitive advantage. In a commodity market, API quality wins. You can build a business on top of a cleaner, simpler API than an incumbent's.

---

## The Standards Canon
<!-- last-verified: 2026-05-12 -->

| Standard | Key contribution | Status |
|----------|-----------------|--------|
| **OpenAPI 3.1** | Machine-readable API contracts; JSON Schema 2020-12 alignment; the lingua franca for REST APIs | Current standard |
| **RFC 9457** (Problem Details, 2023) | Standard error format: `type`, `title`, `status`, `detail`, `instance`. Use this instead of inventing a proprietary error shape | Current RFC |
| **RFC 9110** (HTTP Semantics, 2022) | Authoritative HTTP method semantics, status codes, headers. The ground truth for "what does 409 mean?" | Current RFC |
| **Relay Connection/Cursor spec** | Standard GraphQL pagination shape: `edges`, `node`, `cursor`, `pageInfo`, `first`/`after`/`last`/`before` | De facto standard |
| **Richardson Maturity Model** | Level 2 (URIs + HTTP verbs) is the practical target. Level 3 (HATEOAS) is theoretically pure but rarely worth the client complexity | Reference model |
| **JSON:API** | Compound document structure, relationship links, sparse fieldsets. Reduces bike-shedding on response envelopes | Optional standard |
| **gRPC / Protocol Buffers** | Schema-first binary protocol for internal service-to-service and streaming | Current standard |

## Style-Guide Convergence

Where Google AIP, Zalando RESTful API Guidelines, Microsoft REST API Guidelines, and Stripe agree — these are the settled questions:

| Topic | Consensus answer |
|-------|-----------------|
| Resource naming | Nouns for resources; HTTP verbs for operations |
| Pagination | Cursor pagination for large/dynamic collections; `next_cursor`, `has_more` |
| Error format | RFC 9457 or equivalent structured envelope; machine-readable code + human-readable message |
| Versioning | Additive-only within a version; explicit versioning (URL path or date-header) for breaking changes |
| Deprecation | `Deprecation` + `Sunset` headers for retiring endpoints (RFC 8594) |
| Idempotency | Idempotency keys for non-safe mutations; `request_id` pattern |
| Field naming | Camelcase (JSON API convention) or snake_case — pick one, apply everywhere |

## Books

| Source | Contribution |
|--------|-------------|
| **"API Design Patterns" (JJ Geewax, Manning 2021)** | Comprehensive resource-oriented design for large APIs: naming, partial updates, long-running operations, pagination, filtering, soft deletion — the Google Cloud API design philosophy in book form |
| **"Web API Design: The Missing Link" (Apigee)** | Practical REST design guide; coinage of "API as product" pattern |
| **Brandur Leach's blog** | Honest writing from inside Stripe on the real cost of versioning, the design of idempotency keys, what a multi-year API contract actually requires |
| **Zalando RESTful API and Event Guidelines** | Open-source style guide; strong on HTTP method semantics, `Deprecation`+`Sunset` headers |

## RFC 9457 Problem Details — Quick Reference

The standard error format. Use it for all REST APIs.

```json
{
  "type": "https://example.com/probs/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "The 'email' field must be a valid email address.",
  "instance": "/api/users",
  "errors": [
    { "field": "email", "message": "Must be a valid email address" }
  ],
  "request_id": "req_abc123"
}
```

Core members:
- `type`: a URI identifying the problem class (link to docs describing it)
- `title`: a short, static human-readable summary of the problem type
- `status`: the HTTP status code
- `detail`: a human-readable explanation specific to this occurrence
- `instance`: a URI identifying this specific occurrence

Extension members for operational needs:
- `errors`: field-level validation detail array
- `request_id`: for log correlation

Send `Content-Type: application/problem+json`. Never expose stack traces or internal details.
