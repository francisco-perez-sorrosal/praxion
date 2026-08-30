---
id: dec-339
title: Two regimes for weakly-grounded Rust guidance — contested practices ship as per-project ADR prompts; no-source-exists content ships as conditioned decision procedures
status: accepted
category: behavioral
date: 2026-08-30
summary: Two distinct regimes govern weakly-grounded Rust guidance. REGIME A (sources disagree) — every contested area the research named (MSRV policy, error granularity, anyhow in libraries, clippy::pedantic, source-level deny(warnings), cancellation safety, workspace layout, preludes, module file layout, mocking doctrine, date/time crate, ORM) ships with both positions, their evidence tiers, and a routing sentence to a per-project ADR; no shipped artifact enforces a contested default. REGIME B (no tier-1/2 source exists) — architecture-shaped content is re-expressed as a conditioned decision procedure gated on an observable project property, or deferred to a dedicated research pass; a marker string stating the absence is a disclosure that rides along on residual prescription, never the mitigation. Each subject is bound to exactly one regime.
tags: [rust, contested-practice, adr-prompt, evidence-tier, guidance-design, noise-budget, conditioned-test, evidence-appraisal]
made_by: agent
agent_type: systems-architect
branch: worktree-data-structures-pillar
pipeline_tier: full
affected_files:
  - skills/rust-development/SKILL.md
  - skills/rust-development/references/error-and-panic.md
  - skills/rust-development/references/toolchain-and-workspace.md
  - skills/rust-development/references/essential-crates.md
  - skills/rust-development/references/unsafe-and-concurrency.md
  - skills/rust-development/references/project-scaffolding.md
  - skills/testing-strategy/references/rust-testing.md
  - skills/architectural-fitness-functions/contexts/rust.md
affected_reqs: [REQ-04, REQ-10, REQ-11]
---

## Context

The Rust research produced an unusually clean separation between settled and unsettled practice.
On one side, Rust's canon is exceptionally codified: the API Guidelines are a literal, citable
`C-XXX` checklist, formatting is a solved question owned by `rustfmt`, and the error, panic,
visibility, unsafe, and documentation doctrines are stated in near-identical terms by multiple
primary sources.

On the other side, both research lenses independently produced a list of areas where authoritative
sources genuinely disagree or where no tier-1 source exists at all: MSRV policy (the sharpest live
disagreement in the ecosystem), error-type granularity, `anyhow` in library crates,
`clippy::pedantic` as a project default, source-level `deny(warnings)`, async cancellation safety,
workspace splitting thresholds, shipping a prelude, `mod.rs` versus named-file module layout,
mocking doctrine, the `jiff`/`chrono`/`time` choice, and ORM selection. Separately, the research
flagged hexagonal architecture in Rust as having **no tier-1 or tier-2 source** in either
direction — the weakest-grounded material it produced.

Both lenses converged on the same warning, stated independently: do not put contested items into
lint-style rules, because enforcing a contested default is how a toolkit acquires a reputation
for noise.

That warning has a mechanism worth naming. A toolkit that emits confident directives on genuinely
contested questions gets disabled by the users who disagree — and when it is disabled, the users
lose the *uncontested* guidance too. The cost of over-prescribing is not the bad advice; it is
the good advice that stops being delivered.

## Decision

Two regimes, distinguished by *why* the evidence is weak. Regime A handles disagreement among
sources; Regime B handles a recorded absence of sources. Each subject binds to exactly one.

### Regime A — sources disagree

Every contested area named above is documented in shipped Rust artifacts as a **decision prompt**,
not a directive. The required shape for each:

1. State the competing positions and who holds them.
2. State the evidence tier honestly — primary specification, maintainer documentation, expert
   practitioner writing, or popularity with no argument behind it.
3. Route the choice explicitly to a per-project ADR rather than resolving it.

### Regime B — no tier-1/2 source exists (added by amendment; see below)

Regime A answers *sources disagree*. It is the wrong instrument for content where the research
recorded a positive finding of **absence** — "no tier-1 or tier-2 source found," which is a
different epistemic situation and needs a different artifact shape. For that content:

1. **Re-express it as a conditioned decision procedure** — a test the reader applies, gated on an
   observable project property. The corpus supplies the exemplar: *can you name a second
   implementation that will actually exist? A test double counts; a hypothetical future database
   does not.* That asserts nothing about architecture; it asks a question, so it survives
   paraphrase and needs no hedge. Other admissible gates: crate count, published-vs-internal,
   presence of a library consumer, whether a named tool is in use.
2. **Content that cannot take that form is deferred**, not shipped with a caveat. Deferring costs
   nothing a later dedicated research pass could not recover.
3. **A marker is a disclosure, not a mitigation.** Where content legitimately stays
   prescription-shaped, the containing file carries the literal string
   `Evidence status: no tier-1 or tier-2 source exists`. This is a **statement of absence** — an
   absent source cannot be *named*, so any requirement to name it is unsatisfiable by
   construction. The marker's job is reader disclosure; it must never be recorded as the
   mitigation for "guidance is applied as authoritative," because it changes what a reader could
   know, not what a generating agent does, and a hedge is the first thing lost in restatement.

**One subject, one regime.** A subject filed under both regimes yields contradictory artifact
shapes — Regime A says "present positions, route to an ADR," Regime B says "here is the layout,
disclosed" — and an implementer silently resolves the contradiction. Workspace layout is bound to
**Regime A alone** (the research classifies it as contested-and-single-source).

