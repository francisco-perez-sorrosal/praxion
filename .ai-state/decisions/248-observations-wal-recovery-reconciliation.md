---
id: dec-248
title: observations.jsonl as recovery WAL + deterministic reconciliation + auto-resume-with-audit; WIP.md demoted to a verified cache
status: accepted
category: architectural
date: 2026-06-22
summary: Make pipeline step-completion a verified fact derived from ground truth — reconcile WIP claims against git/tests (Tier 1) localized by the existing observations.jsonl WAL (Tier 2); auto-resume partials with a mandatory five-surface audit trail.
tags: [pipeline, recovery, truncation, reliability, observability, reconciliation, wal]
made_by: agent
agent_type: systems-architect
branch: feat-truncation-recovery
pipeline_tier: standard
affected_files:
  - scripts/reconcile_pipeline_state.py
  - scripts/test_reconcile_pipeline_state.py
  - commands/resume-pipeline.md
  - skills/software-planning/references/agent-pipeline-details.md
  - rules/swe/swe-agent-coordination-protocol.md
  - agents/implementer.md
  - .ai-state/observations.jsonl
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
re_affirmed_by: [dec-draft-30aea871]
dissent: A pure-prevention design (restructure the implementer loop so the durable WIP write is atomic and early) would eliminate the truncation gap at its source and need no reconciliation reader at all — it loses here only because no agent-authored write is trustworthy under a hard mid-turn token cut, so prevention shrinks the gap but cannot close it.
---

## Context

A pipeline subagent — most often `implementer` — can be hard-truncated at its ~200k-token context ceiling **mid-work**: code written and tests green, but the agent dies before recording that fact. The coordinator then either stalls on a `WIP.md` that still claims the step is incomplete, or silently advances on an unverified `[COMPLETE]` claim. The root cause is structural: `WIP.md` is treated as the source of truth for "did this step complete," but it is an **agent-authored claim, written last** (implementer phase 8/10) and **never verified**. Agent-authored signals fail exactly when needed — "agent died" and "status not written" are perfectly correlated. A live `PROGRESS.md` was observed this session with malformed/placeholder timestamps, confirming Tier-3 signals are unreliable in the wild.

Two empirical findings from this session reframe the problem:
1. **`SubagentStop` fires reliably** — Phoenix showed 8,339/8,339 AGENT spans closed, 0 dangling, across 12 agent types. So "did the subagent stop" is an agent-independent signal.
2. **The durable write-ahead log already exists.** `hooks/capture_session.py` (`agent_start`/`agent_stop`) + `hooks/capture_memory.py` (PostToolUse → `tool_use`) durably append to `.ai-state/observations.jsonl` with `agent_id`, `agent_type`, `file_paths`, `outcome`, `classification`, `event_type`, `timestamp` — fcntl-locked, toggle-gated, git-tracked with a merge driver. **Nothing has ever read it back for recovery.** Verified against the live WAL: subagent `tool_use` rows ARE `agent_id`-attributed (7,510/12,875 carry `agent_id != session_id`), so the WAL already records *which agent wrote which file when* — exactly what recovery localization needs.

The orchestrator-side detection contract (the Completion Handshake) already shipped this session in `swe-agent-coordination-protocol.md` + `agent-pipeline-details.md`. What is missing is the **mechanism** that operationalizes it.

## Decision

Adopt a **reliability hierarchy** and demote `WIP.md` from source-of-truth to a *cache of a verifiable fact*:
- **Tier 1 — ground truth (arbiter):** codebase + `git diff` over the step's `Files:` + `TEST_RESULTS.md`. The final word on completion.
- **Tier 2 — harness journal (localization hint only):** the existing `observations.jsonl` WAL. Tells the reconciler which agent stopped and where it last wrote. **Never decides alone** — a dropped async-hook line costs a hint, not a verdict.
- **Tier 3 — agent self-report (never load-bearing):** the `WIP.md` checkbox and `PROGRESS.md`, validated and (on recovery) corrected by the reconciler.

