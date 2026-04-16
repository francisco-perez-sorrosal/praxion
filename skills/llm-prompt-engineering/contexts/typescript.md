# TypeScript Context -- llm-prompt-engineering

TypeScript-specific call shapes, retry loops, and test patterns for prompts that reach a production LLM. Load alongside the generic [llm-prompt-engineering](../SKILL.md) skill.

Back to: [../SKILL.md](../SKILL.md)

## SDK Versions Targeted

<!-- last-verified: 2026-04-16 -->

| Package | Version | Role |
|---------|---------|------|
| `@anthropic-ai/sdk` | 0.30.x+ | Anthropic Messages API client |
| `openai` | 4.x+ | OpenAI client (chat.completions, Responses API, `.parse()`) |
| `zod` | 3.23.x+ | Schema, inference via `z.infer<typeof Schema>` |
| `@instructor-ai/instructor` | 1.x | Multi-provider, Zod-validated retry loop (TS port of Python `instructor`) |
| `promptfoo` | latest pinned | YAML-driven single-prompt regression runner |

Modern TypeScript (5.x) with strict mode enabled, ESM imports. Node.js 20+ for `node:test` usage.

**Version drift.** Verify current signatures via the [`external-api-docs`](../../external-api-docs/SKILL.md) skill before shipping. The TS SDKs move as quickly as the Python ones.

## Zod + `instructor-js` Retry Loop

The TS equivalent of the Python `instructor` pattern. `@instructor-ai/instructor` wraps the OpenAI or Anthropic client, adds `response_model: { schema, name }`, and runs a bounded retry-on-validation-error loop driven by the Zod parser.

```typescript
import Anthropic from "@anthropic-ai/sdk";
import Instructor from "@instructor-ai/instructor";
import { z } from "zod";

const MAX_RETRIES = 3;
const MODEL = "claude-sonnet-4-x"; // pinned via external-api-docs

const ExtractedFields = z.object({
  title: z.string().describe("Document title, verbatim from the source."),
  summary: z.string().describe("One-sentence summary, <=40 words."),
  tags: z.array(z.string()).min(3).max(5).describe("3-5 lowercase topic tags."),
});
type ExtractedFields = z.infer<typeof ExtractedFields>;

const client = Instructor({
  client: new Anthropic(),
  mode: "TOOLS", // tool-use structured output on Anthropic
});

export async function extract(document: string): Promise<ExtractedFields> {
  return client.messages.create({
    model: MODEL,
    max_tokens: 1024,
    max_retries: MAX_RETRIES,
    response_model: {
      schema: ExtractedFields,
      name: "ExtractedFields",
    },
    messages: [
      { role: "user", content: buildPrompt(document) },
    ],
  });
}

function buildPrompt(document: string): string {
  return [
    "Extract the structured fields from the document below.",
    "<document>",
    document,
    "</document>",
  ].join("\n");
}
```

**Type inference travels automatically.** `z.infer<typeof ExtractedFields>` gives you the validated TS type; no duplicate type declaration.

### Retry tuning

- **Cap at 2-3.** Same reasoning as Python: degenerate inputs never parse and drain tokens.
- **Error surfacing.** On retry exhaustion, `instructor-js` throws an error wrapping the final Zod `ZodError`. Catch, log `error.issues`, and re-throw with context so the failing field is visible in production logs.
- **Bounded `max_tokens`.** Match the schema's expected footprint -- overallocating invites runaway output.

### Alternative: native SDK strict mode (no instructor-js)

Some teams prefer to avoid the `instructor-js` dependency. Modern OpenAI and Anthropic SDKs ship first-party structured-output helpers that pair natively with Zod:

- OpenAI: `openai.chat.completions.parse()` accepts a Zod schema via `zodResponseFormat(...)` from the `openai/helpers/zod` submodule.
- Anthropic: build a tool with `input_schema: zodToJsonSchema(Schema)` and parse the tool-use block manually with `Schema.safeParse(...)`.

This trades the retry-on-validation loop for one less dependency. If your prompts are mature and rarely fail validation, native mode is cleaner.

## Anthropic TS SDK Call Shape

Direct call shape when you need lower-level control. Structured output goes through tool-use (same constraint as Python).

