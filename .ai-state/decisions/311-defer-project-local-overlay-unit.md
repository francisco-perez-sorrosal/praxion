---
id: dec-311
title: Defer the project-local registry overlay unit; two of its premises are falsified
status: re-affirmation
category: architectural
date: 2026-07-31
summary: The overlay, the fitness rooting fix, and the originating extensibility gap defer together — the rooting defect has no producing invocation path, and the overlay's own enforcement checker never ships to the deployment it targets.
tags: [multi-perspective-analysis, discipline-consultant, extensibility, registry, plugin-distribution, gate-liveness, deferral]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-integrity-and-overlay
pipeline_tier: full
re_affirms: dec-305
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - agents/discipline-consultant.md
  - commands/consult.md
  - fitness/tests/conftest.py
  - claude/aac-templates/fitness-conftest.py.tmpl
dissent: >
  The overlay is roughly thirty lines of prose in four places plus three
  vacuous-when-absent assertions, and leaving an accepted ADR unbuilt is itself debt that
  compounds; the strongest case against deferring is that the multi-site objection has a
  sanctioned mitigation the rule itself prescribes, so shipping would follow the rule
  rather than violate it, and only the unshipped-checker argument actually blocks.
---

# Defer the project-local registry overlay unit; two of its premises are falsified

## Context

Three open tech-debt rows form one unit: the originating extensibility gap (a managed
project cannot add a consulting discipline), the accepted-but-unbuilt overlay decision
(`dec-305`), and a rooting defect in the shipped fitness suite's `project_root` fixture. The
rows carry an explicit coupling: ship the overlay and the correctly-rooted gate together, or
neither, because "the overlay alone would have a managed project's registry entries silently
ignored by a gate still resolving to the plugin's own root."

Two research passes and direct verification in the authoring worktree established facts the
rows do not reflect.

## Decision

**Defer all three rows as a unit. Do not implement the overlay in this pipeline.** No
partial ship, no cherry-pick. Correct the rows' notes; write no code.

The deferral rests on two falsified premises, not on cost.

**Premise 1 — the rooting defect has no producing invocation path.** The row states the
version-nested plugin cache is "the ONLY path by which a managed project receives the
fitness suite today". It is not the path. Onboarding's AaC phase and the greenfield
scaffolder both install `fitness/` into a managed project by **copying templates** from
`claude/aac-templates/` — including a `conftest.py` template — into the project's own tree,
where `Path(__file__).resolve().parent.parent.parent` resolves to the project's own root and
is **correct**. Nothing instructs a managed project to run the plugin-cache copy; the
fitness README documents a repository-relative invocation. The defect is therefore *latent*:
it belongs to an execution path no instruction produces. Fixing it now would wire a fix for a
consumer with no producer — the exact defect class this pipeline exists to close.

A real live sub-finding surfaced while checking this, and it is worth more than the row as
written: the shipped `fitness/tests/conftest.py` and its `aac-templates` counterpart are
byte-identical duplicates with **no sync check**, while an equivalent sync gate exists for
the canonical-blocks family. Hardening one would silently not harden the other.

**Premise 2 — the overlay is not decomposition-ready.** The row asserts the architecture is
settled and only step decomposition remains. `dec-305`'s enforcement design reads: "Both
files are parsed by the one existing table parser, so 'a valid row' cannot drift between
them." That is true of *enforcement* and false of *resolution* — both real readers, the
convener before spawn and the consultant after, resolve a discipline name by an LLM reading
the markdown table, and the only mechanical parser is referenced by the fitness suite alone.
Implementing union-and-collision therefore means authoring the semantics as prose at four
independent textual sites.

Decisively: **the enforcement layer never reaches the deployment it is designed for.** The
template set copied into a managed project does **not** include the discipline-registry
invariants file. A managed project would receive the overlay's *resolution* — skills, agents
and commands install globally — with **none** of its *validation*. `dec-305`'s fail-loud
contract leans explicitly on "row-shape validity of overlay rows (reusing the existing shape
checker)"; that checker never ships. This is a producer-less consumer inside the accepted
decision's own enforcement design, and it is not repairable by a step plan.

**The coupling constraint's stated rationale is void, and is recorded as such.** The reason
given for never splitting the unit presumes a managed project runs the registry gate. It does
not receive that gate at all. The causal link does not exist. The instruction is honoured
anyway — all three defer — because the honest verdict is uniform.

**Revisit trigger, named so the deferral is bounded.** Re-open when **either**: (a) a
concrete request to add a project-local discipline arrives, which is the demand signal
`dec-305` was designed for and has never received; or (b) the resolution-mechanism question
is settled — whether both readers resolve the union through a small deterministic helper
invoked as a subprocess (single source of truth, mechanically testable, four prose sites
collapsed to one pointer, and a validation path that actually ships) versus prose at four
sites. **(b) is a supersession of `dec-305`, not a patch**, because it changes the mechanism
rather than the policy, and it enlarges the unit by whatever the helper costs.

**This ADR re-affirms `dec-305` rather than superseding it.** The *decision* — union with
collision as a hard error, absence silent and free — survives every fact found here
untouched. What is falsified is an implementability premise in its Enforcement paragraph.
Superseding would require the replacement mechanism, which is exactly what trigger (b) is
for.

**Two adjacent rulings, recorded here because both were asked and both are now settled.**
First, the onboarding row's proposal to scaffold a project-local overlay stub is **void**:
`dec-305`'s Option F rejects exactly that, on grounds nothing found here challenges — a
header-only overlay is a populated-looking absence, and absence should cost nothing. The
surviving half of that row is the three consult-ledger skeletons plus a registry pointer, and
that half is **independently warranted and not blocked by this deferral**: the consult
mechanism's producer ships globally, so a managed project can convene a consult today and the
convener is instructed to append to ledger files that do not exist. Second, the originating
row's description of the overlay as a precedence chain is **stale**; `dec-305` rejected
precedence in both directions and decided union with collision-as-error. The row is corrected
by note, not by re-decision.

