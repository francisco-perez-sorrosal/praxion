# api-design

API design methodology covering REST, GraphQL, OpenAPI specifications, data contracts, and interface contracts. Provides API-first design process, technology decision frameworks, versioning strategies, and contract patterns for service boundaries.

## When to Use

- Designing a new API (REST or GraphQL) from scratch
- Writing or reviewing OpenAPI 3.1 specifications
- Choosing between REST and GraphQL for a project
- Defining data contracts for event-driven or shared-schema interfaces
- Establishing interface contracts between microservices
- Planning API versioning and deprecation strategies
- Reviewing API surface design for consistency and evolvability

## Activation

Load explicitly with `api-design` or reference API design, OpenAPI, GraphQL, REST design, data contracts, interface contracts, schema design, or API versioning.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: API-first process, REST design patterns, REST vs GraphQL decision framework, versioning strategy selection, contract type selection, security essentials, anti-patterns |
| `README.md` | This file -- overview and usage guide |
| `references/openapi-patterns.md` | OpenAPI 3.1 document structure, schema composition, endpoint design, security schemes |
| `references/graphql-patterns.md` | GraphQL type system, query/mutation patterns, connection pagination, federation basics |
| `references/api-versioning.md` | Versioning strategy comparison, breaking change rules, deprecation workflow, migration strategies |
| `references/data-contracts.md` | Schema evolution, compatibility modes, serialization format comparison, schema registries, producer-consumer patterns |
| `references/interface-contracts.md` | Service boundary definition, consumer-driven contracts, contract testing approaches, boundary patterns |

## Quick Start

1. **Start with SKILL.md** -- follow the API-first design process (identify consumers, model resources, write spec, review, implement)
2. **Choose technology** -- use the REST vs GraphQL decision framework
3. **Write the spec** -- load OpenAPI or GraphQL reference for specification patterns
4. **Plan evolution** -- load versioning reference for backward compatibility rules and deprecation workflow
5. **Define contracts** -- load data contracts and/or interface contracts references as needed for service boundaries

## Related Skills

- [`spec-driven-development`](../spec-driven-development/) -- behavioral specifications define what the API should do; API design defines the surface that exposes it
- [`doc-management`](../doc-management/) -- API documentation generation and maintenance
