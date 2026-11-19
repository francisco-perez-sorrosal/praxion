---
id: dec-draft-74fc06dd
title: The gate-liveness checks run in a workflow of their own, one job per kind of check, each limit sized from a measured reading
status: proposed
category: architectural
date: 2026-11-18
summary: "The liveness checks move from test-scheduled.yml to a new .github/workflows/gate-liveness.yml (name Gate liveness) with five independent jobs: the three fast probes, the selection audit, the quick scenarios (tests/acceptance) and the whole-suite scenarios (tests/e2e) split in two. The audit holds its traced suite to a bound of its own, [tool.praxion.gate-liveness] selection-audit-timeout-seconds in pyproject.toml, no longer the step loop's gate-timeout-seconds. Each job limit carries a machine-checked '# sized:' line (1.5 x the scaled reading, rounded up, never under 10 min, at most 240 min; above that the job splits). A plugin records each scenario's duration and free disk space. The workflow is not on the autofix watch list."
tags: [gate-liveness, scheduled-ci, selection-audit, time-limits, canary, workflow]
made_by: agent
agent_type: systems-architect
branch: worktree-liveness-eval-rows
pipeline_tier: standard
affected_files:
  - .github/workflows/gate-liveness.yml
  - .github/workflows/test-scheduled.yml
  - tests/test_gate_liveness_workflow_invariants.py
  - tests/test_test_scheduled_workflow_invariants.py
  - scripts/gate_probes/suite_bound.py
  - scripts/gate_probes/selection.py
  - scripts/check_gates_bite.py
  - scripts/liveness_scenario_record.py
  - pyproject.toml
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-11, REQ-12]
supersedes_in_part: [dec-419]
---

## Context

dec-419 hosted the gate-liveness CLI and the liveness-marked scenarios as two jobs of `test-scheduled.yml`. Its reversal trigger read: "if the last-green coupling produces a stale audit base for more than two consecutive weeks, or the canary job's runtime exceeds its 45-minute limit twice, move both jobs into a dedicated workflow file". Both halves fired:

- the canaries job was cancelled at 45.7, 45.3 and 45.3 minutes on 2026-11-02, -09 and -16;
- `Test (scheduled)` has concluded failure in all seven runs since 2026-10-05, so `audit_tests.py` has had no green run to diff against.

The `gate-liveness` job also ended at its 20-minute step limit with no verdict. The selection audit's traced suite, held to the step loop's `gate-timeout-seconds` (1,500 s since td-488), no longer finishes inside it: the untraced root suite alone took 34.5 minutes on the runner on 2026-11-16. That cost the three fast probes, about 7 s together, their weekly verdicts.

**Activation:** fired. The lens sweep was not run as a separate fan-out. The uncertainty here is in measurable quantities (runner times, disk), which the plan measures in a step of its own rather than deliberating over.

## Decision

- **Host.** A new workflow file, `.github/workflows/gate-liveness.yml`, named `Gate liveness`. It is triggered weekly by cron and by `workflow_dispatch`. The workflow and every job hold exactly `contents: read`, reach no secret and start no assistant session.
- **Five jobs, none waiting for another** (one per kind of check; the whole-suite scenarios are split in two by the 240-minute rule below):
  - `fast-probes`: `--gate mutation-sensor --gate observation-hooks --gate spawn-count`;
  - `selection-audit`: `--gate selection-audit`, with no `continue-on-error`;
  - `scenarios-quick`: `pytest -m liveness tests/acceptance`;
  - `scenarios-whole-suite` and `scenarios-whole-suite-audit-gated`: `pytest -m liveness tests/e2e`, split by node id, each deselecting the other's nodes. The two scenarios that need the audit to pass run apart from the rest, so while td-500 keeps them red no other scenario's result is hidden behind theirs. Each starts by removing the runner's unused toolchains, since each scenario clones the checkout and the measured peak disk use (about 28 GiB locally) is past the runner's free space.

  `test-scheduled.yml` keeps exactly its four health jobs, so a week its health jobs pass is a green run again.
