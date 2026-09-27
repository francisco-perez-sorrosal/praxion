---
id: dec-draft-e7fcbfcc
title: State-aware tech-debt triage — a snapshot reader, an advisory ledger_health probe, sentinel TD07 and /triage-debt, anchored by notes-cell triage stamps
status: proposed
category: architectural
date: 2026-09-27
summary: "Add a state-snapshot reader and an advisory ledger_health probe that select ledger triage candidates from precise evidence only (never file overlap or age), surface them via sentinel TD07, and feed per-row JSON digests to a /triage-debt command whose verdicts are recorded as sha-anchored stamps in the notes cell"
tags: [tech-debt, ledger, triage, sentinel, advisory-probe, dedup-key, state-awareness]
made_by: agent
agent_type: systems-architect
branch: worktree-ledger-triage
pipeline_tier: standard
affected_files:
  - skills/software-planning/references/tech-debt-ledger.md
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - .ai-state/TECH_DEBT_LEDGER.md
  - .ai-state/TECH_DEBT_RESOLVED.md
dissent: "A judge-every-row sweep with no mechanical selection would have perfect recall and no evidence/context policy to maintain; selection misses premise-true-but-moot rows (1 of 9 in the ground truth) by construction."
---

## Context

The tech-debt ledger has no process for retiring rows whose premise the project has moved past. Sentinel TD05 audits
only ledger *discipline* (missing `resolved-by`, stale `in-flight`, unassigned owners), and `last-seen` refreshes only
when the original producer re-detects a row, which one-off producers (verifier, orchestrator) never do. On
2026-09-27, 16 of 75 active rows had a `first-seen` older than 30 days, and a manual survey found 9 rows whose premise
was corrected, falsified, partly resolved, or refuted in place. `wontfix` exists but has no trigger, no criteria and no
repurpose path.

The obvious linkage, file overlap between a row's `location` and an ADR's `affected_files`, was measured and rejected
as evidence. It links 37 of 75 rows (49%), including rows whose premise is live and was being fixed that day, and
restricting it to superseding ADRs still links 29 of 75. The ADR corpus already has the right shape of tool in
`scripts/adr_health.py`, an advisory reference-decay classifier that withholds classes when an oracle is unavailable
instead of guessing.

A further constraint came from the ledger's own gate. For the 12 rows carrying the collision discriminator, the
`dedup_key` hashes the `notes` cell, so any notes edit makes `check_state_ledgers.py --check` raise a blocking
`dedup-mismatch`.

The user ruled that there is no finalize-chain change, so the "event" trigger must come from state recorded at
judgment time.

## Decision

Add four connected components. None of them changes the ledger schema, the `dedup_key` formula, or the finalize chain.

