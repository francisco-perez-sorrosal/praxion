---
id: dec-049
title: Re-affirm dec-022 and ship symmetry + lightweight-tier + tier-template cohort
status: accepted
category: architectural
date: 2026-04-16
summary: Drop the proposed delegation-checklist extraction (dec-022 Option 4 rejection still binds); ship six orthogonal deliverables (D1 condensed-block symmetry, D2 tier-templates.md, D3 Lightweight gap closure, D4 tier-selector tree, D5 validator regression test, D6 persistence); re-affirm, do not supersede, dec-022.
tags: [re-affirmation, coordination-protocol, lightweight-tier, tier-templates, token-budget, progressive-disclosure, decision-quality]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - claude/config/CLAUDE.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/tier-templates.md
  - skills/software-planning/SKILL.md
  - skills/skill-crafting/tests/test_validate_references.py
  - .ai-state/memory.json
affected_reqs: []
supersedes:
superseded_by:
---

## Context

ROADMAP Phase 2.3 Point #1 proposed extracting the `### Delegation Checklists` block (lines 60–86 of `rules/swe/swe-agent-coordination-protocol.md`) into a new on-demand skill reference `skills/software-planning/references/delegation-checklists.md`, with the rationale of freeing ~375–500 tokens of always-loaded content.

This proposal was audited by the researcher (`RESEARCH_FINDINGS.md` Section 3 Objection) and the context-engineer (`CONTEXT_REVIEW.md` F1, CRITICAL), both of whom independently flagged a direct conflict with an in-force accepted ADR: `dec-022` (2026-04-11) whose Option 4 rejected aggressive extraction "including delegation checklists" with three explicit reasons:

1. Higher risk of degrading main-agent decision quality — delegation checklists drive prompt construction on every delegation, frequent enough that keeping them always-loaded is worthwhile
2. Single-pass aggressive extraction prevents the learning loop (observe, iterate) that ecosystem health benefits from
3. Exceeds the clear threshold of "content that describes a *procedure to run*" — delegation checklists describe *what to put in the prompt*, not *how to execute the prompt*

No new evidence was produced to justify reversing dec-022. The budget pressure that would have motivated a reversal is absent: current always-loaded content measures ~10,003 tokens (CONTEXT_REVIEW.md baseline) / ~11,072 tokens conservative (RESEARCH_FINDINGS.md Section 8) against a 15,000-token ceiling, leaving ~3,900–5,000 tokens of headroom. Extracting the block would save only ~370–422 tokens.

A second, independent finding (RESEARCH_FINDINGS.md Section 3.2) surfaced three real regressions in `claude/config/CLAUDE.md` lines 45–49: the condensed deliverables block omits three conditional deliverables present in the rule's detailed checklists (`SYSTEM_DEPLOYMENT.md`, `TEST_RESULTS.md` implementer-write, `TEST_RESULTS.md` verifier-read). The ROADMAP's stated mitigation — "`claude/config/CLAUDE.md` now has condensed deliverables" — is partially false.

A third cluster of findings (RESEARCH_FINDINGS.md Section 6) enumerated eleven specification gaps in the Lightweight tier definition; five are high-severity (agent availability, acceptance-criteria placement, delegation-prompt expectation, test handoff, architecture-doc updates).

A fourth finding (RESEARCH_FINDINGS.md Section 5) mapped greenfield space for a tier-template artifact orthogonal to delegation-checklist content.

A fifth finding (RESEARCH_FINDINGS.md Section 7) confirmed that dec-047's cross-reference validator already FAILs on missing cross-file anchors — no new anchor-resolution tool is needed.

The user confirmed "Refined Path 2": drop the extraction; ship a cohort of six orthogonal deliverables that deliver the real value the ROADMAP implied without contradicting dec-022.

## Decision

Ship six orthogonal deliverables and document the drop of ROADMAP 2.3 Point #1 as a principled decision, not an oversight:

1. **D1 — Condensed-block symmetry fix** in `claude/config/CLAUDE.md` lines 45–49: add three conditional-deliverable bullets (closing research GAPs 1, 2, 3) plus a one-line sync-contract pointer naming the coordination rule as the authoritative source of truth. The detailed `### Delegation Checklists` section in the rule is unchanged.
2. **D2 — Tier-templates reference**: create `skills/software-planning/references/tier-templates.md` with parametric prompt scaffolds (Standard + Full full scaffolds, Lightweight snippet) using angle-bracket placeholders inherited from the existing `[Phase: <Name>]` convention. Register in `software-planning/SKILL.md` satellite-files list. Explicitly does NOT duplicate delegation-checklist content — the template shells link to the rule's checklists as the payload source.
3. **D3 — Lightweight tier inline gap closure**: close research Section 6 high-severity gaps 1, 2, 4, 5, 8 with ≤ 500 B of inline additions to `rules/swe/swe-agent-coordination-protocol.md` Process Calibration section. Defer gaps 3, 6, 7, 9, 10, 11.
4. **D4 — Tier-selector decision tree**: append a 6–8-line fast-path decision tree to the Process Calibration section of the same rule. Explicitly points to the SDD `calibration-procedure.md` for formal signal scoring.
5. **D5 — Regression test via dec-047 validator**: extend `skills/skill-crafting/tests/test_validate_references.py` to assert the post-edit coordination rule passes `validate_references.py --strict`. No new validator script.
6. **D6 — Triple persistence**: this ADR (persistent, git-committed, DECISIONS_INDEX-listed) + `LEARNINGS.md` entry (pipeline-run ephemeral) + `remember()` call creating memory entry `dec-022-delegation-checklist-reaffirm-2026-04` (cross-session). Memory entry importance 7; tags include `re-affirmation` and `dec-022`.

