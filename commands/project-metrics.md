---
description: Compute project complexity/health metrics (churn, complexity, coupling, hot-spots, trends) and write a timestamped report triple to .ai-state/
argument-hint: "[--window-days N] [--top-n N] [--refresh-coverage]"
allowed-tools: [Bash(python3:*), Bash(git:*), Read]
---

Compute a curated set of project complexity and health metrics — SLOC, churn, change entropy, ownership, truck factor, hot-spots, cyclic dependencies, test coverage — and write a timestamped report triple to the project's `.ai-state/` directory. Runs read-only against the working tree: never executes tests, never installs dependencies, never mutates project source.

The command is a thin wrapper over the `scripts.project_metrics` Python CLI. Every metric, delta, hotspot, and trend is computed by a dedicated module in that package; this command file only handles argument passthrough, pre-flight sanity checks, and post-run surfacing.

## Arguments

Three optional flags parsed from `$ARGUMENTS` and forwarded verbatim to the Python CLI:

| Flag | Default | Meaning |
|------|---------|---------|
| `--window-days N` | `90` | Look-back window (days) for churn, ownership, and delta computations. Must be a positive integer. |
| `--top-n N` | `10` | Size of the hot-spot Top-N ranking in the MD report. Must be a positive integer. |
| `--refresh-coverage` | off | Opt-in. Before the read-only metrics pipeline runs, invoke the project's canonical coverage target (via the `test-coverage` skill's probe order) to refresh `coverage.xml`. A refresh failure degrades to a stderr warning and the pipeline still runs. The sole exception to the otherwise read-only contract. |
| `--require-readiness-ai` | off | Hard-fail (non-zero exit, no partial write) when the LLM tier of Agent Readiness cannot run — i.e., when neither `ANTHROPIC_API_KEY` nor `CLAUDE_CODE_OAUTH_TOKEN` is set, or when a judge call fails. Use to enforce LLM scoring in gated pipelines. Do **not** use in offline CI environments. |
| `--mechanical-only` | off | Skip Agent Readiness LLM enrichment entirely. All 4 LLM-judged criteria are marked `llm_skipped` and excluded from the denominator. The level is computed from the 25 mechanical criteria only. Fast and free — no API key required. Recommended for offline CI. |

Invalid arguments (non-positive, non-integer, unknown flag) are rejected by the CLI via `argparse` **before** any file under `.ai-state/` is touched — the no-partial-writes contract is enforced at the orchestration layer, not here.

## Process

### 1. Pre-flight

Verify the environment before invoking the CLI:

- **Git worktree check.** The CLI resolves the repository root via `git rev-parse --show-toplevel`; fail fast here if this is not a git checkout:

  ```bash
  git rev-parse --is-inside-work-tree
  ```

  If the command exits non-zero, stop and surface: "Not inside a git worktree — `/project-metrics` requires a git repository to locate `.ai-state/` and to compute churn."

- **`.ai-state/` writability.** The CLI creates `.ai-state/` at the repo root if missing and writes three files into it. Confirm the directory is writable (or can be created) before invoking; if a non-directory file occupies `<repo-root>/.ai-state`, stop and surface the conflict.

### 2. Run

Invoke the Python CLI, forwarding `$ARGUMENTS` verbatim:

```bash
python3 -m scripts.project_metrics $ARGUMENTS
```

With no arguments, the CLI runs with the documented defaults (`--window-days 90 --top-n 10`). The CLI prints three absolute paths on stdout, one per line, corresponding to the written files.

### 3. Post-run

On success (exit 0), the CLI emits three paths to the repo-root-relative `.ai-state/` directory:

1. `.ai-state/metrics_reports/METRICS_REPORT_<timestamp>.json` — canonical machine-readable payload (aggregate columns, per-collector namespace blocks, trends block, tool-availability).
2. `.ai-state/metrics_reports/METRICS_REPORT_<timestamp>.md` — human-readable rendering of the same report, with delta table and hot-spot Top-N.
3. `.ai-state/metrics_reports/METRICS_LOG.md` — append-only summary log; one row per run.

The timestamp shape is `YYYY-MM-DD_HH-MM-SS` (UTC, filename-safe). Multiple runs produce multiple timestamped report pairs and one growing log; no prior report is ever overwritten. The report **directory** is bounded after each run by a retain-last-N prune (see below); `METRICS_LOG.md` keeps the full per-run history regardless.

Surface the three paths to the user and suggest the next commit as a follow-up (do not auto-commit — the user owns the staging decision):

```
Three files written:
  <json_path>
  <md_path>
  <log_path>

Review the MD rendering. If it reflects project state accurately, stage and
commit with `git add <paths> && git commit`.
```

