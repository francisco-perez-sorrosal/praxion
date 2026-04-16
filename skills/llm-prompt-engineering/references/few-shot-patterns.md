# Few-Shot Patterns

Minimal, structured, and chain-of-demos few-shot prompting; example selection strategies; debiasing research; dynamic retrieval; ordering and positional-bias research distilled for production use.

Back to: [../SKILL.md](../SKILL.md)

## When to Read This File

Load this deep dive when you are:

- Designing a new few-shot prompt and uncertain how many exemplars to ship.
- Debugging a prompt whose accuracy drops when inputs shift — likely distribution mismatch, label bias, or ordering sensitivity.
- Migrating a prompt across model families and seeing accuracy move unexpectedly.
- Deciding between static exemplar lists vs. dynamic retrieval.
- Balancing few-shot cost vs. accuracy at scale.

`SKILL.md` covers the 2026 consensus (shot count, recency bias, ordering, dynamic retrieval, balancing); this file explains *why* those rules hold, the research behind them, and how to operationalize them.

## Shot-Count Sweet Spot: 2–5

### What the evidence says

Across the 2023–2026 literature, accuracy gains flatten after the first few exemplars while prompt cost scales linearly with shots (one extra shot = one extra block of tokens added to every request). Most practical prompts sit in the 2–5 range. Going from zero-shot to one-shot is almost always worth it on instruction-following and extraction tasks; going from five to ten rarely is.

### How to pick N for your prompt

1. Start at **zero-shot**. Draft the task description + output format and run a representative sample.
2. If the output is shape-correct but semantically wrong, add **one exemplar** covering the most common input type.
3. If a specific class of input still fails, add exemplars targeted at that class until you hit the class budget. Stop at five before escalating to a different pattern (retrieval, schema tightening, or fine-tuning).
4. For reasoning-native models (Claude 4.x Opus/Sonnet with extended thinking, GPT-5, o-series, DeepSeek-R1), prefer zero-shot. Few-shot can *reduce* accuracy on reasoning tasks — see the model-family notes below.

### Pattern: minimal few-shot

```text
Classify the customer message into one of: bug, feature, question.

<example>
<input>The login page throws 500 on Safari 17.</input>
<output>bug</output>
</example>

<example>
<input>Please add dark mode to the settings panel.</input>
<output>feature</output>
</example>

<user_input>
{input}
</user_input>
```

Two exemplars. One per class is usually sufficient for a three-class classifier. Expand only when the held-out accuracy drops on a specific class.

### Pattern: structured few-shot

When the output is structured (JSON, XML, named fields), wrap each example in the same tag scaffold the real output will use. Consistency between exemplar shape and instruction shape is the dominant factor in whether the model matches your contract.

```text
Extract the primary action and subject from the user's request.

<example>
<user_input>schedule a 30-min design review with Amy tomorrow at 10am</user_input>
<extraction>
  <action>schedule_meeting</action>
  <subject>design review with Amy</subject>
  <when>tomorrow 10:00</when>
</extraction>
</example>

<user_input>{input}</user_input>
```

Docstrings, field names, and tag names all travel to the model. The structure of the example is itself instruction.

### Pattern: chain-of-demos (stacked exemplars for compositional tasks)

For tasks where the output is the composition of sub-decisions (e.g., classify + extract + summarize in one call), show a demo per sub-decision and a final demo that combines them. The model learns the component steps and the composition pattern separately, which is more sample-efficient than showing only fully-composed examples.

## Recency Bias and End-of-Prompt Positioning

### The effect

The last exemplar in a few-shot block receives more attention than earlier ones. If the last three of five exemplars belong to class A, the model's verdict tilts toward class A (majority-label bias at the tail). This is consistent with positional-bias research going back to 2021 and persists in 2025-era models with reduced amplitude.

### Operational rule

- Place the **most representative** or most-similar-to-the-real-distribution exemplar last.
- Never end a few-shot block with a run of same-class examples — interleave.
- If exemplar order is chosen at runtime (e.g., by retrieval), re-sort so the highest-similarity example appears last.

### Operational rule: randomize when balanced

If classes are balanced and you have no a-priori "most representative" example, randomize the order on each request (or at prompt-compile time). Random permutation reduces variance across evaluation runs.

## Ordering Sensitivity

### The effect

Permutation of few-shot examples has moved benchmark accuracy from chance to near-SOTA on classic tasks. Modern (2025+) models show reduced but non-zero sensitivity; it is safer to treat ordering as a hyperparameter.

