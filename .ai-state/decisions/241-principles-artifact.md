---
id: dec-241
title: Per-project principles artifact — standalone `.ai-state/principles.yaml`, Shape B, per-principle gate severity
status: accepted
category: architectural
date: 2026-06-20
summary: >
  Fold Kiro steering-files + Spec Kit Constitution + the deferred
  project_profile.yaml.principles idea into one standalone, optional,
  on-demand-read .ai-state/principles.yaml; gate per-principle via a
  configurable advisory|blocking severity routed onto the verifier's
  existing FAIL/WARN mechanics. Zero always-loaded cost.
tags: [governance, principles, verifier, planner, project-profile, gating, token-budget]
made_by: agent
agent_type: systems-architect
branch: feat-project-principles
pipeline_tier: standard
affected_files:
  - .ai-state/principles.yaml
  - agents/verifier.md
  - agents/implementation-planner.md
  - skills/software-planning/references/project-principles.md
  - skills/spec-driven-development/SKILL.md
dissent: >
  A standalone file ahead of project_profile.yaml creates a second
  principles read-site to fold in later; the cleaner one-location design
  would wait for the profile producer — at the cost of blocking a real
  capability gap indefinitely.
---

## Context

Three separate signals name one capability: Kiro **steering files** (declarative, user-authored, per-project standard enforcers), Spec Kit's **Constitution** (Signal C), and a previously-deferred **`project_profile.yaml.principles:`** extension. Praxion today has no first-class, pipeline-read, *gated* per-project principles surface — per-project standards live implicitly in each managed project's `CLAUDE.md` prose, which is neither auditable nor gate-checkable.

The process-governance study (baseline-audit) analyzed this under a Balanced-Coupling + philosophy-fit + always-loaded-cost lens and returned an explicit **FOLD** verdict: the three are one work item, and the high-fit implementation is **Shape B** (read on demand by planner + verifier, *not* a new always-loaded "steering" surface). The always-loaded budget sits at ~96% (~918 chars headroom), so any always-loaded design (Shape A) is rejected on cost alone.

Two load-bearing calls were left to the build pipeline: (i) how to ship Shape B given `project_profile.yaml` has **no active producer**, and (ii) the gate semantics (advisory vs blocking). Both are settled here. The user ratified FOLD, Shape B, configurable-per-principle severity, and standalone shipping ahead of profile wiring.

## Decision

1. **Fold** the three ideas into a **single** work item: one declarative, user-authored, per-project standards artifact.
2. **Ship it standalone** as `.ai-state/principles.yaml` (committed, optional), read **on demand** only when the implementation-planner or verifier is spawned — **zero always-loaded cost** (Shape B, decoupled from the unbuilt profile scaffold).
3. **Gate per-principle** via a required `severity: advisory | blocking` field, routed onto the verifier's **existing** mechanics: `blocking` violation → `FAIL` (gates like an unmet acceptance criterion); `advisory` violation → `WARN` (surfaced, never fails the gate); satisfied → `PASS`. No new gate engine — a new input to the one that exists.
4. **Absent / empty / malformed → silent no-op** in both consumers (SH07-style skip; fail-safe, never fail-closed on a user typo).
5. **Migration-ready:** the `principles:` list shape is byte-identical to the eventual `project_profile.yaml.principles:` block; both consumers read through a single resolver seam with a defined precedence (profile wins, file is fallback) so the future fold-in is a one-line edit, not a re-plumb.
6. **Authoring boundary documented:** project-principles = project-specific *standards*; framework rules (`rules/**`) = framework conventions. A decision test ("would this make sense in an unrelated project?") keeps users from reinventing rules.

Schema (minimal): `id` (req), `statement` (req), `severity` (req, `advisory|blocking`), `scope` (opt glob, default `*`), `rationale` (opt). Reserved top-level `version` for forward-compat.

**Activation (design-synthesis lens sweep):** yes — ran the Simplicity, Testability, and Balanced-Coupling lenses. Simplicity drove the no-script / five-field / reuse-existing-gate-engine v1. Testability drove the fixture-matrix acceptance surface (the absent/empty/malformed no-op paths). Balanced Coupling confirmed Shape B (low integration strength, short distance) over Shape A. Security/Performance lenses: not load-bearing (inert data file, on-demand read). Convergence check: all lenses agree on the standalone-Shape-B-per-severity shape.

## Considered Options

### Option 1 — Shape A: new always-loaded "steering" concept (Kiro-literal)
- **Pros:** principles always in context; no per-agent read needed.
- **Cons:** competes directly with the ~918-char always-loaded headroom; violates the token-budget guardrail and Pragmatism. **Rejected on cost** (study scored ~1.8).

### Option 2 — Shape B on `project_profile.yaml.principles:` (bundle with profile wiring)
- **Pros:** one location, no future migration; gathers per-project governance into the one per-project artifact.
- **Cons:** `project_profile.yaml` has **no producer**; bundling blocks a real capability gap on the unbuilt archetype-detection scaffold. **Deferred** (it is the migration *target*, not the v1 vehicle).

### Option 3 — Shape B as standalone `.ai-state/principles.yaml` ahead of profile wiring (CHOSEN)
- **Pros:** closes the gap now; zero always-loaded cost; independently shippable; couples cleanly (extends `.ai-state/`, on-demand); migrates into the profile non-breakingly via a single resolver seam.
- **Cons:** a second read-site to fold in later (mitigated by the single-resolver seam + defined precedence).

### Gate-semantics sub-options
- **All advisory:** toothless for standards a project genuinely wants enforced. Rejected.
- **All blocking:** brittle; punishes legitimately-deferred work; users would stop authoring principles. Rejected.
- **Per-principle `severity` (CHOSEN):** matches real governance (different standards, different stakes); reuses the verifier's existing FAIL+WARN paths (no new structure).

## Consequences

**Positive:**
- Real per-project, pipeline-gated governance at zero always-loaded cost.
- Reuses the verifier's existing FAIL/WARN engine and the planner's existing acceptance-criteria threading — minimal new surface.
- Existing projects are unaffected (absent artifact = current behavior exactly).
- Non-breaking migration path to `project_profile.yaml` is defined before the second location exists.

**Negative / accepted:**
- Two principles read-sites will briefly coexist during migration (precedence rule + single resolver bound this).
- Users must choose severity per principle (mitigated: `advisory` is the safe coercion default).
- Risk of conflating principles with framework rules (mitigated by the documented boundary + decision test).

## Disconfirmation

- **Falsifier:** if, in practice, users author principles that are all framework-rule restatements (no genuinely project-specific standards appear across several managed projects), the artifact adds ceremony without closing a real gap — the decision would be wrong, and the right move would be to drop the artifact and instead let projects extend `rules/` locally.
- **Steelmanned runner-up (Option 2):** waiting for `project_profile.yaml` avoids ever having two read-sites, keeps all per-project metadata in one file, and sidesteps the migration entirely. If the profile producer were imminent, bundling would be the cleaner, lower-total-cost path — one artifact, one resolver, no soft-deprecation dance.
- **Reversal trigger:** when `project_profile.yaml` gains an active producer (archetype-detection scaffold wired into `/onboard-project`), revisit — at that point principles should migrate into the profile (profile wins, file becomes fallback per the defined precedence), and a future ADR should record the consolidation.
