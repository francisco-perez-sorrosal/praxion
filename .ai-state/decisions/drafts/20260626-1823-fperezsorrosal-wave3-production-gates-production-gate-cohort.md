---
id: dec-draft-b8b54821
title: Production-gate cohort — turn four prose obligations into mechanical gates
status: proposed
category: behavioral
date: 2026-06-26
summary: R3 spec-archival gap, R4 calibration coverage, R5 LEARNINGS→td promotion, R9 stale-slug advisory, R13 challenge disposition — each gets a gate with a gate-liveness proof; R5 ownership stays with the verifier to preserve the four-writer ledger contract.
tags: [production-gates, sentinel, calibration, spec-archival, tech-debt-ledger, gate-liveness, learnings-promotion]
made_by: agent
agent_type: systems-architect
branch: wave3-production-gates
pipeline_tier: full
affected_files:
  - agents/sentinel.md
  - agents/verifier.md
  - scripts/check_spec_archival_gap.py
  - scripts/check_calibration_coverage.py
  - rules/swe/agent-intermediate-documents.md
  - skills/software-planning/references/architecture-documentation.md
dissent: R4's detector closes the *detection* half, not the *production* half — without a task-complete hook event the calibration row still depends on a voluntary orchestrator nudge, so the producer gap is mitigated, not closed.
---

## Context

This is the cohort sibling of `dec-draft-41f7a888` (the declarative spine). Where the
spine decides *how to make gates visible*, this ADR decides *which gates to build and how
each proves it bites*. Five §6 rows (R3, R4, R5, R9, R13) plus the A6 producer tail share
one constraint set — each is a prose obligation the analysis verified under-firing on
disk — so they are decided as one behavioral cohort rather than five fragments.

Two existing contracts constrain the design and must not break: the **four-writer
tech-debt ledger contract** (only verifier, sentinel, orchestrator, architect-validator
add rows; all other agents update status in place) and **gate-liveness** (every gate
ships proof it fails on a known-bad input — a canary for CODE, a golden bad-case for
PROMPT/sentinel).

## Decision

**R3 — spec-archival gap (sentinel SH08 + script).** A committed deterministic detector
`scripts/check_spec_archival_gap.py` flags WARN when the newest `.ai-state/specs/SPEC_*`
is more than N days older than a cluster of ≥K finalized ADRs sharing a tag. Sentinel
SH08 (Spec Health dimension, already gated on specs-present) calls it. Zero-spec projects
SH-skip — no false WARN. Proof: pytest canary (golden-input → flag) + a healthy negative
control + a sentinel golden bad-case fixture.

**R4 — calibration coverage (sentinel CA03 wired to a script).** A committed detector
`scripts/check_calibration_coverage.py` compares the calibration log's newest `Timestamp`
against recent Standard/Full pipeline merges and exits non-zero (or emits JSON) when work
has landed without a row — **mechanical detection that runs without a full `/sentinel`
run** (the Key Signal). CA03's auto-half is rewired to invoke it. The *producer* nudge is
a one-line orchestrator cleanup-checklist reminder, not a new `/record-calibration`
command (Simplicity First — the row is one markdown line the orchestrator already knows
how to append; a command artifact over-builds). There is no task-complete hook event to
gate on, so full auto-production is impossible; detector + nudge is the honest closure.
Proof: pytest canary + healthy control.

**R5 — LEARNINGS → td promotion (verifier-owned; four-writer-preserving).** The verifier
already writes ledger rows and already reads `LEARNINGS.md`; it is the **only**
pipeline-end agent that reads LEARNINGS *and* is a ledger writer. So it — not the planner
or implementer — harvests `### Technical Debt` entries into `td-NNN` rows at pipeline end,
extending its existing per-change-debt behavior. Planner/implementer remain *consumers*:
they write observations into `### Technical Debt` but never file rows (the four-writer
contract decides the ownership for us). Double-filing is prevented by the ledger's
structural `dedup_key` and the `finalize_tech_debt_ledger.py` collapse at merge. The
prose sections (`### Gotchas`, `### Patterns`, `### Edge Cases`) are documented honestly
in `agent-intermediate-documents.md` as `/skill-genesis`-harvested-or-lost — the rule
stops describing an automatic merge that does not occur. Proof: a verifier golden bad-case
(a LEARNINGS `### Technical Debt` entry the verifier must promote).

