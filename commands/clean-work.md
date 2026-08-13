---
description: Safely clean .ai-work/ after pipeline completion — state-aware, with --dry-run
argument-hint: "[--dry-run] [--force <slug>] [slug ...]"
allowed-tools: [Bash(clean_work_safety.py:*), Bash(python3:*), Bash(rm:*), Bash(ls:*), Bash(cat:*), Read, AskUserQuestion]
disable-model-invocation: true
---

Remove task-scoped subdirectories from `.ai-work/` — but never silently delete in-flight, unarchived, or audit state.

`.ai-work/<task-slug>/` is gitignored, so `rm -rf` is irreversible. Some artifacts must reach a durable home before deletion (`LEARNINGS.md` → ADRs/specs/docs; `VERIFICATION_REPORT.md` patterns → `LEARNINGS.md`; `traceability.yml` → archived SPEC matrix; `RECOVERY_LOG.md` audit trail; `PRE_REFACTOR_PLAN.md` tech-debt transitions), and a directory with an active `WIP.md` or an open `REWORK_MANIFEST.md` is live pipeline state that must not be deleted at all. A deterministic scanner classifies each directory so this command can refuse, warn, or proceed.

## Arguments

`$ARGUMENTS` holds the invocation; parse it for the flags and optional slugs below before Step 1.

- `slug ...` — restrict to these task slugs; omit to scan every task directory.
- `--dry-run` — report classifications and stop; delete nothing.
- `--force <slug>` — override a **BLOCK** for that one slug after the user confirms; never a blanket force.

## Process

1. **Classify (read-only).** Run the safety scanner. It is installed on `PATH` by `install_claude.sh` (linked into `~/.local/bin/`); in the Praxion self-host checkout use `python3 scripts/clean_work_safety.py` instead:
   ```
   clean_work_safety.py --repo-root "$(git rev-parse --show-toplevel)" --json [slug ...]
   ```
   The scanner mutates nothing. Parse the `task_dirs` array: each entry has `slug`, `classification` (`BLOCK` / `WARN` / `SAFE`), `reasons` (each with `code`, `blocker`, `severity`, `remedy`), and `age_days` (idle days since the newest file; the `summary.stale_safe` count tallies SAFE dirs idle ≥14d). If it reports "Nothing to clean", stop.
2. **Present** the verdicts grouped by classification, listing every `BLOCK` and `WARN` reason with its remedy so the user sees exactly what is at risk. Call out the **stale SAFE** dirs (`age_days ≥ 14`) first — they are the prime cleanup candidates that let `.ai-work/` keep communicating "active work".
3. **`--dry-run`:** stop here — report what *would* be deleted (SAFE), retained (BLOCK), and warned (WARN). Delete nothing.
4. **BLOCK directories:** do **not** delete. Tell the user to resolve the blocker (finish or `/resume-pipeline` the pipeline; complete the rework worktrees), or re-invoke with `--force <slug>` to override that specific slug. Only delete a BLOCK slug when it was passed in `--force` **and** the user confirms via `AskUserQuestion`.
5. **WARN directories:** show the reasons and remedies, then use `AskUserQuestion` to confirm deletion (per slug, or as a batch) — only after the user acknowledges the durable-state handoff. Do not delete a WARN slug without explicit confirmation.
6. **SAFE directories** (and confirmed `--force` / WARN slugs): `rm -rf .ai-work/<task-slug>/`. Remove `.ai-work/` itself only when it is empty afterward.
7. **Confirm** the outcome: list what was deleted, what was retained as blocked, and what was warned and skipped.
