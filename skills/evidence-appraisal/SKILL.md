---
name: evidence-appraisal
description: >
  Appraises imported claims -- cited studies, benchmark results, vendor
  documentation, blog-post findings -- for whether the source actually
  supports the claim being made of it. Covers source-strength hierarchy,
  study design vs claim strength, external validity and transfer to a new
  setting, preprint vs peer-reviewed weighting and replication status,
  citation drift, vendor and marketing claims as a distinct evidentiary
  class, benchmark provenance, and writing a claim with its warrant attached.
  Triggers: citing a study, paper, or benchmark to justify a decision;
  relaying a coefficient, effect size, or vendor number without independent
  verification; importing an external finding into an architecture or design
  doc; appraising a source before it becomes load-bearing. Distinct from
  applied-statistics, which audits inference on our own numbers -- this skill
  audits whether someone else's numbers license the claim we are making of
  them.
allowed-tools: [Read, Glob, Grep, WebFetch]
compatibility: Claude Code
---

# Evidence Appraisal

A claim built on a misread or over-extended source fails silently: the number carries a citation's authority downstream, and nothing ever falsifies it. This skill is the checklist for catching that failure before the claim becomes load-bearing -- before it is cited in an ADR, a design doc, or a dossier that architecture gets built on.

**Content boundary.** This skill governs the relationship between a claim and its *source* -- does the source, read correctly and not over-extended, actually support the claim being made of it? It does not govern the *inference* inside our own numbers -- sample adequacy, multiple-comparisons exposure, confounding, tolerance bands, and stopping rules are the [applied-statistics](../applied-statistics/SKILL.md) skill's domain. The split in one line: **applied-statistics asks whether our analysis of our data is sound; this skill asks whether their claim about their data licenses what we are doing with it.** A dossier that both relays an external coefficient *and* runs its own analysis on it needs both skills -- appraise the import first, then hand the appraised number to applied-statistics for the inference.

**Satellite files** (loaded on-demand):

- [references/source-strength-and-transfer.md](references/source-strength-and-transfer.md) -- the source-strength hierarchy and why it is not a simple ladder, study design versus claim strength (what an observational result can and cannot license), external validity and transfer -- the single most common real failure
- [references/claim-provenance.md](references/claim-provenance.md) -- preprint versus peer-reviewed weighting and replication status, citation drift, vendor and marketing claims as a distinct evidentiary class, benchmark provenance
- [references/writing-warranted-claims.md](references/writing-warranted-claims.md) -- how to write a claim with its warrant attached so a later reader can re-appraise it, worked before/after examples, the warrant template

## Gotchas

