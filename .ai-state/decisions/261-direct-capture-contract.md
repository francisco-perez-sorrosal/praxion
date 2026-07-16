---
id: dec-261
title: Direct-tier capture contract — one row at commit as the universal durable write
status: accepted
category: architectural
date: 2026-07-01
summary: Close the Direct-tier durable-capture leaks with a deterministic commit-time nudge, a one-line calibration row whose Retrospective cell is the micro-capture slot, and a tier-blind coverage detector — enforcement moved up the reliability hierarchy, zero new artifacts.
tags: [calibration, direct-tier, capture, hooks, gate-liveness, feedback-loop, reliability-hierarchy, skill-genesis]
made_by: agent
agent_type: systems-architect
branch: worktree-direct-capture-contract
pipeline_tier: standard
affected_files:
  - hooks/remind_calibration.py
  - hooks/hooks.json
  - scripts/check_calibration_coverage.py
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/tech-debt-ledger.md
  - agents/skill-genesis.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-05, REQ-06, REQ-09]
re_affirms: dec-252
dissent: A one-line Retrospective cell is too coarse a grain for a real learning; if compliance stays near-zero even with the nudge, a dedicated per-session scratch sink was the right sink and this closes the leak on paper only.
re_affirmed_by:
  - dec-264
---

## Context

The Direct tier (`fix → verify → commit`, no agents/plans/specs) is well-designed on paper but non-functional as a capture surface. A three-lens internal audit (`DIRECT_TIER_REVIEW.md`, spot-verified) found: the calibration log has **zero Direct-tier rows in its entire history** (0/43 apparent Direct-tier commits in a 150-commit sample); Direct-tier learnings have **no artifact to live in** (`LEARNINGS.md` is pipeline-scoped and Direct scaffolds no `.ai-work/<slug>/`); and the only mechanical detector (CA03 / `check_calibration_coverage.py`, from `dec-252` R4) counts `feat:`/`fix:` only and is framed as a Standard/Full-pipeline check, so Direct-tier lapses are structurally invisible to it.

Root causes: (1) no moment-of-truth trigger — the one universal Direct ritual is `git commit`, and nothing in the commit path mentions calibration; (2) no sink for learnings; (3) the detector's intent is narrower than its mechanism; (4) a perceived-cost anchor — every existing row is a paragraph, so the one-line format is deterrent-by-obscurity; (5) an ambiguity tax across 12 restating surfaces. Prior audits (F-11, A4) flagged calibration under-production in general terms but none isolated the Direct-tier blind spot.

## Decision

Adopt the **Direct Capture Contract**, keeping the Direct tier's process shape untouched and collapsing all durable capture into **one moment (the commit) and one write (a one-line calibration row)**, with enforcement moved up the reliability hierarchy (deterministic nudge > periodic detection > prompt text):

