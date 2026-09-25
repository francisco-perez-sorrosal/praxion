---
id: dec-draft-e3f0938b
title: Encode the per-tier pipeline envelope mechanically — registry-owned artifact floor, agent_start spawn count with a per-tier budget, model-visible calibration reminder
status: proposed
category: architectural
date: 2026-09-25
summary: The Standard/Full artifact floor becomes a monotone `floor` field on each artifact-registry row that the eval manifest derives from; a new stdlib `scripts/spawn_count.py` counts spawns and light/heavy resumes per slug from agent_start rows so the coordination rule can budget Standard ≤ 8 / Full ≤ 16; the calibration reminder moves to a once-per-session Stop-time additionalContext.
tags: [process-economy, pipeline, spawn-budget, artifact-floor, artifact-registry, calibration, wal, hooks, coordination-protocol]
made_by: agent
agent_type: systems-architect
branch: worktree-process-economy-d
pipeline_tier: standard
affected_files:
  - scripts/artifact_registry.py
  - scripts/test_artifact_registry.py
  - eval/src/praxion_evals/harness/task_manifest.py
  - scripts/spawn_count.py
  - scripts/test_spawn_count.py
  - hooks/remind_calibration.py
  - hooks/hooks.json
  - eval/src/praxion_evals/live/scenarios.py
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/references/artifact-inventory.md
  - agents/implementation-planner.md
affected_reqs: []
supersedes_in_part: dec-261
dissent: "Resume sizing couples spawn_count.py to the harness transcript layout; the 250k heavy threshold is a memory-derived heuristic, not a measured cliff."
---

## Context

The calibration log keeps reporting one pipeline shape and nothing mechanical reads it. `process-economy-c5` ran 16 files / 16 behaviours at Standard with 8 spawns plus 11 resumes carrying 600k+-token contexts; `process-economy-p0-7-live` held 8 spawns by dropping a test-engineer pairing and the verifier's FAILs sat on exactly that unpaired paid path; `CI to green` ran 36 files at 0 spawns. The roadmap's P2.3 (spawn budget, action-parallelism off by default) and P2.4 (artifact floor) have no implementation: the eval task manifest hard-codes five Standard artifacts, Full has no floor at all, the coordination rule has no budget, and `hooks/remind_calibration.py` — the calibration-row nudge `dec-261` D2 introduced — has never reached the model (it prints to stderr at exit 0, which the harness shows only in verbose mode) and cannot fire for a single session anyway (commit-only trigger, K=2 landed-commit threshold evaluated before the pending commit lands, scope-blind prefix matcher, absent-substrate skip).

Probes settled the telemetry grain: `agent_stop` rows are dominated by unannounced harness helpers (4,029 stops vs 332 starts in the main WAL), while `agent_start` rows keyed by the row's `project` (the checkout basename, which is the slug for a worktree pipeline) are one per spawn — and a `SendMessage` resume emits a second `agent_start` with the same `agent_id` (43 ids with >1 start).

## Decision

1. **Floor as registry data.** Replace the correlated `eval_tier`/`eval_required`/`eval_conditional` flags on `Artifact` with one `floor: Floor | None`, where `Floor(standard, full)` takes `"always"` or a signal (`tests-ran`, `sdd-active`, `produced`) and its constructor rejects a Full requirement weaker than Standard. Standard always: TASK_BRIEF, SYSTEMS_PLAN, IMPLEMENTATION_PLAN, WIP, LEARNINGS, TEST_BASELINE, VERIFICATION_REPORT; conditional: TEST_RESULTS (tests-ran), traceability.yml (sdd-active); declarative: RESEARCH_FINDINGS, SPEC_DELTA, CONTEXT_REVIEW, INTERFACE_DESIGN, TRANSACTIONS_DESIGN (produced). Full = Standard with traceability.yml always; spec archival stays enforced at closure by the existing consume-marker policy. The file-decidable predicates move from the eval manifest into the registry; the eval manifest derives its Standard/Full expectations from the registry; sentinel P06 keeps its intake-order logic, bound to the floor by a registry test.
2. **Spawn count as a new component.** `scripts/spawn_count.py` (stdlib, on PATH) tallies `agent_start` rows for a slug: first start per `agent_id` = spawn, each later start = resume; a resume is *heavy* when the agent's own transcript shows ≥ 250k context tokens at its last turn before the resume, and a heavy resume is charged as a spawn. It withholds (exit 2) on an unseen slug rather than reporting zero.
3. **Budget rule.** `§ Process Calibration` gains one envelope bullet: floor pointer; Standard ≤ 8 / Full ≤ 16 charged spawns; read the count before each spawn and log it in the calibration row; never meet the budget by unpairing a step that owns an external side effect or by skipping the verifier — stop, re-tier or split; writers in sequence unless file sets are disjoint with pathspec commits. The planner states a spawn estimate checked at the pre-mortem gate. Net always-loaded cost ≤ 0 tokens and ≤ 0 bytes.
4. **Reminder repair (narrows `dec-261` D2).** `remind_calibration.py` gains a Stop handler that, once per session in a managed project outside a worktree, emits an `additionalContext` reminder when the session authored edits and left `calibration_log.md` untouched; the commit-time lag warning switches from stderr to `additionalContext`.

