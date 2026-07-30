# Claim Provenance

Back to [SKILL.md](../SKILL.md).

## Preprint vs Peer-Reviewed Weighting

Peer review is a signal about process, not a guarantee of correctness -- and preprint status is a signal about process, not a disqualification. Treat both as inputs to how much independent replication should be demanded before a claim is treated as established, not as a binary accept/reject gate.

- **Peer-reviewed** means at least one round of independent expert scrutiny caught the more obvious methodological problems. It does not mean the finding replicates, that the effect size is accurately reported, or that the study is well-powered -- peer review checks soundness of method, rarely re-derives the numbers.
- **Preprint** means the claim has not yet cleared that scrutiny. This is common and often unavoidable in fast-moving fields (most current LLM capability research lives on preprint servers well before any journal version appears) -- it is not itself a mark against the work. It does mean: read the methodology section yourself with the scrutiny a reviewer would apply, and weight the claim as provisional until either peer review or independent replication arrives.
- **Retracted or corrected** papers must be checked for on any claim more than a couple of years old and central to a decision -- a retraction notice does not always propagate to secondary sources citing the original.

## Replication Status

Replication status compounds with review status rather than substituting for it:

| Review status | Replication status | Weight |
|---|---|---|
| Peer-reviewed | Independently replicated (different authors, different data) | Strong -- treat as established, cite normally |
| Peer-reviewed | Unreplicated, single study | Moderate -- usable, but flag as single-source in the dossier |
| Preprint | Independently replicated | Moderate-to-strong -- replication substitutes partially for review |
| Preprint | Unreplicated | Weak -- provisional; treat as a hypothesis, not a settled input |

"Independently replicated" means a different research group, ideally with different data or a different method, reached a compatible conclusion -- not that the same authors ran the study twice, and not that multiple papers cite the same original finding without re-deriving it.

## Citation Drift

A claim strengthens each time it is restated, because each retelling drops the least memorable qualifier first. The typical drift sequence:

1. **Original**: "In our benchmark, under condition X, we observed a 12% improvement (95% CI: 3-21%), though results varied substantially by task category."
2. **First retelling** (a survey or summary paper): "The study found a 12% improvement in performance."
3. **Second retelling** (a blog post covering the survey): "Studies show a 12% improvement."
4. **Third retelling** (an internal doc citing the blog post): "It's established that this approach improves performance by roughly 12%."

By step 4, the condition ("under condition X"), the confidence interval, and the task-category caveat are gone, and "roughly 12%" reads as a stable, general fact rather than a noisy point estimate from one benchmark. Nothing in the retelling was an outright lie -- each step is a plausible compression of the one before it -- but the cumulative effect is a claim the original source never made.

**Practical check.** For any claim relayed more than one hop from its origin, trace it back to the earliest available statement of it -- the actual paper or the actual benchmark writeup, not a summary of a summary. Compare the earliest form to the form currently being relayed. Any dropped hedge, qualifier, or interval is a finding: either restate the claim at its original strength, or explicitly note what was simplified and why that simplification is safe for the decision at hand.

## Vendor and Marketing Claims

Vendor and marketing claims are a distinct evidentiary class, not a weaker version of independent research, because the incentive structure that produced them is structurally different: the point of the artifact is to sell something, and every methodological choice (which baseline to compare against, which workload to benchmark, which metric to report) can be -- and often is -- selected for favorable results without any dishonesty at any single step.

This does not mean vendor claims are false. It means:

- **Quarantine, don't dismiss.** Treat a vendor benchmark as a hypothesis worth testing independently, not as an input a decision can rest on directly.
- **Look for the comparison that wasn't made.** A vendor claim that reports "40% faster than X" invites the question: faster at what, measured how, compared to which configuration of X, and why was that specific comparison chosen over the others available.
- **Independent confirmation upgrades the claim, not the source.** If an independent, disinterested party (an academic group, a different vendor with no stake in the result, a practitioner community with no commercial tie) reaches a compatible conclusion, the *claim* gains weight -- but the original vendor source doesn't retroactively become independent research.
- **A dossier that relays a vendor number without flagging it as vendor-sourced is laundering marketing as evidence.** Always label it explicitly: "per <vendor>'s published benchmark (unverified independently)."

## Benchmark Provenance

A benchmark result is itself a claim with a source, and the same appraisal applies to it as to any other claim -- with one extra question specific to benchmarks: **who ran it, on what, with what incentive to win?**

- **Who ran it** -- the vendor of the product being benchmarked, a third party commissioned by that vendor, an independent lab, or the broader community running a public leaderboard. Each carries a different default level of trust.
- **On what** -- the specific workload, dataset, or task suite. A benchmark's headline number is only as meaningful as the workload's relevance to the decision at hand; a benchmark optimized-for or overfit-to a specific test set (a known failure mode once a benchmark becomes a target) inflates results in ways invisible from the number alone.
- **With what incentive** -- was the benchmarking party paid by, employed by, or otherwise aligned with the entity whose product is being favorably compared? Financial or reputational stake in a specific outcome is a fact worth stating alongside the number, not a reason to discard it outright.

**Practical check.** Before citing any benchmark result in a decision-facing document, state its provenance in the same sentence as the number: "per an independently-run benchmark (X lab, no commercial tie to either vendor)" reads very differently from "per the vendor's own published comparison" -- and both read differently from no provenance statement at all, which silently implies the stronger of the two.

## Related

- [source-strength-and-transfer.md](source-strength-and-transfer.md) -- the design-and-transfer half of appraisal, which this file's review/replication/incentive analysis complements
- [writing-warranted-claims.md](writing-warranted-claims.md) -- how to record provenance, review status, and drift-check results so the appraisal is reusable by a later reader
