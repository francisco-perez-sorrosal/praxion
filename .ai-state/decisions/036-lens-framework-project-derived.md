---
id: dec-036
title: Lens framework is project-derived; SPIRIT is an exemplar, not the canonical default
status: accepted
category: architectural
date: 2026-04-12
summary: 'Replace hardcoded six-dimension SPIRIT lens with a 4-step derivation methodology that composes a project-specific 4-8 lens set from project values + domain constraints + exemplar lens sets (SPIRIT, DORA, SPACE, FAIR, CNCF, Custom)'
tags: [architecture, roadmap, lens-framework, generalization, skills]
made_by: user
pipeline_tier: standard
affected_files:
  - skills/roadmap-synthesis/references/lens-framework.md
  - skills/roadmap-synthesis/references/audit-methodology.md
  - skills/roadmap-synthesis/references/paradigm-detection.md
  - skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md
  - skills/roadmap-synthesis/SKILL.md
  - agents/roadmap-cartographer.md
  - commands/roadmap.md
  - .ai-state/ARCHITECTURE.md
---

## Context

The initial implementation of `roadmap-synthesis` (dec-029 through dec-035) hardcoded Praxion's SPIRIT six-dimension set (Automation · Coordinator Awareness · Quality · Evolution · Pragmatism · Curiosity & Imagination) as the canonical evaluation lens for every target project. This embedded an implicit assumption: SPIRIT's dimensions are universally applicable.

Post-implementation review surfaced the flaw: SPIRIT dimensions are Praxion's own organizing concerns for multi-agent dev tooling. Applying them to arbitrary projects — a Python library, an eval framework, a data pipeline, a research repo, an infrastructure platform — forces the audit through an alien frame:

- A single-maintainer Python library cares about API stability, type safety, and docs; SPIRIT's "Coordinator Awareness" is largely irrelevant
- An agentic eval framework needs lenses like hallucination rate, grader reliability, reproducibility — none are explicit SPIRIT dimensions
- A data pipeline needs schema safety, backfill, latency, observability
- A research codebase benefits from FAIR-ness (Findable, Accessible, Interoperable, Reusable) — a well-established standard SPIRIT does not cover

This is anti-pattern R4 (cargo-cult methodology) and R15 (paradigm mismatch) being committed by the feature designed to prevent them. SPIRIT itself contains the rebuke: the Pragmatism dimension says "use the right tool for the decision at hand."

The user identified the gap: SPIRIT should be one exemplar among several, and the cartographer should **derive** the lens set from the target project's own values and constraints rather than inheriting it.

## Decision

The lens framework is **project-derived**, not hardcoded. SPIRIT is preserved as a first-class exemplar (the one Praxion itself uses for its own audits) but is not the canonical default. Three artifacts embody the decision:

### 1. Derivation methodology (4 steps)

In `skills/roadmap-synthesis/references/lens-framework.md`:

1. **Inventory the project's own values** — read `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/architecture.md`, `.ai-state/decisions/`, pinned issues; grep for principles/goals/values; extract 3-6 recurring themes.
2. **Inventory domain constraints** — paradigm (via `paradigm-detection.md`), deployment model, team shape, stakeholders, regulatory/latency/cost constraints.
3. **Compose the lens set** — 4-8 lenses drawn from project values + best-fit exemplar + universal Quality and Docs lenses. Floor 4 (below: no multi-angle). Ceiling 8 (above: thin per-lens findings).
4. **User confirmation (Gate 1)** — propose the derived set via `AskUserQuestion`; user can accept, modify individual lenses, or override with a named exemplar. Decision recorded verbatim in the ROADMAP's Methodology Footer.

### 2. Exemplar lens sets catalog

Six canonical exemplars documented with when-to-use guidance:

