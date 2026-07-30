# Sequential Testing — Deciding When to Stop Collecting

Type-I and type-II error control when the sample size is not fixed in advance, worked through Wald's sequential probability ratio test. Reference material for the [Applied Statistics](../SKILL.md) skill.

**The question:** every expensive evaluation invites the same shortcut — run some, look, run more if it is close. Done naively that shortcut destroys the error guarantee the test was supposed to provide. Done deliberately it cuts the sample roughly in half. The difference is whether the stopping rule was chosen before the first look.

## Contents

- [Why peeking breaks a fixed-n test](#why-peeking-breaks-a-fixed-n-test)
- [Three legitimate designs](#three-legitimate-designs)
- [SPRT mechanics](#sprt-mechanics)
- [Worked example](#worked-example)
- [Error control, precisely](#error-control-precisely)
- [Truncation and the indifference region](#truncation-and-the-indifference-region)
- [Calibration is the real object](#calibration-is-the-real-object)
- [Choosing among the designs](#choosing-among-the-designs)
- [Gotchas](#gotchas)
- [Sources](#sources)

## Why peeking breaks a fixed-n test

A fixed-`n` test's 5% false-positive rate is a guarantee about **one** look at the data, at a pre-committed `n`. Each additional look is another chance to cross the threshold by luck, and the crossings are not independent of the ones before.

The inflation for repeated significance tests on accumulating data at a nominal 0.05:

| Looks | Actual type-I rate |
|---|---|
| 1 | 0.05 |
| 2 | ~0.08 |
| 3 | ~0.11 |
| 5 | ~0.14 |
| 10 | ~0.19 |
| 20 | ~0.25 |

With unbounded looking and no stopping rule, the probability of eventually crossing a fixed nominal threshold under the null approaches 1. "We stopped when it became significant" is therefore not a description of a result; it is a description of a procedure that will produce a significant result on null data given enough patience.

The same inflation applies to informal variants that do not feel like peeking: adding eval items until the delta looks convincing, extending a run because the trend is promising, re-running with a different seed after a disappointing result.

## Three legitimate designs

| Design | Stopping rule | Cost | Use when |
|---|---|---|---|
| **Fixed-n** | Collect `n`, look once | Simplest; wastes data when the effect is large or absent | `n` is cheap or the analysis must be trivially auditable |
| **Group-sequential** | A small number of pre-planned interim analyses, each at an adjusted threshold (alpha spending) | Modest power loss for early-stopping ability | Regulated or high-stakes settings; a handful of natural checkpoints |
| **SPRT / anytime-valid** | Evaluate after every observation against fixed boundaries | Minimal expected sample size; needs a specified alternative | Observations arrive one at a time and each is expensive |

All three are valid. The invalid design is the fourth one: fixed-`n` machinery applied to data that was looked at repeatedly.

## SPRT mechanics

Specify two point hypotheses and accumulate evidence for one against the other.

```text
H0: p = p0        H1: p = p1

After each observation x_i, accumulate the log-likelihood ratio:

  Lambda_n = sum_{i=1..n} log( f1(x_i) / f0(x_i) )

Boundaries, from the target error rates:

  A = (1 - beta) / alpha        upper, on the likelihood-ratio scale
  B = beta / (1 - alpha)        lower

Decision rule:

  Lambda_n >= log A   -> stop, accept H1
  Lambda_n <= log B   -> stop, accept H0
  otherwise           -> continue
```

For a Bernoulli outcome the per-observation increment takes one of two values:

```text
success -> log( p1 / p0 )
failure -> log( (1 - p1) / (1 - p0) )
```

The expected sample size follows from Wald's identity: the expected total is the boundary distance divided by the expected per-observation drift.

```text
E[N | H1] ~= [ (1 - beta) * log A + beta * log B ] / E[lambda | H1]
E[N | H0] ~= [ alpha * log A + (1 - alpha) * log B ] / E[lambda | H0]
```

`E[lambda | H1]` is the Kullback-Leibler divergence `D(f1 || f0)` — the information each observation carries about the difference between the hypotheses. **The stopping time is boundary distance divided by information per observation.** That single sentence is the whole intuition, and it also predicts the failure mode below.

## Worked example

Does a change lift an agent's pass rate from 70% to 80%? `alpha = beta = 0.05`.

```text
Boundaries
  A = 0.95 / 0.05 = 19          log A =  2.944
  B = 0.05 / 0.95 = 0.0526      log B = -2.944

Per-observation increments
  success:  log(0.80 / 0.70) =  0.1335
  failure:  log(0.20 / 0.30) = -0.4055

Drift
  E[lambda | H1] = 0.80(0.1335) + 0.20(-0.4055) =  0.0257   (KL, nats)
  E[lambda | H0] = 0.70(0.1335) + 0.30(-0.4055) = -0.0282

Expected sample sizes
  E[N | H1] = [0.95(2.944) + 0.05(-2.944)] / 0.0257 ~= 103
  E[N | H0] = [0.05(2.944) + 0.95(-2.944)] / -0.0282 ~=  94

Fixed-n equivalent (one-sided, same alpha and beta)
  n = [1.645*sqrt(0.7*0.3) + 1.645*sqrt(0.8*0.2)]^2 / 0.10^2
    = (0.7538 + 0.6580)^2 / 0.01 ~= 199
```

**About 100 observations expected versus 199 fixed** — roughly half the evaluation budget for the same error guarantees, which is the classical result for SPRT against simple hypotheses. Wald and Wolfowitz proved this optimality: among all tests with error rates no worse than `alpha` and `beta`, the SPRT minimises expected sample size at **both** hypotheses.

Note that the saving is an expectation, not a bound. Individual runs can exceed 199. That is what truncation is for.

## Error control, precisely

Wald's boundaries are approximations that ignore *overshoot* — the accumulated statistic jumps past the boundary rather than landing exactly on it. The resulting guarantees:

```text
alpha_actual <= alpha / (1 - beta)
beta_actual  <= beta  / (1 - alpha)
alpha_actual + beta_actual <= alpha + beta
```

At `alpha = beta = 0.05` the worst case is `0.05 / 0.95 = 0.053`. In practice overshoot pushes the achieved rates slightly *below* nominal, making the test mildly conservative. For an engineering gate this slack is immaterial; state the nominal rates and move on.

What is **not** immaterial: these guarantees hold only for the specified `p0` and `p1`, only if the observations are independent and identically distributed, and only if the stopping rule is followed without amendment. Adding "and also stop if it looks bad after 500" without re-deriving is a different test with unknown error rates.

## Truncation and the indifference region

Between `p0` and `p1` lies the **indifference region**, where the drift `E[lambda]` is near zero. The statistic random-walks without systematic movement toward either boundary, and expected sample size peaks — it can exceed the fixed-`n` equivalent, sometimes substantially.

Two consequences for practice:

- **Always truncate.** Cap the test at some `N_max` (a common choice is the fixed-`n` equivalent, or a small multiple of it) with a declared decision at the cap. Report the cap as part of the design; a truncated SPRT's error rates differ slightly from the untruncated ones, and the honest move is to state the truncation rather than to pretend it never binds.
- **Choose `p0` and `p1` to bracket the decision, not to be plausible.** `p1` should be the smallest effect worth acting on. Setting `p1` far from `p0` makes the test fast and blind to modest real effects; setting it too close makes the drift tiny and the test slow.

## Calibration is the real object

The stopping time is boundary distance divided by information per observation. If the statistic being accumulated carries **no** information distinguishing the two states, the drift is zero, nothing ever crosses, and every case runs to the truncation cap. The rule has not failed noisily — it has silently become "always spend the maximum."

This is not hypothetical. A sequential-consensus governor applied to multi-agent LLM debate reported:

- On a task family where its consensus statistic *was* informative, the rule stopped at about **1.01 rounds and 4.06 model calls at 97.0% accuracy**, against a fixed-5-round protocol at 15 calls and 99.0% — roughly **3.7x fewer calls for 2 points of accuracy**.
- On a different task family, the calibrated divergence between the two hypothesised states collapsed to approximately **zero**. The rule then capped **99.5% of items** at about **2.1x the baseline cost** — worse than not having it.

The second outcome is the important one, and it is a *feature* read correctly: a near-zero calibrated divergence is a measurement that the chosen statistic carries no signal in that domain. Discovering that is worth more than the compute the governor was supposed to save, because it invalidates every other use of the same statistic — including the qualitative gates that were relying on it without measuring anything.

**The transferable discipline:** before adopting any sequential or adaptive stopping rule, measure the divergence between the two states on a **held-out calibration set**, disjoint from the data the rule will run on. Report it. A stopping rule whose calibration was never measured is an untested instrument governing a spend decision, and its silent failure mode is to consume the maximum budget while appearing to work.

The same check generalises beyond SPRT: any adaptive gate — escalate-on-uncertainty, retry-on-low-confidence, route-by-difficulty — rests on a score that is assumed to separate two states. Measure the separation before trusting the gate.

## Choosing among the designs

| If | Then |
|---|---|
| The alternative can be stated as a point value worth acting on | SPRT, truncated |
| Only "some improvement" can be specified | Group-sequential with alpha spending, or a confidence sequence |
| Monitoring is continuous and unplanned | Anytime-valid methods (e-values, confidence sequences) — they permit optional stopping by construction |
| Observations are cheap and `n` is small | Fixed-`n`. The machinery is not worth it |
| The result must be auditable by non-specialists | Fixed-`n` with a pre-registered `n` |

**Choose before the first look.** Every one of these designs is valid prospectively and none of them is valid retrofitted onto data that has already been examined.

## Gotchas

| Gotcha | Why it misleads | What to do |
|---|---|---|
| Stopping when the p-value first dips below 0.05 | Type-I rate approaches 1 with enough looks | Adopt a sequential design before the first look |
| Extending a run because the result is "close" | Same inflation, informally | Pre-commit `n` or use a sequential boundary |
| Untruncated SPRT | Expected `N` peaks in the indifference region | Cap at `N_max` and declare the cap's decision |
| Choosing `p1` for plausibility rather than decision relevance | Test optimised for the wrong effect size | `p1` = smallest effect worth acting on |
| Deploying a stopping rule without measuring its calibration | Silent degradation to always-spend-maximum | Measure the divergence on a held-out set first |
| Reading a capped run as "no difference" | The cap fires both when there is no effect and when the statistic is uninformative | Distinguish the two by reporting the measured divergence |
| Applying SPRT to correlated observations | The i.i.d. assumption underpins the boundaries | Use the task as the unit, or model the dependence |
| Amending the stopping rule mid-run | Error rates become unknown | Fix the rule; re-derive if it must change |

## Sources

- A. Wald, *Sequential Analysis* (1947) — the SPRT, its boundaries, and the error inequalities. Wald and Wolfowitz (1948) established its expected-sample-size optimality against simple hypotheses.
- Armitage, McPherson and Rowe (1969) — the repeated-significance-test inflation table.
- [Sequential Consensus for Multi-Agent LLM Debates (arXiv:2605.19193)](https://arxiv.org/abs/2605.19193) — the applied case study quoted above, including the calibration-collapse outcome.
