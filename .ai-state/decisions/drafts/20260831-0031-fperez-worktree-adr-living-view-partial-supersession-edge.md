---
id: dec-draft-9faf4a80
title: Partial supersession is an edge property — reciprocal id lists converting the full edge, with a named status×edge enforcer
status: proposed
category: behavioral
date: 2026-08-31
summary: 'A decision narrowing some clauses of an earlier one converts the full supersedes/superseded_by edge into reciprocal supersedes_in_part / superseded_in_part_by id lists; the narrowed record keeps its non-terminal status, contradiction shapes are caught by a new adr_health status_edge_conflicts class surfaced as sentinel DH06, and all five existing instances migrate before DL06 loses its carve-out.'
tags: [adr-conventions, decision-lifecycle, supersession, schema, frontmatter, data-structure, migration]
made_by: agent
agent_type: systems-architect
branch: worktree-adr-living-view
pipeline_tier: standard
affected_files:
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - agents/sentinel.md
  - scripts/query_adrs.py
  - scripts/finalize_adrs_crossrefs.py
  - scripts/adr_health.py
  - scripts/regenerate_adr_index.py
  - dashboard_app/src/server/view-models/adr-graph.ts
  - .ai-state/decisions/040-eval-framework-out-of-band.md
  - .ai-state/decisions/112-aac-dac-traceability-sentinel-ac-traceability-checks.md
  - .ai-state/decisions/203-sentinel-t03-threshold-exception.md
  - .ai-state/decisions/219-project-profile-yaml-schema.md
  - .ai-state/decisions/231-defer-eval-lens-and-ach-matrix.md
---

## Context

**The defect is a contradiction, not an absence.** An earlier draft of this decision claimed `dec-263` carries no `supersedes` and that "frontmatter can express neither side". That is false on disk: `263-retire-future-designed-producers.md:18` reads `supersedes: dec-219`, and `219-project-profile-yaml-schema.md:18` reads `superseded_by: dec-263` while its `status` is `accepted`. Frontmatter is not silent — it **over-claims a full supersession** against a record its own status says is live. A consumer reading frontmatter alone is told the whole record is replaced; the body says one clause was.

Re-measured against the correct denominator — *supersession relations*, not all ADRs — partial supersession is not rare. Of 347 finalized records, 18 carry `superseded_by`. **Five of those 18 (27.8%) are partial supersessions**, each confirmed against its narrowing record's `## Prior Decision` prose:

| Narrowed | `status` | `superseded_by` | same-id `re_affirmed_by` | Narrowing record's own words |
|---|---|---|---|---|
| dec-040 | `accepted` | dec-204 | yes | "narrows only clause 3 … re-affirms clauses 1, 2, and 4" |
| dec-112 | `re-affirmation` | dec-323 | yes | "only its AC11 clause" |
| dec-203 | **`superseded`** | dec-328 | yes | "partially superseded … its verifier clause survives unchanged" |
| dec-219 | `accepted` | dec-263 | **no** | "partially supersedes dec-219 … retires only the *Phase 8f output* producer clause" |
| dec-231 | `accepted` | dec-232 | **no** | "Supersedes … only on the ACH-matrix clause" |

One relation, **five different encodings and three different `status` values**. That divergence is user-visible, not cosmetic: `query_adrs.py`'s `DEFAULT_STATUSES` and `adr_health.py`'s `_TERMINAL_STATUSES` both key off `status` alone, so dec-040's surviving clauses are retrievable while **dec-203's surviving verifier clause is invisible to both tools** and its reference decay is never classified.

The convention itself is not missing. Sentinel DL06 carries a named "Carve-out — partial supersession" prescribing `supersedes`/`superseded_by` plus a same-id `re_affirmed_by` entry, with `## Prior Decision` discriminating scope; `dec-328` invokes it by name. But `rules/swe/adr-conventions.md` never documents it, so the convention lives only in the checker — which is exactly why five instances produced five encodings. **The failure is enforcement and discoverability, not expressiveness.** This decision addresses both, and `dec-347`'s promotion of frontmatter to a load-bearing retrieval key is what turns a documentation gap into a correctness defect.

Two structural facts frame the shape. First, partiality is a property of the **edge**, and the schema has nowhere to put an edge attribute — there is no edge object, only two bare id lists in two files. Second, `re_affirmed_by` is currently **overloaded**: it means both "a later ADR re-examined and re-affirmed this whole record" and "the clauses a partial supersession left standing", discriminated only by whether the same id also appears in `superseded_by` — a discriminant nothing names and nothing checks.

## Decision

**1. Two reciprocal, optional, list-typed frontmatter fields.**

| Field | On | Meaning |
|---|---|---|
| `supersedes_in_part` | the narrowing record | ids of prior decisions whose *some* clauses this one replaces |
| `superseded_in_part_by` | the narrowed record | ids of later decisions that replaced some of this record's clauses |

