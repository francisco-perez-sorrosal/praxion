---
id: dec-298
title: Consult dialogue protocol — isolate, challenge, disposition, reconcile; one loop-back; adjudicate per challenge, never blended synthesis
status: accepted
category: architectural
date: 2026-07-30
summary: The consultant dialogue is four rounds bounded at one orchestrator-mediated loop-back, reusing dec-154's challenge-loop mechanism verbatim; reconciliation is single-owner and adjudicates each challenge individually rather than producing a blended narrative, and termination is judged on dispositions rather than on absence of visible disagreement.
tags: [multidisciplinary-identities, discipline-consultant, dialogue-protocol, challenge-loop, reconciliation, lens-independence, termination-condition, dec-154]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
re_affirms: dec-154
affected_files:
  - agents/discipline-consultant.md
  - skills/software-planning/references/coordination-details.md
  - agents/systems-architect.md
  - agents/sentinel.md
affected_reqs:
  - REQ-08
  - REQ-09
  - REQ-10
  - REQ-11
  - REQ-12
dissent: A one-round bound justified by studies of answer-convergence debates may not transfer to design critique, where the first exchange often only establishes that the parties are talking about different things; capping at one round guarantees that a genuinely contested methodological claim terminates in an architect's unilateral dismissal rather than in resolution, and the escalation-to-user valve converts a technical disagreement into a demand on the user's attention rather than resolving it.
---

## Context

The primary source's most actionable finding is a **negative** one: reasoning models spontaneously learn to
*diverge* but not to *converge* — *"individual approaches compete rather than forming an effective ensemble."*
Divergence is free; synthesis is not. That identifies exactly where engineered scaffolding adds value the model
will not supply, and it is the justification for making reconciliation a **mandatory, single-owner** step rather
than an emergent outcome of debate.

