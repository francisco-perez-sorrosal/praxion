---
name: api-design-craft
description: >
  API quality, taste, and review craft — the layer above api-design methodology.
  Canonical APIs (Stripe, S3, Linear, GitHub, Twilio, Resend), Bloch core as review
  checklist, robust-API canon (RFC 9457, cursor pagination, idempotency, versioning),
  REST vs GraphQL vs gRPC selection, HTTP status code semantics (Retry-After, 422 vs
  400), PATCH semantics, webhook design, long-running ops, low-latency ergonomics
  (N+1, ETag, DataLoader). Triggers: reviewing API quality, applying a taste lens,
  choosing a paradigm, designing error contracts/pagination/webhooks, evaluating
  latency ergonomics. Methodology in api-design; agentic tool design in
  agentic-interface-design.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "The Standards Canon"
  - "Rate Limiting"
  - "Connection Reuse"
---

# API Design Craft

This skill is the **quality and taste lens** for REST, GraphQL, and gRPC APIs. It answers: *Is this API good?* The `api-design` skill answers: *How do I structure an API?*

The difference matters for context loading: use `api-design` when building an API from scratch (methodology, OpenAPI spec patterns, resource modeling process). Use this skill when reviewing an API design, applying a quality lens, studying the canonical examples, or making a paradigm choice under trade-offs.

Start with the shared canon in `references/design-fundamentals.md` — Bloch's principles are the foundation of this skill's entire review framework.

**Satellite files** (loaded on-demand):

- [references/design-fundamentals.md](references/design-fundamentals.md) -- durable design canon (Rams, Norman, Nielsen, Bloch) — the first-principles foundation
- [references/api-canon.md](references/api-canon.md) -- canonical APIs (Stripe, GitHub, S3, Twilio, Linear, Resend) and standards (RFC 9457, OpenAPI 3.1, Relay, Google AIP)
- [references/rest-patterns.md](references/rest-patterns.md) -- REST quality patterns: URL design, status codes, PATCH semantics, webhooks, long-running ops, versioning
- [references/graphql-patterns.md](references/graphql-patterns.md) -- GraphQL quality patterns: when to use, schema design, Relay, error unions, DataLoader
- [references/grpc-patterns.md](references/grpc-patterns.md) -- gRPC quality patterns: Protobuf design, FieldMask, streaming modes, Google AIP
- [references/low-latency-ergonomics.md](references/low-latency-ergonomics.md) -- N+1 elimination, caching (ETag, Cache-Control), streaming decisions, round-trip cost
- [references/design-review-checklist.md](references/design-review-checklist.md) -- audit checklist for REST/GraphQL/gRPC APIs

## The Canon Summary

| API | Domain | One Durable Lesson |
|-----|--------|--------------------|
| **Stripe** | Payments | Treat the API as a product: design the error object first, design the list envelope first, use idempotency keys from day one |
| **GitHub REST v3** | Developer platform | REST is the right choice when reach and caching matter; GraphQL was introduced for their specific over-fetch problem, not because REST was bad |
| **AWS S3** | Object storage | Minimal surface area ages well. S3's ~20 years of stability is proof |
| **Twilio** | Telephony | A complex domain can be tamed by aggressive resource modeling behind business-concept nouns |
| **Linear GraphQL** | Project management | GraphQL errors belong in the type system: `union { Success | Error }` from mutations, not HTTP error codes |
| **Resend** | Email | Simplicity is a competitive advantage — you can out-compete incumbents on API quality alone |

Deep treatment of each, plus the standards canon (OpenAPI 3.1, RFC 9457, RFC 9110, Relay, Richardson Maturity Model, Google AIP, Zalando): `references/api-canon.md`.

## Bloch Core as Review Checklist

Apply Joshua Bloch's 8 principles as the primary review checklist for any API:

| Principle | Review question |
|-----------|----------------|
| **Minimal surface area** | Is every element necessary? What can be removed without loss of capability? |
| **Names matter** | If you can't name it well, is the design wrong? Are names self-documenting? |
| **Hard to misuse > easy to use** | Is incorrect usage immediately obvious? Is correct usage the path of least resistance? |
| **Fail fast** | Are errors reported as early as possible (schema validation, not runtime)? |
| **Principle of Least Astonishment** | Does every endpoint do the least surprising thing given its name? |
| **Consistency > local cleverness** | Are naming, pagination, and error shapes consistent across all endpoints? |
| **Document religiously** | Does every element have a description? Does every error have a resolution path? |
| **Avoid long parameter lists** | Are there endpoints that accept many parameters of the same type? |

## Robust API Canon

