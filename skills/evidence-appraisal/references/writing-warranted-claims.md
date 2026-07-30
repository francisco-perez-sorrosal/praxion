# Writing Warranted Claims

Back to [SKILL.md](../SKILL.md).

A claim without its warrant attached forces every future reader to either trust it blindly or redo the whole appraisal from scratch. Writing the warrant alongside the claim is the cheapest insurance against both citation drift (the warrant records the original hedge before it gets dropped) and silent staleness (the warrant records enough to re-check the claim later, without re-finding the source from memory).

## The Warrant Template

A warranted claim states four things, in one to three sentences:

1. **The claim itself**, at the strength the source actually licenses (see [source-strength-and-transfer.md § Study Design Versus Claim Strength](source-strength-and-transfer.md#study-design-versus-claim-strength))
2. **The source and its design** (RCT / observational / benchmark / vendor whitepaper / blog post), specific enough that a reader could find it again
3. **The setting it was measured in**, and how that setting compares to ours if the comparison is not obvious
4. **The confidence to place in it** -- review/replication status, and whether it stands alone or converges with independent sources

## Worked Examples

### Before (unwarranted)

> Studies show that pair programming increases code quality by 15%.

Problems: no source, no design, no setting, no confidence signal, and "studies show" implies a convergence that may not exist. A reader six months from now cannot tell whether this is a settled finding or a single small study's headline number that drifted through two summaries to get here.

### After (warranted)

> A 2019 controlled study of 24 developer pairs (Cockburn & Williams-style design, single organization) found a 15% defect-rate reduction under pair programming versus solo work (no reported CI; single-source, not independently replicated in a comparable setting since). Treat as a directional signal, not an established effect size -- our team size and codebase differ substantially from the study's setting.

This version lets a later reader decide, without re-deriving anything, whether the claim is strong enough to lean on for the decision at hand.

### Before (unwarranted, vendor case)

> Vendor X's platform reduces build times by 40% compared to alternatives.

### After (warranted)

> Per Vendor X's own published benchmark (unverified independently; no disclosed baseline configuration), build times were reported as 40% faster than an unspecified alternative. Quarantined -- no independent confirmation found; do not treat as an input to the build-tooling decision without our own measurement.

## Template for Dossier Entries

```
Claim: <the claim, at the strength the source licenses>
Source: <author/org, year, design type>
Setting: <where/how it was measured; how it compares to ours, if relevant>
Confidence: <review status, replication status, single-source or converging, vendor/marketing flag if applicable>
```

Use this four-line form in any evidence dossier, ADR, or design doc section that leans on an imported claim. It costs four lines and saves a re-derivation.

## When a Claim Cannot Be Warranted

If a claim central to a decision cannot be traced to a specific source, design, and setting -- because it arrived as unattributed "common knowledge," a secondhand paraphrase with no findable original, or a recollection with no citable artifact -- say so explicitly rather than writing a warrant that looks complete but isn't:

> Claim: <the claim>. Source: unattributed / could not be traced to a primary source. Treat as anecdotal until a source is found or the claim is independently tested.

An honest "this is unwarranted" is more useful to a later reader than a warrant fabricated to look rigorous.

## Related

- [source-strength-and-transfer.md](source-strength-and-transfer.md) -- how to determine the claim strength a source licenses, before writing the warrant
- [claim-provenance.md](claim-provenance.md) -- what to check for review status, replication, and vendor/marketing flags before filling in the Confidence line
