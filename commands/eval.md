---
description: Run out-of-band quality evals (Tier 1 behavioral + regression). Opt-in, never hook-driven.
argument-hint: [list | behavioral --task-slug <slug> | regression --baseline <path> | judge --provider openai|anthropic]
allowed-tools: [Bash(uv run --project eval praxion-evals:*)]
---

User-invoked entrypoint for the `eval/` package. This command is opt-in; eval code never runs from hooks, never during a pipeline (see [`dec-040`](../.ai-state/decisions/040-eval-framework-out-of-band.md)). Load the [`agent-evals`](../skills/agent-evals/SKILL.md) skill for eval design guidance.

## Process

1. **No arguments → default to `list`**: invoke `uv run --project eval praxion-evals list` and print the tier status table so the user can see what's ready vs stub.

2. **`list`**: same as above.

3. **`behavioral --task-slug <slug>`**: run `uv run --project eval praxion-evals behavioral --task-slug <slug>` and stream the Markdown artifact-manifest report. Pass through any optional `--tier lightweight|standard|full` flag the user provides.

4. **`regression --baseline <path>`**: run `uv run --project eval praxion-evals regression --baseline <path>`. Reports drift findings against the committed baseline; never mutates Phoenix traces.

5. **`judge --provider openai|anthropic`**: run `uv run --project eval praxion-evals judge --provider <p>`. `openai` delegates to `trajectory_eval.py` (Tier 1 back-compat); `anthropic` is a Tier 2 stub that raises `NotImplementedError`.

6. **Invariant**: this command must only run when the user explicitly invokes it. If any hook or agent script references `praxion_evals`, flag it as a bug.

## Examples

```sh
/eval                                                     # list tiers
/eval behavioral --task-slug phase3-quality-automation    # Tier 1 behavioral
/eval regression --baseline .ai-state/evals/baselines/phase3-quality-automation.json
/eval judge --provider openai                             # OpenAI judge shim
```
