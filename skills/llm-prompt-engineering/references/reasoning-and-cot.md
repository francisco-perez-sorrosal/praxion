# Reasoning and Chain-of-Thought

The 2026 inversion — manual "think step by step" now hurts reasoning-native models; scaffold patterns for non-reasoning models; self-consistency variants; when (and when not) to use inline think-tags.

Back to: [../SKILL.md](../SKILL.md)

## When to Read This File

Load this deep dive when you are:

- Choosing between `reasoning_effort` / `thinking: adaptive` and a manual chain-of-thought prompt.
- Debugging a prompt that became *worse* after you added "think step by step" to a reasoning-native model.
- Deciding whether to pay for self-consistency (multiple samples + vote).
- Designing a decomposition pattern (plan-and-solve, least-to-most) for a multi-step task.
- Migrating a prompt from a non-reasoning model to a reasoning-native one.

`SKILL.md` covers the decision procedure and a short cost-discipline note. This file explains the 2026 reasoning-native inversion in depth, the scaffold patterns still useful on non-reasoning models, and the self-consistency cost/accuracy landscape.

## The 2026 Inversion (Lead Here)

### The historical advice

From 2022 through mid-2024, the standing guidance was: when accuracy on arithmetic, commonsense, or symbolic tasks matters, add `"Let's think step by step"` (zero-shot CoT) or provide few-shot exemplars that show a worked reasoning trace. On non-reasoning models of that era, this materially improved accuracy on GSM8K, SVAMP, AQuA, and similar benchmarks.

### What changed

Reasoning-native model families (Claude 4.x Opus/Sonnet with extended thinking; OpenAI GPT-5 at any tier; OpenAI o-series; Gemini 2.5 with thinking; DeepSeek-R1) have a trained internal reasoning pass that runs before the user-visible output. This internal pass is what the model does when you ask it a hard question and do nothing else. When you prepend "think step by step" or include CoT exemplars, you are competing with that trained pass by biasing the decoder toward a surface-level, English-language, "here are my steps" pattern.

### Why the bias harms accuracy

- The trained reasoning pass allocates compute adaptively based on problem difficulty. A fixed textual scaffold like "think step by step" tends to produce a uniform, under-deep expansion.
- The surface pattern ("first, let's… then we can see…") is a *token-prediction target* that is easier to match than a correct answer. The model can satisfy the surface pattern while skipping the actual reasoning step.
- For DeepSeek-R1 and similar models, authors have published explicit recommendations against few-shot and against manual CoT; measured accuracy is higher with a clean problem statement + output format alone.

### The rule

1. If the model is reasoning-native, **use the native effort knob** (Anthropic `thinking: {type: "adaptive", effort: ...}`, OpenAI `reasoning_effort`, Gemini thinking budget). Do not add manual CoT. Do not add reasoning-trace exemplars.
2. If the model is **not** reasoning-native, manual CoT and self-consistency still work — see below.
3. If you do not know which family the model is in, check the current SDK signature via `external-api-docs` and the `../SKILL.md` model-family matrix before committing.

## Reasoning-Effort Knobs by Family

### Anthropic (Claude 4.x Opus / Sonnet / Haiku)

- `thinking: {type: "adaptive", effort: "low" | "medium" | "high"}` on Opus and Sonnet. Adaptive mode routes compute based on problem complexity; `effort` sets the upper bound.
- Constraint: `temperature` must be unset or exactly `1` when extended thinking is active. Any other value errors out. This is not a soft guideline — the SDK rejects the request.
- Haiku 4.x is non-reasoning. Use manual CoT there; the adaptive API is not applicable.
- The older `budget_tokens` parameter (numeric token budget for thinking) is deprecated on 4.x Opus/Sonnet in favor of adaptive. Continue to see `claude-ecosystem` for the exact current parameter shape; this skill deliberately avoids restating it to prevent drift.

### OpenAI (GPT-5, o-series)

- `reasoning_effort: "minimal" | "low" | "medium" | "high"`.
- Start at `medium`. Profile cost and accuracy before bumping to `high` — the cost curve is steep relative to the accuracy gain (roughly 23× the tokens for ~5% accuracy on many tasks, though exact numbers vary by benchmark).
- On cost-sensitive workloads, test `gpt-5-mini` (or the current mini equivalent) at `medium` against `gpt-5` at `high`. The smaller model at medium effort often wins on cost per correct answer.
- The o-series follows the same `reasoning_effort` API; do not add manual CoT.

