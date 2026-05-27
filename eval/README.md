# Praxion Evals

Out-of-band quality measurement for Praxion agent pipelines. Invoked via the `/eval` and `/eval-praxion` slash commands — never from a Claude Code hook. See [`dec-040`](../.ai-state/decisions/040-eval-framework-out-of-band.md) for the out-of-band invocation contract; `dec-draft-e1f01781` (finalized at merge-to-main) narrows clause 3 to allow LLM-as-judge calls over completed artifacts.

## Tiers

| Command | Tier | Status | Purpose |
|---------|------|--------|---------|
| `/eval` | 1 | ready | Filesystem-only artifact manifest check against `.ai-work/<slug>/` + `.ai-state/` via the `behavioral` sub-package |
| `/eval-praxion` | 2 | ready | LLM-as-judge over completed `.ai-state/` artifacts — Family 1 (pipeline-outcome fidelity) + Family 2 (behavioral-contract adherence). Reports in `.ai-state/praxion_eval_reports/` |
| cost stub | 2 | stub | Token + dollar cost analysis — raises `NotImplementedError`; see `eval/EVAL_PLAN.md` §Family 5 |
| decision-quality stub | 2 | stub | ADR / decision quality analysis — raises `NotImplementedError`; see `eval/EVAL_PLAN.md` §Family 3/4 |

The `regression` sub-package has been **retired** (removed in the praxion-self-eval-v1 pipeline). It was broken by design: baselines were keyed by `task_slug`, but Praxion slugs are one-shot — each feature generates a unique slug with no second run to compare against. The entire broken-by-design surface (448 LOC) was removed clean. The broader regression-mode redesign (tier/shape-keyed envelope baselines over a Phoenix corpus) remains deferred; see `eval/EVAL_PLAN.md` for the scope.

## Usage

```sh
cd eval
uv sync

# List available tiers and their status.
uv run praxion-evals list

# Behavioral eval against a completed pipeline.
uv run praxion-evals behavioral --task-slug phase3-quality-automation

# Self-eval: LLM-as-judge over main HEAD (requires CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY).
uv run praxion-evals eval-praxion

# Self-eval against a specific git ref or worktree.
uv run praxion-evals eval-praxion <ref-or-path>
```

The `/eval` and `/eval-praxion` slash commands in Claude Code wrap the same CLI.

## Auth for `/eval-praxion`

Auth is detected at runtime from environment variables:

1. `CLAUDE_CODE_OAUTH_TOKEN` set → Agent SDK route (`claude-agent-sdk`)
2. `ANTHROPIC_API_KEY` set → direct Messages API (`anthropic` SDK)
3. Neither set → exits non-zero with an actionable message

A single `JudgeClient` adapter in `harness/judge_client.py` encapsulates this seam; family code never imports an SDK directly.

## Families

See `eval/EVAL_PLAN.md` for the full design narrative, deferred families, and open design questions.

| Family | Source | Corpus |
|--------|--------|--------|
| Family 1 — Pipeline-outcome fidelity | `harness/families/family1_pipeline_fidelity.py` | `.ai-state/specs/`, `.ai-state/decisions/`, `DECISIONS_INDEX.md` |
| Family 2 — Behavioral-contract adherence | `harness/families/family2_bc_adherence.py` | `VERIFICATION_REPORT.md` files |

## Development

- `uv run pytest` — test suite (behavioral + harness families).
- `uv run ruff format .` and `uv run ruff check --fix .` — formatting + lint.
- `uv run pyright src/` — static type check (basic mode).

## Back-compat

`trajectory_eval.py` is preserved at the package root for direct invocation (`python eval/trajectory_eval.py --project <name>`). It is a standalone script; install its deps manually per its docstring.
