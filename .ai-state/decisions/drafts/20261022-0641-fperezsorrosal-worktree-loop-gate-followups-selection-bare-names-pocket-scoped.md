---
id: dec-draft-3c42fa4b
title: "A bare file name, a single-segment import stem and a layout pairing connect only within one pocket"
status: proposed
category: behavioral
date: 2026-10-22
summary: "Bare-basename literals, single-segment flat-stem imports and test_<stem> layout pairs no longer cross pocket boundaries; slash literals, globs, dotted imports and declared deps still do; a path left with no connection widens"
tags: [test-selection, resolver, pockets]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/_python_selection.py
  - scripts/resolve_test_scope.py
affected_reqs: [REQ-01, REQ-02, REQ-03]
supersedes_in_part: [dec-411]
---

# A bare file name, a single-segment import stem and a layout pairing connect only within one pocket

## Context

td-463 (selection). A change to `eval/src/praxion_evals/adherence/cli.py` selected 106 root-pocket test files: 78 by a bare `cli.py` literal anywhere, others by a layout pairing with `scripts/project_metrics/tests/test_cli.py` and by flat-stem import resolution, which treats the root pocket as containing every nested pocket. None of those tests reads or loads the eval file.

## Decision

A bare-basename literal (no slash, no wildcard) connects only holders whose most specific pocket is the changed path's; a `test_<stem>`/`<stem>_test` layout pairing connects only within one pocket; the flat-stem fallback for a single-segment import name resolves only to files in the importer's own most specific pocket. Slash literals, globs, dotted multi-segment import suffixes and declared dependencies keep crossing pockets. Accounting is unchanged: a path whose every connection was removed reaches no test and widens. REQ-03 is proven by structure (canaries and inverse guards), a dropped-pair differential over the selection-size instrument's change sets, and the selection audit where it runs.

## Considered Options

### Scope the three bare-name edges to the pocket (chosen)

Keeps every qualified connection and every same-pocket reader.

### Drop bare-basename literals entirely

Loses real readers that name a sibling file by its bare name inside their own pocket.

### A hand-kept list of names that must not cross pockets

Drifts; every new common name re-opens the defect.

## Consequences

- Positive: a common name no longer pulls another pocket into a step's scope; the gate's scope shrinks to what the change can break.
- Negative: a cross-pocket dependency stated only at run time through a bare name (a path insert, a path built from parts) is no longer selected; the CI full suites and the selection audit backstop it.

## Prior Decision

dec-411 classed an exact basename as a named edge that holds at every hop, across the whole repository. This decision narrows that clause to the changed path's own pocket; dec-411's basename-pattern rules and data-only accounting stand.
