---
id: dec-246
title: Unify the bespoke commit gate into the pre-commit framework
status: accepted
category: architectural
date: 2026-06-20
summary: Replace Praxion's bespoke git-pre-commit-hook.sh with .pre-commit-config.yaml; five author blocks become repo:local hooks alongside ruff + gitleaks.
tags: [pre-commit, commit-gate, tooling, readiness, dogfooding]
made_by: agent
agent_type: systems-architect
branch: feat-l3-readiness-config
pipeline_tier: full
affected_files:
  - .pre-commit-config.yaml
  - scripts/git-pre-commit-hook.sh
  - install_claude.sh
  - pyproject.toml
dissent: A separate minimal pre-commit config (ruff+gitleaks only) that leaves the proven 5-block shell author gate untouched carries zero regex-transcription risk to author-gate enforcement.
---

## Context

Praxion fails its own `c.style.precommit_config` L3 readiness check: it has no `.pre-commit-config.yaml`. In its place a bespoke 198-line `scripts/git-pre-commit-hook.sh` (symlinked into `.git/hooks/pre-commit` by `install_claude.sh`) runs five Praxion-author-only blocks: (A) shipped-artifact isolation, (B) canonical-block sync, (C) diagram regeneration, (D) AaC golden-rule gate, (E) rules-manifest drift. Standard checks (ruff lint+format, a secret scanner) run only via Claude Code session hooks, not at git-commit level. Praxion's own `coding-style.md` Baseline-Configuration mandate tells managed projects to carry a `.pre-commit-config.yaml` and NOT to hand-roll gates — Praxion violates its own rule.

## Decision

Unify the commit gate into the `pre-commit` framework. Author `.pre-commit-config.yaml` at the repo root carrying: ruff (lint `--fix` + format), gitleaks (secret scanner), pre-commit-hooks file hygiene, AND the five author blocks re-expressed as `repo: local` hooks that invoke the existing checker scripts (`check_shipped_artifact_isolation.py`, `sync_canonical_blocks.py`, `diagram-regen-hook.sh`, `check_aac_golden_rule.py`, `regenerate_rules_manifest.py`) with their exact staged-file filters preserved via `files:` regex. Retire `scripts/git-pre-commit-hook.sh` and rewrite `install_claude.sh install_praxion_pre_commit()` to run `pre-commit install` instead of symlinking. The checker scripts themselves are unchanged.

Behavior-preservation contract: for each block A–E the (staged-file filter → checker invocation → pass/fail) tuple is identical before and after. Blocks B/C/D/E use `pass_filenames: false` (the scripts self-discover the staged set via `git diff --cached`); Block A uses `pass_filenames: true` (it takes an explicit `--files` list).

## Considered Options

### Option 1 — Unify into `.pre-commit-config.yaml` (chosen)
- Pros: one gate definition (no drift between shell dispatcher and a parallel config); standard pre-commit ecosystem (caching, `--all-files`, autoupdate); ruff+gitleaks at git level; readiness passes as a side effect of real unification.
- Cons: adds a `pre-commit` framework dependency; `repo: local` hooks are more verbose; exact-filter mapping must be tested.

### Option 2 — Safe standalone config (runner-up)
- Keep `git-pre-commit-hook.sh` as the author gate; add a separate minimal `.pre-commit-config.yaml` (ruff+gitleaks only) just to flip the readiness check.
- Pros: zero risk to the proven author gate; trivial to add.
- Cons: two coexisting gate mechanisms guarantee eventual drift; perpetuates the hand-rolled gate `coding-style.md` forbids; the readiness file becomes a vanity artifact, not real unification.

## Consequences

- Positive: single source of truth for the commit gate; standard tooling; closes the git-level lint/secret-scan gap; L3 `precommit_config` passes; Praxion dogfoods its own mandate.
- Negative: migration risk (a `files:`-regex transcription error could widen/narrow a block's trigger); a new dev-dependency on `pre-commit`; the installer must handle `pre-commit` being absent gracefully.

## Disconfirmation

- **Falsifier:** if a `repo: local` hook cannot reproduce a block's `git diff --cached`-based full-staged-set self-discovery (pre-commit batches per file), Option 1 is wrong for that block; fall back to a single `repo: local` shell hook with `pass_filenames: false` wrapping that block.
- **Steelmanned runner-up:** Option 2 is strictly safer for author-gate enforcement — it never touches Block A–E, so no transcription bug can silently disable isolation/sync/golden-rule checks. If enforcement were security-critical and migration appetite were zero, it would win.
- **Reversal trigger:** revisit if the pre-commit framework adds unacceptable commit latency, or if a block's self-discovery semantics break under pre-commit invocation, or if the framework dependency proves unavailable in target dev environments.
