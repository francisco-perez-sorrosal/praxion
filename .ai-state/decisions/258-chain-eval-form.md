---
id: dec-258
title: Criteria→spec chain gate-liveness eval lives in the always-green pytest suite, not the out-of-band eval framework
status: accepted
category: architectural
date: 2026-06-29
summary: The R10 end-to-end criteria→spec chain liveness proof is a pytest integration test in tests/ (always-green suite), not a /eval-praxion check or an eval/ replay-harness, because a gate-liveness proof must run free/deterministic/auth-less on every suite run.
tags: [eval, gate-liveness, spec-chain, traceability, always-green-suite, out-of-band-eval, testing]
made_by: agent
agent_type: systems-architect
branch: wave5-r10-criteria-spec-eval
pipeline_tier: standard
affected_files:
  - tests/test_criteria_spec_eval.py
re_affirms: dec-040
dissent: A reviewer could argue the chain is a *quality* property (does the pipeline produce faithful artifacts?) that belongs with the LLM-as-judge eval cohort; folding it into the binary pytest suite tests only the mechanical plumbing, not the semantic faithfulness the eval framework exists to grade.
---

## Context

Finding G1 / R10 (Wave-5 capstone) flags that Praxion's conditional pipeline tail —
the criteria→spec chain `TASK_BRIEF → SYSTEMS_PLAN (REQ IDs) → traceability.yml → SPEC archival` —
has **never been executed end-to-end on this repo**. The four chain-linking validators
(`spec_drift.detect_drift`, `check_spec_archival_gap.detect_gap`, `check_p06_task_brief.run_p06`,
`regenerate_specs_index` + matrix-presence) each have unit tests in isolation, but no test drives a
freshly-built synthetic chain through all four links and proves the REQ IDs actually flow across all
four artifacts.

Per the gate-liveness rule (`rules/swe/gate-liveness.md`), a gate is a *claim* it catches its defect
class, and must be **proven to bite** — to fail on a known-bad input, not merely pass on the current
good state. The chain validators are CODE gates; their liveness proof must be a canary. The open
architectural question this ADR settles is **where that liveness proof lives** — which determines
whether it runs as live, unconditional evidence or as an opt-in artifact that can silently go inert.

The decision is `category: architectural` because it places a quality gate on one side of the
**always-green-suite vs. out-of-band-eval boundary** — a load-bearing structural line in Praxion's
design record (dec-040, dec-204, dec-257).

## Decision

The R10 chain liveness proof is **(a) a pytest integration test** at `tests/test_criteria_spec_eval.py`,
running in the canonical always-green suite (`python3 -m pytest tests/ -q`). It builds a faithful
synthetic chain in `tmp_path`, drives all four real validators to a clean verdict (faithful PASS),
and ships **four per-link broken-chain canaries** (one per chain link) that each drive the
corresponding validator to a non-clean verdict (BITE). It imports and calls the existing production
callables rather than re-implementing any detection logic.

Forms (b) and (c) are **eliminated**.

## Considered Options

### (a) pytest integration test in `tests/` — CHOSEN

- **Pros:** runs on every `pytest tests/` invocation → deterministic, free, no auth, no LLM, no
  network → it is *live evidence the chain runs*, exactly what a gate-liveness proof requires. Imports
  the real validators (KS3). Builds artifacts in `tmp_path` so nothing is committed under the
  gitignored `.ai-work/` (KS5). Mirrors the precedent of `test_spec_drift.py` and the dec-252
  production-gate canaries.
