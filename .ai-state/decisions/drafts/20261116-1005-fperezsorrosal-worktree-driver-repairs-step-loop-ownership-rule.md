---
id: dec-draft-42477a36
title: One ownership rule for Read-only entries, in a leaf module the gate, the commit and the prompt read
status: proposed
category: architectural
date: 2026-11-16
summary: The meaning of a Read-only entry (a bare path withholds its file and owns its nodes; a path::node entry owns its node's verdict and withholds nothing), matched by repository-relative node id in every pocket, moves from _step_loop_gate.py and _step_loop_io.py into _step_loop_ownership.py.
tags: [step-loop, driver, ownership, read-only, gate, commit]
made_by: agent
agent_type: systems-architect
branch: worktree-driver-repairs
pipeline_tier: full
affected_files:
  - scripts/_step_loop_ownership.py
  - scripts/_step_loop_gate.py
  - scripts/_step_loop_io.py
  - scripts/_step_loop_settle.py
  - scripts/_step_loop_record_gate.py
  - scripts/_step_loop_render.py
  - skills/software-planning/references/document-templates.md
affected_reqs: [REQ-07, REQ-08, REQ-09, REQ-10, REQ-43]
---

## Context

A `Read-only:` entry was read three ways. The gate treated a `path::node` entry as the owner of one node's verdict; the commit cut every entry at `::` and withheld the whole file, so the step that owned the file committed without it and was warned `outer-loop-edit`; and the gate compared a non-root pocket's own node ids with the plan's repository-relative entries, so a node a later step owned in the eval pocket read as a failure and spent an attempt. The implementer, told nothing, read a node entry of its own file as a ban on editing it.

## Decision

`_step_loop_ownership.py` (stdlib only) holds the one rule: the parse `ReadOnlyEntry = BarePath | NodeEntry`, `OUTER_LOOP_PREFIXES`, `entry_owns`, `Ownership` with `in_pocket(pocket)`, `withheld(path, entries)` and `own_node_permissions(step)`. A bare path owns every node under it and withholds its file; a node entry owns its node and withholds nothing; outer-loop directories are withheld whatever the plan says; nodes are matched in the repository's form in every pocket. The gate, the commit, the edit warnings and the prompt read it; `_step_loop_gate.py` and `_step_loop_io.py` re-export the names they held.

## Considered Options

### Patch the three sites in place

Smallest diff. Rejected: it keeps three parses of one entry, the condition td-648 grew from, and leaves `_step_loop_io.py` at 754 lines.

### Put the rule in the plan reader (`_plan_steps.py`)

The plan reader already parses `Read-only:`. Rejected: its import purity is pinned by `scripts/test_plan_steps_files.py`, and pocket and outer-loop knowledge is the driver's, not the plan grammar's.

## Consequences

Positive: one definition serves pending, withholding and the prompt; about 80 lines leave `_step_loop_io.py`; a re-pin of a test in any pocket can be scheduled after the step that changes its value.

Negative: one more module; two re-export shims to keep until the standing tests import the new module directly.

## Disconfirmation

- **Falsifier**: a plan in which a node entry's file is withheld from the commit of the step whose `Files:` names it, or in which a red node a later, not-done step names repository-relative reads as a failure in a non-root pocket.
- **Steelmanned runner-up**: patch in place; the three sites change once and rarely, and a leaf module with re-exports adds indirection a reader must follow.
- **Reversal trigger**: the re-exports outlive one release with no test importing the new module, or a fourth reader of `Read-only:` appears outside the driver; then either fold the module back or widen it to that reader.
