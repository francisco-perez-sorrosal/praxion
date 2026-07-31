---
id: dec-draft-3d84b767
title: Wave 2 ships zero new consulting disciplines, on operational grounds rather than criterion failure
status: proposed
category: architectural
date: 2026-07-31
summary: Closes the Wave-2 roster with no new discipline. cost-economist is excluded as absorbed by the Performance lens; cognitive-ergonomist and data-steward are deferred, not refused — the reasoning that would have refused data-steward was withdrawn under challenge. The binding reason is operational: discipline #2 is merged but unreleased, so a #3 decision is premature.
tags: [multidisciplinary-identities, discipline-consultant, roster, wave-2, expansion-gate, type-ii-error, lens-collision, ship-zero]
made_by: user
agent_type: orchestrator
branch: worktree-wave2-multidisciplinary
pipeline_tier: full
re_affirms: dec-306
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - docs/multidisciplinary-identities-evidence.md
  - .ai-state/CONSULT_LEDGER.md
affected_reqs: []
dissent: Ship-zero is the outcome the convener held before the evidence was gathered, and every statistical argument originally offered for it was withdrawn under challenge — leaving a single operational reason (discipline #2 is unreleased) that would be trivially removed by cutting a release, and that has no logical bearing on whether data-steward is warranted. A decision whose stated grounds are fully replaced during its own deliberation, while its conclusion does not move, is better explained by the conclusion having been fixed in advance than by the new reasoning. The honest alternative was to ship data-steward: it passes the silence criterion on the convener's own analysis, its Type-II cost is undetectable by construction, and adding it costs one registry row and zero always-loaded bytes.
---

## Context

Wave 2's charter was the §12.2 roster: three candidates (`cost-economist`, `cognitive-ergonomist`,
`data-steward`) left "Still waiting" by `dec-306`, each requiring evaluation against that decision's
silence criterion — *a discipline earns a consultant only when its errors are silent.*

The convener reached a provisional ship-zero verdict, then convened a `statistician` consult against
its own verdict, with round-0 isolation enforced. Seven challenges were raised. **Six were accepted
(`switch-now`), one deferred, none dismissed.** The verdict survived; almost none of its original
reasoning did.

Three findings from that consult are load-bearing here.

**The expansion gate reads *not yet informative*, and now for a precise reason.** Per `dec-304`, both
standing conditions must hold before the estimate is read as evidence at all. After fixing a counting
defect the consult found: `statistician` n=3 consults, `evidence-appraiser` n=2, **zero
`dismiss-with-rationale` rows across either**. Condition (b) (`n ≥ 3`) now clears for `statistician`;
condition (a) (all three disposition values observed) does not, for either. The convener declined to
manufacture the dismissal that would have cleared it — see § Consequences.

**No Type-II instrument exists anywhere in the design.** The consult offered a falsifiable test: name
any artifact, gate, ledger, falsifier, or audit that would fire if a warranted discipline had been
wrongly excluded. None could be named. Worse, the asymmetry is *created by* `dec-306`: a criterion
selecting for disciplines whose errors do not surface selects, by construction, for a population whose
wrongful exclusion is undetectable. Composed with the registry's own reversibility (adding a discipline
is one row plus at most one skill file, zero always-loaded bytes — this wave's own removal of two
candidates proves removal is equally cheap), the decision-theoretically defensible bias runs *toward*
the detectable error. Ship-zero is not the conservative choice; it is the choice that maximises the
share of error the project can never observe.

**The `data-steward` rejection rested on a broken estimator.** The draft argued Praxion's
data-governance decision surface is thin, evidenced by an artifact grep. An artifact search can only
find decisions someone already recognised as decisions — the estimator is anti-correlated with the
estimand. That rate is **unestimated**, not low.

## Decision

**Wave 2 ships zero new consulting disciplines.** The roster closes as:

| Candidate | Disposition | Basis |
|---|---|---|
| `cost-economist` | **Excluded — will not ship** | Absorbed by the Performance lens. `skills/performance-architecture/references/agent-era-performance.md` (added by `dec-306`) covers token budget, spawn cost, and cost-per-useful-outcome, and states at line 63 that per-spawn cost is unrecoverable unless captured at the time — verbatim the argument `td-071` makes. Gating that knowledge behind a spawn subtracts availability. The consult explicitly left this candidate untouched: where the absorbed-by-lens finding holds, the Type-II cost is near zero because the knowledge is delivered anyway |
| `cognitive-ergonomist` | **Deferred** | Not refused. The exclusion rested on a claim that agent-facing ergonomics errors surface through sentinel's token-budget dimension, Agent Readiness LLM-judged criteria, and eval scores. That surfacing claim is **asserted, not measured**. The handoff's "overlaps the context-engineer agent" rationale was checked and found weak — one incidental hit for cognitive-ergonomics vocabulary in `agents/context-engineer.md` — and is not relied on |
| `data-steward` | **Deferred under unmeasured Type-II risk** | It passes the silence criterion on this convener's own analysis: retention, consent, and lineage violations produce no signal until an audit or breach. Its decision surface in Praxion is **unestimated**, not thin. It remains the concrete motivating instance for the project-local overlay (`td-064` / `dec-305`) — a managed project handling regulated data has the surface Praxion may lack |

**The binding reason for shipping nothing this wave is operational, not statistical.** `td-073`:
discipline #2 (`evidence-appraiser`) is merged on `main` but absent from `v0.18.0`; no installed copy
has ever received it. Deciding discipline #3 while #2 has not reached a single user is premature on
grounds no sample size can rescue. **This reason expires the moment a release is cut**, and the
deferrals above are expected to be re-opened at that point rather than left to lapse.

