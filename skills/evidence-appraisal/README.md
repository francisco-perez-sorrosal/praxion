# Evidence Appraisal

Appraises **imported** claims -- cited studies, benchmark results, vendor documentation, blog-post findings -- for whether the source actually supports the claim being made of it.

The failure this skill exists to catch is silent. A misread or over-extended source propagates downstream carrying the authority of a number, and nothing later falsifies it: the architecture built on it works, the tests pass, and the claim is restated with its original hedge quietly dropped.

## The boundary against `applied-statistics`

These two are adjacent and must not be confused, so the split is stated in one line:

> **`applied-statistics` asks whether our analysis of our data is sound. This skill asks whether their claim about their data licenses what we are doing with it.**

A document that both relays an external coefficient *and* runs its own analysis on it needs both: appraise the import first, then hand the appraised number to `applied-statistics` for the inference.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: the content boundary, appraisal sequence, claim-vs-warrant discipline, and the objection checklist |
| `references/source-strength-and-transfer.md` | Source-strength hierarchy and why it is not a simple ladder; study design versus claim strength; external validity and transfer into a setting whose assumptions differ |
| `references/claim-provenance.md` | Citation drift, preprint versus peer-reviewed weighting, replication status, vendor and benchmark provenance |
| `references/writing-warranted-claims.md` | The warrant template, worked before/after examples, the dossier-entry shape, and what to do when a claim cannot be warranted at all |

## When it fires

As the knowledge binding for the `evidence-appraiser` consulting discipline, convened when a load-bearing decision rests on an external claim whose strength has not been appraised. It is also usable directly, without a consultant, whenever a design is about to import someone else's number.

## Quick Start

1. Locate the primary source -- not the citation of the citation.
2. Ask what claim the source's design can license, independent of what it concluded.
3. Ask whether our setting satisfies the assumptions the source's setting did.
4. Write the claim with its warrant attached, so a later reader can re-appraise it without repeating the search.

## Related Skills

- [`applied-statistics`](../applied-statistics/) -- inference on our own numbers, once an imported claim has been appraised
- [`multi-perspective-analysis`](../multi-perspective-analysis/) -- the convening mechanism that spawns a discipline consultant against a design
- [`external-api-docs`](../external-api-docs/) -- verifying an external API's documented behavior, a related but distinct concern
