---
name: roadmap-synthesis
description: >-
  Runs an ultra-in-depth project analysis that produces a ROADMAP.md from a
  full-project audit through a project-derived evaluation lens set (not a
  hardcoded universal list). Triggers on "ultra-in-depth project analysis",
  "spring cleaning roadmap", "project state of the union", "lens-based audit",
  "strengths, weaknesses, deprecations roadmap", "agentic-era project evaluation",
  "AGENTS.md-aware audit", and "SDLC health audit". Covers paradigm detection
  (deterministic / agentic / hybrid), lens-set derivation from the project's
  own values + domain constraints + exemplar lens sets (SPIRIT, DORA, SPACE,
  FAIR, CNCF Platform Maturity, or Custom), parallel audit fan-out via
  researchers, lens synthesis, multi-angle reframing, and grounded claim
  generation. Use when producing a ROADMAP.md from a full-project audit rather
  than ordering an existing backlog — contrast with `roadmap-planning` which
  prioritizes and sequences an existing idea set.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Roadmap Synthesis

Produce a **ROADMAP.md** for any project by deriving a project-specific evaluation lens set, running an ultra-in-depth audit through those lenses, and reconciling parallel findings into a grounded, actionable plan. Paired with [`roadmap-planning`](../roadmap-planning/SKILL.md), which owns the prioritization and sequencing step.

This skill is loaded by the [`roadmap-cartographer`](../../agents/roadmap-cartographer.md) agent via its `skills:` frontmatter. It is the audit-to-synthesis half of the roadmap capability (`dec-029`); prioritization logic stays in `roadmap-planning` (`dec-030`). The lens framework is project-derived, not hardcoded (`dec-036`).

**Satellite files** (loaded on-demand):

- [references/lens-framework.md](references/lens-framework.md) -- the 4-step lens-derivation methodology, exemplar lens sets catalog (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity, Custom), lens schema, and SPIRIT worked example
- [references/audit-methodology.md](references/audit-methodology.md) -- parallel deep-dive pattern, lens selection rubric, fragment reconciliation (`dec-035`)
- [references/paradigm-detection.md](references/paradigm-detection.md) -- deterministic / agentic / hybrid classification heuristics (feeds lens derivation Step 2)
- [references/grounding-protocol.md](references/grounding-protocol.md) -- every quantitative claim cites a source; verification checklist
- [assets/ROADMAP_TEMPLATE.md](assets/ROADMAP_TEMPLATE.md) -- the 10-section ROADMAP.md scaffold (Executive Summary → Weaknesses → **Opportunities (forward lines)** → Improvement Roadmap → Decision Log)
- [assets/audit-fragment-template.md](assets/audit-fragment-template.md) -- per-lens researcher fragment schema (`AUDIT_<lens>.md`)

## What this skill does

Given any project — Praxion itself or any codebase Praxion helps develop — produce a `ROADMAP.md` at the project root that captures strengths, weaknesses, improvement opportunities, deprecations, and sequenced work. The skill is paradigm-agnostic (deterministic / agentic / hybrid) and lens-agnostic: it **derives** the right evaluation lens set for the target project from the project's own values and constraints, rather than applying a fixed universal list.

## When to use this skill vs `roadmap-planning`

| Use `roadmap-synthesis` when… | Use `roadmap-planning` when… |
|---|---|
| Producing a fresh `ROADMAP.md` from a full-project audit | Ordering an existing set of ideas (e.g., `IDEA_LEDGER_*.md`) |
| Input is the repository itself (filesystem, CI, docs) | Input is a pre-existing list of candidates with impact/effort fields |
| User asks "what should we build next" without a backlog | User asks "which of these should we do first" |
| Phrases: "spring cleaning", "state of the project", "ultra-in-depth audit" | Phrases: "prioritize backlog", "RICE/MoSCoW", "sequence releases" |
| Lens-based project evaluation is required | Prioritization framework is required |
| Output: `ROADMAP.md` (project root, living) | Output: `ROADMAP.md` + `BACKLOG.md` (`.ai-work/<slug>/`) |

The two skills **compose**: `roadmap-synthesis` runs Phases 1–5 and 7; it delegates Phase 6 (rank and sequence) to `roadmap-planning`'s framework selector and Now/Next/Later format.

## Pipeline position

Standalone capability — not inserted into the `promethean → researcher → systems-architect` chain (`dec-031`). Activated by:

- `/roadmap` command with optional mode argument (`fresh` / `diff` / `<focus-area>`)
- Explicit `@roadmap-cartographer` delegation
- Main agent recognizing roadmap intent (trigger phrases above)

The `roadmap-cartographer` agent owns the end-to-end workflow and loads this skill plus `roadmap-planning` via its `skills:` frontmatter.

## Core workflow

Seven phases. The cartographer mirrors this structure; procedural depth lives in the linked references, not here.