Clause identification stays in the narrowing record's `## Prior Decision`, which becomes **required** when `supersedes_in_part` is present. No clause anchor enters frontmatter (see Option B).

**2. This is a conversion, not an addition.** When a pair is recorded as partial, the **full `supersedes` / `superseded_by` edge for that same pair is removed** and replaced by the partial pair; the same-id `re_affirmed_by` entry that the DL06 carve-out used as the survival marker is removed with it. Leaving the full edge in place would put two contradictory edges between the same two records — the exact illegal state this decision exists to eliminate.

**3. Mutual exclusion, stated as an invariant.** For any ordered pair (A, B), **at most one** of `A.supersedes ∋ B` and `A.supersedes_in_part ∋ B` may hold, and symmetrically on B. `supersedes ⊕ supersedes_in_part` per target pair.

**4. The narrowed record keeps a non-terminal status.** `accepted` (or `re-affirmation`, per dec-112) — never `superseded`, `retired`, or `rejected`. dec-203's current `superseded` is a live instance of this violation and is corrected by the migration.

**5. The invariants have a named enforcer.** `scripts/adr_health.py` gains a `status_edge_conflicts` finding class, surfaced by a new auto sentinel check in the DH family, covering:

| Shape | Conflict |
|---|---|
| (a) | same target in `supersedes` and `supersedes_in_part` |
| (b) | `superseded_in_part_by` non-empty while `status` is terminal |
| (c) | narrowing record's own `status` ∈ {`retired`, `rejected`} |
| (d) | same id in `superseded_in_part_by` and `re_affirmed_by` (migration residue) |
| (e) | `superseded_by` non-empty while `status` is non-terminal (the pre-existing I3 divergence — post-migration this is unambiguously a defect) |

This is deterministic and mechanical; it does not require the checker to read prose.

**6. Migration precedes carve-out deletion — binding on step order.** All five instances (dec-040, dec-112, dec-203, dec-219, dec-231, plus anything a `superseded_by`-carrying grep sweep adds) are converted first. Frontmatter alone cannot discriminate "partially superseded, still live" from "fully superseded and separately re-affirmed" — dec-040 and dec-203 carry the *identical* edge shape under opposite statuses — so the migration **reads `## Prior Decision` prose and surfaces each conversion for human confirmation**. Only once every carrier record has moved is DL06's carve-out paragraph deleted. Shipping the deletion first would strand exactly the records this change serves.

**7. Consumers.** DL04 extends existence checks to both fields; DL06 extends reciprocity to both and *afterwards* loses its carve-out; `finalize_adrs_crossrefs.py` needs **no edit** — implementation-planning verified its draft-id rewrite is field-agnostic whole-file replacement (no field list exists), a mechanism that covers the new fields by construction and is pinned by a regression test asserting rewrite of a draft-stage `supersedes_in_part`; `query_adrs.py` prints a narrowing caveat while keeping the record in the default view; `regenerate_adr_index.py` renders a narrowing marker in the status cell of affected rows (`accepted (narrowed by dec-NNN)`) so the corpus's primary human scan surface stops giving a wrong answer; `dashboard_app/.../adr-graph.ts` teaches `AdrGraphNode` and `buildAdrGraph` both new fields **and `retired_by`**, which is already missing there — the same omission class its own `asIdList` docstring records having caused a live rendering defect; the premise comment at `adr_health.py:91–99` ("the supersession protocol flips status at the same moment it writes the field, so status subsumes the link check") is rewritten, because this decision makes it false.

**Category note.** `behavioral`, not `architectural`, under `dec-318`'s falsifier: no component is added, removed, or has a responsibility moved. `dec-317` — adding `status: retired` + `retired_by` — is `architectural`, but predates `dec-318` by one day; following the current test over the older precedent is deliberate.

## Considered Options

### A — Reject; prose suffices
Pros: zero schema growth, zero always-loaded tokens. Cons: at 5-of-18 supersessions the case is a recurring shape, not an edge case; five instances have already produced five encodings under a prose-only convention, which is direct evidence that prose does not suffice; and `dec-347` made the wrong frontmatter answer a retrieval defect.

### B — `[{id, clause}]` with a stable clause anchor
The steelman is not free text: the anchor would be a `## Prior Decision` heading slug or a short minted kebab clause id, exactly as parseable as `dec-NNN`, enabling set-intersection over two narrowings of the same record ("do these overlap?") — a question nothing can answer today. At a 27.8% base rate this is not obviously over-engineering, so the rejection is re-argued on its merits.