- **A citation is not a verification.** "Relayed" is not a synonym for "checked" -- a number that traveled from a paper through a slide deck through a summary into your dossier has had three chances to drift and zero chances to be re-derived. If the number is load-bearing, read the primary source before it goes in an ADR.
- **Source-strength hierarchy is not a simple ladder -- a well-designed observational study can outrank a small, underpowered RCT** on the specific claim at hand. Rank the *fit between design and claim*, not the source type in isolation. See [source-strength-and-transfer.md](references/source-strength-and-transfer.md#the-hierarchy-is-not-a-ladder).
- **External validity is the most common real failure, not a footnote.** A result true in its original setting is imported into a setting where the mechanism's assumptions don't hold -- different scale, different population, different tooling, different incentive structure. The result is not wrong; the import is. See [source-strength-and-transfer.md](references/source-strength-and-transfer.md#external-validity-and-transfer).
- **Claim strength must not exceed design strength.** An observational correlation licenses "associated with," never "causes." Restating it as a causal claim is the single most common laundering step between a source and a downstream decision.
- **Citation drift compounds each time a claim is restated.** The original hedge ("in our benchmark, under these conditions") is dropped first, then the qualifier, then the confidence interval -- until a tentative finding reads as an established fact. Always trace a striking claim back to its earliest form before relaying it further.
- **Preprint status and peer-review status are facts about the source, not verdicts on the claim** -- but they change how much independent replication should be demanded before the claim is treated as established. Weight, don't dismiss or defer wholesale. See [claim-provenance.md](references/claim-provenance.md#preprint-vs-peer-reviewed-weighting).
- **Vendor and marketing claims are a distinct evidentiary class, not a weaker version of research.** The incentive structure (sell the product) selects which comparisons get published and how. Quarantine them -- use them as a hypothesis to test, never as a settled input to a decision.
- **Benchmark provenance is a claim in itself: who ran it, on what, with what incentive to win.** A benchmark commissioned by the vendor whose product it favors carries a different evidentiary weight than an independently run one, even when the methodology looks identical on paper.
- **Effect size versus statistical significance is a practical question here too** -- a significant effect from an outside source can still be too small to justify the architectural cost of acting on it. Judge relevance to the decision, not just whether the source reports a p-value; the inferential machinery for that judgment lives in applied-statistics.
- **A single source, however strong, is one source.** Require independent traditions -- different authors, different methods, different incentive structures -- to converge before treating a claim as established enough to build on unreviewed.

## The Six-Question Appraisal

Before an imported claim becomes load-bearing, answer these in order. A gap at any step is the finding -- state it, don't paper over it.

1. **What is the source, and what does its design license?** Identify whether the claim rests on an RCT, an observational study, a benchmark, a vendor whitepaper, or a blog post -- then check whether the claim being made matches what that design can support. See [source-strength-and-transfer.md](references/source-strength-and-transfer.md#study-design-versus-claim-strength).
2. **Does the source's setting match ours?** Scale, population, tooling, incentive structure, and time period all bound external validity. Name the specific dimension along which our setting differs, if any. See [source-strength-and-transfer.md](references/source-strength-and-transfer.md#external-validity-and-transfer).
3. **Has the claim drifted from its original form?** Trace it back at least one hop -- to the paper, not the summary of the summary. Note any hedge, qualifier, or confidence interval that was dropped along the way. See [claim-provenance.md](references/claim-provenance.md#citation-drift).
4. **What is its review and replication status?** Preprint or peer-reviewed; replicated once, replicated independently, or standing alone. See [claim-provenance.md](references/claim-provenance.md#preprint-vs-peer-reviewed-weighting).
5. **Whose incentive produced this number?** Independent research, a vendor benchmark, or marketing copy -- and if a vendor or marketing source, quarantine it rather than treat it as a settled input. See [claim-provenance.md](references/claim-provenance.md#vendor-and-marketing-claims).
6. **Does the claim as written carry its warrant?** A reader six months from now, with no access to this conversation, should be able to tell what the claim licenses and what it doesn't from the sentence alone. See [writing-warranted-claims.md](references/writing-warranted-claims.md).

## Convergence Standard

Treat a claim as established enough to build architecture on only when independent traditions converge on it -- not repetitions of the same source, method, or authorship. Two peer-reviewed papers from the same lab using the same dataset are one data point, not two. A vendor benchmark and an independent academic replication that agree are a stronger convergence than either alone. When only one source exists and it is load-bearing, say so explicitly in the dossier (e.g., "single-source, unreplicated -- treat as provisional") rather than let the citation imply more consensus than exists.

## Reading Someone Else's Claim -- Quick Checklist

| Check | Absence implies |
|---|---|
| Is the claim's design (RCT / observational / benchmark / vendor) identified? | The claim's evidentiary weight is unknown, not just unstated |
| Does the causal language match the design's strength? | The claim overstates what the source licenses |
| Was the source's setting compared to ours along at least one dimension? | The transfer has not been checked; the result may not hold here |
| Was the claim traced to its earliest stated form? | Citation drift may have inflated it; you are relaying a relay |
| Is the source's review/replication status stated? | Confidence in the claim is unanchored |
| If vendor or marketing-sourced, is it flagged as such? | The claim is being treated as research when its incentive structure differs |
| Does more than one independent source converge on this? | The claim rests on a single unreplicated data point |
| Does the claim in the dossier carry its warrant (source, design, setting, hedge)? | A later reader cannot re-appraise it without redoing this work |

Two disciplines make this checklist useful rather than obstructive, matching the sibling statistician checklist: **name the specific decision the objection would change** -- an objection that changes no decision is not worth raising -- and **name the settling action** -- read the primary source, find an independent replication, or run our own small check. An appraisal objection without a settling action is a vague doubt, not a finding.

## Related Skills

- **[applied-statistics](../applied-statistics/SKILL.md)** -- inference on our own numbers: sample adequacy, multiple comparisons, confounding, tolerance bands, stopping rules. Consult it once an imported number has been appraised and is being analyzed further; consult this skill first to decide whether the number should be trusted at all.
- **[multi-perspective-analysis](../multi-perspective-analysis/SKILL.md)** -- the convening mechanism that spawns a discipline consultant (including an evidence-appraiser) against a design or claim; this skill is the runtime knowledge binding such a consultant loads.
- **[external-api-docs](../external-api-docs/SKILL.md)** -- a related but distinct concern: verifying an external API or SDK's documented behavior before building against it, rather than appraising a research or vendor claim.
