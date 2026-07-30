# Confounding and Metric Trends — When an Aggregate Lies

Why churn, complexity, coverage, latency, and pass-rate trends reverse under stratification, and what to do before attributing a movement to a cause. Reference material for the [Applied Statistics](../SKILL.md) skill.

**The claim shape this file governs:** *"Metric X moved after we did Y, therefore Y worked."* Every element of that sentence can be true while the conclusion is false.

## Contents

- [Simpson's paradox, worked](#simpsons-paradox-worked)
- [Why this happens constantly in engineering metrics](#why-this-happens-constantly-in-engineering-metrics)
- [The confounder catalogue](#the-confounder-catalogue)
- [Adjustment toolkit](#adjustment-toolkit)
- [The three-question trend audit](#the-three-question-trend-audit)
- [Language discipline](#language-discipline)
- [Gotchas](#gotchas)

## Simpson's paradox, worked

A new lint rule was rolled out. The question: does it reduce defects?

**Aggregate view:**

| Group | Files | Defects | Rate |
|---|---|---|---|
| Lint rule applied | 1,000 | 94 | **9.4%** |
| Not applied | 1,000 | 57 | **5.7%** |

The rule appears to *increase* defect density by 3.7 percentage points. Now stratify by module age — the rule was rolled out to legacy modules first:

| Stratum | Group | Files | Defects | Rate |
|---|---|---|---|---|
| Legacy | Applied | 900 | 90 | **10.0%** |
| Legacy | Not applied | 100 | 12 | **12.0%** |
| New | Applied | 100 | 4 | **4.0%** |
| New | Not applied | 900 | 45 | **5.0%** |

**The rule wins in every stratum and loses in the aggregate.** This is not a rounding artifact or a small-sample fluke — it is exact arithmetic, and it is the normal behaviour of ratios pooled across groups with different base rates and different exposure mixes.

Standardising to an equal mix of legacy and new files reverses the aggregate:

```text
adjusted rate, applied     = (10.0% + 4.0%) / 2 = 7.0%
adjusted rate, not applied = (12.0% + 5.0%) / 2 = 8.5%
```

The confounder is **module age**: legacy files are both more defect-prone *and* more likely to have received the rule. The aggregate compares a mostly-legacy treated group against a mostly-new untreated group, so it is measuring module age, not the lint rule.

**The generalisable point is not "beware Simpson's paradox."** It is that an unadjusted aggregate answers a question about the *population mix*, and a decision about an intervention needs a question about the *intervention*. When exposure is not randomly assigned — and in engineering it never is — those are different questions, and the aggregate can point the wrong way, not merely be imprecise.

## Why this happens constantly in engineering metrics

Engineering rollouts are systematically non-random in exactly the way that generates reversals:

- Tooling lands on the **worst modules first** (that is why it was built).
- Coverage rises fastest where tests are **cheapest to write**, which is where defects are rarest.
- Refactors target **high-churn files**, which are high-churn because they are actively developed, which is also why they carry more defects.
- Agent evaluations add **easy tasks** faster than hard ones, because easy tasks are cheaper to author.

In every case the treated and untreated populations differ on a variable that also drives the outcome. That is the definition of a confounder, and it is the default condition rather than the exception.

## The confounder catalogue

Named failure modes, each with the shape of claim it corrupts.

| Mechanism | How it fakes a result | Typical tell |
|---|---|---|
| **Confounding by indication** | The intervention was targeted at the worst cases | Treated group's *pre*-intervention level differs from control's |
| **Composition / mix shift** | The population changed, not the behaviour | Metric moves with no per-stratum movement; denominators shift |
| **Regression to the mean** | A group selected for an extreme value improves regardless | Selection criterion is itself the metric ("we targeted the top-10 churn files") |
| **Survivorship** | Failures leave the denominator | Deleted files, abandoned runs, timed-out tasks excluded from the sample |
| **Autocorrelation** | Consecutive weeks are not independent samples | A trend test over 12 weekly points treated as `n = 12` |
| **Seasonality / release cadence** | Periodic structure read as trend | Movement aligns with sprint boundaries, freezes, or release weeks |
| **Left truncation** | The window starts at a peak | Start date chosen after seeing the data |
| **Goodhart** | The metric was optimised without the underlying property improving | Metric moves; correlated metrics do not |
| **Instrumentation change** | The measurement changed, not the system | Discontinuity at a tooling upgrade or definition change |
| **Denominator drift** | Rate moves because the base moved | Numerator flat, rate moving |

Regression to the mean deserves special emphasis because it is invisible in the write-up: if a cohort is selected *because* it scored badly, part of any subsequent improvement is guaranteed by the selection alone. Without an equally-extreme untreated control, the intervention's effect and the selection artifact are not separable.

## Adjustment toolkit

Ordered by strength of the causal claim each can support.

| Method | What it needs | What it buys |
|---|---|---|
| **Randomisation** | Ability to assign the intervention | Removes confounding by construction. Feasible more often than assumed: alternate files, teams, or eval items |
| **Stratification / standardisation** | The confounder measured and few-valued | Compares like with like; reports a mix-adjusted aggregate (as above) |
| **Difference-in-differences** | Pre and post measurements for both groups | Cancels time-invariant group differences; needs the parallel-trends assumption to hold pre-intervention, which is checkable |
| **Interrupted time series** | A long enough pre-period | Separates level shift from pre-existing slope; handles autocorrelation explicitly |
| **Matched controls** | A pool of comparable untreated units | Approximates stratification on several variables at once |
| **Negative control** | An outcome the intervention should *not* affect | If the "unaffected" metric moves too, the effect is an artifact of something else |

The negative control is the cheapest and most under-used. If a lint rule appears to cut defects, check a defect class it cannot possibly touch. Movement there indicts the measurement, not the rule.

**Stratify on the variable that determined exposure.** Adjusting for something unrelated to assignment adds noise without removing bias; the question to answer first is always *"why did this unit get the treatment and that one not?"*

## The three-question trend audit

Ask these of any metric-trend claim, including your own, before it is reported.

1. **Who got the treatment, and why them?** If exposure correlates with anything that also drives the outcome, the unadjusted comparison is measuring that thing. Name the selection mechanism explicitly; "it rolled out gradually" is a selection mechanism.
2. **Does the aggregate survive stratification?** Split on the one or two most plausible confounders and check each stratum. If the direction flips or dissolves, the aggregate was mix. If the strata are too small to read, that is the finding — the data cannot resolve the question.
3. **What else changed in the same window?** Team size, refactors, framework upgrades, holiday periods, definition changes, model-version rollouts, sampling changes. List them before attributing. A concurrent instrumentation change is fatal and is the easiest to miss because it leaves no trace in the metric itself.

A fourth question when the movement is small: **is it larger than the metric's own noise?** A weekly metric that varies 8% week to week has not "improved 5%." See [tolerance-bands.md](tolerance-bands.md).

## Language discipline

The strength of the claim must match the strength of the design. Misstating this is the most common way a correct analysis becomes a wrong conclusion downstream, because the caveat is dropped and the causal reading survives.

| Design | Strongest defensible phrasing |
|---|---|
| Randomised assignment | "Y caused a `d` change in X (95% CI ...)" |
| Difference-in-differences with checked parallel trends | "X changed by `d` more in the treated group; consistent with an effect of Y, assuming no concurrent group-specific change" |
| Stratified observational comparison | "X differs by `d` after adjusting for Z; other confounders remain possible" |
| Unadjusted before/after | "X moved by `d` over the window. Attribution is not supported by this design." |

The last row is a legitimate and frequently correct thing to report. State the movement, name the candidate explanations, and say which additional data would separate them. That is more useful than an unsupported causal claim, and it survives review.

## Gotchas

| Gotcha | Why it misleads | What to do |
|---|---|---|
| Reading an unadjusted aggregate as an intervention effect | Compares differently-composed populations | Stratify on the exposure-determining variable |
| Selecting the worst cohort, then celebrating improvement | Regression to the mean guarantees some of it | Use an equally-extreme untreated control |
| Trend test over N weekly points as `N` independent samples | Autocorrelation inflates confidence | Model the serial correlation, or compare distinct pre/post blocks |
| Choosing the window start after seeing the series | The start point is a free parameter | Fix the window before looking; report sensitivity to it |
| Rate movement with a flat numerator | The denominator moved | Always plot numerator and denominator separately |
| Adjusting for a variable that had no role in assignment | Adds variance without removing bias | Adjust for what determined exposure |
| Excluding failed, deleted, or timed-out units | Survivorship inflates the surviving population's quality | Define the denominator before collection and keep it fixed |
| One metric moving in isolation | Consistent with Goodhart or an instrumentation change | Check a correlated metric and a negative control |
