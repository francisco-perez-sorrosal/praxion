---
id: dec-406
draft_id: dec-draft-40ba0ce1
title: Derived test selection with a selection audit replaces the hand-maintained test topology
status: accepted
category: architectural
date: 2026-09-28
summary: "resolve_test_scope.py derives tests from four edge sources (layout, a stdlib-ast import graph, path literals, and a small declared list at tests/declared-deps.toml), and dispatches other ecosystems to their native tools. Anything unmapped widens to the full suite. audit_tests.py turns full-run failures into miss records, and GL07 flags uncollected test files. TEST_TOPOLOGY.md, the test-topology trunk, /refresh-topology, check_topology_conformance.py, _topology_yaml.py and the TT01-TT07 checks are removed."
tags: [testing, test-selection, test-topology, resolver, selection-audit, gate-liveness, retirement, test-suite-refresh]
made_by: agent
agent_type: systems-architect
branch: worktree-test-refresh-core
pipeline_tier: full
supersedes: [dec-085, dec-086, dec-089, dec-091, dec-194]
affected_files:
  - scripts/resolve_test_scope.py
  - scripts/check_gate_liveness.py
  - skills/testing-strategy/SKILL.md
  - commands/test.md
  - agents/implementer.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - agents/sentinel.md
  - .github/workflows/test.yml
affected_reqs: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-16, REQ-17]
dissent: "A stdlib ast scan re-implements what grimp, already locked in through import-linter, does faster and more robustly. It also turns Praxion's unusual flat-import layout into a general design constraint."
---

## Context

The test topology was a 58 KB hand-maintained file with three owners per section. It drifted faster than anyone could maintain it:

- 24 maintenance commits in seven weeks.
- 40 orphan test files found in a single reconciliation, and 2 open today.
- 30 of the 63 manual overrides cite `topology-stale`, and agents made up 7 more reasons outside dec-089's enum.

Several of its mechanisms never fired:

- TT06 cannot fire, because runtime data is always withheld.
- TT04 has skipped on every run.
- TT03 has never produced a row.
- Registry 2 has no consumer.

The topology also could not describe Praxion's own sub-project runners (td-137). Meanwhile Praxion's tests are laid out next to the code they test, so the map was mostly derivable from the code anyway.

The external literature converges on two points:

- Selection should be derived from the graph, with a full-suite backstop behind it. Nx, Turborepo, Pants, Bazel and Microsoft TIA all fall back to running everything when they are unsure.
- Native tools already exist for every ecosystem except Python.

## Decision

### Selection is derived

`scripts/resolve_test_scope.py` is rewritten as an orchestrator over three private stdlib modules: `_test_inventory`, `_declared_deps` and `_python_selection`/`_native_selection`.

For Python, it builds one dependency graph whose edges come from four sources:

1. **Layout.** A test file co-located with its source, or in a mirrored tree; a `conftest.py` also covers every test in its subtree.
2. **Import graph.** A stdlib `ast` scan.
3. **Path literals.** Paths named in test and module code.
4. **Declared list.** The `[[dep]]` entries in `tests/declared-deps.toml`, a TOML sum type that also has `[[inert]]` entries.

It selects the test files that can reach a changed path, and applies a union of all four sources. Source order only decides which source is credited for a test.

For other ecosystems, the resolver hands off to native tools:

| Tool | How the resolver uses it |
|---|---|
| vitest | `related` |
| jest | `--findRelatedTests` |
| cargo | changed crates and their dependents, via `cargo metadata` |
| go | `go list` packages and their dependents |
| maven | `-pl … -amd` |
| gradle | `buildDependents` |
| nx, turbo, pants | `affected` |
| bazel | always widens (documented `rdeps` recipe) |

The resolver widens to the full suite in these cases:

- an unmapped changed path;
- a change to the resolver's own sources or to the declared list;
- an invalid declared list;
- a runner config or lockfile change, which widens that pocket only;
- a missing tool or adapter, which also widens that pocket only.

When a Python selection is at or below the serial threshold, it runs with `-n 0`. Output is JSON schema 2 with runner-prefixed argv.

### The audit replaces hand maintenance

`scripts/audit_tests.py` classifies each full-run failure as `selected`, `widened`, `missed` or `unattributable`. When given a rerun, it also classifies failures as flaky; with `--slow N` it reports the slowest tests. It exits 1 on any miss or flaky test. It runs at the integration checkpoint and in the scheduled workflow. A miss is closed by adding the missing edge. This supersedes dec-194's document cross-check.

### Collection is a liveness check

GL07 in `check_gate_liveness.py` flags any test file that no runner collects, whether through a pytest pocket config or a CI-workflow runner path. It replaces TT07 and is portable to managed projects.

### `Tests:` becomes override-only

The field takes `full` or explicit paths, plus a free-text reason. Leaving it out means derived selection. This supersedes dec-089's enum.

