---
# PINNED FIXTURE — verbatim frontmatter excerpt of
# .ai-state/decisions/020-architecture-md-living-artifact.md
# at commit 756728d1ca91b259c156b0de64c41781cc4a28e0 (2026-09-24).
# Copied so a later, legitimate edit to the live corpus cannot flip this
# fixture's parser test red. Do not edit to "track" the corpus — if the
# real ADR's shape changes, that is not a reason to touch this file; only
# a real change to the frontmatter parser's contract is.
id: dec-020
title: Living ARCHITECTURE.md artifact in .ai-state/
status: superseded
superseded_by: dec-021
category: architectural
date: 2026-04-10
summary: Persistent architecture document maintained by pipeline agents via section ownership, stored in .ai-state/, following the SYSTEM_DEPLOYMENT.md precedent
tags: [architecture, documentation, ai-state, living-document, agent-pipeline]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/ARCHITECTURE.md
  - skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md
  - skills/software-planning/references/architecture-documentation.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/verifier.md
  - agents/sentinel.md
  - agents/researcher.md
  - agents/promethean.md
  - rules/swe/agent-intermediate-documents.md
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/SKILL.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/doc-management/references/documentation-types.md
---

## Context

Fixture excerpt — frontmatter only, body omitted. `_parse_frontmatter` reads only up to
the closing `---`, so the body carries no test-relevant content.
