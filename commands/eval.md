---
description: Run out-of-band quality evals (Tier 1 behavioral + regression). Opt-in, never hook-driven.
argument-hint: [list | behavioral --task-slug <slug> | regression --baseline <path> | capture-baseline --task-slug <slug> | judge --provider openai|anthropic]
allowed-tools: [Bash(uv run --project eval praxion-evals:*)]
---

User-invoked entrypoint for the `eval/` package. This command is opt-in; eval code never runs from hooks, never during a pipeline — the invocation contract is out-of-band by design so eval bugs cannot break agent work. Load the [`agent-evals`](../skills/agent-evals/SKILL.md) skill for eval design guidance.

> ⚠️ **Known limitation — regression mode is effectively useless today.** Baselines are keyed by `task_slug`, but Praxion slugs are one-shot: each feature generates a unique slug, runs once, then `.ai-work/<slug>/` is deleted. There is no "next run" on that slug to compare against. Behavioral and judge modes work as documented; `regression` and `capture-baseline` are proofs-of-concept until the tier/shape-keyed envelope redesign in [ROADMAP 3.7](../ROADMAP.md#37-eval-framework-redesign-tiershape-keyed-baselines) lands. **Before running `regression` or `capture-baseline`, surface this limitation to the user and suggest that `behavioral` is the only Tier 1 mode currently worth running for real quality gating.**

## Process

1. **No arguments → default to `list`**: invoke `uv run --project eval praxion-evals list` and print the tier status table so the user can see what's ready vs stub.

2. **`list`**: same as above.

3. **`behavioral --task-slug <slug>`**: run `uv run --project eval praxion-evals behavioral --task-slug <slug>` and stream the Markdown artifact-manifest report. Pass through any optional `--tier lightweight|standard|full` flag the user provides. **This is the only Tier 1 mode currently useful for real quality gating.**

4. **`regression --baseline <path>`**: **[PROOF-OF-CONCEPT — see banner above.]** Run `uv run --project eval praxion-evals regression --baseline <path>`. Reports drift findings (numeric drift + missing expected deliverables) against the committed baseline; never mutates Phoenix traces. Emits a stderr WARNING when the baseline has no numeric fields. The CLI will itself print a TODO banner pointing to ROADMAP 3.7.

5. **`capture-baseline --task-slug <slug>`**: **[PROOF-OF-CONCEPT — see banner above.]** Run `uv run --project eval praxion-evals capture-baseline --task-slug <slug>`. Snapshots current Phoenix traces + `.ai-work/<slug>/*.md` deliverables into a baseline JSON at `.ai-state/evals/baselines/<slug>.json` (override with `--output`). Read-only against Phoenix. Also blocked by a dep gap — `arize-phoenix` is missing from `eval/pyproject.toml`, so live Phoenix capture currently returns empty.

6. **`judge --provider openai|anthropic`**: run `uv run --project eval praxion-evals judge --provider <p>`. `openai` delegates to `trajectory_eval.py` (Tier 1 back-compat); `anthropic` is a Tier 2 stub that raises `NotImplementedError`.

7. **Invariant**: this command must only run when the user explicitly invokes it. If any hook or agent script references `praxion_evals`, flag it as a bug.

## Examples

```sh
/eval                                                     # list tiers
/eval behavioral --task-slug phase3-quality-automation    # Tier 1 behavioral
/eval capture-baseline --task-slug phase3-quality-automation  # populate a real baseline
/eval regression --baseline .ai-state/evals/baselines/phase3-quality-automation.json
/eval judge --provider openai                             # OpenAI judge shim
```
