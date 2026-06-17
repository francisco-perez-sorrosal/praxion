# Documenting an Existing MCP Server

Producing the **doc artifact** for an MCP server you already have — a tool catalog rendered from live `tools/list` introspection, the input/output schemas the server already declares, safety `annotations`, and error modes. This reference is about *documenting*, never *designing*. Back to [SKILL.md](../SKILL.md).

## The Seam: DESIGN vs DOCUMENT (Read This First)

This skill and `agentic-interface-design` split the MCP surface along one clean, non-overlapping line. State it both ways so the boundary is unambiguous from either side:

> **`agentic-interface-design` DESIGNS the tools.** Tool naming, fat-vs-thin decomposition (when to consolidate, when to split), input/output schema *design*, the error *grammar*, progressive disclosure of a large tool surface, and every "is this tool good?" quality judgment belong there.
>
> **This skill DOCUMENTS the existing server.** It renders the tool catalog from live introspection, surfaces the input/output JSON-schemas and `annotations` the server *already declares*, records the error modes, and links the spec — it produces the doc *deliverable* for a server whose design is already fixed.

The reciprocal line lives in `agentic-interface-design` (a later cross-ref step adds the matching pointer there): *"documenting an existing MCP server → `api-documentation`."* The two statements mirror each other so neither skill claims the other's territory.

**Routing rule when you hit a design question while documenting:**

| If you find yourself asking… | That is a… | Route to |
|------------------------------|------------|----------|
| "Should these two tools be merged / split?" | decomposition decision | `agentic-interface-design` |
| "Is this tool name / description good enough for the model to select on?" | design-quality decision | `agentic-interface-design` |
| "What's the right error grammar for retries?" | error-design decision | `agentic-interface-design` |
| "How do I render the existing 12 tools as a Markdown catalog?" | doc-artifact production | **stays here** |
| "How do I keep that catalog fresh as the server changes?" | doc-artifact production | **stays here** |
| "How do I surface the `destructiveHint` the server already declares?" | doc-artifact production | **stays here** |

Documenting a *bad* tool surface is still documenting — produce the honest catalog of what exists, and route the design-quality finding to `agentic-interface-design` rather than fixing it inline. Doc production never silently redesigns the server.

## What an MCP Doc Artifact Must Cover

An MCP server is self-describing: it already publishes its tools, resources, and prompts via the protocol's `list*` methods, each carrying schemas and metadata. The doc artifact surfaces that introspection — it does not re-author it.

| Section | Content | Source |
|---------|---------|--------|
| **Server identity & transport** | Name, version, transport (stdio / streamable-HTTP), launch command or endpoint, required env / config | Server manifest + README |
| **Tool catalog** | Per tool: name, one-line purpose, full input schema, output shape, error modes, side effects, safety posture | `tools/list` |
| **Resources & prompts** | Exposed URIs / templates, prompt arguments | `resources/list`, `prompts/list` |
| **Annotations** | `readOnlyHint`, `destructiveHint`, `idempotentHint` per tool | tool `annotations` block |
| **Spec link** | Pointer to the MCP specification (modelcontextprotocol.io), not a re-explanation of the protocol | external |

The descriptions inside each tool's `inputSchema` are the **source of truth**, exactly as SDL descriptions are for GraphQL ([graphql.md §1](graphql.md)). Render them; do not paraphrase them into a parallel table that drifts.

## Generate the Catalog from Introspection

The MCP analog of OpenAPI/GraphQL introspection is the live `tools/list` (and `resources/list`, `prompts/list`) response. Generate the doc from it rather than hand-maintaining a tool table that silently goes stale.

The minimal artifact is a README **Tools** section plus a generated schema appendix:

```markdown
<!-- aac:generated source=tools/list -->
## Tools

| Tool | Purpose | Read-only | Destructive | Idempotent |
|------|---------|:---------:|:-----------:|:----------:|
| `search_memory`  | Full-text search over stored notes        | ✓ | – | ✓ |
| `add_memory`     | Append a note to the active collection     | – | – | – |
| `delete_memory`  | Permanently remove a note by id            | – | ✓ | ✓ |

### `delete_memory`

Permanently remove a note by id. **Destructive, idempotent** — re-deleting an
already-removed id is a no-op, not an error.

**Input schema**
```json
{ "type": "object", "required": ["id"],
  "properties": { "id": { "type": "string", "description": "Note id from search_memory." } } }