**Re-affirmation semantics:** dec-022 is re-affirmed, not superseded. Its `status` remains `accepted`; no `superseded_by` field is set on it. This ADR's `supersedes:` field is intentionally empty. Re-affirmation signals that a re-opening was considered against the prior decision and rejected for lack of new evidence — stronger than silent concurrence, gentler than supersession.

## Considered Options

### Option A: Execute the extraction (ROADMAP 2.3 Point #1 as stated)

**Pros:**
- Reclaims ~370–422 tokens of always-loaded budget
- Matches the ROADMAP item as written
- Completes Phase 2.3 Point #1 in one pass

**Cons:**
- Directly contradicts accepted ADR `dec-022` (Option 4 explicitly rejected this) — silent contradiction of an in-force ADR is a behavioral-contract violation at the ecosystem level
- Creates a decision-quality regression risk for ad-hoc delegation (`CONTEXT_REVIEW.md` F2): when the main agent delegates without the `software-planning` skill being active, the extracted reference is not loaded
- Budget pressure justifying reversal does not exist — ~3,900–5,000 tokens of headroom available
- Would need to be paired with a supersession ADR citing new evidence (decision-quality measurements, changed loading semantics) — no such evidence exists

### Option B: Drop the extraction; ship the orthogonal cohort (selected)

**Pros:**
- Honors dec-022 without requiring supersession
- Closes real regressions identified by the research (GAPs 1–3 in `claude/config/CLAUDE.md`, 5 high-severity Lightweight gaps)
- Adds the tier-templates artifact as a genuinely orthogonal capability (dec-022 did not rule this out)
- Uses dec-047's existing validator instead of introducing new tooling
- Persists the re-affirmation in three places so a future agent cannot revive the extraction silently

**Cons:**
- Adds ~600–700 B of always-loaded content (D1 ~300 B + D3 ~500 B + D4 ~400 B — net around +900 B after subtracting nothing, since the extraction is dropped). Budget headroom absorbs this comfortably.
- The "Phase 2.3 Point #1" roadmap item requires explicit closure as "not executed per dec-049" rather than "done"

### Option C: Partial extraction (e.g., extract only the per-agent sub-blocks, keep the intro paragraph)

**Pros:**
- Preserves the section header and intro as always-loaded visual anchor while moving the bulk of the content to a reference

**Cons:**
- Same decision-quality regression class as Option A for the extracted sub-blocks — what is extracted cannot be relied upon at ad-hoc delegation time
- Creates a fragmented section (three lines always-loaded, twenty-three lines on-demand) that is harder to understand than either extreme
- Dec-022's Option 4 rejection reasoning applies equally to a partial extraction — the decision-quality concern is about the sub-blocks, not the intro

## Consequences

**Positive:**
- dec-022 is preserved and strengthened — any future proposal to extract delegation checklists must produce new evidence and formally supersede both dec-022 and dec-049
- Three concrete regressions in `claude/config/CLAUDE.md` are closed (D1)
- Tier-templates.md gives the main agent a prompt-structural scaffold orthogonal to delegation-checklist content, closing a genuine greenfield gap
- Lightweight tier is more actionable for the five highest-impact use cases
- Tier-selector fast path reduces the always-loaded calibration decision to a 6-line tree with a pointer to formal scoring for ambiguous cases
- Validator coverage of the coordination rule is asserted via a regression test, with no new tool
- Memory + LEARNINGS + ADR triple persistence ensures the decision trail is durable

**Negative:**
- Net always-loaded footprint increases by ~600–900 B (small against the ~3,900+ token headroom)
- ADR frontmatter schema does not yet enumerate `re-affirmation` as a first-class concept — using `status: accepted` + tag `re-affirmation` is a pragmatic fit; if the pattern recurs, a future ADR can promote it to a formal `status: re-affirmed` value (FW-3 in SYSTEMS_PLAN.md)
- D1's sync contract between `claude/config/CLAUDE.md` and the rule is declarative, not tool-enforced — drift is possible until a sentinel check is added (FW-1)

**Operational:**
- `install_claude.sh` propagates the `claude/config/CLAUDE.md` change to `~/.claude/CLAUDE.md` on next install (same pathway as dec-022)
- The six deliverables are implementable in five independent commits (D1; D2 is two files but one topic; D3+D4 may share a commit; D5; D6 is the ADR+LEARNINGS+memory triple)
- No CI workflow changes; dec-047's existing `validate-context-artifacts` job covers the new test
- ROADMAP 2.3 Point #1 status: close as "not executed; dropped per dec-049 re-affirmation of dec-022"

## Prior Decision

**dec-022** (2026-04-11, `Extract coordination procedures to on-demand skill reference`) is re-affirmed by this ADR. dec-022's status remains `accepted`; no `superseded_by` field is set on it. This ADR does not overturn, weaken, or qualify dec-022 — it strengthens it by:

1. Publicly recording that a re-opening was considered and rejected for lack of new evidence
2. Documenting the specific evidence that would be required to justify a future supersession (new decision-quality measurements, changed loading semantics of the `software-planning` skill, a formal supersession ADR)
3. Shipping orthogonal value (D1–D6) that dec-022 did not rule out, delivering the real improvements the ROADMAP implied while preserving dec-022's decision-quality guardrail

Any future agent proposing delegation-checklist extraction must discover this ADR (via `DECISIONS_INDEX.md` tag filter on `re-affirmation` or `coordination-protocol`), read dec-022, and produce new evidence meeting the three bars above. Absent such evidence, re-proposing the extraction is a regression of dec-049 and violates the behavioral contract's Register-Objection clause at the ecosystem level.
