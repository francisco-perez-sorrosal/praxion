# Inference for Evals — Multiplicity, Bootstrap Intervals, Agreement, Variance

Turning eval numbers into defensible claims: correcting for many comparisons, putting intervals on `pass@k`, quantifying judge agreement, and separating non-determinism from real effects. Reference material for the [Applied Statistics](../SKILL.md) skill.

**Boundaries — this file does not restate these:**

- `pass@k` / `pass^k` as *metric definitions*, trial-count defaults, and eval suite design belong to the [agent-evals](../../agent-evals/SKILL.md) skill.
- The **judge-calibration protocol as a pipeline gate** (the calibration loop, the pass bar, recalibration triggers, false-pass budgeting) belongs to [agent-evals/references/eval-rigor.md](../../agent-evals/references/eval-rigor.md). This file supplies the *statistics* that protocol consumes: which agreement coefficient, how much it can be trusted at a given sample size, and how to interval it.
- Choosing `n` before collection belongs to [power-and-sample-size.md](power-and-sample-size.md).

## Contents

- [Multiple comparisons across benchmarks](#multiple-comparisons-across-benchmarks)
- [Bootstrap intervals on pass@k](#bootstrap-intervals-on-passk)
- [Comparing two systems](#comparing-two-systems)
- [Judge-agreement statistics](#judge-agreement-statistics)
- [Non-determinism variance](#non-determinism-variance)
- [Gotchas](#gotchas)

## Multiple comparisons across benchmarks

Evaluating one change against twelve benchmarks is twelve hypothesis tests. At a nominal 0.05 each, the probability of at least one spurious "win" under a pure-null scenario is `1 - 0.95^12 = 46%`. Reporting the best of twelve as *the* result is the most common statistical error in eval reporting, and it is invisible in the write-up because the other eleven are not mentioned.

### Declare the family first

The correction depends on `m`, the number of tests in the family — and `m` must be fixed **before** looking at results. In practice `m` is larger than it appears:

```text
m = benchmarks x metrics-per-benchmark x model-variants x checkpoints x prompt-variants
```

Six benchmarks, two metrics each, three prompt variants is `m = 36`, not 6. If the analysis plan says "we will look at accuracy and F1 on all suites, for whichever prompt wins," the family is the whole grid — the choice of which cell to report is itself a comparison.

### FWER or FDR

| Control target | Question it answers | Use when |
|---|---|---|
| **FWER** (family-wise error rate) | "What is the chance I make *any* false claim?" | A single false claim is costly: a shipping gate, a headline result, a regression alarm |
| **FDR** (false discovery rate) | "What fraction of my claims are false?" | The output is a triage list; some false leads are acceptable |

### The procedures

| Procedure | Rule | Notes |
|---|---|---|
| **Bonferroni** | Reject `p_i <= alpha / m` | Simplest, most conservative. Fine for small `m`. |
| **Holm-Bonferroni** | Sort ascending; compare `p_(i)` to `alpha / (m - i + 1)`; stop at the first failure and retain all remaining | Strictly more powerful than Bonferroni with identical FWER control. **There is no reason to prefer plain Bonferroni once you can sort.** |
| **Benjamini-Hochberg** | Sort ascending; find the largest `i` with `p_(i) <= (i/m) * q`; reject all tests up to that rank | Controls FDR at `q` under independence or positive dependence — the usual case for related benchmarks |
| **Benjamini-Yekutieli** | BH with the threshold divided by `H_m = sum(1/i, i=1..m)` | Valid under arbitrary dependence; noticeably more conservative |

### Worked: the three procedures diverge

Ten tests, sorted p-values `0.001, 0.008, 0.012, 0.030, 0.040, 0.070, 0.11, 0.20, 0.35, 0.60`, at `alpha = q = 0.05`:

```text
Bonferroni  threshold 0.05/10 = 0.005          -> 1 rejection  (0.001)
Holm        0.001 < 0.05/10 = 0.0050  reject
            0.008 > 0.05/9  = 0.0056  stop     -> 1 rejection
BH          i=1: 0.001 <= 0.005  ok
            i=2: 0.008 <= 0.010  ok
            i=3: 0.012 <= 0.015  ok
            i=4: 0.030 >  0.020  --
            i=5: 0.040 >  0.025  --
            largest passing i = 3               -> 3 rejections
```

Same data, one claim under FWER control and three under FDR control. Neither is wrong; they answer different questions. What *is* wrong is choosing the procedure after seeing which one yields the desired verdict.

### When correction is not the right tool

- **One pre-declared primary metric plus secondaries.** Declare the primary before collection and test it uncorrected; treat all secondaries as exploratory and label them as such. This is often more honest and more powerful than correcting everything equally.
- **A composite or averaged score.** Averaging twelve benchmarks into one number is a single test, not twelve — but it also dilutes any real effect and hides which suite moved. Prefer a declared primary.
- **Estimation instead of testing.** Reporting twelve effect sizes with intervals, and drawing no binary conclusions, needs no multiplicity correction because no rejection decisions are made. Do not then quietly narrate the largest one as significant.

## Bootstrap intervals on pass@k

`pass@k` is a point estimate on a finite sample of tasks. Without an interval it is not comparable across runs.

### Use the unbiased estimator

With `n` trials per task of which `c` succeed, estimating `pass@k` for `k <= n`:

```text
pass@k = 1 - C(n - c, k) / C(n, k)
```

The intuitive `1 - (1 - p_hat)^k` is **biased upward** for small `n`, sometimes materially. Use the combinatorial form, average it across tasks, and record `n` and `k` alongside the number.

### Resample tasks, not trials

The resampling unit must match the unit of independence. Trials within a task are correlated (see [power-and-sample-size.md](power-and-sample-size.md#repeated-trials-are-not-independent-observations)), so:

```text
for b in 1..B:
    sample n_tasks tasks WITH replacement
    for each sampled task, carry ALL of its trials along unchanged
    recompute pass@k on the resampled task set
percentile interval = the 2.5th and 97.5th percentiles of the B values
```

This is a **cluster (block) bootstrap**. Resampling individual trials independently breaks the within-task correlation and produces intervals that are too narrow — frequently by a factor of two or more when `rho` is high. The narrow interval then makes noise look like a result.

### Practical settings

- **`B >= 2,000`** for a 95% interval; `B >= 10,000` if reporting anything beyond the 95th percentile. Report `B` — the interval itself carries Monte-Carlo error that shrinks as `1/sqrt(B)`.
- **Near the 0 or 1 boundary**, percentile intervals distort. Use BCa, or bootstrap on the logit scale and back-transform, so the interval cannot extend past the boundary.
- **Very few tasks (under ~30)** make any bootstrap unreliable — it can only resample the diversity actually present. With 12 tasks, report the per-task outcomes rather than an interval that implies precision the sample cannot support.
- **Fixed `k` across compared runs.** `pass@k` is not comparable across different `k`, and not comparable across different `n` without the unbiased estimator.

## Comparing two systems

### Interval the difference, not each system

The decision object is the **paired difference**, and it gets its own interval:

```text
for b in 1..B:
    sample tasks with replacement
    d_b = pass@k(system B, resampled tasks) - pass@k(system A, resampled tasks)
interval on d = percentiles of {d_b}
```

Because both systems are evaluated on the same resampled tasks, task difficulty cancels and the interval on `d` is far tighter than either marginal interval.

**Marginal-interval overlap is not a test.** Two systems' individual 95% intervals can overlap substantially while the paired difference interval excludes zero cleanly — the overlap heuristic is a different, and much less powerful, comparison than the one the decision needs. The converse direction is safe: non-overlapping marginal intervals do imply a difference. Build the difference interval and read that.

### For paired binary outcomes

McNemar's test uses only the discordant pairs: `b` items where A is right and B is wrong, `c` items where B is right and A is wrong.

```text
chi2 = (|b - c| - 1)^2 / (b + c)        # continuity-corrected
exact binomial test on b out of (b + c) when b + c < 25
```

Concordant items carry no information about which system is better; this is exactly why the discordance rate, not the accuracy, drives the sample size.

### For anything else

A **paired permutation test** needs no distributional assumption: repeatedly flip the A/B label within each item at random, recompute the difference, and read off the fraction of permutations at least as extreme as the observed one. It is the safest default for unusual metrics (rubric scores, rank-based measures, cost-weighted composites).

## Judge-agreement statistics

An LLM-as-judge is an instrument whose error rate must be measured before its scores gate anything. The *protocol* for doing that lives in [eval-rigor.md](../../agent-evals/references/eval-rigor.md); what follows is the statistics it rests on.

### Which coefficient

| Situation | Coefficient |
|---|---|
| Two raters, nominal categories | Cohen's `kappa` |
| Two raters, ordinal rubric (1-5) | Weighted `kappa` (quadratic weights) — treats a 1-vs-5 disagreement as worse than 1-vs-2 |
| More than two raters, or missing ratings, or mixed scales | Krippendorff's `alpha` |
| Continuous scores from the same instrument | Intraclass correlation |

All of them correct for chance agreement:

```text
kappa = (p_o - p_e) / (1 - p_e)
```

where `p_o` is observed agreement and `p_e` is agreement expected from the marginals alone.

### The kappa paradox

`kappa` can be low while raw agreement is high. Two independent causes, worth diagnosing separately:

- **Prevalence effect.** When one category dominates (95% of outputs pass), `p_e` is close to `p_o` and the ratio collapses. A judge with 0.94 raw agreement can score `kappa = 0.2` on a lopsided set.
- **Bias effect.** When the two raters' marginals differ systematically (the judge passes 80%, humans pass 60%), `kappa` is depressed even where the per-item pattern is consistent.

**Always report the confusion matrix alongside `kappa`.** It is four numbers and it makes both effects visible; the coefficient alone does not. Stratify the calibration set to avoid extreme prevalence rather than reporting a paradoxical `kappa` and arguing about it.

### Kappa has sampling error

A `kappa` point estimate on a small calibration set is far less precise than its two decimal places suggest. The common large-sample approximation:

```text
SE(kappa) ~= sqrt( p_o * (1 - p_o) / ( n * (1 - p_e)^2 ) )
```

At `n = 60`, `kappa = 0.60`, `p_e = 0.50` (so `p_o = 0.80`):

```text
SE = sqrt( 0.80 * 0.20 / (60 * 0.25) ) = sqrt(0.0107) = 0.103
95% interval ~= 0.60 +/- 0.20  ->  [0.40, 0.80]
```

That set is simultaneously consistent with "fair" and "substantial" agreement. Because `SE` scales as `1/sqrt(n)`, pinning `kappa` to a half-width of 0.10 takes roughly **250 items, not 60**.

Two consequences:

- **Gate on the interval's lower bound, not the point estimate.** A judge whose `kappa` interval reaches below the bar has not cleared it.
- **Prefer a bootstrap interval** over the closed form — resample items, recompute `kappa`, take percentiles. The approximation above is adequate for planning, not for reporting.

## Non-determinism variance

Repeated runs of the same agent on the same input differ. Sampling temperature is only one source; kernel non-determinism, batching, tool-call ordering, and provider-side changes all contribute — which is why fixing the seed does not make the variance disappear, it only hides it.

### Decompose it

```text
var_total   = var_between_tasks + var_within_task
rho (ICC)   = var_between_tasks / var_total
```

Estimate both from the `n x k` run matrix. The decomposition drives three separate decisions:

| Component | What it tells you | What it feeds |
|---|---|---|
| `var_between_tasks` | How much the suite discriminates between easy and hard items | Suite design — near-zero means the suite is saturated or trivial |
| `var_within_task` | Run-to-run instability of the system itself | The run-to-run term of a derived tolerance band ([tolerance-bands.md](tolerance-bands.md)) |
| `rho` | How much a marginal trial is worth | Budget allocation and the design effect |

### Report it, do not suppress it

Fixing seeds to obtain a stable number produces a measurement of a configuration nobody deploys. If production samples, the eval should sample, and the reported metric should carry its run-to-run spread. Suppressing variance at measurement time does not remove it from production; it removes your ability to see it.

A useful discipline: report `mean +/- run-to-run sd across k runs (k = ...)` for any headline metric, and treat a change smaller than that spread as unmeasured.

## Gotchas

| Gotcha | Why it misleads | What to do |
|---|---|---|
| Reporting the best of N benchmarks | Selection over N tests, presented as one result | Declare the family and the correction before looking |
| Choosing the correction after seeing p-values | Turns the correction into another researcher degree of freedom | Pre-declare FWER-vs-FDR and the procedure |
| Bootstrapping trials instead of tasks | Breaks within-task correlation; intervals too narrow | Cluster bootstrap: resample tasks, carry their trials |
| `1 - (1 - p)^k` for `pass@k` | Biased upward at small `n` | Use the combinatorial unbiased estimator |
| Declaring "no difference" from overlapping marginal intervals | A weaker and different test than the paired one | Interval the paired difference |
| Trusting a `kappa` point estimate from 50-60 items | Interval spans two agreement bands | Bootstrap the interval; gate on its lower bound |
| High raw agreement read as a calibrated judge | Prevalence inflates raw agreement | Report `kappa` plus the confusion matrix on a stratified set |
| Fixing seeds to stabilise a headline metric | Measures a configuration that is not deployed | Sample as production samples; report the spread |
| Comparing `pass@k` values computed at different `k` or `n` | Not the same quantity | Fix `k`, use the unbiased estimator, record both |
