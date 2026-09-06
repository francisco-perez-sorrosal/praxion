---
id: dec-310
title: The convener seals a lens-run prior list before spawning a consultant, and the seal is tamper-evident rather than tamper-proof
status: accepted
category: architectural
date: 2026-07-31
summary: td-081 resolved by .ai-state/CONSULT_PRIORS.md -- a sibling append-only single-writer file with two tables (priors sealed and committed before the spawn, one classification row per challenge at Round 2), joined on the (task-slug, discipline, stage) triple, with a cross-file fitness gate. The comparison group is a run of the discipline's own bound skill, not the convener's un-primed prior. The measured quantity is framing + standing jointly, never standing alone. The seal's claimed strength is tamper-evidence, not proof.
tags: [consult-ledger, discipline-consultant, instrumentation, falsifier, estimand, gate-liveness, tech-debt, seal, lens-vs-consultant, framing]
made_by: agent
agent_type: systems-architect
branch: worktree-td-081-sealed-prior
pipeline_tier: standard
re_affirms: dec-306
affected_files:
  - .ai-state/CONSULT_PRIORS.md
  - fitness/tests/test_discipline_registry_invariants.py
  - agents/discipline-consultant.md
  - agents/CLAUDE.md
  - skills/software-planning/references/coordination-details.md
  - commands/consult.md
  - scripts/finalize_adrs.py
  - rules/swe/agent-intermediate-documents.md
  - .ai-state/DESIGN.md
  - docs/multidisciplinary-identities-evidence.md
dissent: A convener that wants to cheat still can. Every artifact in this repository passes through the convener's hands before it becomes a commit, so no in-repo seal is tamper-proof, and the two witness checks bite only while the pipeline's gitignored .ai-work/ still exists -- after cleanup the record is self-consistent and uncorroborated. And even a perfectly honest series answers a confounded question -- the A-to-C delta mixes disciplinary framing with standing, so it cannot settle the claim dec-306 actually made, and the arm that would separate them is named and unbuilt. Worse, the estimand may never be computed at all -- this pays a per-consult tax on a mechanism convened five times in its lifetime, to produce a rate whose only named reader is a hypothetical future ADR that re-opens a criterion nobody has asked to re-open. The honest alternative was to amend dec-306's Falsifier to say plainly that it is not estimable at this project's consult volume, and spend nothing.
superseded_in_part_by:
  - dec-draft-fd158a05
---

## Context

`dec-306` established that a discipline earns a consultant only when its errors are silent, resting on the claim that a consultant's entire marginal contribution over a lens is **standing to object** — not knowledge. Its Falsifier makes that claim testable: if a consultant's challenges are consistently things the architect would have caught by reading the skill, the criterion is wrong.

A `statistician` consult (`CH-06`, dispositioned `defer-with-rationale`) established that the Falsifier is **unidentified, not underpowered**. It is a two-arm comparison and the disposition ledger records one arm. The ledger's eleven columns encode nothing that separates a challenge the convener would have caught anyway from one it would not, and its eleven-column contract is closed by an exact-equality fitness assertion. `dec-309` recorded that finding and filed `td-081`; until it is built, `dec-306`'s Falsifier must not be cited as live.

Three facts constrain the design space, each verified rather than assumed.

1. **No site instructs a convener to record anything before the spawn.** All four paired contract sites — the consultant agent's Round-2 paragraph, the `agents/CLAUDE.md` convening paragraph, the coordination-details dialogue protocol, and the `/consult` command — govern post-report disposition only.
2. **A twelfth ledger column is structurally unavailable**, and a sibling append-only single-writer file joined on the `(task-slug, discipline, stage)` triple is the working precedent for exactly this constraint (`dec-308`).
3. **The witness problem is about durability and mediation, not existence.** A hook-written `agent_start` record for the consultant does exist, timestamped and not authored by the convener. It is nevertheless never committed in practice, rotates at 10 MiB into a gitignored segment, and — decisively — is a working-tree file like every other, so committing it re-enters the convener's mediation.

## Decision

**Add `.ai-state/CONSULT_PRIORS.md`**: a sibling append-only file, single writer = the convener, joined on the same triple, carrying two tables written at two moments — `## Sealed Priors` **before the spawn**, `## Challenge Classification` at Round 2 alongside that consult's ledger rows. A cross-file fitness gate fails when a post-boundary consult has no sealed prior, or a post-boundary challenge no classification. The series begins at `2026-07-31T03:00:00Z`; all five pre-existing consults are exempt by construction, with no skip-list.

Three sub-decisions carry the weight.