### What is removed

- `.ai-state/TEST_TOPOLOGY.md`
- `skills/testing-strategy/references/test-topology.md`, replaced by `references/test-selection.md`
- `commands/refresh-topology.md`
- `scripts/check_topology_conformance.py` and its test
- `scripts/_topology_yaml.py`
- the test-topology fixtures
- sentinel TT01–TT07 and pre-commit Block Q
- the topology clauses in six agent prompts and `CLAUDE.md.tmpl`

**Activation:** yes. The choice of import-graph backend (grimp vs stdlib `ast`) runs against a user-approved detail, so it was argued as a steelmanned runner-up. See Disconfirmation.

## Considered Options

### Keep the topology, and recalibrate and automate its maintenance

- Pro: no retirement churn.
- Con: the defect is structural. A hand-kept map drifts as fast as the code changes, and automating the reconciliation just produces the map by derivation anyway, with a stale copy kept alongside.

### Coverage-based selection (pytest-testmon) as the default

- Pro: exact edges, observed from real runs.
- Con: it cannot see subprocess children, and 44% of Praxion's test files spawn them. It stays an option for managed projects whose tests run in-process.

### grimp as the import-graph backend (steelmanned runner-up)

- Pro: 0.04 s builds, and a mature parser.
- Con: measured this pass, it records Praxion's flat sibling imports as external modules (0 internal importers of `scripts._git_runner`), so every edge would need a name-to-file remap and a closure computed outside grimp.
- Con: the resolver reaches managed projects as a `~/.local/bin` symlink run under the ambient `python3`, where grimp is never installed. Every unmapped `.py` change would widen.

### Stdlib `ast` graph with the four sources as a union (chosen)

- Pro: one code path everywhere, no dependency, and GL05 is clean by construction.
- Con: a 1.27 s cold scan on Praxion's 474 files.

## Consequences

- Positive:
    - Selection works from day one in any project, with no file to adopt and no threshold.
    - The maintenance burden shrinks to a short declared list, kept honest by the audit.
    - About 9.6 KB of per-spawn agent prose is deleted.
    - The sub-project runners that the topology could not group (td-137) are now handled natively.
- Negative:
    - The native adapters other than vitest cannot be exercised on Praxion itself, so they are verified only against stub tools.
    - The path-literal edges in production modules may over-select. This is measured, and the edges can be narrowed if needed.
    - The first declared list is seeded from the topology and is coarse until it is pruned.
- Risks accepted:
    - Dynamic imports that are not `importlib.import_module("<literal>")` stay invisible. They are covered only by widening, the audit, and the full suite at the integration checkpoint and in CI (dec-084 is unchanged).

## Disconfirmation

- **Falsifier:** if the scheduled or integration-checkpoint audit shows repeated `missed` records traced to import edges that `ast` resolution failed to see, rather than to missing declared entries, then the parser choice is wrong. The same holds if the median selection over recent `main` commits stays above 25% of the corpus even after narrowing literals.
- **Steelmanned runner-up:** grimp through `uv run` in the self-hosted checkout. It is a mature, fast parser, and it is already locked. The flat-import remap is about 30 lines. Managed projects that use import-linter would get it for free, and Praxion's layout is the outlier, not the norm.
- **Reversal trigger:** switch the edge parser behind `_python_selection` if either of these happens:
    - Praxion adopts a package layout (for example `scripts/__init__.py` with qualified imports);
    - the audit logs two or more import-edge misses within a 30-day window.

## Prior Decision

- **dec-085**, superseded. It decided that the topology protocol does not activate at Lightweight. Derived selection has no activation cost, so it runs at every tier that runs tests.
- **dec-086**, superseded. It isolated parallel-unsafe groups at the runner level and defined the marker naming. Parallel hazards are now fixed in the tests themselves, per dec-405. Nothing runs in a separate serial invocation, and the group markers disappear with the groups.
- **dec-089**, superseded. Its closed `selector=manual` enum becomes an override-only `Tests:` field with a free-text reason; the enum had already drifted to 12 observed values.
- **dec-091**, superseded. Language additivity came from typed registries; it now comes from per-ecosystem native-tool adapters inside the resolver.
- **dec-194**, superseded. The verifier's tier cross-check is replaced by the selection audit, which detects under-selection from actual failures.

This decision also retires dec-087, dec-088, dec-090, dec-192, dec-193 and dec-195. It abolishes the topology, and those records are subjects of it: its pilot, its envelope, its regeneration, its growth trigger, the M2 activation and its implementation ordering. It likewise retires dec-202, whose registry is abolished. Each of those records carries its own `## Prior Decision` section.

dec-193 is retired in full, not in part: none of its clauses (topology wiring, the growth trigger, `/refresh-topology`, and its restatements of dec-087 and dec-090) survives unchanged.

dec-084 (full suite at the integration checkpoint) is kept unchanged.
