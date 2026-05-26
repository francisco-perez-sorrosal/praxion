# Agentic Interface Design Review Checklist

Use this checklist to audit an MCP server, function-calling tool surface, or A2A contract. Apply it when reviewing a design before implementation, auditing an existing server, or running `/review-interface` against an agentic tool surface. Back to [SKILL.md](../SKILL.md).

## Tool Naming and Descriptions

- [ ] Every tool name follows verb-noun format (e.g., `search_customers`, `create_invoice`)
- [ ] No acronyms or abbreviations in tool names that a new team member might not know
- [ ] Past ~20 tools: a domain prefix is used for namespacing (e.g., `github_`, `billing_`, `crm_`)
- [ ] Every tool description says what the tool does AND what it does NOT do
- [ ] Every tool description includes the return value meaning
- [ ] Every tool description includes preconditions if applicable
- [ ] Descriptions are written for a reader with no prior knowledge of the system

## Parameter Design

- [ ] Every parameter has a specific name (no `user`, `id`, `data`, `input`, `item` without a domain qualifier)
- [ ] Every non-obvious parameter has a `description` field
- [ ] Parameter descriptions include format constraints (date format, ID format, length limits)
- [ ] `enum` is used for every constrained string value (status, type, role, mode)
- [ ] `required` contains only fields the tool cannot function without
- [ ] No parameter schema exceeds 3 levels of nesting
- [ ] `examples` are included in descriptions for parameters with non-obvious format
- [ ] `$defs` are used for subschemas that appear in more than one tool

## Error Design

- [ ] Error responses follow the "X failed because Y; to fix: Z" grammar
- [ ] Error responses enumerate available alternatives (valid column names, valid status values, valid tool names)
- [ ] No stack traces in error responses
- [ ] No error-code-only responses (machine code without human-readable context)
- [ ] Error messages are bounded in length (not listing 200 possible values)
- [ ] `retry_safe` field present on errors where retry safety is non-obvious

## Idempotency

- [ ] Every tool with side effects is either naturally idempotent OR accepts a `request_id` parameter
- [ ] `request_id` parameter has a clear description explaining idempotency semantics and deduplication window
- [ ] Documentation confirms server stores results for 5xx errors (so retries are always safe)

## Tool Surface Size and Progressive Disclosure

- [ ] Tool count ≤ ~20, OR progressive disclosure is implemented
- [ ] If progressive disclosure is used: a discovery mechanism exists (meta-tool, domain bundles, or built-in MCP discovery)
- [ ] Domain groupings are documented and each has a clear description
- [ ] No tool is reachable only by knowing its exact name upfront (discoverability)

## Response Design

- [ ] Every list tool result is paginated (no unbounded list responses)
- [ ] Pagination includes: `next_cursor`, `has_more`, `total_count`, `page_size`
- [ ] Default page size is 10–20 items (agentic) or 20–50 (human-facing)
- [ ] Response includes only fields needed for the next step (no gratuitous verbosity)
- [ ] Mixed responses (structured + prose summary) used where appropriate
- [ ] Expansion pattern used where agent commonly needs related data in sequence

## Tool Primitive Selection

- [ ] Every mutation is a tool (nothing that mutates state is modeled as a resource)
- [ ] Resources are genuinely side-effect-free
- [ ] Prompts are used only for recurring parameterized instruction templates

## Consistency Across the Surface

- [ ] Consistent verb vocabulary (not sometimes `create_`, sometimes `add_`, sometimes `new_`)
- [ ] Consistent parameter names for the same concept across tools (e.g., `user_id` everywhere, not mixed with `uid`)
- [ ] Consistent response envelope structure across all tools
- [ ] Consistent error response shape across all tools

## A2A Contracts (if applicable)

- [ ] Agent Card is versioned with semantic versioning
- [ ] Capabilities are enumerated in the card
- [ ] Input and output schemas are defined
- [ ] Error types are enumerated with codes and descriptions
- [ ] Tasks have clear terminal states: `completed`, `failed`, `cancelled`
- [ ] Task errors include enough context for the calling agent to retry or escalate
- [ ] Tasks do not depend on external state that may change during processing

## Quick Verdict Guide

| Finding count | Verdict |
|---------------|---------|
| 0 FAIL, 0 WARN | PASS |
| 0 FAIL, 1–3 WARN | PASS WITH FINDINGS |
| 0 FAIL, 4+ WARN | PASS WITH FINDINGS (significant) |
| 1+ FAIL | FAIL |

FAIL items: missing idempotency on side-effecting tools, stack traces in errors, no pagination on list tools, tool count >20 with no progressive disclosure, no error grammar (just error codes).

WARN items: missing property descriptions, weak parameter names, no `$defs` for repeated subschemas, page size too large, missing `retry_safe` field.
