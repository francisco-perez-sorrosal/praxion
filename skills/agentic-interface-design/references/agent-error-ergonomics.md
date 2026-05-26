# Agent Error Ergonomics

Error design for agentic interfaces is a distinct discipline from error design for human-facing APIs. The consumer is different; the recovery path is different; the constraints are different. Back to [SKILL.md](../SKILL.md).

## The Fundamental Constraint

A model must self-recover from a tool error **in the same turn**, using only the information in its context window. It cannot:
- Ask a human for help
- Search documentation
- Try a variation and observe what happens (it can only infer from what the error tells it)

This means an unhelpful error response leaves the model stuck. It will either give up, hallucinate a fix, or enter an error loop. All three outcomes are failures.

## The Error Grammar

Every error response should follow this grammar:

**"X failed because Y. To fix this: Z."**

| Component | What it provides | Example |
|-----------|-----------------|---------|
| **X** (what failed) | Orients the model — confirms which tool call failed | `"Order creation failed"` |
| **Y** (why it failed) | The actual cause, specific enough to act on | `"because the customer_id 'cust_999' does not exist"` |
| **Z** (how to fix it) | The model's next action, enumerated | `"Use search_customers to find the correct ID first"` |

Full example:
```json
{
  "error": "Order creation failed because the customer_id 'cust_999' does not exist in the database. Use search_customers with the customer name or email to find the correct customer_id, then retry create_order."
}
```

## What Not to Return

| Bad error | Why it fails |
|-----------|-------------|
| Stack trace | The model cannot act on implementation internals; it adds noise that displaces reasoning tokens |
| Error code alone (`"error_code": 42`) | The model cannot infer what 42 means without documentation it cannot access |
| "Internal server error" | Gives the model nothing to act on |
| "Invalid input" | Which input? What's wrong with it? |
| Exception class name | `"NullPointerException"` is meaningless to a model without source context |

## Enumerate Alternatives

The most useful component in an error response is an enumeration of the valid alternatives. This is the specific pattern that enables self-recovery:

```json
{
  "error": "Column 'user_id' not found in table 'orders'. Available columns: id, order_id, customer_id, created_at, updated_at, status, total_amount."
}
```

The model now knows exactly which column names are valid and can immediately retry with a valid column. Without the enumeration, it would have to call a separate schema-inspection tool or guess.

More examples:

```json
// Tool not found
{
  "error": "Tool 'search_invoice' not found. Available tools in the billing domain: search_invoices (search by customer), get_invoice (get by ID), list_recent_invoices (list with date filter)."
}

// Invalid parameter value
{
  "error": "Status 'archived' is not a valid order status. Valid values: pending, confirmed, processing, shipped, delivered, cancelled."
}

// Missing required context
{
  "error": "Cannot create shipment: order 'ord_123' has not been confirmed yet. Call confirm_order(order_id='ord_123') first, then retry create_shipment."
}
```

## Idempotency for Agent Retries

Agents retry on tool errors. This is not a bug — it is expected behavior. If a tool is not idempotent, agent retries cause duplicate side effects.

**Design rule: all tools with side effects must be idempotent.**

Two strategies:

### Strategy 1: Naturally Idempotent Design

Design the operation so re-running it produces the same result:
- "Create or update" semantics instead of "create only"
- Upsert on a unique business key
- Delete is idempotent by nature (deleting a deleted thing is a no-op — return success)

```python
# Naturally idempotent: create or update
def set_user_role(user_id: str, role: str) -> dict:
    """Sets the user's role, replacing any existing role assignment."""
    ...  # upsert semantics
```

### Strategy 2: Caller-Provided Idempotency Key

For operations that are not naturally idempotent (create operations that generate new IDs), accept a `request_id` parameter (caller-provided UUID):

```json
{
  "name": "create_order",
  "description": "Creates a new order. Pass a request_id to make the call idempotent — if an order was already created with this request_id, the existing order is returned instead of creating a duplicate.",
  "parameters": {
    "type": "object",
    "properties": {
      "request_id": {
        "type": "string",
        "description": "Caller-provided UUID for idempotency. If this request_id was used in the last 30 minutes, the previously created order is returned instead of creating a new one. Generate a UUID before the call and use it on retries."
      },
      "customer_id": { ... },
      "items": { ... }
    },
    "required": ["customer_id", "items"]
  }
}
```

The server stores `(request_id → result)` keyed pairs for the deduplication window (5–30 minutes is typical). Critically: **store the result even for 5xx errors**. This means retries are always safe, even when the first attempt encountered a server error (the Stripe pattern — they store 500 results for 24 hours under the idempotency key).

## Idempotency Key in the Description

Tell the model to generate a UUID and reuse it on retries. The model cannot generate cryptographic randomness natively, but it can generate a UUID-format string for short-lived idempotency purposes:

```
"Generate a UUID for request_id before calling this tool. If the call fails and you need to retry, use the same request_id to avoid creating duplicate records."
```

## Error Response Shape

Standardize the error response shape across all tools in a server. Inconsistency here causes the same model-confusion problems as inconsistent tool naming.

Recommended shape:
```json
{
  "success": false,
  "error": "Human-readable error following the X-failed-because-Y-to-fix-Z grammar",
  "error_code": "OPTIONAL_MACHINE_READABLE_CODE",
  "suggested_tools": ["OPTIONAL: list of tools that might help recover"],
  "retry_safe": true
}
```

`retry_safe` tells the model whether retrying is safe — particularly important for tools that have partial side effects. A model that knows a failed call was idempotent will retry confidently; a model that is uncertain will not.

## Errors and the Context Window

Verbose error responses displace reasoning tokens. After the model has understood the error and formed a plan, the error text is waste. Keep error messages:
- Long enough to enable self-recovery (cover X + Y + Z)
- Short enough to not dominate the context (< 300 tokens for most errors)
- The enumeration of alternatives should be bounded (list the top 5–10 alternatives, not 200)

```json
// Too verbose (don't do this)
{
  "error": "Available columns are: id, name, email, phone, address_line_1, address_line_2, city, state, postal_code, country, created_at, updated_at, deleted_at, role, permissions, last_login_at, login_count, failed_login_count, mfa_enabled, avatar_url, bio, timezone, locale, preferences, metadata, external_id, stripe_customer_id, salesforce_id, hubspot_id, intercom_id, pendo_id"
}

// Bounded (better)
{
  "error": "Column 'usr_id' not found. Most commonly queried columns: id, email, name, role, created_at. Full column list: call describe_table(table='users')."
}
```
