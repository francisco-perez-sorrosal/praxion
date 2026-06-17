# GraphQL API Documentation

Documenting a GraphQL API where the SDL schema *is* the documentation — descriptions in the schema, a static published site, CI schema diffing, and live exploration. Back to [SKILL.md](../SKILL.md).

GraphQL is the cleanest instance of the skill's central invariant: **the spec is the source of truth and the agent surface.** For GraphQL the spec is the SDL schema itself — the same role OpenAPI 3.1 plays for REST. Document *in* the schema, generate *from* the schema, diff the schema in CI.

## 1. The Schema IS the Docs

GraphQL's SDL carries documentation natively. Every type, field, argument, and enum value takes a description string, and every consumer-facing tool (IDEs, introspection, doc generators) surfaces it. There is no second document to keep in sync — you document the thing in the thing.

| Mechanism | Syntax | What it does |
|-----------|--------|--------------|
| **Descriptions** | `"""..."""` triple-quoted string placed *immediately before* a definition | Rendered everywhere — introspection, GraphiQL, SpectaQL, IDE hovers |
| **Single-line description** | `"..."` (single double-quotes) before a definition | Same, for one-liners |
| **Deprecation** | `@deprecated(reason: "...")` directive on a field, enum value, or argument | Surfaces in introspection; IDEs strike the element through |
| **Custom directives** | author-defined directives in SDL (e.g. `@auth`, `@complexity`) | SpectaQL reads its own metadata directives to enrich the doc site |

```graphql
"""
A registered customer account. Created via `signup`; deactivated, never deleted,
via `deactivateAccount` (soft-delete preserves order history).
"""
type Account {
  id: ID!
  "Primary contact email. Unique across all accounts."
  email: String!

  "Display name shown in the UI. Defaults to the email local-part."
  displayName: String

  "Deprecated: use `displayName`. Removed after 2026-09-01."
  nickname: String @deprecated(reason: "Renamed to displayName; remove after 2026-09-01.")
}
```

**Deprecation discipline** (universal across the skill): `@deprecated` always carries a `reason` that names the **replacement** and a **removal timeline** — not just the flag. A deprecation without a migration path is an incomplete deprecation.

**Description discipline** — descriptions are load-bearing for the agent surface (see [agent-consumable.md](agent-consumable.md)): an LLM introspecting the schema reasons over the description text exactly as a human reads it in GraphiQL. Write each description as if onboarding a teammate who has never seen the system — state what the field means, its preconditions, and what a non-obvious return implies.

## 2. Static Published Site — SpectaQL

For the human "published reference site," generate static, hostable HTML from the schema (or from a live introspection result).

| Tool | Role | Notes |
|------|------|-------|
| **SpectaQL** (anvilco) | Auto-generate static, hostable HTML API docs from a schema or introspection query | The GraphQL analog of Redoc/Scalar for REST. Reads its own metadata directives for auth/example annotations. |

Minimal setup: `spectaql config.yml` → emits a static `public/` directory you host anywhere. Because the input is the schema, the site regenerates from the source of truth — wrap the rendered output in an `aac:generated source=schema.graphql` fence (per [SKILL.md §6](../SKILL.md)) so it never gets hand-edited and drifts.

## 3. CI Schema Diffing — GraphQL Inspector

Schema changes are the GraphQL equivalent of OpenAPI breaking-change detection. Gate them in CI.

| Tool | Role |
|------|------|
| **GraphQL Inspector** | Schema diffing and breaking-change detection between the prior committed schema and the proposed one |

Minimal gate: `graphql-inspector diff old.graphql new.graphql` in CI — fail the PR on breaking changes, flag newly-`@deprecated` fields. This is the GraphQL slot in the skill's universal `lint → breaking-change diff → contract-test` gate ([SKILL.md §5](../SKILL.md)): the SDL *is* both the lint target and the diff target.

## 4. Live Exploration — GraphiQL / Apollo Sandbox

The interactive "try-it" surface. Two credible options:

| Tool | Role | Hosting |
|------|------|---------|
| **GraphiQL** | In-browser interactive query explorer | Open-source, embeddable directly at the endpoint |
| **Apollo Sandbox** | Hosted interactive explorer / IDE for navigating and testing | Hosted by Apollo; no self-host needed |

> **Do not seed GraphQL Playground.** Apollo Server 2's GraphQL Playground reached end-of-life on **2022-12-31**. Use GraphiQL or Apollo Sandbox for new work.

## 5. The SDL Is the Canonical Spec (Parallel to OpenAPI for REST)

The structural parallel, made explicit:

| Concern | REST | GraphQL |
|---------|------|---------|
| Canonical spec | OpenAPI 3.1 document (committed) | SDL schema (committed) |
| Where descriptions live | `summary`/`description` per operation | `"""..."""` per type/field/arg |
| Deprecation mechanism | `deprecated: true` | `@deprecated(reason:)` |
| Static site generator | Redoc / Scalar / SpectaQL-for-REST | **SpectaQL** |
| CI breaking-change diff | oasdiff | **GraphQL Inspector** |
| Live try-it | Swagger UI / Scalar | **GraphiQL / Apollo Sandbox** |
| Agent surface | raw `openapi.json` at a stable URL | SDL / introspection at a stable URL |

Both protocols obey the same invariant: one committed spec, documented in-place, rendered for humans, diffed in CI, and served raw as the agent surface. The only difference is that GraphQL collapses "spec" and "doc-source" into a single artifact — there is no derivation step, because the schema already carries the descriptions.

## Mandatory Sections — GraphQL Mapping

The [SKILL.md §4](../SKILL.md) mandatory sections still apply; their GraphQL homes:

- **Quickstart / Auth** — `aac:authored` narrative (the schema can't carry "how to get a token").
- **Reference** — generated from the SDL via SpectaQL (`aac:generated source=schema.graphql`).
- **Error catalog** — GraphQL errors belong in the **type system**: model expected failures as result unions (`union AccountResult = Account | AccountError`) rather than relying solely on the top-level `errors` array; each error type's description names its resolution path.
- **Pagination** — document the connection pattern (Relay-style `edges`/`pageInfo`/cursors) once; every paginated field references it.
- **Changelog / deprecation** — driven by the GraphQL Inspector diff output plus an authored deprecation timeline.

## Sources

- [SpectaQL](https://github.com/anvilco/spectaql) — static GraphQL doc-site generation
- [GraphQL Inspector](https://the-guild.dev/graphql/inspector) — schema diffing / breaking-change detection
- [Apollo schema deprecations](https://www.apollographql.com/docs/graphos/schema-design/guides/deprecations) — `@deprecated` reason + replacement discipline
- [Apollo Sandbox](https://www.apollographql.com/docs/graphos/platform/sandbox) — hosted live explorer
- [GraphiQL](https://github.com/graphql/graphiql) — embeddable in-browser explorer
- [GraphQL spec — Descriptions](https://spec.graphql.org/) — SDL description and `@deprecated` semantics