1. **`scripts/ledger_snapshot.py`, the state-snapshot reader.** It reads the world once into an immutable snapshot:
   the ledger pair parsed through `state_ledger_schema`, ADR facts through `query_adrs`'s primitives, and a bounded
   number of git calls (it reuses `adr_health`'s rename and deletion indexes and makes one commit-index call). A pure
   per-row function computes the row's state delta over its window. The window starts at `first-seen`, or at the
   anchor commit of the row's latest triage stamp.
2. **`scripts/ledger_health.py`, the probe.** It is advisory and never edits; exit 0 always. It separates *evidence*
   from *context*.
   - **Evidence** (enough to make a row a candidate): a cited decision now terminal or narrowed; location decay
     (renamed, deleted or vanished); a **notes citation decay** (a backticked path or `path:line` cite in the row's
     notes that no longer resolves at HEAD, filtered for lazy/ephemeral shapes — same oracle set as location decay);
     an unresolvable `adr` goal link; a later code-touching commit naming the td id; a shared base key or a re-file
     after a realignment; a later notes amendment. For judged rows it adds a moved keep-evidence file, a new
     superseding ADR on the row's files, an unusable judgment, and a discard that recurred.
   - **Context** (never enough on its own): file overlap, churn and age.
   - It withholds any class whose oracle is unavailable, with a named reason. It emits the TD07 family envelope and
     per-row judge digests (`ledger-triage-digest/1`).
3. **Sentinel TD07.** A read-only family row that surfaces candidates and writes no ledger row.
4. **`/triage-debt`.** It runs the probe and, for a full sweep (`--all`), fans the per-row digests out to judge
   subagents in batches; each judge re-probes its digests and proposes an outcome — **kept**, **realigned** (rewrite
   location/notes/severity to the current state, prior premise kept in the stamp), **discarded** or **merged**
   (only when the judge's own re-probe cites a `file:line` at HEAD, a named decision, or a named state change — the
   **discard confidence gate**; any judgment short of that, including any "not worth doing" call, is **escalated**
   instead, with no stamp and no ledger edit) — and merges the batch proposals into **one** confirmation table for
   the kept/realigned/discard/merge outcomes. The command applies only what the user confirms, writes
   `TRIAGE_ESCALATIONS.md` for the escalated rows as a separate user discussion, and records each applied outcome as
   a stamp in the notes cell, `[triage YYYY-MM-DD @<anchor>] <outcome>: …`. After applying, it runs
   `check_state_ledgers.py --backfill` and then `--check`, and stops if the check fails. Judges never edit the
   ledger; only the command's apply step does.

**First triage in scope.** Building the tooling is not the deliverable on its own — after this branch's verifier
passes and it merges to `main`, the orchestrator runs `/triage-debt --all` over every active row on `main`, under a
separate task slug and spawn budget, applies the confirmed kept/realigned/discard/merge outcomes in one
`chore(state)` commit, and brings the escalated rows to the user. This pipeline builds the mechanism; the first real
triage is its first use, not a follow-up task.

The stamp anchor is the merge-base of HEAD and the default branch. A judged row resurfaces only when its
`anchor..HEAD` window shows a change of the kinds listed under evidence.

**Activation:** fired. Honest uncertainty sits on the precision and recall of the evidence set, so a Dialectical
Inquiry was run against the judge-everything runner-up (below), and its strongest point is absorbed as the command's
`--all` mode.

## Considered Options

### Option A — Judge every active row, no mechanical selection

A `/triage-debt` sweep over all rows, each with a light digest.

- **Pro:** perfect recall. No evidence/context policy to maintain.
- **Con:** about 75 re-probes per sweep, with no signal for *when* to sweep again. TD07 could not say which rows
  need attention. Stamps would carry no staleness semantics.

### Option B — File overlap (plus tags) as the decision link

- **Pro:** simple, and it reuses `query_adrs --paths` directly.
- **Con:** a measured 49% base rate with live-premise rows included. It would drive wrong discards. Tags add noise.

### Option C (chosen) — Evidence/context split, windowed by sha-anchored stamps

- **Pro:** on the live ledger, about 26 candidates and 8 of 9 ground-truth stale rows recovered. The two live-premise
  controls are not flagged on staleness grounds. Judged rows come back only on real state change. It reuses
  `adr_health` and `query_adrs`.
- **Con:** a class of premise-true-but-moot rows is unreachable mechanically (covered by `--all`). The ruling-2 overlap
  trigger on judged rows can re-surface several kept rows per broad superseding ADR.

### Option D — Stamp in a new column, or strip stamps from the notes digest

- **Pro:** kept `dedup_key` stable for discriminated rows on keep.
- **Con:** a schema change against the registry, the finalize field order and every writer's prose, or a formula
  change that couples identity to a notes micro-grammar. Neither helps realign, discard, merge, or other notes edits
  (rework suffix, recurrence note). Rejected in favour of the ledger's own `--backfill` + `--check`, which is fail-closed at
  pre-commit.

## Consequences

**Positive**

- The ledger gains a premise-level health check to complement TD05's discipline checks.
- `wontfix` gets criteria. Realignment (formerly "repurpose") gets a path that keeps the row's id
  and records its prior shape.
- One reader serves the sentinel, the command and tests.
- No shipped finalize behaviour changes fleet-wide.
- Value judgments ("is this still worth doing") never silently become discards — the discard
  confidence gate routes anything short of re-probed evidence to `escalated`, a user checkpoint
  rather than a ledger edit.
- The ledger actually gets triaged: the first `/triage-debt --all` sweep runs immediately
  post-merge over every active row, not as a deferred follow-up.

**Negative**

- Every triage write must run `--backfill`, because the four active discriminated rows re-key on any notes edit.
- Only `adr` goal links resolve in this version. `architecture`, `claude-md` and `spec-req` links are withheld per row.
- Stamps lengthen `notes` cells.
- The probe must stay stdlib-only and executable, so that the sentinel (bare `python3`) and the shipped command
  (`PATH`) can run it.

## Disconfirmation

- **Falsifier.** This decision is wrong if, after the first two real triages, most confirmed discards or realignments
  came from rows the probe did *not* flag (found only under `--all`), or if most flagged rows are judged `kept` with
  evidence unrelated to their flagged class. Either would mean the evidence/context split selects no better than
  chance and Option A should replace it.
- **Steelmanned runner-up (Option A).** The ledger is small (about 75 rows), and every judgment the probe routes is
  made by the same model anyway. A mechanical selector therefore adds a policy surface (nine classes, oracle
  withholding, stamp windows) whose failure mode, silent under-selection, is invisible, while a full sweep's cost is
  bounded and its recall total. The mechanical signals could shrink to *ranking* hints in a full sweep, with no
  candidacy notion at all.
- **Reversal trigger.** Revisit if the active ledger stays under about 100 rows *and* the `--all` sweep proves cheap
  enough to run at every sentinel cadence. Also revisit if the measured precision of flagged classes stays below
  about 30% over two triages. Then demote candidacy to ranking only.
