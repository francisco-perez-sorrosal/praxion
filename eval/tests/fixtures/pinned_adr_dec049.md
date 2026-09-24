---
# PINNED FIXTURE — verbatim frontmatter excerpt of
# .ai-state/decisions/049-reaffirm-dec022-coord-cohort.md
# at commit 756728d1ca91b259c156b0de64c41781cc4a28e0 (2026-09-24).
# Copied so a later, legitimate edit to the live corpus cannot flip this
# fixture's reciprocity test red. Pairs with pinned_adr_dec022.md, whose
# `re_affirmed_by: [dec-049]` is the reciprocal back-link this scalar
# `re_affirms: dec-022` requires.
id: dec-049
title: Re-affirm dec-022 and ship symmetry + lightweight-tier + tier-template cohort
status: re-affirmation
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
re_affirms: dec-022
---

## Context

Fixture excerpt — frontmatter only, body omitted. `_parse_frontmatter` reads only up to
the closing `---`, so the body carries no test-relevant content.
