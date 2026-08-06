---
id: dec-043
title: Introduce a four-behavior Agent Behavioral Contract as a first-class operational pillar
status: accepted
category: behavioral
date: 2026-04-13
summary: Name Surface Assumptions, Register Objection, Stay Surgical, Simplicity First in an always-loaded rule, cross-reference from CLAUDE.md at both scopes, introduce as README fifth Guiding Principle, inject one-line pointer into 10 pipeline agents, and enforce via six named failure-mode tags in verification reports
tags: [behavioral-contract, philosophy, rules, agents, verifier, always-loaded, budget]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/agent-behavioral-contract.md
  - skills/software-planning/references/behavioral-contract.md
  - skills/software-planning/SKILL.md
  - skills/code-review/references/report-template.md
  - claude/config/CLAUDE.md
  - claude/config/CLAUDE.md
  - CLAUDE.md
  - README.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/context-engineer.md
  - agents/implementer.md
  - agents/test-engineer.md
  - agents/verifier.md
  - agents/doc-engineer.md
  - agents/sentinel.md
  - agents/cicd-engineer.md
  - .ai-state/DESIGN.md
affected_reqs: [REQ-BC-1, REQ-BC-2, REQ-BC-3, REQ-BC-4, REQ-BC-5, REQ-BC-6, REQ-BC-7]
---

## Context

A content audit (`PRIOR_RESEARCH_FINDINGS.md`, 2026-04-13) surfaced a gap between Praxion's philosophy layer and its operational enforcement surface: Karpathy's four disciplined-assistant behaviors — Surface Assumptions, Register Objection, Stay Surgical, Simplicity First — are partially implied by the existing Principles and Methodology in `~/.claude/CLAUDE.md`, but are never **named** as a contract, never **enforced** via any check, and — in the case of Register Objection — never **mentioned at all** in any rule, agent prompt, skill, or philosophy document.

The follow-up integration study (`RESEARCH_FINDINGS.md`, 2026-04-13) mapped coverage per behavior and confirmed the gap:

- Surface Assumptions: strong philosophy coverage (`~/.claude/CLAUDE.md:37`, `:41`), no operational directive.
- Register Objection: **absent** — zero occurrences of "disagree", "challenge the user", "register objection" across rules, CLAUDE.md, agents, or README.
- Stay Surgical: partial — covered by BDD and Incremental Evolution principles, no named directive.
- Simplicity First: partial — covered by Incremental Evolution ("simplest thing that works"), not operationalized as a check.

Naming these behaviors enables measurement: once named, the verifier can emit tagged findings (`[MISSING-OBJECTION]`, `[NON-SURGICAL]`, etc.), the sentinel can aggregate tag frequencies across features, and skill-genesis can harvest recurring contract violations as signals for new patterns. Without naming, the behaviors remain implicit intent — felt when followed, invisible when broken.

The always-loaded budget (15,000 tokens, currently 96.8% utilized per `ROADMAP.md:54`) constrains where the contract can live. The architectural question is not "should we name these behaviors" (the audit answered that) but "where should the name live, at what cost, and in what relationship to existing philosophy".

## Decision

Introduce the **Agent Behavioral Contract** as a first-class operational pillar with the following architecture:

1. **One always-loaded rule** at `rules/swe/agent-behavioral-contract.md` (≤800 chars, no `paths:` frontmatter) that names the four behaviors, states each as a directive, and carries a self-test question bank. This is the canonical source of the four behavior names and their ordering.

2. **One progressive-disclosure reference** at `skills/software-planning/references/behavioral-contract.md` (~3,500–4,500 chars, on-demand via the `software-planning` skill) containing definitions, per-agent application guidance, objection-registration templates, and an explicit "Relationship to coding-style DRY" subsection.

3. **Philosophy-layer anchor** in `~/.claude/CLAUDE.md`: new section "The Behavioral Contract" between Methodology and Learning Loop, framing the contract as *stance under pressure* rather than *phase in the workflow*. Mirrored in `claude/config/CLAUDE.md`.

