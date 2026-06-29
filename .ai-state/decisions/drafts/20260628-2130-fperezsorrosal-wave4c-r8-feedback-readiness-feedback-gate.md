---
id: dec-draft-89c07cfc
title: Close the readiness write-only loop via a sentinel RD check; document eval human-gating as deliberate
status: proposed
category: architectural
date: 2026-06-28
summary: Readiness gains its "apply" phase as a new mechanical sentinel check (RD01) reading readiness.data.adjusted_level and flagging Important when < 3, riding the existing sentinel → promethean edge; the eval-results loop is consciously left human-gated and documented as such because "recurring FAIL" is unmeasurable on a 1-run history.
tags: [feedback-loops, sentinel, promethean, agent-readiness, eval-praxion, gate-liveness, write-only, four-writer-ledger]
made_by: agent
agent_type: systems-architect
branch: wave4c-r8-feedback
pipeline_tier: standard
affected_files:
  - scripts/check_readiness_feedback.py
  - scripts/test_check_readiness_feedback.py
  - agents/sentinel.md
  - skills/agent-readiness/SKILL.md
  - commands/eval-praxion.md
  - tests/fixtures/sentinel/readiness_below_threshold/
  - .ai-state/DESIGN.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07]
dissent: Firing RD01 on Praxion's own mechanical-only level-2 may surface a verdict that a full LLM run would lift to level-3 — the gate could read as noise on a project that is actually fine, and the "annotate, don't suppress" choice bets that an honest-but-conservative finding beats silence.
---

## Context

Finding D1 / backlog R8 of the Wave-4c artifact-process-flow analysis verified the clearest
write-only pattern in the system: the agent-readiness level (computed by `/project-metrics`,
embedded in `METRICS_REPORT_*.json`, dashboarded, interpreted by a human-consultation skill) and
the `/eval-praxion` results (one recorded run: 402 PASS / 150 WARN / 219 FAIL) are **computed and
displayed but never gate or modify any pipeline behavior**. The "apply" phase of the Learning Loop
is absent for both — a Level-1 and a Level-5 project run identical pipelines.

Praxion already owns the closed-loop template the analysis says to copy: `sentinel → promethean`
(promethean halts if the latest sentinel report is missing or > 7 days old; ideation accounts for the
health grade). The task is to apply that template, or to consciously document the human-gating so it
reads as intentional rather than as a gap.

Two existing contracts constrain the design and must not break: the **four-writer tech-debt ledger
contract** (only verifier, sentinel, orchestrator, architect-validator add rows) and **gate-liveness**
(every gate ships proof it fails on a known-bad input). This decision is a direct sibling of `dec-252`
(the production-gate cohort that turned five prose obligations into mechanical gates under the same two
constraints) and is grounded by `dec-213` (readiness embeds as a `readiness` block at the **metrics JSON
root**, not under `collectors`) and `dec-204` (eval runs LLM-as-judge **out-of-band** via `/eval-praxion`).

## Decision

**A — Readiness: feed back (A1).** A committed stdlib detector `scripts/check_readiness_feedback.py`
(structural clone of `scripts/check_calibration_coverage.py`) reads the latest `METRICS_REPORT_*.json`,
parses `readiness.data.adjusted_level` (fallback `readiness.data.level`), and reports
`below_threshold: true` when the level is `< 3`. A new sentinel dimension `RD` / check `RD01`
(Pass-1 auto) invokes it and flags **Important** when below threshold. The finding flows through the
**existing** `sentinel → promethean` edge — promethean reads the latest `SENTINEL_LOG` row plus
Important findings, so a below-floor readiness level now informs ideation. The loop closes
**transitively**; no `promethean → readiness` direct wire is created.

Three sub-questions resolved:
- **JSON path** → `readiness.data.adjusted_level` (disk truth; `dec-213`). The contradicting doc line
  `skills/agent-readiness/SKILL.md:38` (`collectors.readiness.data`) is corrected in lockstep — the gate
  cannot read a path the doc misdescribes.
- **`mechanical-only`** → **fire-but-annotate**. The mechanical level is the best available signal and
  surfaces a true finding; requiring the LLM tier would make the gate inert in exactly the auth-less / CI
  environments most in need of it. The finding annotates that the verdict is a mechanical-only floor that
  a full `/project-metrics` run may raise.
- **Threshold** → `< 3` on `adjusted_level`. "Adjusted" already folds Praxion's tuned `pillar_weights`,
  so the gate reads the weight-tuned number directly. Level 3 ("Practiced") is the production-discipline
  floor below which an agent pipeline is unsafe.

**RD01 emits an Important finding only — it writes no `td-NNN` row** (identical to CA03/SH08). The
four-writer ledger contract is preserved unchanged in membership; sentinel exercises only its
finding-emission role.

**B — Eval: document human-gating as deliberate (B2).** No feedback machinery is built. `commands/eval-praxion.md`
gains a section recording that eval is an out-of-band quality instrument whose results are human-gated by
design, naming the reversal trigger (a multi-run history that makes "recurring FAIL" measurable). The
rationale: "recurring" is unmeasurable on a 1-run history; sentinel does not read eval reports today
(genuinely new surface); eval FAILs are frequently expected (corpus / calibration limits at
`eval-praxion.md:122`).

**Gate-liveness (CODE gate per `dec-252`).** A pytest canary drives `adjusted_level: 2` and asserts the
gate flags it; a no-false-positive control drives `adjusted_level: 3`; a substrate-absent case asserts
skip-with-INFO; a sentinel golden bad-case fixture (`tests/fixtures/sentinel/readiness_below_threshold/`)
ships with a control.

