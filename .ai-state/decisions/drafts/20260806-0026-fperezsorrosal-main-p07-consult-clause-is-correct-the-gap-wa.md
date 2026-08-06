---
id: dec-draft-259cd344
title: P07's consult clause is correct; the missing producer was in the always-loaded tier
status: proposed
category: behavioral
date: 2026-08-06
summary: 'Sentinel P07 was reported as a consumer with no producer, reading a fragment field nothing writes. Three documents require the write-back and all predate the violating consults; the two always-loaded surfaces omit it, which is why the convener wrote ledger rows and skipped the fragment. Keep P07, widen it to count an absent field as undispositioned, and state both Round-2 obligations in the summary tier.'
tags: [sentinel, discipline-consultant, gate-liveness, progressive-disclosure, consult-ledger, false-finding, always-loaded]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: direct
dissent: 'Twelve of twelve live challenges failed this check while every disposition sat correctly in the ledger — a check whose real-world hit rate is 100% is empirically indistinguishable from one that is simply wrong, and declaring the pipeline at fault rather than the check is the more self-serving of the two readings.'
affected_files:
  - agents/sentinel.md
  - agents/CLAUDE.md
  - rules/swe/swe-agent-coordination-protocol.md
  - tests/fixtures/sentinel/consult_no_disposition/
---

## Context

A sentinel report raised as Important that P07's consult clause "reads a field nothing produces." The reasoning was that P07 flags a `CONSULT_<discipline>.md` `### CH-NN` entry whose `**Disposition:**` is empty or still the convener placeholder, while every producer instruction routes dispositions to `.ai-state/CONSULT_LEDGER.md` instead — making P07 a consumer with no producer, and its findings false by construction. Live evidence appeared to support it: two consults under one task slug, twelve challenges between them, **twelve undispositioned fragments and twelve correct ledger rows**.

The premise does not survive checking. Three documents require the in-fragment write-back:

- `agents/discipline-consultant.md` — *"You leave the `Disposition:` and `Rationale:` fields present and empty **for them to fill**."*
- `skills/software-planning/references/coordination-details.md` § Round 2 — *"Disposition and rationale are recorded per-entry, **in place, in the same `CONSULT_<discipline>.md` fragment**."*
- the same file, § Termination — a consult *"is done only when `## Not Challenged` is populated and **every `## Challenges` entry carries a disposition**."*

Both clauses landed at 08:51Z and 08:12Z on the day the consults ran at 23:10Z and 00:05Z — roughly fourteen hours earlier. The protocol was in force.

The supporting quote was also misread. `rules/swe/swe-agent-coordination-protocol.md` warns that *"a challenge whose reasoning lives **only** in the ephemeral fragment is lost at cleanup"* — that is the **"Every disposition needs a durable home"** clause, arguing the fragment is not *sufficient* and must be joined by an ADR, a tech-debt row, or a `wontfix` tombstone. It does not route dispositions away from the fragment. "Not sufficient" was read as "not wanted."

So P07 is correct and the twelve findings are real. What remains is the more interesting question: **why did a competent convener skip an obligation stated three times?**

Because neither place it was reading says so. Round 2 carries two obligations, and the surfaces disagree on how many:

| Surface | Loaded | Ledger row | In-fragment write-back |
|---|---|---|---|
| `rules/swe/swe-agent-coordination-protocol.md` | always | stated | **absent** |
| `agents/CLAUDE.md` § Who may convene | on `agents/` | stated | **absent** |
| `coordination-details.md` § Round 2 | on demand | stated | stated |
| `agents/discipline-consultant.md` | consultant only | — | stated |

The convener did exactly what its always-loaded context prescribed. The asymmetry is reinforced mechanically: the ledger obligation is gated by `fitness/tests/test_discipline_registry_invariants.py`, which names a missing `(task-slug, discipline, stage)` triple, while the fragment obligation is gated only by P07 — a periodic audit nobody had run against these artifacts. **The gated half was met and the ungated half was not**, which is the ordinary outcome and not a lapse of care.

A second defect surfaced while grounding this. One of the two fragments carries **no `**Disposition:**` field at all**: that consultant improvised a trailing `## Disposition Summary` table of `<!-- convener -->` cells instead of the per-entry fields. P07 was phrased to flag a field that "is empty or still the placeholder" — an *absent* field is neither, so the fragment that deviates furthest from the template is the one most likely to evade the check. The fixture directory covered only the placeholder case.

A third, quieter one: the fixture directory had two bad cases' worth of proof that P07 **fails** correctly and no proof at all that it **passes** correctly on a consult that raised challenges. Its only control was a fragment with no `## Challenges` section. A P07 that flagged every fragment carrying challenges at all would have satisfied every file in the directory.

