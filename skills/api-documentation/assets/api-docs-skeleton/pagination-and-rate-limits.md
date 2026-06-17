---
diataxis: how-to
audience: [human, agent]
---

# Pagination & Rate Limits

<!-- aac:authored owner=unspecified -->
Two mandatory concerns an agent cannot infer from individual operation schemas:
how collections paginate, and how the API throttles. Document both explicitly.

## Pagination

State the model — **cursor** (preferred at scale; O(1)) or **offset** (simple;
O(N) scan). Show the envelope shape every collection returns:

```json
{
  "data": [ /* … */ ],
  "next_cursor": "eyJpZCI6MTIzfQ==",
  "has_more": true
}
```

To page: pass the returned `next_cursor` as the `cursor` query parameter on the
next request. `next_cursor: null` (or `has_more: false`) means the last page.

## Rate limits

State the limit, the headers returned, and the back-off guidance:

| Header | Meaning |
|--------|---------|
| `RateLimit-Limit` | Requests allowed per window |
| `RateLimit-Remaining` | Requests left in the current window |
| `Retry-After` | Seconds to wait after a `429` |

On `429`, wait `Retry-After` seconds, then retry with exponential back-off and
jitter. See the `rate-limited` entry in the [error catalog](errors.md).
<!-- aac:end -->