**Activation:** yes — genuine architect-owned fork, `category: architectural`. The Phase-9 lens sweep
(developer / test / operations / simplicity / security) ran; the Dialectical-Inquiry sub-step is
discharged in the Disconfirmation block below (the runner-up A2 + B1 argued in earnest, not as assigned
opposition). Tier-B cross-model challenge: **not fired** — stakes are an internal advisory sentinel
check, fully reversible (delete two files, revert four Markdown edits); below the security / one-way-door /
user-visible-breaking bar.

## Considered Options

### A — Readiness: A1 (feed back) vs A2 (document as intentional)

Chosen **A1**. Readiness differs from eval in the only dimension that sets cost: sentinel **already reads**
`metrics_reports/` and the `sentinel → promethean` edge **already exists**, so A1 is a near-zero-surface
clone of `dec-252`'s CA03/SH08, not new machinery. The readiness signal is also actionable for ideation —
a low level names concrete missing production-discipline criteria a promethean idea can close. A2 would be
the right call only if readiness were as calibration-limited and as un-read as eval; it is neither.

### B — Eval: B2 (document) vs B1 (feed back)

Chosen **B2**. B1 requires teaching sentinel a brand-new input (it reads no eval reports today), a new
dimension, and a new detector — all to act on a signal ("recurring FAIL") that is **undefinable with N=1**.
The Health Guard forbids building feedback machinery on a 1-run history. B2 records the deliberate
human-gating and a measurable revisit condition, converting the apparent gap into a decision.

### Form: standalone bundled ADR vs formal re-affirmation of dec-204

Chosen **standalone, citing inline**. A formal `re_affirms: dec-204` was considered (the D1 finding does
challenge eval's out-of-band model and B2 finds it still correct) and declined for Simplicity First: it
would churn `dec-204`'s `re_affirmed_by` frontmatter for marginal traceability benefit, and B2 is a fresh
*policy* decision (the deliberate-human-gating-as-feedback-model choice), not merely a restatement of
`dec-204`'s harness decision. The citation is inline.

## Consequences

**Positive:** the clearest write-only pattern in the system gains its "apply" phase at the cost of one
detector + one sentinel row; the gate is armed-and-honest on Praxion's own disk (level-2 → Important,
satisfying the dogfood Key Signal); the four-writer ledger contract is preserved intact; every new gate
carries a liveness proof; the eval half is recorded as a decision with a measurable reversal trigger
rather than left as an unexplained gap; a doc/disk contract bug (`collectors.readiness.data`) is fixed in
passing.

**Negative / accepted:** RD01 fires red on Praxion until it reaches level 3 (intended, not a defect); the
mechanical-only level may be conservative (mitigated by annotation + reversal trigger); the eval "apply"
phase stays human-mediated until a multi-run history exists; `agents/sentinel.md` grows ~6 lines (within
its accepted T03 exception).

## Disconfirmation

**Falsifier.** RD01 false-firing on healthy or optional-absent state would mean the gate added noise, not
signal: specifically, if mechanical-only understatement is *systematic* (healthy projects routinely score
a mechanical level-2 that a full LLM run lifts to 3+), then the finding fires on projects that are
actually fine — disconfirming the "surfaces a true finding" premise. It must skip-with-INFO on absent
`metrics_reports/` and ship a no-false-positive control. For B2, the falsifier is the arrival of a stable
multi-run eval history in which a specific check FAILs *recurrently* and *unexpectedly* — at which point
"unmeasurable, so don't gate" no longer holds.

**Steelmanned runner-up (DI sub-step — A2 + B1, argued in earnest).** The symmetric position is that
readiness and eval are *the same kind of artifact* — out-of-band quality instruments — and should be
treated identically. The honest case for **A2**: pipeline safety does not demonstrably depend on the
readiness *level* today; no pipeline agent's correctness changes between a level-2 and a level-4 project,
so gating ideation on it imports a number whose causal link to outcomes is unproven — documenting both as
deliberately human-gated is the more intellectually consistent answer and avoids a gate that fires on the
authoring repo itself. The honest case for **B1**: D1's core complaint is the *absence of an apply phase*,
and the cleanest cure is to actually build one — routing eval FAILs into the ledger via the same
`sentinel → promethean` machinery would be the literal closure the analysis asks for, and "we can't
measure recurrence yet" is a reason to start accumulating runs, not a reason to decline. This runner-up is
coherent; it is rejected because the **cost asymmetry is real** (readiness rides an edge + reader that
already exist; eval needs both built from zero) and because acting on an *undefinable* signal (N=1
recurrence) would violate the Health Guard and flood the ledger — but if the cost asymmetry closed (eval
gains a multi-run history; readiness proves causally inert), the runner-up becomes the better design.

**Reversal trigger.** *Readiness:* if RD01 fires chronically on demonstrably healthy projects (systematic
mechanical-only understatement), raise the threshold or require the LLM tier before verdicting. *Eval:*
once `/eval-praxion` has accumulated ≥ K runs (≈5) and a stable FAIL-recurrence metric exists, revisit B1
— route recurring FAILs into the ledger via the same `sentinel → promethean` edge this ADR builds for
readiness.

## Prior Decision

Not a supersession. This ADR applies the `dec-252` production-gate cohort pattern to a new surface
(readiness) and cites `dec-213` (readiness JSON-root embed — the authority for the corrected path) and
`dec-204` (eval out-of-band — the basis for B2's deliberate human-gating). All three remain `accepted`.
