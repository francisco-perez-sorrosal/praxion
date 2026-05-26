# Tool Design for Models

The core craft of agentic interface design: writing tool names, descriptions, and parameter schemas that enable a language model to use a tool correctly on every call. Back to [SKILL.md](../SKILL.md).

## The Description Is the Interface

A human learns a tool once. A model reasons over the description on every invocation with no accumulated knowledge. This single fact changes every design decision:

- **The description is executable, not documentary.** It directly shapes model behavior.
- **A description change fixes incorrect behavior.** Code changes are often unnecessary.
- **Vague descriptions produce vague behavior.** Specify what the tool does AND what it does not do.

### What a Good Description Contains

1. **What the tool does** — in one sentence, present tense, precise verb. "Searches the customer database by name or email and returns matching records."
2. **What the tool does NOT do** — the boundary statement. "Does not create or modify customer records. Does not search orders or products."
3. **Preconditions** — what must be true for the tool to work. "Requires an authenticated session. The query must be at least 3 characters."
4. **What the return value means** — so the model knows what to do with the result. "Returns an array of customer objects. An empty array means no matches, not an error."

### Examples: Before and After

Bad (too vague):
```
"Search for customers"
```

Good:
```
"Searches the customer database by name or email address. Returns up to 20 matching
customer records sorted by relevance. An empty results array means no matches found —
it is not an error. Does not search orders, products, or other entities. Use
search_orders for order lookups."
```

Bad (no boundary):
```
"Manage user accounts"
```

Good (separate tools):
```
# Tool: create_user
"Creates a new user account with the given email and role. Does not send a welcome
email (use send_welcome_email for that). Returns the created user object including
the generated user_id."

# Tool: update_user
"Updates fields on an existing user account. Only the fields provided are updated;
omitted fields are unchanged. Cannot update email once set — create a new account
instead."
```

## Tool Naming

Tool names are how the model selects which tool to call. They must be unambiguous at a glance.

### Naming Rules

**verb-noun format**: `search_customers`, `create_invoice`, `cancel_subscription`. The verb signals intent; the noun signals what is acted on.

**No acronyms**: `get_crm_rec` is illegible. `get_customer_record` is clear. The model cannot expand acronyms reliably.

**Specific, not generic**: `send_email` when the tool only sends marketing emails becomes a hazard when the model uses it for transactional emails too. `send_marketing_campaign_email` is more specific and harder to misuse.

**Namespace past ~20 tools**: When a server has more than ~20 tools, group by prefix.

| Without namespace (bad at 40+ tools) | With namespace (better) |
|--------------------------------------|------------------------|
| `create_issue` | `github_create_issue` |
| `create_task` | `jira_create_task` |
| `add_item` | `cart_add_item` |

The prefix tells the model which system the tool belongs to — critical disambiguation when multiple systems are wired.

### Common Naming Mistakes

| Mistake | Example | Fix |
|---------|---------|-----|
| Generic verb | `get_thing` | `get_customer_by_id` |
| Ambiguous noun | `data_tool` | `query_analytics_table` |
| Imperative name | `DoSearch` | `search_documents` |
| Abbreviation | `upd_usr_role` | `update_user_role` |
| Double-barreled | `search_and_filter` | Split into two tools |

## Parameter Naming

The parameter name is the only disambiguation signal available to the model when filling in a call.

### Parameter Naming Rules

**Specific, not generic**:

| Generic (bad) | Specific (good) | Why |
|---------------|-----------------|-----|
| `user` | `user_id` | Disambiguates ID from name from object |
| `branch` | `source_branch` | Two branches in a merge — which is which? |
| `date` | `start_date` | One of potentially several dates |
| `id` | `order_id` | When multiple entity types have IDs |

**Type-hint suffixes** help: `_id`, `_url`, `_at` (timestamps), `_count`, `_list`.

### Parameter Descriptions

Every non-obvious parameter needs a description. "Non-obvious" means: anything beyond a simple string that the model might format incorrectly.

Required in description:
- Format constraints: `"ISO 8601 date string, e.g., '2025-01-15'"`
- Valid ranges: `"An integer from 1 to 100"`
- Enumerable values: `"One of: 'pending', 'active', 'cancelled'"` — but prefer `enum` in the schema
- Examples: `"e.g., 'user_12345' or 'usr_abc'"`
- What null/empty means: `"Pass null to use the account default"`

### The Required Field Trap

Mark a parameter `required` only if the tool cannot function without it. Required parameters force the model to produce a value even when none is known — this leads to hallucinated values.

```json
// Bad: forces model to hallucinate a filter_date
{
  "required": ["table_name", "filter_date"]
}

// Good: date is optional with clear default
{
  "required": ["table_name"],
  "properties": {
    "filter_date": {
      "description": "ISO 8601 date. If omitted, returns all records without date filtering."
    }
  }
}
```

## Tool Granularity

See the main SKILL.md body for the fat-vs-thin decision rule. Applied here:

### Signs a Tool Is Too Fat

- The description needs "and also" — it does two distinguishable things
- Some callers need only the first half
- An error in step 2 leaves step 1's side effects with no rollback

### Signs a Tool Is Too Thin

- Three tools are always called in the same order with no branching
- The model has nothing new to reason about between calls
- Round-trip count is the primary performance concern

### The Sequence Test

Ask: "Can the model skip the middle tool based on the result of the first?" If no — consolidate. If yes — keep separate.

## Consistency Across a Tool Surface

Inconsistency causes tool selection failures. The model builds an internal pattern over tool names. When a tool breaks the pattern, it either misselects or hesitates.

Rules:
- Same verb for the same operation across all entity types: `create_`, not sometimes `add_`, sometimes `new_`
- Same parameter name for the same concept: `user_id` everywhere, not `uid` in one tool and `user_id` in another
- Same response envelope structure: if most tools return `{data: T, error: null}`, all should
- Same error format: every error response follows the same grammar (see `agent-error-ergonomics.md`)

## Verifying Description Quality

Before shipping a tool, apply this quick test:

1. Cover the code. Read only the tool name, description, and parameter schema.
2. Can you tell what the tool does?
3. Can you tell what it does NOT do?
4. Can you tell what each parameter means and how to fill it?
5. Can you tell what a successful result looks like?
6. Can you tell what an error looks like and how to recover?

If any answer is "no," the description needs work.
