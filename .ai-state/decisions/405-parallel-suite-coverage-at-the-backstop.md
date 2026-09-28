---
id: dec-405
draft_id: dec-draft-4c5fa4f9
title: Praxion's suite runs parallel by default and measures coverage only at the backstop
status: accepted
category: configuration
date: 2026-09-27
summary: "The root pytest config runs every invocation under pytest-xdist (-n auto, load distribution) and no longer carries --cov in addopts; CI and the canonical coverage target request coverage explicitly, and the coverage-target probe passes --cov --cov-report=xml when addopts lacks it. The two fixtures that broke under parallel runs are fixed in the tests, a `large` marker (deselected by default) replaces the unused `slow` marker, and skills/ joins testpaths."
tags: [testing, pytest-xdist, parallelism, coverage, test-suite-refresh, configuration, backstop]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - pyproject.toml
  - .github/workflows/test.yml
  - scripts/project_metrics/cli.py
  - scripts/project_metrics/tests/conftest.py
  - tests/test_dispatch_reworks_bg.py
  - tests/test_dispatch_reworks_manifest.py
  - task-chronograph-mcp/pyproject.toml
---

## Context

The root suite (5,547 tests) ran serially, with pytest-cov forced on every invocation through `addopts`. A measured baseline on 2026-09-27 found:

- The full suite ran 7× faster under `pytest-xdist -n auto` on a loaded host (841 s → 121 s), and about 1.9× faster in a second back-to-back comparison on the same busy machine (404 s → 209 s).
- Two fixtures blocked parallel runs. The project-metrics git fixtures raced on a cold checkout: 615 `FileExistsError`s, and a cold checkout is CI's starting state. The dispatch-reworks tests created directories in the real checkout's `.claude/worktrees/`, and two tests reuse the same names.
- Coverage overhead is workload-dependent. It is noise on the full suite, because 44% of test files spawn uninstrumented subprocesses. It is about 1.8× on in-process slices such as `hooks/`, and those slices are exactly what agents run in the inner loop.
- Coverage in `addopts` rewrote `coverage.xml` with a partial measurement on every scoped run. It also put a coverage table into the output tail that agents read. This contradicted the test-coverage skill's own rule against regenerating as a side effect.
- `--dist loadfile`, the recommended default in the Python leaf, lost to `load`: one 109-test sidecar file pins a single worker. `worksteal` also measured slower than `load` here.

## Decision

- **Parallel by default.** `addopts` becomes `-ra --strict-markers -n auto --dist load -m 'not large'`, with `pytest-xdist` added as a dev dependency. Parallel-safety is enforced by always running parallel. Debugging uses `-p no:xdist`.
- **Coverage leaves the default run.**
    - CI's root step requests `--cov … --cov-fail-under=80` explicitly. The floor is unchanged and pytest-cov combines worker data.
    - `_discover_coverage_target` in `scripts/project_metrics/cli.py` now appends `--cov --cov-report=xml` when a project has `[tool.coverage.*]` config but no `--cov` in `addopts`. Without that, plain `pytest` would produce no `coverage.xml`.
- **Parallel hazards are fixed in the tests, not recorded as metadata.**
    - The project-metrics fixture build is serialized with an exclusive `flock` and re-checked under the lock.
    - The dispatch-reworks tests each run the script from their own throwaway git repository.
- **A `large` marker replaces the never-applied `slow` marker,** for tests needing live external services; it is deselected by default. The chronograph Phoenix diagnostics carry it; their live failure is td-289.
- **`skills` joins `testpaths`,** because `skills/skill-crafting/tests/` ran nowhere.

## Considered Options

### Keep coverage in `addopts`, add only xdist

- Pro: no change to how the metrics report finds its coverage target.
- Con: keeps the inner-loop cost, the `coverage.xml` clobbering and the noisy tails. The probe fix solves discovery directly.

### Parallel only in CI; serial locally

- Pro: no worker start-up cost (~3 s with 12 workers) on tiny local runs.
- Con: parallel hazards surface only in CI, after the change is pushed. Local full runs keep their full serial cost. The start-up cost is better removed by the test-scope resolver, which knows the size of each selection.

### Record unsafe groups as `parallel_safe: false` and run them in a separate serial invocation (the dec-086 mechanism)

- Pro: no test changes.
- Con: this keeps a hazard as metadata that must be maintained, instead of fixing a small, known defect. Both fixes turned out to be under 30 lines.

## Consequences

- Positive:
    - The full suite is several times faster locally and on CI.
    - A newly introduced shared-state test fails locally, not only in CI.
    - `coverage.xml` is written only by deliberate measurements.
    - Agent-facing output tails are shorter.
    - 43 previously unrun tests now run.
- Negative:
    - Every invocation pays roughly 3 s of worker start-up until the resolver drops xdist for tiny selections.
    - `--pdb` and single-test debugging need `-p no:xdist`.
    - Four chronograph diagnostics are out of the default run until td-289 is fixed.
- The broader test-selection and topology changes, including superseding dec-086's runner-level isolation, are decided separately by the test-suite-refresh architecture.

## Erratum

The debug escape cited above and in Consequences as `-p no:xdist` is incorrect under this ADR's own `addopts`: `-n auto --dist load` is already active, and `-p no:xdist` errors when xdist is already loaded. The correct debug escape is `-n 0`. Corrected 2026-09-27 by the test-suite-refresh pipeline; no semantic change to the decision.
