---
id: dec-305
title: Project-local discipline registry overlay with collision-as-error precedence
status: accepted
category: architectural
date: 2026-07-30
summary: A managed project may add consulting disciplines via an optional .ai-state overlay unioned with the shipped registry; a duplicate key is a named [BLOCKED] error, never an override.
tags: [multi-perspective-analysis, discipline-consultant, extensibility, registry, fail-loud, plugin-distribution]
affected_files:
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - agents/discipline-consultant.md
  - fitness/tests/test_discipline_registry_invariants.py
  - .ai-state/discipline_registry_overlay.md
---

Fixture stub: frontmatter only, reproducing dec-305's live status/edges for the ledger-triage test corpus.