Additionally:

- **Version numbers are paired with their verification path.** Shipped artifacts name channels and
  editions (stable identifiers) rather than releases (perishable ones); where a release figure is
  unavoidable it ships with the command or registry that confirms it.
- The **uncontested** canon is stated directly and without hedging. This decision is not a licence
  to hedge everywhere; a document that qualifies every claim is as useless as one that
  over-prescribes. `rustfmt` defaults are not a policy question, `correctness` lints are not
  optional, and error types must be `Send + Sync + 'static` — those are stated flatly.

## Considered Options

### Option 1 — Pick a defensible default for each contested area and ship it as guidance

**Pros.** Maximally actionable; a reader gets an answer instead of a decision. Reduces the
per-project ADR burden. Consistent with how the Python and TypeScript skills handle several
choices (a named default linter, a named default test runner).

**Cons.** On genuinely contested questions the default will be wrong for a substantial fraction of
projects, and being wrong confidently is what gets a guidance surface distrusted. MSRV policy in
particular is credited by the ecosystem's own discussion with causing fragmentation — Praxion
adding a twelfth opinion helps nobody.

### Option 2 — Document positions and route to a per-project ADR (chosen)

**Pros.** Preserves the toolkit's credibility on the much larger uncontested surface. Produces a
durable per-project record of a real decision instead of an unexamined inherited default. Matches
what both research lenses independently recommended.

**Cons.** Less immediately actionable; a reader wanting a quick answer gets a decision to make.
Grows the per-project ADR count. Requires authoring discipline to keep the hedging confined to the
genuinely contested list rather than spreading.

### Option 3 — Omit contested areas from shipped artifacts entirely

**Pros.** Zero risk of encoding a wrong default; shortest artifacts.

**Cons.** The contested questions are exactly the consequential ones. Omitting MSRV policy from a
Rust guidance surface leaves a Praxion-managed Rust project with no MSRV declaration at all, which
the Cargo documentation treats as itself a finding.

## Consequences

### Positive

- The guidance surface stays trustworthy on the large body of genuinely settled Rust canon.
- Contested choices become recorded per-project decisions with rationale, which is exactly what
  ADRs exist for — the toolkit produces better records rather than more defaults.
- The low-evidence marker gives a discipline-consultant or reviewer a locatable target rather than
  prose that must be re-audited from scratch.

### Negative

- More reader effort at the point of decision, and more ADRs per Rust project.
- The boundary between "contested" and "settled" is itself a judgment; a future reader may
  disagree about which list an item belongs on. Mitigated by naming the source and tier for each,
  so the classification is auditable rather than asserted.

### Neutral

- The contested list is expected to shrink over time (a pre-1.0 crate reaching 1.0, a stalled
  project declaring itself finished or abandoned). Staleness markers on the crate and toolchain
  sections make that revisit scheduled rather than accidental.

## Amendment — evidence-appraiser loop-back (2026-08-30)

Regime B, the one-subject-one-regime rule, and the marker-as-disclosure demotion were **added by
amendment** after a `discipline-consultant` in the `evidence-appraiser` discipline appraised this
pipeline's architecture-shaped evidence imports. The convener dispositioned all eight challenges
`switch-now`; fragment at `.ai-work/rust-first-class/CONSULT_evidence-appraiser.md`, ledger rows in
`.ai-state/CONSULT_LEDGER.md`.

**Why amendment and not supersession.** The original record decided *how weakly-grounded Rust
guidance ships*. Regime B answers the same question for a case the original under-specified — it
adds a branch, reverses no clause, and leaves Regime A's contested-practice protocol operative
verbatim. Nothing here contradicts the prior text, so flipping the record to `superseded` would
misrepresent a scope extension as a reversal and orphan the still-binding Regime A.

**What the appraisal established that this record now carries:**

- A marker is a **disclosure**, not a mitigation. It changes what a reader could know, not what a
  generating agent does; and the citing discipline's own core finding is that hedges are the first
  casualty of restatement, which a skill-file → agent-context → generated-artifact chain is.
  Recording a marker as the sole mitigation for "guidance applied as authoritative" overstated its
  coverage.
- The original Decision's marker bullet was **literally unsatisfiable** — it required naming the
  absent tier-1/2 source. An absent source cannot be named. Corrected to a statement of absence
  with a specified literal string, which is greppable and therefore verifier-checkable.
- A **uniform** low-evidence tag over an asymmetric base discards the one directional finding the
  research established (its own critique is better-supported than its prescription). Regime B's
  conditioned-test form carries the direction; a flat tag cannot.
- Three items were **deferred** rather than shipped with caveats: prescriptive architecture
  guidance that resists the conditioned-test form, the task-automation convention survey, and a
  layering-enforcement mechanism for single-crate Rust projects.

**Falsifier for Regime B.** Name an observable difference in a *generated* Rust project between a
marked prescription and an unmarked one. If none can be named, marking was never a mitigation and
the conditioned-test reformulation is doing all the work — which is the claim Regime B rests on.
If, conversely, a conditioned test proves to be routinely stripped back into a prescription
downstream, Regime B is no better than the marker it replaced and deferral becomes the only honest
option.

**Scope note.** Regime B is stated for Rust because that is where the research recorded the
absence. Nothing about it is Rust-specific; if a second language's research produces the same
"no tier-1/2 source found" finding, this record is the precedent to cite rather than re-derive.
