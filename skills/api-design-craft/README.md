# api-design-craft

API design quality, taste, and review craft — the layer above `api-design`'s methodology.

## When to Use

Activate this skill when:

- Reviewing API quality ("Is this a good API design?")
- Applying a taste lens to an API design
- Studying the canonical APIs (Stripe, GitHub, S3, Twilio, Linear, Resend)
- Choosing an API paradigm (REST vs GraphQL vs gRPC)
- Designing an error contract (RFC 9457), pagination strategy, or webhook flow
- Evaluating low-latency ergonomics (N+1, caching, streaming decisions)
- Auditing an API for Bloch-principle violations or consistency issues

## Activation

The skill activates on quality/taste/review vocabulary: "API quality", "API review", "API canon", "good API", "taste lens", "RFC 9457", "Bloch principles", "idempotency keys", "cursor pagination", "N+1 elimination", "webhook design", "long-running operation pattern".

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core quality framework: Bloch checklist, robust-API canon, paradigm selection table, status code guide, Postel's critique |
| `references/design-fundamentals.md` | Shared design canon (Rams, Norman, Nielsen, Bloch) — load for first-principles grounding. **Byte-identical** across all four interface-design skills (intentional; sentinel will flag as redundancy — it is correct). |
| `references/api-canon.md` | Deep treatment of Stripe/GitHub/S3/Twilio/Linear/Resend + standards (RFC 9457, OpenAPI 3.1, Relay, Google AIP) + books |
| `references/rest-patterns.md` | REST quality patterns: URL design, status codes, PATCH semantics, webhooks, long-running ops, bulk/batch, versioning, caching |
| `references/webhooks.md` | Receiving webhooks: signature verification (HMAC schemes, provider SDK verifiers), idempotency, async/fan-out processing, local tunnels, retries and DLQ |
| `references/graphql-patterns.md` | GraphQL quality patterns: when to use, schema design, Relay connections, error unions, DataLoader |
| `references/grpc-patterns.md` | gRPC quality patterns: when to use, Protobuf design, FieldMask, streaming modes, Google AIP |
| `references/low-latency-ergonomics.md` | Latency toolkit: N+1 elimination (expansion/includes/DataLoader), caching (ETag, Cache-Control), streaming decisions, round-trip cost modeling |
| `references/design-review-checklist.md` | Audit checklist for REST/GraphQL/gRPC APIs with PASS/FAIL/WARN verdict |

## Related Skills

- **`api-design`** — The methodology layer: API-first process, resource modeling, OpenAPI spec patterns, contract types. This skill is the quality/taste lens; `api-design` is the how-to.
- **`agentic-interface-design`** — Sibling hat: the same quality/taste lens for MCP tools, function-calling schemas, and A2A contracts (the model as consumer).
- **`data-modeling`** — Backend schema design informs API resource modeling.
- **`performance-architecture`** — Infrastructure-level performance behind the API surface.
