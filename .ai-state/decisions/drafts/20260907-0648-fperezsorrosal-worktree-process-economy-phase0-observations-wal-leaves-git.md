---
id: dec-draft-66cd5bb6
title: The raw observations WAL leaves git; a per-session summary stays committed
status: proposed
category: architectural
date: 2026-09-07
summary: .ai-state/observations.jsonl becomes gitignored at its current path (file stays on disk); a new committed .ai-state/observations_summary.jsonl gains one compact row per session at Stop.
tags: [process-economy, observability, observations-jsonl, wal, gitignore, onboarding-contract]
made_by: agent
agent_type: implementation-planner
branch: worktree-process-economy-phase0
pipeline_tier: standard
dissent: Losing the raw WAL from git history removes the only append-only forensic trail across a lost or corrupted working tree — a fresh clone or a wiped .ai-state/ now recovers only the local active file plus the one archived .1 rotation segment, never the full historical row set git previously preserved.
affected_files:
  - .gitignore
  - skills/onboard-project/references/phases-core.md
  - scripts/onboard-project
  - scripts/upgrade_project_pins.sh
  - rules/swe/agent-intermediate-documents.md
  - hooks/capture_session.py
---

## Context

The process-economy roadmap's cost audit found `.ai-state/observations.jsonl` (the raw
observations write-ahead log) responsible for 146 of 1,252 commits in 120 days, a rewrite
(not append-only) git diff footprint, and a documented worktree-merge race — while having
exactly one analytical reader (`scripts/reconcile_pipeline_state.py`) whose own downstream
artifact (`RECOVERY_LOG.md`) has never been produced. `dec-248` established this file as a
git-tracked recovery WAL, and `dec-250` bounded its size via best-effort rotation to a
gitignored `.1` segment. Neither of those decisions is being reopened here: the
step-completion reconciliation architecture they describe is unaffected, because the
reconciler continues to read the same local, working-tree path exactly as before — only the
storage medium of the *active* file changes, from git-tracked to gitignored-but-present.

## Decision

`.ai-state/observations.jsonl` becomes gitignored at its current path (`git rm --cached`,
the file remains on disk with unchanged content and every existing local reader keeps
working). A new Stop-lifecycle hook extension (`hooks/capture_session.py`) appends one
compact, committed row per session to `.ai-state/observations_summary.jsonl` (session id,
started/ended timestamps, spawns by agent type, tool calls by tool, tokens by agent type,
duration, models used, gate-fire counts) — a durable per-session rollup without the raw
WAL's git churn. The onboarding `.gitignore` canonical block and its propagation path
(`scripts/upgrade_project_pins.sh`) are updated so both new and already-onboarded projects
converge on the same state.

## Considered Options

| Option | Pros | Cons |
|---|---|---|
| **Gitignore raw + commit a per-session summary (chosen)** | Removes the commit-churn and merge-race cost entirely; the summary gives durable, low-volume evidence exactly where the roadmap's evidence lens found a real gap (per-agent tokens/duration) | Loses git-historical granularity below the session level for anything not captured in the summary schema |
| Keep raw tracked, periodically squash-compact via scheduled commits | Preserves full git history of every row | Still couples routine per-session bookkeeping to the commit stream; does not resolve the documented worktree-merge race the custom merge driver exists to paper over |
| Status quo — fully tracked, no summary | No implementation cost | This is exactly the measured cost (146 commits/120d, one reader, no output) this decision responds to |

## Consequences

**Positive**: commit-stream bookkeeping cost drops; the worktree-merge race for this file
stops mattering once it is no longer tracked; a genuinely useful, low-volume durable
artifact (the summary) replaces a high-volume one nobody reads. **Negative**: a lost or
never-committed local working tree now has a narrower recovery surface than before (local
active file + one archived `.1` segment, per `dec-250`'s already-established durability
scope) — accepted because `dec-250` had already clarified that git-historical durability was
a commit-cadence convention, not an enforced guarantee, before this decision.

## Disconfirmation

**Falsifier**: if a real recovery incident needs raw per-row WAL history beyond what the
local active file and the archived `.1` segment retain, and git history would have supplied
exactly the missing rows, this decision was wrong to trade that away for commit-stream
economy.

**Steelmanned runner-up**: keep the raw WAL git-tracked but relocate it under
`.ai-state/observations/` with size-based file rotation and periodic squash-compaction
commits, reducing commit count without losing git-historical durability. It loses because
it still couples routine per-session bookkeeping to the commit stream and does nothing about
the worktree-merge race the custom merge driver exists to paper over — it treats the
symptom (commit volume) without removing the underlying coupling.

**Reversal trigger**: if `reconcile_pipeline_state.py`'s local-file recovery model proves
insufficient in a documented incident — specifically, a truncation that could only have
been localized by a git-historical row outside the local active file and `.1` segment —
revisit this decision and restore git tracking (or widen the local retention window) rather
than treating the incident as a `reconcile_pipeline_state.py` defect alone.
