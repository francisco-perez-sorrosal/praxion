---
id: dec-280
title: Split the reporter script into a praxion_feedback package by responsibility
status: accepted
category: implementation
date: 2026-07-23
summary: scripts/report_praxion_issue.py becomes a thin argparse CLI over a new scripts/praxion_feedback/ package (fingerprint.py, sanitizer.py, candidate_store.py, render.py), each independently unit-testable with no CLI/network concerns — because the fingerprint/normalization logic is explicitly the dedup contract and the primary test target, and mixing it with argparse plumbing, file I/O, and rendering in one file would both blow past the file-size/single-responsibility conventions and make the highest-risk logic harder to test in isolation.
tags: [self-healing-loop, healing-sidecar, module-structure, praxion-feedback, fingerprint, scripts]
made_by: agent
agent_type: implementation-planner
branch: feat-self-healing-p4
pipeline_tier: standard
affected_files:
  - scripts/report_praxion_issue.py
  - scripts/praxion_feedback/__init__.py
  - scripts/praxion_feedback/fingerprint.py
  - scripts/praxion_feedback/sanitizer.py
  - scripts/praxion_feedback/candidate_store.py
  - scripts/praxion_feedback/render.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-07, REQ-08]
re_affirms: dec-279
---

## Context

`SYSTEMS_PLAN.md` (dec-279) names the reporter as a single file,
`scripts/report_praxion_issue.py`, exposing `capture` / `render` / `list` / `mark-filed`
subcommands. That is the external CLI contract — not a mandate that all logic lives in
one file. The plan's own Risk Assessment singles out fingerprint normalization as the
dedup contract and "the primary test target," and the Test lens calls the script
"stdlib-only and deterministic ... fingerprint, normalization, sanitizer, render are pure
functions." Estimated combined size of normalization + sanitizer regex catalog +
PENDING.md candidate-block I/O + rendering + argparse wiring comfortably exceeds the
200-400 line target for a single file and mixes at least four distinct concerns
(hash/normalize, redact, persist, project-to-markdown).

`scripts/project_metrics/` is an existing precedent in this same `scripts/` directory
for a multi-concern script suite organized as a package with a `tests/` subdirectory
(`scripts/project_metrics/tests/test_*.py`), and `scripts/_repo_root.py` already
provides the exact git-root-resolution helper the reporter needs (never `__file__`) —
reusing it avoids a second implementation of the same plugin-cache-safe logic.

## Decision

`scripts/report_praxion_issue.py` becomes a thin argparse CLI that imports from a new
`scripts/praxion_feedback/` package:

- `fingerprint.py` — `normalize_error`, `normalize_artifact_path`, `compute_fingerprint`
- `sanitizer.py` — mechanical sanitizer (secret/PII/path stripping) + scope-filter
  (shipped-family path-shape check)
- `candidate_store.py` — `PENDING.md` candidate-block parse/append/dedup/list/mark-filed
- `render.py` — §5.2 markdown body projection (owns the fixed heading-order constant)

Each module gets its own `scripts/praxion_feedback/tests/test_<module>.py`, mirroring
`scripts/project_metrics/tests/`. `report_praxion_issue.py` reuses
`scripts/_repo_root.py`'s `resolve_repo_root` / `git_toplevel_from_cwd` for the
managed-project-root resolution instead of reimplementing it.

The external CLI surface (subcommand names, flags, file paths) is unchanged from
`SYSTEMS_PLAN.md` — this is purely an internal module-layout decision.

## Considered Options

### Option A — package split by responsibility (chosen)
- **Pros:** isolates the highest-risk logic (fingerprint normalization) for focused unit
  testing with zero CLI/network noise; reuses `_repo_root.py` instead of duplicating it;
  matches the existing `project_metrics/` precedent in the same directory; keeps every
  file within the file-size/single-responsibility conventions.
- **Cons:** one more directory to navigate than a single file; a reader has to open four
  files instead of one to see the whole reporter.

### Option B — single `scripts/report_praxion_issue.py` file (as literally named in SYSTEMS_PLAN.md)
- **Pros:** matches the plan's file list exactly with no interpretation; one file to
  open.
- **Cons:** mixes hash/normalize, redact, persist, and render concerns in one file,
  pushing it past the file-size target; makes it harder to unit-test the normalization
  function (the dedup contract) without also exercising argparse/file-I/O scaffolding;
  does not reuse `_repo_root.py` as cleanly since the git-root logic would live inline
  alongside unrelated concerns.

## Consequences

- **Positive:** the dedup-contract logic (fingerprint normalization) is independently,
  heavily testable exactly as the plan's Risk Assessment demands; `report_praxion_issue.py`
  stays a thin, readable entrypoint; the codebase gains no new cross-cutting convention
  (the package-with-tests-subdir shape already exists for `project_metrics/`).
- **Negative / cost:** four new files instead of one; a future reader must know the
  package exists rather than finding everything in a single named file (mitigated by the
  CLI wrapper importing all four modules at the top, making the map visible on open).

## Disconfirmation

- **Falsifier:** if the four modules turn out to be trivially small (each well under 100
  lines) such that the combined file would have stayed under 300 lines anyway, the split
  adds navigation overhead for no isolation benefit.
- **Steelmanned runner-up:** Option B is simpler to describe to a first-time reader ("one
  script, four subcommands") and matches the plan's literal file list without requiring
  this ADR at all.
- **Reversal trigger:** if a future maintainer finds the four-file navigation genuinely
  costly relative to the isolation benefit (e.g., the fingerprint function never changes
  independently of the others across several feature cycles), collapse back to one file.

## Prior Decision

This ADR does not supersede `dec-279` (now finalized as the parent architecture
ADR) — it re-affirms its filing-authority decision and its `scripts/report_praxion_issue.py`
CLI-contract naming while resolving an internal module-layout question the parent ADR left
to "the implementer/planner's call" (see `SYSTEMS_PLAN.md` § Existing Patterns).
