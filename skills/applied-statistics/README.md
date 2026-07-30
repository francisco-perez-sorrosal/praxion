# Applied Statistics

Design and inference for decisions made from data: how much data a decision needs, what a number licenses you to claim, and where an aggregate can be arithmetically correct and directionally wrong.

The skill covers the pre-collection half of statistics (power, sample size, stopping rules) and inference for evaluations (multiplicity, interval estimation, agreement, confounding, derived thresholds). Microbenchmark measurement mechanics are a separate, adjacent concern owned by `performance-architecture/references/benchmarking.md`.

## When to Use

- Claiming an effect is significant, or that a metric improved
- Sizing a sample, an eval set, or a number of runs before collecting data
- Comparing systems across multiple benchmarks
- Putting a confidence interval on `pass@k` or another eval metric
- Deciding whether an LLM judge's scores can be trusted to gate anything
- Attributing a churn, coverage, complexity, or latency trend to a cause
- Choosing the width of a PASS/WARN/FAIL tolerance band
- Deciding when to stop collecting data

## Activation

Activates when statistical vocabulary appears in the task: significance, power, sample size, confidence interval, effect size, variance, correction, agreement, tolerance band, stopping rule, confounding.

Trigger explicitly by mentioning "applied-statistics skill" or referencing it by name. It is also the discipline binding consulted when a statistician perspective is convened on a design or a claim.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Content boundary, gotchas, the five pre-claim questions, instrument-selection table, the checklist for auditing someone else's claim |
| `references/power-and-sample-size.md` | Pre-collection planning: MDE selection, paired vs unpaired sample size, design effect, budget allocation |
| `references/eval-inference.md` | Multiple comparisons, bootstrap intervals on `pass@k`, paired comparison, judge agreement, non-determinism variance |
| `references/confounding-and-trends.md` | Simpson's paradox worked, confounder catalogue, adjustment methods, claim-strength language |
| `references/tolerance-bands.md` | Deriving a band width from an error model; floor-and-ceiling constraints |
| `references/sequential-testing.md` | Peeking inflation, group-sequential and anytime-valid designs, Wald SPRT worked example, calibration as the real object |
| `README.md` | This file -- overview and usage guide |

## Related Skills

- [`agent-evals`](../agent-evals/SKILL.md) -- eval suite design and metric definitions; this skill supplies the inference
- [`performance-architecture`](../performance-architecture/SKILL.md) -- microbenchmark measurement mechanics
- [`llm-training-eval`](../llm-training-eval/SKILL.md) -- tolerance-band syntax for acceptance criteria
- [`experiment-tracking`](../experiment-tracking/SKILL.md) -- making a comparison reconstructible
- [`testing-strategy`](../testing-strategy/SKILL.md) -- the deterministic counterpart to statistical evaluation