### Gemini 2.5 (Pro / Flash with thinking)

- Thinking tokens are exposed via the native SDK; exact parameter names and defaults drift. Verify current via `external-api-docs` before pinning.
- Flash without thinking behaves as a non-reasoning model for CoT-decision purposes.

### DeepSeek-R1

- No effort knob; reasoning is always on.
- **Zero-shot with a clean problem statement + output format.** No CoT scaffold, no few-shot.

## Patterns That Still Work on Non-Reasoning Models

### Zero-shot CoT

```text
Solve the following problem step by step, then write "Final answer:" followed by the numeric result.

Problem: {problem}
```

Non-reasoning models (Claude Haiku 4.x, GPT-4.1, Gemini 2.5 Flash without thinking, most open-weights < ~70B) still benefit from this scaffold on arithmetic, symbolic, and commonsense reasoning tasks. Measured lifts vary by task; expect mid-single-digit-to-low-double-digit percentage gains on GSM8K-like benchmarks.

### Few-shot CoT

When zero-shot CoT is insufficient, provide 2–3 exemplars that show the reasoning trace in the target format. The exemplar's reasoning should be clear and minimal; do not pad. See `./few-shot-patterns.md` for exemplar design.

### Plan-and-solve

```text
Step 1: Produce a plan to solve the problem below — list 2-5 intermediate goals.
Step 2: Execute the plan one step at a time, verifying each step before moving on.
Step 3: State the final answer after "Final answer:".

Problem: {problem}
```

Plan-and-solve reduces the chance of skipping a step on complex tasks. On reasoning-native models it manifests not as a multi-call chain but as a structured instruction inside a single prompt — the trained reasoning pass handles the execution, while your prompt provides the structure.

### Least-to-most

Decompose the task into strictly increasing sub-problems, solve each in order, and use earlier answers as inputs to later sub-problems. Useful when the task has a clear difficulty gradient (e.g., parsing + extraction + reasoning + formatting).

On reasoning-native models, least-to-most is sometimes unnecessary — the model does it internally. Test before adopting it as a pattern.

### Inline think-tags (Claude-specific)

When you want the model to reason inline and you want the reasoning in the output (for auditing, debugging, or downstream pipelines):

```text
Return your reasoning inside <thinking> tags, then the final answer inside <answer> tags.
```

This works even on reasoning-native Claude. It is complementary to `thinking: adaptive` — the adaptive thinking is still available to the trained reasoning pass; your explicit tags provide a deterministic output shape for downstream consumers. Use when you need reproducible inline reasoning that your test harness can parse.

Caveats:

- Do not confuse `<thinking>` output with the private thinking output from adaptive/extended thinking mode. They are independent surfaces; the adaptive output is API metadata, while `<thinking>` tags are part of the visible response body.
- Inline think-tags add tokens to every response. Gate by config if latency or cost matters.

## Self-Consistency

### What it is

Sample the model K times at nonzero temperature on the same prompt, then aggregate the answers (majority vote for discrete outputs; some form of consensus for free-form). Self-consistency with CoT lifts accuracy on reasoning-sensitive benchmarks by +5–17% depending on task and K.

### The cost problem

Naive self-consistency at K=40 costs 40× the base request. Production rarely tolerates this. Two efficient variants:

- **Confidence-weighted voting (CISC-style)**: weight each sample by the model's stated confidence. Often achieves near-equal accuracy with half the samples.
- **Adaptive stopping**: sample until the top answer exceeds a confidence threshold. On easy problems the adaptive sampler terminates early; on hard problems it keeps sampling. Measured reductions of 46–70% in sample count for equivalent accuracy.

### When to use it

- Offline pipelines where latency is not the constraint (batch evaluation, training data curation).
- High-stakes decisions where the extra cost is justified by the accuracy lift.
- **Not** for interactive UIs without user-visible progress feedback — the latency is prohibitive.

### Relationship to reasoning-effort