```
**Errors** — `NOT_FOUND` when the id never existed (vs. the idempotent no-op for an already-deleted id).
<!-- /aac:generated -->
```

The catalog table (`aac:generated source=tools/list`) regenerates from introspection; any authored quickstart / auth narrative around it stays in an `aac:authored` fence (per [SKILL.md §6](../SKILL.md)).

**Annotations are the safety surface.** Surface `readOnlyHint` / `destructiveHint` / `idempotentHint` prominently — they are what both a human reader *and* a host-agent use to reason about whether a tool is safe to call unprompted. Omitting them from the doc strips the consumer's safety signal even when the server declares them.

There is no dominant third-party static-doc generator for MCP yet (the ecosystem is young). The durable strategy: keep each tool's `description` and `inputSchema` rich **in code**, render the table from `tools/list` output, and link the spec at [modelcontextprotocol.io](https://modelcontextprotocol.io). When the server changes, the catalog regenerates — don't edit it by hand.

## Keeping It Fresh (CI)

The catalog is a CI artifact, same as any spec-derived reference ([SKILL.md §5](../SKILL.md)):

1. **Introspect** the running (or test-harness) server — capture `tools/list` / `resources/list` / `prompts/list`.
2. **Regenerate** the `aac:generated source=tools/list` block from that capture.
3. **Diff** the committed catalog against the regenerated one; fail the PR if they differ (the maintainer changed the tool surface without regenerating the docs).

This is the MCP slot in the universal gate: introspection replaces "lint the spec," the catalog diff replaces "breaking-change diff." It guarantees the documented tool surface and the live server cannot silently diverge.

## REST + MCP: Two Surfaces of One Capability — Cross-Link, Don't Duplicate

A common pattern is the **same capability exposed as both a REST endpoint and an MCP tool** (and sometimes a library too). The skill's two-surface rule ([SKILL.md §1](../SKILL.md)) applies: publish each surface, cross-link them, never triplicate the same content.

**sandbook is the worked example** — one memory capability, three surfaces:

| Surface | What it is | Documented by | Source of truth |
|---------|-----------|---------------|-----------------|
| Python library | a package others `import` | [python.md](python.md) (docstrings → mkdocstrings) | docstrings |
| REST `/v1` service | endpoints others call | [rest-openapi.md](rest-openapi.md) (OpenAPI → Scalar) | `openapi.json` |
| MCP server | tools a host-agent invokes | **this reference** (`tools/list` → catalog) | tool `inputSchema` |

The MCP doc and the REST doc describe **the same underlying capability** through two different lenses. The right move is a single cross-link — the MCP tool catalog points at the REST operation that backs each tool, and the REST reference points back at its MCP wrapper — *not* a second hand-written copy of the semantics in each place. Duplicated semantics drift; one canonical description per concept plus a link does not.

> **A naive 1:1 generator dump is not a design pattern this skill endorses.** Whether a REST surface *should* be wrapped 1:1 into MCP tools, or pruned and reshaped into agent-shaped capabilities, is a **design** question — route it to `agentic-interface-design`, which carries the production lessons (tool explosion, description rewriting, response transformation) on why 1:1 mapping fails at scale. This skill documents whatever wrapper exists; it does not decide its shape.

## Sources

- [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25) — `tools/list` / `resources/list` / `prompts/list` introspection, tool `annotations`
- [MCP introduction](https://modelcontextprotocol.io) — server identity, transports (stdio / streamable-HTTP)
- [Speakeasy — generating MCP from OpenAPI, 50+ production servers](https://www.speakeasy.com/blog/generating-mcp-from-openapi-lessons-from-50-production-servers) — why naive 1:1 OpenAPI→MCP mapping fails (a design lesson; routed to `agentic-interface-design`)
- [Truto — auto-generated MCP tools](https://truto.one/blog/auto-generated-mcp-tools-for-ai-agents-a-2026-architecture-guide/) — tool manifest / metadata structure
