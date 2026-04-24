---
id: dec-draft-ceae80ca
title: /project-metrics planning conventions — Full-tier escalation, test placement, committed fixture repo
status: proposed
category: implementation
date: 2026-04-23
summary: Implementation-planner decisions for /project-metrics decomposition — escalate from Standard to Full tier on step-count grounds, place tests at scripts/project_metrics/tests/ rather than tests/scripts/, commit fixture git repo for byte-deterministic collector tests rather than synthesize per-test
tags: [implementation, planning, testing, conventions, metrics, project-metrics]
made_by: agent
agent_type: implementation-planner
pipeline_tier: full
affected_files:
  - .ai-work/project-metrics/IMPLEMENTATION_PLAN.md
  - scripts/project_metrics/tests/
  - scripts/project_metrics/tests/fixtures/minimal_repo/
re_affirms: dec-draft-c566b978
---

## Context

The systems-architect recommended Standard tier for `/project-metrics` with an explicit flag: file count (~18–22) flirts with Full. The architect also deferred three choices to the implementation-planner via the "Open Questions for the Implementation Planner" section: parallel execution, fixture repo strategy, and `--dry-run` scoping. Independently, the SYSTEMS_PLAN referenced a test location (`tests/scripts/project_metrics/`) that does not match any convention present in the repository.

During decomposition the planner had to settle three implementation-approach questions that shape step ordering and supervision granularity:

1. **Process tier** — Standard vs Full. Affects parallel-group annotation, doc-engineer activation, supervision-checkpoint cadence, spec archival expectations.
2. **Test placement** — `tests/scripts/project_metrics/` (as SYSTEMS_PLAN suggested), `scripts/test_project_metrics_*.py` (sibling to script files, matching `scripts/test_finalize_adrs.py`), or `scripts/project_metrics/tests/` (embedded under the package, matching `task-chronograph-mcp/tests/`).
3. **Fixture strategy** — committed fixture git repo with fixed SHAs, or synthesized-per-test in `tmp_path`. The architect flagged this open question and deferred to the planner "per test style conventions already in use."

None of these are architectural in the sense of the four ADR drafts from Phase 4 (they do not change system boundaries, data model, technology, or security). They are approach-level and affect how the plan decomposes and executes. An ADR is warranted because (a) they survive the pipeline via `LEARNINGS.md` and the Decisions Made section; (b) future /project-metrics work (v2 language tiers) will inherit the test layout and fixture strategy; (c) the tier escalation is a reviewable decision that the verifier and sentinel will cross-reference against the delivered step count.

## Decision

