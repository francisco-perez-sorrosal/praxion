# Structured Output

JSON mode semantics per provider; Pydantic/Zod as the contract language; the `instructor` retry-repair loop in depth; tool-use as structured output; open-weights via `outlines`/`guidance`.

Back to: [../SKILL.md](../SKILL.md)

## When to Read This File

Load this deep dive when you are:

- Designing a new structured-output prompt and choosing between JSON-mode, strict JSON-Schema, and tool-based function-calling.
- Debugging a structured-output prompt that returns empty output, wrong types, or silently dropped fields.
- Building the retry-repair loop around a Pydantic/Zod model.
- Integrating structured output with an on-device or open-weights model via `outlines` or `guidance`.
- Migrating between providers and hitting quiet behavioral differences (Anthropic's schema rewriting, OpenAI's strict-mode invariants).

`SKILL.md` covers the decision matrix and provider deltas at a summary level; this file gives the operational depth.

## "The Pydantic/Zod Model Is the Prompt"

Field names, docstrings, and `Field(description=...)` text travel to the model alongside the JSON Schema. The schema is not merely a decoder constraint; it is part of the instruction surface. Consequences:

- Write field names as if a model reads them — because it does. `customer_email` beats `email` when the document might contain multiple emails.
- Docstrings and `description` are free prompt real estate. Use them to disambiguate edge cases (`"Return null if no customer name is present."`).
- Enum values are part of the contract. Prefer closed enums to free-form strings when the downstream consumer cares.
- Nested models give the prompt hierarchical structure for free.

Validation at the boundary is non-negotiable. The strict mode flags from providers reduce malformed output but do **not** guarantee semantic correctness. Always re-validate with the Pydantic/Zod model before passing data to downstream code.

## OpenAI Strict JSON Schema

### The happy path

```python
# Python, OpenAI SDK.
# <!-- SDK version: 2026-04-16 training-data assumption; verify via `external-api-docs` before shipping. -->

response = client.chat.completions.create(
    model="gpt-5",  # pin a verified, dated model ID
    messages=[
        {"role": "system", "content": "Extract the fields into the schema."},
        {"role": "user", "content": user_input},
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "ExtractedFields",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "summary", "tags"],
                "additionalProperties": False,
            },
        },
    },
)
```

### Load-bearing constraints

- **`additionalProperties: false`** is mandatory. Omit it and some model versions silently return empty output with no error.
- **Every property must appear in `required`.** If you want an optional field, declare the type as `["string", "null"]` and add the field to `required`; the model will return `null` when absent.
- **Enum support**: closed `enum` arrays are honored. Use them whenever the downstream cares about a bounded vocabulary.
- **`anyOf` and `oneOf`**: supported but less thoroughly tested in strict mode. Validate carefully on the specific model version.
- **Unsupported keywords** (`minimum`, `maximum`, `minLength`, `pattern`, `format`): not enforced by the decoder. Validate at the boundary.
- **Depth and recursion**: strict mode limits schema depth and disallows self-referential schemas in some providers/versions. Check the current guidance via `external-api-docs` before shipping a recursive schema.

### Failure modes

| Symptom | Likely cause |
|---------|--------------|
| Empty output, no error | Missing `additionalProperties: false`, or a property not in `required` |
| Fields silently dropped | Same |
| Type coercion (string returned for a number field) | Schema allowed `["string", "number"]`; narrow it |
| Model refuses with a natural-language apology | Input hit a safety filter; strict mode does not suppress refusals |

### `response_format` vs. tools

For structured output without external effects, `response_format` with strict JSON Schema is the simpler path. For structured output that also calls a tool (function), use `tools` with `strict: true` on the tool schema. On OpenAI, the two features compose — you can require both a structured final message and one or more tool calls in the same turn.

## Anthropic Tool-Based Structured Output

### The idiomatic path

Claude does not expose a direct `response_format` equivalent to OpenAI's JSON mode. The idiomatic structured-output path is tool-based:

```python
# Python, Anthropic SDK.
# <!-- SDK version: 2026-04-16 training-data assumption; verify via `external-api-docs`. -->

tool = {
    "name": "record_extraction",
    "description": "Record the extracted fields from the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "summary", "tags"],
    },
}

response = client.messages.create(
    model="claude-sonnet-4-x",  # pin a verified, dated model ID
    max_tokens=1024,
    tools=[tool],
    tool_choice={"type": "tool", "name": "record_extraction"},
    messages=[
        {"role": "user", "content": f"Extract the fields from: {user_input}"},
    ],
)

# The structured output is in the tool_use block of the response.
tool_use_block = next(b for b in response.content if b.type == "tool_use")
payload = tool_use_block.input  # dict; validate with Pydantic before use
```

### Schema rewriting