**The comparison group is a run of the discipline's own bound skill, not the convener's un-primed prior.** `dec-306`'s Falsifier names its arm twice and both namings agree: *what a lens-style always-on reference would have produced*, *what the architect would have caught by reading the skill*. So the sealed step is to **run the lens**: having decided to convene, the convener loads the matched registry row's `binds-to` skill through the `Skill` tool and works that row's `challenge-obligations` — the consultant's own Round-1 checklist — against the draft. Recording what the convener merely already believed would measure a strictly smaller set, classify more challenges as novel, and bias the rate **upward** — the one direction that flatters the mechanism precisely when it is worthless.

**The measured quantity is framing + standing, jointly — never standing alone.** `dec-306` holds that the consultant's *"entire marginal contribution over a lens is standing to object. Not knowledge, not quality — standing."* That collapses three things into two. Knowledge is content and a lens delivers it fully; `dec-306` is right there. **Framing** — the disposition to notice that something *is* a statistical claim, and to partition a problem the way a discipline partitions problems — is not delivered by a lens, because a lens is read *through the reader's own framing*. Praxion's own dossier §4.1 already named this when it resolved the persona paradox: *"Methodological framing supplies a **procedure**."* A procedure is not knowledge. `dec-306` compressed procedure into standing and lost the distinction. So the arms are: **A** = same knowledge, convener's own framing, no second party (what this file seals); **C** = same knowledge, disciplinary framing, second party (the consultant). The A→C delta is therefore **framing + standing, confounded by construction**, and every statement of the estimand — this ADR, the file's `Named consumer` section, the evidence dossier — must say so. Reporting it as a test of standing alone would be the mis-specified-estimand error this decision exists to fix, committed one level up.

The reference consult supplies the concrete instances: `CH-01` identified an artifact grep as *an estimator anti-correlated with its estimand* — a sentence absent from `applied-statistics`, produced by the reflex to ask "what is your estimator?" of a paragraph nobody had thought of as containing one; `CH-03` partitioned the decision into Type-I and Type-II and noticed only one had instruments. Neither is a knowledge lookup.

**Arm B is named as a future decomposition and deliberately not built.** Arm **B** — a *generic* agent handed the same `binds-to` skill and asked to challenge — would isolate standing (A→B) from disciplinary identity (B→C). Three arms triples the per-consult cost against `n=5`, so it waits until the two-arm series has volume; the schema is built to accept it without change. It is not an academic refinement: dossier §15.2 records *"Expert Personas Improve LLM Alignment but Damage Accuracy"*, and the dossier's own comment calls its MT-Bench **Coding** regression *"the most uncomfortable single datum for this initiative: coding is Praxion's domain."* B→C could come back **negative** — disciplinary framing performing worse than a generic challenger holding the same knowledge. A design that cannot discover that is not an instrument.

The tax is real and is not the pessimization `dec-306` used to remove `performance-engineer`. That objection was that gating knowledge *subtracts availability*; this puts the discipline's knowledge into the convener's context on every consult, unconditionally, which raises availability. What rises with it is token spend — on the order of 5–15% of a consult that already costs six figures. The pass is required on **every** consult, not a sample: sampling needs a pre-registered selection rule to keep the convener from choosing which consults are measured, and at five consults ever it would produce roughly one observation per wave.

**The seal is tamper-evident, and the ADR claims nothing more.** Every artifact in this repository passes through the convener's hands before it becomes a commit; there is no path by which an independent party writes into git history without convener mediation. That is a property of the trust topology, not a budget constraint, so **no in-repo mechanism can be tamper-proof against a convener willing to edit before committing.** What is achievable is making revision a deliberate, visible, multi-step act: the file is append-only and committed *before* the spawn; the consultant records `git rev-parse HEAD` at Round 0 as `**Round-0 HEAD:** <sha>` — content-free, so Round-0 isolation is untouched, and the one datum in the consult the convener did not author; and the gate asserts both that the fragment's sha agrees with the transcribed `seal-witness` (while `.ai-work/` lives) and that the witnessed commit's tree actually contains the sealed rows (durably, absent a squash-merge). The cheat this threat model predicts — a motivated-but-honest convener writing the list after reading the challenges, in the same session — must now be executed as a deliberate fabrication of another agent's artifact, and is caught by a test the convener runs at Round 2 and by CI thereafter — the latter only because this decision also widens the Architecture workflow's `paths:` filter to include `.ai-state/CONSULT_*.md`, which it did not, so neither this gate nor `dec-308`'s ran on a consult-only change.

**The ordering constraint is part of the decision, not an implementation note.** *Decide to convene → run the lens → seal → spawn.* A convener that ran the lens first and only then decided would systematically skip the consults where the lens had already found everything — selecting away exactly the observations that would falsify the criterion. No gate can detect a consult that never happened, so ordering is the only available mitigation and it is written at all four sites.

