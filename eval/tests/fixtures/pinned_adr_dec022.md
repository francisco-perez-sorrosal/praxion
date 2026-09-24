---
# PINNED FIXTURE — verbatim frontmatter excerpt of
# .ai-state/decisions/022-coordination-detail-extraction.md
# at commit 756728d1ca91b259c156b0de64c41781cc4a28e0 (2026-09-24).
# Copied so a later, legitimate edit to the live corpus cannot flip this
# fixture's parser/reciprocity test red. Pairs with pinned_adr_dec049.md,
# a verbatim excerpt of the same commit's dec-049, which carries the
# reciprocal `re_affirms: dec-022` scalar.
id: dec-022
title: Extract coordination procedures to on-demand skill reference
status: accepted
category: architectural
date: 2026-04-11
summary: Move procedural detail from always-loaded coordination rules to a new on-demand `coordination-details.md` reference, preserving anchors for cross-references.
tags: [token-budget, progressive-disclosure, skills, rules, refactoring, coordination-protocol]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/swe/agent-intermediate-documents.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/SKILL.md
  - claude/config/CLAUDE.md
re_affirmed_by:
  - dec-049
---

## Context

Fixture excerpt — frontmatter only, body omitted. `_parse_frontmatter` reads only up to
the closing `---`, so the body carries no test-relevant content.
