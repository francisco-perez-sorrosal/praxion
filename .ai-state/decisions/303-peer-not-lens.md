---
id: dec-303
title: The discipline consultant is a peer sub-architect, not an evaluation lens — Lens Catalog untouched in Wave 1
status: accepted
category: architectural
date: 2026-07-30
summary: A discipline consultant is architecturally a shadow sub-architect with standing to object, not a Lens-Catalog lens; Wave 1 carries no supersession, and the deferred lens-collision condition becomes a mechanically-visible registry field plus a recorded reversal trigger.
tags: [multidisciplinary-identities, discipline-consultant, lens-catalog, agent-boundary, design-synthesis, peer-sub-architect, deferred-condition]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
affected_files:
  - agents/discipline-consultant.md
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - skills/software-planning/references/design-synthesis.md
affected_reqs:
  - REQ-01
  - REQ-02
  - REQ-18
dissent: A disciplinary consultant that evaluates a design against a domain criterion is behaviorally indistinguishable from a lens, and the Lens Catalog's "No new lenses" clause exists precisely to stop the design space from being re-entered through a differently-named door; calling the same function a "peer" to avoid a supersession is a naming manoeuvre, and the first colliding discipline (performance-engineer) proves the collision is real rather than hypothetical.
---

## Context

Two Wave-A research lenses, forbidden from reading each other, reached **directly contradictory** verdicts on
whether a disciplinary consultant is a *lens* (an evaluation criterion applied to options, governed by the closed
Lens Catalog in `skills/software-planning/references/design-synthesis.md`) or a *peer* (an agent with standing to
object, governed by the shadow-sub-architect precedent). The context-engineer rated it CRITICAL and demanded a
Wave-1 ADR supersession of the Lens Catalog; the internal-surface lens found the catalog needs no edit at all.
A disagreement that survives isolation marks genuine ambiguity, not noise.

The stakes are process cost. `design-synthesis.md` states: *"No new lenses. If a future need arises for a lens
not in this table, file an ADR supersession rather than editing this reference to introduce one."* A lens reading
therefore makes every future discipline a supersession event.

The context-engineer's CRITICAL finding was specific and correct on its own terms: the proposed
`performance-engineer` discipline binds to `skills/performance-architecture/SKILL.md` — the *same* owning artifact
as the catalog's existing Performance lens — so two different mechanisms (a free, mechanical, always-fires-at-
Phase-7 lens note vs. a gated, adversarial, multi-round consult) would point at one body of knowledge with no
documented relationship between them. Per MAST, undocumented overlapping scope is the top failure category.

## Decision

The consultant is a **peer sub-architect**, not a lens. The Lens Catalog is **not** edited and **not** superseded
in Wave 1.

Three things make this a structural finding rather than a naming choice:

1. **Verified precedent.** Neither `interface-designer` nor `agentic-transactions-architect` appears anywhere in
   `design-synthesis.md` today, despite both applying domain judgment to architectural options. The category
   "domain specialist that is not a lens" already exists in this repository and is already load-bearing.
2. **Mechanically different shape.** A lens is a criterion the *architect itself* applies during a synthesis
   sweep — one line per option, no second party. The consultant is a separate context window that reads sources
   in isolation, then challenges a draft, then receives a disposition. A lens cannot be dispositioned because
   there is nobody to disposition. This is the same distinction that eliminated the skills-only option: absorbed
   knowledge produces no tension.
3. **Wave-1 scope dissolves the live collision.** Wave 1 ships exactly one discipline, `statistician`, whose
   binding (`applied-statistics`) is a genuinely new artifact with no Lens-Catalog counterpart. The CRITICAL
   finding was specifically about `performance-engineer`, which is deferred.

The deferred collision is made **mechanically visible instead of remembered**: every registry row carries a
required `lens-collision` field (`none`, or the named lens whose owning artifact it shares). A future discipline
that collides must either (a) declare the collision and document an **escalation** relationship — the lens is
the cheap always-fires default; the consultant is the gated escalation when the sweep signals a contested or
high-stakes decision — or (b) carry an ADR supersession of the Lens Catalog. The committed fitness test asserts
the field is populated on every row, so the condition surfaces when the offending row is written.