```typescript
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

const Classification = z.object({
  label: z.enum(["bug", "feature", "question"]),
  confidence: z.number().min(0).max(1),
});
type Classification = z.infer<typeof Classification>;

const client = new Anthropic();

export async function classify(message: string): Promise<Classification> {
  const response = await client.messages.create({
    model: "claude-sonnet-4-x",
    max_tokens: 256,
    system: "You classify user messages. Call the `classify` tool exactly once.",
    tools: [
      {
        name: "classify",
        description: "Record the classification for the user message.",
        input_schema: zodToJsonSchema(Classification) as Anthropic.Messages.Tool.InputSchema,
      },
    ],
    tool_choice: { type: "tool", name: "classify" },
    messages: [{ role: "user", content: message }],
  });

  const toolBlock = response.content.find((b) => b.type === "tool_use");
  if (!toolBlock || toolBlock.type !== "tool_use") {
    throw new Error("Expected tool_use block in response");
  }
  // Validate at the boundary -- do not trust strict mode alone.
  return Classification.parse(toolBlock.input);
}
```

### Call-shape gotchas (shared with Python)

- **Anthropic SDK silently rewrites schema constraints** (`.min()`, `.max()`, `.regex()` get moved into the description). Always re-validate with Zod at the boundary.
- **Tool-use adds ~313-346 tokens of system overhead.** Matters at scale.
- **First request pays grammar compilation latency;** compiled grammars cached ~24h.
- **Prompt caching** works the same way as the Python client -- see [`claude-ecosystem`](../../claude-ecosystem/SKILL.md) for thresholds.

## OpenAI TS SDK Call Shape

Two modes, same advice: prefer the schema-backed one.

### JSON mode (avoid for new builds)

```typescript
import OpenAI from "openai";

const client = new OpenAI();

const response = await client.chat.completions.create({
  model: "gpt-5",
  response_format: { type: "json_object" },
  messages: [
    {
      role: "system",
      content: "Return a JSON object with keys: label (string), confidence (number).",
    },
    { role: "user", content: "The login button throws 500." },
  ],
});
```

No schema enforcement -- the model still hallucinates fields. Validate with Zod anyway. For anything past a prototype, use the strict mode below.

### Structured Outputs (`json_schema` strict, default)

```typescript
import OpenAI from "openai";
import { zodResponseFormat } from "openai/helpers/zod";
import { z } from "zod";

const Classification = z.object({
  label: z.enum(["bug", "feature", "question"]),
  confidence: z.number().min(0).max(1),
});

const client = new OpenAI();

export async function classify(message: string) {
  const response = await client.chat.completions.parse({
    model: "gpt-5",
    response_format: zodResponseFormat(Classification, "Classification"),
    messages: [
      { role: "system", content: "Classify the user message." },
      { role: "user", content: message },
    ],
  });

  // `.parsed` is already validated and typed as z.infer<typeof Classification>.
  return response.choices[0].message.parsed;
}
```

Or the manual `response_format` shape:

```typescript
response_format: {
  type: "json_schema",
  json_schema: {
    name: "Classification",
    schema: zodToJsonSchema(Classification),
    strict: true,
  },
}
```

### Strict-mode gotchas

- **`additionalProperties: false` is mandatory** on every object in the schema. `zodToJsonSchema` does not always emit it -- use `zodResponseFormat` from the official OpenAI helper submodule, which patches the schema correctly.
- **All properties must be in `required`.** Zod's `.optional()` lowers to an optional schema, which strict mode rejects unless handled explicitly. Model optional fields as `z.union([z.string(), z.null()])` and place them in `required`.
- **Reasoning-effort cost.** Same GPT-5 caveat as Python -- `high` uses ~23x tokens of `minimal` for marginal accuracy lift on structured tasks.

## Promptfoo: Generating YAML Configs From TypeScript

Promptfoo consumes YAML, but the test matrix is often easier to maintain in TypeScript -- especially for large parametrized suites shared across multiple prompt versions. Generate the YAML at build time.

The canonical example lives at [`../assets/promptfoo-prompt-suite.yaml`](../assets/promptfoo-prompt-suite.yaml). For programmatic generation:

