---
name: llm-prompt-engineering
description: Prompt engineering for LLMs -- few-shot patterns, chain-of-thought, reasoning-effort
  control, structured output via Pydantic/Zod, prompt versioning, and prompt testing
  (single-prompt regression assertions). Use when designing prompts for production
  LLM calls, writing system prompts, debugging output-quality issues, migrating across
  model versions, picking a prompt-management platform, or establishing prompt regression
  tests. Framework-agnostic; defers to claude-ecosystem for Claude-specific API features,
  agentic-sdks for agent-loop plumbing, agent-evals for deeper eval design, and external-api-docs
  for current SDK signatures.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
staleness_sensitive_sections:
  - "Model Family Matrix"
  - "Platform Comparison"
  - "Gotchas"
---

# LLM Prompt Engineering

Systematic prompt design for production LLM calls. Covers few-shot patterns, chain-of-thought and reasoning-effort control, structured output via Pydantic/Zod, prompt versioning, and single-prompt testing. Framework-agnostic: the principles hold across Claude, GPT-5, Gemini, and open-weights models.

**Terminology note.** Karpathy's "context engineering" framing now dominates 2026 industrial discourse. Treat *prompt engineering* as the subset of context engineering concerned with the instruction-and-example portion of the context window. Retrieval, memory, summarization, and tool-result curation — the orchestration layer — are adjacent territory, out of scope for this skill.

**Satellite files** (loaded on-demand):

- [references/few-shot-patterns.md](references/few-shot-patterns.md) -- calibrate-before-use, dynamic retrieval tooling, positional-bias research, debiasing strategies
- [references/reasoning-and-cot.md](references/reasoning-and-cot.md) -- self-consistency variants, decomposition patterns, extended-thinking parameters, superseded-patterns appendix
- [references/structured-output.md](references/structured-output.md) -- provider-specific code patterns, Pydantic/Zod-as-prompt idioms, retry-repair loop, open-weights constraints
- [references/versioning.md](references/versioning.md) -- platform deep comparison, DSPy/MIPROv2 workflow, prompt-caching-friendly layout, envelope-pinning template
- [references/prompt-testing.md](references/prompt-testing.md) -- Promptfoo YAML, DeepEval pytest, LLM-judge bias mitigations, single-prompt vs agent-level boundary
- [references/prompt-injection-hardening.md](references/prompt-injection-hardening.md) -- author-side hardening, XML delimiters, instruction-after-data, OWASP LLM-01 pointers

**Language contexts** (load per language):

- [contexts/python.md](contexts/python.md) -- `instructor` + Pydantic retry loop, Anthropic/OpenAI SDK call shapes, pytest integration
- [contexts/typescript.md](contexts/typescript.md) -- Zod + `instructor-js`, native SDK `strict: true`, Promptfoo YAML-from-TS, Node test-runner

**On-disk templates** (optional):

- [assets/pydantic-retry-template.py](assets/pydantic-retry-template.py) -- minimal retry-on-ValidationError loop
- [assets/promptfoo-prompt-suite.yaml](assets/promptfoo-prompt-suite.yaml) -- starter Promptfoo suite with contains/not-contains/llm-rubric assertions
- [assets/envelope-manifest.yaml](assets/envelope-manifest.yaml) -- full-envelope pinning template (model, temp, top_p, max_tokens, schema hash, rollout)

## When to Use This Skill

| Use for | Defer to |
|---------|----------|
| Designing a new production prompt (system + user) | — |
| Picking few-shot count, ordering, dynamic retrieval | — |
| Deciding whether to add chain-of-thought or use reasoning-effort | — |
| Structuring a Pydantic/Zod model as the output contract | — |
| Picking a prompt-management platform, pinning the call envelope | — |
| Writing single-prompt regression assertions | — |
| Migrating a prompt across model families or versions | — |
| Claude model IDs, API features, prompt-caching block sizes | `claude-ecosystem` |
| Agent-loop plumbing, tool registration, MCP protocol | `agentic-sdks`, `mcp-crafting` |
| Trajectory evals, LLM-as-judge rubric engineering, eval CI architecture | `agent-evals` |
| Current SDK method signatures, endpoint parameters | `external-api-docs` |
| Runtime prompt-injection detection in shipped apps | `context-security-review` |
| Claude Code subagent configuration (agent files, system prompts) | `agent-crafting` |

