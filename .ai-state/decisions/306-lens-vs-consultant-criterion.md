---
id: dec-306
title: A discipline earns a consultant only when its errors are silent; otherwise the knowledge belongs in the lens's owning skill
status: accepted
category: architectural
date: 2026-07-30
summary: Establishes the lens-versus-consultant criterion — convene a consultant only when a wrong answer produces an artifact indistinguishable from a right one absent expert challenge — and applies it to remove performance-engineer and queueing-modeler from the Wave-2 roster, strengthen the Performance lens with the agent-era dimension instead, and select evidence-appraiser as discipline #2.
tags: [multidisciplinary-identities, discipline-consultant, lens-catalog, performance, evidence-appraisal, selection-criterion, wave-2, silent-failure]
made_by: user
agent_type: orchestrator
branch: main
pipeline_tier: standard
re_affirms: dec-303
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - skills/performance-architecture/SKILL.md
  - skills/evidence-appraisal/SKILL.md
  - docs/multidisciplinary-identities-evidence.md
dissent: The criterion is stated crisply but rests on a distinction that will blur in practice — "does the error surface through normal feedback" is itself a judgement call, and a motivated author can classify almost any domain either way to get the answer they want. Worse, it may be self-serving — it justifies exactly the one discipline already shipped and rules out the one a user proposed, which is the shape of a criterion reverse-engineered from a conclusion. A simpler and less gameable rule — no consultant for any domain that already owns a lens — would have reached the same outcome on performance without inventing a new axis, and would not have needed a second discipline to be selected in the same breath to demonstrate that the axis discriminates.
re_affirmed_by:
  - dec-309
  - dec-310
---

## Context

Wave 1 shipped one consulting discipline (`statistician`) and recorded a Wave-2 candidate roster in the
evidence dossier §12.2, including `performance-engineer` and `queueing-modeler`. A separate deferred
condition (`dec-303`) required that any discipline colliding with an existing evaluation lens must have
its escalation relationship written *before* it ships — encoded as the mandatory `lens-collision` registry
field.

`performance-engineer` was the named instance of that collision: the **Performance lens** already exists
in the Lens Catalog, owned by `skills/performance-architecture/SKILL.md`, and fires *unconditionally*
during design synthesis at research and at two architecture phases.

Writing that escalation relationship raised a prior question the design had never answered: **what makes a
discipline worth a consultant at all, rather than knowledge in a lens?**

Two facts settled it.

**First, a lens and a consultant deliver identical knowledge.** Wave A established this when it eliminated
the "skills injected into existing agents" option: a skill read by the architect *is the architect thinking
with better knowledge* — there is no second party, so there is nothing to disagree with. The consultant's
entire marginal contribution over a lens is **standing to object**. Not knowledge, not quality — standing.

**Second, the specific knowledge was already there.** `skills/performance-architecture/references/capacity-planning.md`
already contains Little's Law, back-of-envelope estimation, and cost-performance modelling — precisely
what §12.2 reserved for `queueing-modeler` and what §13 routed to `performance-engineer`. Both proposed
consultants would have delivered, behind a gate and at the cost of an opus spawn, knowledge the architect
already receives free on every design pass.

That inverts the usual framing. Gating knowledge that improves *every* decision does not add rigor; it
**subtracts availability**. It is a pessimization dressed as diligence.

## Decision

**A discipline earns a consultant only when its errors are silent.** Otherwise its knowledge belongs in the
owning artifact of a lens, where it is delivered free and unconditionally.

The discriminator is: **does the error surface through normal feedback?**

- **Performance errors surface.** Benchmarks, profilers, latency graphs, cost bills. A wrong performance
  intuition is falsified by measurement, usually before it becomes load-bearing.
- **Statistical errors do not.** An inadequate sample size produces a number that looks correct
  indefinitely. This is not theoretical: the first live consult found six defects in a quantitative gate
  whose author believed it sound, including exact operating characteristics showing the gate could not
  discriminate the cases its own decision turned on.

Three consequences follow, and are adopted:

1. **`performance-engineer` and `queueing-modeler` are removed from the Wave-2 roster.** Neither will ship.
   The `lens-collision` obligation is not discharged by writing an escalation relationship for
   `performance-engineer`; it is discharged by concluding that the discipline should not exist. A
   non-`none` `lens-collision` value is therefore re-read as a **signal to re-examine whether the discipline
   is warranted**, not merely a documentation chore to complete before shipping.
2. **The Performance lens is strengthened instead.** `skills/performance-architecture/` gains the agent-era
   dimension — token budget as a capacity constraint, context-window efficiency, spawn cost and fan-out,
   pipeline wall-clock, and the measurement discipline each requires. This gap was verified rather than
   assumed: token budget is presently owned by `rule-crafting`, `skill-crafting`, and a rules README, and
   by **no** artifact the Performance lens points at — so the lens fires on agentic designs and says
   nothing about the resource they actually spend. Making performance always-on is strictly stronger than
   making it a gated consult.
3. **`evidence-appraiser` becomes discipline #2**, bound to a new `evidence-appraisal` skill. It satisfies
   the criterion: an imported claim that is misread or over-extended propagates downstream carrying the
   authority of a number, and nothing falsifies it. The charter is concrete — the first live consult
   explicitly declined to verify the coefficients its own analysis rested on, writing that they were
   *relayed* rather than checked.