## Considered Options

### Option A — Ship the unit as `dec-305` describes (rejected)

Prose at four sites plus three fitness assertions, closing an accepted-but-unbuilt ADR.
Rejected on premise 2's second half: it ships a fail-loud contract to the one deployment
where the mechanism making it true is absent.

### Option B — Ship the overlay, defer the rooting fix (rejected)

Forbidden by the unit constraint, and independently wrong: it would ship the feature whose
validation gap is the actual blocker while deferring the row whose premise turned out not to
hold.

### Option C — Ship the rooting fix alone as cheap defensive hardening (rejected)

Superficially attractive — it is a small change to a small fixture. Rejected because the
value claim is void: no invocation path produces the failure, and the change would not reach
a managed project anyway without also editing the template, whose divergence nothing detects.
Hardening the template pair is a *different* and better-grounded change, and it belongs to
whoever files that row.

### Option D — Redesign the overlay now around a deterministic resolver (rejected for this pipeline)

The likely correct eventual answer, and the substance of trigger (b). Rejected as in-scope
work: it is a supersession requiring its own design pass, its own probe of whether the
convener can invoke a subprocess pre-spawn, and its own decision about a validation path that
ships. Folding it into a pipeline already closing eight gate-integrity rows would be exactly
the scope creep the behavioural contract forbids.

## Consequences

**Positive.**

- No code ships on top of a falsified premise, and no consumer is wired for a producer that
  does not exist.
- The originating extensibility gap remains visibly open rather than being marked resolved by
  a feature that would not work in the deployment it targets.
- Two rows gain corrected premises, so the next reader does not re-derive them.
- A better-grounded finding — the unsynced duplicate template pair — is surfaced for filing.
- The deferral is bounded by two concrete triggers, one of which is a demand signal that
  costs nothing to wait for.

**Negative / accepted.**

- An accepted ADR stays unbuilt for longer, and unbuilt accepted decisions are their own
  debt class. The mitigation is that this ADR records *why*, so the state is explained rather
  than merely persistent.
- The user-authorship axis of the extensibility requirement stays closed. Accepted because no
  user is blocked today: no managed project has attempted step one, which is itself the
  evidence trigger (a) waits for.
- Three rows stay open on a pipeline whose purpose was closing rows. Recorded plainly rather
  than dressed up.

## Disconfirmation

**Falsifier.** If a managed project is found running the *plugin-cache* fitness suite — by an
instruction, a documented workflow, or observed practice — premise 1 collapses and the
rooting fix becomes live work. If the template set is found to include, or is changed to
include, the discipline-registry invariants file, premise 2's decisive half collapses and
Option A becomes shippable as written. Either finding should reopen this immediately.

**Steelmanned runner-up.** Option A is stronger than the rejection makes it sound. The
four-textual-sites objection has a mitigation the rule itself prescribes — an explicit
cross-reference note naming the paired sites at each location — and the rule's own worked
example is these very files. Under that mitigation, shipping follows the rule rather than
violating it, and the remaining cost is roughly thirty lines of prose plus three assertions
that are vacuous when no overlay exists. The overlay's resolution half genuinely does ship
and genuinely would work; a user with a well-formed overlay row would get the feature.
Everything then turns on how much weight the unshipped shape-checker carries — and a
defensible reading is that fail-loud resolution by prompt is *most* of the contract, with the
shape checker a convenience. This decision weights it higher because the whole pipeline is
about gates that claim more than they enforce, and shipping one more would be
self-contradictory. A reasonable architect could weigh it the other way.

**Reversal trigger.** Trigger (a): the first concrete request for a project-local discipline.
Trigger (b): a decision on deterministic-resolver versus prose-at-N-sites, which arrives as a
supersession of `dec-305`. Additionally (c): if the `aac-templates` family gains a sync gate,
the template-versus-source divergence stops being a blocker and Option C's cost drops
materially.

## Prior Decision

`dec-305` is **re-affirmed, not superseded.** Its decision — a project may define disciplines
in an optional project-owned overlay; both readers resolve against the **union** of the two
tables; a key present in both is a hard `[BLOCKED]` error rather than a precedence rule;
absence is silent and costs nothing — survives every fact established here without amendment.
Options A through F were re-read against the new evidence and none of their rejections is
weakened by it.

What this ADR falsifies is a single sentence in `dec-305`'s Enforcement paragraph: *"Both
files are parsed by the one existing table parser, so 'a valid row' cannot drift between
them."* That holds for the fitness-test enforcement layer and not for runtime resolution,
which is prompt-interpreted at both read moments; and the enforcement layer it names is not
among the files a managed project receives. `dec-305` was authored without that distinction
available.

**A future supersession must supply, and nothing less will do:**

1. A resolution mechanism whose union-and-collision semantics have **one** source of truth
   rather than four prose sites — most plausibly a small deterministic helper both readers
   invoke, together with a probe establishing whether a convener can invoke it *pre-spawn*.
2. A **validation path that ships**: some mechanism reaching a managed project that enforces
   overlay row shape, so the fail-loud contract is true where it is claimed and not only in
   Praxion's own tree.
3. Evidence that the feature is wanted — at minimum one concrete request — since the decision
   has stood unbuilt without a single user reaching step one.

Absent all three, re-opening `dec-305` would be re-litigation without new evidence, which is
what the re-affirmation route exists to prevent.
