# Praxion Evals

Out-of-band quality measurement for Praxion agent pipelines. Invoked via the `/eval` slash command or CI — never from a Claude Code hook. See [`dec-040`](../.ai-state/decisions/040-eval-framework-out-of-band.md) for the architectural contract.

## Tiers

| Tier | Status | Purpose |
|------|--------|---------|
| `behavioral` | ready | Filesystem-only artifact manifest check (`.ai-work/<slug>/` + `.ai-state/`). |
| `regression` | ready | Phoenix trace diff against a committed baseline JSON summary. |
| `judge-openai` | ready | OpenAI GPT judge over TOOL spans (back-compat shim to `trajectory_eval.py`). |
| `judge-anthropic` | stub | Claude-as-judge — Tier 2, raises `NotImplementedError`. |
| `cost` | stub | Token + dollar cost analysis — Tier 2. |
| `decision-quality` | stub | ADR / decision quality analysis — Tier 2. |

## Usage

```sh
cd eval
uv sync

# List available tiers and their status.
uv run praxion-evals list

# Behavioral eval against a completed pipeline.
uv run praxion-evals behavioral --task-slug phase3-quality-automation

# Regression eval against a committed baseline.
uv run praxion-evals regression --baseline ../.ai-state/evals/baselines/phase3-quality-automation.json

# Judge a project's TOOL spans with an OpenAI model.
uv run praxion-evals judge --provider openai
```

The `/eval` slash command in Claude Code wraps the same CLI.

## Baselines

Baselines live at `.ai-state/evals/baselines/<task-slug>.json`. The schema is a narrow summary — NOT a raw trace dump. See [`.ai-state/evals/README.md`](../.ai-state/evals/README.md) for the field list and refresh workflow.

## Tier 2 status

All Tier 2 stubs intentionally raise `NotImplementedError`. A future phase will implement them behind the same out-of-band invocation contract — hooks remain off-limits by ADR.

## Development

- `uv run pytest` — test suite (behavioral + regression + judges).
- `uv run ruff format .` and `uv run ruff check --fix .` — formatting + lint.
- `uv run pyright src/` — static type check (basic mode).

## Back-compat

`trajectory_eval.py` is preserved at the package root for direct invocation (`python eval/trajectory_eval.py --project <name>`). The OpenAI judge tier delegates to it so existing workflows continue to work.
