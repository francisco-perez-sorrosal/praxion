---
id: dec-221
title: Unified out-of-tree run-storage model for experiment/eval-bearing projects
status: accepted
category: architectural
date: 2026-06-05
summary: Operational run artifacts default out of the repo tree at $HOME/.<project-name>/; commit only the curated tier-2 summary + config.
tags: [storage, eval, agentic-eval, ml-training, run-store, archetype, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/agent-evals/references/run-ledger-schema.md
  - rules/swe/agent-intermediate-documents.md
  - commands/onboard-project.md
related: [dec-220, dec-217, dec-218, dec-219, dec-216]
---

## Context

The SIA → Praxion fit study (P2) surfaced that every experiment/eval-bearing managed project
produces high-volume operational artifacts (generated agent code, logs, submissions,
trajectories, per-step metric traces, checkpoints) interleaved with a small amount of curated
intelligence worth preserving. SIA itself has no separation — cross-generation memory is a
single free-text `context.md`, tokens are discarded, and comparing runs is a manual markdown
diff. Praxion's existing ML convention partially solves this but commits *per-run traces*
in-tree (`experiments/<run-tag>/config.yaml`, `metrics.jsonl`), mixing disposable detail with
the repo.

Placement is locked by `CONTEXT_REVIEW.md` (P2 two-tier model). This ADR formalizes the
load-bearing storage decision the whole enhancement program rests on.

## Decision

Adopt a **two-tier storage model** for any experiment/eval-bearing managed project:

- **Tier 1 — operational run store (out of the repo tree, not committed).** Heavy per-run
  artifacts default to `$HOME/.<project-name>/` (client-configurable). Disposable, regenerable.
- **Tier 2 — curated intelligence (committed, small).** A per-kept-run summary
  (`EVAL_RESULTS.md` at project root, sibling to `TRAINING_RESULTS.md`) plus an append-only
  aggregate (`.ai-state/eval_ledger/EVAL_LOG.md`). Each tier-2 record cross-references the
  tier-1 `run_id` + `store_uri`.

The portable default (`~/.<project-name>`, `$HOME` expands per-user) is committed in
`.ai-state/project_profile.yaml` `run_store_root:`. Machine-specific absolute paths live only in
gitignored `.claude/settings.local.json` or env vars — never committed.

## Considered Options

### A — In-tree gitignored operational artifacts (current ML `runs/`/`checkpoints/` pattern)
- Pros: artifacts present in the working tree; no external store.
- Cons: clutters the working tree; risks accidental commits (answer keys, checkpoints); the
  `.ai-state`/git surface must constantly exclude them.

### B — Commit per-run traces in-tree (current ML `experiments/<run-tag>/` pattern)
- Pros: full per-run trace is versioned and diffable in git.
- Cons: commits high-volume disposable detail; bloats the repo; conflates operational output
  with curated intelligence — the exact anti-pattern this program corrects.

### C — Out-of-tree operational store; commit only curated summary + config (CHOSEN)
- Pros: zero git/`.ai-state` interference; no accidental answer-key/checkpoint commits; clean
  disposable-vs-curated separation; the committed summary + `store_uri` are sufficient for
  leaderboard/audit/reproducibility.
- Cons: artifacts are not in the clone (regenerate or fetch from the store); one more config
  indirection.

## Consequences

- **Positive:** a single, clean storage invariant for the archetype; the curated commit is tiny;
  the operational store is pluggable (see `dec-220`). Improves on the ML convention.
- **Negative:** reproducibility depends on the store being reachable — mitigated by committing
  `store_uri` + the curated summary. Introduces `project_profile.yaml` config indirection
  (see `dec-219`).
- **Cross-cutting:** this model is *recommended* to also absorb the ML branch
  (`dec-218`); if that reconciliation is declined, this ADR's scope must be narrowed
  to agentic-eval projects and explicitly carve out ML.
