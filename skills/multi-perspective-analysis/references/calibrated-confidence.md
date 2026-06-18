# Calibrated Confidence Schema

Single source of truth for the verbal+numeric confidence anchor table used across the Praxion pipeline. Back to [SKILL.md](../SKILL.md).

## Purpose

Verbal probability expressions vary by ~40 percentage points across readers (Sherman Kent 1964; replicated by Dhami 2018). This schema anchors verbal labels to numeric ranges so that a claim annotated `[certainty: high]` by a researcher carries the same meaning when read by a verifier weeks later.

**This file defines the schema. Consuming agents cite this file; they do not restate the schema.**

## Confidence Anchor Table

| Verbal label | Numeric range | Meaning |
|---|---|---|
| **high** | > 80% | Strong convergent evidence; few plausible confounders; direct sources available |
| **medium** | 40–80% | Mixed or indirect evidence; plausible alternative explanations exist |
| **low** | < 40% | Sparse, indirect, or conflicting evidence; high uncertainty; treat as provisional |

### Annotation format (per-claim)

```
[certainty: high/med/low — <one-line basis>]
```

Example: `[certainty: med — three sources agree but all derive from the same benchmark suite]`

The basis clause is mandatory. A naked label without a basis clause is a schema violation.

## GRADE-Recast Downgrade Factors

When a researcher or verifier finds that one or more GRADE downgrade factors apply to a claim, the confidence label MUST be lowered by at least one tier (high → med or med → low). Two or more factors warrant lowering two tiers if currently at high, or flagging `[certainty: low — multiple downgrade factors]` if already at medium.

| Factor | Signal | Downgrade trigger |
|---|---|---|
| **Source tier** | Evidence comes from opinion, anecdote, blog, or single vendor white-paper rather than peer-reviewed or multi-source confirmation | Applies to any tier |
| **Inconsistency** | Studies or sources disagree in direction or magnitude | ≥ 2 conflicting sources |
| **Indirectness** | Evidence is from an analogous but non-identical domain (e.g., lab study applied to production setting) | Population, intervention, or outcome differs meaningfully |
| **Imprecision** | Confidence intervals are wide, sample sizes are small, or the claim is inherently qualitative and not measured | Prevents distinguishing medium from high |
| **Publication / reporting bias** | Only positive results visible; failure cases absent; vendor-funded primary sources | Applies whenever the search space is controlled by an interested party |

### Downgrade cascade rule

Downgrade factors are cumulative. Start at the nominal tier, apply each factor in order, and record the final tier. Example:

```
Nominal: high (multiple sources agree)
→ Indirectness applies (all sources are lab benchmarks, not production traces)
→ Drops to: medium
→ Imprecision applies (no error bars, qualitative only)
→ Drops to: low
Final: [certainty: low — indirectness + imprecision]
```

## Authoring Guidance

**Researchers** annotate per-claim within `## Comparative Analysis` and `## Divergence Map`. The annotation rides with the claim into any artifact that quotes it — do not strip it.

**Verifiers** carry a `confidence` field in their structured verdict block using the same three-tier vocabulary: `high (>80%) | medium (40–80%) | low (<40%)`. The verifier applies downgrade factors to the verdict confidence, not to individual claims.

**Systems-architect ADR authors** may use the three-tier labels within a `dissent:` frontmatter field to characterize the strength of evidence for the rival design (e.g., `dissent: "strong: three independent replications confirm the rival approach outperforms on latency"`).

## Relationship to Convergence Signals

Confidence labels are **not** convergence signals for design synthesis (see `design-synthesis.md § Convergence Signals`). Synthesis converges on REQ-ID stability, risk-budget satisfaction, blast-radius bound, and user acceptance — all mechanically checkable. A confidence label is a per-claim annotation; it does not substitute for any of the four mechanical signals and must never be used as a threshold gate in an ADR.

## References

- [`../SKILL.md`](../SKILL.md) — parent skill; activation gate and satellite table.
- `agents/verifier.md` — `confidence` field in structured verdict; cites this schema.
- `agents/researcher.md` — per-claim annotation discipline in `## Comparative Analysis` and `## Divergence Map`; cites this schema.
- Sherman Kent (1964), *Words of Estimative Probability* — original verbal-to-numeric motivation.
- Dhami, M.K. (2018), *On the Importance of Numerical Communication of Human Judgment* — replication establishing ~40-pt spread.
- GRADE Working Group (Guyatt et al., BMJ 2008) — source of the five downgrade factors.