On a reasoning-native model at `high` effort, much of the self-consistency benefit is already captured by the trained reasoning pass. Do not stack both unless you have measured that the combination is worth it. The naive path (effort=high + K=40) is the most expensive configuration in the space and rarely the best cost-per-correct-answer point.

## Decomposition Patterns

### When to decompose

Decompose when the task is genuinely multi-step (parse → reason → format; retrieve → rank → select), when each step benefits from different prompts or models, or when you need to audit a specific intermediate step.

Do **not** decompose just because the task is hard; a single well-specified prompt to a reasoning-native model often outperforms a decomposed pipeline on cost and latency.

### Shapes of decomposition

- **Linear pipeline**: A → B → C, each call feeding the next. Easy to debug; each step can use a different model (smaller for parsing, reasoning-native for the hard step, smaller again for formatting).
- **Router then specialist**: a cheap classifier decides which specialist prompt handles the input, then the specialist runs. Effective when tasks are heterogeneous; tune the classifier's exemplars (`./few-shot-patterns.md`).
- **Plan-and-execute inside a single call**: the structured prompt replaces the external pipeline. Cheaper and simpler on reasoning-native models.

### Decomposition and structured output

When decomposing, each step's output is the next step's input. Use structured output (`./structured-output.md`) at each boundary so the handoff is type-safe and testable.

## Superseded Patterns Appendix

Patterns that were load-bearing in 2022–2024 and are now either redundant or actively harmful on reasoning-native models.

| Pattern | Status on reasoning-native models | Status on non-reasoning models |
|---------|-----------------------------------|--------------------------------|
| `"Let's think step by step"` prefix | Harmful — biases surface patterns over trained reasoning | Still lifts accuracy |
| Reasoning-trace few-shot exemplars | Harmful on Claude 4.x extended thinking and OpenAI o-series | Still useful |
| `budget_tokens` numeric scheme (Claude) | Deprecated on 4.x Opus/Sonnet; use adaptive | Not applicable |
| Self-consistency at K=40 | Wasteful at high effort; overlaps trained reasoning | Still meaningful (prefer efficient variants) |
| Manual decomposition into sequential calls for every multi-step task | Often redundant; prefer single structured prompt | Still useful for heterogeneous pipelines |

If you have an existing prompt that uses one of the superseded patterns on a reasoning-native model, migration is usually a simplification — remove the scaffold, set `reasoning_effort`/adaptive `effort`, and re-measure.

## Cross-References

- `../SKILL.md` — the decision procedure (which knob on which model) lives there; this file explains why.
- `./few-shot-patterns.md` — reasoning-exemplar design for non-reasoning models.
- `./structured-output.md` — structured handoffs when decomposing.
- `./versioning.md` — pin `reasoning_effort` / `thinking` parameters in the envelope manifest.
- `./prompt-testing.md` — non-determinism discipline when self-consistency or reasoning effort is in play.
- Sibling skill: `claude-ecosystem` — the current parameter shape for `thinking: adaptive`, deprecated `budget_tokens`, and the `temperature=1` constraint on extended thinking.
- Sibling skill: `external-api-docs` — fetch current SDK signatures before pinning reasoning knobs.
- Sibling skill: `agent-evals` — multi-turn and trajectory-level reasoning eval architecture (this file and `prompt-testing.md` cover only single-call assertions).

## External Sources

- Wei et al. 2022, *Chain-of-Thought Prompting*.
- Kojima et al. 2022, *Large Language Models are Zero-Shot Reasoners* — the "think step by step" origin.
- Wang et al. 2022, *Self-Consistency Improves Chain-of-Thought* — GSM8K / SVAMP gains at K=40.
- Zhou et al. 2023, *Least-to-Most Prompting*.
- Wang et al. 2023, *Plan-and-Solve Prompting*.
- 2025 follow-ups on CISC, confidence-weighted voting, and adaptive stopping — see arxiv 2502.06233 and 2511.12309.
- Anthropic docs — extended thinking, adaptive thinking.
- OpenAI docs — `reasoning_effort` and o-series guidance.
- DeepSeek-R1 model card — zero-shot recommendation.
- PromptHub — *Prompt Engineering with Reasoning Models* (consolidated practitioner guidance).
