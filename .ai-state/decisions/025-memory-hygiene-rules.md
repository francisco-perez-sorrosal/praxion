---
id: dec-025
title: Memory hygiene disposition rules (R1–R7)
status: accepted
category: behavioral
date: 2026-04-12
summary: Seven deterministic rules (condense oversized, preserve no-authority, consolidate overlap, preserve distinct angles, supersede stale initiatives, fix doc-drift, skip user-profile invention) govern memory hygiene sprints
tags: [memory, hygiene, rules, behavioral]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/memory.json
  - rules/swe/memory-protocol.md
---

## Context

Memory hygiene sprints — in which `.ai-state/memory.json` is audited, oversized entries condensed, overlapping entries consolidated, and stale initiatives superseded — have historically relied on ad-hoc judgment. Each sprint produced different dispositions for similar inputs, depending on the reviewing agent's framing at the time. This is bad for two reasons: it makes the results non-reproducible (a later audit cannot verify past decisions), and it creates false negatives (entries that should have been condensed remain, while safe-to-keep entries get merged aggressively).

The Phase 1.4 audit identified six oversized entries (>2,000 chars), three clusters of overlapping entries (ecosystem-health, architecture-docs, memory-enforcement), three stale-initiative entries whose implementation has shipped, and one documentation-drift entry. Applying ad-hoc judgment to ~18 actions would yield inconsistent results; a deterministic rule set yields repeatable audits that later sprints can verify by re-running the same rules against the same inputs.

## Decision

Adopt seven deterministic rules (R1–R7) for all memory hygiene sprints. Each rule has a concrete when-condition and a concrete action. Rules are applied in order per entry; the first rule whose condition matches wins.

| Rule | When it applies | Action |
|------|------------------|--------|
| **R1 — Condense oversized** | Entry value > 2,000 chars AND the content is derivable from an authoritative source (SKILL.md, ADR, code file, rule doc) | Reduce value to a ≤400-char summary that cites the authoritative source (path or ADR ID). Preserve `summary`, `tags`, `importance`, `category`, `type`, `key`, `created_at`. Set `updated_at = now` (ISO 8601 UTC). |
| **R2 — Preserve oversized (no authority)** | Entry value > 2,000 chars AND no single authoritative source exists (cross-cutting insight, multi-source synthesis) | Leave entry intact. Append an item to `.ai-work/<slug>/LEARNINGS.md` flagging it as a doc-extraction candidate for a future skill or reference file. |
| **R3 — Consolidate on content overlap** | Two+ entries in the same topic share ≥70% content overlap (lexical or semantic) | Keep the most recent (highest `updated_at`). Absorb any unique facts from older entries into the survivor's value. Archive the older ones (`status: archived`, keeps history). Never hard-delete. |
| **R4 — Preserve distinct angles** | Two+ entries share a topic tag but describe distinct facets (different gotchas, different patterns, different tools) | Leave all entries. Optionally add a bidirectional `related` link between them. |
| **R5 — Supersede stale initiatives** | Entry summary describes "research phase," "just starting," "N parallel researchers launched," etc. AND the code state shows the work has shipped (verified via file existence / test presence) | Set entry status to `archived`. Add a line to the summary pointing to the "implementation-complete" sibling entry (if one exists) or to the committed code. |
| **R6 — Docstring/documentation drift** | Entry describes a claim in a docstring / CLAUDE.md / README that contradicts code | Update the documentation (source of truth = code). Update the memory entry's value to describe the **current** behavior. |
| **R7 — Do not invent user-profile entries** | User-profile dimensions (role, expertise, decision style) | Skip. User agency required. Log as follow-up in `.ai-work/<slug>/LEARNINGS.md`. |

Rules are ordered by frequency of application in practice (R1 and R3 dominate; R7 is a carve-out). R2 and R4 exist explicitly as "do nothing" rules to prevent over-eager consolidation — the default bias is preservation when there is doubt.

## Considered Options

### Option 1 — Ad-hoc judgment per entry

The pre-existing mode. Each reviewer decides case by case.

**Pros:**
- Flexible; no framework to maintain.

**Cons:**
- Non-reproducible — two agents applying the same audit produce different dispositions.
- No way to later verify that a sprint was applied correctly.
- Tends toward one of two failure modes: over-consolidation (useful distinct entries get merged) or under-hygiene (oversized entries remain).
- Hygiene sprints become expensive because every entry demands fresh reasoning.

### Option 2 — Deterministic R1–R7 rules (chosen)

The seven-rule table above. Each rule has mechanical when-and-action semantics.

**Pros:**
- Reproducible — the same audit twice yields the same dispositions.
- Later reviewers can verify a sprint by re-running the rules.
- Sprint cost drops because most entries trigger on obvious conditions (size threshold, archive-vs-keep by timestamp).
- Preserves agency for genuinely ambiguous cases (R2, R4 are explicit "do nothing" outcomes).
- R7 carves out the user-profile dimension where agent-side invention is inappropriate.

**Cons:**
- Edge cases that straddle two rules (e.g., an oversized entry that is also the anchor for a distinct-angle cluster) require a tie-break convention — solved by first-match-wins rule ordering.
- Some rules (R3's "70% overlap") require subjective threshold judgment; the 70% figure is a documented convention, not a measured score.

### Option 3 — LLM-triage per entry (archive/keep/condense classification)

Use a downstream LLM call to classify each entry and return a structured disposition.

**Pros:**
- Potentially captures semantic nuance beyond mechanical rules.

**Cons:**
- Non-deterministic by construction — the value of reproducibility is lost.
- Adds LLM cost to every hygiene sprint.
- Shifts the trust boundary from documented rules to opaque model behavior.
- No natural way to audit or revise the classifier's decisions.

## Consequences

**Positive:**

- Memory hygiene sprints are now repeatable and auditable. A future reviewer can re-apply R1–R7 to the same entries and confirm every disposition.
- Sprint cost drops: obvious cases (oversized, overlapping, shipped) classify mechanically, leaving genuinely ambiguous entries for hand review.
- R2 and R4 defend against the most common hygiene failure modes (over-consolidation, over-condensation).
- R7 preserves user agency for the user-profile dimension — the sprint cannot invent facts about the user.
- Rules can be extended by adding new entries to the table; supersession protocol governs rule changes.

**Negative:**

- R3's "70% overlap" threshold remains a judgment call; calibration across sprints depends on reviewer consistency.
- First-match-wins ordering privileges R1 over later rules — an entry that is both oversized and part of a distinct-angle cluster gets condensed rather than preserved. This is the intentional bias: when in doubt, keep the shorter form of truth.
- Rules do not handle merging into *newly authored* authoritative sources — if a new skill absorbs the content of three memory entries, the rules say "condense and point to skill," but the skill's creation is out-of-sprint work.

**Operational:**

- Rules live in this ADR; the `rules/swe/memory-protocol.md` rule points here for the canonical disposition table. Agents consulting that rule during a hygiene sprint load this ADR on demand.
- R7 ("no user-profile invention") is called out explicitly to prevent well-meaning agents from fabricating role/expertise/decision-style entries without user agency.
- Each hygiene sprint records its rule-application results in `.ai-work/<slug>/LEARNINGS.md` under a `### Memory Hygiene Disposition` header, so the audit trail persists even after the memory.json edits land.