**R9 — stale-slug advisory (sentinel P08, reusing clean_work_safety).** Sentinel P08
calls `clean_work_safety.py --json` and emits an advisory when `summary.stale_safe ≥ N`.
No new script — the staleness counting is already canaried in `test_clean_work_safety.py`.
The dashboard completion-state separation is **deferred to Wave 4** (see Register
Objection in `SYSTEMS_PLAN.md` — it is TypeScript UX hygiene, not a production gate, and
crossing into the dashboard would break Wave 3's single-language focus). Proof: a
documented golden bad-case (`stale_safe ≥ 3` → WARN).

**R13 — challenge-loop disposition (sentinel P07, no script).** Sentinel P07 flags a
non-empty `## Architecture Challenges` section in `INTERFACE_DESIGN.md` /
`TRANSACTIONS_DESIGN.md` with no recorded disposition. The analysis explicitly calls for
the lighter fix first (sentinel check, not a YAML-parser script) because the path fires
only when a specialist sub-architect raises a challenge — rare/never on Praxion. Proof: a
sentinel golden bad-case fixture.

**A6 tail — `DESIGN_CHANGELOG` producer.** A one-line standing producer instruction in
`architecture-documentation.md` assigns the changelog a writer so the Wave-1 hand-restored
split cannot re-drift. Closes a gate-liveness GL01 orphan (a consumed-but-unproduced
artifact). Proof: `grep -rl DESIGN_CHANGELOG skills/` now returns ≥1.

## Considered Options

### R4 mechanism: detector script vs `/record-calibration` command vs orchestrator checklist

Chosen: **detector script + checklist nudge**. The detector is the load-bearing missing
half (mechanical, runs without `/sentinel`, CI-wireable). A `/record-calibration` command
was rejected — it lowers producer friction marginally but adds a command artifact for a
single-row append; the checklist line reinforces the already-mandated append at near-zero
cost.

### R5 ownership: extend verifier vs add planner/implementer as filers

Chosen: **verifier only**. Adding planner/implementer as filers would violate the
four-writer ledger contract. The contract is not an obstacle to route around — it makes
the decision: route all `### Technical Debt` promotion through the one writer that already
reads LEARNINGS.

### R3/R9/R13 form: standalone script vs inline-bash sentinel check

Chosen per-item by complexity: **R3 = script** (date-math + tag-grouping is beyond grep
and benefits from a tested, reusable, CI-wireable detector — matching the GL02/EC07/AC10
"sentinel calls a committed detector" precedent); **R9 = reuse existing script**;
**R13 = inline sentinel grep** (genuinely grep-amenable; "script only if frequent").

## Consequences

**Positive:** four obligations that under-fire on disk become mechanical or visible; the
spec-archival gate restarts a starved SDD surface (Wave 3 dogfoods it by archiving its own
spec — the first since 2026-05-11); the four-writer ledger contract is preserved intact;
every new gate carries a liveness proof, so none can pass on bad input unseen.

**Negative / accepted:** R4 closes detection but not production (no hook event exists);
R9's dashboard half and the broader Theme-C lifecycle work are deferred; the cohort adds
~4 sentinel checks to an already-large agent (within its T03 700-line exception) and two
new detector scripts to maintain.

## Disconfirmation

**Falsifier.** If the new sentinel checks false-positive on healthy or
optional-absent state (R3 on a legitimately spec-less project, R13 on an absent
`INTERFACE_DESIGN.md`, R9 on an empty `.ai-work/`), the cohort has added noise, not
signal — each check must skip-with-INFO on absent substrate (the TT/PR conditional-
activation idiom) and ship a no-false-positive control alongside its golden bad-case.

**Reversal trigger.** If R4's detector + checklist nudge still yields chronic uncalibrated
pipelines after one wave, escalate to a real producer mechanism (a `/clean-work`-time
auto-append or a commit-msg-trailer harvest) rather than leaving the producer gap open.
