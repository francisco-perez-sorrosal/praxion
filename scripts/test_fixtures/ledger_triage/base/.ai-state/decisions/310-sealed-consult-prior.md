---
id: dec-310
title: The convener seals a lens-run prior list before spawning a consultant, and the seal is tamper-evident rather than tamper-proof
status: accepted
category: architectural
date: 2026-07-31
summary: td-081 resolved by .ai-state/CONSULT_PRIORS.md -- a sibling append-only single-writer file with two tables, joined on the (task-slug, discipline, stage) triple, with a cross-file fitness gate.
tags: [consult-ledger, discipline-consultant, instrumentation, falsifier, estimand, gate-liveness, tech-debt, seal, lens-vs-consultant, framing]
superseded_in_part_by:
  - dec-375
affected_files:
  - .ai-state/CONSULT_PRIORS.md
  - fitness/tests/test_discipline_registry_invariants.py
  - agents/discipline-consultant.md
---

Fixture stub: frontmatter only, reproducing dec-310's live status/edges for the ledger-triage test corpus.
