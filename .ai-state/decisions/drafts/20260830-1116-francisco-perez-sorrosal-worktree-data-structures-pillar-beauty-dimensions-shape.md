---
id: dec-draft-c7238bd8
title: Eight beauty dimensions land as a clause under Structural Beauty + beautiful-code skill + coding-style anchors + Praxion's first principles.yaml, not new principles
status: proposed
category: architectural
date: 2026-08-30
summary: Engrave the eight dimensions of beautiful code (storytelling, simplicity, clarity of intent, expressiveness, purity, sustainability, durability, creativity) as one clause under Structural Beauty, a new beautiful-code index-plus-gap-filler skill, four path-scoped coding-style sections, verifier/implementer/architect hooks with a creativity guard, and Praxion's first live .ai-state/principles.yaml — rejecting both a new top-level principle and dimension-per-principle expansion
tags: [beautiful-code, structural-beauty, philosophy, code-review, coding-style, principles-yaml, creativity, purity, durability, storytelling]
made_by: agent
agent_type: orchestrator
branch: worktree-data-structures-pillar
pipeline_tier: full
dissent: "Burying eight enforcement-relevant dimensions behind an aesthetics-framed principle risks the discoverability loss a prior decision explicitly rejected for Balanced Coupling — a dedicated principle (or two) would give stronger citation anchors for the genuinely novel dimensions (purity, durability, creativity)."
affected_files:
  - claude/config/CLAUDE.md.tmpl
  - codex/config/AGENTS.md.tmpl
  - AGENTS.md
  - skills/beautiful-code/SKILL.md
  - skills/beautiful-code/references/dimension-canon.md
  - skills/beautiful-code/references/beauty-review-checklist.md
  - rules/swe/coding-style.md
  - agents/verifier.md
  - agents/implementer.md
  - agents/systems-architect.md
  - skills/code-review/SKILL.md
  - .ai-state/principles.yaml
---

# Eight beauty dimensions land as a clause under Structural Beauty + beautiful-code skill + coding-style anchors + Praxion's first principles.yaml, not new principles

## Context

The user mandated engraving eight dimensions of beautiful code into Praxion's
philosophy and code path, explicitly as a refresher over existing coverage. An
exhaustive internal audit found: no prior artifact enumerates the dimensions;
Simplicity and Clarity of intent are fully covered (behavioral contract,
coding-style gates); Sustainability is covered at process level; Storytelling,
Expressiveness, Purity, and Durability are partial; Creativity is absent from
the code layer and in explicit tension with the "readability over cleverness"
stance. Two precedents constrain the shape: dec-097 engraved a cornerstone as
clauses under existing principles to prevent principle bloat, and dec-229
rejected "augment Structural Beauty" for Balanced Coupling because
aesthetics-framing weakened its enforcement anchor. The always-loaded budget
had 1,442 tokens of headroom. Primary-source research (two independent
researcher passes, quote-verified with confidence labels) established the
canon: Hickey/Ousterhout/Brooks (simplicity), Knuth/antirez/Ousterhout
(storytelling), Beck/Fowler/Hofmeister (clarity), Iverson/Matz
(expressiveness), Carmack/Bernhardt/Cockburn (purity), Cunningham/Feathers/
Eghbal (sustainability), SQLite/Knuth/Torvalds/Hyrum/RFC-9413 (durability),
Knuth/Dijkstra/Norvig/Wayne (creativity — the clever-vs-insightful
reconciliation). A dormant, fully-built `.ai-state/principles.yaml` mechanism
(planner threading + verifier Phase 4.5 gating) existed with no live instance.

## Decision

1. **One clause under `### Structural Beauty`** in all three philosophy sites
   names the eight dimensions and delegates to the skill (~60 always-loaded
   tokens). No new principle; no per-dimension principles.
2. **New `skills/beautiful-code/`** as an index-plus-gap-filler: each dimension
   names its canonical existing home and adds only missing depth; references
   carry the verified canon (with confidence labels) and a judgment-layer
   review checklist with golden bad-cases.
3. **Four path-scoped `coding-style` sections** anchor the genuinely missing
   conventions: Reading Order and Narrative, Side-Effect Discipline,
   Expressive Constructs, Compatibility and Deprecation — zero always-loaded
   cost; the verifier's Phase 5 derivation contract picks them up.