## Gotchas

- **Manual CoT hurts reasoning-native models.** Adding "think step by step" to Claude Opus 4.x with extended thinking, GPT-5 at medium+, o-series, or DeepSeek-R1 often *reduces* accuracy by biasing surface patterns over end-to-end reasoning. Use the model's native effort knob instead.
- **`budget_tokens` is deprecated on Claude 4.x Opus/Sonnet** in favor of `thinking: {type: "adaptive"}` + effort. Document both only if you must support older tiers; prefer adaptive. See `claude-ecosystem` for the current parameter shape.
- **Few-shot majority label bias = end-of-prompt class clustering.** If your last 3 of 5 exemplars are class A, the model tilts toward A. Balance class counts, randomize ordering, or add an explicit de-bias instruction.
- **OpenAI strict mode silently fails without `additionalProperties: false`.** In `response_format: {type: "json_schema", strict: true}`, every property must be in `required` AND the schema must set `additionalProperties: false`. Omitting either produces empty or malformed output on some model versions — no error.
- **Anthropic SDK silently rewrites your JSON Schema.** Constraints like `minimum`, `maximum`, `minLength`, `pattern` get moved into the description and validated post-generation, not as hard decoding constraints. Treat the schema as a spec, validate at the boundary.
- **Tool-use adds ~313–346 tokens of system overhead on Anthropic.** Matters at scale — benchmark before assuming tool-based structured output is "free."
- **`temperature=0` does not guarantee determinism.** Sampling may still vary across backend revisions, hardware, and batch boundaries. Tests must accommodate drift (pass@k, semantic equivalence), not exact-match.
- **Prompt caching silently ignores blocks below threshold.** 1024 tokens on Opus/Sonnet, 2048 on Haiku. Under-threshold `cache_control` markers produce no cache hit and no error — just an unexplained cost. See `claude-ecosystem`.
- **DeepSeek-R1 degrades with few-shot prompts.** Authors recommend zero-shot with a clear problem statement + explicit output format. Test before assuming your few-shot pattern transfers.
- **LLM-as-judge position bias flips verdicts >10%.** Swap `A` vs `B` order and the preferred output may change. Always run paired-order evaluation and aggregate, not single-order. See `agent-evals` for mitigation rubrics.
- **Retry loops without a bound blow up token budgets.** Cap at 2–3 retries on a degenerate input; log the failure rather than retrying indefinitely.
- **Tool-based structured output on Anthropic caches grammars ~24h.** First request pays the compilation latency; stable schemas amortize. Don't benchmark cold-path and assume steady-state cost.

## Model Family Matrix

<!-- last-verified: 2026-04-16 -->

Reasoning capability and prompting discipline now diverge by family. The "always add CoT" rule from 2023 inverts on reasoning-native models — see **Reasoning-Native Prompts** below.

