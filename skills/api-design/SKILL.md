---
name: api-design
description: API design methodology covering REST, GraphQL, OpenAPI specifications,
  data contracts, and interface contracts. Covers API-first/design-first development,
  resource modeling, endpoint naming, HTTP semantics, OpenAPI 3.1 schema patterns,
  GraphQL schema design, API versioning strategies, schema evolution, contract testing
  concepts, consumer-driven contracts, and service boundary definition. Use when designing
  APIs, writing OpenAPI specs, choosing between REST and GraphQL, defining data contracts,
  planning API versioning, designing interface contracts, or reviewing API surface design.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# API Design

Methodology and patterns for designing APIs that are consistent, evolvable, and contract-driven. Covers the full API lifecycle from initial design through specification, versioning, and contract management.

**Satellite files** (loaded on-demand):

- [references/openapi-patterns.md](references/openapi-patterns.md) -- OpenAPI 3.1 specification patterns, schema composition, endpoint design, request/response modeling
- [references/graphql-patterns.md](references/graphql-patterns.md) -- GraphQL schema design, type system, query/mutation patterns, federation basics
- [references/api-versioning.md](references/api-versioning.md) -- versioning strategy comparison, deprecation workflows, backward compatibility rules
- [references/data-contracts.md](references/data-contracts.md) -- schema evolution, serialization format comparison, schema registries, producer-consumer contracts
- [references/interface-contracts.md](references/interface-contracts.md) -- service boundary definition, consumer-driven contracts, contract testing integration

## Core Principles

**Design-First**: Define the API contract before writing implementation code. The specification is the source of truth -- implementation conforms to it, not the other way around. Review the API surface with stakeholders (consumers, frontend teams, partner integrators) before building.

**Consumer-Oriented**: Design from the consumer's perspective. The API surface should reflect what callers need, not how the backend is structured internally. Avoid leaking internal domain models, database schemas, or implementation details through the API.

**Consistency**: Apply uniform conventions across every endpoint -- naming, error formats, pagination, authentication. Consistency reduces cognitive load for consumers and eliminates per-endpoint learning curves.

**Evolvability**: Design for change from the start. Use additive changes, explicit versioning, and contract guarantees so APIs can evolve without breaking existing consumers.

## API-First Design Process

Follow this sequence for new APIs or significant API changes:

1. **Identify consumers** -- who will call this API? Internal services, frontend apps, third-party integrators, AI agents?
2. **Define resources** -- model the domain as resources (nouns), not operations (verbs). Each resource represents a business entity consumers care about.
3. **Design operations** -- map CRUD and domain-specific actions to HTTP methods (REST) or queries/mutations (GraphQL).
4. **Write the specification** -- produce an OpenAPI or GraphQL schema before any implementation. Include examples for every endpoint.
5. **Review with consumers** -- share the spec, collect feedback, iterate. Mock the API if helpful.
6. **Implement to spec** -- build the implementation to match the contract. Validate responses against the schema in tests.
7. **Establish contracts** -- define backward compatibility guarantees and versioning strategy before the first consumer goes live.

## REST API Design

### Resource Modeling

Model resources as plural nouns in URL paths. Represent relationships through nesting (one level deep) or links.

```
GET    /users                  # List users
POST   /users                  # Create user
GET    /users/{id}             # Get user
PUT    /users/{id}             # Replace user
PATCH  /users/{id}             # Partial update
DELETE /users/{id}             # Delete user
GET    /users/{id}/orders      # List orders for a user
```

**Naming conventions:**

- Plural nouns for collections: `/users`, `/orders`, `/products`
- Kebab-case for multi-word resources: `/order-items`, `/payment-methods`
- No verbs in paths -- use HTTP methods for actions
- Limit nesting to one level: `/users/{id}/orders` not `/users/{id}/orders/{oid}/items/{iid}`
- Use query parameters for filtering, sorting, pagination: `/users?status=active&sort=created_at&limit=20`

### HTTP Method Semantics

| Method | Semantics | Idempotent | Request Body | Success Code |
|--------|-----------|------------|-------------|--------------|
| GET | Read resource(s) | Yes | No | 200 |
| POST | Create resource or trigger action | No | Yes | 201 (create), 200/202 (action) |
| PUT | Full replacement of resource | Yes | Yes | 200 |
| PATCH | Partial update | No | Yes | 200 |
| DELETE | Remove resource | Yes | No | 204 |

### Status Codes

Use standard HTTP status codes consistently:

| Range | Purpose | Common Codes |
|-------|---------|-------------|
| 2xx | Success | 200 OK, 201 Created, 202 Accepted, 204 No Content |
| 3xx | Redirection | 301 Moved, 304 Not Modified |
| 4xx | Client error | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable Entity, 429 Too Many Requests |
| 5xx | Server error | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable |

### Standard Error Response

Define a single error format and use it across every endpoint:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Must be a valid email address"
      }
    ],
    "request_id": "req_abc123"
  }
}
```

Include: machine-readable error code, human-readable message, field-level details for validation errors, request ID for tracing. Never expose stack traces or internal implementation details.

### Pagination

Use cursor-based pagination for large or frequently changing datasets. Offset-based is acceptable for small, stable collections.

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true
  }
}
```

### Filtering and Sorting

Express filters as query parameters. Use consistent operators for range and comparison queries:

```
GET /orders?status=pending&created_after=2026-01-01&sort=-created_at&limit=20
```

Prefix sort fields with `-` for descending order. Document all supported filter parameters in the OpenAPI spec.

