# MCP Primitives as Design Surfaces

The three MCP primitives — tools, resources, and prompts — are design choices, not implementation choices. Picking the right primitive shapes how the model understands and uses the interface. Back to [SKILL.md](../SKILL.md).

## The Three Primitives

| Primitive | Purpose | Side effects | Identified by |
|-----------|---------|-------------|---------------|
| **Tool** | Action or computation | Yes (may mutate state) | Verb: `search_customers`, `create_invoice` |
| **Resource** | Data read | None (read-only) | URI: `customers://list`, `invoice://12345` |
| **Prompt** | Recurring template | None (produces instruction) | Name + parameterized template |

### The Hard Rule: Do Not Mix

If a function reads and then mutates, it is a **tool** — always. Resources must be side-effect-free. A resource that also creates a record is a misuse of the primitive, and it misleads the model into thinking the read is safe to retry.

```
# Bad: describes a resource but mutates
GET /api/user/activate → activates user account

# Good: separate the read from the write
Resource: user://{id}           → reads user state
Tool: activate_user(user_id)    → activates the account
```

## When to Use Each Primitive

### Tool: Use When

- The operation has side effects (create, update, delete, send, invoke)
- The operation requires computation (search, calculate, analyze)
- The operation is deterministic given the same inputs (but NOT necessarily idempotent — see `agent-error-ergonomics.md`)
- You want the model to be explicit about calling it (tools are deliberate invocations)

Tools are the primary surface in most MCP servers. When in doubt, use a tool.

### Resource: Use When

- The operation is a pure read with no side effects
- The data can be identified by a stable URI
- The same URI always returns the same logical data (content may change, but the identity is stable)
- You want the model to be able to read data without explicitly "calling" a function

Resources are good for: configuration files, reference data, document content, static schemas. They are NOT good for: search results (no stable URI), dynamically generated content, data that changes on read.

### Prompt: Use When

- You have a recurring interaction pattern that always produces the same formatted instruction
- The template is complex enough that you don't want to repeat it in every conversation
- The parameters are well-defined and bounded

Prompts are the least-used primitive. Good examples: a structured code review request with specific checklists, a formatted debugging session opener with environment context.

## Progressive Disclosure and the Primitive Set

When a server has many tools, the token cost of serving all schemas upfront becomes prohibitive (see `progressive-disclosure-of-tools.md`). The primitive set gives you two built-in progressive disclosure mechanisms:

**Using resources for discovery**: expose a resource `tools://categories` that lists tool categories and their descriptions, without full schemas. The model reads this to decide which category to explore next.

**Domain-grouped bundles**: group tools by the resource type they operate on. A server with 60 tools becomes 6 domain bundles of 10. Present the bundles first; expand a bundle on demand.

**Meta-tool approach**: a `list_tools(category?)` tool that returns tool names and brief descriptions for a category, with full schemas available on demand via a `get_tool_schema(tool_name)` call.

## How the Primitives Map to Design Decisions

### Capability → Primitive

Ask: "Is this a read or a write?"

```
Is it purely reading data?
  ├─ YES → Can it be URI-identified?
  │         ├─ YES → Resource (read-only, no side effects)
  │         └─ NO  → Tool (compute/search tools have no stable URI)
  └─ NO  → Tool (any mutation → tool)
```

### When a Capability Is Unclear

Sometimes a capability straddles the line. Two tests:

**The retry test**: can the model safely retry this operation if it fails? If retrying would cause duplicate side effects → tool (and design idempotency in). If retrying is always safe → could be a resource.

**The audit test**: does this operation need to be in an audit log? If yes → tool (audit trails track tool calls, not resource reads).

### Tool vs. Direct LLM Call

When should something be a tool vs. a prompt (asking the model directly)?

- If the operation requires deterministic computation (math, parsing, lookups) → tool
- If the operation requires external I/O (API calls, file reads, database queries) → tool
- If the operation is pure reasoning over information already in context → prompt (no tool needed)

## Deferred to `mcp-crafting`

This file covers *which primitive to choose* for a given design problem. The mechanics of building a tool, resource, or prompt — FastMCP decorator syntax, transport configuration, server packaging, testing with MCP Inspector — belong in the `mcp-crafting` skill.

The design decision (what to build) precedes the implementation decision (how to build it). Make the primitive selection thoughtfully; the implementation follows.