Build the missing consumer and recovery path — **no new journal infrastructure**:
1. `scripts/reconcile_pipeline_state.py` — a deterministic, side-effect-free reader emitting per-step JSON verdicts (`verified-complete` / `mismatch` / `partial@<pt>` / `in-flight` / `unknown`), with Tier-1 as arbiter and the WAL correlated by a **file+time backward** contract (the WAL has no task slug, so correlate from the task's known `Files:` and time-window back to the agents that touched them; ambiguity degrades to `unknown`).
2. `commands/resume-pipeline.md` — `/resume-pipeline <slug>`: reconcile → auto-mark `verified-complete` → auto-resume `partial`/`in-flight` scoped to the unfinished remainder → surface `unknown` to the user.
3. A **mandatory five-surface audit trail** for every auto-recovery (`RECOVERY_LOG.md`, `WIP.md` `[AUTO-RECOVERED]` annotation, `LEARNINGS.md ### Recovery Events`, in-conversation notice, synthetic `recovery` event into the WAL) — so "automatic" never means "silent."

Completion becomes *verified, not claimed*. A truncated agent can never leave the pipeline silently wrong; the worst case is "detected-unverified → reconciled."

## Considered Options

### Option A — Read back the existing observations.jsonl as the Tier-2 WAL (CHOSEN)

- **Pros:** Zero new journal infrastructure — the WAL is already hardened (fcntl locking, merge driver, toggle gate, auto-rotation) and carries every field recovery needs. One new *reader*, not a new *writer*. Honors Simplicity First.
- **Cons:** The WAL was not designed as a recovery log → carries no task slug. Paid for by a file+time correlation contract.

### Option B — New per-agent AGENT_TRACE_<agent>.jsonl written by an extended send_event.py hook

- **Pros:** A purpose-built recovery trace could carry the task slug directly, simplifying correlation.
- **Cons:** Duplicates the existing WAL — a second journal recording the same tool stream, with its own locking/rotation/merge concerns. This was the original proposal's "Layer B"; the session's discovery that `observations.jsonl` already serves the role makes it dead weight. **Rejected against Simplicity First.**

### Option C — Pure prevention: restructure the implementer loop so the durable WIP write is atomic and early (the steelmanned runner-up)

- **Pros:** Closes the write-behind gap at its source; if every step recorded its completion *before* doing the work (write-ahead intent) and flushed durably *per file*, a truncation would lose at most one file of state and the coordinator could trust the record. No reconciliation reader, no correlation contract, no recovery command — strictly simpler surface area. Prevention is always cheaper than cure when it works.
- **Cons (why it loses):** **No agent-authored write is trustworthy under a hard mid-turn token cut.** A token-ceiling truncation can land *between* the write-ahead marker and the flush, or mid-flush; the existing turn-budget guard is keyed to `maxTurns`, not the token ceiling, and a hard cut bypasses it entirely with no opportunity to write anything. Prevention shrinks the blast radius but cannot guarantee the durable record reflects reality — which is the exact property recovery needs. Worse, a pure-prevention design provides *no path at all* for the case that already happened (an agent died mid-work this session): there is nothing to reconcile against, so the pipeline is simply stuck. Prevention and reconciliation are not substitutes — prevention reduces *how often* reconciliation fires; only reconciliation against Tier-1 ground truth can *recover* a truncation that already occurred. We therefore keep a **minimal** slice of prevention (`[IN-PROGRESS]`-at-start + a token-budget guard) as a cheap accelerator, but anchor the design on reconciliation.

## Consequences

**Positive:**
- Completion is verified from ground truth; a truncated agent cannot advance the pipeline on a false claim.
- Reuses a hardened, already-shipped WAL — minimal new surface (one reader script + one command + light edits).
- Recovery is fully transparent and reversible (five-surface audit); a wrong auto-action is always visible.
- Read-only reconciler is safe to run at any pipeline seam.
- Adds the fourth pipeline feedback loop, structurally consistent with the existing rework / CIS / skill-genesis loops.

**Negative / costs:**
- Correlation without a slug is the softest spot; mitigated by file+time keys and safe degradation to `unknown`.
- The synthetic `recovery` event adds a new `event_type` for metrics/dashboard consumers (additive, filterable).
- Recovery restores *pipeline position*, not *correctness sign-off* — the verifier still runs downstream as the behavioral gate. A `verified-complete` verdict means "the work exists and its tests pass," not "the work is correct."

## Disconfirmation

- **Falsifier (what evidence would make this decision wrong):** If `observations.jsonl` were found to drop tool rows often enough that file+time correlation is wrong (not merely imprecise) on a material fraction of real truncations — i.e., the reconciler attributes a step's work to the *wrong* agent and emits a false `verified-complete` — the Tier-2-as-hint premise fails and the WAL would need slug-stamping (Option B) or the design would have to rely on Tier-1 alone. The guard is that ambiguity degrades to `unknown`; a *confident-but-wrong* attribution is the falsifier to watch for. Likewise, if `SubagentStop`/`PostToolUse` hooks were shown NOT to fire on a hard token-ceiling cut in the live harness (the one assumption still resting on Phoenix-window evidence rather than a mid-work-cut probe), Tier-2's "did it stop" signal weakens to best-effort — survivable (Tier 1 still arbitrates) but it removes the `in-flight` discrimination.
- **Steelmanned runner-up (Option C, pure prevention):** The strongest case for prevention is that *the cheapest bug is the one that never happens*. If the implementer loop wrote step intent write-ahead and flushed `WIP.md` durably per file completed, the durable record would trail reality by at most one file, the coordinator could mostly trust it, and the entire reconciler + correlation + recovery-command surface (≈3 new files, a correlation contract, a 5-verdict state machine) would evaporate. For a team that values a small surface over recovery completeness, and that accepts "occasionally stuck, human un-sticks it" as the failure mode, prevention-only is a defensible, simpler choice.
- **Reversal trigger (the future signal that should prompt revisiting):** If, after rollout, the reconciler emits `unknown` on a *majority* of real truncations (correlation too weak to be useful) OR the auto-resume path is observed clobbering/duplicating verified work despite the Tier-1 guard, revisit: either stamp the WAL with the task slug (collapsing correlation to a lookup, partially adopting Option B) or down-scope to detect-and-surface-only (drop auto-resume, keep reconciliation). Conversely, if truncations effectively stop occurring because a future harness change makes the durable write atomic/early at the platform level, retire the recovery command and keep only the read-only reconciler as a verification gate.