4. **Project-layer pointer** in `CLAUDE.md` (repo root): ≤55-token section referencing the rule and skill reference. No re-definition — single source of truth is the rule.

5. **README fifth Guiding Principle** "Behavioral contract over polite compliance" — parallel in style to the existing four, introducing the four behavior names with hyphen-em-dash formatting and closing on the enforcement mechanism (rule + self-tests + tags).

6. **Per-agent one-line injection** in 10 pipeline agents that write, plan, or review artifacts: `researcher`, `systems-architect`, `implementation-planner`, `context-engineer`, `implementer`, `test-engineer`, `verifier`, `doc-engineer`, `sentinel`, `cicd-engineer`. Each injection is a single line (≤160 chars) in the agent's Constraints / Boundary Discipline / Self-Review section. Three agents (`promethean`, `skill-genesis`, `roadmap-cartographer`) receive no injection — they don't emit code/plan/review artifacts; the always-loaded rule suffices.

7. **Six named failure-mode tags** in `skills/code-review/references/report-template.md`, new subsection "Behavioral Contract Findings": `[UNSURFACED-ASSUMPTION]` (Surface Assumptions), `[MISSING-OBJECTION]` (Register Objection), `[NON-SURGICAL]` and `[SCOPE-CREEP]` (Stay Surgical — split into collateral-damage and capability-creep), `[BLOAT]` and `[DEAD-CODE-UNREMOVED]` (Simplicity First). Emitted by the verifier during Phase 5 Convention Compliance.

8. **Four new sentinel checks BC01–BC04** auditing the contract's integrity: rule presence and unscoped status (BC01), CLAUDE.md anchor presence with canonical ordering (BC02), per-agent injection presence (BC03), report-template tag vocabulary presence with six canonical tags (BC04).

**Budget coupling**: contract cost (~498 tokens added to always-loaded surface) is offset by path-scoping `rules/swe/coding-style.md` (−1,900 tokens), executed as a separate commit in the same PR — see `dec-044`. Net always-loaded delta: **−1,402 tokens** (reclaimed).

## Considered Options

### Option 1 — Host behaviors in existing rule `coding-style.md`

**Pros:** No new file; no always-loaded cost beyond content.
**Cons:** `coding-style.md` declares itself "language-independent structural and design conventions" (file header). Its scope is syntactic (function size, nesting, naming, immutability, error handling). Adding behavioral directives ("register objection when a request violates scope") violates its charter and conflates two concerns. A future skill-crafting reader looking for structural conventions would be surprised by stance-under-pressure directives. **Rejected.**

### Option 2 — Host behaviors in existing rule `swe-agent-coordination-protocol.md`

**Pros:** Already the home for agent-agnostic conventions.
**Cons:** Already the single largest always-loaded artifact (14,127 chars / 3,412 tokens, flagged at `ROADMAP.md:54` as the primary budget offender). Adding ~800 chars here deepens the budget problem; Phase 1A already extracted procedural content from this rule (`dec-022`) specifically to slim it. **Rejected.**

### Option 3 — New always-loaded rule `rules/swe/agent-behavioral-contract.md` (chosen)

**Pros:** Fits the "declarative, not procedural" charter of `rules/` (per `rules/CLAUDE.md:5`). Unconditional load ensures coverage during planning-only and review-only sessions where no file is yet open. ≤800-char budget is within the ~350-token new-content envelope when paired with the `dec-044` offset. Pattern (always-loaded rule + on-demand reference) is proven by `dec-022`.
**Cons:** Adds one more file to always-loaded scan surface (minor discovery cost). Requires offset to stay under budget ceiling.

### Option 4 — Skill-only placement at `skills/agent-behavioral-contract/SKILL.md`

**Pros:** Zero always-loaded cost beyond the SKILL.md metadata blob (~200 chars).
**Cons:** Agents only see skill content when the skill activates. A contract that fires under pressure must be in context *before* pressure arrives — progressive disclosure is structurally wrong for this use case. The contract would be silent exactly when an agent is about to take a shortcut. **Rejected.**

