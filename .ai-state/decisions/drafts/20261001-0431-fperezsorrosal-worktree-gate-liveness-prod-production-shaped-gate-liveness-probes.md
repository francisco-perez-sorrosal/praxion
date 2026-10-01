---
id: dec-draft-54f10c9f
title: Production-shaped gate-liveness probes run behind one CLI in a read-only job of the scheduled test workflow
status: proposed
category: architectural
date: 2026-10-01
summary: "New CLI scripts/check_gates_bite.py over a new scripts/gate_probes/ package runs four probes (mutation sensor, observation-log hooks, spawn counter, selection audit), each reaching its gate through the production entry point and input shape; it reports one verdict per gate (JSON schema 1 owned by gate_probes/verdict.py) and exits 1 if any fails. New test-scheduled.yml jobs gate-liveness (20-minute step limit, contents: read, no secret) and gate-liveness-canaries (the liveness-marked e2e scenarios); a new liveness pytest marker is deselected by default and absent from the -m large job"
tags: [gate-liveness, canary, scheduled-ci, mutation-sensor, observation-log, spawn-count, test-selection]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-liveness-prod
pipeline_tier: standard
affected_files:
  - scripts/check_gates_bite.py
  - scripts/gate_probes/verdict.py
  - scripts/gate_probes/mutation.py
  - scripts/gate_probes/hook_replay.py
  - scripts/gate_probes/observation.py
  - scripts/gate_probes/selection.py
  - scripts/gate_probes/fixture/liveness_target.py
  - scripts/gate_probes/fixture/liveness_checks.py
  - .github/workflows/test-scheduled.yml
  - pyproject.toml
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-06, REQ-07, REQ-08, REQ-09]
---

## Context

Between 2026-09-27 and 2026-10-01 four gates went dead while their tests stayed green: the mutation sensor, the observation-log hooks, `spawn_count.py` and the test-scope resolver. The tests fed inputs unlike production's: a fixture outside the repository tree, hook payloads from the checkout root, hand-built log rows. `test.yml` and `test-scheduled.yml` already ran those tests every push and every week, so the gates were never unrun. They were unrepresentatively *fed*. The existing `scripts/check_gate_liveness.py` asks whether a gate is wired (static GL checks). Nothing asked whether a gate still bites.

The acceptance tests (BA-01) fix the boundary: one command, run from a repository root with no secret and no assistant session, that runs all four checks or a named subset, reaches each gate in that repository, exits non-zero on any failure and reports a verdict with a reason per check. The Key Signals name `test-scheduled.yml` or `audits.yml` as the host.

**Activation:** no. The design-synthesis lens sweep was not run. The uncertainty here is in measurable quantities (hosted runtime, default-suite cost), which the plan measures early instead of deliberating over.

## Decision

- **A new CLI `scripts/check_gates_bite.py`** over a new package `scripts/gate_probes/` (`verdict`, `mutation`, `hook_replay`, `observation`, `selection`, plus `fixture/` and `tracer/`). The CLI owns argument parsing, repo-root resolution from git or `--repo-root` (never `__file__`), the scrubbed environment, fixed run order, per-probe containment (an exception or timeout is a failed verdict) and rendering. `gate_probes/verdict.py` is the sole owner of the verdict format (JSON schema 1).
- **Each probe is production-shaped.**
  - The mutation probe copies a tracked fixture into the gitignored `tmp/` *inside* the repository tree, so the sensor's inner pytest inherits the root config, and invokes the sensor CLI exactly as a pipeline writer does.
  - The hook probes replay events through the commands `hooks/hooks.json` registers, from a subdirectory working directory of a scratch project.
  - The counter probe counts rows the hooks wrote, never hand-written rows.
- **Host: `test-scheduled.yml`**, as two jobs:
  - `gate-liveness`: the CLI, with a step `timeout-minutes: 20`, `permissions: contents: read`, and no secret or token.
  - `gate-liveness-canaries`: `pytest -m liveness tests/e2e`, with job `timeout-minutes: 45`.
- **A `liveness` marker**, registered in `pyproject.toml` and deselected by addopts (`-m 'not large and not liveness'`), so the whole-suite audit scenarios run only in the canary job, never in the default run or the `-m large` job (SQ-01).

## Considered Options

### Option 1: new jobs in `test-scheduled.yml` (chosen)

- **Pro**: already read-only, with invariants pinned by `tests/test_test_scheduled_workflow_invariants.py`; the same Python 3.11 frozen environment as `test-root`; already the scheduled loop of the testing doctrine.
- **Con**: a red job makes the workflow run non-success, which moves `health-root`'s "last green" diff base for `audit_tests.py`.

### Option 2: a step or job in `audits.yml`

- **Pro**: thematically "gate liveness"; already runs `check_gate_liveness.py`.
- **Con**: its only job holds `contents: write` for the metrics commit-back. A step there would run mutmut and hook scripts in a write-scoped job (REQ-08 forbids it). A new job there would have no invariant test, and the environment is 3.13 and unfrozen.

### Option 3: extend `scripts/check_gate_liveness.py`

- **Pro**: one "liveness" tool.
- **Con**: it is stdlib static analysis (708 lines), run by the sentinel and in a write-scoped job. Mixing dynamic, minutes-long probes into it couples two reasons to change and grows a near-limit file.

## Consequences

**Positive**:

- A dead gate surfaces within a week, through the input shape that killed it.
- Dead-gate scenarios and unit canaries prove each probe bites.
- No new secret or write grant, and no new dependency.

**Negative**:

- A new six-module package plus its tests.
- A hosted runtime cost: the probes take minutes. The canary job runs about four traced suites each week, a footprint the spec's table does not bound and which is flagged to the orchestrator.
- A red liveness job widens `health-root`'s next audit window. That direction is conservative and accepted.
- The replay cannot prove harness payload drift or plugin-cache parity (out of scope; needs a live session).

## Disconfirmation

- **Falsifier**: within the first eight scheduled runs, a gate dies in a way the probe's input shape does not reach, while the probe stays green. Examples: a hook regression reached only through a payload field the replay does not send, or a sensor failure under a `src/` layout. That would show "production-shaped" was too narrow a fixture.
- **Steelmanned runner-up**: a separate workflow file `gate-liveness.yml` isolates the job completely. It keeps no coupling to the last-green lookup and carries its own invariant test, without touching a workflow whose purpose is suite health. It loses only because the Key Signals and the acceptance tests name the two existing workflows.
- **Reversal trigger**: if the last-green coupling produces a stale audit base for more than two consecutive weeks, or the canary job's runtime exceeds its 45-minute limit twice, move both jobs into a dedicated workflow file.