| Family | Tier | CoT / Reasoning guidance | Few-shot tolerance | Structured output mode |
|---|---|---|---|---|
| Claude 4.x Opus | Reasoning (extended thinking) | `thinking: {type: "adaptive", effort: ...}`. Skip manual CoT. XML `<thinking>` tags for deterministic inline reasoning | High; ordering-sensitive but recovers | Tool-based with `strict: true` on tool schema |
| Claude 4.x Sonnet | Reasoning (hybrid) | Same as Opus; default `effort: medium` | High | Tool-based with `strict: true` |
| Claude Haiku 4.x | Non-reasoning | Manual CoT still helps on multi-step tasks | Moderate; benefit saturates quickly | Tool-based with `strict: true` |
| OpenAI GPT-5 (all tiers) | Reasoning | `reasoning_effort` ∈ `{minimal, low, medium, high}`. Start at `medium`; profile before `high` (~23× tokens for ~5% gain). GPT-5-mini at medium often beats GPT-5 high on cost/quality | Variable; prefer zero-shot, add shots only if output misses | `response_format: {type: "json_schema", strict: true}` + `additionalProperties: false` |
| OpenAI o-series | Reasoning | Use `reasoning_effort`. Do not add manual CoT | Low; often zero-shot | Same as GPT-5 |
| OpenAI GPT-4.1 | Non-reasoning | Manual zero-shot CoT + optional self-consistency | High | Strict mode available |
| Gemini 2.5 (Pro/Flash) | Reasoning (thinking tokens) | Supports adaptive thinking; check current SDK signature via `external-api-docs` before pinning | Moderate | JSON-Schema-backed structured output via native SDK |
| DeepSeek-R1 | Reasoning | Zero-shot only; few-shot **degrades** accuracy | Zero | Tool-based via OpenAI-compatible API |
| Open-weights (Llama 3.x+, Mistral, Qwen) | Mostly non-reasoning | Manual CoT essential; self-consistency meaningful | High | `outlines` or `guidance` for hard constraints |

**Do not pin exact model version numbers in code unless the project's `external-api-docs` dependency audit has confirmed them.** Use family-level language ("Claude 4.x Opus tier", "GPT-5 medium") in prompts and runbooks; pin specific IDs only at the deployment envelope (see **Prompt Versioning**).

## Few-Shot Patterns

### Consensus, 2026

- **Shot count sweet spot: 2–5.** Accuracy gains flatten after the first few examples while token cost scales linearly. One-shot first; add more only if output still misses.
- **Recency bias is load-bearing.** The last example gets more attention — place the most representative case *last*. End-of-prompt class clustering biases predictions toward the trailing class (majority label bias at the tail).
- **Ordering sensitivity persists** even on 2025-era models. Permutation alone has moved accuracy between chance and near-SOTA on classic benchmarks. Re-test ordering when migrating models.
- **Dynamic retrieval beats static lists in production.** Use semantic similarity to pull the most relevant exemplars per input. Static lists are for prototypes.
- **Balance classes; diversify inputs.** Exemplar diversity should span the expected input distribution from common to edge cases. Unbalanced labels induce majority label bias.

### Anti-patterns

- Leaking the *answer* to look-alike inputs — the model pattern-matches instead of reasoning.
- Distribution mismatch between exemplars and real traffic. The #1 quiet failure mode in production.
- Unwrapped exemplars mixed with instructions. Use consistent delimiters (XML tags for Claude; `<example>…</example>` is conventional, no canonical name).

Deep dive: [references/few-shot-patterns.md](references/few-shot-patterns.md).

## Reasoning-Native Prompts

**Start here:** The "always add 'think step by step'" advice from 2023 is actively harmful on reasoning-native models. It biases the decoder toward surface patterns and suppresses the model's trained reasoning loop.

### Decision procedure

1. **Identify tier.** Is the target model reasoning-native (Claude 4.x Opus/Sonnet extended thinking, GPT-5, o-series, Gemini 2.5 thinking, DeepSeek-R1)? Or non-reasoning (Haiku 4.x, GPT-4.1, Gemini 2.5 Flash without thinking, open-weights < ~70B)?
2. **Reasoning-native → use the native knob.** Claude: `thinking: adaptive` with `effort`. OpenAI: `reasoning_effort`. Do not add manual CoT. The model's trained reasoning is better than your prompt-engineered chain.
3. **Non-reasoning → manual CoT helps.** Zero-shot `"Let's think step by step"` still lifts accuracy on arithmetic, commonsense, and symbolic tasks. Self-consistency (multiple samples + majority vote) adds another ~5–17% on reasoning-sensitive benchmarks.
4. **Decomposition patterns (plan-and-solve, least-to-most)** help on multi-step tasks for both tiers; on reasoning models they manifest as structured prompts ("Produce a plan. Then execute step-by-step.") rather than multi-call chains.

