# Source Strength and Transfer

Back to [SKILL.md](../SKILL.md).

## The Hierarchy Is Not a Ladder

The conventional evidence hierarchy -- meta-analysis and systematic review at the top, then RCTs, then observational studies, then case reports and expert opinion, then anecdote -- is a useful default ordering but a poor decision rule when applied mechanically. Two corrections matter more in practice than the ordering itself:

- **Fit between design and claim beats source type in isolation.** A well-designed, adequately powered observational study that directly measures the claim in question outranks a small, underpowered, or indirectly-related RCT. The hierarchy ranks *average* reliability across all possible claims a design type could support; a specific claim needs the specific fit checked, not the average.
- **A source higher on the ladder can still fail on setting-match.** A meta-analysis of enterprise Java codebases says nothing directly about a solo developer's Python project, however many studies it aggregates. Rank position answers "how much did this design control for confounds," not "does this apply to me."

Use the hierarchy to set a prior, then check design-claim fit and external validity before finalizing the weight given to a source.

### Practical ranking, most to least resistant to misleading conclusions

1. Meta-analysis / systematic review of multiple independent studies, when the included studies are themselves sound
2. Randomized controlled trial, pre-registered, adequately powered
3. Well-designed observational study (matched cohorts, adjustment for known confounders, sensitivity analysis)
4. Benchmark result with disclosed methodology, run by a party without a stake in the outcome
5. Single unreplicated observational study, or a benchmark run by an interested party but with disclosed methodology
6. Vendor whitepaper, marketing benchmark, undisclosed methodology
7. Blog post, forum anecdote, single-practitioner experience report, uncorroborated

A claim resting on tier 6 or 7 alone should never appear in a dossier as a settled fact. It may appear as a hypothesis worth testing, explicitly labeled as such.

## Study Design Versus Claim Strength

The design of a study bounds the strength of causal language that can honestly attach to its result. Three common design types and what each licenses:

| Design | What it licenses | What it does NOT license |
|---|---|---|
| Randomized controlled trial | "X causes Y" (within the study's population and setting) | Universal causal claims outside that population; magnitude claims beyond the measured effect and its interval |
| Well-controlled observational study (matched, adjusted) | "X is associated with Y, and known confounders don't explain it" | "X causes Y" -- residual and unmeasured confounding remain possible |
| Unadjusted observational study or correlation | "X and Y move together in this sample" | Any causal claim; any claim about a different sample |
| Single case study or anecdote | "X occurred in this one instance" | Any generalization at all |

The failure mode this table exists to catch: an unadjusted correlation from a blog post gets restated in a design doc as "X causes Y," and the causal claim then justifies an architectural decision the correlation never supported. When appraising an imported claim, identify its design first, then check that the language used to relay it doesn't exceed what that design licenses. If it does, restate it at the correct strength before it enters a dossier -- do not silently accept the inflated version because it is more useful to the argument.

## External Validity and Transfer

This is the single most common real failure this skill exists to catch: a result that is *true* in its original setting gets imported into a setting where the mechanism producing it does not hold. The result was not wrong -- the transfer was.

External validity fails along a small number of recurring dimensions. Check each explicitly before importing a claim:

- **Scale.** A finding from a 10-person team's workflow study may not transfer to a 500-engineer organization, and vice versa -- coordination overhead, review latency, and knowledge distribution scale non-linearly.
- **Population.** A benchmark run against senior engineers' output does not describe junior engineers' output, and a study of one language's ecosystem does not describe another's tooling maturity.
- **Tooling and infrastructure generation.** A performance or reliability finding from three major versions ago of a framework, database, or runtime may not hold after the vendor changed its internals, even if the API surface looks identical.
- **Incentive structure.** A finding produced under a research grant, a hackathon, or a paid pilot may reflect the incentive under which the work was done (impress reviewers, meet a deadline, satisfy a sponsor) rather than the mechanism the paper claims to isolate.
- **Time.** Findings about LLM capability, benchmark saturation, or tool ecosystem maturity decay faster than most other empirical claims; a result from eighteen months prior may already be stale for a fast-moving subfield.

**Practical check.** For each dimension above, ask: does our setting differ from the source's setting on this axis, and if so, does the mechanism the source claims to have found still plausibly operate under that difference? If the answer is "the mechanism plausibly still holds," say so and note the assumption. If the answer is "unclear" or "no," the claim needs re-derivation in our own setting before it can be treated as established here -- import it explicitly as an untested hypothesis, not a settled fact.

## Related

- [claim-provenance.md](claim-provenance.md) -- what a source's review and replication status adds to (or subtracts from) the design-and-transfer assessment above
- [writing-warranted-claims.md](writing-warranted-claims.md) -- how to record the design, transfer check, and any assumption made, so a later reader doesn't have to redo this analysis from scratch
