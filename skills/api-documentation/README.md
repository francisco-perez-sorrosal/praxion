# api-documentation

Produces best-in-class documentation of a project's OWN API surface — REST/OpenAPI, Python and TypeScript library/service docs, GraphQL schema docs, MCP server docs, and agent-consumable docs (llms.txt) — for both human readers and AI agents. A lean SKILL.md carries the universal core (two doc surfaces, spec-as-source-of-truth, the human-vs-agent divergence, mandatory doc sections, docs-as-CI-artifact, Diátaxis↔AaC fence mapping, adjacency boundaries) and routes to seven on-demand references for per-surface tooling depth. This is the doc-production specialist; it documents the API but does not design it.

## When to Use

- Documenting a REST API from an OpenAPI 3.1 spec
- Documenting a Python or TypeScript library and/or service surface
- Documenting a GraphQL API from its SDL
- Documenting an existing MCP server from `tools/list` introspection
- Producing agent-consumable docs (raw spec at a stable URL, llms.txt)
- Wiring docs into CI (lint → breaking-change diff → contract-test)

## Activation

Load explicitly with `api-documentation` or reference documenting your API, API reference docs, OpenAPI docs, MCP server docs, GraphQL schema docs, agent-consumable docs, llms.txt, or documenting a REST/Python/TypeScript API surface.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Universal core (7 settled rules) + reference-routing table + adjacency boundary table |
| `README.md` | This file — overview and usage guide |
| `references/rest-openapi.md` | OpenAPI 3.1 pipeline: lint, diff, contract-test, render, publish |
| `references/agent-consumable.md` | Spec-as-agent-surface, token economy, llms.txt, overlays |
| `references/python.md` | Python library (mkdocstrings/Sphinx/pdoc) + service (FastAPI) |
| `references/typescript.md` | TypeScript library (TypeDoc/TSDoc) + service (tsoa/zod-to-openapi) |
| `references/graphql.md` | SDL-as-docs, SpectaQL, GraphQL Inspector, GraphiQL |
| `references/mcp-docs.md` | Document an existing MCP server from `tools/list` introspection |
| `references/extending.md` | Add-a-surface pattern + seeded gRPC/Go/Rust/AsyncAPI stubs |

## Related Skills

- [`api-design`](../api-design/) — designs the API this skill documents
- [`api-design-craft`](../api-design-craft/) — the API quality/taste/review lens
- [`agentic-interface-design`](../agentic-interface-design/) — designs the MCP tools this skill documents
- [`external-api-docs`](../external-api-docs/) — consuming *others'* API docs (the inverse)
- [`doc-management`](../doc-management/) — general project documentation