**Consequential narrowing of the intake hypothesis.** The consultant authors **no ADR fragments**. An agent with
no decision authority recording a decision it did not make is incoherent; its surviving challenges become the
architect's `## Disconfirmation` block and `dissent:` frontmatter — exactly what those surfaces exist for. This
removes the `rules/swe/adr-conventions.md` "Who Writes ADRs" edit from the change set (−~240 always-loaded bytes)
and sharpens the boundary against the two existing sub-architects, which *are* decision-authority peers.

## Considered Options

### Option 1 — Lens: add discipline entries to the Lens Catalog, with a Wave-1 supersession

- **Pros:** honours the catalog's stated closure protocol literally; the Performance overlap is resolved at the
  point of decision rather than deferred; one registry of evaluation criteria instead of two adjacent concepts.
- **Cons:** factually wrong about the mechanism — a lens has no second party and cannot be dispositioned, so the
  dialogue requirement (the user's stated sub-goal 4) is unsatisfiable inside the lens abstraction. It also
  contradicts the standing precedent of two existing sub-architects that are absent from the catalog, and makes
  every future discipline a supersession event, which is the opposite of the extensibility mandate.

### Option 2 — Peer sub-architect, catalog untouched, collision deferred as a mechanically-visible field (chosen)

- **Pros:** matches the verified precedent and the actual mechanism; zero Wave-1 supersession; the deferred
  collision cannot be silently forgotten because a required registry field plus a fitness assertion carry it;
  the escalation relationship (cheap lens → gated consult) is a genuinely better model than duplication.
- **Cons:** the collision is deferred, not solved — `performance-engineer` still needs its escalation
  relationship written before it ships, and a future author could technically write `lens-collision: none`
  incorrectly (the fitness test asserts presence, not correctness).

### Option 3 — Rename the catalog concept to absorb both

- **Pros:** removes the taxonomy question entirely.
- **Cons:** a wide edit to a closed, cited reference in service of a naming problem; touches an artifact many
  agents depend on for a change that alters no behaviour. Rejected on Stay Surgical grounds.

## Consequences

**Positive:** no Lens-Catalog supersession in Wave 1; the two mechanisms stay distinguishable and their future
relationship is pre-specified as escalation rather than duplication; the `lens-collision` field turns a
remembered condition into a checked one; the no-ADR-authorship narrowing removes an always-loaded edit and
tightens the MAST role boundary.

**Negative:** two adjacent concepts (lens, discipline) now coexist and a reader must learn the distinction;
the Performance collision is real and merely postponed.

**Risks accepted:** a future author adds a colliding discipline with `lens-collision: none` and the escalation
relationship never gets written. The fitness test catches an *empty* field, not a *wrong* one — this residual
gap is accepted rather than solved with a hardcoded lens-name cross-check, which would re-introduce a
per-discipline always-loaded coupling.

## Disconfirmation

- **Falsifier:** a consult whose challenges are, in substance, one-line-per-option criterion notes that the
  architect could have generated itself during a Phase-7 sweep — i.e. the consult produces lens-shaped output.
  If the first several `statistician` consults read like lens rows rather than falsifiable claims naming a
  decision, the peer framing was wrong and the function belonged in the catalog.
- **Steelmanned runner-up:** Option 1. The catalog's closure clause is not decoration — it exists because the
  design space keeps trying to grow new evaluation criteria, and "peer, not lens" is exactly the kind of
  re-entry-through-a-different-door the clause anticipates. The runner-up is strongest on the observation that
  `performance-engineer` binds to the identical owning artifact as an existing lens: if two mechanisms point at
  one artifact, the parsimonious reading is that there is one concept with two invocation costs, and the
  catalog should own both. Deferring that collision rather than resolving it is the weakest point of the
  chosen option.
- **Reversal trigger:** any future discipline whose name or `binds-to` artifact matches a Lens-Catalog lens
  **and** for which no escalation relationship can be coherently stated. At that point the two concepts have
  genuinely merged and the Lens Catalog supersession the context-engineer asked for becomes correct. The
  `lens-collision` registry field is the tripwire that surfaces this at row-authoring time.
