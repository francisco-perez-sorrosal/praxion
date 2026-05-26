# Roadmap Synthesis

Produces a `ROADMAP.md` for any project by deriving a project-specific evaluation lens set, running a parallel multi-lens audit, and synthesizing findings into a grounded, actionable plan. Pairs with `roadmap-planning` (which owns prioritization and sequencing at Phase 6).

## When to Use

- Producing a fresh `ROADMAP.md` from a full-project audit (not from a pre-existing backlog)
- User asks "what should we build next", "spring cleaning", "state of the project", or "SDLC health audit"
- Lens-based project evaluation is needed (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, or a custom-derived set)
- Running an agentic-era or `AGENTS.md`-aware audit of a codebase
- Project classification (deterministic / agentic / hybrid) is required before evaluation

Use `roadmap-planning` instead when the input is an existing list of candidates with impact/effort fields.

## Activation

Loaded by the `roadmap-cartographer` agent via its `skills:` frontmatter. Also activates when the assistant recognizes roadmap-synthesis trigger phrases: "ultra-in-depth project analysis", "spring cleaning roadmap", "project state of the union", "lens-based audit", "agentic-era project evaluation", "SDLC health audit".

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: seven-phase workflow, lens framework summary, paradigm detection, grounding rule, multi-angle reframing, anti-patterns, quick reference |
| `README.md` | This file — overview and usage guide |
| `references/lens-framework.md` | 4-step lens derivation methodology, exemplar lens sets (SPIRIT, DORA, SPACE, FAIR, CNCF, Custom), lens schema, SPIRIT worked example |
| `references/audit-methodology.md` | Parallel deep-dive pattern, lens selection rubric, fragment reconciliation |
| `references/paradigm-detection.md` | Deterministic / agentic / hybrid classification heuristics |
| `references/grounding-protocol.md` | Every quantitative claim cites a source; verification checklist |
| `assets/ROADMAP_TEMPLATE.md` | 10-section ROADMAP.md scaffold |
| `assets/audit-fragment-template.md` | Per-lens researcher fragment schema (`AUDIT_<lens>.md`) |

## Quick Start

1. Classify the target project: deterministic / agentic / hybrid (Phase 1 → [paradigm-detection.md](references/paradigm-detection.md))
2. Derive the lens set: 4-8 lenses from project values + domain constraints + exemplar (Phase 1 → [lens-framework.md](references/lens-framework.md))
3. Surface paradigm and proposed lenses to the user (Gate 1)
4. Inventory the ecosystem: skills, agents, rules, CI, docs, `.ai-state/` (Phase 2)
5. Spawn N parallel researcher agents for N lenses; each writes `AUDIT_<lens>.md` (Phase 3)
6. Synthesize fragments into draft roadmap sections (Phase 4)
7. Reframe top 3 weaknesses with ≥2 angles; record runners-up as *Considered Angles* (Phase 5)
8. Delegate to `roadmap-planning` for framework selection and Now/Next/Later formatting (Phase 6, Gate 2)
9. Self-verify all quantitative claims; emit final `ROADMAP.md` (Phase 7, Gate 3)

## Related Skills

- [`roadmap-planning`](../roadmap-planning/) — prioritization and sequencing; activated at Phase 6
- [`project-exploration`](../project-exploration/) — codebase orientation before audit fan-out when the target project is unfamiliar