**D1 — Escalate from Standard to Full tier.** The plan contains 18 steps exceeding the ~10-step Standard ceiling. Breadth-driven (6 collectors + 4 composition modules + CLI + command + docs + integration) rather than depth-driven. The Full-tier process gets activated: parallel execution across disjoint collector file sets, explicit doc-engineer step for the docs reference (honoring the architect's registered objection that the README must be a complete contract document), structured supervision checkpoints at four milestones, spec archival with 16 REQ IDs and a traceability matrix.

**D2 — Place tests under the package at `scripts/project_metrics/tests/`.** Mirror the `task-chronograph-mcp/tests/` convention. Each collector, composition module, CLI, and integration surface gets its own test file inside this directory. Fixtures live at `scripts/project_metrics/tests/fixtures/`. This keeps the package self-contained and avoids polluting either a nonexistent `tests/scripts/` root or a flat `scripts/test_project_metrics_*.py` layout that would crowd the `scripts/` directory with 14+ new files.

**D3 — Commit a minimal fixture git repository** at `scripts/project_metrics/tests/fixtures/minimal_repo/` with a known set of commits, authors, and file-change maps. Use nested `.git/` (if git allows it via `git init` + `git add`) or a tarball unpacked at test-setup time — final mechanism chosen during Step 5 implementation. A second fixture `minimal_stdlib_repo/` covers the stdlib-only path (AC2 / REQ-PM-02).

## Considered Options

### D1 — Tier choice

- **Option A: Standard tier, bundle steps.** Collapse the six collector steps into two or three grouped steps (e.g., "Tier 0 collectors", "Tier 1 Python collectors"). Brings step count under 10.
  - *Pros*: matches architect's recommendation.
  - *Cons*: destroys the architectural value proposition that collectors are independent and pluggable; hides per-collector test coverage boundaries; makes supervision opaque (what does "50% done with Tier 1 Python collectors" mean?).

- **Option B: Full tier, 18 steps with paired BDD/TDD. (chosen)**
  - *Pros*: each collector is a first-class step with its own REQ-linked test pair; parallel batches exploit file-disjoint independence; doc step gets a dedicated owner (doc-engineer) honoring the architect's objection on docs completeness.
  - *Cons*: more overhead; more supervision touchpoints; spec archival mandatory.

### D2 — Test placement

- **Option A: `tests/scripts/project_metrics/`.** As SYSTEMS_PLAN suggested.
  - *Cons*: no `tests/` directory exists at repo root. Would create a new top-level convention that nothing else follows. Rejected on discovery-cost grounds.

- **Option B: `scripts/test_project_metrics_<topic>.py` sibling files.** Matches `scripts/test_finalize_adrs.py` precedent.
  - *Cons*: with 6 collectors + 4 composition modules + CLI + integration, we'd produce 12+ test files at `scripts/` root, crowding a directory that currently holds 10 scripts total. The sibling pattern works for single-file scripts, not packages.

- **Option C: `scripts/project_metrics/tests/` embedded. (chosen)**
  - Matches `task-chronograph-mcp/tests/` convention; keeps test artifacts co-located with what they test; fixtures neighbor the tests that use them.

### D3 — Fixture strategy

- **Option A: `tmp_path` per-test synthesis.** Each test creates its fixture repo from a Python spec (list of commit operations), runs assertions, tears down.
  - *Pros*: no committed binary/git artifact; each test is fully self-contained.
  - *Cons*: synthesized commits have wall-clock timestamps (even with `--date` overrides, the commit-sha includes committer-date), which means SHAs drift across test runs. Byte-deterministic assertions on churn ordering / ownership percentages become flaky. Test startup is slow (must run `git init` + N `git commit` operations per test).

- **Option B: Committed fixture git repo. (chosen)**
  - *Pros*: SHAs stable across all runs; assertions can be byte-exact against golden values; test setup is a file copy.
  - *Cons*: a nested `.git/` directory inside the repo is unconventional. Mitigation: use a tarball shipped alongside the test file, or isolate the nested repo via `.gitignore` exceptions. The mechanism is chosen during Step 5 implementation, not now — the *decision* is that fixtures are pre-materialized rather than synthesized.

## Consequences

**Positive:**

- Step decomposition is honest to the architectural shape (collectors as first-class plugins) and reviewable at implementer-step granularity.
- Test placement follows an in-repo precedent (`task-chronograph-mcp/tests/`), reducing onboarding friction for future contributors.
- Committed fixture enables byte-deterministic collector tests, which is the biggest reliability risk the architect called out (SYSTEMS_PLAN §Test Lens: "Determinism — the biggest test-reliability risk").
- Full-tier process gets the doc-engineer involved on Step 17, which directly honors the architect's registered objection that `docs/metrics/README.md` must be a complete contract, not a stub.

**Negative:**

- Full tier demands more supervision cycles. Mitigated by scheduling only four explicit checkpoints (after Steps 4, 10c, 15, 18) rather than per-step.
- A committed nested `.git/` fixture is an unusual artifact in this repo. Mitigated by bundling it as a tarball if the nested-dir approach causes friction (e.g., `git` tooling treating it as a submodule).
- The SYSTEMS_PLAN reference to `tests/scripts/` is now stale; the architect document's Components row for `/project-metrics` and the SYSTEMS_PLAN §Script Layout Decision paragraph both name `tests/scripts/project_metrics/` — the implementer should treat those as advisory and use the decision here.

## Prior Decision

This ADR `re_affirms: dec-draft-c566b978` (Collector Protocol). No supersession is implied; the protocol decision stands. The re-affirmation is structural: the Full-tier decomposition depends on collectors being first-class independent units (per dec-draft-c566b978), and bundling them to meet a Standard-tier step budget would have silently undermined the protocol's extension-seam value. Recording this cross-reference so a future reader understands why a planning-level tier choice is coupled to an architectural protocol choice.

No new evidence would be required to supersede either decision — the coupling is logical, not empirical.
