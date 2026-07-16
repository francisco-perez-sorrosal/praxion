---
id: dec-103
title: TECH_DEBT_LEDGER source enum widened to include orchestrator
status: accepted
category: behavioral
date: 2026-04-30
summary: 'Widen the TECH_DEBT_LEDGER source enum from verifier|sentinel to verifier|sentinel|orchestrator so explicit-user-directed writes from the main agent carry honest provenance instead of misattributing to sentinel/verifier.'
tags: [tech-debt-ledger, ledger-conventions, source-enum, ledger-writers, behavioral]
made_by: user
pipeline_tier: standard
affected_files:
  - rules/swe/agent-intermediate-documents.md
  - .ai-state/TECH_DEBT_LEDGER.md
re_affirmed_by:
  - dec-105
---

## Context

The TECH_DEBT_LEDGER schema in `rules/swe/agent-intermediate-documents.md` defined a `source` field with a closed enum: `verifier | sentinel`. The accompanying prose said "Writers (only two): verifier, sentinel" and "No other agent writes ledger rows."

In practice, two patterns of legitimate orchestrator-led writes have emerged:

1. **Pre-existing td-002** (filed 2026-04-27): a row was filed by the orchestrator mid-pipeline because the finding (canonical-block size budget violation) did not fit verifier's per-change scope or sentinel's periodic-audit scope. The notes record the deviation: *"Filed by orchestrator mid-pipeline (slight protocol stretch — canonical sources are verifier and sentinel); verifier may re-source."*

2. **AaC+DaC v1 P0a M2 work** (filed 2026-04-30): four rows (td-007 through td-010) were filed by the main agent under explicit user direction to persist compression opportunities surfaced during the P0a reconnaissance pass. To fit the closed enum, they were tagged `source: sentinel` — a misattribution that the verifier's design-stage review (D8-FAIL-1 in `VERIFICATION_REPORT.md`) flagged as a schema violation.

The pattern is recurring and structural: when the user explicitly directs the main agent to file a debt finding that is grounded but does not fit either the per-change or the periodic-audit scope, neither extant enum value is honest. The `notes` field can document the deviation, but the `source` field carries an incorrect value.

## Decision

Widen the `source` enum to `verifier | sentinel | orchestrator`, with `orchestrator` reserved for explicit-user-direction writes from the main agent. Update the "Writers" prose accordingly to acknowledge three writers, and clarify that `orchestrator` writes are the exception — `verifier` and `sentinel` remain the canonical producers and may re-source orchestrator-filed rows on subsequent runs.

Concretely:

- `rules/swe/agent-intermediate-documents.md` — `source` enum row updated from `verifier | sentinel` to `verifier | sentinel | orchestrator`, with a note clarifying that `orchestrator` is reserved for explicit-user-direction writes.
- Same file — "Writers (only two)" prose updated to "Writers (only three)" with a third bullet describing `orchestrator`'s role.
- `.ai-state/TECH_DEBT_LEDGER.md` — rows td-007 through td-010 updated from `source: sentinel` to `source: orchestrator`; notes-field disclosure of "convention violation" framing removed (no longer applicable post-widening).
- td-002 already uses `source: orchestrator` and is unchanged; its notes record the historical "stretch" framing as accurate state-at-time and become non-prescriptive post-widening.

## Considered Options

### Option 1 — Match td-002 precedent without widening

Change td-007–td-010 to `source: orchestrator`. Schema still violated (orchestrator is not in the enum) but consistently with td-002's existing precedent. Notes-field disclosure stays.

- **Pros**: Zero rule change; preserves existing pattern.
- **Cons**: Perpetuates the violation; multiple rows now carry an enum-violating value; future verifier/sentinel re-source workload accumulates; the "Writers (only two)" prose continues to lie about reality.

### Option 2 — Widen the enum (chosen)

Edit the rule to add `orchestrator` as a third recognized writer. Update both the schema row and the Writers prose. Migrate td-007–td-010 to the new value. td-002 (already orchestrator) becomes rule-compliant retroactively.

- **Pros**: Honest provenance; rule and schema agree with reality; existing td-002 row no longer violates; future user-directed writes have a clean home.
- **Cons**: One rule edit + one ADR (this one). Token impact on the always-loaded surface is negligible (~30–50 tokens added).

### Option 3 — Accept and defer (file a meta TECH_DEBT row)

Leave the rule and the rows unchanged. Add a new TECH_DEBT row capturing the enum-too-narrow finding for a future sprint.

- **Pros**: Zero edits today.
- **Cons**: Filing a meta-debt row using `source: orchestrator` (or `sentinel`) re-creates the violation. Recursion. The rule remains incoherent with practice.

Option 2 chosen because it resolves the violation properly with minimal cost and aligns rule prose with documented practice.

## Consequences

**Positive:**

- TECH_DEBT_LEDGER schema is internally consistent with documented writer practice.
- Future explicit-user-directed orchestrator writes carry honest provenance without verifier/sentinel re-source workload.
- Verifier's TD05 status-update-discipline check (which validates ledger schema) will not flag legitimate orchestrator-source rows.
- The implementation plan's Step 0.3 (adding `architect-validator` as a fourth writer) builds on a rule that already accommodates non-verifier/non-sentinel writers — the precedent reduces friction for the next addition.

**Negative:**

- Rule edit adds ~30–50 tokens to an always-loaded surface. Below the 25k budget headroom (P0a recon confirms 23,294 conservative tokens — adding ~50 leaves ~1,656 tokens of headroom).
- "Orchestrator may write" is a permission that future maintainers might over-use. The prose explicitly frames it as the exception, not the routine path. Verifier/sentinel re-source remains the preferred resolution when an orchestrator-filed row could have been filed by either of them.

**Neutral:**

- td-002's notes ("slight protocol stretch — canonical sources are verifier and sentinel") become historically accurate but no longer prescriptive. No edit needed; the row records its state-at-time.
- No retroactive effect on the verifier and sentinel agents. They remain the canonical writers; orchestrator is supplementary.
- Step 0.3 in the AaC+DaC v1 IMPLEMENTATION_PLAN.md is updated to reflect the new starting state ("Writers (only three)" → "Writers (four)") so the plan remains executable as the rule evolves.
