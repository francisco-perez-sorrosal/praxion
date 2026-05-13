# Agent Contracts

JSON-schema design for tool definitions, structured response design, pagination, and A2A contract design — the contracts that make agentic interfaces predictable and reliable.

## JSON Schema Design for Tool Parameters

The JSON schema in a tool definition IS the interface. The model uses it to know what parameters to provide, what formats are required, and what values are valid.

### `$defs` for Reused Subschemas

When the same shape appears in multiple tools, define it once in `$defs` and reference it:

```json
{
  "definitions": {
    "DateRange": {
      "type": "object",
      "properties": {
        "start": {
          "type": "string",
          "description": "Start date in ISO 8601 format (YYYY-MM-DD), inclusive."
        },
        "end": {
          "type": "string",
          "description": "End date in ISO 8601 format (YYYY-MM-DD), inclusive. Must be >= start."
        }
      },
      "required": ["start", "end"]
    }
  },
  "parameters": {
    "type": "object",
    "properties": {
      "date_range": {
        "$ref": "#/definitions/DateRange",
        "description": "The date range to query. Defaults to the last 30 days if omitted."
      }
    }
  }
}
```

This reduces repetition and ensures consistency. When the model learns what a `DateRange` is from one tool, it applies that knowledge across all tools using it.

### Description on Every Property

Every non-trivially-named property needs a `description` field — not just top-level parameters. This includes nested objects and array items.

```json
// Bad: no property descriptions
{
  "type": "object",
  "properties": {
    "filters": {
      "type": "object",
      "properties": {
        "status": { "type": "string" },
        "assigned_to": { "type": "string" }
      }
    }
  }
}

// Good: descriptions throughout
{
  "type": "object",
  "properties": {
    "filters": {
      "type": "object",
      "description": "Optional filters to narrow results. All filters are ANDed together.",
      "properties": {
        "status": {
          "type": "string",
          "description": "Filter by order status. One of: 'pending', 'processing', 'shipped', 'delivered', 'cancelled'.",
          "enum": ["pending", "processing", "shipped", "delivered", "cancelled"]
        },
        "assigned_to": {
          "type": "string",
          "description": "Filter by agent user_id. Use list_agents to get valid user_ids."
        }
      }
    }
  }
}
```

### `enum` for Constrained Values

When a string parameter has a fixed set of valid values, always use `enum`:

```json
// Bad: open string — model will hallucinate invalid values
{
  "priority": {
    "type": "string",
    "description": "Task priority: low, medium, high, or critical."
  }
}

// Good: enum — model picks from known valid values
{
  "priority": {
    "type": "string",
    "enum": ["low", "medium", "high", "critical"],
    "description": "Task priority level."
  }
}
```

Models select from `enum` values reliably. Open strings invite hallucination. Use `enum` whenever the set of values is finite and known.

### Nesting Depth

Avoid more than **3 levels of nesting** in parameter schemas. The model's reasoning degrades with nesting depth, and deeply nested parameters are harder to fill correctly.

| Nesting | Risk level |
|---------|-----------|
| 1 level (flat) | Safest |
| 2 levels | Fine |
| 3 levels | Acceptable |
| 4+ levels | Reasoning degrades; restructure if possible |

When you need deep nesting, consider flattening: instead of `config.database.credentials.password`, accept `database_password` as a top-level parameter.

### `examples` in Descriptions

Include examples for parameters where format is non-obvious:

```json
{
  "user_id": {
    "type": "string",
    "description": "The user's ID as returned by get_user or search_users. Format: 'usr_' followed by alphanumeric characters. Example: 'usr_abc123' or 'usr_7Kp9mNq'."
  }
}
```

Examples reduce format errors. The model pattern-matches on examples more reliably than it follows format specifications in prose.

## Structured vs. Prose Responses

### When to Return Structured Data

Return structured (JSON) responses when:
- The agent will extract specific fields for a subsequent tool call
- The data will be processed programmatically
- The caller needs to check specific values (status, count, ID)

```json
// Structured: agent can extract order_id for the next call
{
  "success": true,
  "order_id": "ord_xyz789",
  "status": "confirmed",
  "estimated_ship_date": "2025-01-20"
}
```

### When to Return Prose