## Considered Options

### Option A — Mechanical envelope at existing seams (chosen)

- **Pros:** one data source per concern; the count survives compaction and resumes; heavy-resume charging makes the quality-correct choice budget-neutral; no new dependency.
- **Cons:** eval imports `scripts/`; resume sizing reads harness transcripts; one more Stop hook.

### Option B — Prose-only budget and floor

- **Pros:** zero code; zero coupling.
- **Cons:** the orchestrator's count is lost at compaction; c5 and p0-7 show the prose cap was met by degrading quality, invisibly. Rejected.

### Option C — Extend existing telemetry (cost collector or the committed per-session summary)

- **Pros:** reuses WAL discovery; the summary is durable.
- **Cons:** the collector is periodic and token-grained (`attributed_rows`); the summary updates only at Stop and its `spawns_by_agent_type` already conflates spawns with resumes. Neither answers mid-run. Rejected for the reader; the summary's resume split is a named follow-up.

### Option D — Generalise P06 into a stage-ordered floor check

- **Pros:** a shipped floor check for managed projects.
- **Cons:** needs a new stage dimension; mid-pipeline it false-positives on not-yet-produced artifacts; completed slugs are usually cleaned before a sentinel sees them. Rejected for now.

## Consequences

**Positive:**
- Adding an artifact to the floor is one registry edit; eval and the inventory table follow or a test fails.
- Spawn and resume counts become a per-run fact quoted in the calibration row — the evidence base the budget is recalibrated from.
- The calibration reminder reaches the model for the first time since it shipped.

**Negative:**
- Standard runs that skipped TASK_BRIEF or TEST_BASELINE now FAIL the eval manifest (both were already mandated in prose).
- Managed projects still get no mechanical per-run floor completeness check (the eval package is Praxion-side).
- A reminded session pays one extra continuation turn; an interactive session may be reminded before it is done (bounded to once).

**Open question for the D2 Spike (out of scope here):** the floor keeps `WIP.md` as its own required artifact. Should `WIP.md`'s checkboxes merge into `IMPLEMENTATION_PLAN.md` (roadmap P2.4)? The Spike must establish that a merged plan lowers per-run artifact cost without degrading its ~50 load-bearing readers (the dec-393 reconciler, handoff composition, dashboard view-models, compaction hooks, eval manifest, planner/implementer/test-engineer agents, shipped onboarding content) before any design work.

## Disconfirmation

- **Honest-denominator caveat:** the budget numbers rest on the calibration log, not telemetry. Only two rows report spawn and resume counts (c5, p0-7), both from the programme that proposed the cap, so selection bias is built in. Past per-slug spawn counts are not recoverable from worktree WALs; the committed per-session summary carries slugs only since 2026-09-24 and conflates spawns with resumes. The ~2026-10-08 telemetry window does not gate this decision (user ruling); 8 and 16 are priors, not measurements.
- **Falsifier:** within the next ten Standard runs, a run that stays within 8 charged spawns shows a higher verifier-FAIL or rework rate than runs of the same plan shape that overran — i.e. the budget itself is causing the degradation it was meant to prevent.
- **Steelmanned runner-up (Option B):** a budget is a planning prior, not a runtime invariant; a competent orchestrator counts its own Agent calls, and a count instrument plus hook plus registry field adds three maintenance surfaces for a number the calibration row could record by hand. If orchestrators log accurate hand counts and never degrade quality to meet the cap, the mechanism is overhead.
- **Reversal trigger (per plan, not a corpus mean):** at the pre-mortem gate of any single Standard plan with ≤ 4 behaviours, compute the plan's minimum spawn need (architect + planner + one agent per solo step + two per paired side-effect step + verifier). If that minimum exceeds 8 — so the plan cannot fit without unpairing a side-effect step or charging a heavy resume — revisit the Standard budget for that plan shape; and if the tally shows a plan finishing with a heavy resume the budget did not charge (unsized), revisit the resume rule. A trigger on the corpus mean spawn count would stay green while plan shapes that cannot fit keep degrading.

## Prior Decision

`dec-261` D2 added `hooks/remind_calibration.py` as a commit-time stderr reminder gated on K=2 uncalibrated commits. This decision narrows that clause only: the reminder's channel becomes `additionalContext` (stderr at exit 0 is shown in verbose mode only and never reached the model), and a Stop-time session reminder takes over the per-session obligation the commit path cannot see. D1, D3–D8 of `dec-261` stand unchanged.
