---
id: dec-draft-f93d0d1e
title: Split detection from production in the artifact registry and make it a read source-of-truth
status: proposed
category: architectural
date: 2026-06-27
summary: Add a detection_gate field separating presence-detection (sentinel checks) from production (producers), reclassify the 3 mislabelled rows, and wire build_doc_manifest to read the registry — closing dec-251's populated-not-read dissent.
tags: [artifact-registry, declarative-spine, detection-gate, production-gate, ea-02, ea-11, registry-consumer]
made_by: user
branch: wave4b-registry-seams
pipeline_tier: standard
affected_files:
  - scripts/artifact_registry.py
  - scripts/test_artifact_registry.py
  - scripts/build_doc_manifest.py
dissent: A second gate field is more schema to keep honest; the documented `sentinel:` kind already meant "enforces presence/quality", so sharpening the comment could have addressed EA-02's labelling complaint without a structural change.
---

## Context

`dec-251` grew the artifact registry into a declarative spine with `production_gate` +
`cleanup_policy`, recording the dissent that the fields would be *populated but not read*. The
Wave-1–3 external audit then raised two related findings:

- **EA-02** — three artifacts (`TASK_BRIEF`, `INTERFACE_DESIGN`, `TRANSACTIONS_DESIGN`) named a
  `sentinel:Pxx` value as their `production_gate`. A sentinel check *detects an artifact's absence*;
  it does not *produce* it. The field whose comment reads "the gate that makes it exist" was naming
  a detector — production and detection conflated in one column.
- **EA-11** — confirmed on disk: nothing reads `production_gate`/`cleanup_policy`. dec-251's own
  dissent, realised.

## Decision

Two coupled moves that mature the spine:

1. **Separate detection from production.** Add a `detection_gate` field to `Artifact`, with its own
   vocabulary `_DETECTION_GATE_KINDS = {sentinel, none}`; remove `sentinel` from the production
   `_GATE_KINDS` (a sentinel check is never a producer). Reclassify the three rows:
   `TASK_BRIEF` → `production_gate=producer:orchestrator`, `detection_gate=sentinel:P06`;
   `INTERFACE_DESIGN` → `producer:interface-designer` + `sentinel:P07`;
   `TRANSACTIONS_DESIGN` → `producer:agentic-transactions-architect` + `sentinel:P07`. A new
   `test_detection_is_not_labelled_as_production` canary forbids any future `sentinel:` value in
   `production_gate`.
2. **Make the spine *read*.** Wire `build_doc_manifest` to import the registry's ordered dashboard
   projection instead of duplicating the `.ai-work` filename list (R18) — the first consumer that
   *reads* the registry rather than being drift-checked against it. This is the down-payment on
   dec-251's deferred "wire a consumer" and a direct answer to EA-11.

This **extends** dec-251 (it does not supersede it): the spine remains, gains a column, and gains
its first reader.

## Considered Options

### Option A — Add `detection_gate`, reclassify, wire a reader (CHOSEN)

- **Pros:** "what produces X" and "what detects missing X" become two orthogonal, grep-able facts;
  the labelling EA-02 flagged is fixed structurally; a canary keeps it fixed; R18 makes the spine
  load-bearing for at least one consumer.
- **Cons:** a second gate field is more surface to keep honest; the per-artifact `cleanup_policy`
  still has no reader (the per-dir/per-file granularity gap — see Disconfirmation), so EA-11 is only
  *partially* closed.

### Option B — Document the vocabulary, no new field

- **Pros:** zero schema change; `sentinel:` is already documented as "enforces presence/quality".
- **Cons:** production and detection stay in one column, so "list every artifact's producer" stays
  un-answerable by a grep; the audit's structural point is papered over with prose. Rejected.

### Option C — Reclassify to `producer:`, drop sentinel entirely

- **Pros:** simplest; one column, all producers.
- **Cons:** loses the P06/P07 association — the registry would no longer record that a detection
  backstop exists. Rejected: the detection info is worth keeping, just in its own column.

## Consequences

**Positive:**
- The spine answers two questions where it answered a muddled one; EA-02 is closed with a canary.
- `build_doc_manifest` stops duplicating the artifact list — one fewer drift surface.

**Negative / costs:**
- `cleanup_policy` still has no reader; EA-11 is partially, not fully, closed (tracked forward).
- One more field for future artifact authors to populate correctly.

## Disconfirmation

- **Falsifier:** if, a year on, `detection_gate` is still `none` for every artifact except the
  three reclassified here, the field earned no breadth and Option B's "document, don't add" would
  have been right.
- **Steelmanned runner-up (Option B):** the `sentinel:` kind was *already* documented as
  presence-enforcement; a reader who read the vocabulary would not have been misled, and a sharper
  one-line comment is a strictly smaller change than a new column + new constant + new tests.
- **Reversal trigger:** if the per-artifact `cleanup_policy` reader never materialises (the
  granularity gap proves fundamental) and `detection_gate` gains no new members, collapse both back
  into documented `production_gate` semantics and retire the second column.