### Option 5 — Philosophy-only placement (add prose to `~/.claude/CLAUDE.md`, no rule, no skill, no tags)

**Pros:** No rule sprawl; relies on existing philosophy mechanism.
**Cons:** The gap the audit identified is *not* that philosophy is missing — it is that philosophy is **implied but not named and not enforced**. Adding prose to CLAUDE.md without a measurable enforcement surface (tags, sentinel checks) does not close the gap. The Register Objection clause in particular needs named tag support so recurrence is trackable. **Rejected on its own; partially adopted as a component of Option 3 (the chosen solution has both a CLAUDE.md section and a rule).**

## Consequences

**Positive:**

- Register Objection gains a named operational directive for the first time in Praxion; previously absent at every layer (philosophy, rule, agent prompt, README).
- Surface Assumptions, Stay Surgical, and Simplicity First gain a named tag vocabulary that lets the verifier emit structured findings — downstream consumers (sentinel aggregation, skill-genesis pattern harvest) get data they did not have before.
- Single-definition principle: the rule is the only place the four behaviors are defined; all other surfaces echo or point. Vocabulary drift is caught automatically by sentinel BC02/BC04.
- Budget posture improves: net −1,402 tokens, moving always-loaded utilization from 96.8% to ~87.5% — 12.5% headroom for future ecosystem growth (principles, new rules, extended coordination content).
- Follows proven patterns: "always-loaded rule + on-demand skill reference" (dec-022), "text addition + offsetting path-scope in the same PR" (dec-027 + dec-028), "bracket-tag findings in verifier reports" (`[Security:*]`, `[Architecture:*]` precedents).

**Negative:**

- Six new files/sections to keep in sync across evolution of the contract (rule, skill ref, global CLAUDE, project CLAUDE, README principle, report-template tag subsection). Mitigated by sentinel BC01–BC04 which fail any health grade where drift is present.
- The behavior's imperative phrasing risks adverse interaction with future LLM safety tuning — agents may read a blunt directive as "refuse" rather than "state a reason and decide". Mitigated by naming the behavior **Register Objection** (canonical) and framing it in the rule + skill reference as "state the conflict with a reason before complying or declining — not refusal". If `[MISSING-OBJECTION]` tag emissions spike after a model update, revisit phrasing.
- Six agents have existing ambiguity/interpretation clauses that now overlap with Surface Assumptions and Register Objection. This Phase 1 leaves those clauses in place; consolidation is deferred to Phase 2 after observing empirical tag-emission frequencies.
- The `~/.claude/CLAUDE.md` modification is user-scope — it affects every project on the user's machine. Implementation requires user consent; not an autonomous edit. Praxion-preserved mirror at `claude/config/CLAUDE.md` is edited autonomously.

**Operational:**

- **Commit ordering:** path-scoping commit (dec-044) lands first, then contract commit. Both commits in the same PR per git-conventions "one logical change per commit" and the budget coupling that prevents the contract from landing without the offset.
- **Rollback:** reverting the contract commit removes all contract content but retains the reclaimed budget from dec-044 — safe partial state. Reverting both commits restores full pre-change state.
- **Verifier engagement:** new Phase 5.5 sub-phase scans for tag-eligible violations and emits findings using the six canonical bracket tags. Sentinel aggregates across VERIFICATION_REPORT_*.md archives (existing mechanism for `[Security:*]`).
- **Deferred work explicitly listed in SYSTEMS_PLAN.md Out of Scope:** MUST-2 (PR-reviewer CI), MUST-3 (eval harness), SHOULD-1 (writer/reviewer shadow), SHOULD-2 (active memory recall), ambiguity-clause consolidation (Phase 2 follow-up), full-paragraph injection upgrade (Phase 2 conditional).
- **Evolution path:** if empirical tag-emission data shows certain agents are not consulting the rule, specific one-line injections may be upgraded to full-paragraph injection in Phase 2. If the contract grows beyond four behaviors, a dedicated `agent-behavioral-contract` skill may be warranted; this ADR can be superseded at that point.