## REST vs GraphQL Decision Framework

| Factor | Choose REST | Choose GraphQL |
|--------|------------|---------------|
| **Consumer diversity** | Few, known consumers with stable needs | Many consumers with varying data requirements |
| **Data shape** | Predictable, resource-aligned responses | Deeply nested or variable-shape responses |
| **Caching** | Critical (HTTP caching works natively) | Less critical or handled at application layer |
| **Real-time** | Webhooks or SSE sufficient | Subscriptions needed for live updates |
| **Team expertise** | Team knows REST conventions well | Team has GraphQL experience |
| **API surface** | CRUD-dominant operations | Query-heavy with complex relationships |
| **Ecosystem** | Broad tooling and infrastructure support | Need schema-driven type safety across stack |

**Default to REST** unless the project has a specific need that GraphQL addresses better. REST has broader tooling support, simpler caching, and lower operational overhead. Use GraphQL when consumer diversity or data shape variability justifies the added infrastructure.

**Hybrid approach**: REST for external/public APIs (simplicity, cacheability), GraphQL for internal APIs (flexibility, type safety). Maintain separate specifications for each.

## Versioning Strategy Selection

| Strategy | Mechanism | Visibility | When to Use |
|----------|-----------|-----------|-------------|
| **URL path** | `/v1/users` | High -- visible in every request | Public APIs, external consumers, simple routing |
| **Header** | `X-API-Version: 2` | Medium -- requires header inspection | Internal APIs, when URL aesthetics matter |
| **Content negotiation** | `Accept: application/vnd.api.v2+json` | Low -- embedded in media type | Fine-grained resource versioning, advanced consumers |
| **Query parameter** | `/users?version=2` | High -- visible but unconventional | Transitional, prototyping |

**Default to URL path versioning** for public and external APIs -- it is the most explicit, easiest to route, and simplest for consumers to understand. Use header or content negotiation for internal APIs where cleaner URLs justify the added complexity.

--> See [references/api-versioning.md](references/api-versioning.md) for deprecation workflows, backward compatibility rules, and migration strategies.

## Contract Types

Three contract categories serve different purposes in API development:

| Contract Type | Purpose | Audience | Reference |
|---------------|---------|----------|-----------|
| **API specification** | Define the API surface (endpoints, schemas, examples) | API consumers, frontend teams | [openapi-patterns.md](references/openapi-patterns.md), [graphql-patterns.md](references/graphql-patterns.md) |
| **Data contract** | Guarantee schema structure and evolution rules for data exchange | Service producers and consumers, data teams | [data-contracts.md](references/data-contracts.md) |
| **Interface contract** | Define service boundary behavior and consumer expectations | Service teams, platform engineers | [interface-contracts.md](references/interface-contracts.md) |

### When to Use Each

- **API specification only**: Single service with well-defined REST or GraphQL endpoints. Sufficient for most projects.
- **API spec + data contracts**: Services exchanging data via events/messages or shared schemas that evolve independently.
- **API spec + interface contracts**: Microservices architecture where service boundaries need explicit behavioral guarantees.
- **All three**: Large-scale distributed systems with event-driven communication, multiple consumer teams, and independent deployment cycles.

## API Security Essentials

Apply these security patterns to every API:

- **Authentication**: Use standard mechanisms (OAuth 2.0, API keys, JWT). Define security schemes in the OpenAPI spec.
- **Authorization**: Implement at the resource level, not just the endpoint level. Document required scopes/permissions.
- **Transport**: TLS everywhere -- no exceptions for internal APIs.
- **Input validation**: Validate all input at the API boundary. Use schema validation to reject malformed requests before business logic.
- **Rate limiting**: Protect against abuse. Return `429 Too Many Requests` with `Retry-After` header.
- **CORS**: Configure explicitly for browser-facing APIs. Never use wildcard origins in production.

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Verbs in URLs | `/getUser`, `/createOrder` | Use nouns + HTTP methods: `GET /users/{id}` |
| Exposing internal models | Database columns as API fields | Design a consumer-oriented representation |
| Inconsistent errors | Different error formats per endpoint | Single error schema applied everywhere |
| No pagination | Unbounded list responses | Always paginate collections |
| Breaking changes without versioning | Adding required fields, renaming endpoints | Use additive changes; version for breaking ones |
| God endpoint | `/api/do?action=X` dispatching everything | One resource per entity, one method per operation |
| Ignoring idempotency | Retries create duplicates | Implement idempotency keys for non-idempotent operations |

## Integration with Other Skills

- **[Spec-Driven Development](../spec-driven-development/SKILL.md)** -- behavioral specifications (When/and/the system/so that) define what the API should do; API design defines how the surface exposes that behavior
- **[Data Modeling](../data-modeling/SKILL.md)** -- data models inform API resource design; schema evolution rules complement API versioning strategy
- **[Doc Management](../doc-management/SKILL.md)** -- API documentation generation and maintenance

## Pre-Design Checklist

Before implementing an API:

- [ ] Consumers identified and their needs documented
- [ ] Resources modeled as domain nouns, not implementation artifacts
- [ ] REST vs GraphQL decision made with rationale
- [ ] OpenAPI or GraphQL schema written and reviewed
- [ ] Error response format standardized
- [ ] Pagination strategy chosen for all collection endpoints
- [ ] Versioning strategy selected with deprecation policy
- [ ] Authentication and authorization model defined
- [ ] Rate limiting and abuse protection planned
- [ ] Data contracts defined for event-driven or shared-schema interfaces
- [ ] Backward compatibility rules documented