1. **Scope, Paradigm & Lens Derivation** — classify target as deterministic / agentic / hybrid → [paradigm-detection.md](references/paradigm-detection.md), then derive the project-specific lens set (4-8 lenses drawn from project values + domain constraints + exemplar lens sets) → [lens-framework.md](references/lens-framework.md). Surface paradigm **and** proposed lens set to the user (Gate 1).
2. **Ecosystem Inventory** — filesystem scan of skills, agents, rules, commands, hooks, tests, CI, `AGENTS.md`/`CLAUDE.md`, `.ai-state/ARCHITECTURE.md`, `.ai-state/decisions/`, memory; read the latest `SENTINEL_REPORT_*.md` if present; detect an existing `ROADMAP.md` for `diff` mode.
3. **Parallel Audit Fan-out** — spawn N researcher agents (N = lens_count, capped at 6) in parallel, one per lens from the derived set; each writes an `AUDIT_<lens>.md` fragment via the fragment template → [audit-methodology.md](references/audit-methodology.md).
4. **Lens Synthesis** — reduce fragments into draft roadmap sections through the derived lens set → [lens-framework.md](references/lens-framework.md).
5. **Multi-Angle Reframe** — for each of the top 3 weaknesses, articulate ≥2 framings; record the runners-up as *Considered Angles*. Universal step regardless of lens set.
6. **Prioritize & Sequence** — delegate to [`roadmap-planning`](../roadmap-planning/SKILL.md) for framework selection and Now/Next/Later formatting (Gate 2 on proposed deprecations).
7. **Self-Verify & Emit** — grounding check on every quantitative claim → [grounding-protocol.md](references/grounding-protocol.md); Gate 3 on phase ordering; write `ROADMAP.md` preserving the Decision Log (`dec-032`).

## Lens framework summary

Lens sets are **derived per project**, not fixed. Four exemplar sets plus a Custom branch cover the common project classes; the cartographer composes 4-8 lenses from the best-fit exemplar + the project's own values.

| Exemplar | When to use | Lenses |
|---|---|---|
| **SPIRIT** (Praxion exemplar) | Multi-agent dev tools, LLM-app frameworks | Automation · Coordinator Awareness · Quality · Evolution · Pragmatism · Curiosity & Imagination |
| **DORA** | Continuous-delivery products, SaaS | Deploy Frequency · Lead Time · Change Fail Rate · MTTR |
| **SPACE** | Developer productivity, internal platforms | Satisfaction · Performance · Activity · Communication · Efficiency (pick 3+) |
| **FAIR** | Research code, scientific data repos | Findable · Accessible · Interoperable · Reusable |
| **CNCF Platform Maturity** | Infra platforms, IDPs, K8s operators | Investment · Adoption · Interfaces · Operations · Measurement |
| **Custom / Derived** | Anything not matching an exemplar | 4-8 lenses composed from project values + universal Quality + universal Docs |

Full methodology (4-step derivation), lens schema (name / definition / sub-questions / evidence / failure signals), and the SPIRIT worked example in [lens-framework.md](references/lens-framework.md). Lenses are **evaluation tools applied to the target project**, not the project's own principles — those live at their canonical homes (e.g., Praxion's `README.md#guiding-principles`) and are not re-authored by the cartographer.

## Paradigm detection (summary)

The cartographer classifies the target project from three signal families — dependency manifests (e.g., `anthropic`, `@modelcontextprotocol/*`), filesystem markers (`agents/`, `skills/`, `.claude-plugin/`), and directory layout conventions. The classification feeds lens derivation Step 2 (domain constraints) and selects which sub-question set applies within each chosen lens. A misclassification is a named anti-pattern (R15). Full rubric: [paradigm-detection.md](references/paradigm-detection.md).

## Grounding rule

**Every quantitative claim in the emitted `ROADMAP.md` must cite a source.** Counts, percentages, ratios, and dates are rejected by the Phase 7 self-verification pass if unsourced. Qualitative claims prefer evidence where it exists. Accepted citation formats (file references, command output, ADRs, memory entries, sentinel reports, external URLs with fetch dates) and the full verification checklist: [grounding-protocol.md](references/grounding-protocol.md).

## Multi-angle reframing (Phase 5 inline procedure)

For each of the top 3 weaknesses from Phase 4, the cartographer produces at least two framings before selecting one, then records the rejected framings as *Considered Angles* in the output.

1. **State the weakness** in the terms that emerged from Phase 4 (the default framing).
2. **Invert the frame** — ask whether the weakness is a symptom of a deeper structural pattern, or whether it is itself a masked strength (e.g., "missing CI integration test" may be "absence of expensive integration flakiness").
3. **Recombine frames** — consider whether two weaknesses share a root cause and collapse into one remediation.
4. **Select** the framing whose remediation is smallest yet addresses the root cause; keep the runners-up as *Considered Angles* in the roadmap entry.
5. **Record rejected framings** — the ROADMAP template has a `## Considered Angles` sub-block under each top-3 weakness. Never drop rejected framings silently; they are the audit's Curiosity trail.

