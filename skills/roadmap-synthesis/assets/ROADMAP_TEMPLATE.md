<!--
SECTION-OWNERSHIP (cartographer incremental-regeneration contract)

Diff-mode regeneration obeys this contract; fresh-mode regenerates all.
  1.  Executive Summary        REGENERATE
  2.  What's Working            MERGE (additive; deletions require user gate)
  3.  Weaknesses                REGENERATE
  4.  Opportunities             REGENERATE (forward lines — non-deficit items)
  5.  Improvement Roadmap       REGENERATE
  6.  Deprecation & Cleanup     REGENERATE
  7.  Quality Metrics           REGENERATE (carry-forward baselines)
  8.  Guiding Principles        MERGE (rare edits; cross-refs stable)
  9.  Methodology Footer        REGENERATE
  10. Decision Log              PRESERVE VERBATIM (append-only)

User lines marked <!-- USER --> are preserved in merge-mode.
Lens coverage annotated inline (<!-- serves: lens-1, lens-2 -->); lens names come
from the derived lens set for THIS project (see lens-framework.md) — not a fixed
universal list. Replace the SPIRIT placeholders below with your derived lens names.
Authoring guidance: skills/roadmap-synthesis/SKILL.md
-->

# [Project Name] Roadmap

**Date**: [YYYY-MM-DD]
**Scope**: [one-line scope statement]
**Lens set used**: [comma-separated lens names from the derived set — e.g., for SPIRIT: Automation, Coordinator Awareness, Quality, Evolution, Pragmatism, Curiosity & Imagination; for a Python library: API Stability, Type Safety, Docs, Coverage, Performance]
**Lens set source**: [SPIRIT | DORA | SPACE | FAIR | CNCF Platform Maturity | Custom] — [one-line rationale tying to project values]
**Method**: [N] parallel deep-dive audits (one researcher per lens)
**Cartographer version**: [semver or git sha]
**Paradigm detected**: [deterministic | agentic | hybrid]
**Mode**: [fresh | diff | focus]

---

## Executive Summary
<!-- serves: [pick 2-3 lens names from your derived set] -->