### Reasoning-effort cost discipline

- GPT-5 high uses roughly 23× the tokens of GPT-5 minimal for ~5% accuracy on many tasks. Measure before bumping.
- Claude extended thinking requires `temperature` unset or exactly 1. Any other value errors.
- Self-consistency is expensive but can be compressed: CISC-style confidence-weighted voting and adaptive stopping cut sample count 46–70% for equivalent accuracy.

Deep dive: [references/reasoning-and-cot.md](references/reasoning-and-cot.md).

## Structured Output Design

### Consensus, 2026

- **Constrained decoding is the production default.** Plain "return JSON" prompts are obsolete. All mainstream providers ship strict-schema modes.
- **The Pydantic/Zod model *is* the prompt.** Type names, docstrings, and `Field(description=...)` text are passed to the model and shape output quality. Write them as if a model reads them — because it does.
- **Validate at the boundary.** Trust nothing returned by the model until a Pydantic/Zod validator has parsed it. Do not rely on the `strict: true` flag alone — defense in depth.
- **Retry on `ValidationError`, bounded.** Feed the validation message back to the next attempt so the model self-corrects. Cap at 2–3 retries; log the failure beyond.

### Decision matrix

| Need | Use |
|------|-----|
| Typed object from free text, Python | Pydantic + `instructor` (or direct SDK strict mode) |
| Typed object from free text, TypeScript | Zod + `instructor-js` or native SDK strict mode |
| Model must call a tool with typed args | Function-calling with `strict: true` on the tool |
| Multi-modal output (text + tool call + JSON side-channel) | Tool-use preferred; `response_format` + tools compose on OpenAI |
| On-device / open-weights | `outlines` or `guidance` for hard constraints; `instructor` works across providers |

### Provider deltas

- **OpenAI**: `response_format: {type: "json_schema", strict: true, schema: ...}` for free-form; `tools` with `strict: true` for function-calling. `additionalProperties: false` is **mandatory**; every property must be in `required`.
- **Anthropic**: No direct `response_format` equivalent. Idiomatic path: tool-based structured output with `strict: true` on the tool schema. SDK silently rewrites constraints like `minimum`/`maximum`/`pattern` into the description and validates post-generation.
- **Google Gemini, Mistral, AWS Bedrock**: JSON-Schema-backed structured output supported; behavior details vary by release. Check `external-api-docs` before pinning.

See [contexts/python.md](contexts/python.md) and [contexts/typescript.md](contexts/typescript.md) for full retry-loop implementations. Deep dive: [references/structured-output.md](references/structured-output.md).

## Prompt Versioning

Prompts are first-class deployable artifacts. They need the same controls as code: versions, labels (dev/staging/prod), audit trail, diff, rollback, A/B traffic split, per-version metadata.

### Pin the full envelope

A "v3 prompt" is only meaningful with the full call envelope pinned:

- Model ID (exact, dated)
- Temperature, top_p, top_k
- Max tokens, stop sequences
- System/user message roles and order
- Structured-output schema (content-addressed hash)
- Tool registrations (names + schemas)
- Reasoning effort (when applicable)

Template: [assets/envelope-manifest.yaml](assets/envelope-manifest.yaml).

### Two-track practice (common)

1. **Git-native.** Prompt files in the repo, reviewed in PRs, deployed with the app. Use for prompts that change with code and need strict version pinning.
2. **Prompt-management platform.** A CMS-style store with API/SDK pull, labels, A/B. Use when product/prompt-ops people iterate without a code release.

Most production teams run both and accept the dual source of truth.

### Rollout discipline

- **Traffic labels beat hard cutovers.** Use `prod`/`canary` / percentage splits rather than replace-in-place.
- **Changelog per version.** Human-readable note of *why* — invaluable six months later when regression-hunting.
- **Cache-friendly structure.** Keep stable prefixes (system prompt, few-shot block) first so prompt-caching hits remain valid across versions. See `claude-ecosystem` for block thresholds.
- **DSPy / MIPROv2 as a compilation layer.** You write the program + metric; the optimizer produces a better prompt variant + exemplar set. Treat the output as code to commit, not as a replacement for versioning.