### How to handle

- When you change models, **re-test ordering**. The ordering that worked on Claude Sonnet 3.x may not be the ordering that works on Claude Sonnet 4.x.
- For production, include ordering in your prompt-evaluation matrix: test 3–5 orderings and keep the one with best held-out accuracy.
- Treat ordering as part of the **pinned envelope** (see `./versioning.md`). A "v3 prompt" with a different example order is a new version.

## Dynamic Example Retrieval

### Why static lists fail at scale

Static exemplar lists work at prototype scale because the input distribution is narrow. Production traffic is wider. A static list either under-covers the distribution (accuracy drops on long-tail inputs) or over-covers it (token cost inflates without accuracy gain).

### Dynamic retrieval pattern

1. Build an exemplar store: a set of `(input, output)` pairs, ideally with metadata (class, difficulty).
2. Embed each exemplar input at ingest time.
3. At request time, embed the user input and retrieve the top-K most similar exemplars (K = 2–5).
4. Inject them in the prompt with the most similar example last (recency bias).
5. Validate the output; if it fails, log the input for addition to the exemplar store.

### Retrieval backends

- **Small exemplar stores (< ~1K items)**: plain in-memory cosine similarity against a pre-computed embedding matrix — no vector DB needed.
- **Larger stores**: a vector database (pgvector, Qdrant, Weaviate, etc.). The choice is orthogonal to this skill; use whatever the project already runs. Note that the embedding-model family should match the semantic distribution you care about (general-purpose sentence embeddings are fine for English text; code or multilingual cases need dedicated models).
- **Hybrid**: lexical + embedding retrieval re-ranked. Useful when inputs have distinctive keywords (error codes, error messages).

### Retrieval governance

- **Freshness**: rotate the exemplar store when input distribution drifts. Monitor hit-rate (top-1 similarity); sustained drops signal drift.
- **Toxicity and PII**: exemplars shipped to the model must be scrubbed. Treat the exemplar store as a user-content store under your normal data controls.
- **Attribution**: keep a per-exemplar source tag so you can trace a bad output back to the exemplar that biased it.

## Debiasing Strategies

### Majority label bias

If your exemplar labels are unbalanced (e.g., 4 positives and 1 negative in a binary classifier), the model tilts toward the majority label regardless of input content. Mitigations in order of preference:

1. **Balance classes** in the exemplar set. Equal counts per class is the default.
2. **Randomize order** across requests to spread any residual tilt.
3. **Explicit de-bias instruction**: add a line such as `The correct label is not correlated with the label distribution above.` Measurable but weak effect; use as backup.

### Recency bias (tail class clustering)

End-of-prompt clustering of one class biases toward that class. Interleave so the tail is not single-class. If you must keep a clustered tail for another reason (e.g., retrieval-ordered), add a contrastive example at the very end from a different class.

### Common-token bias

If exemplars share a surface feature (same phrase, same formatting quirk), the model over-relies on the surface feature. Audit exemplars for shared tokens that do not belong in the task contract.

### Calibrate-before-use (Zhao et al. 2021)

On classifier-like prompts, the model has a prior over output labels that is independent of the input. The *calibrate-before-use* technique estimates this prior by running a content-free input (e.g., "N/A") through the prompt, then subtracts the prior at inference. The technique still works on reasoning-era models for narrow-class classifiers but is less impactful on open-ended generation. Use on a per-prompt basis when you see persistent class skew that balancing and ordering did not fix.

## Exemplar Diversity

### The principle

Exemplars should span the input distribution — common cases, edge cases, and near-miss cases. Low-diversity exemplar sets over-fit the prompt to one input neighborhood and fail on the long tail.

### How to diversify

- **Cluster real traffic** on embeddings; sample exemplars from each cluster proportional to cluster size.
- **Include "near-miss" negatives**: examples that look like class A but are class B, and vice versa. These examples are sample-efficient because they teach the decision boundary.
- **Cover failure modes**: each production-observed failure mode should have at least one exemplar demonstrating the correct handling. This is the counterpart to regression-test fixtures in code (see `./prompt-testing.md`).

## Anti-Patterns

### Leaking the answer via look-alike exemplars

An exemplar whose input almost matches the real input but with a different ground-truth answer teaches the model to pattern-match on surface features rather than reason. Symptom: the model produces the exemplar's answer when given a paraphrased version of the exemplar's input. Remedy: remove the exemplar or substantially vary its surface features.

