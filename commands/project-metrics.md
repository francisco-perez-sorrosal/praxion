---
description: Compute project complexity/health metrics (churn, complexity, coupling, hot-spots, trends) and write a timestamped report triple to .ai-state/
argument-hint: "[--window-days N] [--top-n N]"
allowed-tools: [Bash(python3:*), Bash(git:*), Read]
---

Compute a curated set of project complexity and health metrics — SLOC, churn, change entropy, ownership, truck factor, hot-spots, cyclic dependencies, test coverage — and write a timestamped report triple to the project's `.ai-state/` directory. Runs read-only against the working tree: never executes tests, never installs dependencies, never mutates project source.

The command is a thin wrapper over the `scripts.project_metrics` Python CLI. Every metric, delta, hotspot, and trend is computed by a dedicated module in that package; this command file only handles argument passthrough, pre-flight sanity checks, and post-run surfacing.

## Arguments

Two optional flags parsed from `$ARGUMENTS` and forwarded verbatim to the Python CLI:

| Flag | Default | Meaning |
|------|---------|---------|
| `--window-days N` | `90` | Look-back window (days) for churn, ownership, and delta computations. Must be a positive integer. |
| `--top-n N` | `10` | Size of the hot-spot Top-N ranking in the MD report. Must be a positive integer. |

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

1. `.ai-state/METRICS_REPORT_<timestamp>.json` — canonical machine-readable payload (aggregate columns, per-collector namespace blocks, trends block, tool-availability).
2. `.ai-state/METRICS_REPORT_<timestamp>.md` — human-readable rendering of the same report, with delta table and hot-spot Top-N.
3. `.ai-state/METRICS_LOG.md` — append-only summary log; one row per run.

The timestamp shape is `YYYY-MM-DD_HH-MM-SS` (UTC, filename-safe). Multiple runs produce multiple timestamped report pairs and one growing log; no prior report is ever overwritten.

Surface the three paths to the user and suggest the next commit as a follow-up (do not auto-commit — the user owns the staging decision):

```
Three files written:
  <json_path>
  <md_path>
  <log_path>

Review the MD rendering. If it reflects project state accurately, stage and
commit with `git add <paths> && git commit`.
```

### Failure modes

- **Non-positive `--window-days` or `--top-n`**: CLI exits non-zero with a clear stderr message; nothing is written. Surface the stderr text as-is.
- **`git rev-parse --show-toplevel` fails inside the CLI**: CLI refuses to invent an `.ai-state/` location and exits non-zero. Surface the stderr text as-is.
- **Missing optional tooling** (`scc`, `uvx`-hosted collectors, language-specific analyzers): collectors downgrade to skip markers; the run still succeeds and the MD rendering notes which collectors were skipped with install hints. No special handling needed here.

## Notes

- **Read-only by contract.** The CLI never runs `pytest`, `coverage run`, or any project-defined test target. Coverage, when reported, is read from a pre-existing artifact the project maintains (e.g., `coverage.xml`, `lcov.info`). A stale or missing artifact simply shows as a skip marker in the report.
- **Artifact shape, not entries.** The `.ai-state/METRICS_REPORT_*` triple follows a conventional shape — files are discovered by glob, not by hardcoded names. Downstream UIs (static HTML, local server, Datasette/Grafana) consume the glob.
- **Schema evolution.** The JSON payload carries a `schema_version`. Additive changes bump minor; breaking changes bump major and surface as a `schema_mismatch` trends status on the first run against a newer prior report.
