---
id: dec-355
title: Upgrade-path reconciliation consolidates in the script layer; /upgrade-project stays a standalone thin wrapper
status: accepted
category: architectural
date: 2026-09-01
summary: All /upgrade-project reconciliation logic (labels baseline, AaC namespace surfaces, Block D structural repair) moves from the command body into upgrade_project_pins.sh + a new tested reconcile_aac_surfaces.py; the command remains a standalone shipped command for managed projects, not an onboard-project mode.
tags: [upgrade-path, onboarding, managed-projects, reconciliation, aac, block-d, command-architecture]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - commands/upgrade-project.md
  - scripts/upgrade_project_pins.sh
  - scripts/reconcile_aac_surfaces.py
  - scripts/test_reconcile_aac_surfaces.py
  - claude/aac-templates/precommit-block-d.sh.frag
dissent: "Folding the AaC logic into a second Python script splits the reconciler across three files (sh + two py), where a single onboard-project 'upgrade mode' would give users one entry point for every install-and-maintain operation."
---

## Context

A post-refactor review of `/upgrade-project` (after the onboarding unification)
found the command layer had accumulated executable logic that contradicted its
own design thesis of "deterministic tested script + thin wrapper": a ~60-line
inline Python heredoc reconciling the AaC namespace surfaces (untestable, and
invisible to anyone invoking `upgrade_project_pins.sh` directly), and a
labels-baseline refresh step that ignored `--check`/`--dry-run` and mutated the
manifest anyway. The review also surfaced a shipped defect: the Block D
fragment (`precommit-block-d.sh.frag`) resolved `PLUGIN_ROOT` by walking the
top level of `installed_plugins.json` — whose real shape nests installs under
`.plugins[key][N].installPath` — so the AaC golden-rule gate silently skipped
on every commit in every onboarded project, with no test exercising the
fragment. Finally, the review had to settle the command's target: Praxion only,
or managed projects.

## Decision

1. **Target**: `/upgrade-project` serves **praxion-managed projects**;
   Praxion's own checkout is a recognized self-host no-op. It therefore stays a
   standalone shipped command and is **not** embedded into `onboard-project`.
2. **Consolidation**: every reconciliation surface moves into the script layer.
   `upgrade_project_pins.sh` gains the labels-baseline surface (mode-aware via
   temp-copy + diff) and delegates the AaC surfaces to a new stdlib-only
   `scripts/reconcile_aac_surfaces.py` (namespace token re-point + structural
   repair of the broken Block D region, both under test). The command retains
   only what the script must not do itself: resolving the live plugin path and
   the current hub SHA, and reporting.
3. **Block D repair**: the fragment template is fixed to the Phase-4 jq key
   loop, and the reconciler structurally replaces any installed Block D
   carrying the broken shape; a hand-edited Block D is reported, never
   clobbered.

## Considered Options

### Embed upgrade functionality as an onboard-project mode (rejected)

- Pro: one entry point for install + maintain; the unified skill already
  resolves four modes from detected state.
- Con: onboarding's idempotency predicates are file-existence guards that
  deliberately skip existing files — the upgrade path exists precisely to
  reconcile what those guards cannot reach (SHA-pinned callers, labels
  baseline, instantiated AaC surfaces). Embedding would either re-couple the
  gate-free deterministic path to the gated LLM-driven flow, or require a
  fifth mode that is a wrapper around the same script — indirection with no
  removed duplication.

### Keep the AaC heredoc in the command body (rejected)

- Pro: no new file; logic visible in the command doc.
- Con: untestable, unreachable from direct script invocations and CI `--check`
  runs, and LLM-transcribed at run time. The Block D defect survived precisely
  because fragment behavior had no test home.

### Implement the AaC logic in bash inside upgrade_project_pins.sh (rejected)

- Pro: single-file reconciler.
- Con: multi-line region location (banner → depth-matched `fi`) and
  region replacement are error-prone in bash; a Python sibling keeps the
  logic testable in isolation while the shell script stays the orchestrator.

## Consequences

- Positive: `--check` is now honest for every surface; the Block D gate
  actually fires in onboarded projects once repaired; fragment behavior has
  live-fire regression tests (including the inverse guard demonstrating the
  legacy silent skip); the self-host misclassification of finalize hooks in
  checkouts named `praxion` is fixed and pinned by tests.
- Negative: the reconciler now spans three files; `reconcile_aac_surfaces.py`
  must track onboarding's AaC templates (the existing lock-step obligation in
  `scripts/CLAUDE.md` widens to cover it).
- Residual (out of charter, noted for a future decision): surfaces frozen at
  install by design remain unrefreshed — the hackathon artifact set, the
  metrics-viewer HTML, `.pre-commit-config.yaml` rev pins, and
  `architecture.yml`'s pinned third-party action SHAs (dependabot-class
  staleness, not plugin-upgrade staleness).

## Disconfirmation

- **Falsifier**: managed-project operators repeatedly need upgrade behavior
  that requires judgment (disposition loops, content merges) rather than
  deterministic reconciliation — the thin-wrapper split would then force that
  judgment into the wrong layer, and an interactive mode inside the
  onboarding skill would have been the better home.
- **Steelmanned runner-up**: an `onboard-project --upgrade` mode would give
  one discoverable entry point, reuse the skill's mode-detection scaffolding,
  and guarantee upgrade coverage evolves in the same review unit as the
  install surfaces it mirrors — the lock-step obligation would be structural
  rather than documented.
- **Reversal trigger**: a third maintenance command emerges (beyond
  `/upgrade-project` and `/refresh-claude-blocks`) or the lock-step between
  the reconciler and onboarding's templates breaks twice despite the
  documented obligation — at that point, unify maintenance under one
  mode-resolving entry point.
