---
diataxis: reference
audience: [human, agent]
---

# Changelog & Deprecation Policy

<!-- aac:authored owner=unspecified -->
What changed, the versioning scheme, and the deprecation policy. Structure each
release as a checklist so readers can scan for breaking changes fast.

## Versioning

`/v1/` path-versioned. Backward compatibility is maintained within a major
version; a breaking change ships a new major version plus a migration guide.

## Deprecation policy

A deprecated operation:
1. is marked `deprecated: true` in the spec,
2. returns a `Sunset` header with the removal date,
3. is documented here with its replacement and hard removal date.

Typical window: ~12 months (announce → response warnings → throttle → `410 Gone`).

## Releases

### v1.1.0 — YYYY-MM-DD

- **Breaking**: _(none)_
- **Added**: `<new operation>`
- **Deprecated**: `<operation>` → use `<replacement>` (removal: YYYY-MM-DD)
- **Auth / rate-limit changes**: _(none)_

### v1.0.0 — YYYY-MM-DD

- Initial release.
<!-- aac:end -->
