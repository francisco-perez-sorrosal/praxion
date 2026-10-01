---
id: dec-draft-ccf73d37
title: The selection audit's oracle is traced direct and child-process reads, with first-importer credit reported but not judged, evaluated through a per-path resolver mode
status: proposed
category: architectural
date: 2026-10-01
summary: "A committed stdlib read tracer (scripts/gate_probes/tracer/: a sitecustomize audit hook plus a pytest plugin) records, per test file, the tracked files opened for reading on three channels: direct (in-process, non-import, including explicit path loads), child (any read in a process the test started) and import (an in-process load under importlib _find_and_load, credited to whichever test imported first). Bytecode-cache reads map back to source. The verdict judges direct and child pairs only; import pairs are a note. resolve_test_scope.py gains --per-path (with --changed and --json): JSON Lines, each line identical to the single-path payload, with the graph built once. A missing per-path answer counts as selecting nothing"
tags: [test-selection, selection-audit, tracer, determinism, resolver, gate-liveness]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-liveness-prod
pipeline_tier: standard
affected_files:
  - scripts/gate_probes/selection.py
  - scripts/gate_probes/tracer/sitecustomize.py
  - scripts/gate_probes/tracer/selection_trace_plugin.py
  - scripts/resolve_test_scope.py
  - tests/declared-deps.toml
affected_reqs: [REQ-04, REQ-05, REQ-06]
---

## Context

REQ-04 asks for an audit whose oracle is the reads observed while the default suite runs: every test reading a file must be selected when that file changes, and a list of known cases may not replace it. REQ-05 asks for the same verdict and the same unselected pairs on two runs over one commit, "even though which test is credited with a shared module's first import can vary".

The td-296 spike's tracer exists only in a session scratchpad. Two same-mode runs measured on 2026-10-01 (102 s and 107 s, 277 test files) differed on 16 files by 65 paths, all of them import-time reads of production modules credited to whichever xdist worker's test imported first. A resolver CLI call takes about 2 s (measured), so one call per read file (about 1,000 files) would take more than half an hour. A `--changed` union call cannot be decomposed: it reports only the first connecting source per test, and one unmapped path widens the whole call.

**Activation:** no. The three options were compared on measured jitter and cost; no lens sweep was run.

## Decision

- **Tracer**: committed under `scripts/gate_probes/tracer/` (no `__init__.py`, on `PYTHONPATH` only for the traced run). A `sitecustomize.py` installs a `sys.addaudithook` for read-mode `open` events under `PX_TRACE_ROOT` and maps `__pycache__` reads back to their source with `importlib.util.source_from_cache`. A pytest plugin sets the current test file, writes a heartbeat per test file and records the collected set. Records are JSON Lines per process, outside the repository.
- **Channels**:
  - `import`: an in-process open with `importlib._bootstrap._find_and_load` on the stack.
  - `direct`: any other in-process read, including `spec_from_file_location`/`exec_module` and `runpy` path loads.
  - `child`: any read in a descendant process.
- **Verdict**: unselected `direct ∪ child` pairs fail the audit, sorted and repo-relative. Unselected `import` pairs are reported as a count in the verdict's notes. The audit also fails on a collection or internal pytest error, on no records, or on a collected test file without a heartbeat.
- **Resolver evaluation**: a new `--per-path` mode (only with `--changed` and `--json`) emits one schema-2 payload per path, each pinned byte-equal to the single-path CLI output, with the graph built once. A path with no parseable payload counts as selecting nothing (fail closed).
- **Closures** for unselected pairs are declared reads in `tests/declared-deps.toml`, bounded by FC-04; past the bound, the change escalates.

## Considered Options

### Option 1: every open-level read, credited to the running test

- **Pro**: the literal reading of REQ-04.
- **Con**: it reproduces the measured jitter (16 of 277 files). The verdict would flip on scheduling whenever a first-import pair is unselected, which breaks REQ-05.

### Option 2: credit module loads through the observed import graph

- **Pro**: deterministic, and it keeps every module dependency in the verdict.
- **Con**: it over-approximates. A test's closure through `conftest.py` imports would demand selections the resolver rightly omits, and closing those would widen selection and push FC-04 for no real dependency.

### Option 3: the channel model (chosen)

- **Pro**: stable by construction. The five known gap tests (two repo-walking scanners, three path-loading exporter tests) stay in the verdict, because their reads are `direct`. First-importer credit is exactly the class the resolver's static import-edge source covers.
- **Con**: an in-process lazy import that the static source misses is only a note, not a failure.

### Rejected evaluation strategies

- One CLI call per read file: about 2 s each, more than half an hour per audit.
- In-process import of the resolver module: it bypasses the CLI that BA-01 names, and a replaced resolver script would crash rather than answer.

## Consequences

**Positive**:

- The audit observes; it never relies on someone listing a case.
- Two runs over one commit agree by construction for the measured jitter class.
- One resolver process per audit.

**Negative**:

- The resolver gains a mode, and its equivalence pin must hold forever.
- Blind spots: children started with `-I`/`-E` or a scrubbed `PYTHONPATH`, reads made in scratch copies outside the root, and module-level data caches credited to a first reader. The two-run comparison at the first full audit checks the last one.
- The first full audit may surface a large closure set, which FC-04 bounds.

## Disconfirmation

- **Falsifier**: a real selection miss (a test that fails when file F changes and was not selected for F) whose read was recorded only on the `import` channel, found by `audit_tests.py`'s weekly failure-based audit after merge.
- **Steelmanned runner-up**: option 2. A test truly depends on everything its import closure can reach. Over-approximation errs toward running more tests, the same safe direction as the resolver's widen-never-narrow property, and FC-04 would reveal its cost honestly instead of the audit quietly not judging a class.
- **Reversal trigger**: the falsifier firing once, or the `import`-channel note count exceeding the `direct ∪ child` unselected count at the first full audit. Either moves import pairs into the verdict under option 2's graph credit, scoped to modules the static source cannot see.
