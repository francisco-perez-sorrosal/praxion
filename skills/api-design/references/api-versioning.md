# API Versioning

Strategies for versioning APIs, managing breaking changes, and deprecating old versions without disrupting consumers.

## Versioning Strategy Comparison

| Strategy | Mechanism | Pros | Cons | Best For |
|----------|-----------|------|------|----------|
| **URL path** | `/v1/users`, `/v2/users` | Explicit, easy to route, simple for consumers | Proliferates URL structures, entire API versioned at once | Public APIs, external consumers |
| **Custom header** | `X-API-Version: 2` | Clean URLs, per-request version control | Hidden from casual inspection, requires header awareness | Internal APIs, controlled consumers |
| **Content negotiation** | `Accept: application/vnd.api.v2+json` | Per-resource versioning, HTTP-standard mechanism | Complex for consumers, poor tooling support | Advanced use cases, fine-grained versioning |
| **Query parameter** | `/users?version=2` | Easy to test in browsers | Unconventional, pollutes query space, caching complications | Prototyping, transitional use |

### Decision Guidance

- **Public/external APIs**: URL path versioning. Transparency and simplicity outweigh URL aesthetics.
- **Internal microservices**: header versioning or content negotiation. Cleaner URLs, and consumers are controlled.
- **Single-resource evolution**: content negotiation. Version individual resources independently.
- **Avoid query parameter versioning** in production -- it complicates caching and is not a recognized convention.

## What Constitutes a Breaking Change

Changes that break existing consumers and require a new version:

| Breaking Change | Example |
|----------------|---------|
| Remove a field | Drop `user.name` from responses |
| Rename a field | `user.name` becomes `user.display_name` |
| Change a field type | `user.age: string` becomes `user.age: integer` |
| Add a required field to request | New required `phone` field in create request |
| Remove an endpoint | Drop `DELETE /users/{id}` |
| Change URL structure | `/users/{id}` becomes `/accounts/{id}` |
| Change authentication mechanism | API key to OAuth2 |
| Change error response format | New error schema structure |
| Narrow accepted values | Enum `[active, inactive, pending]` becomes `[active, inactive]` |

### Non-Breaking (Additive) Changes

Safe to make without a new version:

- Add optional fields to request or response schemas
- Add new endpoints
- Add new query parameters (optional)
- Add new enum values (with caution -- consumers with exhaustive switches may break)
- Add new HTTP headers
- Relax validation constraints (increase `maxLength`, widen enum)

## Deprecation Workflow

Follow this sequence when deprecating an API version:

1. **Announce** -- communicate the deprecation timeline through changelog, developer portal, and API response headers. Minimum 6 months for public APIs, 3 months for internal.
2. **Mark deprecated** -- add `Deprecation` and `Sunset` headers to all responses from the deprecated version:
   ```
   Deprecation: true
   Sunset: Sat, 01 Mar 2027 00:00:00 GMT
   Link: <https://api.example.com/v2/docs>; rel="successor-version"
   ```
3. **Monitor usage** -- track call volume to the deprecated version. Reach out to high-volume consumers directly.
4. **Return warnings** -- add a `Warning` header or response body field alerting consumers:
   ```
   Warning: 299 - "API v1 is deprecated. Migrate to v2 by 2027-03-01. See https://api.example.com/migration"
   ```
5. **Sunset** -- after the deadline, return `410 Gone` with a migration guide link. Do not silently drop requests.

## Backward Compatibility Rules

### The Additive-Only Rule

Once an API version is published, treat its contract as append-only:

- **Add** new optional fields, endpoints, parameters, and enum values
- **Never remove** existing fields, endpoints, or parameters
- **Never change** the type, format, or semantics of existing fields
- **Never add** required fields to existing request schemas

### Robustness Principle

Design consumers to follow Postel's Law: "Be conservative in what you send, be liberal in what you accept."

- **Producers**: send all documented fields, use exact types, validate output against the schema
- **Consumers**: ignore unknown fields, handle missing optional fields gracefully, do not rely on field ordering

### Compatibility Testing

Validate backward compatibility as part of the CI pipeline:

- **Schema diff**: compare the current spec against the previous published version. Flag breaking changes.
- **Contract tests**: run consumer contract tests against the provider to verify no expectations are violated.
- **Example validation**: ensure all spec examples remain valid against current schemas.

## Migration Strategies

### Parallel Versions

Run both old and new versions simultaneously during the migration window:

```
https://api.example.com/v1/users  --> still active, deprecated
https://api.example.com/v2/users  --> current version
```

Route at the gateway level. Share business logic internally -- version differences should be limited to request/response transformation.

### Expand-Contract Pattern

For evolving within a version without breaking consumers:

1. **Expand**: add the new field alongside the old one. Both are populated in responses.
2. **Migrate consumers**: update consumers to use the new field.
3. **Contract**: once all consumers have migrated, deprecate the old field. Remove it in the next major version.

```json
// Phase 1: Expand -- both fields present
{ "name": "Jane Doe", "display_name": "Jane Doe" }

// Phase 2: Migrate -- consumers switch to display_name

// Phase 3: Contract -- name deprecated, removed in next version
{ "display_name": "Jane Doe" }
```

## Version Lifecycle

Define clear lifecycle stages for each API version:

| Stage | Description | Duration |
|-------|-------------|----------|
| **Preview/Beta** | Unstable, may change without notice | Weeks to months |
| **General Availability** | Stable, backward-compatible changes only | Until next major version |
| **Deprecated** | Functional but scheduled for removal | 6+ months (public), 3+ months (internal) |
| **Sunset** | Returns 410 Gone | Permanent |

Document the current stage of every API version in the developer portal and OpenAPI spec `info.description`.