```typescript
// scripts/generate-promptfoo-suite.ts
import { writeFileSync } from "node:fs";
import { stringify } from "yaml";

type TestCase = {
  description: string;
  vars: Record<string, string>;
  assert: Array<Record<string, unknown>>;
};

const CASES: Array<{ input: string; expected: string }> = [
  { input: "The login button throws 500 on Safari 17.", expected: "bug" },
  { input: "Please add dark mode.", expected: "feature" },
  { input: "How do I invite teammates?", expected: "question" },
];

const tests: TestCase[] = CASES.map(({ input, expected }) => ({
  description: `Classifies "${input.slice(0, 40)}..." as ${expected}`,
  vars: { input },
  assert: [
    { type: "contains", value: expected },
    // Negative assertion: output must not include other labels.
    ...["bug", "feature", "question"]
      .filter((label) => label !== expected)
      .map((label) => ({ type: "not-contains", value: label })),
  ],
}));

const suite = {
  description: "Classifier single-prompt regression suite",
  providers: [
    {
      id: "anthropic:messages:claude-sonnet-4-x",
      config: { temperature: 0, max_tokens: 64 },
    },
  ],
  prompts: [{ label: "classifier-v1", raw: CLASSIFIER_PROMPT }],
  tests,
};

writeFileSync("promptfoo.generated.yaml", stringify(suite));
```

Run: `npx promptfoo@latest eval -c promptfoo.generated.yaml`. Regenerate on every prompt-version bump so the suite and the prompt stay locked.

**Boundary reminder.** Promptfoo covers single-prompt assertions. For agent-level trajectory evals, defer to [`agent-evals`](../../agent-evals/SKILL.md).

## Node Test Runner Integration

The built-in `node:test` runner is sufficient for most single-prompt test suites; Vitest is the common alternative when you want richer snapshots, a watch mode, and UI.

### `node:test` parametrized tests

```typescript
// tests/classifier.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { classify } from "../src/classifier.js";

const CASES: Array<{ input: string; expected: string }> = [
  { input: "The login button throws 500 on Safari 17.", expected: "bug" },
  { input: "Please add dark mode.", expected: "feature" },
  { input: "How do I invite teammates?", expected: "question" },
];

for (const { input, expected } of CASES) {
  test(`classifies "${input.slice(0, 30)}..." as ${expected}`, async () => {
    const result = await classify(input);
    assert.equal(result.label, expected);
    assert.ok(result.confidence >= 0 && result.confidence <= 1);
  });
}
```

Run: `node --test tests/*.test.ts` (with a loader such as `tsx` or native TS support on recent Node versions).

### Vitest alternative

```typescript
import { describe, expect, test } from "vitest";
import { classify } from "../src/classifier.js";

describe("classifier", () => {
  test.each([
    ["The login button throws 500 on Safari 17.", "bug"],
    ["Please add dark mode.", "feature"],
    ["How do I invite teammates?", "question"],
  ])("classifies %s as %s", async (input, expected) => {
    const result = await classify(input);
    expect(result.label).toBe(expected);
  });
});
```

### Flaky-model handling pattern (shared with Python)

Distinguish **soft fails** (semantic drift on a probabilistic output) from **hard fails** (schema violation).

```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { ZodError } from "zod";
import { extract } from "../src/extractor.js";

const DOCUMENT = "Sample document about TypeScript 5.x release notes.";

// pass@3: retry on semantic drift, fail hard on schema violation.
for (let attempt = 0; attempt < 3; attempt++) {
  test(`extraction semantic pass@3 (attempt ${attempt + 1})`, async () => {
    let result;
    try {
      result = await extract(DOCUMENT);
    } catch (err) {
      if (err instanceof ZodError) {
        assert.fail("schema violation -- hard fail, do not retry");
      }
      throw err;
    }
    assert.ok(result.summary.toLowerCase().includes("typescript"));
  });
}

test("extraction schema hard fail", async () => {
  // ZodError bubbles up and the test fails deterministically.
  // Do not wrap in try/catch that swallows it.
  const result = await extract(DOCUMENT);
  assert.ok(result);
});
```

**Rule (shared with Python).** Retry on soft fail (semantic drift). Fail hard on schema violation. A schema violation means the prompt regressed or the SDK changed -- that is a real bug and should page, not retry.

### Snapshot assertions

Vitest's built-in snapshots work well for stable-shape outputs (extraction, classification). For `node:test`, use the native `assert.snapshot()` API (Node 22.3+) or serialize to JSON and compare against a checked-in fixture. Snapshot *shape*, not probabilistic text content.

## Version Drift Checkpoint

Before shipping any code against a pinned SDK version, run the [`external-api-docs`](../../external-api-docs/SKILL.md) skill -- `chub_search` for the package, `chub_get` for the specific reference -- and compare the documented call shape against what this file describes. Both `@anthropic-ai/sdk` and `openai` ship breaking-within-major bumps frequently; this context file is a starting point, not a contract.
