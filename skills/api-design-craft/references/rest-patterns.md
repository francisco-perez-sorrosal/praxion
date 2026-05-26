# REST Patterns

REST quality patterns — the taste layer above `api-design`'s methodology. This file covers the opinionated guidance for making REST APIs excellent, not just functional. Back to [SKILL.md](../SKILL.md).

## URL Design and Resource Naming

Quality REST URLs follow these rules:

```
# Good
GET  /users                          # collection
GET  /users/{id}                     # single resource
POST /users                          # create
PUT  /users/{id}                     # replace
PATCH /users/{id}                    # partial update
DELETE /users/{id}                   # delete
GET  /users/{id}/orders              # one level of nesting
POST /users/{id}/activate            # custom action (only valid exception to no-verbs rule)

# Bad
GET  /getUsers                        # verb in path
GET  /user                            # singular collection
GET  /users/{id}/orders/{oid}/items  # too deep (2+ levels)
POST /users/create                    # /create is redundant with POST
```

Rules:
- Plural nouns for collections: `/users`, `/orders`, `/payment-methods`
- Limit nesting to **one level**: `/users/{id}/orders` is fine; deeper is a resource modeling problem
- Kebab-case for multi-word: `/payment-methods`, `/order-items`
- Query parameters for filtering, sorting, pagination: `?status=active&sort=-created_at&limit=20`
- No verbs in paths — `POST /users/{id}/activate` is the only valid exception (a custom action on a resource)

## Status Codes — Opinionated Guidance

The full HTTP status code semantics live in RFC 9110. The commonly misused ones:

| Code | Correct use | Common mistake | Quality note |
|------|-------------|---------------|--------------|
| `200` | Success; response body contains result | — | OK |
| `201` | Resource created; `Location` header points to it | Using 200 for created resources | Include `Location` |
| `202` | Accepted for async processing | Used when work is synchronous | Pair with `Location` for polling |
| `204` | Success with no body (delete, action with no response) | — | OK |
| `400` | Request is malformed (bad JSON, missing required field) | Used for business logic validation errors | Use 422 for semantic errors |
| `401` | Not authenticated (no or invalid token) | Confused with 403 | Include `WWW-Authenticate` header |
| `403` | Authenticated, not authorized | Used when 404 is safer | Prefer 404 when leaking existence is a security concern |
| `404` | Resource not found | Overused for authorization | Use 403 when the resource exists but access is denied (if safe to reveal existence) |
| `409` | Conflict (duplicate key, optimistic lock failed, concurrent edit) | **Underused** | Include which resource conflicts |
| `422` | Semantically invalid (passes syntax, fails business validation) | Conflated with 400 | Use RFC 9457 body |
| `429` | Rate limited | Missing `Retry-After` header | **Always include `Retry-After`** |

## PATCH Semantics

Two standards, one clear default:

**JSON Merge Patch (RFC 7396)** — the default:
- Send only the fields you want to update
- `null` means "delete this field"
- Simple, widely understood, appropriate for most resources

```json
// PATCH /users/123
{
  "name": "Updated Name",
  "bio": null
}
// Result: name updated, bio deleted, all other fields unchanged
```

**JSON Patch (RFC 6902)** — use when:
- Partial update semantics must be unambiguous (audit trail, CRDT semantics)
- Array manipulation is needed (append, reorder, remove by index)
- More complex semantics are required

```json
// PATCH /users/123 with JSON Patch
[
  { "op": "replace", "path": "/name", "value": "Updated Name" },
  { "op": "remove", "path": "/bio" }
]
```

**Default: JSON Merge Patch**. Use JSON Patch only when you have a specific reason.

## Rate Limiting
<!-- last-verified: 2026-05-12 -->

Always include rate limit headers. Use the IETF draft `draft-ietf-httpapi-ratelimit-headers`:

```
RateLimit-Limit: 100          # requests allowed in the window
RateLimit-Remaining: 43       # requests remaining in current window
RateLimit-Reset: 1640000000   # Unix timestamp when window resets
Retry-After: 30               # seconds to wait (on 429 responses)
```

On 429: always return `Retry-After`. Never return 503 for rate limiting. 503 means "service unavailable"; 429 means "slow down."

## Webhook Design

The Stripe/Twilio webhook pattern is the industry standard:

**1. Sign every payload.** Use HMAC-SHA256 with a per-endpoint shared secret. Include a timestamp to prevent replay attacks. The receiver verifies the signature before processing.

```
X-Webhook-Signature: sha256=<hmac>
X-Webhook-Timestamp: 1640000000
```