## Considered Options

### A — Sealed lens-run prior list in a sibling file, tamper-evident (**chosen**)

Grain matches the quantity at both moments. Zero churn on the ledger's eleven-column contract. Follows the established sibling-file precedent rather than inventing a second answer to the same constraint. Costs one new `.ai-state/` artifact, one gate section, and a pre-spawn clause at four sites.

### B — Seal the convener's un-primed prior instead of a lens run

Cheaper: no skill load, no per-consult tax. Rejected because it measures the wrong arm. The bias runs upward — more challenges classified novel than the Falsifier's own comparison would license — so the instrument would make the mechanism look most valuable in exactly the case where it adds least. Precision on the wrong estimand is worse than no estimand, because it looks like an answer.

### C — A twelfth `CONSULT_LEDGER.md` column carrying `novel`/`matched`

Rejected on the closed contract (an exact-equality assertion plus every committed row) and, more fundamentally, on grain: the sealed priors have no per-challenge home at all, so a classification column would record the set difference while discarding the set it was taken against — leaving `matched` unauditable.

### D — Amend `dec-306`'s Falsifier to declare it non-estimable, and build nothing

The `dissent:` position and the honest runner-up; argued in full under Disconfirmation. Rejected because the estimand *is* identifiable — `CH-06` said the falsifier requires a design change and named the design — and declaring a falsifier permanently unmeasurable when a proportionate mechanism exists is the same defect class as a gate nobody has seen fail.

### E — An out-of-band seal: external timestamping, a second signing identity, or CI-recorded state

The only constructions that would be genuinely tamper-proof. Rejected as disproportionate: an external authority for a five-observation series, and CI state the convener still chooses when to push.

## Consequences