- **Cons:** the pytest suite is binary pass/fail — it proves the mechanical plumbing links up, not the
  *semantic* faithfulness of pipeline-produced artifacts (that is the eval framework's job). This is
  the documented `dissent` above; it is acceptable because R10's charge is the plumbing-liveness proof,
  not artifact-quality grading.

### (b) a new `/eval-praxion` check — ELIMINATED

- **Pros:** co-located with the artifact-faithfulness judges; richer (could grade semantic quality).
- **Cons:** `/eval-praxion` is **out-of-band by design** (dec-040, re-affirmed by dec-204 clauses 1/2/4
  and dec-257): it runs only via user-invoked command or opt-in CI, never from a hook or pipeline, and
  the LLM-as-judge path even **refuses to run inside a nested Claude Code session** (dec-206). A
  liveness gate that fires only when a human opts in is not live evidence — it is precisely the inert
  gate the gate-liveness rule warns against.

### (c) an `eval/` replay-harness family check — ELIMINATED

- **Pros:** the eval package already has chain-fidelity machinery (`family1_pipeline_fidelity`).
- **Cons:** `eval/` is a **separate installed package** (`praxion-evals`, Python 3.13+, depends on
  `anthropic` + `claude-agent-sdk`), not on the root pythonpath, requiring auth and an LLM. Same
  out-of-band boundary as (b), plus a heavier dependency surface. Importing `family1`'s
  `_check_spec_traceability` from `tests/` would pollute the always-green boundary; the matrix-presence
  check it performs is a one-liner (`"## Traceability" in content`) cheaply inlined instead.

## Consequences

**Positive:**

- The chain gate is **always live** — every contributor running `pytest tests/` re-proves the chain
  links up and that each link bites when broken. The G1 "never run end-to-end" gap closes mechanically.
- Zero new always-loaded tokens, zero auth, zero LLM, fully deterministic (override hooks + injected
  `now`) — satisfies HG1/HG2 and the determinism testing convention.
- Reinforces the dec-040/204/257 boundary by demonstrating the correct side for a deterministic
  liveness proof, keeping the eval framework reserved for genuinely LLM-graded quality.

**Negative / accepted:**

- The test proves mechanical link-up, not semantic artifact quality (the `dissent`). A future need to
  grade *faithfulness* of agent-produced chain artifacts would still route to the eval framework — this
  ADR does not foreclose that; it scopes R10 to the liveness proof.
- The four per-link canaries add test code (~one bite test per link) over a single representative
  break — accepted because per-link coverage is what makes the gate trustworthy (a single shared break
  could leave a link silently unproven).

## Disconfirmation

- **Falsifier:** evidence that the always-green suite cannot deterministically drive one of the four
  validators without auth/LLM/network/git-subprocess (forcing an out-of-band dependency) would refute
  the choice. (Checked false: `detect_drift` has hermetic `_changed_files_override`/`_deleted_files_override`
  hooks; `detect_gap` takes an injected `now`; `run_p06`/`regenerate_specs_index` read only `tmp_path`.)
- **Steelmanned runner-up:** (b) `/eval-praxion`. Its strongest case: the criteria→spec chain is
  fundamentally a *quality* contract — "did the pipeline produce faithful, cross-linked artifacts?" —
  and quality contracts are the eval framework's reason to exist; a binary pytest test can rot into a
  green-only plumbing check that passes while the artifacts it inspects are semantically hollow. If
  R10's true intent were artifact-faithfulness grading rather than chain-liveness, (b) would win.
- **Reversal trigger:** if a future requirement asks the chain proof to grade the *semantic* quality of
  agent-generated artifacts (not just mechanical link-up), or if the pytest test proves unable to stay
  deterministic without reaching for the eval package's machinery, revisit and split a quality-grading
  companion into `/eval-praxion` — superseding this ADR's scope (not its always-green placement of the
  liveness half).

## Prior Decision

Re-affirms **dec-040** ("Eval framework is out-of-band only — /eval command + CI, never hook-driven").
A reopening was considered — placing the chain liveness proof in the eval cohort alongside the
LLM-as-judge checks — and rejected: dec-040's out-of-band contract (re-affirmed by dec-204 clauses
1/2/4 and dec-257, and hardened by dec-206's nested-session refusal) means an eval-housed gate is not
live evidence. The evidence a future supersession would require: a deterministic, auth-less,
LLM-free execution path for the eval framework that runs unconditionally on every suite invocation —
which would collapse the always-green / out-of-band distinction this ADR depends on.
