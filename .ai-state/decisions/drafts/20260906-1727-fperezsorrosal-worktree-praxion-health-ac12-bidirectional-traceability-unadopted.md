---
id: dec-draft-6f149b5a
title: Praxion deliberately does not adopt AC12's bidirectional REQ-to-element traceability convention
status: proposed
category: behavioral
date: 2026-09-06
summary: The req_ids / architectural_elements convention stays unpopulated in Praxion at 1 real .c4 model and 9 archived specs, where the check would find orphans by construction rather than by drift. AC12's skip note gains a clause so a permanent skip reads as a decision, not a backlog item.
tags: [sentinel, traceability, aac, likec4, spec-driven-development, adoption]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-health
pipeline_tier: full
dissent: Non-adoption is the default that never gets revisited. A convention nobody has to populate is a convention nobody populates, and the reversal trigger below is a promise made by the party that benefits from not keeping it. If the check is worth specifying in full — and AC12's row is one of the longest in the sentinel table — the honest options are to populate it or to retire it, not to leave a fully-specified check permanently dormant behind an ADR that makes the dormancy respectable.
affected_files:
  - agents/sentinel.md
  - docs/aac-dac.md
---

## Context

Sentinel finding S-12: AC12 (traceability orphans) has never activated. Its precondition is
that the bidirectional convention be populated by at least one LikeC4 element carrying
`metadata.req_ids` **or** at least one archived SPEC carrying `architectural_elements:`
frontmatter. Measured in this checkout on 2026-09-06:

- `.c4` files: **2** — `docs/diagrams/architecture/src/architecture.c4` (the real model) and
  `tests/fixtures/minimal.c4` (a fixture).
- Elements carrying `req_ids`: **0**.
- Archived specs under `.ai-state/specs/`: **9**.
- Specs carrying `architectural_elements:`: **0**.

So AC12 skips with an INFO note on every run, and has since it shipped. The open question is
whether the convention should be adopted (populate both sides, so the check activates) or
whether non-adoption should be recorded as a decision.

The adoption cost is not the initial backfill — it is the standing obligation. Every future
architect adding a component to the model would owe a `req_ids` list, and every archived spec
would owe an `architectural_elements:` list, in perpetuity, maintained by hand. The yield is
orphan detection: a REQ no element claims, or an element citing a REQ no spec declares.

At Praxion's current shape that yield is close to zero and the noise is close to total. Nine of
the nine archived specs predate the convention, so a naive backfill of the element side would
report **every REQ in every archived spec as an orphan** — a wall of WARNs describing the
backfill's own incompleteness rather than any real drift. Producing signal instead of noise
would mean retro-annotating nine historical specs against a model that has itself changed
underneath them, which is archaeology, not traceability.

## Decision

**Praxion does not adopt the bidirectional traceability convention.** `req_ids` stays absent
from `.c4` elements and `architectural_elements:` stays absent from archived SPEC frontmatter.
AC12 continues to skip, and the skip is now a recorded decision rather than an unexamined
default.

**AC12's specification is not weakened and not retired.** The check stays fully specified in
`agents/sentinel.md`, with its Bash reader, its severity ladder and its golden bad-case
intact. It is dormant-by-decision, and it activates the day either side is populated — by
Praxion or by any managed project, for which this decision says nothing.

**One text change, so the skip is documented rather than latent.** AC12's row (and, if the
paired site needs it, the AaC subset in `docs/aac-dac.md`) gains a clause to the effect that:

> A project may record a deliberate non-adoption of the bidirectional convention as an ADR.
> When such a decision exists, the skip note cites it, so that a permanent skip reads as a
> decision rather than as an unworked backlog item.

The clause is deliberately project-agnostic — the sentinel specification must not hard-code
Praxion's own stance — and it makes the *difference* between "not yet populated" and "decided
not to populate" legible in the report, which is the same three-state discipline AC12's
existing skip-note requirement already enforces for its other preconditions. The planner
schedules the edit; `docs/aac-dac.md` is a paired site per `agents/sentinel.md`'s own note and
must be checked in the same commit.

## Considered Options

### A — Adopt: backfill both sides, activate the check

Pros: the check earns its specification; traceability becomes mechanically enforced. Cons: nine
historical specs need retro-annotation against a model that has drifted since they were
written; a partial backfill produces an orphan-WARN wall describing the backfill, not the
codebase; a standing hand-maintenance obligation on every future architect and verifier for a
project whose model has a single real `.c4` file.

### B (chosen) — Record deliberate non-adoption; keep the check specified and dormant

Pros: no false-signal wall; no standing obligation; the check survives intact for the day the
substrate justifies it; the skip becomes legible. Cons: a fully-specified check stays dormant
indefinitely, and non-adoption decisions are the ones least likely to be revisited (see
`dissent:`).

### C — Retire AC12 from the sentinel check set

Pros: honest about a check that has never run; removes specification weight from a long table.
Cons: throws away a correct and reusable specification. AC12 is written for *managed projects*
as much as for Praxion, and a managed project with a REQ-heavy spec corpus and a rich model is
exactly where it earns out. Retiring it because Praxion's substrate is thin would be
generalising from the self-host.

### D — Adopt on the element side only (populate `req_ids`, leave specs alone)

Pros: half the cost. Cons: AC12's element-side orphan check would then flag every `req_ids`
entry as an orphan, because no archived spec declares any REQ. Half-adoption is strictly worse
than either whole.

## Consequences

**Positive.** No noise floor introduced into sentinel reports. No standing annotation tax. The
skip stops reading as an unworked item, which is the specific defect S-12 named. The check
remains available and correct for managed projects and for a future Praxion with a richer
model.

**Negative.** A specified check stays dormant, and the specification weight in
`agents/sentinel.md` is paid every read for a check that does not run here. Traceability from
REQ to architectural element stays a matter of prose and reviewer attention in Praxion's own
pipelines. The reversal trigger below depends on someone noticing the condition, which is the
weakness `dissent:` names.

## Disconfirmation

**Falsifier.** A verification or sentinel pass finds a real REQ-to-element drift — a REQ
implemented against a component the spec never named, or a component whose justifying REQ was
dropped — that AC12 would have caught. One such finding makes the "yield is close to zero"
premise false and this decision wrong.

**Steelmanned runner-up (Option A).** The measurement problem AC12 addresses is real and gets
worse silently. Praxion's `.c4` model is small *now*; adoption is cheapest at exactly this
size, and every component added before adoption raises the future backfill cost. The
orphan-wall objection is an argument about *sequencing* — populate the spec side first, then
the element side — not about the convention. Deferring until the substrate is big enough to
justify the check guarantees the backfill happens when it is most expensive, which is the
classic shape of a debt that is always rational to defer once more.

**Reversal trigger.** Any of three: (i) the falsifier above; (ii) the LikeC4 model grows past
roughly a dozen `component` elements, at which point prose-level traceability stops being
reviewable by attention alone; (iii) a managed project adopts the convention and reports that
AC12 produced actionable findings — external evidence that the check earns out, which would
make Praxion's own non-adoption a self-host exception rather than a considered stance.
