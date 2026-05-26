# API Design Review Checklist

Use this checklist to audit a REST, GraphQL, or gRPC API design. Apply it when reviewing a design before implementation, auditing an existing API, or running `/review-interface` against an API surface. Back to [SKILL.md](../SKILL.md).

## Errors and RFC 9457

- [ ] All error responses use RFC 9457 Problem Details format (`type`, `title`, `status`, `detail`, `instance`)
- [ ] Responses sent with `Content-Type: application/problem+json`
- [ ] Error type URIs are documented and resolve to human-readable descriptions
- [ ] Field-level validation errors include an `errors` array with field and message per violation
- [ ] No stack traces exposed in error responses
- [ ] No opaque error codes without human-readable context
- [ ] Error messages include actionable detail (not just "invalid input")
- [ ] `request_id` or equivalent tracing identifier present in errors

## Resource Naming and URL Design (REST)

- [ ] Resource names are business-concept nouns, not implementation artifacts (Bloch: names matter)
- [ ] Collections use plural nouns (`/orders`, not `/order`)
- [ ] Nesting limited to one level (no `/users/{id}/orders/{oid}/items/{iid}`)
- [ ] No verbs in paths (exception: `POST /{resource}/{id}/activate` for custom actions)
- [ ] Kebab-case for multi-word paths (`/payment-methods`, not `/paymentMethods`)
- [ ] Filter, sort, and pagination parameters are query params, not path segments

## Idempotency

- [ ] All non-safe mutations (`POST`, `PUT`, `PATCH`, `DELETE`) support idempotency
- [ ] Either: the operation is naturally idempotent (upsert semantics, idempotent deletes)
- [ ] Or: an `Idempotency-Key` header (REST) or `request_id` parameter (gRPC/tool) is accepted
- [ ] Idempotency window documented (e.g., 24 hours for Stripe; 5–30 minutes for most cases)
- [ ] 5xx results stored under the idempotency key (so retry is always safe, not just on success)

## Pagination

- [ ] Every collection endpoint is paginated (no unbounded list responses)
- [ ] Default page size is small enough to be safe (≤50 for human-facing, ≤20 for agentic)
- [ ] `has_more` / `has_next_page` boolean present
- [ ] `next_cursor` (or equivalent) present for forward pagination
- [ ] `total_count` present (helps callers plan how many pages to fetch)
- [ ] Cursor pagination used for large/dynamic collections (not offset — offset is O(n) and inconsistent under mutation)

## HTTP Status Codes (REST)

- [ ] `400` used only for malformed requests (not business logic errors)
- [ ] `422` used for semantically-invalid requests (pass syntax, fail business validation)
- [ ] `401` vs `403` vs `404` used correctly (401 = unauthenticated, 403 = unauthorized, 404 safer when leaking existence is a concern)
- [ ] `409` used for conflicts (not silently returning 200 or 400)
- [ ] `429` always accompanied by `Retry-After` header
- [ ] `202` used only for genuinely asynchronous operations (not as a polite 200)

## Naming Consistency (Bloch: Consistency > Local Cleverness)

- [ ] Consistent verb vocabulary across all endpoints/methods (`create_`, not mixed with `add_` and `new_`)
- [ ] Consistent parameter names for the same concept across endpoints (`user_id` everywhere)
- [ ] Consistent error envelope shape across all endpoints
- [ ] Consistent pagination shape across all collection endpoints
- [ ] Consistent naming convention (camelCase or snake_case — pick one, apply everywhere)

## Versioning

- [ ] Versioning strategy documented (URL path, date-header, custom header — one choice)
- [ ] Within the current version: additive-only changes (no breaking changes without version bump)
- [ ] `Deprecation` and `Sunset` headers present on deprecated endpoints (RFC 8594)
- [ ] Breaking changes require a new major version

## Webhooks (if applicable)

- [ ] Every payload signed with HMAC-SHA256 + timestamp (replay protection)
- [ ] At-least-once delivery with exponential backoff documented
- [ ] Receivers designed for idempotency (event ID as idempotency key)
- [ ] Thin-payload + fetch pattern used (not fat payloads with embedded resource state)
- [ ] Documentation states ordering is not guaranteed

## Long-Running Operations (if applicable)

- [ ] `POST` returns `202 Accepted` with `Location: /operations/{id}` header
- [ ] `GET /operations/{id}` returns `{status, percentage_complete, result}`
- [ ] Success state redirects with `303 See Other` to the created resource
- [ ] Failure state includes RFC 9457 error in result

## Caching

- [ ] Every `GET` endpoint has an explicit caching policy (not "default browser cache")
- [ ] Stable resources use `Cache-Control: max-age=N`
- [ ] Changing resources use `ETag` + `If-None-Match` (conditional GET → 304)
- [ ] `Vary` header present where request headers affect the response
- [ ] Sensitive/personal data: `no-store` explicitly set

## Surface Design (Bloch: Minimal Surface Area)

- [ ] Every element is necessary — nothing added "for future use"
- [ ] No parameter lists with multiple parameters of the same type
- [ ] Correct usage is the path of least resistance (sensible defaults)
- [ ] Incorrect usage is immediately obvious (fail fast at schema validation)

## GraphQL-Specific

- [ ] Relay Connection spec used for pagination (not custom cursor/page shapes)
- [ ] Mutations return typed error variants (`union { Success | Error }`)
- [ ] DataLoader (or equivalent) used for all nested list resolution
- [ ] Schema uses non-nullable (`!`) where data is always present
- [ ] Custom scalars used for constrained types (DateTime, URL, ID formats)

## gRPC-Specific

- [ ] No field numbers reused (reserved numbers for removed fields)
- [ ] Removed field names reserved in `reserved` directive
- [ ] `FieldMask` used for update operations and selective reads
- [ ] Streaming mode matches the use case (not unary when streaming would eliminate round-trips)
- [ ] Standard methods (Get/List/Create/Update/Delete) follow Google AIP naming

## Quick Verdict Guide

| Finding count | Verdict |
|---------------|---------|
| 0 FAIL, 0 WARN | PASS |
| 0 FAIL, 1–3 WARN | PASS WITH FINDINGS |
| 0 FAIL, 4+ WARN | PASS WITH FINDINGS (significant) |
| 1+ FAIL | FAIL |

FAIL items: no RFC 9457, no pagination on collection endpoints, no idempotency on mutations, stack traces in errors, breaking changes without version bump, 429 without Retry-After.

WARN items: missing caching policy on some GETs, inconsistent naming, offset pagination (should be cursor), missing Deprecation/Sunset headers on deprecated endpoints.