**2. At-least-once delivery.** Retry with exponential backoff (e.g., 5 attempts over 24 hours). Notify the caller (email/dashboard) when retries are exhausted. At-least-once means the receiver WILL see duplicate events.

**3. Idempotent receivers.** Use the event ID as an idempotency key at the receiver. Upsert semantics: if the event was already processed, return success without re-processing.

**4. Thin payloads + fetch pattern.** Send a thin event with `event_type` and `object_id`; the receiver fetches the full object from the API. This ensures:
- Replays are safe (receiver fetches current state, not stale embedded state)
- Payload is small regardless of object size
- Receiver always has the latest data

```json
// Thin payload
{
  "id": "evt_abc123",
  "type": "order.shipped",
  "created": 1640000000,
  "data": {
    "object_id": "ord_xyz789",
    "object_type": "order"
  }
}
```

**5. Don't guarantee ordering.** Events for the same resource may arrive out of order. Design receivers to handle `created` arriving after `updated` by checking timestamps on the fetched object.

## Long-Running Operations

The standard pattern (Google AIP + Azure guidelines):

```
POST /exports         → 202 Accepted
Location: /operations/op_123

GET /operations/op_123 → { "status": "running", "percentage_complete": 45, "stage": "processing_records" }

GET /operations/op_123 → { "status": "succeeded", "result": { "download_url": "..." } }
                         Location: /exports/exp_456   (303 See Other to created resource)

GET /operations/op_123 → { "status": "failed", "error": { ... RFC 9457 ... } }
```

Rules:
- `POST` triggers the operation → `202 Accepted` with `Location: /operations/{id}` header
- `GET /operations/{id}` returns status: `pending` / `running` / `succeeded` / `failed`
- On success: `303 See Other` to the created/modified resource
- Expose progress (`percentage_complete`, `stage`) for user-facing operations
- Include RFC 9457 error in the result on failure

## Bulk/Batch Endpoints

```json
// Request
POST /orders/bulk-cancel
{
  "order_ids": ["ord_1", "ord_2", "ord_3"]
}

// Response: 207 Multi-Status (partial success is possible)
{
  "succeeded": [
    { "id": "ord_1", "status": "cancelled" },
    { "id": "ord_2", "status": "cancelled" }
  ],
  "failed": [
    { "id": "ord_3", "error": { "code": "ALREADY_SHIPPED", "message": "Order has already shipped and cannot be cancelled" } }
  ]
}
```

Rules:
- Return partial success explicitly with `succeeded` and `failed` arrays
- Use `207 Multi-Status` when partial success is possible
- Document a maximum batch size (100 items is common); return `422` for oversized batches
- Per-item errors must follow the same error format (RFC 9457) as single-item errors

## Versioning Strategies — Cost Comparison

| Strategy | Maintenance cost | Breaking-change friction | Recommendation |
|----------|-----------------|--------------------------|----------------|
| Additive-only, no version | None | Zero breaking changes ever | Ideal; not always achievable |
| URL path (`/v2/`) | Parallel codebase or routing layer | Low (explicit in URL) | **Default for public APIs** |
| Date-based header (Stripe model) | Transformation modules per version | Low (explicit via header) | **Best for long-lived public APIs** |
| Custom header (`X-API-Version`) | Same as URL but hidden | Medium (invisible in URL) | Internal APIs only |
| Never-version ("just change it") | Zero upfront; infinite downstream breakage | Maximum | **Never** |

Add `Deprecation` and `Sunset` headers when retiring endpoints (RFC 8594):
```
Deprecation: Sat, 01 Jan 2026 00:00:00 GMT
Sunset: Sat, 01 Jul 2026 00:00:00 GMT
Link: <https://api.example.com/v2/users>; rel="successor-version"
```

## Caching — Quick Reference

Every `GET` endpoint should have an explicit caching policy. "Default browser cache" is not a policy.

| Mechanism | When to use | Example header |
|-----------|-------------|---------------|
| `Cache-Control: max-age=N` | Stable resource; CDN and client cache | `Cache-Control: public, max-age=3600` |
| `ETag` + `If-None-Match` | Changing resource; conditional GET returns 304 if unchanged | `ETag: "abc123"` |
| `Last-Modified` + `If-Modified-Since` | Alternative to ETag for time-based validation | `Last-Modified: Tue, 15 Jan 2025 00:00:00 GMT` |
| `Cache-Control: no-store` | Sensitive data; must never be cached | `Cache-Control: no-store, private` |
| `Vary` | Signal which request headers affect the response | `Vary: Accept-Encoding, Authorization` |
