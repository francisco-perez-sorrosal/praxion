# Progressive Disclosure of Tools

When a tool surface grows, the token cost of serving all schemas upfront becomes a hard constraint — not a preference, but a physics problem. This reference covers the problem in numbers and the patterns that solve it. Back to [SKILL.md](../SKILL.md).

## The Token Economy Problem
<!-- last-verified: 2026-05-12 -->

A JSON schema for a single tool with a few parameters: approximately 300–800 tokens.

A typical enterprise MCP server with 400 tools:
- **400 × 800 tokens = 320,000 tokens** for schemas alone
- Claude's default context: 200K tokens
- **Result: the schema list exceeds the context window before the conversation begins**

Even for more modest servers:
- 50 tools × 800 tokens = 40,000 tokens dedicated to schema definitions
- That is 40K tokens that cannot be used for reasoning, context, or user content

## The Degradation Threshold

Research and production data show that LLM decision quality degrades measurably when presented with more than **~20–25 tools** at once. This is not a linear degradation — it is a cliff. The model's tool selection accuracy drops sharply as the list grows, independent of schema token cost.

Implication: even if you have the token budget, serving 100 tools upfront degrades quality.

**Rule of thumb: if the surface has more than ~20 tools, it needs progressive disclosure. No exceptions.**

## What Progressive Disclosure Achieves

Lazy schema loading — serving tool schemas on demand rather than upfront — achieves **85–100× token reduction** while maintaining tool selection accuracy. The model sees summaries and selects a domain; it then receives full schemas only for the domain it needs.

## Design Patterns

### Pattern 1: Meta-Tool Discovery

Expose a discovery tool that returns tool names and brief descriptions without full schemas:

```json
{
  "name": "list_available_tools",
  "description": "Lists available tools grouped by domain with brief descriptions. Call this first to discover what tools are available before selecting a specific tool. Returns tool names and one-line descriptions, not full schemas. Use get_tool_schema(tool_name) to retrieve the full schema for a specific tool.",
  "parameters": {
    "type": "object",
    "properties": {
      "domain": {
        "type": "string",
        "description": "Optional domain filter. Valid values: 'customers', 'orders', 'billing', 'inventory', 'analytics'. If omitted, returns all domains.",
        "enum": ["customers", "orders", "billing", "inventory", "analytics"]
      }
    }
  }
}
```

Pair with a schema-retrieval tool:

```json
{
  "name": "get_tool_schema",
  "description": "Returns the full parameter schema for a specific tool by name. Use after list_available_tools to get details before calling a tool.",
  "parameters": {
    "type": "object",
    "required": ["tool_name"],
    "properties": {
      "tool_name": {
        "type": "string",
        "description": "The exact tool name as returned by list_available_tools."
      }
    }
  }
}
```

This reduces the upfront token cost to ~2 tool schemas (the discovery tools) regardless of how many domain tools exist.

### Pattern 2: Domain-Grouped Bundles

Instead of exposing all tools in a flat list, group tools by domain into separate bundles. Present bundle summaries; expand a bundle when the model requests it.

Structure:
```
MCP Server
├── bundle: customers     (10 tools — search, create, update, delete, list, ...)
├── bundle: orders        (12 tools — create, cancel, ship, track, ...)
├── bundle: billing       (8 tools — invoice, payment, refund, ...)
└── bundle: analytics     (15 tools — report, aggregate, export, ...)
```

Each bundle is presented with a single description: "Customer management tools: searching, creating, updating, and deleting customer records." The model selects a bundle before receiving individual tool schemas.

### Pattern 3: MCP's Built-In Discovery

MCP has built-in tool discovery via the `tools/list` method. This is distinct from upfront schema injection — the client calls `tools/list` when it needs tool metadata, rather than having all schemas in the system prompt.

Frameworks that implement lazy loading (tool schemas served on `tools/call`, not pushed upfront) automatically achieve progressive disclosure. If you are using a framework that pushes all schemas upfront by default, check for a configuration option to enable lazy loading.

### Pattern 4: Capability Descriptions vs. Parameter Schemas

Serve capability descriptions first, parameter schemas on demand:

Phase 1 (upfront): tool name + one-line description
Phase 2 (on request): full parameter schema with all properties and descriptions

This can be implemented as a two-level discovery: the initial tool list contains only names and descriptions; calling a meta-tool or a specific MCP capability returns the full schema.

## Implementation Guidance

When designing a server with more than ~20 tools:

1. **Group by domain first** — which 4–6 natural groupings exist in the problem domain?
2. **Design domain bundles** — 8–15 tools per bundle is a reasonable target
3. **Write domain descriptions** — each bundle needs a single description precise enough for a model to select it
4. **Choose a discovery mechanism** — meta-tool vs. built-in MCP discovery vs. lazy schema loading (framework-dependent)
5. **Test with the discovery flow** — verify the model can reach the right tool in 1–2 discovery hops

## Deferred

The implementation of progressive disclosure in specific frameworks (FastMCP bundle configuration, how to implement lazy schema loading in the MCP Python SDK, etc.) belongs in `mcp-crafting`. This file covers the design rationale and the patterns; the implementation mechanics are in the building skill.