This procedure operationalizes the Curiosity lens (called Curiosity & Imagination in the SPIRIT exemplar) and mitigates R9 (single-perspective bias). It runs regardless of the derived lens set — multi-angle framing is universal.

## Composition with `roadmap-planning`

At **Phase 6**, the cartographer activates the [`roadmap-planning`](../roadmap-planning/SKILL.md) skill and delegates:

- **Framework selection** — `roadmap-planning`'s decision table picks RICE / MoSCoW / WSJF / Kano / ICE / simple rank based on project context.
- **Dependency mapping** — `roadmap-planning`'s dependency graph construction and critical-path identification.
- **Now / Next / Later formatting** — the default roadmap format per `roadmap-planning` for projects with evolving scope.

The cartographer does **not** re-implement any of this; it hands the synthesized candidates to `roadmap-planning` and receives a sequenced Now/Next/Later structure back.

## Output

The canonical output is `ROADMAP.md` at the **project root** (`dec-032`) — a living document preserved across runs. The cartographer also writes these working files under `.ai-work/<task-slug>/`:

- `ROADMAP_DRAFT.md` — intermediate draft before Gate 3
- `AUDIT_<lens>.md` — one per researcher (Phase 3 fragments)
- `PROGRESS.md` — phase-transition signals

Use [`assets/ROADMAP_TEMPLATE.md`](assets/ROADMAP_TEMPLATE.md) as the scaffold. The template's 10-section shape (Executive Summary → Decision Log, including the **Opportunities (Forward Lines)** section between Weaknesses and Improvement Roadmap) is the output contract. In `diff` mode the cartographer updates sections in place and appends a new Decision Log entry — it never rewrites the Decision Log. Opportunities catalogue forward-looking items (new capabilities, strategic bets, evolution trends) that may or may not be promoted to Improvement Roadmap items in this cycle — cataloguing them keeps the road ahead visible without forcing premature commitment.

## Anti-patterns

Distilled from pre-design research and validated by context-engineer review. Each row states the risk and the design's mitigation. Inline list because a reader scanning the skill needs to see them without a second click.

| ID | Anti-pattern | Mitigation |
|---|---|---|
| R1 | Hallucinated features or metrics | Grounding protocol + Phase 7 self-verify (unsourced quantitatives rejected) |
| R2 | Roadmap rot | "Last audited" header + `diff` mode + Decision Log preserved |
| R3 | Premature prioritization before synthesis | Phase 4 synthesis strictly precedes Phase 6 ranking |
| R4 | Cargo-cult methodology (lens set OR prioritization) | Lens derivation (project values + exemplars) + `roadmap-planning` framework selector |
| R5 | Score worship over judgment | Template *Judgment override* field per item |
| R6 | Kitchen-sink roadmap | Now cap ≤ 5 items + dedicated Deprecation section |
| R7 | Weaknesses without strengths | Template Section 2 "What's Working" precedes weaknesses |
| R8 | Implementation prescription in roadmap | "Next pipeline action" names downstream agent, not code |
| R9 | Single-perspective bias | N ≥ 3 parallel lenses + Phase 5 multi-angle reframe |
| R10 | Missing user touchpoints | Three mandatory `AskUserQuestion` gates (scope, deprecations, ordering) |
| R11 | Bus factor | Optional `Ownership` field in template |
| R12 | Stalled Now items | `diff` mode surfaces no-progress items |
| R13 | Cookie licking | Optional "next-step by" timestamp |
| R14 | Over-metricization | Template metric cap per section |
| R15 | Paradigm mismatch | [`paradigm-detection.md`](references/paradigm-detection.md) + Phase 1 gate |
| R16 | Regeneration destroys institutional memory | Decision Log preserved; `diff` mode asks before destroy |
| R17 | Skill-agent activation collision with `roadmap-planning` | Disambiguation clause in both descriptions (this skill and agent) |

## Quick reference

| Dimension | Reference |
|---|---|
| Core commands | `/roadmap` (fresh \| diff \| `<focus-area>`) |
| Default mode | `fresh` — full audit, writes new `ROADMAP.md` |
| Incremental mode | `diff` — re-audits, preserves Decision Log, surfaces deltas |
| Focused mode | `<area>` — narrows audit weighting to a focus area; still produces full structure |
| Typical runtime (cartographer) | 3–6 parallel researchers + synthesis ≈ minutes, not hours |
| Paired skill | [`roadmap-planning`](../roadmap-planning/SKILL.md) — activated at Phase 6 |
| Output location | `ROADMAP.md` at project root (`dec-032`) |
| Common pitfall | Skipping paradigm detection or lens derivation → R4/R15 false findings (e.g., cargo-culting SPIRIT to a Python library) |
| Decision trail | `dec-029` shape · `dec-030` coexistence · `dec-031` placement · `dec-032` location · `dec-033` lens file placement · `dec-034` budget · `dec-035` parallel audit · `dec-036` lens framework project-derived |