4. **Agent hooks**: four verifier Phase 5 bullets + a creativity guard
   (interrogate unfamiliar-but-justified designs, never flag nonconformity
   alone) + milestone checklist routing; two implementer Self-Review items;
   one systems-architect Phase 3 design-level creativity duty.
5. **Praxion's first `.ai-state/principles.yaml`**: the eight dimensions as
   advisory, behavior-phrased principles — the first live exercise of the
   planner-threading/Phase-4.5 mechanism, loader-validated.
6. **Research-flagged calls ratified**: green-software energy efficiency is
   excluded from Sustainability (orthogonal checks; exclusion stated, not
   silent); Praxion takes RFC 9413's explicit-reject stance over Postel
   tolerance (consistent with parse-don't-validate), naming the robustness
   principle as superseded-in-part; contested attributions stay labeled
   (Dijkstra/Hoare; Saint-Exupéry paraphrase; Bernhardt attributed-not-verbatim).

## Considered Options

### Option A — New top-level principle(s) (per-dimension or one "Beautiful Code" principle)

- Pros: strongest citation anchors; maximum discoverability.
- Cons: dec-097's sustained objection — principle bloat decays the
  always-loaded signal-to-noise; eight dimensions would consume most of the
  1,442-token headroom; the curated principle set is deliberately small; a
  fixed universal dimension list hardcoded into philosophy is the shape
  dec-036 flags as cargo-cult risk.

### Option B — Clause under Structural Beauty + skill + rule anchors + principles.yaml (chosen)

- Pros: near-zero always-loaded cost with full enforcement reach — the
  citation anchor `CLAUDE.md§Structural Beauty` already exists in the fitness
  citation contract; conventions land where the verifier's derivation contract
  already reads (coding-style); depth loads on demand; the dormant
  principles.yaml mechanism finally gets dogfooded; mirrors the proven
  data-structure-design landing pattern.
- Cons: the dissent above — dec-229 showed aesthetics-framing can weaken
  discoverability. Answered: unlike Balanced Coupling (a design-mechanics
  canon mislabeled as aesthetics), these dimensions ARE the aesthetics —
  Structural Beauty is their semantically correct home, and the four
  coding-style sections give each enforcement-relevant dimension its own
  non-aesthetic rule anchor.

### Option C — Enrich existing artifacts only, no new skill

- Pros: zero new components.
- Cons: the canon (quotes, exemplars, tensions, the clever-vs-insightful
  reconciliation) has no home — coding-style is declarative convention, not
  canon; distributing it would duplicate across five artifacts what one skill
  can hold once.

## Consequences

- Positive: every dimension now has a named canonical home, a review path
  (mechanical floor in Phase 5, judgment layer in the milestone checklist),
  and — for the six that touch code diffs — a rule anchor findings can cite.
- Positive: Creativity is reconciled, not bolted on: clever stays banned,
  insight is licensed with a documented premise, and reviewers gain an
  explicit guard against conformity-only findings.
- Positive: principles.yaml goes from designed-but-unexercised to live,
  with eight advisory rows the verifier can gate and the planner can thread.
- Negative: coding-style grows by four sections (~90 lines) — path-scoped,
  but per-code-session context cost is real.
- Negative: verifier Phase 5 grows to 16 bullets + two paragraphs — nearing
  the point where a future consolidation pass may be warranted.
- Neutral: ~60 always-loaded tokens consumed; headroom remains ≈1,300.

## Disconfirmation

- **Falsifier**: verification reports over the coming quarters showing the new
  dimension checks either never fire (inert gates — the audit's own
  gate-liveness bar) or fire predominantly as noise findings the user
  dismisses; or principles.yaml Phase 4.5 sections consistently empty on
  code-touching pipelines. Either proves the embedding is ceremony, not
  engraving.
- **Steelmanned runner-up**: Option A for a subset — a dedicated
  `### Code Purity` or `### Durability` principle would give the two most
  enforcement-heavy new dimensions first-class citation anchors and
  discoverability that a clause cannot, at ~150 tokens each; if the falsifier
  shows the clause-anchored dimensions underperform the principle-anchored
  ones (Data Structures First as the natural control), the runner-up was right.
- **Reversal trigger**: a future sentinel or calibration finding that
  verifier findings citing `CLAUDE.md§Structural Beauty` are systematically
  weaker (more dismissed, less actioned) than those citing dedicated
  principles — at which point promote Purity and Durability to their own
  principles and shrink the clause.
