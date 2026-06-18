# Disconfirmation Tiers

Reference for the two-tier disconfirmation protocol: Tier-A (always-on for `category: architectural` ADRs) and Tier-B (cross-model adversarial challenge, gated). Back to [SKILL.md](../SKILL.md).

## DI vs. DA Distinction

**Dialectical Inquiry (DI)** — the invoking agent constructs a genuinely believed rival design and argues it before committing to the `### Decision` block. The rival must be a position the author would actually defend, not a strawman. (Schweiger 1989: DI > Devil's Advocacy > consensus for decision quality under uncertainty.)

**Devil's Advocacy (DA)** — an agent assigned to oppose the chosen option, regardless of actual belief. Schweiger's comparative studies show DA is better than unstructured consensus but worse than DI because the advocate is not invested in the rival's quality. Assigned DA tends toward theater: the advocate meets the social obligation to push back without genuinely contesting the evidence.

**Praxion uses DI, not DA.** The "argue-the-runner-up-genuinely" instruction in `agents/systems-architect.md` Phase 7 is DI: the architect pauses before the `### Decision` block and argues the steelmanned runner-up as if it were their actual recommendation.

## Tier-A: Always-On Disconfirmation (Architectural ADRs)

**Activation**: all ADRs with `category: architectural`.

**Required sections** within the ADR body under `## Disconfirmation`:

| Sub-section | Content |
|---|---|
| **Falsifier** | What evidence or outcome would invalidate the chosen approach? Name a concrete, observable condition — not "if requirements change." |
| **Steelmanned runner-up** | The strongest version of the primary alternative. Argue it as if it were your actual recommendation. Include the specific context under which it would dominate. |
| **Reversal trigger** | The condition under which the decision should be revisited and the runner-up reconsidered. Must be observable: a metric threshold, a milestone, a team-size crossing, an SLA breach. |

**Machine-queryable companion**: the ADR `dissent:` frontmatter field (see `rules/swe/adr-conventions.md`) holds a short summary of the steelmanned runner-up. Sentinel and verifier can query `dissent:` without parsing the full body. The body's `## Disconfirmation` section is the authoritative prose; `dissent:` is the index entry.

**Why always-on for architectural ADRs.** Architectural decisions are high-reversibility-cost, long-lived, and have high blast radius. A decision made without recording its falsification condition and its best alternative cannot be safely revisited when new evidence arrives — the future reader has no anchoring point. The Tier-A block costs ~5 minutes of author time per ADR and pays for itself at the first revisit.

## Tier-B: Cross-Model Adversarial Challenge (Gated)

**Activation gate**: honest-uncertainty fires AND stakes ∈ {security, one-way-door, user-visible-breaking}.

Both conditions must hold. Stakes alone do not trigger Tier-B if the architect can name a clear winner (honest-uncertainty gate closed). Honest-uncertainty alone does not trigger Tier-B unless stakes are elevated — use Tier-A instead.

**What Tier-B is**: a different-model agent is invoked as an external oracle to argue the rival design. The external-oracle rationale is grounded in Huang et al. (ICLR 2024): self-correction via further prompting of the same model is approximately zero at the capability frontier, because the model's self-critique collapses onto its own prior. A cross-model challenge (different weights, potentially different training data) functions as a genuine external oracle, not a sycophantic reflection.

**What Tier-B is not**: it is not a debate. Both models do not "argue" back and forth. The pattern is:
1. The proposing architect documents the chosen option fully (Tier-A complete).
2. A Tier-B oracle agent (different model, no access to the proposer's reasoning) is given the problem statement and the rival design's description only — not the chosen option.
3. The oracle argues the rival as persuasively as possible.
4. The proposer reads the oracle's argument and either: (a) updates the ADR to reflect a genuine change in conclusion, or (b) records in `## Disconfirmation § Steelmanned runner-up` why the argument did not change the decision.

**Tier-B is not a rubber stamp.** If the oracle's argument is strong and the proposer does not update — the proposer must write a substantive rebuttal in the ADR body. "We chose X anyway" without engaging the oracle's best argument violates the contract.

**Cost.** Tier-B adds one full oracle-model call per gated ADR. At the activation gate conditions (high stakes, genuine uncertainty), this cost is justified. At Standard-tier frequency, expect Tier-B to fire on fewer than 20% of architectural ADRs.

## References

- [`../SKILL.md`](../SKILL.md) — parent skill; activation gate; satellite table.
- `agents/systems-architect.md` — Phase 7 DI sub-step (uses this file's DI definition and Tier-A contract); Tier-B cross-model note.
- `rules/swe/adr-conventions.md` — `dissent:` frontmatter field; `## Disconfirmation` body section.
- `skills/software-planning/references/design-synthesis.md` — S3 (Architecture) synthesis gate; convergence signals.
- Schweiger, D.M., Sandberg, W.R., & Ragan, J.W. (1989). *Group approaches for improving strategic decision making: A comparative analysis of dialectical inquiry, devil's advocacy, and consensus.* Academy of Management Journal, 32(1), 51–71.
- Huang, J., et al. (2024). *Large Language Models Cannot Self-Correct Reasoning Yet.* ICLR 2024.
