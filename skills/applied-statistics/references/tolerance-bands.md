# Derived Tolerance Bands — Thresholds With an Error Model Behind Them

How to compute the width of a PASS/WARN/FAIL band from the noise it has to absorb, instead of picking a round number. Reference material for the [Applied Statistics](../SKILL.md) skill.

**Boundary:** the *syntax* of a threshold-with-tolerance criterion and its PASS/WARN/FAIL classification rules belong to the [llm-training-eval](../../llm-training-eval/SKILL.md) skill and the eval-driven-verification conventions. This file supplies the number that goes into the `+/-` slot, and the argument for why that number and not another.

## Contents

- [Three provenances for a band](#three-provenances-for-a-band)
- [Building the error model](#building-the-error-model)
- [Worked derivation](#worked-derivation)
- [The floor and the ceiling](#the-floor-and-the-ceiling)
- [When floor exceeds ceiling](#when-floor-exceeds-ceiling)
- [Asymmetric bands for gates](#asymmetric-bands-for-gates)
- [Recompute triggers](#recompute-triggers)
- [Reporting a derived band](#reporting-a-derived-band)
- [Gotchas](#gotchas)

## Three provenances for a band

| Provenance | How the width was obtained | Failure mode |
|---|---|---|
| **Asserted** | Someone picked a round number that felt right | Uncorrelated with the metric's actual noise — fires constantly or never |
| **Measured** | Empirical spread observed in one batch of runs | Captures only the variance sources active *during that batch*; silently omits the rest |
| **Derived** | Computed from an explicit model of every noise source, then checked against the decision it gates | Wrong if a noise source was omitted — but the omission is visible and arguable |

Only the derived band can be defended, adjusted, or refuted, because only it exposes its assumptions. "We use plus or minus 2%" is unfalsifiable; "we use plus or minus 4.6pp because sampling error at n=400 contributes 2.2pp and run-to-run variance contributes 0.8pp, combined to 2.3pp, doubled for a 4.6% false-alarm rate" can be checked line by line and challenged at any line.

A measured band is a useful *input* to a derived one — it is how the run-to-run term gets its number — but a measured spread presented as the band assumes the batch exercised every source of variation that production will. It usually did not: same hardware, same day, same model version, same eval snapshot.

## Building the error model

Enumerate the sources, quantify each as a standard deviation on the metric's own scale, then combine.

| Source | Where it comes from | How to quantify |
|---|---|---|
| **Sampling error** | The eval set is a finite sample of the task population | For a proportion: `sd = sqrt(p*(1-p)/n)`. For a mean: `sd = s/sqrt(n)` |
| **Run-to-run variance** | Non-determinism, batching, tool ordering, scheduling | Standard deviation across `k` repeat runs on an identical configuration |
| **Instrument / grader error** | An imperfect judge or a noisy measurement pipeline | Grader disagreement rate translated to metric scale; see [eval-inference.md](eval-inference.md#judge-agreement-statistics) |
| **Environment drift** | Provider-side model updates, dependency upgrades, hardware pools | Spread across runs separated in time or across environments |

For independent sources, combine in quadrature:

```text
sd_total = sqrt( sd_sampling^2 + sd_run^2 + sd_grader^2 + sd_env^2 )
```

Quadrature has a practical consequence worth internalising: **the largest term dominates and the small ones nearly vanish.** A 2.2pp source combined with a 0.8pp source yields 2.3pp — the smaller term added 0.1pp. Spend effort measuring and shrinking the biggest contributor; do not agonise over terms an order of magnitude below it.

If a metric is a ratio or product of measured quantities, combine *relative* standard deviations in quadrature instead of absolute ones.

## Worked derivation

A gate on exact-match accuracy for an agent eval suite. Observed accuracy is around 75% on 400 items, and five repeat runs of an unchanged system showed a standard deviation of 0.8pp.

```text
Sampling error
  per-item sd  = sqrt(0.75 * 0.25) = 0.4330
  sd_sampling  = 0.4330 / sqrt(400) = 0.02165        (2.17pp)

Run-to-run
  sd_run       = 0.008                                (0.80pp)

Combined
  sd_total     = sqrt(0.02165^2 + 0.008^2)
               = sqrt(0.00046872 + 0.000064)
               = 0.02308                              (2.31pp)

Band at 2 sd  = +/- 4.6pp   (two-sided false-alarm rate ~4.6%)
Band at 3 sd  = +/- 6.9pp   (two-sided false-alarm rate ~0.3%)
```

**Now test a plausible asserted band against this model.** Suppose the criterion had been written as `accuracy >= 0.75 +/- 0.02` — a natural-looking 2pp tolerance:

```text
z = 0.02 / 0.02308 = 0.87
P(|Z| > 0.87) = 0.39
```

**An unchanged system would trip that band on roughly two runs in five.** The gate would be treated as flaky within a week and then ignored — which is worse than no gate, because the ignored gate still consumes CI time and still suppresses attention when it eventually fires for a real reason.

The derivation took four lines of arithmetic and it changed the gate from unusable to usable.

## The floor and the ceiling

A band is constrained from both directions, and the two constraints come from different places.

```text
FLOOR    band >= z * sd_total          (from the error model; z set by the tolerated false-alarm rate)
CEILING  band <= smallest regression worth catching   (from the decision)
```

- **Below the floor**, the band fires on noise. Every false alarm spends attention and erodes the gate's credibility.
- **Above the ceiling**, the band is blind to regressions that matter. The gate is green while the system degrades.

Both numbers must appear in the justification. A band stated without its floor cannot be checked for flakiness; a band stated without its ceiling cannot be checked for blindness.

Choosing `z`: 2 gives a two-sided false-alarm rate of about 4.6% (roughly 1 run in 22); 3 gives about 0.3% (1 in 370). On a gate that runs on every PR, `z = 2` means a false alarm every few weeks — often the right trade, but decide it deliberately. Note that the false-alarm rate compounds across independent gates exactly as multiple comparisons do (see [eval-inference.md](eval-inference.md#multiple-comparisons-across-benchmarks)): twenty 2-sigma gates produce roughly one false alarm per full CI run.

## When floor exceeds ceiling

Continuing the worked example: suppose the smallest regression worth catching is 2pp, but the floor is 4.6pp. **There is no valid band.** The instrument cannot support the decision, and no choice of number fixes that — anything in between is simultaneously flaky and blind.

Four honest resolutions, in rough order of cost:

1. **Increase `n`.** Sampling error falls as `1/sqrt(n)`, so shrinking 2.17pp to 0.6pp needs about 5,200 items — a 13x increase for a 3.6x reduction. Quadrature is expensive at the margin.
2. **Reduce run-to-run variance.** Pin versions, isolate the environment, average over more repeat runs. Averaging `k` runs divides the run-to-run term by `sqrt(k)`, leaving sampling error untouched.
3. **Change the comparison to a paired one.** Comparing against a baseline *on the same items in the same run* cancels most sampling error, and the paired difference has a much smaller standard deviation than either absolute level. This is usually the cheapest real fix.
4. **Accept a larger MDE for this gate** and catch smaller regressions by a different mechanism (trend monitoring across many runs, a canary suite, targeted tests).

**The irreducible floor.** In the worked example, `sd_run = 0.8pp` does not shrink with more items. Even with an infinite eval set, `sd_total >= 0.8pp` and a 2-sigma band cannot go below 1.6pp. Any request for a tighter band than that is a request to reduce run-to-run variance, not to add data — and knowing which lever applies is the entire value of decomposing the error model.

## Asymmetric bands for gates

A two-sided band treats over-performance and under-performance symmetrically. A gate usually should not.

- **For a regression gate**, only the downside matters. Use a one-sided band and spend the full `alpha` there: a one-sided `z = 1.645` for a 5% false-alarm rate is tighter than the two-sided `z = 1.96` at the same rate.
- **The asymmetric cost argument.** A false PASS ships a regression; a false FAIL costs an investigation. When those costs differ by an order of magnitude, the band should sit where the expected cost is minimised, not where the false-alarm rate is symmetric. Say which error the band is tuned to bound.
- **A WARN zone is the honest expression of the gap between floor and ceiling.** When the floor is 4.6pp and the ceiling is 2pp, a `FAIL` beyond 4.6pp and a `WARN` between 2pp and 4.6pp encodes exactly what the instrument knows: below 2pp, indistinguishable from noise; above 4.6pp, real; in between, needs a second look. That is more truthful than forcing a binary at either end.

## Recompute triggers

A derived band is valid for the configuration it was derived from. Recompute when any input changes:

- **`n` changes** — the sampling term moves as `1/sqrt(n)`. Adding items to a suite silently tightens the achievable band; failing to re-derive leaves a band that is now too loose.
- **The metric definition changes** — a different scale means a different band.
- **The model, provider, or hardware changes** — the run-to-run term is configuration-specific.
- **The grader changes** — a new judge or rubric changes the instrument-error term.
- **The observed rate moves far from the derivation point** — `p*(1-p)` is maximised at `p = 0.5`, so a band derived at 75% is too tight at 50% and unnecessarily loose at 95%.

Record the derivation inputs alongside the band so the recompute is mechanical rather than archaeological.

## Reporting a derived band

```text
Metric:            exact-match accuracy, agent eval suite
Band:              -4.6pp (one-sided regression gate), WARN from -2.0pp
Derivation:
  sd_sampling      2.17pp   (n = 400, p ~ 0.75)
  sd_run           0.80pp   (5 repeat runs, unchanged system)
  sd_total         2.31pp   (quadrature)
  z                2.0      -> ~2.3% one-sided false-alarm rate
Ceiling:           2.0pp    (smallest regression worth catching)
Floor > ceiling:   yes -> WARN zone spans 2.0pp to 4.6pp
Recompute when:    n changes, model/provider changes, grader changes
```

Nine lines, and every number in the criterion is now traceable to an assumption someone can argue with.

## Gotchas

| Gotcha | Why it misleads | What to do |
|---|---|---|
| A round-number band with no derivation | Uncorrelated with the metric's noise | Derive from the error model; show the terms |
| Band narrower than `sd_total` | Fires on unchanged systems; gate gets ignored | Check the floor before adopting the band |
| Band wider than the regression worth catching | Green while the system degrades | Check the ceiling too; state both |
| Empirical spread from one batch used as the band | Omits sources not active in that batch | Treat it as one term, not the total |
| Adding noise terms linearly | Overstates total; independent sources add in quadrature | `sqrt(sum of squares)` |
| Assuming more data always tightens the band | Run-to-run variance does not shrink with `n` | Identify the irreducible floor first |
| Reusing a band after changing `n`, model, or grader | Derivation inputs no longer hold | Record inputs; recompute on the listed triggers |
| Symmetric band on an asymmetric decision | Spends false-alarm budget on the harmless side | One-sided band for a regression gate |
| Many independent 2-sigma gates in one pipeline | False alarms compound like multiple comparisons | Budget the pipeline-level false-alarm rate, not the per-gate one |