## Decision

**Keep P07's consult clause.** It is a correct check that caught a real, unremediated process violation. Do not repoint it at `CONSULT_LEDGER.md`.

Four changes, none of them to what P07 is trying to detect:

1. **Widen P07 to count an absent field as undispositioned**, naming the summary-table substitution explicitly so it reads as the same finding rather than an exemption. A check that only inspects a field the fragment declined to write is satisfied by the omission.

2. **State both Round-2 obligations in the always-loaded tier.** `rules/swe/swe-agent-coordination-protocol.md` and `agents/CLAUDE.md` now say the adjudication lands in two places — the `### CH-NN` entry beside the claim it answers, *and* a ledger row — with "both, never either" stated in as many words. Cost: 59 tokens against 1,611 of headroom.

3. **Add the two missing fixtures.** A second golden bad-case for the omitted-field shape, and — the more valuable one — a control in which challenges were raised *and* adjudicated, so the gate is shown to pass for the right reason and not merely to fail for the right one.

4. **Bring the two live fragments into compliance** by transcribing the twelve dispositions already recorded in the ledger, and remove the improvised summary table so one run's drift is not copied by the next reader. This is transcription, not adjudication: every value already existed.

## Considered Options

### Option A — Repoint P07's consult clause at `CONSULT_LEDGER.md`

Check ledger coverage by `(task-slug, discipline, challenge-id)` instead of reading the fragment.

**Pros:** the ledger is durable where the fragment is deleted at cleanup; coverage is mechanically checkable; today's twelve findings disappear.

**Cons:** they disappear *because the violation is redefined as compliance*, which is the failure mode this project's own anti-cheating test names first. It would also delete the only gate on an obligation three documents impose, and it would do so on the strength of a premise the evidence refutes. And the two surfaces are not redundant: the ledger answers "was this adjudicated," the fragment answers "adjudicated *how*, next to the claim it answers" — a reader reconstructing the argument needs the second, which is exactly why the protocol asks for both.

### Option B — Add a write-back instruction to the convener

The reported remedy. It is a **no-op**: the instruction exists in three places already. Acting on it would have added a fourth statement of an unfollowed rule while leaving the reason it went unfollowed untouched.

### Option C — Keep P07 unchanged, fix only the producer surfaces (chosen, extended)

Addresses the root cause at minimum cost. Chosen, but extended with the P07 widening and the two fixtures, because the root-cause fix alone leaves the omitted-field shape unproven — and that shape is the one a live fragment actually exhibits.

## Consequences

**Positive.** The obligation is now visible where the convener reads rather than one indirection away. P07 covers both ways a disposition can be missing. The fixture directory proves the check in both directions. Twelve real dispositions are back beside the claims they answer.

**Negative.** 59 tokens of always-loaded budget, and roughly four lines of overlap between the summary tier and the reference tier — the duplication progressive disclosure exists to avoid. Accepted deliberately: the omitted clause is not detail, it is one of two halves of an obligation, and a summary that states one half reads as complete. The failure mode of omission here is silent and was demonstrated; the failure mode of duplication is drift between two sites, which is visible and which the paired-site convention already handles.

**Neutral.** P07's row grows by ~60 words in a file already over its warn band. The AC11 retirement in the same session removed more than this adds.

## Disconfirmation

Included voluntarily. This decision **declines to fix a reported Important finding and declares the check correct instead** — precisely the shape where the record must show what would prove it wrong.

**Falsifier.** A consult in which the convener, working from the amended always-loaded surfaces, records ledger rows and still leaves fragment entries unfilled. That would show the omission was never an information problem and the write-back obligation is being rejected in practice rather than missed — at which point the honest response is to ask whether the fragment surface earns its keep, not to state the rule a fifth time. Equally falsifying: a convener that fills the fragment and skips the ledger, which would mean the amendment traded one omission for another.

**Steelmanned runner-up.** Option A's real argument is not the one advanced for it. It is that the fragment is deleted at cleanup, so a disposition recorded *only* there is lost — which the coordination protocol itself says. If fragment dispositions are never read again after cleanup, then P07 gates an artifact whose content has no downstream consumer, and the ledger genuinely is the surface that matters. The reason it still loses: the fragment is read *during* the pipeline, by the orchestrator deciding whether to loop back and by the verifier checking adjudication, and P07 runs while the artifact still exists. Its value is in-flight, not archival, and being ephemeral is not the same as being unread.

**Reversal trigger.** The consult mechanism accumulates enough history for the fragment-versus-ledger question to be answered with data rather than argument — say twenty consults across five task slugs. If the ledger is the only surface anything actually reads back, retire the fragment field and repoint P07 then, as a decision grounded in observed reads rather than in a misread warning.