Anthropic's SDK **silently rewrites** JSON Schema constraints such as `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, and `format`. These are moved into the field descriptions and validated post-generation (by the service, not by the decoder). Consequence: the model's output may violate those constraints without the SDK raising a decode error. Your Pydantic/Zod validator at the boundary is the real enforcement.

### Tool-use token overhead

Tool-use on Anthropic adds roughly 313–346 tokens of system-prompt overhead per request (prompt-token cost, counted against your budget). At scale, this is non-trivial — benchmark before assuming tool-based output is free. Prompt caching can amortize it if the tool block is stable.

### Grammar compilation cache

The first request with a given tool schema pays a grammar-compilation latency cost. Subsequent requests in the same cache window (roughly 24 hours) hit a compiled grammar and are faster. If you cold-path benchmark, you will misjudge steady-state latency; run a warmup.

### `strict` on tools

Anthropic supports `strict: true` on tool schemas. Set it. This causes the model to conform to the schema structure more reliably (pre-generation constraints) while the post-generation validator catches remaining drift.

### When to use `tool_choice: "any"` vs. `{"type": "tool", "name": ...}`

Use `{"type": "tool", "name": "record_extraction"}` when you want guaranteed structured output — the model must emit that tool call. Use `"any"` or `"auto"` when the model may legitimately choose not to call a tool; the output may then be natural-language text, and your caller must handle both paths.

## Google Gemini Structured Output

Gemini supports JSON-Schema-backed structured output via the native SDK. Behavior has drifted across releases (from "return the object" to "return a response with structured parts"). The current shape is documented in the Gemini SDK docs and is best fetched via `external-api-docs` before coding against it.

Notes:

- Enum support is strong; prefer closed enums for deterministic outputs.
- Thinking mode and structured output compose (with thinking enabled); verify current parameter shape per SDK release.

## Mistral and AWS Bedrock

Both providers support JSON-Schema structured output. Mistral's approach mirrors OpenAI's (`response_format` with JSON Schema). Bedrock's shape depends on the underlying model vendor (Anthropic, Mistral, Meta, etc.) and uses the vendor's native structured-output mechanism through the Bedrock wrapper.

When working cross-provider, an abstraction layer like `instructor` (Python) or `instructor-js` (TypeScript) insulates application code from provider-specific shapes.

## The Retry-Repair Loop

### Why retry on `ValidationError`

Even in strict mode, the model occasionally returns output that:

- Uses a valid schema shape with semantically wrong content (a number where a domain-specific range is required).
- Hits a safety boundary and returns a refusal message that is syntactically but not semantically schema-conformant.
- Drifts on open-weight models where constrained decoding is enforced externally (see `outlines`/`guidance` below) and the model runs out of tokens mid-output.

A bounded retry loop that feeds the `ValidationError` back to the model as part of the next call lets the model self-correct without operator involvement.

### The `instructor` pattern (Python)

The `instructor` library wraps the retry loop. See `../assets/pydantic-retry-template.py` for a minimal template.

```python
import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field

class ExtractedFields(BaseModel):
    title: str = Field(description="Document title, verbatim from the source.")
    summary: str = Field(description="One-sentence summary, <= 40 words.")
    tags: list[str] = Field(description="3-5 lowercase topic tags.")

client = instructor.from_anthropic(Anthropic())

result = client.messages.create(
    model="claude-sonnet-4-x",
    max_tokens=1024,
    max_retries=3,                 # cap at 2-3 in production
    response_model=ExtractedFields,
    messages=[{"role": "user", "content": build_prompt(document)}],
)
```

The library catches `pydantic.ValidationError`, formats the error into a re-prompt, and retries. On exhaustion, it raises. Cap `max_retries` at 2–3 to bound cost.

### Manual retry-repair loop

For non-Python stacks, or when you want control over the retry message format:

```text
Attempt 1:
  prompt  -> model
  output  -> validator -> fail

Attempt 2:
  prompt + "Your previous output failed validation with: {error}. Return output that validates." -> model
  output -> validator -> fail

Attempt 3:
  prompt + "Final attempt. Previous error: {error}. Output must conform to {schema-summary}." -> model
  output -> validator -> pass | give up
```

Log the final failure. Never retry indefinitely — pathological inputs can loop forever and blow the token budget.

### What to put in the re-prompt error message

- The **validation error**, human-readable (Pydantic and Zod both format these clearly).
- **Do not** include the prior invalid output verbatim; it biases the model to repeat it. Summarize what was wrong (e.g., `"The 'tags' field must contain strings, not objects."`).
- Keep the core instruction and user input identical across retries. Only the error-correction preamble changes.

### Retry exhaustion handling

When retries exhaust, you have three options, listed in order of preference:

1. **Fail the request** and log. Appropriate when the pipeline has a safe fallback (return the user a generic error, drop the item in batch processing).
2. **Degrade gracefully**: use a simpler extraction (unstructured text, partial fields) and flag the record for manual review.
3. **Escalate**: call a larger or reasoning-native model as a fallback. Measurable cost increase, but some tasks genuinely are beyond smaller models' capability and you would rather pay for a correct answer than fail.

