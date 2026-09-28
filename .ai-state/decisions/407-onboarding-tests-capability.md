---
id: dec-407
draft_id: dec-draft-dce28525
title: Onboarding gains a `tests` capability that ships a parallel, coverage-off test baseline with derived selection from day one
status: accepted
category: architectural
date: 2026-09-28
summary: "A new onboarding capability `tests` (Phase 8e.10-8e.13, default on in new mode, opt-in for existing) installs a parallel, coverage-off runner config; tests/acceptance/ and tests/e2e/ with ownership READMEs; an empty tests/declared-deps.toml; a test CI workflow (full parallel suite with a ratchet coverage floor) and a scheduled workflow (large tests, audit, flaky and slow reports); and a `## Testing` canonical block. There is no topology file and no adoption threshold."
tags: [onboarding, testing, canonical-block, ci, project-baseline, test-suite-refresh, published-contract]
made_by: agent
agent_type: systems-architect
branch: worktree-test-refresh-core
pipeline_tier: full
affected_files:
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-optional.md
  - scripts/onboard-project
  - claude/canonical-blocks/project-essentials.md
  - claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl
  - scripts/sync_canonical_blocks.py
affected_reqs: [REQ-18, REQ-19, REQ-20]
dissent: "Shipping CI workflows and directory scaffolds by default for `new` projects presumes GitHub Actions and a single test runner, and the scheduled job pulls scripts from the Praxion hub at a pinned SHA. That couples every new project's CI to the hub's availability."
---

## Context

Managed projects receive Praxion's testing philosophy (skills, rules) and its dormant selection machinery, but no testing defaults:

- no runner config;
- no test CI workflow, so ci-autofix has nothing to watch;
- no layout scaffold;
- no coverage configuration beyond a default that puts `--cov` in the inner loop.

Before this change the only test content in the onboarding blocks was a `<test command>` placeholder in Project Essentials. The topology adoption path required a growth trigger that cannot fire, and `/refresh-topology --init` needed four or more Built components. Derived selection (dec-406) removes both prerequisites, so selection can work in a project from its first commit.

## Decision

Add a capability `tests` to the Capability IDs, owning sub-steps 8e.10–8e.13.

| Mode | Default |
|---|---|
| `new` | On |
| `existing` | Off (opt-in via `--with tests` or the G3 Profile) |
| `--profile all` | Included |
| `hackathon` | Skipped |

Each sub-step checks whether its file already exists and skips it if so. Nothing is overwritten.

- **8e.10: runner config.**
    - Python: append `[tool.pytest.ini_options]` from `skills/python-development/assets/pytest-baseline.toml`:
        - `-ra --strict-markers -n auto --dist load -m 'not large'`
        - the `large` marker
        - no `--cov`

      Then print the dev-dependency install command.
    - TypeScript: vitest already runs in parallel with coverage off by default, so only a note is printed.
    - Rust: print the nextest suggestion.
- **8e.11: outer-loop directories.** Create `tests/acceptance/README.md` and `tests/e2e/README.md`, which state that the implementer runs these tests but never edits them.
- **8e.12: declared list.** Create `tests/declared-deps.toml` with `schema = 1` and a header only.
- **8e.13: workflows.** Create `.github/workflows/test.yml` and `.github/workflows/test-scheduled.yml` from `claude/project-baseline/tests/*.tmpl`.

  | Placeholder | Filled with |
  |---|---|
  | `{{FULL_TEST_COMMAND}}` | The project's full test command |
  | `{{COVERAGE_FLOOR}}` | `new`: 80. `existing`: the measured coverage rounded down, or 0 plus a printed instruction to raise it as coverage rises |
  | `{{PRAXION_HUB}}`, `{{HUB_SHA}}` | The Praxion hub and a pinned SHA. The scheduled job sparse-checks out the hub's `scripts/` at that SHA to run the audit |

  When `ci` is selected in the same run, 8e.8 adds these workflow names to its watched list.

The capability also adds a new canonical block, `claude/canonical-blocks/testing.md` (`## Testing`). Onboarding fills it and appends it once; it is not refreshable. It carries:

- the layout convention;
- the selected-run command (`resolve_test_scope.py | sh -e`);
- the full-run command;
- a pointer to the declared-deps list;
- the rule that the outer loop is read-only.

When `tests` is selected, item 2 of Project Essentials' Verification list points to `## Testing`. Otherwise it is filled with the detected test command, as today.

**Sidecar placement.**

| Artifact | Treatment |
|---|---|
| Tracked files (runner config, directories, declared list) | Share-gated, like `quality` |
| Workflows | Dropped, like the `architecture.yml` sub-surface of `aac` |

**Dogfooding.** Praxion carries the same shape:

- `tests/declared-deps.toml`
- `tests/acceptance/README.md` and `tests/e2e/README.md`
- `.github/workflows/test-scheduled.yml` (name `Test (scheduled)`), watched by ci-autofix
- its existing `test.yml`, which gains a junit artifact

## Considered Options

### Fold the scaffolding into `quality`

- Pro: no new capability ID.
- Con: `quality` defaults on for any detected stack in existing projects. The brief makes `tests` opt-in there, and a test CI workflow is an organizational choice, not linter hygiene.

### Ship the `## Testing` block as `core`

- Pro: the Project Essentials placeholder is always replaced.
- Con: it cuts across the capability boundary the user approved. The two-branch fill of item 2 avoids a dangling reference either way.

### Install the scheduled audit as a hub reusable workflow (`on: workflow_call`)

- Pro: mirrors ci-autofix.
- Con: junit must pass between the caller and callee jobs through artifacts, and the audit is one stdlib script. A sparse checkout of the hub at the pinned SHA is simpler, and it uses the same pinning discipline.

### A new capability, `tests`, with templates in `claude/project-baseline/tests/` (chosen)

## Consequences

- Positive:
    - New projects get parallel runs, derived selection, a CI backstop with a ratchet floor, a scheduled health job, and the outer-loop layout from day one.
    - ci-autofix gains a real target to watch.
- Negative:
    - The onboarding surface grows: four sub-steps, two templates, one block, one asset, plus tests for the capability tables.
    - The scheduled job depends on the hub being reachable at a pinned SHA; if it cannot fetch, it skips the audit with a warning.
    - Existing projects must opt in to get the scaffold.

## Disconfirmation

- **Falsifier:** onboarded `new` projects routinely delete or disable the shipped `test-scheduled.yml`, or its runs are red for environmental reasons more often than for real ones (hub fetch failures, `large` tests without services). That would mean the default is noise rather than signal.
- **Steelmanned runner-up:** ship only the CLAUDE.md block and the declared list, since selection needs nothing else, and leave the CI workflows and scaffolding to the `cicd` skill on request. This gives the smallest published surface, no hub coupling in CI, and no presumption of GitHub Actions.
- **Reversal trigger:** within two release cycles, a majority of observed `new`-mode onboardings drop `--with tests`, or two hub-availability incidents redden managed projects' scheduled jobs. Then move the workflows out of the default and keep only the block and the list.