| Practice | Why it matters |
|----------|---------------|
| Idempotency keys for mutations | Networks are unreliable; clients will retry; duplicate side effects are silent bugs |
| At-least-once delivery, idempotent receivers | For webhooks: reliability and duplicate protection are separate concerns |
| Pagination from day one | "Works fine in dev, OOMs in prod" is a recurring failure mode |
| RFC 9457 errors as first-class citizens | Callers handle errors programmatically; string parsing is not an interface |
| Cursor pagination at scale | Offset is O(n) in the DB; cursor is consistent under concurrent mutation |
| Versioning discipline | You cannot un-ship an API; additive-only within a version |
| Retries with backoff and jitter | Synchronized retries amplify failures; jitter breaks the thundering herd |

## Paradigm Selection: REST / GraphQL / gRPC

| Dimension | REST | GraphQL | gRPC |
|-----------|------|---------|------|
| **Primary strength** | Resources, caching, broad reach | Client-driven field selection | Internal service-to-service, streaming |
| **Caching** | Native HTTP (ETag, Cache-Control, CDNs) | Application-layer only | Not applicable (binary) |
| **Tooling breadth** | Highest (curl, Postman, everything) | High (Apollo, GraphiQL) | Medium (grpcurl, Evans) |
| **Learning curve** | Low (~2 days) | Medium (~6 days) | High (~7+ days; Protobuf toolchain) |
| **Browser-friendly** | Yes | Yes | No (gRPC-web proxy needed) |
| **Streaming** | SSE / chunked transfer | Subscriptions | Native bidirectional |
| **Latency** | ~250ms median | ~180ms complex queries | ~25ms equivalent queries |

**Decision heuristic:**
- Public API, third-party clients → **REST** (reach, caching, tooling)
- Internal graph with many consumer shapes, N+1 round-trip problem → **GraphQL**
- Internal service-to-service, high-throughput or streaming → **gRPC**
- LLM/agentic interface → see `agentic-interface-design`

## Commonly Misused HTTP Status Codes

| Code | Correct use | Common mistake |
|------|-------------|---------------|
| `400` | Request is malformed (bad JSON, missing required field) | Used for business logic errors (use 422) |
| `401` | Not authenticated (no token or invalid token) | Confused with 403 |
| `403` | Authenticated but not authorized | Used when 404 is safer (don't leak resource existence) |
| `404` | Resource not found | Overused for authorization |
| `409` | Conflict (duplicate key, concurrent edit) | **Underused** — should be used more often |
| `422` | Semantically invalid (passes syntax, fails business validation) | Conflated with 400 |
| `429` | Rate limited | Missing `Retry-After` header — always required with 429 |
| `202` | Accepted for async processing | Used when work is synchronous (use 200 or 201) |

## Postel's Law — Use with Caution

"Be liberal in what you accept, be conservative in what you send" was designed for TCP bootstrapping — not API design. Modern critique ([CACM, RFC on Robustness Principle Reconsidered](https://cacm.acm.org/practice/the-robustness-principle-reconsidered/)):

- Permissive acceptance entrenches bugs as de facto standards
- Creates security vulnerabilities (overly permissive parsers are attack surfaces)
- Complicates future evolution (anything accepted becomes load-bearing)

**Practical stance for new APIs**: be conservative on **both** sides. Accept precisely what the schema documents; return precisely what is documented. Reserve liberal acceptance for legacy interoperability you cannot control.

## When to Reach for Which Reference

| Task | Reference file |
|------|---------------|
| Study the canonical APIs and standards in depth | `api-canon.md` |
| REST quality patterns (status codes, PATCH, webhooks, versioning) | `rest-patterns.md` |
| GraphQL quality patterns (Relay, errors in type system, DataLoader) | `graphql-patterns.md` |
| gRPC quality patterns (Protobuf design, FieldMask, streaming modes) | `grpc-patterns.md` |
| Latency: N+1, caching, streaming, payload shape | `low-latency-ergonomics.md` |
| Reviewing an API design | `design-review-checklist.md` |
| Shared design principles (Rams, Norman, Nielsen, Bloch) | `design-fundamentals.md` |

## Related Skills

- **[`api-design`](../api-design/SKILL.md)** — the methodology layer: API-first process, resource modeling, OpenAPI spec patterns, versioning strategies, interface contracts. This skill is the quality lens; `api-design` is the how-to.
- **[`agentic-interface-design`](../agentic-interface-design/SKILL.md)** — the same quality/taste lens applied to MCP tools, function-calling schemas, and A2A contracts (the model as consumer).
- **[`external-api-docs`](../external-api-docs/SKILL.md)** — for verifying current API specifications, SDK versions, or library capabilities before committing to a paradigm decision.
- **[`data-modeling`](../data-modeling/SKILL.md)** — backend schema design informs resource modeling; when the resource model feels wrong, often the data model is the root cause.
- **[`performance-architecture`](../performance-architecture/SKILL.md)** — infrastructure-level performance behind the API surface; this skill covers interface-level latency ergonomics.
