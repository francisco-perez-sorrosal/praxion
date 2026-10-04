---
id: dec-draft-ffb3c58b
title: Onboarding installs the diagram kit through a scripted idempotent installer, and managed projects render with a project-local renderer copy
status: proposed
category: architectural
date: 2026-10-04
summary: "New component scripts/install_diagram_kit.py performs onboarding 8b.4 and 8b.5: writes, each only if absent, the _spec.c4 style kit plus an example model (only when no .c4 exists under the diagrams dir), a copy of scripts/regenerate_diagrams.py, and .github/workflows/architecture.yml rendered from the fixed template that pins the same toolchain as Praxion; CI and the developer run the same project-local renderer; no managed-project pre-commit block is added."
tags: [onboarding, aac, diagrams, installer, ci, managed-projects, determinism]
made_by: agent
agent_type: systems-architect
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - scripts/install_diagram_kit.py
  - scripts/test_install_diagram_kit.py
  - claude/aac-templates/architecture.yml.tmpl
  - claude/aac-templates/likec4-style-kit.c4.tmpl
  - claude/aac-templates/likec4-example-model.c4.tmpl
  - skills/onboard-project/SKILL.md
  - skills/onboard-project/references/phases-optional.md
  - skills/onboard-project/references/seed-pipeline.md
affected_reqs: [REQ-15, REQ-16]
supersedes_in_part: [dec-113]
dissent: "Copying the renderer into every managed project re-creates the per-project script drift dec-113 avoided; CI could instead check out Praxion at a pinned tag and run the canonical renderer, upgrading by bumping one ref."
---

## Context

A freshly onboarded project must receive a category vocabulary, an example view, and one documented command that regenerates its renders, and the second onboarding run must change nothing. Its CI drift gate must run the same toolchain versions as Praxion's.

Today's Phase 8b:
- installs only an empty `docs/diagrams/` and a workflow template that is broken (it installs `@likec4/cli`, unpinned, with the old output dir and no normalization);
- performs the installs as agent prose, which no test can drive;
- under dec-113, keeps every AaC script canonical in the plugin path ("no per-project script copies"), but CI runners have no plugin installed.

## Decision

Add **`scripts/install_diagram_kit.py`**, which Phase 8b.5 calls (8b.4's template rendering moves into it; phase ids are preserved). It writes each item only if absent and prints one `installed`/`skipped` line per item:
1. `<diagrams>/architecture/src/_spec.c4` and `architecture.c4` from the kit templates, together and only when no `*.c4` exists under the diagrams dir. That predicate replaces "`docs/diagrams/` absent", so projects onboarded earlier receive the kit on re-run.
2. `scripts/regenerate_diagrams.py`, copied from the plugin.
3. `.github/workflows/architecture.yml`, rendered from the fixed template: pinned likec4 and d2, `python3 scripts/regenerate_diagrams.py` as the regen step, and a diff step that also fails on untracked renders.

The installer never renders and never runs git. When the toolchain is present, the onboarding agent runs the documented command once.

No pre-commit regeneration block is added to managed projects. The drift gate names the command.

## Considered Options

### Option 1: Plugin-path pre-commit block + CI fetching Praxion (dec-113's pattern)

**Pros:** one canonical renderer; upgrades propagate.
**Cons:**
- CI has no plugin, so it must check out Praxion at a pinned ref (network, ref management).
- An upgrade restyles committed renders silently and trips the byte gate.
- A fifth hook block to reconcile.

### Option 2: Project-local renderer copy + scripted installer (chosen)

**Pros:**
- CI and developer run the identical file.
- Byte determinism is pinned per project.
- Testable, idempotent install.

**Cons:** copies drift from Praxion; upgrades need `/upgrade-project` work.

### Option 3: Keep agent-prose installation

**Pros:** no new script.
**Cons:** cannot be driven by a test; substitution errors are invisible; the order dependency between 8b.4 and 8b.5 persists.

## Consequences

**Positive:**
- REQ-15/REQ-16 become testable end to end.
- Managed projects get a working drift gate on day one.
- The installer is reusable by `/upgrade-project` later.

**Negative:**
- Each managed project carries a renderer copy (≈ 600 lines).
- Existing projects keep their broken workflow until reconciled. This is a ledger row and is out of scope.

## Disconfirmation

- **Falsifier:** within two release cycles, a renderer bug fix has to reach more than a handful of managed projects by hand, or copies diverge enough that review checks give different verdicts across projects for the same model.
- **Steelmanned runner-up:** option 1 with a pinned checkout. Praxion already treats the plugin as the canonical home of AaC scripts. A `uses: actions/checkout` of Praxion at a tag, plus `python3 praxion/scripts/regenerate_diagrams.py`, is about four YAML lines. It keeps one renderer and makes upgrades a one-line ref bump, which `reconcile_aac_surfaces.py` already knows how to patch.
- **Reversal trigger:** the falsifier fires. Then move the managed-project regen step to a pinned Praxion checkout and drop the copy.

## Prior Decision

**dec-113 (narrowed, not replaced).** Phase 8b's opt-in gate, its five idempotent surfaces, fence seeding, the fitness scaffold, Block D and the plugin-path invocation of `check_aac_golden_rule.py` / `aac_fence_validator.py` all stand. Narrowed:
- surface 4 (workflow render) and surface 5 (diagrams scaffold) are now performed by `install_diagram_kit.py`, and surface 5 installs a style kit and example model instead of a `.gitkeep`;
- the "no per-project script copies" clause no longer covers the diagram renderer, which is copied because CI has no plugin and committed renders must stay byte-stable per project.

Activation: fired — structural + published onboarding contract + multiple plausible paths; lens set = Security (no plugin code executed in CI), Simplicity, Testability; convergence = stable.
