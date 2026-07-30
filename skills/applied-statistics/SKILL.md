---
name: applied-statistics
description: >
  Applied statistics for engineering decisions: power and sample-size planning
  before collection, multiple-comparisons correction, bootstrap intervals on
  pass@k, chance-corrected judge agreement, non-determinism variance,
  confounding and Simpson's-paradox risk in metric trends,
  error-model-derived tolerance bands, sequential testing and type-I/II error
  control. Triggers: claiming an effect is significant, sizing a sample or run
  count, comparing systems across benchmarks, deriving a threshold or tolerance
  band, when to stop collecting data.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Applied Statistics

Design and inference for decisions made from data: how much data is needed, what a number licenses you to claim, and where an aggregate can be arithmetically correct and directionally wrong.

**Content boundary.** This skill covers **pre-collection design** (power, sample size, stopping rules) and **inference for evaluations** (multiplicity, interval estimation, agreement, confounding, derived thresholds). Microbenchmark measurement mechanics — iteration counts, coefficient of variation, latency percentiles, and run isolation for performance benchmarks — are a distinct, adjacent concern owned by [performance-architecture/references/benchmarking.md, section Statistical Rigor](../performance-architecture/references/benchmarking.md#statistical-rigor). Consult that file for how to *take* a performance measurement; consult this skill for how many observations the decision requires and what the resulting number supports.

**Satellite files** (loaded on-demand):

- [references/power-and-sample-size.md](references/power-and-sample-size.md) -- pre-collection planning: the four quantities, choosing an MDE, paired vs unpaired sample size, design effect for repeated trials, budget allocation, and what to do when the budget cannot reach the MDE
- [references/eval-inference.md](references/eval-inference.md) -- multiple-comparisons correction across benchmarks (FWER vs FDR, Holm, Benjamini-Hochberg), bootstrap intervals on `pass@k`, paired system comparison, judge-agreement coefficients and their sampling error, non-determinism variance decomposition
- [references/confounding-and-trends.md](references/confounding-and-trends.md) -- Simpson's paradox worked on a code-metric claim, the confounder catalogue for engineering metrics, adjustment methods, and the language discipline that matches claim strength to design strength
- [references/tolerance-bands.md](references/tolerance-bands.md) -- deriving a PASS/WARN/FAIL band width from an error model: noise-source enumeration, quadrature combination, the floor-and-ceiling constraint, and what to do when no valid band exists
- [references/sequential-testing.md](references/sequential-testing.md) -- why peeking breaks a fixed-n test, group-sequential and anytime-valid alternatives, the Wald SPRT with a worked expected-sample-size calculation, and why calibration is the object that actually governs an adaptive stopping rule

## Gotchas

The failure modes below survive competent analysis, which is why they are worth loading before the work rather than after.

- **Sample size is a design decision, not an analysis decision.** Power spent is unrecoverable. Once collection is done, no method recovers the ability to detect an effect the design was never sized for — and computing power *after* a null result is uninformative, because observed power is just a restatement of the p-value.
- **Repeated trials are not independent observations.** Running 5 trials on 100 tasks yields 500 measurements and, at a within-task correlation of 0.6, the statistical power of about 147 independent items. Extra trials per task buy far less than the run count suggests.
- **The best of N benchmarks is a selection, not a result.** Twelve independent tests at a nominal 0.05 produce at least one spurious win 46% of the time under the null. The family size must be declared before looking, and it is usually larger than the benchmark count (metrics, variants, and checkpoints multiply it).
- **Overlapping confidence intervals are not a test of no-difference.** The decision object is the interval on the *paired difference*, which is much tighter than either system's marginal interval. Reading overlap as equivalence is a weaker and different comparison than the one the decision needs.
- **A tolerance band narrower than the metric's own noise is a false-alarm generator.** A 2-point band on a metric whose combined standard deviation is 2.3 points fires on roughly two runs in five of an unchanged system. The gate then gets ignored, which is worse than having no gate.
- **An unadjusted aggregate can point the opposite way from every stratum.** This is exact arithmetic, not a small-sample fluke, and it is the normal consequence of non-random rollout: tooling lands on the worst modules first, so the treated and untreated populations differ on the thing that drives the outcome.
- **Stopping when the result "becomes significant" guarantees significance eventually.** Under the null, unbounded peeking crosses a fixed nominal threshold with probability approaching 1. Choose the stopping rule before the first look, or accept a fixed `n` and look once.
- **Fixing seeds to stabilise a headline number measures a configuration nobody deploys.** If production samples, the eval must sample, and the reported metric must carry its run-to-run spread.
- **Statistical significance is not effect size, and effect size is not decision relevance.** A significant 0.3-point gain that costs 2x the tokens is a significant result and a bad decision. Report the magnitude and its interval; test against the smallest effect worth acting on.
- **Pairing is usually a 5x saving and is almost always available.** Evaluating both systems on the same items turns the cost driver from the accuracy level into the *discordance rate*. Retaining per-item outcomes rather than only the aggregate is what makes it possible — and it is the cheapest single thing to get right at collection time.

## The Five Questions

Before a number becomes a claim, answer these in order. A gap at any step is the finding; do not proceed past it silently.

1. **What decision does this number drive, and what is the smallest change that would alter it?** That change is the minimum detectable effect. Without it, no sample size, band width, or stopping rule can be justified — and any of them chosen without it is arbitrary. See [power-and-sample-size.md](references/power-and-sample-size.md#choosing-the-effect-size-honestly).
2. **What is the unit of independence?** Items? Tasks? Runs? Users? Repositories? Everything downstream — the sample size, the bootstrap resampling unit, the degrees of freedom — follows from this answer, and getting it wrong is the single most common source of intervals that are too narrow.
3. **How many comparisons is this really one of?** Count the whole grid: benchmarks times metrics times variants times checkpoints, plus every comparison that was looked at and not reported. Declare the family and the correction before seeing results. See [eval-inference.md](references/eval-inference.md#multiple-comparisons-across-benchmarks).
4. **What else could produce this number?** Confounding, composition shift, regression to the mean, survivorship, an instrumentation change. Name the alternatives before attributing the movement to the intended cause. See [confounding-and-trends.md](references/confounding-and-trends.md#the-three-question-trend-audit).
5. **What is the noise floor?** A change smaller than the metric's own standard deviation has not been observed, whatever the point estimate says. See [tolerance-bands.md](references/tolerance-bands.md#building-the-error-model).

## Choosing the Instrument

| The question | Instrument | Where |
|---|---|---|
| How many items or runs do I need? | Power calculation, solved for `n` | [power-and-sample-size.md](references/power-and-sample-size.md#worked-unpaired-comparison-of-two-systems) |
| What could I detect with the budget I have? | MDE, solved for `delta` | [power-and-sample-size.md](references/power-and-sample-size.md#worked-inverting-the-question-at-a-fixed-budget) |
| Is system B better than system A on the same suite? | Paired difference interval; McNemar for binary outcomes | [eval-inference.md](references/eval-inference.md#comparing-two-systems) |
| Is this `pass@k` number precise enough to compare? | Cluster bootstrap over tasks | [eval-inference.md](references/eval-inference.md#bootstrap-intervals-on-passk) |
| I ran 12 benchmarks and 3 improved | Holm (FWER) or Benjamini-Hochberg (FDR) | [eval-inference.md](references/eval-inference.md#multiple-comparisons-across-benchmarks) |
| Can I trust this LLM judge's scores? | Chance-corrected agreement with a bootstrap interval | [eval-inference.md](references/eval-inference.md#judge-agreement-statistics) |
| How unstable is the agent run to run? | Between/within variance decomposition, ICC | [eval-inference.md](references/eval-inference.md#non-determinism-variance) |
| Coverage rose and defects rose; did quality drop? | Stratify, then standardise | [confounding-and-trends.md](references/confounding-and-trends.md#simpsons-paradox-worked) |
| Did the intervention cause the trend? | Difference-in-differences or interrupted time series | [confounding-and-trends.md](references/confounding-and-trends.md#adjustment-toolkit) |
| How wide should this gate's tolerance be? | Error model, combined in quadrature | [tolerance-bands.md](references/tolerance-bands.md#worked-derivation) |
| Can I stop the eval early? | Truncated SPRT, or a group-sequential boundary | [sequential-testing.md](references/sequential-testing.md#sprt-mechanics) |

## Estimation Over Testing

Prefer reporting an effect size with an interval to reporting a binary verdict. Three reasons, in ascending order of practical consequence:

- **An interval answers more questions than a verdict.** It shows the magnitude, the precision, and what the data rules out — including, crucially, whether a null result rules out anything worth caring about.
- **Estimation is robust to the multiplicity problem.** Reporting twelve effect sizes with intervals and drawing no binary conclusions needs no correction, because no rejection decisions were made. (The discipline only holds if you then refrain from narrating the largest one as significant.)
- **Thresholds hide the decision.** "p less than 0.05" conceals whether the effect is large enough to act on. A decision needs the magnitude and its uncertainty; the binary verdict is at best a summary of them and at worst a substitute.

Reserve hypothesis tests for genuine gates, where a binary output is the actual product: does this PR merge, does this model ship, does this alarm fire.

## Reading Someone Else's Claim

The interrogation checklist for an existing statistical or metric claim — a benchmark comparison, a trend report, an acceptance threshold, a "significant improvement." Each item names what to look for and what its absence implies.

| Check | Absence implies |
|---|---|
| Is the sample size justified against a declared effect size? | The design cannot support a null result, and may not support a positive one |
| Is the unit of independence stated and consistent with the analysis? | Intervals are probably too narrow |
| Was the comparison family declared before results were seen? | The reported win may be a selection over unreported comparisons |
| Is the comparison paired where pairing was available? | The result is far less precise than it could have been, likely underpowered |
| Does the aggregate survive stratification on the obvious confounder? | The claim may be about population mix, not the intervention |
| Is the movement larger than the metric's run-to-run spread? | The change has not been observed, only estimated |
| Does a threshold or tolerance band come with a derivation? | It is asserted; its false-alarm and blind-spot rates are both unknown |
| Was the stopping rule fixed before the first look? | The error rate is not the nominal one |
| Does the causal language match the design's strength? | The conclusion overstates what the data licenses |

Two disciplines make this checklist useful rather than obstructive. First, **name the specific decision each objection would change** — an objection that changes no decision is not worth raising. Second, **name the settling test** — the additional measurement, stratification, or interval that would resolve the point either way. A statistical objection without a settling test is an opinion.

## Related Skills

- **[agent-evals](../agent-evals/SKILL.md)** -- eval suite design, `pass@k` and `pass^k` as metric definitions, trial-count conventions, judge-calibration protocol as a pipeline gate. This skill supplies the inference those metrics need; agent-evals owns the metrics and the gate.
- **[performance-architecture](../performance-architecture/SKILL.md)** -- performance measurement and load testing; its `benchmarking.md` owns microbenchmark measurement mechanics (see Content boundary above).
- **[llm-training-eval](../llm-training-eval/SKILL.md)** -- metric-threshold and tolerance-band *syntax* for acceptance criteria; this skill derives the width that goes into it.
- **[experiment-tracking](../experiment-tracking/SKILL.md)** -- recording runs, configurations, and results so that a comparison is reconstructible.
- **[testing-strategy](../testing-strategy/SKILL.md)** -- property-based testing and coverage philosophy, the deterministic counterpart to statistical evaluation.
- **[observability](../observability/SKILL.md)** -- production metric collection, where the trend claims this skill audits usually originate.
