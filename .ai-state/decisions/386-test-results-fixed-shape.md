---
id: dec-386
draft_id: dec-draft-b8543553
title: TEST_RESULTS.md has a fixed green-step shape, bounded by a byte ceiling the verifier checks; failures-only is the test-invocation default
status: accepted
category: behavioral
date: 2026-09-17
summary: "Roadmap item P3.4 as re-scoped on measurement: pasted test output is ~1.5% of what implementers read back (33,645 B over 60 already-quiet pytest runs against 2.2 MB of other Bash output in one session), so the cost is the prose written around each run, not the runs. The TEST_RESULTS.md schema becomes a fixed shape — command, one Result: pass/fail/skip line, duration, optional topology lines — with no notes field; a green section carries nothing further and is bounded at 1,024 bytes by scripts/check_test_results_shape.py, which the verifier runs at Phase 10 (WARN during rollout); red sections add a log pointer and failure blocks and are never size-checked. The invocation -q --tb=short -rf with a log redirect is the documented default on the implementer, the test-engineer and the Python testing leaf."
tags: [process-economy, roadmap-p3-4, test-results, verifier, evidence-standard, quality-guard]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - skills/software-planning/references/agent-pipeline-details.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - skills/testing-strategy/references/python-testing.md
  - scripts/check_test_results_shape.py
  - scripts/test_check_test_results_shape.py
  - .ai-state/TEST_TOPOLOGY.md
affected_reqs: []
---

## Context

The process-economy roadmap's P3.4 ("silence on success") assumed test output inflated
`TEST_RESULTS.md` and that printing full output only on red would recover the bytes. The
premise did not reproduce. Measured on 2026-09-14 from the harvest on disk and the session WAL:
fenced (pasted) output is 4% of P2.10's 16 result files (43,840 B) and 15% of Phase B's 15
fragments (74,852 B); pytest output pulled into subagent context over one session was 33,645 B
across 60 runs — every one already `-q` — against 2,249,155 B over 1,062 other Bash calls.
Across 237 sections in 40 `TEST_RESULTS*.md` files the green-section byte distribution was
p50 910 / p75 1,433 / p90 2,528 / max 33,432, and the largest sections carried a few hundred
bytes of fenced output each. The bytes are prose the schema invited: its "free-form notes"
field was a slot every agent filled.

dec-378 requires a measured cost and an executable guard for any simplification of a
process artifact.

## Decision

1. **Fixed green-step shape.** A `## Step N` section of `TEST_RESULTS.md` contains the
   command, one `Result: pass=<n> fail=<n> skip=<n>` line, the duration, and the optional
   topology lines (`Tier`/`Groups`/`Parallelism`/`Per-group results`). A green section
   (`fail=0`, no `error=`>0) carries nothing further: no notes field, no coverage summary
   (coverage lives in `coverage.xml`). A red section adds `Log: .ai-work/<task-slug>/logs/step-<N>.log`
   and one `### Failures` block per failing test. Verification prose belongs in the agent's
   return message or `LEARNINGS.md`.
2. **Executable guard.** `scripts/check_test_results_shape.py` (stdlib only, exit 0/1/2,
   `--json`, `--ceiling` default **1,024 bytes**) flags `green-over-ceiling` and
   `missing-result-line`; it never flags a red section for size. The verifier runs it at
   Phase 10 where it reads `TEST_RESULTS.md`; findings are `WARN` during rollout, like the
   missing-file case. The canary in `scripts/test_check_test_results_shape.py` plants an
   over-ceiling green section and is registered in the `repo-gates` topology group.
3. **Failures-only default invocation.** `<runner> pytest <scope> -q --tb=short -rf > .ai-work/<task-slug>/logs/step-<N>.log 2>&1; tail -n 30 <log>`
   is the documented default on the implementer (step 6), the test-engineer (Phase 4 steps 4
   and 6) and the Python testing leaf, byte-identical on the flag string. The agent's context
   receives the summary; the log holds the full output; the path is cited only on red.

The ceiling is ~2× the fixed shape (~450 B) and would have flagged about half of today's
green sections — that is the intent. No sentinel check is added: the file is ephemeral
`.ai-work/` content the sentinel does not read, and a P-dimension check would be a
registration-triangle change out of proportion to a Lightweight item.

## Considered Options

### Print full pytest output only on red (the roadmap's original framing)

- Pro: zero schema change.
- Con: refuted by measurement — the runs were already quiet; the bytes were never in the output.

### Ceiling at 2,048 bytes

- Pro: flags only the top ~15% of today's green sections; fewer rollout WARNs.
- Con: lets most narrative through; the shape has no notes field, so the looser bound
  guards nothing the shape does not already forbid.

### Add a sentinel P-dimension check reading TEST_RESULTS.md

- Pro: one more reader of the same number.
- Con: new check id + family registration (correction 23), over an ephemeral artifact the
  sentinel does not otherwise consume; deferred until P3.1's fragments show the after-measurement.

### Fixed shape + 1,024-byte ceiling + verifier caller (chosen)

- Pro: removes the slot rather than asking agents to fill it less; the guard is executable and
  canary-tested; the verifier caller satisfies gate-liveness GL04.
- Con: legacy `TEST_RESULTS.md` files (no `Result:` line) report `missing-result-line` on
  every section — expected, and only the current task's file is ever checked.

## Consequences

- Positive: the "after" measurement is mechanical — P3.1's fragments run through the same
  script; the calibration row for P3.4 records the before distribution above.
- Positive: three invocation surfaces cannot drift on the flag string without a grep noticing.
- Negative: the reconciler's merge semantics (concatenate by step, no dedup) are unchanged, so an
  agent that re-runs a step still appends a second section; the ceiling applies per section.
- Negative: the WARN-not-FAIL rollout posture means an over-ceiling section does not block a
  verdict; revisit once three pipelines have produced files in the new shape.
