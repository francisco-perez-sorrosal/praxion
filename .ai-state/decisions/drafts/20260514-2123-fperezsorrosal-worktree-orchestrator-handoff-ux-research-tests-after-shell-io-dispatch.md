---
id: dec-draft-82645f34
title: "Tests-after approach for I/O-heavy shell dispatch script; TDD pairing reserved for pure-logic steps"
status: proposed
category: implementation
date: 2026-05-14
summary: "For scripts/dispatch-reworks (bash + external process I/O), use tests-after with --dry-run as the unit-test affordance; apply test-engineer pairing only to the two pure-logic steps (manifest parsing, arg shaping)."
tags: [testing, tdd, bash, dispatch, rework-loop]
made_by: agent
agent_type: implementation-planner
branch: worktree-orchestrator-handoff-ux-research
pipeline_tier: standard
affected_files:
  - scripts/dispatch-reworks
  - hooks/notify_bg_session_state.py
  - tests/test_dispatch_reworks_manifest.py
  - tests/test_dispatch_reworks_bg.py
  - tests/test_notify_bg_session_state.py
---

## Context

The hybrid rework dispatch plan (dec-draft-88106752) decomposes into a bash script
(`scripts/dispatch-reworks`) that fans out `claude --bg` or `claude-cli://` calls per
rework row, and a Python hook (`hooks/notify_bg_session_state.py`) that fires macOS
notifications on session state changes.

The implementation-planner must decide whether to apply strict TDD (test-engineer paired
concurrently on every step) or tests-after (tests written after implementation stabilizes)
to each step. The general planning methodology defaults to paired TDD for behavioral
acceptance criteria, but permits tests-after when "the test scaffolding cost exceeds the
per-step benefit."

The dispatch script:
- Calls `claude --bg` (a real external process, non-mockable without PTY harness)
- Calls `open "claude-cli://..."` (macOS LaunchServices, non-mockable in unit tests)
- Calls `lsregister` (system binary, requires macOS)

The dry-run flag (`--dry-run`) was explicitly designed in the architecture (SYSTEMS_PLAN.md
§ Architecture, Component 1) as the test affordance — it exercises the full parse/discover/plan
path with no side effects.

## Decision

Apply **tests-after** for the full dispatch script except for two inner concerns where a
test-engineer can write meaningful pytest tests before the implementation stabilizes:

1. **Step 3 (manifest parsing + dry-run output)**: paired — `parse_json_blocks()` is pure
   Python called via `python3 -c`; the dry-run output format is determinate from the spec.
   A test-engineer can write `test_dispatch_reworks_manifest.py` against fixture manifests
   before the `--bg`/`--terminals` loops exist.

2. **Step 4 (`--bg` dispatch loop)**: paired — argument-shaping (the `--name` flag value,
   the permission-mode flag, the session ID extraction pattern) is testable via `--dry-run`
   without spawning real `claude` processes.

Steps 5 (`--terminals`), 7 (hook registration), 8 (slash command), 9 (verifier edit) are
configuration or LaunchServices-dependent — no unit-test surface; manual verification only.

The hook (Step 6) gets a lightweight paired test (Step 6a) for the name-prefix filter,
which is pure Python logic callable via subprocess with mocked stdin/stdout.

## Considered Options

### A. Strict TDD on all steps

Pair every implementation step with a concurrent test-engineer.

**Pros**: maximum behavioral coverage before implementation lands; tests shape the interface.

**Cons**: for `--bg` and `--terminals` dispatch loops, the "interface" is the external
`claude` CLI and `open` LaunchServices call — neither is meaningfully mockable at the unit
level. A test-engineer writing a test for "does it call `claude --bg`?" would end up
verifying `subprocess.Popen` calls that are untestable in a sandboxed CI environment.
The scaffolding cost exceeds the per-step benefit.

### B. Tests-after on all steps

No paired test-engineers; tests written after all steps complete.

**Pros**: zero coordination overhead; fastest path to done.

**Cons**: loses the shaping property of TDD for the two steps where it does add value
(manifest parsing and arg-shaping are determinate enough to write tests first).

### C. Tests-after for I/O-heavy steps; TDD pairing for pure-logic steps *(chosen)*

**Pros**: balances the cost-benefit. The two deterministic inner concerns (parsing, arg
shaping) benefit from test-first; the external-process steps do not. The hook filter is
pure Python and similarly benefits from a test-first approach.

**Cons**: slightly more coordination than option B. Acceptable given the test value.

## Consequences

### Positive
- Steps 3, 4, and 6 have test coverage before the implementation is "done" — catching
  edge cases (empty manifest, missing worktree, wrong `--name` format) early.
- `--dry-run` serves as a system-level acceptance test for all modes without requiring
  a real `claude` binary in the test environment.
- The decision is explicit and documented — future implementers know why TDD was selective
  here rather than assuming it was forgotten.

### Negative
- Steps 5 and 7–9 have no automated test coverage in this plan. They are verified manually
  at Step 10 and by the verifier's AC checklist. If a regression is introduced later, there
  is no automated safety net for those steps.
- The decision is specific to this script's I/O profile. It should not be generalized to
  "bash scripts don't need TDD" — scripts with pure logic (e.g., `scripts/ccwt`'s worktree
  discovery) could benefit from test-first.
