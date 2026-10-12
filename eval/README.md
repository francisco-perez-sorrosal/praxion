# Praxion Evals

Out-of-band quality measurement for Praxion agent pipelines. Invoked via the single `/eval-praxion` skill (CLI: `praxion-evals`) — never from a Claude Code hook. See [`dec-040`](../.ai-state/decisions/040-eval-framework-out-of-band.md) for the out-of-band invocation contract; `dec-204` (finalized at merge-to-main) narrows clause 3 to allow LLM-as-judge calls over completed artifacts.

The Tier 1 behavioral / artifact-manifest surface (formerly `/eval behavioral`) has been folded into Family 1; pass `--task-slug <slug>` to activate it and combine with `--mechanical-only` to reproduce the cheap, free verdict.

## Modes

| Invocation | What runs | Cost |
|------------|-----------|------|
| `praxion-evals` (no args) | All families against `main` HEAD; LLM judging on | API credits |
| `praxion-evals <ref-or-path>` | All families against the resolved target | API credits |
| `praxion-evals --task-slug <slug>` | Adds the in-flight `.ai-work/<slug>/` manifest scan to Family 1 | API credits |
| `praxion-evals --mechanical-only` | Skip every LLM-judged check across families; no auth env needed | Free |

A separate, opt-in console entry, `praxion-evals-adherence`, measures process adherence per spawned role in paired arms. It spends API money, is never reachable from `/eval-praxion`, and is documented under [Process-adherence eval](#process-adherence-eval) below.

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

The `/eval-praxion` skill in Claude Code wraps the same CLI.

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
| Seeded scenario corpus | `harness/families/seeded_scenarios.py` | Bundled fixtures under `tests/fixtures/scenarios/` |
| Family 5 — Token-budget surface stability | `harness/families/family5_token_budget_stability.py` | `.ai-state/token_budget_baseline.json` (read-only) |
| Process-adherence eval (separate entry, `praxion-evals-adherence`) | `adherence/` | Fresh sandboxed `claude -p` sessions over bundled fixtures under `adherence/fixtures/` |

## Process-adherence eval

`praxion-evals-adherence` measures, for a chosen role, whether a spawned agent keeps its own part of the Praxion process in two paired arms: `full` (the checkout as it is) and `lean` (the role's agent definition carries `omitClaudeMd: true`). Each task runs in both arms as a fresh headless `claude -p` session and yields one pair. Design and statistics: [`EVAL_PLAN.md`](EVAL_PLAN.md#process-adherence-eval-startup-context-diet-instrument-i2).

> [!WARNING]
> Every run spends API money. Start with `--dry-run`, which prints the sessions a run would launch and starts none. The run cap defaults to $50 and each session to $3.

**Scope today.** Every role has its check rows and a task kit: the `researcher`, the `verifier` and the `implementer` have full kits (24 producible tasks each); the other fourteen have smoke kits (three runnable tasks by default, 24 producible). The main-session conditional-adherence eval is deferred (`EVAL_PLAN.md`).

```sh
cd eval

# 1. Dry run: print the planned sessions, spend nothing, write nothing.
uv run praxion-evals-adherence .. --role researcher --role verifier --dry-run

# 2. Smoke run, both arms, two pairs per role, with the judge's golden cases.
uv run praxion-evals-adherence .. --role researcher --role verifier \
  --required-pairs 2 --pair-slack 0 --judge-golden \
  --max-total-usd 30 --session-budget-usd 3 --output ../tmp/smoke-run.json

# 3. Calibration: the full arm against itself, the source of mechanical allowances.
uv run praxion-evals-adherence .. --role researcher --calibration \
  --required-pairs 4 --pair-slack 0 --max-total-usd 15 --output ../tmp/calibration-run.json

# 4. A paired run that uses the calibration's allowances.
uv run praxion-evals-adherence .. --role researcher --calibration-run ../tmp/calibration-run.json

# 5. Render a results file; launches nothing.
uv run praxion-evals-adherence --report ../tmp/smoke-run.json
```

The first positional argument is the plugin checkout under test (default: this repository's root). Inside a Claude Code session, export `CLAUDE_CODE_OAUTH_TOKEN=""` first so the judge client does not reuse the session's token.

| Option | Meaning |
|--------|---------|
| `--role ROLE` | Repeatable; one of the 17 roles |
| `--arm {full,lean}` | Repeatable; default both. A paired verdict needs both arms in one run |
| `--output FILE` | Default `.ai-state/eval_ledger/adherence/<run-id>.json` under the repository root |
| `--overwrite` | Replace an existing results file; without it the run refuses at start, before any session launches |
| `--seed N` | Task-list seed (default 7); the same seed reproduces the same tasks |
| `--max-total-usd`, `--session-budget-usd` | Run-level cap (default 50) and per-session budget (default 3) |
| `--required-pairs N`, `--pair-slack N` | Target complete pairs per role (default 20) and slack above it (default a fifth of the target, at least four) |
| `--margin-pp`, `--confidence` | Judged-check non-inferiority margin in percentage points (default 10) and interval confidence (default 0.95); declared in the results file before the first session |
| `--calibration` | Run the `full` arm against itself; mutually exclusive with `--calibration-run` |
| `--calibration-run FILE` | Take each mechanical check's allowance from this calibration file; without it every allowance is zero |
| `--judge-golden` | Judge each judged check's golden good and bad case once and record both verdicts |
| `--no-judge` | Withhold judged checks |
| `--model`, `--effort` | Session model and effort (defaults `opus`, `medium`) |
| `--keep-sandbox` | Keep each session's sandbox for inspection |
| `--fixture-pages-base-url URL` | Directory URL that serves the C6 fixture page; without it C6 is withheld |
| `--report FILE` | Render a results file as text; launch nothing |
| `--dry-run` | Print the planned sessions; start none |

Exit codes: 0 the run completed; 1 it is incomplete (a refused launch, an arm that could not be built or proven, an errored session; the results are still written); 2 usage error.

The report states counts and bounds. A role with fewer complete pairs than the target is reported underpowered with no flip verdict, and no wording claims improvement. The user's ratification of the flip rule is owed before any verdict gates a lean-spawn flip.

## Development

- `uv run pytest` — test suite (behavioral + harness families).
- `uv run ruff format .` and `uv run ruff check --fix .` — formatting + lint.
- `uv run pyright src/` — static type check (basic mode).

## Back-compat

`trajectory_eval.py` is preserved at the package root for direct invocation (`python eval/trajectory_eval.py --project <name>`). It is a standalone script; install its deps manually per its docstring.