| Exemplar | Class | Lenses |
|---|---|---|
| SPIRIT | Multi-agent dev tools, LLM frameworks (Praxion's class) | Automation · Coordinator Awareness · Quality · Evolution · Pragmatism · Curiosity & Imagination |
| DORA | Continuous-delivery products | Deploy Frequency · Lead Time · Change Fail Rate · MTTR |
| SPACE | Developer productivity platforms | Satisfaction · Performance · Activity · Communication · Efficiency (pick 3+) |
| FAIR | Research code, data repos | Findable · Accessible · Interoperable · Reusable |
| CNCF Platform Maturity | Infrastructure platforms, IDPs | Investment · Adoption · Interfaces · Operations · Measurement |
| Custom / Derived | Anything else | 4-8 composed from project values |

### 3. Lens schema

Every lens (exemplar or custom) declares: name, definition, sub-questions (paradigm-aware), evidence types, failure signals, optional example findings.

### Integration changes

- Agent Phase 1 is now "Scope, Paradigm & Lens Derivation" with 1a/1b sub-steps; Gate 1 confirms paradigm **and** lens set.
- Agent Phase 4 renamed "Lens Synthesis" (from "Six-Dimension Synthesis") — uses the derived set, not a fixed list.
- `audit-methodology.md` "6 Parallel Deep-Dives" → "Parallel Deep-Dives Pattern"; N = derived lens count (4-6 typical, 6 cap).
- `ROADMAP_TEMPLATE.md` `<!-- serves: ... -->` comments become placeholder form; Methodology Footer records lens set + source + derivation inputs.
- `SKILL.md` trigger phrases drop "six-dimension" as a primary trigger; add "lens-based audit" and preserve "ultra-in-depth project analysis" as primary.
- `dec-033` placement decision stands (reference file + template asset + SKILL.md summary) — this ADR changes the **content** of those files, not their placement.

## Considered Options

### Option A — Keep SPIRIT as hardcoded default (status quo pre-dec-036)

Do nothing. Six SPIRIT dimensions apply to every project.
**Pros:** no change; matches initial implementation.
**Cons:** cargo-culting SPIRIT to non-tooling projects produces misfired audits; directly violates the SPIRIT anti-patterns the feature was designed to detect (R4, R15); the skill's own discovery logic (paradigm detection) already hinted at project-specificity. Rejected.

### Option B — Replace SPIRIT entirely with a neutral methodology

Strip SPIRIT content; provide only the lens-derivation methodology.
**Pros:** fully generic; no exemplar bias.
**Cons:** destroys Praxion's canonical worked example (which is itself validated: Praxion's own `ROADMAP.md` was produced through SPIRIT); loses the proven sub-question detail (deterministic + agentic sub-questions per dimension); users composing Custom sets have no worked example to reverse-engineer. Rejected.

### Option C — Generalize to lens framework; preserve SPIRIT as first-class exemplar (chosen)

Methodology + exemplar catalog + SPIRIT Appendix preserving the full worked example.
**Pros:** SPIRIT retains its validated role for Praxion itself (the cartographer applied to Praxion derives SPIRIT); other projects get fit-for-purpose lens sets; the Appendix is a concrete template for composing new lenses; exemplar catalog covers common classes (SaaS → DORA, research → FAIR, infra → CNCF Platform Maturity); user-gate ensures no silent misfit.
**Cons:** more content in `lens-framework.md` (grows from 188 to ~370 lines — still on-demand tier 4); requires updates across 7+ files to de-hardcode "six-dimension" language.

### Option D — Add exemplars but keep SPIRIT as "first among equals" default

Preserve SPIRIT as the default for projects that don't otherwise specify.
**Pros:** minimal change.
**Cons:** the "default" framing recreates the original flaw — anyone who doesn't explicitly opt out gets SPIRIT cargo-culted. The derivation methodology's point is that the *project's own values* drive the set, not a centralized default. Rejected.

## Consequences

**Positive:**

- Roadmaps produced for non-multi-agent projects (Python libraries, data pipelines, research repos, infra platforms, SaaS products) get fit-for-purpose lens sets.
- SPIRIT retains its validated role for Praxion's own audits and for other multi-agent dev tools.
- Lens schema documents the minimum structure any lens must declare — makes Custom sets approachable.
- Aligns the feature with its own anti-pattern mitigations (R4, R15): no more cargo-culting.
- Pragmatism dimension (SPIRIT's own dim 5) is served by a choice that uses the right frame for the project at hand.
- Evolution dimension (SPIRIT's own dim 4) is served by staying current with 2026 multi-framework convergence (DORA, SPACE, FAIR all remain canonical in their domains).

**Negative:**

- `lens-framework.md` grows to ~370 lines (still tier 4, on-demand).
- Users familiar with "six-dimension audit" phrasing must learn the new vocabulary ("lens set", "derived lens", "exemplar"). Mitigated by preserving SPIRIT-named trigger phrases in the skill description and agent description.
- Seven files touched to de-hardcode language. One-time cost.
- Initial run on a project requires an additional derivation step at Phase 1 (modest — grep + paradigm detection + exemplar selection = minutes).

**Operational:**

- Existing Praxion `ROADMAP.md` at repo root remains valid (produced through SPIRIT, which is Praxion's fit).
- Re-running `/roadmap` on Praxion itself should derive SPIRIT (or SPIRIT-adjacent Custom) from Praxion's own values — self-consistency check.
- Template `<!-- serves: ... -->` comments become placeholder form; the cartographer fills them with actual derived lens names during synthesis.
- Verifier updates: AC-2 "Six-dimension coverage" becomes "Derived-lens coverage" (every lens in the derived set has evidence in the roadmap).

## Prior decisions and relationship

- `dec-033` (lens content placement) stands unchanged — the placement decision (tier 4 references + tier 5 asset + tier 3 summary) is correct; this ADR updates the *content* of those files, not their placement.
- `dec-035` (parallel researcher fan-out) stands unchanged — N is now derived from lens count (4-6) rather than fixed at 6; the fan-out pattern is identical.
- `dec-029` through `dec-032` and `dec-034` are unaffected.