**Rejected, on a structural defect in the anchor's identity.** The anchor would be minted by the *narrowing* record, so it is a stable identity for **the narrowing, not the clause**. Two independent decisions narrowing the same clause of one record would mint different anchors, and set-intersection would return "these do not overlap" — a confidently **wrong** answer, strictly worse than today's honest "cannot answer". Making it compose requires clause ids minted by the *narrowed* record, which is impossible: ADR bodies are immutable, so a record cannot acquire clause ids after the fact, and pre-minting them across the corpus is a retroactive body rewrite this project has rejected twice on integrity grounds. The only remaining path — the second narrower reads the first narrower's body and reuses its numbering — is exactly the unenforceable prose inference this decision removes.

Supporting, not load-bearing: double-narrowing has **zero instances** across all five cases; and the list-of-mappings shape would break `query_adrs.py`'s stdlib fallback parser, which handles flat lists only and exists so managed projects without PyYAML still work.

**The composability gap is accepted, named, and given a reversal trigger** (below) rather than papered over.

### C — Reciprocal id lists, clause text in the body (chosen)
Pros: makes the relation mechanically visible to the consumers that can act on it; purely additive optional fields; parses under the stdlib fallback; leaves the inherently narrative part in prose. Cons: cannot express clause-level overlap between two narrowings of one record.

### D — New `status: partially-superseded`
Rejected. Two consumers carry hard-coded status sets (`query_adrs.DEFAULT_STATUSES`, `adr_health._TERMINAL_STATUSES`); a new value forces each into an include-or-exclude decision with no correct answer — excluding drops clauses still in force, including hides the narrowing.

### E — Derive `status` from the incoming edge set
The option closest to the root cause: `status` is a hand-maintained denormalization of the incoming edges, and it is the field that actually diverges (three different values across one relation). Deriving it at index/query time would close that divergence class by construction with no new edge vocabulary.

**Rejected, on stated grounds.** (i) It moves an O(1) per-record field read into a corpus-wide index build that **all six consumers must perform identically** — `query_adrs.py` answers a single-path query today without loading the full graph, and the stdlib-fallback path would have to grow one. That coupling is a real cost, not a hypothetical. (ii) It does not subsume this decision: derivation still needs a machine-readable partiality marker on the edge to distinguish "narrowed, still live" from "fully replaced", so E requires C rather than replacing it. (iii) The user-visible wrong answer E targets — dec-203's hidden verifier clause — is closed anyway by the migration (§6) and the enforcer (§5).

Recorded rather than silently omitted, because it is the design nearest the root cause and a future reader deserves to see why it was not taken.

## Consequences

**Positive.** A consumer reading frontmatter alone can no longer inherit a narrowed clause as if in force, and — post-migration — can no longer be told a live record was fully replaced. The five divergent encodings converge on one. The invariants have a **named, mechanical enforcer** rather than a paragraph of prose inference; DL06 shrinks by that paragraph. `retired_by` reaches the dashboard graph as a side benefit, closing a pre-existing instance of the same omission class.

**Negative.** Scope is materially larger than an additive schema change: five records migrate with human confirmation per record, four consumers change, and a new health-check class ships. The migration reads prose — the very step being designed out — which is unavoidable, since the old encoding is ambiguous by construction; this is a one-time cost paid to stop paying it.

**Accepted limitation — index rendering and composability.** The narrowing marker in `DECISIONS_INDEX.md` names the narrowing decision but not the clause; a reader wanting clause scope still opens the record. And two narrowings of the same record cannot be compared at the clause level. Both are consequences of keeping the anchor out of frontmatter (Option B) and are accepted knowingly.

**Deferred.** The edge-field vocabulary is now enumerated at five independent sites (`adr-conventions.md` frontmatter table, `finalize_adrs_crossrefs.py`, sentinel DL04, sentinel DL06, `adr-graph.ts`). Collapsing them into one registry — the `scripts/artifact_registry.py` pattern — is real coupling relief but a cross-cutting refactor this pipeline should not grow mid-flight. Filed as **td-150** with the five sites named, so the debt is grounded rather than folklore.

**Honest scoping of the central claim.** Markdown frontmatter has no type system, so illegal states are not *unrepresentable* — they are **detected and reported by a named enforcer**. The earlier draft's "unrepresentable" was unearned and is withdrawn.

## Disconfirmation

- **Falsifier**: `status_edge_conflicts` returning shapes (a)–(e) on records authored *after* this lands would prove that adding a fifth edge family to an already-inconsistently-populated schema reproduces the divergence it was meant to end — i.e. that the problem was never expressiveness and the enforcer is the only part that mattered.
- **Steelmanned runner-up**: Option E. If post-landing conflicts cluster on `status` rather than on the edges, the stored status is the defect and deriving it is correct — the six-consumer recompute cost is worth paying to delete a whole divergence class, and this decision's edge fields are precisely the input such a derivation needs.
- **Reversal trigger**: the first record acquiring **two** entries in `superseded_in_part_by` → re-open Option B, since the composability gap becomes load-bearing at that moment; a second `status_edge_conflicts` finding on post-landing records within two months → re-open Option E.
