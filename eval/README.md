# Praxion Evals

Out-of-band quality measurement for Praxion agent pipelines. Invoked via the single `/eval-praxion` slash command (CLI: `praxion-evals`) — never from a Claude Code hook. See [`dec-040`](../.ai-state/decisions/040-eval-framework-out-of-band.md) for the out-of-band invocation contract; `dec-204` (finalized at merge-to-main) narrows clause 3 to allow LLM-as-judge calls over completed artifacts.

The Tier 1 behavioral / artifact-manifest surface (formerly `/eval behavioral`) has been folded into Family 1; pass `--task-slug <slug>` to activate it and combine with `--mechanical-only` to reproduce the cheap, free verdict.

## Modes

| Invocation | What runs | Cost |
|------------|-----------|------|
| `praxion-evals` (no args) | Both families against `main` HEAD; LLM judging on | API credits |
| `praxion-evals <ref-or-path>` | Both families against the resolved target | API credits |
| `praxion-evals --task-slug <slug>` | Adds the in-flight `.ai-work/<slug>/` manifest scan to Family 1 | API credits |
| `praxion-evals --mechanical-only` | Skip every LLM-judged check across families; no auth env needed | Free |

Two future-family sentinels live under `stubs/` (cost, decision-quality) — they raise `NotImplementedError` and document deferred work in `eval/EVAL_PLAN.md`.

The retired `regression` and `judges/` packages (broken-by-design baseline diff + back-compat shims) were deleted in the praxion-self-eval-v1 pipeline. The broader regression redesign (tier/shape-keyed envelope baselines over a Phoenix corpus) remains deferred.

## Usage

```sh
cd eval
uv sync

# Self-eval: LLM-as-judge over main HEAD (requires CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY).
uv run praxion-evals

# Self-eval against a specific git ref or worktree.
uv run praxion-evals <ref-or-path>

# In-flight artifact-manifest check for a live pipeline (cheap, no auth).
uv run praxion-evals --task-slug phase3-quality-automation --mechanical-only

# Full eval over a worktree.
uv run praxion-evals my-feature-worktree
```

The `/eval-praxion` slash command in Claude Code wraps the same CLI.

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