Return prose when:
- The agent will reason over the information before acting (not extract a field)
- The result is the final human-facing output
- The information is inherently narrative (a summary, an explanation)

### Mixed Response Pattern

Often the right answer is both — structured metadata + a prose summary:

```json
{
  "success": true,
  "result": {
    "order_id": "ord_xyz789",
    "status": "confirmed",
    "total": 149.99
  },
  "summary": "Order ord_xyz789 created successfully for $149.99, confirmed and scheduled to ship January 20."
}
```

The model can extract `order_id` from the structured part and use the `summary` for user-facing responses.

## Response Size Discipline

Return only what the agent needs for the **next step**. This is the single most commonly violated rule in agentic interface design.

Verbose responses that include all possible related data:
1. Displace reasoning tokens from the context window
2. May be truncated silently by the framework
3. Increase token cost without adding value

The agent can always call again with more specific parameters if it needs more detail.

### Pagination Is Not Optional

Every list tool result must be paginated. The model's context is a shared resource.

Required pagination fields:
```json
{
  "results": [...],
  "pagination": {
    "next_cursor": "cursor_abc123",   // null if no more results
    "has_more": true,
    "total_count": 847,               // total matching records (for model planning)
    "page_size": 20                   // how many were returned in this page
  }
}
```

Default page sizes:
- Human-facing interfaces: 20–50 items
- Agentic tools: **10–20 items** (more conservative — preserve reasoning budget)

Never return more than 100 items in a single tool response. If the model needs all records, it should paginate.

### The Expansion Pattern for Agents

If the model will almost always need related data X after getting Y, return X alongside Y in the first call:

```json
// Without expansion: agent needs two calls
GET /orders/ord_123
→ { order_id, customer_id, items }

GET /customers/cust_456
→ { name, email, address }

// With expansion: one call
GET /orders/ord_123?expand=customer
→ { order_id, customer: { name, email, address }, items }
```

Apply the expansion pattern to tool responses: if 80% of calls to `get_order` are followed by `get_customer` for the same customer, return the customer inline by default (or as an optional `include_customer` boolean parameter).

## A2A Contract Design
<!-- last-verified: 2026-05-12 -->

When designing agent-to-agent interfaces (one agent calling another), the design primitives are: the Agent Card (the API declaration), and the Task (the unit of work).

### Agent Cards as Versioned Contracts

An Agent Card is a contract, not just a description. Design it with the same rigor as an API contract:

```json
{
  "name": "invoice-processor",
  "version": "2.1.0",
  "description": "Processes invoice documents: extracts line items, validates totals, and creates accounting entries. Input: PDF or structured invoice data. Output: structured invoice record with validation status.",
  "capabilities": [
    "extract-invoice-data",
    "validate-invoice-totals",
    "create-accounting-entries"
  ],
  "input_schema": { ... },
  "output_schema": { ... },
  "error_types": [
    { "code": "INVALID_PDF", "description": "..." },
    { "code": "VALIDATION_FAILED", "description": "..." }
  ]
}
```

Version the card with semantic versioning. Breaking changes require a major version bump. The calling agent should check the version before relying on specific capabilities.

### Tasks With Clear Terminal States

Design tasks that complete independently. A task should have all the context it needs in its initial request — it should not depend on external state that may have changed by the time it processes.

Terminal states every task should define:
- `completed` — task succeeded; result is in the output
- `failed` — task failed; error is in the result with recovery information
- `cancelled` — task was cancelled by the caller before completion

Avoid:
- Tasks that depend on external state being unchanged during processing
- Tasks with ambiguous completion states ("done" vs "processing" vs "pending")
- Errors without enough context for the calling agent to retry intelligently

### Error Design for A2A Tasks

Task errors must carry enough context for the calling agent to retry intelligently or escalate. Apply the same X-failed-because-Y-to-fix-Z grammar from `agent-error-ergonomics.md`:

```json
{
  "status": "failed",
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invoice total validation failed: line items sum to $847.23 but invoice states $912.50. Difference of $65.27 is unaccounted for. Check for missing line items or an applied discount not reflected in the line items.",
    "retry_safe": false,
    "suggested_action": "Resubmit with corrected totals or add the missing line items."
  }
}
```

The calling agent can use `suggested_action` to decide whether to retry, correct the input, or escalate to a human.
