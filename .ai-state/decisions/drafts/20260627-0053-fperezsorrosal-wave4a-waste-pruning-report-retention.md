---
id: dec-draft-bcb50377
title: Retain-last-N retention for the metrics and sentinel report families
status: proposed
category: configuration
date: 2026-06-27
summary: Bound the unbounded growth of metrics_reports/ and sentinel_reports/ with a retain-last-10 prune script, producer-triggered, git-history as the archive.
tags: [report-retention, hygiene, metrics, sentinel, waste-pruning, prune]
made_by: user
branch: wave4a-waste-pruning
pipeline_tier: standard
affected_files:
  - scripts/prune_reports.py
  - scripts/test_prune_reports.py
  - agents/sentinel.md
  - commands/project-metrics.md
---

## Context

`.ai-state/metrics_reports/` (64 files) and `.ai-state/sentinel_reports/` (39 files) grow one
timestamped report per run with no upper bound. The repository's large-file guard
(`.pre-commit-config.yaml`) explicitly **excludes** both directories, so nothing pushes back on
the count — the process-flow analysis (finding C2 / R11) flagged 100+ committed report files
accumulating indefinitely. The per-run reports are point-in-time snapshots; the durable historical
signal lives in the append-only `*_LOG.md` index, not in every individual report.

## Decision

Add `scripts/prune_reports.py --keep N` (default **N=10**), which keeps the N most-recent report
*runs* per family and removes older ones from the working tree:

- **Families:** `metrics_reports`, `sentinel_reports`. A run is grouped by its
  `YYYY-MM-DD_HH-MM-SS` timestamp, so a metrics run's `.md` + `.json` pair is always kept or pruned
  together.
- **Exempt by construction:** the `*_LOG.md` index and `.lock` files carry no `_REPORT_` token, so
  the full historical summary survives every prune.
- **Archive = git history.** Pruned reports are deleted from the working tree only; they remain
  recoverable from git history. This is the same "history, not a live directory" principle applied
  to `token_budgeting/` in the sibling Wave-4a decision.
- **Producer-triggered.** The two report producers invoke it after writing: sentinel Phase 7 (after
  appending to `SENTINEL_LOG.md`) and the `/project-metrics` post-run step. Installed on `PATH` by
  `install_claude.sh` (executable bit set), like `clean_work_safety.py`, so the shipped command and
  agent can call it by name in managed projects; the Praxion self-host checkout calls
  `python3 scripts/prune_reports.py`.
- **Advisory, never a gate.** Exit 0 always; `--dry-run` previews; absent family directories are a
  no-op. A `test_bites_canary` proves it actually deletes the over-limit runs.

## Considered Options

### Option A — Retain-last-N, producer-triggered (CHOSEN)

- **Pros:** bounds each directory continuously; the LOG keeps the full history; git history archives
  pruned reports; one small stdlib script with a thorough test including a deletion canary; mirrors
  the established `clean_work_safety.py` maintenance-script pattern.
- **Cons:** producer-triggered invocation is prompt-wired (an agent/command step), so a skipped step
  defers a prune rather than enforcing it; deterministic CLI-level wiring (calling prune from inside
  the metrics engine) is a possible future hardening.

### Option B — Keep all reports (status quo)

- **Pros:** zero work; every report forever retrievable in the working tree.
- **Cons:** the unbounded growth the analysis flagged; the large-file guard already abstains, so the
  count only rises. Rejected.

### Option C — Age-based retention (delete older than D days)

- **Pros:** time-bounded rather than count-bounded.
- **Cons:** a burst of runs in a short window still floods the directory; count-bounding is the more
  direct fix for "too many files." Rejected; count-based is simpler and matches the stated problem.

## Consequences

**Positive:**
- Both report directories stay bounded at ~10 runs; the dashboard and any consumer see a small,
  recent set; the `*_LOG.md` index remains the complete historical record.
- Reusable in managed projects (PATH-installed), so the retention policy ships, not just dogfoods.

**Negative / costs:**
- Prompt-wired invocation means retention is eventually-consistent, not enforced-at-write (see the
  Option A con and falsifier).
- A one-time prune of Praxion's existing backlog deletes ~70 committed reports from the working tree
  (retained in git history) — a large but mechanical deletion, committed separately from the mechanism.