**Three claims from the provisional verdict are withdrawn, not reworded:**

1. That the candidates failing by three *different* routes evidences a discriminating criterion. Three
   rejections and zero acceptances leaves sensitivity unestimable; independent rejection routes raise
   P(reject) whether or not the criterion discriminates. A positive control against `security` —
   which `dec-306` names as a domain with both a lens and archetypally silent errors — is **owed and
   not run**.
2. That `data-steward` fails the criterion. It does not; its decision surface is unmeasured.
3. That this consult tested `dec-304`'s falsifier. It cannot: that falsifier requires two *independent*
   readers, and a consultant convened by the convener on the convener's framing is not one. The
   falsifier remains **untested**.

## Considered Options

### Option A — Ship zero, deferrals expiring at the next release (chosen)

- **Pros.** Does not add a discipline whose warrant is unestimated. Keeps the decision reversible in
  the direction that is cheap. Names the missing Type-II instrument rather than pretending restraint is
  free. The operational reason is checkable by anyone in one command.
- **Cons.** The conclusion did not move while its grounds were wholly replaced — see `dissent:`. It also
  accumulates exclusively the error the project cannot measure, for one more release cycle.

### Option B — Ship `data-steward`

- **Pros.** The consult's strongest position, and the `dissent:` above. It passes the silence criterion
  on this convener's own analysis; adding it costs one registry row and zero always-loaded bytes; the
  Type-I error it risks is detectable and cheap to reverse, while the Type-II error avoided is neither.
- **Cons.** Its `fires-when` predicate would have to be authored against a decision surface nobody has
  measured, and `dec-302` requires a restrictive predicate — "any privacy question" is not one. Shipping
  a third discipline into a distribution that has not yet delivered the second compounds `td-073`.

### Option C — Ship `data-steward` gated behind the project-local overlay

- **Pros.** Puts the discipline where its decision surface actually lives (a managed project handling
  regulated data) rather than in Praxion, which may have none.
- **Cons.** The overlay is designed (`dec-305`) but **not implemented**, and its load-bearing half is
  unproven — the Wave-1 spike would not have licensed the decision. Blocked on `td-064`.

### Option D — Defer the whole roster question with no analysis

- **Pros.** Zero cost now.
- **Cons.** Leaves §12.2 reading "Still waiting" indefinitely, and re-derives the same analysis next
  wave. The `dec-306` criterion would go another cycle without ever being applied to a candidate it did
  not itself select.

## Consequences

**Positive.** The roster no longer reads "Still waiting" against any candidate. `cost-economist` is
closed permanently rather than re-litigated each wave. Two counting defects in the shipped fitness
helpers were found and fixed as a direct result of convening the consult. The Type-II blind spot is now
named in a durable artifact instead of being an unexamined property of `dec-306`.

**Negative.** Ship-zero accumulates, for at least one more release cycle, exclusively the error class
this design cannot detect. The `dissent:` is not answered by this decision — it is recorded so a later
reader can weigh it. Two deferrals now depend on someone noticing that a release has been cut.

**Neutral — and worth recording.** Condition (a) of `dec-304` remains unmet because the convener
declined to manufacture a dismissal. All seven dispositions were fixed on the merits and written down
**before** computing their effect on the standing conditions, at the consult's own suggestion. The
gate stays un-cleared, which is the informative outcome: a `dismiss-with-rationale` produced by a
convener one row away from unblocking its own gate would satisfy the condition by construction and
measure nothing.

## Disconfirmation

**Falsifier.** If a release ships `evidence-appraiser`, the deferrals are re-opened, and
`data-steward` is then admitted on the *same* evidence available today — no new measurement of its
decision surface, no positive control run — then the operational reason recorded here was a
rationalisation, and the `dissent:` was correct that the conclusion preceded its grounds.

**Steelmanned runner-up.** Option B. The consult's `CH-03` is the strongest argument in this record and
it is not refuted, only outweighed by a scheduling fact. Adding `data-steward` costs one registry row;
the criterion it satisfies is the project's own; the error avoided is undetectable and the error risked
is measured by five separate instruments. Against that, the only thing Option A has is that discipline
#2 has not shipped — which is a fact about a release pipeline, not about whether the discipline is
warranted. A reader who thinks scheduling should not govern a design question should read this decision
as wrong, and that reading is defensible.

**Reversal trigger.** Any of three: (a) a release ships `evidence-appraiser`, which removes the binding
reason and obliges re-opening both deferrals; (b) a data-governance decision in Praxion or a managed
project goes wrong in a way no existing instrument surfaced, which would confirm the Type-II asymmetry
empirically; (c) the positive control against `security` returns "rejected", which would show the
silence criterion rejects a domain `dec-306` itself names as archetypally silent, falsifying the
criterion rather than any candidate.

## Prior Decision

This **re-affirms** `dec-306` rather than superseding it. The silence criterion stands and is applied
here for the first time to candidates `dec-306` did not itself select. What this decision adds is a
limit `dec-306` did not state: the criterion selects for a population whose false-negative cost is
structurally unobservable, so applying it without a Type-II instrument systematically biases toward
exclusion. `dec-306`'s Falsifier is also recorded as **unidentified rather than underpowered** — no
sample size makes it estimable, because the ledger's eleven columns encode nothing that separates a
challenge the architect would have caught anyway from one it would not.