Then bound the directory: run `prune_reports.py` (PATH-installed by `install_claude.sh`; in the Praxion self-host checkout use `python3 scripts/prune_reports.py`) to retain the last 10 `METRICS_REPORT_*` runs — each run's `.md` + `.json` pair is kept or pruned together. It never touches `METRICS_LOG.md` (the full history stays); pruned reports remain in git history. Stage the pruned deletions in the same commit as the new report.

### Failure modes

- **Non-positive `--window-days` or `--top-n`**: CLI exits non-zero with a clear stderr message; nothing is written. Surface the stderr text as-is.
- **`git rev-parse --show-toplevel` fails inside the CLI**: CLI refuses to invent an `.ai-state/` location and exits non-zero. Surface the stderr text as-is.
- **Missing optional tooling** (`scc`, `uvx`-hosted collectors, language-specific analyzers): collectors downgrade to skip markers; the run still succeeds and the MD rendering notes which collectors were skipped with install hints. No special handling needed here.
- **`--refresh-coverage` dispatch failure**: if the project has no canonical coverage target, or the target exits non-zero, the CLI degrades to a stderr warning and proceeds with the existing (possibly stale or missing) `coverage.xml`. The run still exits 0 and writes all three artifacts; the MD rendering surfaces coverage as stale/skipped.

## Notes

- **Agent Readiness block.** Every run writes a `readiness` namespace at the root of the JSON report (schema version `1.1.0`). The block carries: `level` (1–5, the Factory-comparable 8-pillar score), `pass_pct`, `pillars` (8 pillar objects each with `{id, name, level_pass[], pass_pct, numerator, denominator}`), `manageability` (Pillar 9 sub-score — never folded into `level`), `criteria` (per-criterion verdict with `{id, pillar, level, scope, applicable, passed, llm, rationale}`), and `llm` sub-block (`{status, model, grounded_on}`). When `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` is set, the 4 LLM-judged criteria (`c.style.naming_conventions`, `c.testing.test_quality`, `c.docs.readme_quality`, `c.docs.agent_friendliness`) are scored via the Anthropic Messages API; otherwise they are set to `passed: null` and excluded from all denominators. These two variables are read from a `.env` file (searched from the cwd upward) when invoked via `python -m scripts.project_metrics`, so you need not pass them inline; an explicit `export` still takes precedence (the loader uses `override=False`). The dashboard Metrics page renders the readiness level badge, 8-pillar radar, Pillar-9 chip, and top-failing criteria list from this block. Load the `agent-readiness` skill for rubric interpretation and remediation guidance.
- **Read-only by contract.** The CLI never runs the project's test suite or invokes any test runner subprocess. Coverage, when reported, is read from a pre-existing artifact the project maintains (e.g., `coverage.xml`, `lcov.info`). A stale or missing artifact simply shows as a skip marker in the report. The opt-in `--refresh-coverage` flag is the one exception — when set, it dispatches to the project's canonical coverage target before the read-only metrics pipeline runs.
- **MD is human-readable, JSON is canonical.** The MD report renders headline tables (tool availability, aggregate summary, hot-spots, trends, per-language breakdown) as full Markdown plus per-collector executive summaries (top-N churning files, top-N coupled pairs, ownership concentration, top-N most complex files). It deliberately does **not** dump full per-file or per-pair structures — those live in the JSON sibling artifact. Each per-collector subsection ends with a one-line italic pointer to the JSON namespace where the full payload lives. Programmatic consumers (Datasette, Grafana, dashboards) should read the JSON; humans should read the MD.
- **Path filtering.** All collectors that walk the working tree or git history (`git`, `scc`, `lizard`) drop ecosystem-noise directories that are not part of the project's source code: `.ai-state/`, `.ai-work/`, `.claude/worktrees/`, `.cursor/`, `.git/`, `__pycache__/`, `.venv/`, `venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `dist/`, `build/`, `htmlcov/`, `node_modules/`, `.trees/`. Single source of truth: `scripts/project_metrics/_path_filter.py:DEFAULT_EXCLUDED_DIRS`. Filtering happens at collection (so the JSON artifact is also clean), not just rendering. Tools that support directory exclusion (`scc --exclude-dir`, `lizard --exclude`) receive the appropriate flags; defense-in-depth post-filtering catches anything the flags missed (e.g., multi-component patterns like `.claude/worktrees`).
- **Artifact shape, not entries.** The `.ai-state/metrics_reports/METRICS_REPORT_*` triple follows a conventional shape — files are discovered by glob, not by hardcoded names. Downstream UIs (static HTML, local server, Datasette/Grafana) consume the glob.
- **Schema evolution.** The JSON payload carries a `schema_version`. Additive changes bump minor; breaking changes bump major and surface as a `schema_mismatch` trends status on the first run against a newer prior report.
