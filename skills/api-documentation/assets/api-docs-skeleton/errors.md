---
diataxis: reference
audience: [human, agent]
---

# Errors

<!-- aac:authored owner=unspecified -->
The error catalog. Every error this API emits, each with a resolution path —
an agent must self-recover from the response alone, so each entry states what
went wrong, why, and how to fix it.

## Error format

This API uses **RFC 9457 Problem Details** (`application/problem+json`):

```json
{
  "type": "https://api.example.com/problems/<slug>",
  "title": "Human-readable summary",
  "status": 422,
  "detail": "What specifically went wrong with this request",
  "instance": "/v1/<resource>/<id>"
}
```

Each `type` URI is stable and browsable — document every one below.

## Problem-type catalog

| `type` slug | Status | When it happens | How to recover |
|-------------|--------|-----------------|----------------|
| `invalid-credential` | 401 | Missing or expired token | Re-authenticate; see [Authentication](authentication.md) |
| `insufficient-scope` | 403 | Token lacks the required scope | Request a token with the listed scope |
| `not-found` | 404 | Resource does not exist | Verify the id |
| `validation-failed` | 422 | Request body failed business validation | Read `detail`; fix the named field |
| `rate-limited` | 429 | Too many requests | Back off per the `Retry-After` header |
<!-- aac:end -->

<!-- aac:generated source=<spec> view=errorResponses -->
<!--
  Per-operation error responses render here, generated from the spec's documented
  4xx/5xx responses. Regenerated from the committed spec — do not hand-edit.
  Until the generator is wired, this fence is an empty placeholder.
-->
<!-- aac:end -->
