---
id: dec-511
draft_id: dec-draft-66ca6b02
title: "Small debt is fixed after the feature through a follow-up record the cleanup gate blocks on"
status: accepted
category: architectural
date: 2026-11-12
summary: "Debt found during a task that meets a seven-condition small bar goes to a per-task FOLLOW_UPS.md record (open, fixed <sha>, ledgered td-NNN, dropped <reason>) parsed by one grammar module; the orchestrator closes each item after the feature, and the cleanup gate BLOCKs while any item is open."
tags: [tech-debt, follow-ups, cleanup-gate, artifact-registry, verifier]
made_by: agent
agent_type: systems-architect
branch: feat/process-principles
pipeline_tier: standard
affected_files:
  - scripts/_follow_ups.py
  - scripts/clean_work_safety.py
  - scripts/artifact_registry.py
  - rules/swe/agent-intermediate-documents.md
  - skills/software-planning/references/tech-debt-ledger.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/coordination-details.md
  - claude/kernels/src/ledger-writer.md
  - claude/kernels/src/ledger-writer-verifier-overlay.md
  - agents/verifier.md
  - agents/implementer.md
affected_reqs: [REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12]
---

## Context

In the 30 days before this decision, 205 ledger rows were filed, about 7 a day. Many were one-file warnings from a verification. The user decided two things:

- Debt found while solving a task is fixed in its own commit after the feature when it is small.
- A row is filed only when the debt is not small, or when it could not be finished this session.

Small means all seven conditions: at most two production files plus their tests; no design decision or ADR; no new dependency; no acceptance, end-to-end or frozen test change; nothing on the ask-first list; no shipped-contract change; it fits in the session.

## Decision

- **The record.** A per-task `.ai-work/<task-slug>/FOLLOW_UPS.md` holds one item per line, shaped `- [<state>] <description>`. The state is one of `open`, `fixed <sha>`, `ledgered td-NNN` or `dropped <reason>`. A new stdlib-only module, `scripts/_follow_ups.py`, owns the grammar in its docstring and parses lines into a sum type. An unreadable line, or a final state whose argument is missing or misshapen, counts as open.
- **Who writes.** The verifier and the orchestrator append open items. The implementer reports such debt on an optional `Follow-ups:` line inside its existing at-most-5-line return. Only the orchestrator writes the final states, in a follow-up pass after the feature's last commit and the verifier: each item is fixed test-first in its own commit with the derived test scope, or ledgered with a reason, or dropped. No extra verifier spawn runs.
- **The gate.** `scripts/clean_work_safety.py` gains a BLOCK reason read through the parser. The registry registers the record under `block-if-active`, together with its dashboard, snapshot and inventory consumers.
- **Verifier-only text.** It lives in the `local-verifier` kernel overlay. The condensed `ledger-writer` text, which also reaches the sentinel and the architect-validator, changes only its orchestrator clause. Both keep filing every finding.
- **Lower tiers.** At Direct and Lightweight tiers, the session's task list holds the items.

## Considered Options

- **A per-task record, one parser, the existing gate (chosen).**
- **A section in `LEARNINGS.md`.** It has no closed state set, its cleanup class is already WARN, and the verifier already harvests it into rows.
- **A new ledger status.** It is persistent, and it fills the ledger the rule means to stop filling.
- **A new gate.** The user decided to reuse the cleanup gate.

## Consequences

- **Positive.** Small debt is paid in the session that found it, in separate named commits. The ledger keeps only what cannot be fixed now. A task directory with unfinished follow-ups cannot be cleaned.
- **Negative.** It adds one more artifact and one more parser. A malformed line falsely BLOCKs cleanup, which is the safe direction. Follow-up fixes land after verification and are guarded only by test-first and the derived scope.

## Disconfirmation

- **Falsifier.** The open-row count keeps rising at the same rate after the rule lands. Or a task directory with an open follow-up is classified other than BLOCK.
- **Steelmanned runner-up.** A `### Follow-ups` section in `LEARNINGS.md` reuses an existing artifact and needs no registry entry. It loses because it has no closed state set the gate can parse, and because its lifecycle (WARN, harvested into rows) is the filing path the rule replaces.
- **Reversal trigger.** Follow-up fixes after verification regress behaviour that the derived scope missed. Then add a light verification of follow-up commits, or move the pass before the verifier.

**Activation:** no. The user decided the behaviour and the gate reuse; only the representation was open.