Two questions were open at intake: whether one challenge round is the right bound, and whether the
lens-independence doctrine (agents must not see each other's work during collection) conflicts with the dialogue
requirement (agents must engage).

Wave A closed the round-count question with four independent convergent sources: an adaptive
sequential-probability-ratio governor stops at **1.01 average rounds** (97.0% accuracy, 4.06 calls) versus
fixed-five rounds (99.0%, 15 calls) — rounds 2–5 bought 2pp for 3.7× the calls; a controlled six-factor study
found the **debate-depth coefficient 0.019, not significant**, while the **agent-count coefficient was 0.066,
p<0.001**; a peer-reviewed ICML result found multi-agent debate does not reliably beat self-consistency and that
the larger lever was first-round *agreement intensity*, not round count; and the one dissenting result (benefit
extending to five rounds) applies only to **RL-trained** agents, whereas these consultants are prompt-level.

Uncomfortably, the *harm* pathways also fire at first exposure: conformity *"reaches high levels at minimal peer
exposure (K=2) and intensifies with greater initial diversity"* — precisely the regime a discipline roster
creates. So sparse exposure does not protect against conformity, and the highest-value gate is **before** round 0.

A separate 2026 result sharpens the termination question: debate *"reduces detectable contradictions between
agents while simultaneously decreasing the semantic similarity of their reasoning chains; agents appear to agree
more but reason less consistently."* Apparent convergence can therefore coexist with diverging rationales.

Finally, the reconciliation *mode* was unspecified at intake. The evidence on mode is the largest single effect
retrieved: with an identical generator pool, judge-style **selection** scored 0.810 versus MoA-style
**synthesis** 0.179 (Δ +0.631, Hedges' g = 3.86, p = 1.29×10⁻¹⁵), and the synthesis mode *"loses to the
single-model baseline in 82% of comparisons."*

## Decision

**Four rounds, bounded at one orchestrator-mediated loop-back, reusing `dec-154`'s challenge-loop mechanism
verbatim.**

| Round | Action | Discipline enforced |
|---|---|---|
| **0 — Isolate** | The consultant reads the *same source materials* as researcher and architect, with **no access to their draft** and no access to any sibling `CONSULT_*.md`. Writes `## Independent Reading` and an explicit `## Sources Read` list | Lens independence during collection. Sharing the draft here produces correlation collapse — N× cost for a correlated opinion |
| **1 — Challenge** | The same instance now reads `SYSTEMS_PLAN.md` (and `IMPLEMENTATION_PLAN.md` when convened at the planning seam) and appends `## Challenges`. Each entry carries a **falsifiable claim**, **the decision it would change**, **the test that would settle it**, and a calibrated confidence | A challenge that names no decision is dropped by the consultant itself — the mechanical filter against decorative expertise |
| **2 — Disposition** | The orchestrator routes challenges to the convener, who adjudicates **per challenge** using the shared vocabulary (`switch-now` / `defer-with-rationale` / `dismiss-with-rationale`) and appends one ledger row per challenge | Silent dismissal is already a behavioural-contract violation, so the obligation to answer is pre-enforced |
| **3 — Reconcile, then stop** | Bounded at **one** loop-back. Reconciliation is owned by **one party**, never negotiated between peers. Non-convergence escalates to the user with both positions stated | Direct answer to the reconciliation deficit and to MAST's inter-agent-misalignment and missing-termination-condition modes |

Three specifications the intake hypothesis did not carry:

1. **Reconciliation mode is adjudication, not synthesis.** The convener adjudicates each challenge individually
   and does **not** write a blended narrative that averages challenges away. Phrased as *"adjudicate per
   challenge"* rather than *"never synthesize"*, because a conflicting result favours trace-level synthesis on
   *verifiable* tasks; the safe formulation covers both. Zero mechanism cost, guarding the largest measured
   effect in the retrieved literature.
2. **Termination is judged on dispositions, not on absence of visible disagreement.** Because apparent agreement
   can mask diverging rationales, "the rounds terminated" is not sufficient evidence of resolution. The real
   termination test is **zero undispositioned challenges**, with sentinel `P07`'s scope extended in place to
   `CONSULT_*.md` as the mechanical backstop.
3. **The gate is before round 0, not at round 2.** Because both the value peak and the conformity harm fire at
   first exposure, there is no useful "should we do another round?" decision — the only decision that matters is
   whether to convene at all. This is why convening is gated and the round bound is fixed rather than adaptive.

**Surviving challenges flow into surfaces that already exist:** a `switch-now` challenge becomes architecture
plus the ADR's `## Disconfirmation` block and `dissent:` frontmatter — a statistician's objection becoming a
*recorded falsifier* is exactly what that field is for. A `defer-with-rationale` challenge carrying residual risk
flows through the existing verifier→tech-debt-ledger path; the consultant never writes a ledger row itself,
preserving the four-writer contract.

**Multi-instance:** lens independence holds *across* instances during round 0 — no instance may read a sibling's
fragment. Concurrent consultants that can see each other collapse into one correlated opinion at N× the cost.
Reconciliation is **not** distributed: one owner merges N fragments, because selector quality dominates
generator diversity by a large margin.

**"Isolate, then dialogue" resolves the apparent doctrinal conflict.** Lens independence governs round 0;
dialogue governs rounds 1–2. Both hold. A contradiction that survives that sequence marks genuine ambiguity
rather than anchoring, and is the highest-value signal the pipeline can produce. Anthropic's own agent-teams
documentation independently names **anchoring** as the failure that independence prevents and pairs independence
with **mutual disproof** — structurally identical to round 0 plus round 1.

## Considered Options

### Option 1 — Four rounds, one loop-back, as specified (chosen)

- **Pros:** four independent convergent sources support the bound; reuses an existing, load-bearing mechanism
  with no new machinery; explicit termination condition closes MAST's missing-termination mode; bounded cost.
- **Cons:** a genuinely contested claim terminates in unilateral dismissal or a user escalation rather than in
  resolution.

### Option 2 — Two challenge rounds

- **Pros:** a second pass lets the consultant respond to the architect's reasoning, which is where design
  critique arguably differs from answer convergence.
- **Cons:** measured depth coefficient not significant; 3.7× calls for 2pp in the adaptive-governor comparison;
  conformity intensifies with exposure. Refuted rather than merely unsupported.

### Option 3 — Adaptive sequential-test round governor

- **Pros:** converts a qualitative bound into a measured one and doubles as a failure detector — in the source
  experiment the calibrated statistic collapsing to ≈0 *revealed* that the consensus signal carried no
  information in that domain rather than silently wasting rounds.
- **Cons:** substantial machinery for a protocol whose bound is already one round; needs a per-domain calibration
  set; degraded to capping 99.5% of items when calibration failed. Deferred as machinery — but adopted as
  *content* for the new statistics skill, where it is the best available worked example of sequential testing and
  calibration-as-the-real-object.

### Option 4 — Peer-to-peer exchange between consultants (agent-teams substrate)

- **Pros:** the vendor's own guidance favours teams for *"complex work requiring discussion and collaboration"*,
  which is literally the consultant's purpose.
- **Cons:** three documented blockers — `skills:` frontmatter is **silently dropped** for teammates (which would
  kill every discipline binding, leaving a role label with no bound knowledge artifact), no nested teams (which
  would collapse self-nomination into orchestrator-only selection), and the definition body is *appended* to the
  teammate's system prompt rather than replacing it (eroding round-0 independence). Independently, peer-to-peer
  mid-task exchange is the channel the 2026 literature associates with sycophantic conformity, consensus
  collapse, and the consistency illusion.

## Consequences

**Positive:** bounded, predictable cost; zero new loop-back machinery, which is precisely why per-discipline
always-loaded cost is zero (the git archaeology showed a new *loop-back mechanism* is what costs always-loaded
bytes, not a new value); the reconciliation mode is externally supported rather than assumed; termination has a
mechanical test.

**Negative:** one round may under-explore a genuinely contested claim; the escalation path spends user attention
rather than resolving the disagreement technically.

**Risks accepted:** round-0 isolation is enforced by instruction and made *checkable* by the `## Sources Read`
section, not enforced mechanically — a consultant could read the draft anyway. Accepted because the alternative
(a mechanical read-barrier) does not exist in the harness, and the artifact-level check is the strongest
available. Also accepted: round 0 gives every instance *identical* rather than *perturbed* input, so the
trace-diversity mechanism that makes single-backbone ensembles work is not exploited; deliberately varying the
framing of the same materials is an unexplored cheap knob left for a later pass.

## Prior Decision

`dec-154` ("Specialist sub-architects are active quality advocates with standing — the orchestrator-mediated
challenge loop") is **re-affirmed, not superseded**. Its mechanism is reused unchanged: a specialist writes
challenges into a dedicated section of its own artifact; the orchestrator (not agent-to-agent messaging) routes
substantive challenges back; the architect is obligated to accept or reject **with a reason**; the loop is bounded
at one re-evaluation round; non-convergence escalates to the user with both positions stated. The only
differences are the section name (`## Challenges` rather than `## Architecture Challenges`, so sentinel `P07`'s
grep stays unambiguous across artifact types) and the required per-entry fields.

One asymmetry is worth recording explicitly: `dec-154`'s specialists hold **decision authority in their own
partition** — the challenge concerns the boundary between two domains of authority. The discipline consultant
holds **no** decision authority anywhere, so every one of its outputs is a challenge and none is a decision.
That makes the obligation to disposition strictly heavier here, not lighter, and it is why the disposition
counter is a prerequisite rather than an afterthought. A supersession of `dec-154` would require evidence that
the orchestrator-mediated loop itself fails — nothing here shows that; if anything the reuse strengthens it by
demonstrating the mechanism generalizes to a second, differently-shaped party.

## Disconfirmation

- **Falsifier:** consult rounds systematically failing to terminate within the one-loop-back bound, observed
  live — or, more subtly, terminating on schedule while the ledger shows challenges dispositioned
  `dismiss-with-rationale` whose rationale does not engage the falsifiable claim. The second is the failure the
  consistency-illusion result predicts: apparent closure with no real reconciliation.
- **Steelmanned runner-up:** Option 2 (two rounds). The strongest case is that every round-count study retrieved
  measured *answer convergence on verifiable tasks*, while this protocol runs *design critique with no ground
  truth*. In design critique the first exchange frequently only establishes that the two parties were reasoning
  about different assumptions; the second is where the real disagreement gets stated. The measured depth
  coefficient may therefore be a domain-mismatched prior, and capping at one round may be buying cost discipline
  with resolution quality. If the ledger shows a persistent pattern of dismissals whose rationale is "the
  consultant misunderstood the constraint", that is evidence for Option 2, not for deleting the consultant.
- **Reversal trigger:** a measured dismissal pattern dominated by *mutual misunderstanding* rather than by
  *disagreement on the merits*, over ≥10 challenges. That specific signature — and not a generally high dismiss
  rate — is what would justify widening the bound to two rounds. Separately, if Claude Code applies `skills:`
  frontmatter to teammates and permits nested teams, the agent-teams substrate becomes viable and Option 4
  should be re-evaluated.
