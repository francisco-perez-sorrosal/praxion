---
id: dec-426
draft_id: dec-draft-ee960cee
title: Implementer returns are recorded in an append-only ITERATION_LEDGER.jsonl task artifact with one parser-and-writer module, not in a WIP.md section
status: accepted
category: architectural
date: 2026-10-04
summary: "New registered pipeline artifact .ai-work/<slug>/ITERATION_LEDGER.jsonl (floor=None, dashboard=False, snapshot=False, cleanup delete) holds one JSON record per implementer return: v, recorded_at, step, attempt, agent_id, verdict, decided_by, test_result (a Result: line that parses as Counts or NoRun), commit (sha or explicit null; key required), stop_reason (completed/turn-cap/blocked/no-marker). New scripts/iteration_ledger.py is its one reader (records in append order plus findings located by 1-based append position; absent and empty read as no history) and one writer (round-trip validation before a single append-mode write), with a CLI whose append derives verdict and decided_by from reconcile() and the test result from the step's recorded Result: line. Written by the orchestrator now, by the step-loop driver later"
tags: [iteration-ledger, step-loop, pipeline-artifact, artifact-registry, data-structure]
made_by: agent
agent_type: systems-architect
branch: worktree-step-schema
pipeline_tier: standard
affected_files:
  - scripts/iteration_ledger.py
  - scripts/artifact_registry.py
  - skills/software-planning/references/artifact-inventory.md
  - skills/software-planning/references/agent-pipeline-details.md
affected_reqs: [REQ-09, REQ-10, REQ-11]
superseded_in_part_by: [dec-432, dec-428]
---

## Context

The step-loop driver that follows this change must read the loop's history (step, attempt, agent, verdict and what decided it, test result, commit, stop reason) without the orchestrator's memory. The loop falsifiers need the same history: cap-outs, and steps the orchestrator absorbed. The brief rated the ledger's shape 6/10 on certainty, specifically an append-only file versus a `WIP.md` section. So the `data-structure-design` pass was run before choosing.

The pass established:
- **Legal states.** A record is a value. `commit` is a sum type, a sha or an explicit "none holds the work". The key must be present, so an absent key is a defect and is never read as none. `stop_reason` is a closed set.
- **Invariants.** Earlier records never change (REQ-10). Every reader gets the same records. A malformed record is reported with its position and never guessed.
- **Ownership.** One writer at a time, the orchestrator now and the driver later. No agent writes it.
- **Lifecycle.** Absent, then empty, then n records; absent and empty read the same.
- **Evolution.** Additive keys are ignored, and a version key covers breaking changes.

**Activation:** fired, as for the companion `dec-427`. Two plausible representations, a file of its own and a section of `WIP.md`, plus a third format option.

## Decision

1. **The file.** The ledger is `.ai-work/<slug>/ITERATION_LEDGER.jsonl`, one JSON object per non-blank line. A line's 1-based index among non-blank lines is its append position.
2. **The module.** `scripts/iteration_ledger.py` (stdlib, Python 3.9-safe) holds the normative shape in its docstring and is the only reader and writer:
   - `read_ledger(task_dir) -> LedgerReading(records, findings)`.
   - `append_record(task_dir, record)`, which renders the record, round-trips it through the line parser, refuses before writing on failure, and appends one line.
   - A CLI: `append <slug> --step --attempt --agent-id --stop-reason (--commit <sha> | --no-commit)` derives `verdict`/`decided_by` from `reconcile()` and `test_result` from the step's latest recorded `Result:` line. `read <slug> [--json]` exits 0 clean, 1 on findings, 2 on an input error.
3. **Registration.** `scripts/artifact_registry.py` registers the ledger with no consumer flags (`floor=None`, `dashboard=False`, `snapshot=False`) and cleanup `delete`, after the `MEASUREMENTS.md` precedent. A per-artifact test with a canary pins it. `artifact-inventory.md` documents its writer, readers and lifetime.
4. **The procedure.** One record per implementer return, after the handshake commit. It is stated in the same authoritative paragraph as the attempt cap.

## Considered Options

### Option A: A `## Iterations` section of `WIP.md`

- **Pro:** no new file, and the records sit beside the progress they describe. The acceptance driver allows it.
- **Con:**
  - `WIP.md` is rewritten by several writers (the implementer's own fields, the planner's fragment merges, the orchestrator), so "earlier records never change" cannot be enforced.
  - Four line parsers already read `WIP.md`, and every spawn loads it, so each record costs context on every later spawn.
  - The driver would have to load prose to read data.

### Option B: An append-only Markdown table, like `MEASUREMENTS.md` (dec-418)

- **Pro:** human-readable rendered, and a proven precedent with a shared table reader.
- **Con:** agent ids, result lines and replan text need pipe escaping. An empty ledger is a header-only table. The consumer is code, the driver, not a human verifier, which is the reverse of the reason `MEASUREMENTS.md` chose a table.

### Option C: A JSONL file with one module (chosen)

- **Pro:**
  - Append-only by construction.
  - JSON escaping carries any text.
  - A line index is the append position.
  - It matches the observation-log precedent.
  - It is machine-first for the driver.
- **Con:** humans read it through `read` or a pager. `scripts/test_artifact_registry.py`'s consumer-filename scan looks only at `.md`/`.yml`/`.yaml` names, so the `.jsonl` name needs its own per-artifact test. That is harmless while no consumer lists it.

### Writer CLI that derives fields vs. one that takes every field (sub-decision)

Deriving `verdict`, `decided_by` and `test_result` from ground truth means the record never carries the orchestrator's transcription of a verdict, which would be a self-report one step removed. The cost is that the ledger module depends on `reconcile_pipeline_state.reconcile()`. That dependency points toward the more stable component.

## Consequences

- **Positive:** the driver and the measurements get history as data, with one parser, and malformed records surface with their position. Registration keeps the artifact discoverable without touching the dashboard, precompact or floor consumers.
- **Negative:**
  - The ledger is deleted with the task directory. The orchestrator-absorbed-steps falsifier therefore cannot be computed from past pipelines' ledgers unless the driver pipeline decides to harvest them (into the calibration row, or archived).
  - The registry's consumer-filename drift scan does not see `.jsonl` names.
  - The CLI's `append` costs one reconcile per record.

## Disconfirmation

- **Falsifier:** the decision is wrong if the step-loop driver, once built, needs to read the ledger together with `WIP.md` on every iteration anyway, for example because it must re-derive the step order or the attempt count from both and finds them disagreeing. That would mean splitting the state across two documents cost more than the rewrite hazard it avoided. A second sign: if fewer than half of the pipelines that should write records do so, the separate file would be unread operational overhead.
- **Steelmanned runner-up (Option A, a `WIP.md` section):** `WIP.md` is already the single place a resuming agent, a human and the reconciler look for a step's state. The attempt count already lives there by this same change. Putting the iteration history beside it keeps the attempt count and the attempt records in one document, so they cannot disagree. The rewrite hazard is a procedure problem that one rule ("never edit the section") and a reconciler check that record counts only grow would contain. The context cost is bounded too, at about two short lines per step.
- **Reversal trigger:** if the driver pipeline makes `WIP.md` machine-owned (written only by the driver), the multi-writer hazard disappears. Then reconsider folding the ledger into `WIP.md`. If the ledger and the `Attempts:` lines are ever observed disagreeing, make the ledger the attempt count's source and drop the `WIP.md` line.
