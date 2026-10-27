---
id: dec-draft-f90fa3fc
title: Select tests that drive another pocket through a derived pocket-drive edge
status: proposed
category: behavioral
date: 2026-10-27
summary: A module outside a pocket whose code holds the constant --project and a constant equal to the pocket's root path drives that pocket; a change inside the pocket selects, through the import closure, every test that imports such a module.
tags: [test-selection, resolver, pockets, eval]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-repairs
pipeline_tier: standard
affected_files:
  - scripts/_python_selection.py
  - scripts/resolve_test_scope.py
  - skills/testing-strategy/references/test-selection.md
affected_reqs: [REQ-01, REQ-02, REQ-03]
---

## Context

Root-pocket tests that run the eval package through `uv run --project <root>/eval` (the adherence partial-output scenarios, the spend-and-results journey, the no-claude tripwire, and the rest built on the same drivers) were never selected by a change to the eval package, `eval/pyproject.toml` or `eval/uv.lock`: the resolver's layout, import, path-literal and declared sources see no edge, because the code is reached in a child process and the pocket path is built from a bare `"eval"` constant, which dec-471 keeps inside its own pocket. The final CI-equivalent run of lean-spawn-continuation found six regressions this way (td-476); the selection audit later confirmed the gap (td-500's evidence).

## Decision

Add a fifth, derived edge source, `pocket-drive`. A module outside pocket P is a driver of P when its syntax tree holds a string constant `--project` and a string constant equal to P's root-relative path. A changed path inside P maps to every driver of P; from each driver the existing import closure (transitive through non-test modules) reaches the tests, each attributed `via: pocket-drive` with `because` the changed path. It is last in the attribution order, adds no output key, and leaves every other answer byte-identical. Widening for a pocket's configuration or lockfile change is unchanged.

**Activation:** no -- one component, one viable derived design; the declared alternative fails REQ-02 by construction.

## Considered Options

### Derived pocket-drive edge (chosen)
- Pro: a test added later through the same drivers is selected with no edit; works in any managed project that drives a Python pocket with `uv run --project`.
- Con: a pocket path built from several segments, or another launcher (`cd` in a shell string, `--directory`), is a declared limit; a module that merely mentions both constants over-selects (safe direction).

### A `[[dep]]` entry listing today's eval-driving tests
- Pro: smallest change.
- Con: a hand-kept list, which is how the resolver's predecessor drifted; the next such test escapes it (rejected by the answered Spec Question).

### Widen the root pocket on every eval change
- Pro: cannot miss.
- Con: every eval edit pays the whole root suite (about 1,100 s).

## Consequences

- Positive: steps in the eval pocket (Phase 3) get the root tests that would catch their regressions; managed projects with a driven pocket benefit without configuration.
- Negative: selection for eval changes grows by the driven tests (bounded by the selection-size footprint); the declared limits stay the selection audit's to catch.
