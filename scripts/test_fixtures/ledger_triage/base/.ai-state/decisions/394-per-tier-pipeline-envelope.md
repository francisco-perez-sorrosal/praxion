---
id: dec-394
title: Encode the per-tier pipeline envelope mechanically — registry-owned artifact floor, agent_start spawn count with a per-tier budget, model-visible calibration reminder
status: accepted
category: architectural
date: 2026-09-25
summary: A monotone `floor` field on each artifact-registry row drives the eval manifest; scripts/spawn_count.py counts spawns and resumes per slug from agent_start rows; the calibration reminder moves to a once-per-session Stop-time additionalContext.
tags: [process-economy, pipeline, spawn-budget, artifact-floor, artifact-registry, calibration, wal, hooks, coordination-protocol]
supersedes_in_part: dec-261
affected_files:
  - scripts/artifact_registry.py
  - scripts/test_artifact_registry.py
  - eval/src/praxion_evals/harness/task_manifest.py
  - scripts/spawn_count.py
  - hooks/remind_calibration.py
  - hooks/hooks.json
---

Fixture stub: frontmatter only, reproducing dec-394's live status/edges for the ledger-triage test corpus — its file overlap with td-264's location (hooks/remind_calibration.py) is a context-only link (REQ-04), never evidence.