Deep dive: [references/versioning.md](references/versioning.md).

## Prompt Testing

**Boundary call.** This skill covers **single-prompt-cell testing**: one prompt version, one call, deterministic assertions. For multi-turn evals, trajectory grading, LLM-as-judge rubric engineering, and eval-CI architecture (tiered execution, cost budgeting), defer to [`agent-evals`](../agent-evals/SKILL.md).

### Assertion primitives for a single prompt call

| Assertion | Use |
|-----------|-----|
| Exact / contains / not-contains / regex | Cheap, deterministic guards on output shape |
| JSON Schema conformance + property-level assertions | For structured-output prompts; fail the test on any schema drift |
| `deepeval.assert_test(...)` / Promptfoo YAML | Framework integration |
| LLM-as-judge rubric | **Last resort.** Prefer deterministic assertions when the output is structured |

### Dataset-driven prompt tests

- Small, version-controlled fixtures keyed to prompt versions. Each prompt version = a CI run of its suite.
- Treat prompt-version bump + model-version bump as **independent experiments**. Evaluate each in isolation.

### Non-determinism discipline

- Never expect exact output matching.
- Run multiple trials per test case; report `pass@k` (k typically 3–5).
- `temperature=0` does not guarantee determinism — test accordingly.

### Framework selection (short form)

- **Promptfoo** — YAML-first, CI-friendly, red-teaming built in. Default for non-Python teams. See [assets/promptfoo-prompt-suite.yaml](assets/promptfoo-prompt-suite.yaml).
- **DeepEval** — Python, pytest-style, 60+ metrics, strong GitHub Actions integration. Default for Python teams. See [contexts/python.md](contexts/python.md).
- **Inspect AI** — offline eval, reproducibility focus. Research-grade / government evaluations.
- **OpenAI Evals** — OpenAI-centric stacks; less multi-provider.

Deep dive: [references/prompt-testing.md](references/prompt-testing.md).

## Platform Comparison

<!-- last-verified: 2026-04-16 -->

Prompt-management and prompt-ops platforms are a dense landscape. Pick one based on team shape, not feature count.

| Platform | Model | Strengths | When to pick |
|----------|-------|-----------|--------------|
| **LangSmith** | SaaS, LangChain-native | Deepest LangChain/LangGraph integration, trace-linked debugging | Teams already on LangChain |
| **Langfuse** | OSS (self-host) + cloud | OpenTelemetry-native, prompt CMS + evals + tracing, multi-provider | Data-residency needs, multi-provider stacks |
| **PromptLayer** | SaaS | Git-like prompt registry, visual diff | Small teams, simple flows |
| **Humanloop** | SaaS | Non-technical UX, eval coupling | Product-led teams with PM/Ops authoring |
| **Braintrust** | SaaS | Eval-first, experiments graph | Eval-heavy workflows |
| **Maxim AI** | SaaS | End-to-end (prompt + eval + observability) | Enterprise one-vendor preference |
| **Mirascope** | Library, code-first | Content-addressable versioning, env-based deploys | Prompts-as-code, richer than raw git |
| **DSPy** | Library (optimizer) | Compiles prompts from metrics — auto-optimization (MIPROv2) | Pipelines with a measurable metric, affordable optimization runs |

Cost, latency, and feature surface drift quarterly. Treat this matrix as a starting set, not a scorecard — verify via the vendor's current docs or `external-api-docs` before committing.

## Security: Prompt-Injection Hardening

This skill covers **author-side hardening** — patterns the prompt author controls to reduce injection risk. For detection, runtime guardrails, and OWASP LLM-01 implementation in shipped applications, defer to [`context-security-review`](../context-security-review/SKILL.md).

Load-bearing patterns:

