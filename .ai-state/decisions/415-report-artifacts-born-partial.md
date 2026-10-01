---
id: dec-415
draft_id: dec-draft-b819a971
title: Report artifacts are written first, marked [PARTIAL], and unmarked last; existence no longer means finished
status: accepted
category: behavioral
date: 2026-10-01
summary: "The verifier, researcher, systems-architect, implementation-planner and sentinel write their report within their first three tool calls with [PARTIAL] on the title and remove it as their last edit (a light review writes LIGHT_REVIEW_step-<N>.md the same way); artifact_registry owns PARTIAL_MARKER and is_partial, the eval task manifest reports partial and the dashboard no longer treats a [PARTIAL] verification report as done"
tags: [agents, turn-cap, partial-output, write-early, artifact-registry, eval-manifest, dashboard, completion-handshake]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - agents/verifier.md
  - agents/researcher.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/sentinel.md
  - scripts/artifact_registry.py
  - eval/src/praxion_evals/harness/task_manifest.py
  - eval/src/praxion_evals/harness/families/family1_pipeline_fidelity.py
  - dashboard_app/src/server/view-models/workshops.ts
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/intra-step-review.md
affected_reqs: []
---

## Context

Between 2026-09-29 and 2026-10-01 the verifier stopped at its 80-turn cap twice and a td-296 researcher once, each with no report on disk. Recovery cost a charged resume or a fresh spawn. Four of the five report-producing agents already carried an "Incremental writing" instruction ("write the document structure at the start of Phase 1"), so the gap was not a missing instruction:

- The instruction sat inside each agent's **final** phase section (the verifier's Phase 12, line ~303 of 471). An agent working through its phases in order meets it only after the turns it protects are spent.
- `[PARTIAL]` was defined as something written *on failure*. A turn cap ends the agent mid-call with no cleanup pass, so the marker could never be written in the case it existed for.

Two consumers equated an artifact's existence with completion: the eval task manifest (`present` whenever the file exists) and the dashboard (a workshop is done once `VERIFICATION_REPORT.md` exists). A report written early would have turned both into false passes.

## Decision

1. **Born partial, unmarked last.** The verifier, researcher, systems-architect and implementation-planner write their report within their first three tool calls, titled with ` [PARTIAL]`, with a `**Completed phases**:` line and every section `[pending]`. They fill sections as phases end and remove the marker as their last edit. The instruction sits before Phase 1, replacing the late paragraph and the on-failure bullet. The sentinel opens its report titled `# Sentinel Report [PARTIAL]` and unmarks it at the Phase 6 close-out. A light review writes `LIGHT_REVIEW_step-<N>.md` as `verdict: [PARTIAL]` and sets the verdict last.
2. **Existence no longer means done.** `scripts/artifact_registry.py` owns `PARTIAL_MARKER` and `is_partial(text)` (the first `# ` heading carries the marker; a body quote does not count). The eval manifest reports `partial` (FAIL when required, WARN when optional); the dashboard does not mark a workshop done on a `[PARTIAL]` verification report. The completion handshake reads a `[PARTIAL]` title as contradicting a finished return.
3. **Placeholder names resolve.** `by_name` matches instances of placeholder names (`CONSULT_<discipline>.md`, `LIGHT_REVIEW_<step>.md`) with a lowercase-slug variable part; exact names win.

## Considered Options

### Option 1: write the partial report under a different name and rename it at the end

Existence at the canonical path would keep meaning "done", so no consumer changes. Rejected: the dashboard and the compaction snapshot could not show work in progress, the orchestrator would need a second name to look for, and the user asked for a `[PARTIAL]` marker.

### Option 2: only move the existing paragraph earlier

Fixes the placement but keeps `[PARTIAL]` as an on-failure act, so a capped agent still leaves a skeleton indistinguishable from a finished report. Rejected.

### Option 3: born partial plus consumer predicate (chosen)

Small prompt change (about 1.1 KB across five agents), one shared predicate, two consumers taught, a drift test pinning the instruction ahead of Phase 1.

## Consequences

- A capped report agent leaves a usable partial report whose `[pending]` sections name the remainder to resume.
- Every future consumer that treats a report as finished must read `is_partial`; the registry comment and this record name the obligation.
- The light review now leaves a small file per reviewed step, cleaned up with its slug.
- Agents load from the installed plugin, so the change reaches spawned agents only after a release and plugin update.
