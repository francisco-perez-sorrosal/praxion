---
id: dec-draft-0555e355
title: Sidecar-placement scripts split across six sibling modules
status: proposed
category: implementation
date: 2026-09-02
summary: Decompose SYSTEMS_PLAN.md's DS-2/3/5/6/7/8/9 across five new scripts/ sibling modules plus a thin praxion-sidecar CLI, mirroring the finalize_adrs.py split pattern.
tags: [sidecar-placement, module-structure, code-organization]
made_by: agent
agent_type: implementation-planner
pipeline_tier: full
branch: worktree-sidecar-placement
affected_files:
  - scripts/_state_repo.py
  - scripts/_sidecar_manifest.py
  - scripts/_sidecar_checks.py
  - scripts/_sidecar_link.py
  - scripts/_sidecar_commit.py
  - scripts/praxion-sidecar
affected_reqs: [REQ-15, REQ-16, REQ-17, REQ-18, REQ-19, REQ-22, REQ-24, REQ-25, REQ-30, REQ-31, REQ-35, REQ-36, REQ-37]
---

## Context

`SYSTEMS_PLAN.md § Architecture § Data Structures` specifies seven data
structures for P1 (sidecar placement) — DS-2 (manifest), DS-3 (placement
resolver), DS-5 (exclude-block rewrite), DS-6 (shadow-slot classification),
DS-7 (identity), DS-8 (CLAUDE.md placement cases), DS-9 (commit serialization)
— plus an 8-subcommand CLI (`praxion-sidecar`) that consumes all of them. The
architect's Components table names `scripts/_state_repo.py` and
`scripts/praxion-sidecar` as the two new files, without prescribing whether the
CLI's remaining logic (manifest parsing, the check registry, link
reconciliation, commit locking) lives inline in `praxion-sidecar` or in
further sibling modules. Step decomposition must choose a concrete file layout
before writing implementation steps.

## Decision

Split the DS-bearing logic across six files: `scripts/_state_repo.py` (DS-3,
DS-7 — the stdlib-only hot-path resolver), `scripts/_sidecar_manifest.py`
(DS-2, DS-8 — the only module permitted to import PyYAML), `scripts/
_sidecar_checks.py` (the D3 check registry, one source of truth rendered by
both `status` and `doctor`), `scripts/_sidecar_link.py` (DS-5, DS-6 — the
`link` verb's reconciliation logic), `scripts/_sidecar_commit.py` (DS-9 —
advisory-lock commit serialization), and `scripts/praxion-sidecar` itself as
thin CLI orchestration (argparse, exit-code contract, help text, error
messages) over the five siblings.

## Considered Options

### Option A — One `praxion-sidecar` file with everything inline

Single file implementing all 8 subcommands, all 7 data structures, and the
check registry.

- **Pros**: no cross-module imports to reason about; matches
  `INTERFACE_DESIGN.md` A1's original bash-single-script assumption.
- **Cons**: first-pass estimate exceeds 1500 lines against
  `coding-style.md`'s 800-line hard ceiling; mixes the stdlib-only hot path
  (DS-3/DS-7, read by every hook and finalize script) with the
  PyYAML-dependent full manifest parser in one file, obscuring DS-2's "two
  readers, two parsers, one owner" invariant at the file-organization level
  even though the logical separation would still exist in code; one test file
  would need to cover unrelated concerns (locking, YAML parsing, symlink
  classification, CLI argument parsing), violating `testing-strategy`'s
  file-mirrors-source convention.

### Option B — `_state_repo.py` only, everything else inline in `praxion-sidecar`

Keep the hot-path resolver separate (as the architect's table already
requires) but fold DS-2/DS-5/DS-6/DS-8/DS-9 and the check registry into the
CLI file.

- **Pros**: fewer files than the chosen option; still separates the
  stdlib-only hot path from the PyYAML-dependent CLI.
- **Cons**: still exceeds the file-size ceiling on a smaller margin; DS-2's
  manifest smart constructor and DS-9's commit-lock discipline are each
  independently complex enough (multiple closed enums, cross-field
  invariants, an advisory-lock protocol) to warrant dedicated test files: one
  `test_praxion_sidecar.py` covering all of manifest parsing, link
  reconciliation, and commit locking becomes an unmanageable mixed-concern
  test file.

### Option C — Six sibling modules (chosen)

As described in Decision above.

- **Pros**: each module owns exactly one DS/responsibility
  (`coding-style.md § Code Organization`); mirrors the codebase's existing
  `finalize_adrs.py` + `finalize_adrs_{fragments,crossrefs,backlinks}.py`
  precedent, so the pattern is already familiar to future maintainers; each
  module gets its own test file, keeping per-concern test suites cohesive;
  the PyYAML-import boundary is enforced at the file level, not just by
  convention.
- **Cons**: more files to navigate; `praxion-sidecar`'s CLI orchestration
  must import from five siblings rather than defining everything locally.

## Consequences

- **Positive**: no file in the P1 surface risks the 800-line ceiling; the
  stdlib-only/PyYAML boundary is structurally enforced (only
  `_sidecar_manifest.py` imports `yaml`); each new module has a dedicated,
  cohesive test file; the pattern is consistent with the codebase's existing
  `finalize_adrs.py` sibling-module precedent, lowering the learning curve
  for future contributors.
- **Negative**: six new files instead of one or two — more surface area to
  onboard a new contributor to, though each file is individually small and
  single-purpose.
- **Risk accepted**: none beyond ordinary module-boundary maintenance; this
  decision does not change what the architecture builds, only how its
  already-specified data structures are distributed across files.

## Departure from the Plan

Not a supersession — this decision fills a gap the architect's Components
table left open (file-level packaging within an already-approved component
region), rather than replacing or narrowing any prior decision.
