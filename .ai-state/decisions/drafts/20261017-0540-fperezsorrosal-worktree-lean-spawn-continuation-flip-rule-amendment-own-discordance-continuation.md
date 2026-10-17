---
id: dec-draft-c9d81997
title: The flip rule sizes mechanical allowances by the run's own discordance, seeds launch order, states coverage, and makes a stopped run one declared run that is continued or closed
status: proposed
category: behavioral
date: 2026-10-17
summary: "Amends dec-459 clauses 2 and 5 after the statistician consult (CH-01 to CH-06, all switch-now), awaiting the user's ratification before the next flip. Each mechanical allowance is the exact one-sided quantile at the run's own discordant count for that check; no calibration run sets an allowance; the two arms' launch order is seeded per task. The report states each allowance in points beside the margin and lists a check as not covered when it exceeds the margin, and C5 as not covered under five both-ran-out pairs. A run stops after N >= 3 identical (masked-tail) infrastructure errors in one arm. A two-armed stop or a spend refusal is continuable under an identical tree outside the results directory, and a continuation is one run with its lineage. A fresh run of a role is refused while a continuable stopped run is neither continued nor closed. C5 binds only on a role the harness stopped at its cap. Earlier runs are grouped by role definition and kernel identity, every other run of the role listed apart."
tags: [eval, adherence, statistics, flip-rule, lean-spawns, consult, continuation, startup-context-diet]
made_by: agent
agent_type: systems-architect
branch: worktree-lean-spawn-continuation
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/
  - eval/EVAL_PLAN.md
  - docs/lean-spawn-how-to.md
affected_reqs: [REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: dec-459
superseded_in_part_by: null
dissent: null
---

## Context

dec-459 set the flip rule the lean-spawn pilot ran under. The pilot closed with gaps that make the instrument either costly or undecisive:
- every mechanical allowance stayed zero because no calibration run existed (td-450);
- a dead credential spent a run's remaining sessions (td-445);
- a stopped run could not be continued (td-451);
- C5 could not tell a role that ran out of turns from one that judged itself finished (td-447);
- the earlier-run listing, scoped to one commit, never fired (td-455).

The statistician consult (`CONSULT_statistician.md`, round 1) showed by exact calculation and simulation at 24 pairs that:
- an allowance taken from any calibration's discordant count gives an unchanged role a family-level false-regression rate of 0.30 (separate run) to 0.38 (concurrent replicate), while the same quantile at the trial's own count stays under nominal;
- a 95% allowance on a noisy check tolerates two to three times the 10 pp margin unseen;
- a stop confined to one arm plus a relaunch would redraw lean failures;
- N = 2 lets one task stop a run;
- an operator free to continue or start fresh after seeing interim counts lifts false clearance by 3 to 12 points;
- C5 bound to running out of turns leaves 0 to 4 usable pairs per role.

Activation: no -- the option set was fixed by the consult's dispositions and the orchestrator's checkpoint decisions.

## Decision

1. **Allowances (replaces clause 2).** A mechanical check regresses when `fails_lean - fails_full` exceeds its allowance, and the allowance is the exact one-sided quantile, at the declared confidence, of `2 * Binomial(d, 1/2) - d`, where `d` is that check's discordant count over the pairs this run's verdict counts: the exact one-sided paired-test critical value, one per role and check. No calibration run is an allowance source.
2. **Seeded order.** The two arms of each task launch in an order drawn from the run's seed for that task, recorded with the task and kept by a continuation.
3. **Coverage.** The report states each mechanical allowance in pairs and in percentage points beside the declared margin. A check whose allowance exceeds the margin times its usable pairs is listed as not covered at the margin and named in the flip claim. C5 is listed as not covered when fewer than five pairs ran out of turns on both sides. The run-out table and the differential run-out rate are reported, never gated.
4. **Infrastructure stop.**
   - The run declares before launch a stop count N (at least 3, default 3), the counting error kinds (never an evaluation exception) and a masking rule for evidence tails.
   - N sessions in a row in one arm of one role ending in the same kind and the same masked tail stop all launching.
   - The stop is continuable only when the role's other arm ended in the same kind and masked tail inside the streak's window.
5. **Continuation (extends clause 5's unit).**
   - *What may continue*: a continuable stop or a spend refusal is continued only on an identical tree outside the results directory, with the same resolved model, seed, task list, launch orders and declarations.
   - *What relaunches*: only the streak's sessions and spend-refused launches count as never launched, and their tasks relaunch whole. Every other session keeps its outcome, and lean-only errors remain lean failures.
   - *How it counts*: the lineage is one run, with one verdict and one listing entry, and any part's id resolves to the whole.
6. **Pre-commitment.** A fresh run of a role is refused while a stopped run of that role that was continuable when it stopped is neither continued nor closed. Closing needs an explicit, recorded reason. A closed run is listed as a not-clear draw carrying its interim per-check result, and does not by itself refuse a later switched record.
7. **C5.** C5 binds only on a session whose role the harness stopped at its turn cap. A role that ended before its cap is scored on C2 instead, and C5 is withheld when the cap cannot be established. Recorded sessions are never re-scored.
8. **Earlier runs (replaces clause 5's scope).** Earlier runs are listed by role definition and kernel identity, whatever the commit. Every other run of the role is named apart, calibration runs apart, lineages once, closed runs as not-clear draws, and non-results files are skipped and named.

Clauses 1, 3, 4, 6 and 7 of dec-459 stand.

## Considered Options

### Allowance from the run's own discordance (chosen)

Pros: nominal size at zero extra sessions; exchangeability is bought by the seeded order. Cons: it cannot flag a check with fewer than five discordant pairs, which the coverage statement makes visible.

### A separate same-arm calibration run per role, pooled across matching runs

Pros: more power on low-discordance checks. Cons: the power comes from an excess false-regression rate (family-level 0.30), not from information; it doubles sessions per role, and one calibration draw is shared by every trial that uses it.

### A concurrent replicate arm inside the trial

Pros: 3 sessions per task, and identity matches by construction. Cons: the shared full arm raises the false-regression rate further (0.15 on the commonest profile, family-level 0.38), at no gain in power; it also adds a third slot to the stop and the continuation.

### Visibility instead of pre-commitment

Pros: no refusal. Cons: listing an abandoned run never changes a flip, so optional continuation still inflates clearance.

## Consequences

- td-450 is resolved by design, with no paid calibration run. The `--calibration-run` option is removed, and `--calibration` survives only as a diagnostic.
- A noisy mechanical check can read "not covered" on a flip claim. That is honest and may need more pairs, which is the user's call per role.
- C5 may be withheld or not covered for roles whose early-stop cap does not make them run out; tuning that cap is td-461.
- The amended rule binds only after the user ratifies it. Until then the report and the docs say so.

## Prior Decision

dec-459 (partially superseded) set the allowance as the 95th percentile of a same-arm calibration run's discordance (zero until calibrated), and listed earlier runs of a role on the same checkout sha. What changes: the allowance source and its coverage statement, the run unit under a stop and continuation, the listing's scope, and C5's binding. The point-estimate judged gate, the worst-case recount, slack and the one-retry policy, the honest judge-error wording and the 20-pair target are unchanged. It is a partial rather than a full supersession because those clauses stand.
