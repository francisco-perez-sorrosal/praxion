---
id: dec-037
title: Opportunities (Forward Lines) as a first-class roadmap section; Motivation field generalization
status: accepted
category: architectural
date: 2026-04-12
summary: 'Add §4 Opportunities (forward lines of work — non-deficit items) to ROADMAP_TEMPLATE.md; generalize Improvement Roadmap item field from `Problem addressed` (Weakness-only) to `Motivation` (Weakness | Opportunity | Evolution trend | Strategic bet | User request | Prior item). 9-section scaffold becomes 10-section'
tags: [architecture, roadmap, template, forward-looking, generalization]
made_by: user
pipeline_tier: standard
affected_files:
  - skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md
  - skills/roadmap-synthesis/references/lens-framework.md
  - skills/roadmap-synthesis/references/audit-methodology.md
  - skills/roadmap-synthesis/SKILL.md
  - agents/roadmap-cartographer.md
  - commands/roadmap.md
  - .ai-state/ARCHITECTURE.md
---

## Context

The initial ROADMAP_TEMPLATE.md (as shipped in dec-029 and updated by dec-036) had nine sections: Executive Summary, What's Working, Weaknesses, Improvement Roadmap, Deprecation & Cleanup, Quality Metrics, Guiding Principles for Execution, Methodology Footer, Decision Log. Each Improvement Roadmap item had a required `Problem addressed: [Weakness Wn or prior item id]` field — forcing every future-planned item to trace back to a current deficit or a prior chained item.

User review after the first pass surfaced the gap: a roadmap without a forward-looking view of new features is not a roadmap, it is a maintenance list. A project team wanting to roadmap "build an eval framework as a new capability" or "ride the 2026 standards convergence (AAIF/MCP/AGENTS.md)" has to mis-frame the item as "weakness: no eval framework" — which positions an opportunity as a deficit and distorts the roadmap's narrative.

Praxion's own `ROADMAP.md` had handled this by labeling its final Improvement Roadmap phase "Phase 5: Strategic Horizons" — but the label alone did not change the per-item schema, which still demanded Weakness citations. The template inherited the per-item schema and not the phase-label convention, losing the forward-looking signal.

Separately, opportunities have different evidence shapes from weaknesses. A weakness cites a `file:line` or a metric-from-command (current state). An opportunity cites an external trend URL + fetch date, a user signal from an issue/transcript, or adjacent-project traction — evidence about what *could* be, not what *is*. A single field labeled "Problem addressed" misreads this material.

## Decision

Introduce **Opportunities (Forward Lines)** as a first-class roadmap section (§4) between Weaknesses and Improvement Roadmap, and generalize the Improvement Roadmap item's deficit-only field into a Motivation field accepting multiple legal values.

### Three coordinated changes

1. **New §4 "Opportunities (Forward Lines)"** — parallel in structure to §3 Weaknesses but for non-deficit items:
   - `O1…On` numbered entries with: Description, **Why now** (external trend / user signal / adjacent-project traction / internal-shape invitation), Evidence, Potential impact (on which lens), Confidence (opportunities are speculative — honest confidence framing matters), Effort estimate (S/M/L/XL), optional Ownership.
   - Capped at ~5 per cycle for signal-to-noise; cataloguing opportunities does not commit to shipping them.
   - Distinguishing rule from Weaknesses: if an item can only be framed as "we don't have X", it's a Weakness. If it's framed as "X would unlock Y", it's an Opportunity.

2. **Motivation field** (replaces `Problem addressed`) with legal values: `Weakness Wn | Opportunity On | Evolution trend | Strategic bet | User request | Prior item id`. Every Improvement Roadmap item names exactly one motivation.

3. **Phase label convention** — Phase 3 ("Later" horizon) is labeled "Strategic Horizons" when its dominant motivation is Opportunity / Strategic bet / Evolution trend rather than Weakness. Mixed-motivation phases are fine; label by the dominant motivation.

### Section renumbering

The template scaffold expands from 9 to 10 sections. New order: Executive Summary (§1), What's Working (§2), Weaknesses (§3), **Opportunities (§4)**, Improvement Roadmap (§5), Deprecation & Cleanup (§6), Quality Metrics (§7), Guiding Principles (§8), Methodology Footer (§9), Decision Log (§10).

### Agent Phase 4 update

The cartographer's Phase 4 "Lens Synthesis" now classifies findings into **four buckets** (was three): strengths, weaknesses, **opportunities**, improvements. The agent is explicitly instructed that a roadmap surfacing only Weaknesses without Opportunities is structurally incomplete — Evolution-class lenses (e.g., SPIRIT Evolution, CNCF Platform Maturity Adoption) and Curiosity-class lenses are expected to produce forward-looking material.

### Lens-to-section mapping

