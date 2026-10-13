---
id: dec-458
draft_id: dec-draft-33a753e3
title: Process-adherence eval as a third opt-in console entry and package over the live runner's boundary layer
status: accepted
category: architectural
date: 2026-10-11
summary: Adds the praxion_evals.adherence package and its own opt-in console entry, praxion-evals-adherence, which measures per-role process adherence in paired full/lean arms (lean = runner-owned copy with omitClaudeMd on the measured role), spawning each role through a harness-fixed thin main session, grading C1-C6 plus the alignment map's role checks (each naming its rule file and section) into a closed outcome sum type, and computing per-role paired verdicts; it reuses live/session, materialize, spend and the error kinds, extends live/session.parse_stream additively, and narrows dec-040 clause 3 exactly as dec-392 did (isolated, operator-invoked sessions only).
tags: [eval, adherence, lean-spawns, omitClaudeMd, startup-context-diet, live-runner]
made_by: agent
agent_type: systems-architect
branch: worktree-adherence-eval
pipeline_tier: full
affected_files:
  - eval/pyproject.toml
  - eval/src/praxion_evals/adherence/
  - eval/src/praxion_evals/live/session.py
  - eval/EVAL_PLAN.md
  - eval/README.md
affected_reqs: [REQ-01, REQ-02, REQ-05, REQ-07, REQ-08, REQ-09, REQ-17, REQ-18, REQ-19, REQ-21]
dissent:
  - "Steelmanned runner-up (fold into praxion-evals-live as a variant axis) keeps one run loop and one spend/isolation path; rejected for BA-01 and model mismatch, with a reversal trigger below."
  - "Statistics method (Tango score, one-sided 0.95) was a behavioral choice pending the applied-statistics consult (SQ-1); the consult ran in the same pipeline and dec-459 fixes the rule: the judged gate is the point estimate, the interval is reported and never decides, and the 20-pair default is bounded as stated there."
---

## Context

Phase 2 of the startup-context diet flips `omitClaudeMd` on agents one at a time, and each flip needs a measured, bounded non-regression gate (research §6.6 I2; alignment map §5 flip criterion; user decisions of 2026-10-11, map §8 Q10). The existing live runner (dec-392, isolation dec-391) runs seeded single-session scenarios against head/canary copies; it has no notion of a spawned role, paired arms, a per-role check catalog or a paired verdict. dec-040 keeps all evals out-of-band.

## Decision

Add `eval/src/praxion_evals/adherence/` (model, catalog, tasks + fixtures, arms, common and role checks, grade, verdict, results, report, cli) and the console entry `praxion-evals-adherence` in `eval/pyproject.toml`. Each session is a thin harness-fixed main session that spawns exactly one role via the Agent tool. The `lean` arm is built over a runner-owned materialized copy by setting `omitClaudeMd: true` on the measured role's definition (plus whatever SubagentStart injection the checkout ships); a copy-diff check and an arm proof (planted nonce plus first-request tokens) gate scoring. Each check names its rule (file + section) and is graded into a closed sum type: passed / failed / withheld / not applicable / errored; errored and not-measured sessions never enter a rate. Reuse `live/session` (argv, env, run, parse, isolation), `live/materialize`, `live/spend` and the error kinds; extend `parse_stream` additively with Agent tool results and per-subagent first-request usage. Like dec-392, this narrows dec-040 clause 3 only for isolated, operator-invoked sessions; nothing is reachable from a hook, pre-commit or a workflow, and no shipped agent, rule, skill or hook changes.

## Considered Options

### Option 1 — sibling package and console entry over the live boundary layer (chosen)
Pros: clean boundary for a different model (arms × pairs × catalog); reuses isolation and spend unchanged; satisfies BA-01. Cons: a second session loop beside live/cli.py.

### Option 2 — fold adherence into praxion-evals-live as a variant axis
Pros: one run loop, one CLI, one spend path. Cons: live's case/variant model is single-session graded scenarios; arms, pairing, the per-role catalog and paired verdicts would bloat a 624-line cli.py; BA-01 binds a separate entry.

### Option 3 — a standalone script under eval/scripts/ (like inheritance_probe.py)
Pros: smallest footprint. Cons: no console entry (KS1), no package-level tests for 17 roles' catalogs, report and verdicts.

### Option 4 — in-pipeline measurement from the observation WAL
Rejected by dec-040 (never hook-driven, never during a pipeline) and by the need for controlled paired fixtures.

## Consequences

Positive: every flip gets a reproducible, capped, paired measurement whose checks trace to existing rules; the token saving (first-request tokens) and adherence come from the same runs; a flip record can cite a run id. Negative: two session loops exist (live, adherence); full flip runs are long and paid (40-56 sessions); judged-check power at the 20-pair default is bounded as dec-459 states (the gate is the point estimate; the interval is reported, never decides).

Activation: no — the honest-uncertainty gate does not fire on the component boundary (the live runner's reuse surface is known); the statistics method, where uncertainty is real, is routed to the applied-statistics consult rather than decided here.

## Disconfirmation

- **Falsifier:** if implementing `adherence/cli.py` requires copying more than ~100 lines of `live/cli.py` orchestration (session loop, spend settle, checkpointing) instead of calling shared boundary functions, the separate-entry boundary is wrong and a shared run loop should have been extracted first.
- **Steelmanned runner-up:** Option 2 — one live runner with a generalized variant axis (head, canary, full, lean) would have one isolation, spend and preflight path, so a fix to sandboxing or spend lands once; the adherence catalog and verdict modules could still be separate libraries called by that one loop.
- **Reversal trigger:** a third live-session eval family is proposed, or the two loops diverge on an isolation or spend fix (a fix landing in one but not the other) — then extract a shared run loop under `live/` and make both entries thin.
