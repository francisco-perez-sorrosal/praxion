---
id: dec-draft-6692b078
title: Observation-log location and project resolve once, in the owner package, to the nearest project within the checkout
status: proposed
category: architectural
date: 2026-10-01
summary: "A new hooks/_observation_log/location.py locate(cwd) becomes the only answer to which log a row goes to and which project it carries; capture_session, capture_observations, measure_context_surface and record_gate_fire stop deriving Path(cwd)/.ai-state and Path(cwd).name, so sessions working in a checkout subdirectory are recorded instead of silently dropped"
tags: [observability, observations-jsonl, hooks, wal, spawn-budget, td-288]
made_by: agent
agent_type: systems-architect
branch: worktree-wal-slug-attribution
pipeline_tier: standard
affected_files:
  - hooks/_observation_log/location.py
  - hooks/_observation_log/__init__.py
  - hooks/_observation_log/writer.py
  - hooks/capture_session.py
  - hooks/capture_observations.py
  - hooks/measure_context_surface.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-10]
dissent: "A git subprocess (git rev-parse --show-toplevel) is the authoritative checkout root; .git-entry detection can disagree with git under GIT_DIR overrides or a broken .git file."
---

## Context

Each of four observation-log writers decided for itself where its row goes: `capture_session.py` (`_resolve_ai_state_dir`, `_pipeline_slug`), `capture_observations.py`, `measure_context_surface.py` and `writer.record_gate_fire`. Every one computed `Path(cwd) / ".ai-state"` and `Path(cwd).name`. A session whose working directory was a subdirectory of the checkout (it was `.ai-work/<slug>/` twice in the selection-gaps-dogfood pipeline) therefore wrote no `agent_start`, `agent_stop` or tool row at all. `spawn_count.py` reported 6 spawns for 7, and 6 for 16 in an earlier pipeline. `dec-401` made `hooks/_observation_log/` the single write path but left location to the callers. `dec-390` requires a row's `project` and the committed summary's `pipeline_slug` to come from one shared mapping.

## Decision

Add `locate(cwd) -> Location | None` to `hooks/_observation_log/location.py`. `Location` is a value `(state_dir, project_dir, project)`, and `locate` is its only constructor. All four writers call it once at their boundary.

Resolution, in one upward pass with no subprocess:
1. If the `cwd` itself holds `.ai-state/`, use it. That is today's behavior.
2. Otherwise, use the nearest ancestor holding `.ai-state/`, but never one above the first directory carrying a `.git` entry (the checkout root; a linked worktree's `.git` file counts).
3. When no `.git` exists above, the `cwd` is in no checkout, and nothing is recorded.

`project` and `pipeline_slug` are `project_dir.name`, never a resolved symbolic-link target's name. A non-string or empty `cwd` resolves to `None`. Rows recorded at a checkout root are unchanged.

**Activation:** no. Live probing and the acceptance contracts left one viable shape; the only open choice was git-subprocess versus filesystem detection of the checkout root, settled below.

## Considered Options

### Option 1 — fix each writer in place
- **Pros:** no new module.
- **Cons:** keeps four copies of the rule that caused the defect, so `project` and `pipeline_slug` can drift again (`dec-390`).

### Option 2 — one resolver in the owner package (chosen)
- **Pros:** one rule and one test surface. It sits beside the append it serves (`dec-401`), and the shared `project`/`pipeline_slug` mapping survives.
- **Cons:** writers gain an import. `.git`-entry detection is an approximation of git's own answer.

### Option 3 — resolve with `git rev-parse --show-toplevel`
- **Pros:** git's authoritative answer, already used by `remind_task_brief.py`.
- **Cons:** a subprocess on every tool call, which the writer's hot-path rule forbids. It also costs latency on the per-tool `PostToolUse` path and fails when git is missing.

## Consequences

- **Positive:**
  - Sessions in any subdirectory are recorded under the checkout's name, so `spawn_count.py` stops undercounting.
  - Nested fixture projects keep their own logs.
  - A nested separate clone without `.ai-state/` never leaks rows into the enclosing project.
  - `measure_context_surface` measures the project root.
- **Negative:**
  - The checkout root is detected from the filesystem, not from git.
  - A session in a non-git directory below a project records nothing, as it does today.

## Disconfirmation

- **Falsifier:** a recorded session whose rows land in a log other than the nearest `.ai-state/` at or below its checkout root. Or a subdirectory session whose rows differ from the root session's in any field except those recording time. REQ-01 and REQ-02 acceptance tests detect both.
- **Steelmanned runner-up:** Option 3. git is the source of truth for "the checkout", it handles every `GIT_DIR`/`GIT_WORK_TREE` arrangement, and `remind_task_brief.py` already pays the subprocess at `PreToolUse`. A cached resolution per session could amortize it.
- **Reversal trigger:** a real session whose rows are dropped or misplaced because `.git`-entry detection disagreed with git. Or the writer's hot-path import constraint is lifted, at which point a cached git resolution costs nothing.
