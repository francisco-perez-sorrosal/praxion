# Schema Contract Patterns

Language-neutral representation discipline for schemas whose consumers include models, not just code: agent-tool JSON-schemas, inter-agent message shapes, pipeline-artifact section formats. Back to [SKILL.md](../SKILL.md).

## The Representation Design Pass, Applied to a Tool Schema

```json
{
  "name": "get_customer_orders",
  "input_schema": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "description": "Customer ID, format cus_XXX" },
      "status": { "type": "string", "enum": ["pending", "shipped", "delivered"] },
      "page_size": { "type": "integer", "minimum": 1, "maximum": 20, "default": 10 }
    },
    "required": ["customer_id"]
  }
}
```

- `customer_id`, not `id` or `customer` — the name is the schema-level newtype; for a model consumer, the field name carries the semantics a nominal type would
- `enum` for the closed set — the schema-level sum type. A bare `"type": "string"` status field is stringly-typed at the contract level, and the model will eventually invent a value
- Bounded integers with defaults — the schema encodes the invariant instead of trusting the caller; an unbounded `page_size` is an invariant with no enforcement point
- Minimal `required` set — every required field is a constraint on the caller; require what the operation cannot proceed without, default the rest

## Error Shapes Are Part of the Contract

An agent tool's error response steers retry behavior. Make errors a designed shape, not a string dump:

- Name what failed, why, and what a corrected call looks like ("status must be one of pending|shipped|delivered") — actionable errors convert a retry loop into a corrected call
- Keep the error shape consistent across every tool in a surface — the consumer learns one grammar
- Never leak internals (stack traces, raw SQL, provider error codes) into a model-facing error — the model will reason about them

## Evolution Contract for Wire Shapes

Decide before shipping, not at the first breaking change:

- **Additive-only** (default): new fields are optional with defaults; existing field meanings never change; removal goes through a deprecation window. State the policy where the schema is defined
- **Version-tagged**: when meaning must change, add an explicit version discriminant and treat versions as a sum type — consumers switch on it exhaustively, and an unknown version is a parse failure at the boundary, not a silent misread
- The discipline is identical for an in-process type crossing a module boundary; only the mechanism differs (compiler vs schema registry vs contract test)

## Pipeline Artifacts Are Schemas Too

A pipeline document's required sections are a wire format between agents — the schema binds the path, not the author. Treat a change to a required heading or field format as a contract change: name the consumers (the agents that grep for the heading), update producer and consumer in the same commit, and prefer additive subsections over renames. A renamed required heading is the document-level equivalent of a removed wire field: every downstream grep silently reads emptiness.

## Evidence Calibration

State schema benefits at their measured strength: schema constraints demonstrably reduce interface-format errors (invalid calls, malformed payloads); controlled evidence that they improve end-task success does not yet exist. Design schemas for precision and self-description — do not expect them to fix a semantic planning problem, and do not justify schema work with the stronger claim.