## Tool Use as Structured Output

Tool use is structured output with a side effect: the model's output is a typed function call that your code then executes. The schema design principles are identical — the `input_schema` of the tool is your contract language, and field names/descriptions are part of the prompt.

Tool use intersects with `agentic-sdks` when multiple tools are orchestrated into a loop. This skill covers the schema design and validation; the loop plumbing is out of scope — see `agentic-sdks` and `mcp-crafting`.

### Single-tool forced use

When you need guaranteed structured output with a tool shape:

- OpenAI: `tools: [...]` with `tool_choice: {"type": "function", "function": {"name": "..."}}` and `strict: true` on the tool schema.
- Anthropic: `tools: [...]` with `tool_choice: {"type": "tool", "name": "..."}` and `strict: true` on the tool schema.
- Gemini: forced-function-calling via the SDK's function-call config.

### Multiple tools, routed

When the model chooses among tools based on input, the prompt becomes a classifier over tools. Keep tool names short and descriptions pointed; avoid overlapping descriptions that confuse the router. Provide a fallback "no-tool" path (a natural-language message) when you want the model to decline to call any tool.

### Tool output validation

The arguments the model produces are parsed JSON; validate them with the same Pydantic/Zod model you would use for `response_format`. The tool-execution side (actually running the function) is a separate concern — validate first, then execute.

## Open-Weights and On-Device via `outlines` / `guidance`

When the target model is open-weights (Llama 3.x+, Mistral, Qwen, DeepSeek) or on-device, the provider's structured-output flag does not exist. Two libraries enforce structure via constrained decoding:

- **`outlines`** (Python) — compiles a regex or Pydantic model to a state machine that masks the logit space at each decoding step. Deterministic: the output is always valid against the schema.
- **`guidance`** (Python) — template-based structured generation with embedded control flow.

Both work with `transformers`, `vllm`, and compatible serving stacks. Tradeoffs:

- **Latency overhead** is non-trivial on long schemas. Profile before adopting in a latency-critical path.
- **Grammar compilation** is upfront; cache compiled grammars for reuse.
- **Cross-provider portability**: `instructor` works with both providers and local models, which makes it a good abstraction if you will later switch between hosted and local.

### When to use constrained decoding vs. retry loop

- **Constrained decoding (`outlines`/`guidance`)** guarantees valid output but at compilation and decoding cost. Preferred for hard schemas on self-hosted models.
- **Retry loop with validation** tolerates non-strict providers and is cheaper on the happy path. Preferred with hosted providers that ship native strict modes.
- **Both layered** is valid: use constrained decoding for shape and a Pydantic validator at the boundary for semantic checks.

## Validation Boundary Discipline

Regardless of provider or mode:

1. The model's output is untrusted. Validate with Pydantic/Zod before use.
2. The validator catches type errors, missing required fields, and enum violations. Semantic constraints (ranges, business rules) belong in a second validation layer after Pydantic/Zod structural validation passes.
3. Log validation failures with enough context to reproduce: prompt hash, model ID, output, error. This dataset becomes your regression suite (`./prompt-testing.md`).

## Cross-References

- `../SKILL.md` — overview, decision matrix, gotchas.
- `./few-shot-patterns.md` — wrapping exemplars to match structured output.
- `./reasoning-and-cot.md` — when structured output and reasoning-effort interact (the trained reasoning pass and structured decoding compose; verify on your specific model).
- `./versioning.md` — pinning schema hash in the envelope manifest.
- `./prompt-testing.md` — structured-output-specific assertions (schema conformance + property-level checks).
- `../assets/pydantic-retry-template.py` — minimal retry-on-ValidationError template.
- `../assets/envelope-manifest.yaml` — `schema_hash` field pins the schema version alongside the prompt.
- Sibling skill: `agentic-sdks` — tool-use loops, multi-tool orchestration (outside this skill's scope).
- Sibling skill: `claude-ecosystem` — prompt-caching thresholds relevant to stable tool blocks.
- Sibling skill: `external-api-docs` — current SDK signatures for `response_format`, `tools`, Gemini SDK, Bedrock wrapper.

## External Sources

- OpenAI, *Structured outputs guide* — strict JSON Schema, `additionalProperties: false`, `required` invariants.
- Anthropic, *Structured outputs* — tool-based output, schema rewriting, tool-use overhead.
- `instructor` (Python) — https://python.useinstructor.com/ — retry-on-ValidationError pattern.
- `instructor-js` (TypeScript).
- `outlines`, `guidance` (constrained decoding for open-weights / local).
- 2026 provider-comparison articles — Medium/Rost Glukhov consolidated comparison; BuildMVPfast 2026 guide.