**The boundary against `statistician` is load-bearing** and is written into both rows: the statistician asks
whether the *inference* is sound given the data, operating on **our own** numbers; the evidence-appraiser
asks whether the *source* supports the claim being made of it, operating on **someone else's** claims that
we are importing.

**Expansion-gate disposition, recorded rather than bypassed.** The discipline-#2 criterion currently reads
*not yet informative* — one distinct consult, two of three disposition values observed. Shipping #2 today
is a **human disposition against that reported estimate**, which is the mechanism working exactly as
designed: the gate was deliberately demoted from an automatic threshold to an estimate a human adjudicates.
The reasons are stated so a later reader can judge them: the multi-instance concurrency contract (`td-070`)
is untestable at one discipline and is a Wave-2 prerequisite; and the second discipline was selected on a
structural criterion rather than on enthusiasm for a candidate. This is knowingly the risk the prior
decision's reversal trigger named.

## Considered Options

### Option A — Criterion plus lens strengthening (chosen)

- **Pros.** Answers the general question once instead of per-candidate. Removes two roster entries that
  would have duplicated existing knowledge at spawn cost. Redirects the effort into an always-on channel,
  so every design pass benefits rather than only gated ones. Reinterprets `lens-collision` as a design
  signal, which makes the existing mandatory field more useful without changing it.
- **Cons.** The criterion's key term is a judgement call (see `dissent:`). It also creates an asymmetry:
  knowledge added to a lens is never *rejected* by anyone, whereas a consultant's challenge must be
  dispositioned — so lens-delivered knowledge has weaker accountability.

### Option B — Write the escalation relationship and keep `performance-engineer`

- **Pros.** Honours the deferred condition literally. Preserves optionality; the discipline could still be
  convened for genuinely contested capacity questions.
- **Cons.** Requires specifying when a gated expensive mechanism supersedes a free always-on one that has
  already run — and the honest answer, given the knowledge is identical, is "never, except to obtain
  standing to object." Paying an opus spawn for standing alone, in a domain where measurement settles
  disputes, is poor value. It also leaves the general question unanswered for every future candidate.

### Option C — Keep the roster and decide per-candidate later

- **Pros.** Zero decision cost now; no risk of a premature general rule.
- **Cons.** The roster is read as intent. Leaving two entries that analysis shows should not ship invites a
  future wave to implement them on the roster's authority. Deciding later also means deciding it repeatedly.

### Option D — Add a "no consultant where a lens exists" rule instead

- **Pros.** Simpler, harder to game, reaches the same verdict on performance. This is the `dissent:`
  position and it is strong.
- **Cons.** Over-fits to the current five-lens catalog. Security is a lens *and* a domain whose errors are
  archetypally silent; a flat prohibition would rule out a security consultant on structural grounds
  rather than on merit. The silence criterion at least asks the question that matters.

## Consequences

**Positive.** Two roster entries removed before they cost anything. The Performance lens gains the dimension
most relevant to what Praxion actually builds. A general criterion now exists, so the next candidate is
evaluated against a stated rule rather than by re-litigation. The `lens-collision` field acquires a sharper
meaning at zero implementation cost.

**Negative.** The criterion is judgement-shaped and can be argued either way by a motivated author. Removing
`queueing-modeler` deletes the one candidate §13 identified as the genuine non-decomposable residue of a
rejected identity — if capacity modelling later proves to need standing to object, this decision must be
revisited rather than worked around. Discipline #2 ships ahead of its own evidence gate.

**Neutral.** The Lens Catalog is untouched, honouring its closed-catalog rule; nothing here adds or edits a
lens. `dec-303`'s peer-not-lens framing is re-affirmed and given a sharper operational test.

## Disconfirmation

**Falsifier.** If, after `evidence-appraiser` accumulates dispositions, its accepted-challenge rate is
indistinguishable from what a lens-style always-on reference would have produced — that is, if its
challenges are consistently things the architect would have caught by reading the skill — then "standing to
object" is not the load-bearing property and the criterion is wrong.

**Steelmanned runner-up.** Option D. The silence criterion asks the author to predict whether an error
would have surfaced — a counterfactual, and counterfactuals are exactly where motivated reasoning lives. A
structural rule ("a domain with a lens does not get a consultant") is checkable by anyone in seconds,
requires no judgement, and cannot be reverse-engineered to a desired conclusion. Its cost is over-fitting to
the current catalog, but a catalog that is closed by its own rule is a stable thing to over-fit to. The
honest assessment is that Option D is more robust and Option A is more correct, and this decision preferred
correctness on the bet that the criterion will be applied by parties willing to be argued out of a candidate.

**Reversal trigger.** Two signals, either sufficient: (a) a discipline is admitted or refused on the silence
criterion and the decision is later judged to have been driven by the desired outcome rather than the test —
the gameability the dissent predicts, observed; or (b) a performance or capacity decision goes wrong in a way
measurement did not catch in time, which would falsify the claim that performance errors surface through
normal feedback and would reopen `queueing-modeler` specifically.

## Prior Decision

This re-affirms `dec-303` rather than superseding it. That decision held that a discipline consultant is a
peer sub-architect and not a Lens-Catalog lens, left the catalog untouched, and converted the deferred
lens-collision condition into a mandatory registry field plus a recorded reversal trigger. All of that
stands. What changes is the *interpretation* of a non-`none` `lens-collision` value: it was read as an
obligation to document an escalation relationship before shipping, and is now read first as evidence that
the discipline may not warrant existing. The field, its mandatory status, and the fitness test asserting it
are unchanged.