**Positive, and the largest item was not planned.** Checking *where this gate would actually execute* — rather than assuming — surfaced that the consult instrumentation has effectively never been gated in CI. Two facts compose: `.github/workflows/architecture.yml` is the only workflow that runs `pytest fitness/tests/`, and its `paths:` filter omits `.ai-state/CONSULT_*.md`; while `.github/workflows/test.yml` has no `paths:` filter but runs bare `pytest`, and `pyproject.toml`'s `testpaths = ["tests", "scripts"]` means a bare run collects 1,925 tests and **zero** from `fitness/`. A consult-only PR triggers the workflow that cannot see the gate and does not trigger the workflow that can. The consequence is sharper than a missing path entry: `dec-308`'s cost-coverage gate has run in CI exactly **once, on the PR that introduced it** (which touched `fitness/**` and so triggered itself) and never again on the change class it polices — and the same holds for the stray-row check `td-079` produced and the consult-identity checks. This is the strongest instance yet of the gate-liveness clause about a computed value with no live reader, compounded by the scope-fidelity clause. Widening the filter is part of this decision and repairs all four gates at once; adding `fitness` to `testpaths` was considered and rejected as a wider blast radius (it would change what `test.yml`'s coverage threshold measures) and is left as its own task. Beyond that: `dec-306`'s Falsifier acquires a producer and a named consumer, so it stops reading as a test merely waiting for data. `td-081` resolves. The set difference is recomputable by a stranger from two committed files with `grep` and `wc`, and every `matched` classification names the specific prior a reader can contest. The lens pass improves the draft as a side effect — a fixed defect cannot be raised, so it correctly counts for neither party. The ledger's eleven-column contract, its gate, and the cost series are untouched.

**Negative, stated rather than papered over.**

*The gate catches omission and inconsistency, never falsehood.* A padded list of vague concerns passes every check. The defense is auditability, not prevention — identical in kind to the residual `dec-308` accepted for hand-recorded token counts.

*The witness degrades.* After `.ai-work/` cleanup the fragment check skips and the sha becomes self-consistent and uncorroborated; a squash-merged branch also erases the witnessed commit and skips the durable check. Both skips print their reason so a permanent skip is visible rather than silent.

*Selection bias is unmitigated by anything mechanical.* A consult abandoned after the lens pass leaves no ledger row and therefore no trace. Ordering is a convention.

*The per-consult tax may shrink the series it creates.* If the extra step deters convening, the instrument reduces the population it measures.

**Neutral.** `dec-306`'s Disconfirmation block is **not edited**. Its Falsifier reads as though it is waiting for data, and after this decision that reading is correct — the design `CH-06` asked to be named is named here, and the prior register's own `Named consumer` section binds any future ADR re-opening the criterion to cite the computed rate. Amending a finalized ADR's body was considered and declined in favour of naming the producer where the data lives.

## Disconfirmation

**Falsifier.** Two signatures, either sufficient. **(i)** Six months on, `.ai-state/CONSULT_PRIORS.md` holds classification rows for at least three distinct consults, the novelty rate is computable — and no ADR, roadmap, or evaluation has ever cited it, while claims about the consultant's value continue to be made from prose. That is the named-consumer clause failing in practice, and it would mean this bought instrumentation nobody consumes. **(ii)** The gate goes red at merge and is resolved by adding a skip-list entry rather than by writing the missing rows, which is the dead-gate failure the series boundary exists to prevent.

**Steelmanned runner-up — option D, amend the Falsifier and build nothing.** The strongest case against this decision is not that the estimand is wrong; it is that **the estimand is unreachable at this project's consult rate, and building a precise instrument for an unreachable quantity is the more expensive way to be wrong.** `CH-06`'s own power note puts the requirement at roughly 20–25 challenges to separate a 0.5 novelty rate from a 0.9 — about four consults at the observed rate — and immediately adds that challenges cluster within a consult, so 20–25 is a *floor* and the clustered requirement is larger. This project has convened five consults in its entire history, across two waves, and `dec-309` deferred its whole roster partly because the second discipline had not yet reached a single user. On that trajectory a usable interval is years away, and every consult until then pays a skill load, a commit, and a classification pass to move an estimate that will still read *not yet informative*. Meanwhile the decision this instrument is supposed to inform — whether standing-to-object is load-bearing — will in practice be made, as `dec-309` made its own, on operational grounds long before the number is readable. Option D costs one paragraph: state in `dec-306` that its Falsifier requires more observations than the mechanism will generate, which is an honest limit of the same kind as the cost series' `n=1`, and stop pretending otherwise. The runner-up also has the better simplicity argument by a wide margin — no new file, no new gate, no new obligation at four sites, no per-consult tax.

The counter that decides it, and it is narrower than it looks: **the classification is useful at n=1 in a way the rate is not.** A single consult whose challenges are all `matched` against a sealed lens run is, on its own, strong qualitative evidence that the lens would have sufficed — no interval required to read it. The instrument therefore produces something legible immediately, and the rate is the long-run bonus rather than the justification. What the steelman gets right, and this decision concedes in the same words `dec-308` conceded its own, is that the file must never be read as more instrumented than it is — which is why the scope limits, the `not yet informative` standing rule, and the honest strength label are written into the file itself rather than only into this record.

**Reversal trigger.** Any of five: **(i)** three or more consults accumulate with the rate never cited by any decision-making artifact — Falsifier (i), reopen as option D; **(ii)** the gate goes red and the proposed remedy is a skip-list entry; **(iii)** a managed project's prior register is cited as evidence, which requires porting the gate out of `fitness/` into a shipped `scripts/check_*` with its own canary before the citation may stand; **(iv)** a convener is found to have written a sealed list after reading the challenges and the witness checks did not catch it — which would mean the tamper-evidence claim is weaker than stated, and the honest response is to downgrade the label rather than to add machinery; **(v)** the two-arm series reaches three or more consults with a materially non-zero novelty rate, which is the point at which arm B becomes worth its cost — because a joint framing-plus-standing effect that is real is exactly the case where knowing which half produced it changes what the project builds next.

## Prior Decision

This **re-affirms** `dec-306` rather than superseding it, with one stated limit.

What stands: the silence criterion itself; the identical-knowledge premise (a lens and a consultant deliver the same content, so a skill read by the author *is* the author thinking with better information); and the removal of `performance-engineer` and `queueing-modeler`. The removal in particular is **not** reversed here — it rested on an independent and still-sound reason, that performance errors surface through benchmarks, profilers and cost bills before they become load-bearing. Nothing below reopens it.

What is limited: the claim that standing to object is the **entire** marginal contribution. That does not survive `dec-306`'s own supporting corpus — dossier §4.1, resolving the persona paradox, records that *"methodological framing supplies a procedure"*, and a procedure is neither knowledge nor standing. A lens is read through the reader's own framing and therefore cannot supply a discipline's way of partitioning a problem. `dec-306` accounted for knowledge and standing and dropped framing, so the argument was doing more work than it could bear: the conclusions it reached remain defensible, but "standing, and nothing else" is one term short.

The practical consequence is confined to measurement, which is why a re-affirmation is the right instrument rather than a supersession. The sealed-prior series introduced here estimates **framing + standing jointly**; no artifact may report it as a test of standing alone; and the third arm that would decompose it is named in this record and left unbuilt. A future supersession of `dec-306` would need arm-B data — specifically, a B→C contrast showing disciplinary framing contributes near zero (which would restore `dec-306`'s original wording) or negative (which, given dossier §15.2's expert-persona accuracy regression on coding, would put the whole consultant construct in question rather than just its wording).