[2-3 narrative paragraphs, not bullets. Open with the project's stance relative to the broader landscape (cite one external research anchor). Move to the concrete internal picture (cite one internal metric anchor with evidence). Close with the arc this roadmap traces.]

---

## What's Working (Preserve and Protect)
<!-- serves: all lenses in the derived set; non-negotiable (AC-3) -->

Strengths confirmed across multiple audit lenses. Don't fix what isn't broken.

### [Strength Category 1 — e.g., Architecture & Design]
- **[Strength name]** — [one-sentence claim]. [Evidence: `file:line`, metric, or external consensus]
- **[Strength name]** — [...]

### [Strength Category 2 — e.g., Quality Infrastructure]
- **[Strength name]** — [...]

### [Strength Category 3 — e.g., Content or Tooling]
- **[Strength name]** — [...]

---

## Weaknesses (Critical Issues)
<!-- serves: [quality-oriented lens + pragmatism-oriented lens from derived set]; every weakness must be evidence-grounded -->

### W1. [Weakness Title]

**Description**: [One-paragraph concrete characterization.]
**Impact**: [One-paragraph consequence statement.]
**Evidence**:
- [`file:line` or metric-from-command]
- [command output: `$ cmd` → result]
- [external source: URL (fetched YYYY-MM-DD)]
- [ADR id if relevant — e.g., `dec-NNN`]

**Severity**: [Low | Medium | High | Critical] — [one-line rationale]
**Judgment override** (optional): [If cartographer's severity differs from raw evidence, explain; else omit.]
**Affected files**: [comma-separated paths, or "see Evidence"]

### W2. [Weakness Title] — [same schema as W1]

<!-- Add W3..Wn as needed. -->

---

## Opportunities (Forward Lines)
<!-- serves: [evolution-oriented lens + curiosity-oriented lens from derived set]; non-deficit items — the "road ahead" -->

Forward-looking items driven by **opportunity, not deficit** — new capabilities, strategic bets, evolution trends the project wants to ride, or user-signal-driven directions. Unlike weaknesses (which mark what is currently broken), opportunities mark where the project **could go next** if prioritized. Not every opportunity will be promoted to the Improvement Roadmap in this cycle; cataloguing them here keeps them visible without forcing premature commitment.

Distinguish opportunities from weaknesses: a weakness is something the project **is missing relative to its own goals today**; an opportunity is something the project **could add to extend its reach tomorrow**. When an aspirational item can only be framed as "we don't have X" (deficit language), it belongs in Weaknesses. When it's framed as "X would unlock Y" (opportunity language), it belongs here.

### O1. [Opportunity Title]

**Description**: [One-paragraph characterization — what capability, direction, or bet this represents.]
**Why now**: [What external trend, user signal, adjacent-project traction, or evolution-lens finding points at this. Opportunities are time-sensitive; the "why now" is load-bearing.]
**Evidence**:
- [external research: URL (fetched YYYY-MM-DD)]
- [user signal: issue / transcript / interview reference]
- [adjacent-project traction: repo + metric]
- [internal signal: `file:line` where the project's own shape invites this]

**Potential impact**: [Which lens(es) does this lift? One or two sentences.]
**Confidence**: [High | Medium | Low] — [one-line rationale; opportunities are speculative so honest confidence framing matters]
**Effort estimate**: [S | M | L | XL] — [rough; refined at Improvement Roadmap promotion time]
**Ownership** (optional): [user | cartographer | TBD]

### O2. [Opportunity Title] — [same schema as O1]

<!-- Add O3..On as needed. Cap at ~5 per cycle to keep signal-to-noise high; the point is to name the road ahead, not to catalog every possibility. -->

---

## Improvement Roadmap
<!-- serves: [most lenses in the derived set — improvement items address multiple lenses] -->

Phased, dependency-ordered. Phases may overlap once prerequisites clear. Horizons (Now / Next / Later) express relative urgency, not calendar dates.

### Phase 1: [Phase Title — e.g., Foundation Repair (Critical Path)]
**Horizon**: Now (≤ 5 items). Execute before starting Phase 2.

#### 1.1 [Action — stated as outcome, not implementation]

- **Outcome**: [What the project looks like when this is done.]
- **Motivation**: [Exactly one of: `Weakness Wn` | `Opportunity On` | `Evolution trend` | `Strategic bet` | `User request` | `Prior item id`. Weakness-driven items fix a current deficit; opportunity-driven items extend reach; evolution-trend items track an external shift the project wants to ride; strategic bets are intentional deviations from the current trajectory; user requests cite a specific signal; prior-item motivations chain off completed work.]
- **Evidence**: [`file:line`, metric, ADR id, external URL (fetched YYYY-MM-DD), or Opportunity/Weakness id backing the motivation.]
- **Dependencies**: [Wn / On / prior item id / "—"]
- **Risk**: [Low | Medium | High] — [one-line rationale]
- **Next pipeline action**: [Downstream agent or command — e.g., "hand to `implementation-planner` via `/plan`"; "queue for `sentinel`"; "spawn `researcher`"] (required — AC-12)
- **Ownership** (optional): [user | cartographer | TBD]
- **Next-step by** (optional): [YYYY-MM-DD]

#### 1.2 [Action] — [same per-item schema as 1.1]

### Phase 2: [Phase Title]
**Horizon**: Next. Depends on Phase 1 completion.
#### 2.1 [Action] — [same per-item schema as 1.1]

### Phase 3: [Phase Title — e.g., "Strategic Horizons" when items are Opportunity-driven]
**Horizon**: Later. Can overlap with Phase 2 once Phase 1 Now items clear. When this phase's items are primarily Opportunity-motivated or Strategic-bet-motivated (not Weakness-motivated), the conventional label is "Strategic Horizons" — it signals the phase is forward vision rather than deficit repair.
#### 3.1 [Action] — [same per-item schema as 1.1]
<!-- Every phase item MUST name a Motivation AND a Next pipeline action. Mixed motivations (some weakness-driven, some opportunity-driven) within one phase are fine; label the phase by the dominant motivation. -->

---

## Deprecation & Cleanup
<!-- serves: [pragmatism-oriented lens + quality-oriented lens from derived set] -->

| Item | Action | Phase |
|------|--------|-------|
| [path or name] | [KEEP with rationale / DELETE / MIGRATE to X / CONSOLIDATE with Y] | [N] |
| [path or name] | [...] | [N] |

---

## Quality Metrics
<!-- serves: [quality + pragmatism lenses from derived set] — every metric names its measurement methodology -->

Metric cap: one per phase item.

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| [metric name] | [value or "Unknown"] | [value or conservative/optimistic range] | [command or document path used] |
| [metric name] | [...] | [...] | [...] |

**Footnotes** (optional): [Tokenizer assumptions, ratios, scope carveouts.]

---

## Guiding Principles for Execution
<!-- serves: automation + pragmatism lenses from derived set — cross-reference project principles; do not re-author -->

Project-level principles live at their canonical homes.
- [README.md#guiding-principles](../README.md#guiding-principles) — project core principles
- [ROADMAP.md#guiding-principles-for-execution](../ROADMAP.md#guiding-principles-for-execution) — prior roadmap's execution rubric (when one exists)

Roadmap-specific execution principles (only the ones unique to this cycle):
1. **Evidence-grounded decisions** — every quantitative claim cites a source. See `skills/roadmap-synthesis/references/grounding-protocol.md`.
2. **User-gated architecture decisions** — deletions and architecture/design/deployment decisions always surface for user approval.
3. **[Additional cycle-specific principle, if any]** — [one-line rationale].

---

## Methodology Footer
<!-- serves: pragmatism + quality lenses from derived set — audit trail -->

Produced by the `roadmap-cartographer` agent via the `roadmap-synthesis` skill.
- **Lens set used**: [comma-separated lens names]
- **Lens set source**: [SPIRIT | DORA | SPACE | FAIR | CNCF Platform Maturity | Custom] — [rationale for fit with project values and constraints]
- **Lens derivation inputs**: [project values extracted from: README section X, CLAUDE.md section Y; domain constraints: paradigm=P, deployment=D, stakeholders=S]
- **Researcher count**: [N researchers spawned in parallel via the Task tool]
- **Evidence sources consulted**: [file count, command count, external-source count]
- **Paradigm detected**: [deterministic | agentic | hybrid] — [one-line rationale]
- **Mode**: [fresh | diff | focus] — [one-line rationale]
- **Cartographer version**: [semver or git sha]
- **Generated**: [ISO 8601 timestamp, UTC]

---

## Decision Log
<!-- PRESERVE VERBATIM across regenerations. Append-only. -->

Roadmap-level decisions recorded as the document evolves. ADR-worthy decisions also land in `.ai-state/decisions/` per the ADR conventions.

- `[YYYY-MM-DD]` — [Decision] — by [user | cartographer]. Rationale: [...]. [Links to ADR ids.]

<!-- Append new entries below; never rewrite prior entries. -->
