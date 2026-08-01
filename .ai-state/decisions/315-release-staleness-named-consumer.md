---
id: dec-315
title: The release-staleness advisory names the release cut as its required reader
status: accepted
category: implementation
date: 2026-07-31
summary: Satisfy gate-liveness clause 6 for check_release_staleness.py by naming its reader and decision point in the gate's own definition, wiring it into the release command, and correcting the document its output already contradicted.
tags: [gate-liveness, named-consumer, release, advisory, plugin-distribution]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-integrity-and-overlay
pipeline_tier: full
affected_files:
  - scripts/check_release_staleness.py
  - commands/release.md
  - docs/multidisciplinary-identities-evidence.md
---

# The release-staleness advisory names the release cut as its required reader

## Context

`scripts/check_release_staleness.py` lists plugin artifacts registered at `HEAD` but absent
from the last `v*` tag — invisible to marketplace installs until a release is cut. The check
is correct, CI-wired, and **deliberately advisory**: its own docstring argues that firing per
feature commit would contradict the pinned-stable version model. That design is sound and is
not in question.

What failed is clause 6 of `rules/swe/gate-liveness.md`: nothing is named as the advisory's
required reader. The gap is self-demonstrating. A committed dossier states that an artifact
is "MERGED … NOT YET RELEASED" — false as of two subsequent tags, both of which ship the
artifact's five files and its complete registry row — and the same paragraph goes on to note
that the staleness check "detected this correctly and is CI-wired; it is advisory, and
nothing consumed its output." The document records the gap and is simultaneously its first
casualty: with no named reader, a human-authored claim drifted from the gate's own output
exactly as the clause predicts.

A correction to that sentence alone would not close anything. The same drift recurs at the
next release.

## Decision

Satisfy clause 6 through the remedy the rule's own menu permits for a correctly-advisory
gate — a named reader at a named decision point, plus a golden bad-case at the gate's own
definition — rather than by making the gate blocking.

1. **`scripts/check_release_staleness.py` gains a `## Named consumer` block in its module
   docstring**, stating the obligation directly: before any committed document asserts that
   a plugin artifact has or has not shipped, the author runs the check for the tag being
   claimed and quotes the verdict. The block carries the **golden bad-case** concretely —
   a document reading "MERGED … NOT YET RELEASED" for an artifact the check reports as
   present at the named tag — so a future reader sees the failure the gate exists to prevent,
   not only the computation it performs.
2. **`commands/release.md` runs the advisory as part of the cut and records its verdict.**
   This is the decision point that actually fires on a cadence, and it is where the value is
   actionable — a maintainer about to cut a release is the one person for whom "what is
   unreleased" changes a decision.
3. **The false sentence is corrected**, so the tree stops asserting something its own tooling
   contradicts.

(1) and (2) together close the gap; (3) alone would not, which is why the finding stayed
open after the releases landed.

**Explicitly not done: making the check blocking.** Its advisory design was argued correctly
and remains correct. Clause 6 says so in as many words — what fails is sound advisory design
*plus* no named reader, and the repair is the reader.

**Flagged, not fixed:** a second advisory job in the same workflow describes itself in its own
comment as mirroring the release-staleness pattern, so it plausibly carries the identical
gap. It is outside this change's scope and is referred for filing rather than silently
widened into.

## Considered Options

### Option A — Make the check blocking with `--check` in CI (rejected)

Trivially closes the gap by forcing every commit to confront it. Rejected because it
contradicts the check's own well-argued design: firing on every feature commit between
releases would fight the pinned-stable version model, and clause 6 explicitly warns against
"fixing" a correctly-advisory gate by making it blocking.

### Option B — Generate a published release-status artifact and diff computed against published (rejected)

The strongest mechanical option: a generated block that documents derive from, plus a check
that reddens when the block drifts from a fresh computation. Rejected as disproportionate —
it introduces a new artifact, a generator, and a documentation convention to close one gap
whose observed instance is a single sentence in a single dossier. Worth revisiting if the
drift recurs after this change.

### Option C — A detector scanning documents for release-status phrases (rejected)

Grep committed documents for "NOT YET RELEASED", "SHIPPED", and similar, requiring each to
be adjacent to a verification token. Rejected as fragile prose-matching with an unstatable
computed scope — the same objection that disqualified a lexical heuristic elsewhere in this
pipeline. It would also be a gate whose own scope fidelity could not be checked.

### Option D — Correct the document only (rejected)

The minimum. Rejected because it is precisely what the finding says is insufficient: without
a named reader the drift recurs at the next release, and the corrected sentence becomes stale
again with nothing to surface it.

## Consequences

**Positive.**

- The advisory's output reaches a decision point that fires on the cadence at which the value
  matters.
- The obligation lives in the gate's own definition, so a reader of the script learns it
  without needing a report or a rule lookup.
- The golden bad-case documents the correct reading, which is the artifact clause 6 names for
  gates of this kind.
- The tree stops asserting a falsehood about its own release state.

**Negative / accepted.**

- The obligation on document authors is documentary, not mechanical: a future author can
  still write a release claim without running the check. Accepted deliberately — the
  mechanical alternative is Option B's artifact-plus-differ, whose cost exceeds the observed
  harm. If the drift recurs, that is the escalation.
- The release command grows one step.
- A sibling advisory with the same likely gap remains open, by choice, to keep this change
  surgical.
