---
id: dec-459
draft_id: dec-draft-e471117c
title: The lean-spawn flip rule gates on paired point estimates with a calibrated noise allowance, lists every run, and recounts lean-only errors as failures
status: accepted
category: behavioral
date: 2026-10-12
summary: "After the applied-statistics consult (six challenges, all switch-now): a judged check is non-inferior when the lean arm's pass rate over complete pairs is no more than the declared margin (10 pp) below the full arm's, with the one-sided score interval reported and never claimed as a bound; a mechanical check regresses when lean fails more pairs than full by more than a per-check allowance derived from a same-arm calibration run (zero until calibrated, which is today's strict rule); the flip verdict uses the worst-case recount in which a pair errored on the lean side only counts as a lean failure; a role's task set carries slack above the target and an errored session gets one infrastructure-only retry; the report lists every run of the role on that checkout so a rerun cannot be read as a fresh draw; judge error is stated as attenuating, not conservative, and the smoke run judges a golden good case beside each golden bad case."
tags: [eval, adherence, statistics, flip-rule, lean-spawns, consult, startup-context-diet]
made_by: agent
agent_type: orchestrator
branch: worktree-adherence-eval
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/
  - eval/EVAL_PLAN.md
  - docs/independent-analysis/subagent-alignment-map.md
affected_reqs: [REQ-20, REQ-21, REQ-22, REQ-23, REQ-26]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
superseded_in_part_by: [dec-draft-c9d81997]
---

## Context

The ratified flip rule (alignment map §5 and §8 Q10) reads: no regression on any mechanical check, and judged checks non-inferior within a margin declared before the run, proposed at 10 percentage points over about 20 paired tasks per role, claiming bounded non-regression and never improvement. The architect's spec encoded the judged half as a confidence bound (Tango one-sided 0.95) and showed that no run of 20 pairs can satisfy it even when both arms agree on every pair. The `statistician` consult (`CONSULT_statistician.md`, Round-0 HEAD 7ecda507) then showed, by exact calculation over the paired table, that a 25-pair bound clears an unchanged role's single judged check only 42% of the time and two checks 17%; that the strict mechanical rule blocks an unchanged role 55–97% of the time once it carries four to eight checks; that "a flip record cites one run" permits best-of-N reruns (three runs lift false clearance from about 6% to 16–20%); that non-differential judge error attenuates the paired difference, which is anti-conservative for non-inferiority; that a target set at the power floor is left underpowered by a single errored session on 40–92% of runs; and that excluding pairs errored on the lean side only is biased toward lean.

## Decision

1. **Judged checks gate on the point estimate.** Non-inferior when `(passes_lean − passes_full) / complete_pairs ≥ −margin`, margin 10 pp unless declared otherwise. The one-sided 95% score interval (Tango) on the paired difference is computed and reported with every verdict, and the report says what it does and does not show; it never gates and the wording never claims a confidence bound was met. This is the user's rule as ratified; the confidence-bound reading was the spec's, and no affordable run can meet it.
2. **Mechanical checks gate on a calibrated allowance.** A mechanical check regresses when `fails_lean − fails_full > allowance(check)`, where the allowance is the 95th percentile of the same-arm net discordance observed in a declared calibration run (the `full` arm against itself on the same tasks and seed) for that check, and **zero until a calibration run exists**, which is the strict rule the user ratified. The calibration run's id is a declared setting.
3. **Worst-case recount gates.** A pair whose lean side errored while the full side did not is counted as a lean failure for every check that pair carried; the verdict uses that recount, and the report shows both the recount and the complete-pairs figures. A pair errored on the full side only, or on both, is incomplete and excluded as before.
4. **Slack and one retry.** The generated task set holds the declared target plus declared slack (default: a fifth of the target, at least four tasks); an errored session is retried once, only for infrastructure error kinds the live runner already distinguishes, never for a behavioural outcome; the retry is recorded.
5. **Every run is listed.** The results file and the report name every earlier run of the same role on the same checkout sha, in order, with each run's verdict; the Phase 2 flip record cites all of them. A rerun is therefore visible as a repeated draw, not a fresh one.
6. **Judge error is stated honestly.** The smoke run judges a golden good case beside each judged check's golden bad case and records both; the report states the judge's observed error on those cases and that judge error attenuates differences.
7. **Target.** The default target stays 20 complete pairs per role, declared before the run; the report states, per judged check, the usable pairs and the interval's width so the reader sees the precision the run bought.

## Considered Options

### Keep the confidence-bound reading and raise the target (25 or 35 pairs)

Rejected: at 25 pairs the gate blocks an unchanged role most of the time, and the pairs needed for 80% power (about 85) cost four times the budget the user set. A gate that blocks unchanged roles is ignored, which is worse than no gate.

### Point-estimate gate with the interval reported (chosen)

Pros: feasible at the ratified budget; the claim is bounded by the margin and the interval is on the record; calibration turns the mechanical rule's allowance from an assertion into a measurement. Cons: a truly worse lean arm passes more often than under a bound; the report's interval and the every-run listing are what keep the reader honest.

### Widen the margin to 12–15 pp

Rejected: it moves the number to what 20 pairs can show rather than to what matters; the user's margin stays and the method changes instead.

## Consequences

- The verdict module declares method, margin, target, slack, retry policy, allowance source and calibration run id before the first launch, and refuses to change them afterwards.
- The smoke run (REQ-26) gains a same-arm calibration run for one pilot role, which also settles the consult's CH-01, CH-02 and CH-06 with data.
- Spend per flip rises by the slack and the retries, not by a larger target.
- Each consult challenge's disposition is recorded in `.ai-state/CONSULT_LEDGER.md` against this record; the user ratifies this rule before the first Phase 2 flip, and a different ratified rule supersedes this record.