- **D1 (keystone):** at Direct-tier completion the orchestrator appends one one-line calibration row (the sanctioned worked-example format, not a pipeline essay); the `Retrospective` cell doubles as the micro-capture slot for any learning / gotcha / debt / decision note — a sentence, promotable to an ADR (decision) or a `td-NNN` row (debt). The row is the floor, not the ceiling. Closes leak #2 with zero new artifacts and makes leak #1 cheap enough to honor.
- **D2:** a new `hooks/remind_calibration.py` advisory in the `commit_gate.sh` chain — on `git commit`, when `.ai-state/calibration_log.md` exists and lags ≥K=2 task-completing commits (reusing `check_calibration_coverage.py::compute_coverage` **in-process** — one source of truth, two consumers), emit a one-line fail-open stderr reminder. Suppressed inside linked worktrees and for `bump:`/`chore(finalize)` commits. Ships to every managed project via plugin hooks; existence-gating makes it a no-op in non-onboarded projects. CODE gate → canary.
- **D3:** widen `check_calibration_coverage.py`'s prefix set to task-completing commits of any tier (excluding `bump:`/`chore(finalize)`) and reframe its docstring/report from "Standard/Full pipeline merges" to "task-completing commits (any tier)". Turns the one mechanical detector tier-blind in the good sense; auto-serves D2 via the shared counting function.
- **D4:** add calibration-log `Retrospective` cells (newer than the last harvest) as skill-genesis's sixth source — the harvest path for Direct-tier learnings. PROMPT gate → golden bad-case.
- **D5:** a one-sentence Direct-tier mid-task escalation clause symmetric to Lightweight's, closing the mis-tiering leak at its root.
- **D7:** widen the tech-debt-ledger orchestrator exception to cover standalone Direct-tier sessions (record adjacent debt, don't expand into it — the Stay-Surgical redirect).
- **D8 (consolidation):** a single canonical Direct-tier wording; derivative surfaces point rather than restate; the change mirrored into the canonical block + both install commands. **D8's optional mechanical threshold-drift check is deferred** (see Consequences).

This re-affirms `dec-252` (which added the CA03 *detector*) and completes it with the missing *producer-side* trigger (D2) and *tier-blind* scope (D3). (D6 — orchestrator as Direct/Lightweight ADR author — and the tier-vs-execution-mode taxonomy are split into the sibling ADR `dec-262`.)

## Considered Options

### Option 1 — One-line calibration row, `Retrospective` cell as micro-journal (chosen)
- **Pros:** zero new artifact; single moment + single write; leverages existing CA03 (D3) and skill-genesis (D4) plumbing; the row was already formally owed by every tier; the micro-journal is promotable so nothing substantial is trapped in a cell.
- **Cons:** a sentence is a coarse grain for a rich learning; relies on discipline to promote substantial items; the nudge is advisory (compliance is not guaranteed).

### Option 2 — Dedicated per-session Direct-tier scratch file
- **Pros:** a real, structured learnings sink for Direct tier; richer than a cell; harvestable directly.
- **Cons:** a NEW artifact and lifecycle (creation, cleanup, gitignore, sentinel coverage) for the tier whose whole identity is "no planning documents"; contradicts F-11's detection-first disposition and the health guard "no new `.ai-state/` artifact"; adds ceremony to the one tier that must not gain any.

### Option 3 — Enrich `observations.jsonl` with rationale + a tier-inference consumer
- **Pros:** reuses the largest free channel (17k+ events, fires unconditionally at every tier); no new write obligation.
- **Cons:** the WAL carries structured metadata, not rationale; would need a richer capture at write time AND a downstream consumer that reconstructs task boundaries and infers a tier from raw tool-call sequences — heavier than the row it replaces; conflicts with the bounded-WAL truncation-recovery role (`dec-248`/`dec-250`).

## Consequences

**Positive:**
- Leak #1 (calibration) gains a deterministic trigger at its natural moment; leak #2 (learnings) gains a sink with zero new artifacts; the only leak with zero prior coverage (Direct-tier learning) is closed via D4.
- One counting source (`compute_coverage`) feeds both the nudge and the periodic detector — D3's widening cannot drift between the two.
- Ships everywhere via plugin hooks; existence-gating guarantees a safe no-op for non-onboarded projects.
- The reliability hierarchy is honored: prompt-text is demoted to the floor, the nudge and the detector carry the weight.

**Negative / accepted:**
- D3's widening makes the detector count docs:/refactor:/test: commits, raising flag frequency; damped by K=2 + `bump:`/`chore(finalize)` exclusion + worktree suppression, and advisory-only.
- D2 couples the hook to `check_calibration_coverage.py`'s module surface via an in-process import; mitigated by the fail-open wrapper and a frozen `compute_coverage` signature.
- **D8's optional threshold-drift check is deferred** to a tech-debt observation (recorded in `SYSTEMS_PLAN.md § Codebase Readiness`, not written to the ledger — the architect is a consumer). Rationale: a substantive cross-surface threshold-agreement check over heterogeneous prose risks the gate-liveness anti-patterns (brittle grep, existence-not-substance); D8's consolidation is itself the structural drift-reduction; the new machinery would enlarge the blast radius the Uncertainty Flag names.
- A latent gate-liveness hole (the canary-coverage meta-test glob does not cover the `remind_*.py` family) is documented for a follow-up pass; `remind_calibration.py` still ships its canary.

## Disconfirmation

- **Falsifier:** After the nudge ships, Direct-tier calibration rows stay near-zero (compliance does not improve), OR the rows that appear carry empty/placeholder `Retrospective` cells (the micro-journal is written but says nothing). Either would show that the grain (a cell) — not the trigger — was the binding constraint, and that Option 2's dedicated sink was the correct sink.
- **Steelmanned runner-up (Option 2 — dedicated scratch sink):** The honest case for a per-session file is that a *sink shaped like a learning* invites a learning, whereas a *cell in a tier-selection table* invites a tier verdict and nothing more — the schema signals the expected content. A single narrow-column cell in a row whose other six columns are all tier-calibration metadata will predictably be filled with "correct" and left there; the rich "this was hacky but out of scope" note has no room to breathe and will still be lost. A dedicated `.ai-work/<slug>/`-style scratch file (created only when the Direct session actually has something to say, cleaned up like any ephemeral) would cost one gitignored file and give skill-genesis a real artifact to harvest — the same shape it already harvests everywhere else, removing the special-case sixth source (D4) entirely. The runner-up loses today only because it adds an artifact to the one tier defined by having none, and because the nudge+cell is testable *now* with zero new lifecycle; it wins the moment the falsifier fires.
- **Reversal trigger:** Two consecutive `/skill-genesis` runs (or a sentinel CA-family pass) show Direct-tier `Retrospective` cells present but content-empty at a rate that makes the micro-journal a checkbox rather than a capture. That is the signal to reopen Option 2 (or Option 3's WAL-consumer path) and give Direct tier a learning-shaped sink.

## Prior Decision

Re-affirms `dec-252` (production-gate cohort — R4 calibration coverage added the CA03 *detector* with a gate-liveness proof). `dec-252` deliberately shipped detection only ("Detection — not a new command surface — is the right enforcement," per F-11); this ADR does not overturn that — it keeps the no-new-command-surface disposition (D2 is a nudge, not a `/record-calibration` command) and adds the producer-side *trigger* and the *tier-blind* scope that `dec-252`'s detector lacked. No supersession: `dec-252`'s gate stands and is extended.
