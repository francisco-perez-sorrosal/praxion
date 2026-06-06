---
description: Read .ai-state/eval_ledger/EVAL_LOG.md and render a ranked leaderboard table of eval runs, with optional task filter and sort control.
argument-hint: "[--task <name>] [--sort <primary_metric|generation|cost_usd>] [--top <N>]"
allowed-tools: [Read]
disable-model-invocation: true
---

Display a ranked leaderboard of eval runs recorded in `.ai-state/eval_ledger/EVAL_LOG.md`.
This command is read-only — it never writes files or executes shell commands.

For context on the eval loop that produces the log, see
[`skills/agent-evals/SKILL.md`](../skills/agent-evals/SKILL.md).

## Arguments

Parse `$ARGUMENTS` for the following optional flags:

| Flag | Default | Meaning |
|------|---------|---------|
| `--task <name>` | all tasks | Filter to rows where the `task` column contains `<name>` (partial match, case-insensitive) |
| `--sort <col>` | `primary_metric` | Sort by the named column, descending. Accepted values: `primary_metric`, `generation`, `cost_usd` |
| `--top <N>` | all rows | Limit output to the top N rows after sorting |

Unknown flags are ignored. Missing or invalid `--sort` values default to `primary_metric`.

## Process

### 1. Locate the log

Read the file at `<project-root>/.ai-state/eval_ledger/EVAL_LOG.md`.

If the file does not exist or is empty (header-only), emit the following and stop:

```
No eval runs recorded yet.
Run the eval loop on a managed project to populate .ai-state/eval_ledger/EVAL_LOG.md.
See skills/agent-evals/SKILL.md for the eval loop workflow.
```

### 2. Parse the table

The log is an append-only Markdown table with 11 columns (sourced from
`skills/agent-evals/references/run-ledger-schema.md` §EVAL_LOG.md Column Set):

```
| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
```

Parse each data row (skip the header and separator lines). Treat `primary_metric`,
`held_out_delta`, `generation`, and `cost_usd` as numeric columns — coerce to float/int
where possible; treat non-numeric or blank cells as `null`.

### 3. Filter

If `--task <name>` is provided, retain only rows where the `task` column contains `<name>`
(case-insensitive substring match). If no rows match, emit:

```
No eval runs found for task matching "<name>".
```

### 4. Sort

Sort the retained rows by the `--sort` column, descending (highest first). Rows with `null`
in the sort column sort last.

### 5. Limit

If `--top <N>` is provided and N is a positive integer, keep only the top N rows.

### 6. Render the leaderboard

Prepend a `rank` column (1-based) and render the result as a Markdown table. Numeric
columns are right-aligned in the header separator (`---:`) for readability.

Example output shape (not hardcoded column values):

```markdown
## Eval Leaderboard

| rank | run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |
|------|--------|------|---:|--------------:|---------------:|----------|-------------|-------------|--------:|---------|-----------|
| 1    | ...    | ...  | ... | ...            | ...            | ...      | ...         | ...         | ...     | ...     | ...       |
```

Include a footer line noting the total number of rows in the log and the number shown:

```
Showing N of M total run(s).
```

## Column Reference

All 11 columns are defined in `skills/agent-evals/references/run-ledger-schema.md`
§EVAL_LOG.md Column Set. Key columns for leaderboard interpretation:

- **`primary_metric`** — scored result for the run (accuracy, F1, pass@k — task-dependent); higher is better
- **`held_out_delta`** — held-out score minus public score; negative values signal no contamination
- **`generation`** — iteration number in the eval loop; higher generations reflect more refinement
- **`cost_usd`** — monetary cost of the run (0.0 for free-tier / local models)
- **`store_uri`** — path to the tier-1 run store where heavy artifacts (traces, logs, submissions) live

## Notes

- This command is read-only. It never modifies `EVAL_LOG.md` or any other file.
- `EVAL_LOG.md` is an append-only log — rows accumulate across runs; this command reads
  the full log each time.
- `prompt_hash` and `dataset_sha` in the table are short 8-character prefixes for
  readability. Full hashes live in the corresponding `EVAL_RESULTS.md` at project root.
