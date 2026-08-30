---
name: api-documentation
description: >
  Producing best-in-class documentation of your OWN API surface for both humans
  and AI agents: REST/OpenAPI reference docs, Python and TypeScript library/service
  docs, GraphQL schema docs, MCP server docs from tools/list introspection, and
  agent-consumable docs (llms.txt). Covers spec-as-source-of-truth, the human-vs-agent
  divergence, mandatory doc sections (quickstart/auth/RFC9457 errors/pagination/
  rate-limit/changelog), and docs-as-CI-artifact. Triggers: document my API, API
  reference docs, OpenAPI docs, MCP server docs, GraphQL schema docs, agent-consumable
  docs, llms.txt, document a REST/Python/TypeScript API surface.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# API Documentation

Procedural expertise for documenting your **own** API surface — REST/OpenAPI, Python, TypeScript, GraphQL, MCP — so both humans and AI agents can consume it. This skill produces the doc *deliverable*; it does not design the API (see Boundaries below).

The body below is the **universal core**: the settled, cross-validated rules that apply to every API surface. Deep, contested, or tooling-specific knowledge lives in the seven on-demand references — load only the ones your surface needs via the Reference Routing table.

## The Universal Core

### 1. Two Doc Surfaces

Every API is documented from one of two sources, and the choice is structural:

| Surface | Source of truth | Tooling shape |
|---------|-----------------|---------------|
| **Library** (a package others `import`) | docstrings / type signatures in code | docstring extractors (mkdocstrings, TypeDoc) |
| **Service** (an endpoint others call) | a committed spec (OpenAPI / SDL / proto) | spec renderers (Scalar, Redoc, SpectaQL) |

A package that is **both** (e.g. a Python lib that also exposes a REST service, or sandbook: lib + REST + MCP) must publish **both** surfaces and **cross-link** them — never triplicate the same content. The user navigates one surface; links bridge to the others.

### 2. Spec Is the Source of Truth — and the Agent Surface

The committed spec (OpenAPI 3.1, GraphQL SDL, protobuf, AsyncAPI) is canonical: committed to the repo, CI-validated, drift-checked. **The raw spec at a stable URL *is* the agent-consumable surface** — an LLM consumes the spec directly, no rendered HTML required. This is the single highest-leverage invariant; everything else follows from it.

**Spec-first vs code-first** is a non-issue *as long as the spec is canonical*. Spec-first is the default recommendation for public/versioned/cross-team APIs. Code-first (FastAPI, tsoa, zod-to-openapi emitting the spec) is fully acceptable **when the generated spec is committed + linted + contract-tested** — otherwise it silently drifts. The invariant is "the spec is committed, linted, and drift-checked in CI," not the authoring direction.

### 3. Humans and Agents Diverge — Mind the Metadata

The same API serves two consumers with different needs:

| Dimension | Human reader | Agent (LLM) consumer |
|-----------|--------------|----------------------|
| **Primary artifact** | rendered docs site (try-it, search) | raw spec / structured metadata |
| **Reads docs** | once, builds a mental model | every call, no persistent learning |
| **Discovery** | browses, follows links | only what's in the spec at call time |
| **Error recovery** | reads message, searches docs | must self-recover from the response alone |
| **Response size** | bigger is often more helpful | smaller is better; verbose payloads displace reasoning tokens |

**Agent-metadata discipline** is the least-contested, highest-value lever: every operation must carry a stable `operationId`, a one-line `summary`, a `description` that states preconditions and what the return means, and at least one `example`. These four fields are what an agent reasons over — write them as if onboarding a teammate who has never seen the system.

### 4. Mandatory Doc Sections

Every API's documentation must cover these, regardless of protocol or language:

- **Quickstart** — first successful call in under five minutes
- **Authentication** — how to obtain and present credentials
- **Reference** — every operation, generated from the spec/docstrings
- **Error catalog** — structured errors (REST: **RFC 9457 Problem Details**; GraphQL: error unions in the type system), each with a resolution path
- **Pagination** — the envelope shape and cursor/offset semantics for every collection
- **Rate limits** — limits, headers (`Retry-After`), and back-off guidance
- **Changelog / versioning / deprecation** — what changed, the versioning scheme, and the deprecation policy

A missing section is a documentation bug, not a stylistic gap.

### 5. Docs Are a CI Artifact