- **XML-delimited user data.** Wrap untrusted input in `<user_input>…</user_input>` tags (or similar consistent naming). Instruct the model that content inside those tags is data, not instruction.
- **Instruction-after-data positioning.** Place the actual task *after* any untrusted content, so the trailing instruction takes precedence over embedded attacker instructions.
- **System-vs-user role weighting.** Keep hard constraints in the system prompt; treat user-message content as lower-authority. Some models give system prompts higher weighting than others — verify behavior.
- **Avoid `ignore previous instructions` vulnerability patterns** by never putting the operational instruction in a position where user text can override it.

Deep dive: [references/prompt-injection-hardening.md](references/prompt-injection-hardening.md).

## Integration With Agent and SDK Surfaces

Prompts rarely exist in isolation — they ship inside agents, SDK calls, or MCP servers. Keep the prompt-engineering concerns *inside* this skill and the plumbing in the adjacent ones.

- **Building Claude Code subagents, writing subagent system prompts.** → [`agent-crafting`](../agent-crafting/SKILL.md). Use *this* skill for the prompt-design patterns that go *inside* those system prompts.
- **Agent-loop architecture, tool integration, handoffs, multi-agent orchestration.** → [`agentic-sdks`](../agentic-sdks/SKILL.md). This skill's structured-output and few-shot patterns feed into the agent's tool calls and instructions.
- **MCP prompts primitive (server-side registration, wire protocol).** → [`mcp-crafting`](../mcp-crafting/SKILL.md). This skill covers the content-design questions for prompts exposed via MCP.

## Evaluation

Single-prompt testing is covered in **Prompt Testing** above. For anything beyond that scope — multi-turn agent trajectories, LLM-as-judge rubric engineering, grader reliability (κ / Krippendorff α), eval CI architecture, golden-dataset curation — defer to [`agent-evals`](../agent-evals/SKILL.md). The boundary is clean: if the evaluation is one prompt → one response, it belongs here; if it spans multiple turns or tool calls, it belongs in `agent-evals`.

## Complementary Skills

| Skill | Role |
|-------|------|
| [`claude-ecosystem`](../claude-ecosystem/SKILL.md) | Claude model IDs, API features (extended thinking, adaptive effort, prompt-caching thresholds), SDK selection |
| [`agentic-sdks`](../agentic-sdks/SKILL.md) | Agent-loop patterns, tool integration, multi-agent orchestration; prompts ship inside agents |
| [`agent-evals`](../agent-evals/SKILL.md) | Multi-turn evals, LLM-as-judge rubric design, trajectory grading, eval CI |
| [`agent-crafting`](../agent-crafting/SKILL.md) | Claude Code subagent configuration; this skill shapes the prompt content inside subagents |
| [`mcp-crafting`](../mcp-crafting/SKILL.md) | MCP protocol and prompts-primitive registration |
| [`external-api-docs`](../external-api-docs/SKILL.md) | Current SDK method signatures and endpoint parameters — fetch before writing integration code |
| [`context-security-review`](../context-security-review/SKILL.md) | Runtime prompt-injection detection and guardrails in shipped applications |

## References

- [references/few-shot-patterns.md](references/few-shot-patterns.md)
- [references/reasoning-and-cot.md](references/reasoning-and-cot.md)
- [references/structured-output.md](references/structured-output.md)
- [references/versioning.md](references/versioning.md)
- [references/prompt-testing.md](references/prompt-testing.md)
- [references/prompt-injection-hardening.md](references/prompt-injection-hardening.md)
- [contexts/python.md](contexts/python.md)
- [contexts/typescript.md](contexts/typescript.md)

External authoritative sources (current-as-of 2026-04-16):

- [Anthropic prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)
- [Anthropic extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) and [adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [OpenAI structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)
- [instructor (Python)](https://python.useinstructor.com/)
- [Promptfoo](https://github.com/promptfoo/promptfoo)
- [DeepEval](https://deepeval.com/)
- [DSPy / MIPROv2](https://dspy.ai/api/optimizers/MIPROv2/)
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [Karpathy on context engineering](https://x.com/karpathy/status/1937902205765607626)
