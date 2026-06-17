---
diataxis: explanation
audience: [human, agent]
---

# <API Name> Documentation

<!-- aac:authored owner=unspecified -->
One-paragraph overview: what this API does, who it's for, and the shape of the
surface (REST service / library / GraphQL / MCP). State the canonical spec
location — the raw spec at a stable URL **is** the agent-consumable surface.

- **Spec (source of truth)**: `<path-or-url-to-openapi.yaml | asyncapi.yaml | schema.graphql>`
- **Base URL**: `https://api.example.com/v1`
- **Versioning**: `/v1/` path-versioned; see [Changelog](changelog.md).

## Map of this documentation

This documentation follows [Diátaxis](https://diataxis.fr/) — four reader intents:

| Start here if you want to… | Go to |
|----------------------------|-------|
| Make your first successful call | [Getting Started](getting-started.md) |
| Obtain and present credentials | [Authentication](authentication.md) |
| Look up an operation, schema, or parameter | [Reference](reference/index.md) |
| Understand and recover from an error | [Errors](errors.md) |
| See what changed and the deprecation policy | [Changelog](changelog.md) |
<!-- aac:end -->
