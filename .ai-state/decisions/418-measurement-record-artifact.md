---
id: dec-418
draft_id: dec-draft-47fb43f2
title: Measured footprint values are recorded in an append-only MEASUREMENTS.md table, not as TEST_RESULTS.md lines
status: accepted
category: implementation
date: 2026-10-01
summary: "Measurement steps append rows (Criterion, Phase baseline|final, Value, Reading measured|estimate|none, Head, Taken, Command) to .ai-work/<slug>/MEASUREMENTS.md; the latest row per criterion and phase is authoritative; a measurement step records Result: none measurement in TEST_RESULTS.md and never adds Measurement: lines there, keeping the shared step parser and the 1024-byte no-run ceiling untouched"
tags: [measurement, test-results, pipeline-artifacts, footprint, verifier]
made_by: agent
agent_type: systems-architect
branch: worktree-quant-acceptance-criteria
pipeline_tier: standard
affected_files:
  - scripts/check_footprint_criteria.py
  - scripts/artifact_registry.py
  - skills/software-planning/references/artifact-inventory.md
  - skills/software-planning/references/document-templates.md
affected_reqs: [REQ-02, REQ-03]
---

## Context

REQ-02 requires each measurement to record the command, the value it reported and when it ran, somewhere the verifier reads it. `TEST_RESULTS.md` already admits a `Result: none` block for a measurement step, and its `Mutation:` line is a precedent for an additive per-step line. However:
- the file is parsed by one shared step parser that serves both the shape checker and the reconciler;
- no-run blocks are capped at 1024 bytes;
- freshness detection needs each reading's commit (`head`) and its reading kind as typed fields.

## Decision

- Measured values go in `.ai-work/<slug>/MEASUREMENTS.md`, a table with these columns:
  - Criterion: a spec `FC-` id;
  - Phase: `baseline` or `final`;
  - Value: in the criterion's unit;
  - Reading: `measured`, `estimate` or `none: <reason>`;
  - Head: 8-character SHA;
  - Taken: UTC ISO-8601;
  - Command: the exact command run, backticked.
- Rows are append-only. The latest row per `(Criterion, Phase)` is authoritative.
- A measurement step records `Result: none measurement` in `TEST_RESULTS.md` and nothing else there.
- The check script is the log's only parser.

## Considered Options

### `Measurement:` lines in `TEST_RESULTS.md`

- **Pros:**
  - No new artifact.
  - The verifier already reads the file.
- **Cons:**
  - Touches the shared step parser.
  - Five or more criteria with commands approach the 1024-byte no-run ceiling.
  - Key-value lines are a weaker typed record than a table with a header.

### Dedicated `MEASUREMENTS.md` (chosen)

- **Pros:**
  - A typed table that the spec-table reader also parses.
  - No reconciler interplay.
  - No byte ceiling.
- **Cons:** one more ephemeral artifact to register (artifact registry and inventory).

## Consequences

**Positive:** stale, late, incomparable and wrong-command measurements are decidable from the file plus git.

**Negative:**
- A new registry entry and inventory row.
- Agents must remember not to duplicate values into `TEST_RESULTS.md`; the measurement-step template says so.
