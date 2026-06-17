---
diataxis: tutorial
audience: [human]
---

# Getting Started

<!-- aac:authored owner=unspecified -->
The shortest path to a first successful authenticated call. Assume no prior
knowledge of this API. Target: a working call in under five minutes.

## 1. Get a credential

See [Authentication](authentication.md) for how to obtain a token.

## 2. Make your first call

Replace `$TOKEN` with your credential:

```bash
curl https://api.example.com/v1/<first-resource> \
  -H "Authorization: Bearer $TOKEN"
```

## 3. Read the response

Expected `200`:

```json
{ "data": [], "next_cursor": null }
```

## Next steps

- Browse every operation in the [Reference](reference/index.md).
- Learn the [error model](errors.md) before you handle failures.
<!-- aac:end -->
