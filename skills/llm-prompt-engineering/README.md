# LLM Prompt Engineering

Systematic prompt design for production LLM calls. Covers few-shot patterns, chain-of-thought and reasoning-effort control, structured output via Pydantic/Zod, prompt versioning, and single-prompt testing. Framework-agnostic across Claude, GPT-5, Gemini, and open-weights models.

## When to Use

- Designing new production prompts (system prompts, few-shot examples)
- Deciding whether to use chain-of-thought or a model's native reasoning-effort knob
- Structuring Pydantic/Zod models as output contracts for structured extraction
- Picking a prompt-management platform or pinning a call envelope (model, temp, schema)
- Writing single-prompt regression tests with Promptfoo or DeepEval
- Migrating prompts across model families or versions

## Activation

Triggers on: designing prompts for LLM calls, writing system prompts, debugging output quality, few-shot patterns, chain-of-thought, structured output, Pydantic, Zod, prompt versioning, prompt regression testing, migrating across model versions.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: model family matrix, few-shot patterns, structured output, prompt versioning, testing overview |
| `contexts/python.md` | Python: `instructor` + Pydantic retry loop, Anthropic/OpenAI SDK call shapes, pytest + DeepEval integration |
| `contexts/typescript.md` | TypeScript: Zod + `instructor-js`, native SDK `strict: true`, Promptfoo YAML, Node test-runner |
| `references/few-shot-patterns.md` | Dynamic retrieval, positional-bias research, debiasing strategies, calibrate-before-use |
| `references/reasoning-and-cot.md` | Self-consistency, decomposition patterns, extended-thinking parameters, superseded-patterns appendix |
| `references/structured-output.md` | Provider-specific code patterns, Pydantic/Zod-as-prompt idioms, retry-repair loop |
| `references/versioning.md` | Platform comparison, DSPy/MIPROv2 workflow, prompt-caching-friendly layout, envelope-pinning template |
| `references/prompt-testing.md` | Promptfoo YAML, DeepEval pytest, LLM-judge bias mitigations, single-prompt vs agent-level boundary |
| `references/prompt-injection-hardening.md` | Author-side hardening, XML delimiters, instruction-after-data, OWASP LLM-01 pointers |
| `assets/pydantic-retry-template.py` | Minimal retry-on-ValidationError loop template |
| `assets/promptfoo-prompt-suite.yaml` | Starter Promptfoo suite with assertion examples |
| `assets/envelope-manifest.yaml` | Full-envelope pinning manifest template |

## Related Skills

- [`claude-ecosystem`](../claude-ecosystem/) -- Claude model IDs, API features (extended thinking, prompt-caching thresholds), SDK selection
- [`agentic-sdks`](../agentic-sdks/) -- Agent-loop plumbing, tool registration; this skill shapes the prompts inside agents
- [`agent-evals`](../agent-evals/) -- Multi-turn evals, LLM-as-judge rubric design, trajectory grading, eval CI
- [`agent-crafting`](../agent-crafting/) -- Claude Code subagent configuration; this skill shapes prompt content inside subagents
- [`external-api-docs`](../external-api-docs/) -- Current SDK method signatures and endpoint parameters