- **The audit's own bound.** It is declared once, as `[tool.praxion.gate-liveness] selection-audit-timeout-seconds` in `pyproject.toml`. Three readers take it from there: `scripts/gate_probes/suite_bound.py`, the selection probe (which no longer reads `_step_loop_pocket_runs`), the CLI's limit for the probe (360 s plus the bound), and the whole-suite scenarios' driver. An undeclared bound fails the audit, naming the key; there is no fallback to the step loop's bound. `gate-timeout-seconds` stays 1500.
- **Limits.** One `# sized:` line beside each job-level `timeout-minutes`:
  `measured=`, `commit=`, `where=local|runner`, `step=`, `scale=`, `setup=`, `fixed=`, `margin=1.5`, `limit=` (and `bound=` for the audit job).
  - The limit is `max(10, ceil((1.5 × (step × scale + setup) + fixed) / 60))` minutes, at most 240; the 10-minute floor covers the runner's own setup variance.
  - Sized from readings of 2026-11-19 on `ea85b08d52ea`, scaled 1.53 to the runner: `fast-probes` 10 (the floor), `selection-audit` 69 with a bound of 3540 s, `scenarios-quick` 47, the whole-suite jobs 201 and 135 (the audit-gated one).
  - A job that would exceed 240 minutes is split by node id.
  - A scenarios step's own limit is two minutes under its job's.
  - For the audit job, `limit × 60 ≥ bound + 360 + setup`.
  - The new invariant test checks all of it.
- **Records.** `scripts/liveness_scenario_record.py`, loaded by `-p`, appends a start line and an end line per scenario (with free disk space) to a file. A report step with `if: always()` prints every scenario's duration, a cut one included, and the free space before, lowest and after. The audit's verdict notes the traced suite's own duration.
- **No autofix.** `ci-autofix.yml` still watches exactly `Test`, `Architecture` and `Test (scheduled)`, so a red audit, red by design until td-500 is answered, starts no assistant session.
- **Reversal trigger for limits.** Any job that uses more than 80 percent of its limit in a weekly run is re-sized from that run's own durations (`where=runner scale=1`).

## Considered Options

### Option 1: a dedicated workflow, one job per kind of check (chosen)

- **Pro:** a slow audit can never again cost the fast probes or the quick canaries their verdicts. The health workflow's green no longer depends on liveness. Each job is sized from its own reading.
- **Con:** five runner setups, and a fourth workflow invariant to keep.

### Option 2: keep both jobs in `test-scheduled.yml` with larger limits

- **Pro:** no new file.
- **Con:** the diff-base coupling stays, and with it a red health run whenever the audit is red (every week until td-500). A slow audit still holds back the fast probes' verdicts.

### Option 3: a dedicated workflow with dec-419's two jobs

- **Pro:** smaller file.
- **Con:** repeats the failure inside each job: the audit beside the fast probes, the whole-suite scenarios beside the quick ones.

## Consequences

**Positive:**

- The three fast probes and the quick scenarios report every week.
- The audit reaches its own verdict instead of a time limit.
- The health workflow's diff base advances.
- Every limit can be checked against its evidence.

**Negative:**

- The audit job and two whole-suite scenarios are red every week until td-500 is answered. This is reported, not hidden.
- Limits must be re-sized as the suite grows. The 80-percent trigger makes that a weekly-visible, one-line change.
- The fast-probe job's scaled reading is under a minute, so its limit is the 10-minute floor, generous for a job that runs in seconds.
- Placing a new whole-suite scenario takes a workflow edit: until it is placed in one job and the limits re-sized, it runs in both.
- A second `[tool.praxion.*]` table in the root project file.

## Disconfirmation

- **Falsifier:** within the first four weekly runs, one job's failure or time limit leaves another job without its own conclusion. Or the audit job ends at a time limit rather than at a verdict. Either would show the jobs are not independent, or the bound does not fit.
- **Steelmanned runner-up:** Option 2, with the audit made non-blocking (`continue-on-error`) inside `test-scheduled.yml`. It keeps one scheduled workflow, one invariant test and one place to look. The health run stays green while the audit is red. It loses for two reasons. A `continue-on-error` audit is a red verdict shown as green, which REQ-03 forbids. And a slow audit in the same run still delays everything behind it, inside one 6-hour budget shared with the root health job (already 37.8 of its 45 minutes).
- **Reversal trigger:** any job above 80 percent of its limit in a weekly run triggers a re-size from that run's durations. If the whole-suite scenarios need more than two jobs to stay under 240 minutes, revisit whether they belong in a weekly run at all, rather than splitting further.

## Prior Decision

This partially supersedes dec-419. **Narrowed:** dec-419's host clause (`test-scheduled.yml`, jobs `gate-liveness` and `gate-liveness-canaries`), its 20-minute step limit and its 45-minute canaries limit. **Also changed:** the selection audit's bound, which td-488's later fix tied to the step loop's `gate-timeout-seconds`. **Unchanged:**

- the CLI `scripts/check_gates_bite.py` and the `scripts/gate_probes/` package;
- production-shaped probes and per-probe containment;
- the verdict format (JSON schema 1, `gate_probes/verdict.py`);
- the `liveness` marker, deselected by default and absent from `-m large`;
- the read-only, secretless, no-session posture.
