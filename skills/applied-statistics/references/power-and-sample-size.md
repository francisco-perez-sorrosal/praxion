# Power and Sample Size — Planning Before Collection

How many runs, items, or observations are needed to detect an effect worth acting on. Reference material for the [Applied Statistics](../SKILL.md) skill.

**This file answers the question asked *before* data exists.** Everything here is a design decision. Once the data is collected, the answers below are fixed and no analysis can recover the power that was never bought.

## Contents

- [The retrospective-power trap](#the-retrospective-power-trap)
- [Four quantities, fix three](#four-quantities-fix-three)
- [Choosing the effect size honestly](#choosing-the-effect-size-honestly)
- [Worked: unpaired comparison of two systems](#worked-unpaired-comparison-of-two-systems)
- [Worked: inverting the question at a fixed budget](#worked-inverting-the-question-at-a-fixed-budget)
- [Pairing is the cheapest power you will ever buy](#pairing-is-the-cheapest-power-you-will-ever-buy)
- [Repeated trials are not independent observations](#repeated-trials-are-not-independent-observations)
- [Allocating a fixed budget between tasks and trials](#allocating-a-fixed-budget-between-tasks-and-trials)
- [Estimating variance before you have data](#estimating-variance-before-you-have-data)
- [When the budget cannot reach the MDE](#when-the-budget-cannot-reach-the-mde)
- [Reporting template](#reporting-template)
- [Gotchas](#gotchas)

## The retrospective-power trap

After a null result, the reflex is to compute power from the *observed* effect. This is uninformative: observed power is a monotone transformation of the p-value, so it adds no evidence the p-value did not already carry. A large p-value always yields low observed power, by construction.

The two questions that *are* informative after a null result:

1. **What does the confidence interval exclude?** An interval of `[-1pp, +2pp]` rules out anything worth shipping. An interval of `[-9pp, +11pp]` rules out nothing — that run was an expensive way to learn nothing.
2. **Was the design powered for the smallest effect worth acting on?** This is answerable only if the effect was declared *before* collection. Declare it.

For "is the new version *not worse*," use an equivalence test (two one-sided tests) against a declared non-inferiority margin. A non-significant difference test is not evidence of equivalence.

## Four quantities, fix three

| Quantity | Symbol | Typical choice | Meaning |
|---|---|---|---|
| Significance level | `alpha` | 0.05 | Tolerated false-positive rate (claiming an effect that is not there) |
| Power | `1 - beta` | 0.80, or 0.90 for gates | Probability of detecting a real effect of the declared size |
| Effect size | `delta` | Declared, not hoped-for | The smallest difference worth acting on (the MDE) |
| Sample size | `n` | Solved for | Items, tasks, or runs |

Fix any three; the fourth is determined. Two of the three planning modes matter in practice:

- **Solve for `n`** when the budget is negotiable. "What do I need to buy?"
- **Solve for `delta`** when the budget is fixed. "Given 200 items, what is the smallest difference I could reliably see?" This is the MDE, and it is the honest way to state what a fixed-budget experiment can and cannot conclude.

Both use `z_{1-alpha/2} + z_{1-beta}`. At `alpha = 0.05` (two-sided) and power 0.80 this is `1.96 + 0.84 = 2.80`, so `(z_{1-alpha/2} + z_{1-beta})^2 = 7.85`. At power 0.90 it is `1.96 + 1.28 = 3.24`, squared `10.51` — a third more data for the extra 10 points of power.

## Choosing the effect size honestly

The most common design failure is powering for the effect you *hope* to see rather than the smallest one worth acting on. Three defensible ways to set the MDE:

- **Decision cost.** What improvement justifies the migration, the latency regression, or the token spend? If a 1pp accuracy gain does not pay for a 2x cost increase, do not power for 1pp — power for the break-even delta.
- **Historical deltas.** Look at the size of previous accepted changes on the same metric. If shipped improvements have historically been 2-4pp, powering for 0.5pp designs an experiment that will spend its budget on noise.
- **Instrument floor.** The MDE cannot be smaller than the measurement's own noise. See [tolerance-bands.md](tolerance-bands.md) — an MDE below the derived band width is undetectable regardless of sample size at the *run* level, because the run-to-run variance component does not shrink with more items.

## Worked: unpaired comparison of two systems

Two systems evaluated on **different** item samples. Per-arm sample size for a two-proportion comparison:

```text
n_per_arm = (z_{1-alpha/2} + z_{1-beta})^2 * [ p1*(1-p1) + p2*(1-p2) ] / (p1 - p2)^2
```

Detecting a 5-point lift from 70% to 75%, at `alpha = 0.05` and power 0.80:

```text
variance term = 0.70*0.30 + 0.75*0.25 = 0.2100 + 0.1875 = 0.3975
delta^2       = 0.05^2 = 0.0025
n_per_arm     = 7.85 * 0.3975 / 0.0025 = 1248
```

**About 1,250 items per arm — 2,500 total.** Most eval suites are one to two orders of magnitude smaller than this. That is the single most useful number in this file: a 5-point improvement on a 200-item benchmark is not measurable as an unpaired comparison, and reporting it as "an improvement" is a claim the data cannot support.

## Worked: inverting the question at a fixed budget

Given `n` per arm, the smallest detectable difference (around a common rate `p`):

```text
MDE = (z_{1-alpha/2} + z_{1-beta}) * sqrt( 2*p*(1-p) / n )
```

With `n = 200` per arm at `p = 0.70`:

```text
sqrt(2 * 0.21 / 200) = sqrt(0.0021) = 0.0458
MDE = 2.80 * 0.0458 = 0.128
```

**About 12.8 percentage points.** A 200-item-per-arm suite can reliably detect "70% to 83%" and nothing finer. State this in the plan, before running, so a 3-point observed delta is read as noise rather than as a result.

## Pairing is the cheapest power you will ever buy

When both systems can be run on the **same items**, the design becomes paired and the cost driver changes: what matters is no longer the accuracy level but the **discordance rate** — the fraction of items where the two systems disagree. Items both get right, or both get wrong, carry no information about which is better.

For a paired binary comparison (McNemar), with `d = p10 - p01` the net discordance in favour of the better system and `psi = p10 + p01` the total discordance rate:

```text
n_pairs ~= (z_{1-alpha/2} + z_{1-beta})^2 * psi / d^2
```

Same 5-point net improvement, with 15% of items discordant:

```text
n_pairs = 7.85 * 0.15 / 0.0025 = 471
```

**471 paired items versus 2,500 unpaired** — roughly a fivefold reduction in total labelled items for the same power. Pair whenever the design allows it: same eval set, same task list, same seeds, same prompts. The only cost is bookkeeping (retain per-item outcomes, not just the aggregate score), and that bookkeeping is also what the paired bootstrap in [eval-inference.md](eval-inference.md) requires.

Note the direction of the surprise: highly *similar* systems have low discordance and therefore need *more* items, not fewer. Two near-identical model versions are the expensive comparison.

## Repeated trials are not independent observations

Running `k` trials per task on `n` tasks yields `n*k` measurements but **not** `n*k` independent observations. Outcomes within a task are correlated — a task that is hard is hard on every trial. Quantify with the intraclass correlation `rho` and the design effect:

```text
DEFF  = 1 + (k - 1) * rho
n_eff = n * k / DEFF
```

100 tasks, 5 trials each, `rho = 0.6`:

```text
DEFF  = 1 + 4 * 0.6 = 3.4
n_eff = 500 / 3.4 = 147
```

Five hundred runs bought the statistical power of 147 independent items — a 47% gain over the 100 tasks alone, for 5x the compute. As `rho` approaches 1 (task difficulty dominates, trials agree), `n_eff` approaches `n`: extra trials buy nothing for *between-system comparison*. They still buy something else — a measurement of within-task variance, which is what the run-to-run component of a derived tolerance band needs. Know which of the two you are paying for.

## Allocating a fixed budget between tasks and trials

When adding a task costs `c_task` (authoring, labelling, review) and an extra trial on an existing task costs `c_trial` (compute only), the variance-minimising trial count is:

```text
k* = sqrt( (1 - rho) / rho * (c_task / c_trial) )
```

High `rho` and cheap tasks push toward `k* = 1` (more tasks, one trial each). Low `rho` and expensive labelling push toward more trials per task. In agent evals the usual regime is high `rho` with expensive task authoring, which drives `k*` to a small single-digit value — enough to characterise within-task variance, not so many that the budget is spent re-measuring the same hard items. The concrete trial-count default is the [agent-evals](../../agent-evals/SKILL.md) skill's to set; what this formula adds is *why* it is small, and the conditions under which it should not be.

## Estimating variance before you have data

Planning needs a variance estimate before collection. Three defensible sources, in order of preference:

1. **A pilot run.** 20-40 items is usually enough for a usable `rho` and `psi` estimate. Treat pilot point estimates as rough — inflate the resulting `n` by 15-25% to absorb their own uncertainty.
2. **A comparable prior run** on the same suite, same metric family.
3. **The conservative bound.** For a proportion, `p*(1-p)` is maximised at `p = 0.5` (value 0.25). Using 0.25 guarantees the design is not underpowered, at the cost of over-buying when the true rate is far from 0.5.

Never plan from the *hoped-for* variance. Under-estimating variance is the failure that produces an experiment which cannot answer its own question.

## When the budget cannot reach the MDE

This is common and it has exactly three honest resolutions. Picking a fourth — running anyway and reporting the point estimate as a finding — is the failure this file exists to prevent.

| Resolution | What it costs | When it is right |
|---|---|---|
| **Raise the MDE** | You can no longer claim small effects | The decision genuinely only cares about large effects |
| **Cut the variance** | Design work: pair the comparison, stratify, fix seeds across arms, use a paired bootstrap | Almost always worth attempting first — pairing alone is often a 5x saving |
| **Declare it underpowered** | You report a direction and an interval, not a conclusion | The comparison is exploratory or the budget is genuinely fixed |

The third is a legitimate outcome. Reporting "the point estimate favours B by 3pp; the 95% interval is [-6pp, +12pp]; this design could only have detected 13pp" is more useful, and more honest, than a bare "B is better."

## Reporting template

Record these before collection, in the plan or the acceptance criteria:

```text
Comparison:      system A vs system B on suite S
Design:          paired (same items, same seeds) | unpaired
Metric:          exact-match accuracy
alpha:           0.05, two-sided
Power:           0.80
MDE:             4pp absolute (break-even for the added latency)
Variance source: pilot run, 30 items, discordance 0.15
Planned n:       600 items, 3 trials each
Multiplicity:    1 primary comparison; 4 secondary (BH at q=0.10)
Stopping rule:   fixed-n, no interim looks
```

The `Multiplicity` and `Stopping rule` lines are not decoration — they are the pre-commitments that make the later analysis valid. See [eval-inference.md](eval-inference.md) and [sequential-testing.md](sequential-testing.md).

## Gotchas

| Gotcha | Why it misleads | What to do |
|---|---|---|
| Powering for the hoped-for effect | Produces an experiment that only "works" if the change is a blowout | Power for the smallest effect worth acting on |
| Computing power after a null result | Observed power is a restatement of the p-value | Report the interval; compare it against the MDE |
| Counting `n*k` runs as `n*k` observations | Ignores within-task correlation; inflates apparent precision | Apply the design effect; report `n_eff` |
| Treating a non-significant difference as equivalence | Absence of evidence, not evidence of absence | Run an equivalence test against a declared margin |
| Unpaired analysis of a paired design | Discards the item-level pairing; needs roughly 5x the data | Retain per-item outcomes; analyse the paired difference |
| Planning from the observed rate of the *better* arm | Optimistic variance, undersized experiment | Use the pooled or conservative variance |
| Adding items after peeking at the result | Turns a fixed-n test into an uncontrolled sequential one | Fix `n` up front, or adopt a sequential design deliberately |