### Distribution mismatch between exemplars and real traffic

The most common silent failure mode. Symptom: held-out accuracy on your test set stays high while production accuracy drops. Remedy: rebuild exemplars from a recent production sample (scrubbed, labeled) rather than a curated-for-prototype set.

### Unwrapped exemplars mixed with instructions

If exemplars and instructions share the same formatting (same headings, same tags), the model may misread an exemplar input as a new instruction. Remedy: wrap exemplars in consistent delimiters. On Claude, XML tags (`<example>…</example>` or equivalent) are idiomatic. On OpenAI, nested delimiters like triple-backticks or explicit section headers work equivalently; see `./prompt-injection-hardening.md` for the broader delimiter discussion.

### Over-large exemplar blocks

Each exemplar costs tokens on every request. If five exemplars are 2000 tokens, a 1M-request month costs 2B tokens just for exemplars. Budget the exemplar block against the expected throughput and cost-per-token; favor shorter, sharper exemplars.

## Model-Family Notes

### Claude 4.x Opus / Sonnet (reasoning-native)

- Tolerates few-shot well. Ordering-sensitive but recovers faster than prior generations.
- Prefers XML-delimited exemplars.
- Extended thinking mode: **prefer zero-shot** with a clear task description. If few-shot is needed, test head-to-head against zero-shot with the same `effort` setting. See `./reasoning-and-cot.md`.

### Claude Haiku 4.x (non-reasoning)

- Moderate tolerance; benefit saturates quickly (often after 2–3 exemplars).
- Manual chain-of-thought in the exemplar output still helps on multi-step tasks.

### OpenAI GPT-5 (reasoning tiers)

- Few-shot is variable by tier. `medium` effort often works better with 1–2 exemplars than with 5.
- Start zero-shot; add exemplars only if output misses.

### OpenAI o-series

- Zero-shot preferred. Few-shot can hurt. If you must use few-shot, keep exemplar count at 1–2 and prefer short, high-signal cases.

### GPT-4.1 and other non-reasoning OpenAI models

- High few-shot tolerance. 2–5 exemplars is the sweet spot.
- Nested JSON or XML exemplars are both fine; choose whichever matches the output format.

### Gemini 2.5 (Pro / Flash with thinking)

- Moderate tolerance. Structured output via JSON Schema plays well with wrapped exemplars.
- Verify current SDK signature via `external-api-docs` before committing to a thinking-mode exemplar pattern.

### DeepSeek-R1 and other reasoning-only models

- **Zero-shot only.** Few-shot *degrades* accuracy. Author recommendation: clear problem statement + explicit output format, no exemplars.

### Open-weights (Llama 3.x+, Mistral, Qwen)

- High tolerance; ordering sensitivity higher than closed models.
- Benefit from larger exemplar counts (3–8) on underspecified tasks; the marginal exemplar cost is higher relatively since these models are often self-hosted with finite throughput.

## Cross-References

- `../SKILL.md` — overview, model-family matrix, trigger terms.
- `./reasoning-and-cot.md` — when to *drop* few-shot in favor of reasoning-native modes.
- `./structured-output.md` — wrapping exemplars when the output is a structured schema.
- `./versioning.md` — treating exemplar order and count as part of the pinned envelope.
- `./prompt-testing.md` — regression detection when exemplars change.
- `./prompt-injection-hardening.md` — delimiter strategy for user-data vs. exemplars.
- `../assets/envelope-manifest.yaml` — where exemplar-set hash can be pinned alongside the call envelope.
- Sibling skill: `claude-ecosystem` — for Claude-family-specific prompt-caching thresholds that interact with few-shot block stability.
- Sibling skill: `external-api-docs` — fetch current SDK signatures before pinning exemplar delivery code.

## External Sources

- Zhao et al. 2021, *Calibrate Before Use* — majority label / recency / common-token bias.
- Lu et al. 2022, *Fantastically Ordered Prompts* — ordering sensitivity at permutation scale.
- ICCS 2025 paper on positional bias of in-context learning — persistence in 2025 models.
- Anthropic, *Use XML tags to structure your prompts* — delimiter guidance for Claude.
- DeepSeek-R1 model card — zero-shot recommendation.
- Mem0, *Few-Shot Prompting Guide 2026* — consolidated consensus.