Documentation freshness is a pipeline byproduct, not a manual chore. The minimal gate:

```
lint  →  breaking-change diff  →  contract-test
```

- **Lint** the spec (Spectral / Vacuum) against a ruleset that requires `operationId`, descriptions, examples, error schemas, tags.
- **Diff** against the prior committed spec (oasdiff) to flag breaking changes before merge.
- **Contract-test** (Schemathesis, consumer-driven contracts) so the live API and the spec cannot silently diverge.

If the spec is generated code-first, this gate is what keeps it honest. See `references/rest-openapi.md` for the provider-neutral CI snippet.

### 6. Diátaxis ↔ AaC Fence Mapping

Structure docs by Diátaxis mode and wrap each section in the matching AaC fence (per `rules/writing/aac-dac-conventions.md`):

| Diátaxis mode | Reader intent | AaC fence |
|---------------|---------------|-----------|
| **Reference** | authoritative lookup | `aac:generated source=<spec>` — regenerated from the spec, never hand-edited |
| **Tutorial / Quickstart** | learning by doing | `aac:authored` |
| **How-to** | solving a specific problem | `aac:authored` (with `aac:generated` for sourced examples) |
| **Explanation** | understanding rationale | `aac:authored` |

The fence boundary is what lets reference content regenerate from the spec without erasing authored narrative. The shipped `assets/api-docs-skeleton/` encodes this layout.

### 7. Boundaries — What This Skill Does NOT Do

| Concern | Owner | This skill's relationship |
|---------|-------|---------------------------|
| **Designing** the API (resources, endpoints, versioning strategy) | `api-design` | consumes the design; produces its docs |
| API **quality / taste / review** (canon, Bloch lens, RFC 9457 design) | `api-design-craft` | applies the design's decisions in docs |
| **Designing** MCP tools (naming, schema, fat-vs-thin, error grammar) | `agentic-interface-design` | DOCUMENTS an existing server; routes design questions there |
| **Consuming** other people's API docs (Stripe, OpenAI, etc.) | `external-api-docs` | this skill documents your OWN API |
| **General** project docs (README, catalogs, architecture, changelogs) | `doc-management` | the deep API-doc specialist; doc-management is the generalist entry point |

This skill = **produce best-in-class docs for the API surface you own.**

## Reference Routing

Load only the references your surface requires. A Python REST service loads `python.md` + `rest-openapi.md` — exactly the two-surface split core item 1 teaches.

| You are documenting… | Load |
|----------------------|------|
| A REST API with an OpenAPI spec | [`references/rest-openapi.md`](references/rest-openapi.md) |
| The agent-consumable surface (spec-as-agent-API, token economy, llms.txt, overlays) | [`references/agent-consumable.md`](references/agent-consumable.md) |
| A Python library and/or FastAPI service | [`references/python.md`](references/python.md) |
| A TypeScript/Node library and/or service (tsoa, zod-to-openapi) | [`references/typescript.md`](references/typescript.md) |
| A GraphQL API (SDL-as-docs, SpectaQL, GraphiQL) | [`references/graphql.md`](references/graphql.md) |
| An existing MCP server (from live `tools/list` introspection) | [`references/mcp-docs.md`](references/mcp-docs.md) |
| A Rust crate (rustdoc, doc-tests, `# Errors`/`# Panics`/`# Safety`) | [`references/rust.md`](references/rust.md) |
| A surface not listed above (gRPC, Go, AsyncAPI) — or adding a new one | [`references/extending.md`](references/extending.md) |

## Scaffolding

The `/document-api` command operationalizes this skill: it detects the target's language/protocol/surface, scaffolds the matching `assets/api-docs-skeleton/` subtree plus the Spectral ruleset and CI gate, and cross-links multi-surface projects. Run it to bootstrap; this skill governs the content quality.

## Related Skills

- [`api-design`](../api-design/SKILL.md) — the methodology this skill documents the output of
- [`api-design-craft`](../api-design-craft/SKILL.md) — the API quality/taste lens
- [`agentic-interface-design`](../agentic-interface-design/SKILL.md) — designs the MCP tools this skill documents
- [`external-api-docs`](../external-api-docs/SKILL.md) — consuming *others'* API docs (the inverse of this skill)
- [`doc-management`](../doc-management/SKILL.md) — general project documentation; the generalist entry point
