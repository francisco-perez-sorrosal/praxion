---
id: dec-021
title: Dual-audience architecture documentation
status: accepted
category: architectural
date: 2026-04-10
summary: Split architecture docs into design-target (.ai-state/ARCHITECTURE.md) and code-verified navigation guide (docs/architecture.md) with distinct validation models
tags: [architecture, documentation, ai-state, dual-audience, validation, living-document]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/ARCHITECTURE.md
  - docs/architecture.md
  - skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md
  - skills/software-planning/references/architecture-documentation.md
  - skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md
  - skills/doc-management/references/documentation-types.md
  - skills/doc-management/SKILL.md
  - skills/software-planning/SKILL.md
  - skills/software-planning/references/agent-pipeline-details.md
  - agents/systems-architect.md
  - agents/implementer.md
  - agents/implementation-planner.md
  - agents/verifier.md
  - agents/sentinel.md
  - agents/researcher.md
  - agents/promethean.md
  - agents/doc-engineer.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/swe-agent-coordination-protocol.md
supersedes: dec-020
---

## Context

Dec-020 introduced `.ai-state/ARCHITECTURE.md` as a living document maintained by pipeline agents. During its first instantiation for Praxion, a fundamental tension emerged: the document serves two audiences with conflicting needs.

**Architects** (systems-architect, implementation-planner) need a design target that abstracts above concrete code. They work with planned components that don't yet exist, abstract component names that encompass multiple modules, and design decisions that constrain future implementations. They need high depth and design coherence, not strict code accuracy.

**Developers** navigating the codebase need a factual guide where every component name maps to a real module, every file path resolves on disk, and nothing is described that doesn't actually exist. They need high accuracy and present-tense descriptions.

A single document cannot serve both audiences without constant friction: architects adding "Planned" components that developers find misleading, or developers removing planned items that architects need for design continuity. The sentinel's validation checks compound the problem — should AC02 ("component names match actual modules") apply to a design-target document that intentionally abstracts above module names?

## Decision

Split architecture documentation into two purpose-built documents sharing the same 8-section structure but with distinct framing, content policies, and validation models:

1. **`.ai-state/ARCHITECTURE.md`** (architect-facing, design target) — abstracts above concrete code, includes Status column (Designed/Built/Planned/Deprecated), validates via design coherence (internal consistency, design accounts for reality)
2. **`docs/architecture.md`** (developer-facing, navigation guide) — present-tense only, code-verified accuracy, no Status column, every name and path resolves on disk

The derivation relationship is directional: the developer guide is derived from the architect doc (filtering to Built components) and verified against the codebase. The architect doc defines the design space; the developer doc captures what actually exists.

Key design choices:
- **Same 8-section structure** — both documents use the same sections with different framing. This makes the derivation relationship clear and the implementer's job mechanical (filter Built, verify paths, reframe to present tense)
- **Systems-architect creates both** in Phase 3.8 — single agent responsibility for initial creation ensures consistency
- **Implementer updates both** (step 7.6 for architect doc, step 7.7 for developer doc) — natural sequencing, step 7.7 only fires when 7.6 was done
- **Doc-engineer maintains developer doc** — periodic filesystem verification at pipeline checkpoints
- **Split validation** — sentinel AC01-AC04 become design-coherence checks (architect doc), AC05-AC08 are strict code-verified checks (developer doc), AC09 is cross-consistency
- **Developer template in doc-management** — the developer guide is a documentation artifact; its template belongs with the doc-management skill, not software-planning

## Considered Options

### Option 1: Dual-document with shared structure (chosen)

**Pros:** Each audience gets optimized content. Validation models are unambiguous. The derivation relationship is clear and mechanical. Both documents stay compact because they don't compromise for the other audience.

**Cons:** Two documents to maintain. Risk of drift between them. More agent responsibilities (step 7.7, AC05-AC09).

### Option 2: Single document with audience-toggle sections

**Pros:** One document, one source of truth. No drift risk.

**Cons:** The document becomes complex — conditional content, audience markers, unclear validation model. "For architects" / "For developers" sections create a reading tax for both audiences. The sentinel can't apply different validation rules to different sections of the same document without significant complexity.

### Option 3: Single document optimized for developers, with architect annotations

**Pros:** Developer accuracy is preserved. Architect needs served via annotations.

**Cons:** Architect doc becomes constrained by developer accuracy requirements. Cannot include Planned/Designed components. Design-target value is significantly reduced.

### Option 4: Keep single document, accept the tension

**Pros:** No additional work. Simple.

**Cons:** Continuous friction. Validation rules are either too strict (fails on abstract component names) or too loose (allows inaccurate paths). Neither audience is well served.

## Consequences

**Positive:**
- Each audience gets a document optimized for their needs with no compromises
- Validation is unambiguous: design coherence for architect doc, code accuracy for developer doc
- The derivation relationship provides a natural update pathway (architect doc changes trigger developer doc updates)
- Doc-engineer gets a clear maintenance responsibility for the developer guide
- Sentinel checks can be precise without "it depends on context" exceptions

**Negative:**
- 21 artifacts need modification (8 agent definitions, 2 templates, 1 methodology reference, 2 rules, 4 skill files, 3 instances/ADR, 1 index)
- Implementer gets an additional step (7.7) on architecture-annotated work
- Sentinel grows by ~12 lines (5 new checks + guidance)
- Risk of developer doc drifting from architect doc if cross-consistency check (AC09) is not enforced

## Phase Renumbering Addendum (2026-04-12)

Phases referenced in this ADR (3.8, 7.6, 7.7, 4.8a, 4.8b) were renumbered to (5, 7.6, 7.7, 8, 9) on 2026-04-12 per pipeline-hardening task 2.1. Step 7.6/7.7 are implementer sub-steps (not phases) and remain stable. ADR body preserved unchanged — historical phase numbers appear above in their original form to maintain the decision's authenticity at time of authoring; downstream agent prompts, skill references, and validation docs now use the renumbered values.

## Prior Decision

This supersedes dec-020 (Living ARCHITECTURE.md in .ai-state/). Dec-020 established the single living document pattern. Dec-021 preserves the core pattern (section ownership, staleness mitigation, pipeline maintenance) but splits the single document into two with distinct audiences and validation models. The architect doc retains all of dec-020's design, adding Status column and design-target framing. The developer doc is the new addition.