[lens-framework.md](../../skills/roadmap-synthesis/references/lens-framework.md#using-the-derived-lens-set-in-the-audit) documents which lenses naturally feed which sections: deficit-oriented lenses (Quality / Reliability / Operations) produce Weaknesses; forward-oriented lenses (Evolution / Curiosity / Adoption) produce Opportunities. When a project has no Evolution-class lens in its derived set, the cartographer still probes the Evolution axis during synthesis to ensure Opportunities are not left empty by default.

## Considered Options

### Option A — Keep "Problem addressed" field; use phase labels only

Rely on the "Later" horizon phase label (e.g., "Strategic Horizons") to mark forward items. Don't change the field.
**Pros:** minimal template change; matches Praxion's own ROADMAP.md exactly.
**Cons:** per-item field still demands a Weakness citation, so the phase label is decorative; items can still only be framed as deficits; the template continues to force opportunity retconning as weakness. Rejected.

### Option B — Single field generalization (Motivation) without new section

Change `Problem addressed` → `Motivation` with wider legal values. No new top-level section.
**Pros:** smaller template change; fewer edits downstream.
**Cons:** opportunities that don't graduate to Improvement Roadmap items this cycle have no home — they are lost between audits. Opportunity cataloguing is valuable even without commitment; forcing promotion-or-discard at the same time as generation underweights the "road ahead" visibility the user flagged as missing. Rejected.

### Option C — New §4 Opportunities section + Motivation field generalization (chosen)

Both changes together.
**Pros:** Opportunities catalogued independent of promotion decisions; Improvement Roadmap items can cite any motivation source; Evolution and Curiosity lenses have a natural landing place; matches IDEA_LEDGER's "Future Paths" precedent (promethean agent already has this pattern); forward vision is visible at scan-time.
**Cons:** template grows to 10 sections; section ownership contract lists 10 rather than 9; seven downstream files need section-count references updated.

### Option D — Merge Weaknesses and Opportunities into a single "Findings" section with a type column

One section, with each entry tagged as Weakness or Opportunity.
**Pros:** fewer top-level sections.
**Cons:** evidence types differ (deficit-now vs trend-ahead); confidence framing differs (high-certainty for measured deficits, speculative for opportunities); mixing them dilutes both. The Weaknesses section's "every weakness is evidence-grounded" discipline weakens if speculative opportunities share the same space. Rejected.

## Consequences

**Positive:**

- Roadmaps produced for any project now include an explicit forward-looking view — "the road ahead" — not just deficit repair.
- Evolution-class and Curiosity-class lenses get a natural destination for their forward-looking findings, increasing the value extracted from every audit.
- Opportunities are catalogued separately from commitments, allowing aspirational items to remain visible across multiple audit cycles without forcing premature prioritization decisions.
- Improvement Roadmap items carry correct provenance (Weakness / Opportunity / Evolution trend / Strategic bet / User request / Prior item) rather than retconning everything as deficit.
- Phase 3 "Strategic Horizons" label convention carries Praxion's own ROADMAP.md pattern forward to every project.
- Alignment with the six-dimension SPIRIT lens (Evolution + Curiosity & Imagination) is now operationalized — those lenses no longer compete for floor space with deficit-oriented lenses in the Weaknesses section.

**Negative:**

- Template grows to 10 sections; section-count references in downstream documentation need updating (agent prompt, SKILL.md, audit-methodology.md, commands/roadmap.md, dec-029/dec-032 ADR body language).
- Cartographer Phase 4 synthesis workload increases slightly — classifying findings into four buckets rather than three, and explicitly probing Evolution axis if fragments don't surface opportunities.
- Opportunities-without-promotion can become a dumping ground if the ~5-per-cycle cap isn't respected.
- Confidence framing on Opportunities requires discipline — speculative items with no evidence should not be catalogued.

**Operational:**

- `ROADMAP_TEMPLATE.md` updated with new §4 Opportunities section, renumbered §5-§10, changed per-item schema.
- Agent Phase 4 synthesizes four buckets; four-bucket guidance added to audit-methodology.md fragment-reconciliation step.
- lens-framework.md Using-the-derived-lens-set section documents lens-to-section mapping explicitly.
- Section ownership contract at top of ROADMAP_TEMPLATE.md lists 10 sections with Opportunities marked REGENERATE (matches Weaknesses lifecycle).
- Verifier AC-2 (lens coverage) now has 4 destinations to check per finding (strength / weakness / opportunity / improvement) rather than 3.

## Prior decisions and relationship

- `dec-029` (shape), `dec-030` (coexistence), `dec-031` (pipeline placement), `dec-032` (location/lifecycle), `dec-034` (budget), `dec-035` (parallel audit) are unaffected.
- `dec-033` (lens content placement) is unaffected — placement of lens content in reference + asset + summary is independent of this template-structure decision.
- `dec-036` (lens framework project-derived) is complemented — this decision extends the generalization: just as lens sets are project-derived rather than hardcoded, the roadmap structure now accommodates forward lines of work rather than mandating deficit-framing.
