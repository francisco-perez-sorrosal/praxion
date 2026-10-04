---
id: dec-draft-854e860b
title: Diagram regeneration command interface and review-check list format
status: proposed
category: behavioral
date: 2026-10-04
summary: "One command (python3 scripts/regenerate_diagrams.py [ROOT...] [--staged|--check] [--json]) serves the hook, CI and docs; exit codes 0/1/2/3; regeneration failures are three-line stderr messages of four named kinds; findings are '<CHECK-ID> <VIEW> <PASS|FAIL> <evidence>' lines; the review checks are one Markdown table DRC-01..DRC-12 linked from the diagram conventions rule"
tags: [diagrams, cli, pre-commit, ci, review-checks, likec4, agents]
made_by: agent
agent_type: interface-designer
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - scripts/diagram-regen-hook.sh
  - .pre-commit-config.yaml
  - .github/workflows/architecture.yml
  - claude/aac-templates/architecture.yml.tmpl
  - docs/architecture-diagrams.md
  - rules/writing/diagram-conventions.md
affected_reqs: [REQ-10, REQ-11, REQ-14, REQ-15, REQ-16, REQ-17]
---

## Context

Regeneration is documented in four divergent incantations: the model header's `likec4 export d2 <file>` does not exist; the architecture doc uses a wrong output directory; the catalog lists 2 of 7 view commands. The hook, CI and the managed-project template each carry their own loop.

The spec requires four things here:
- regeneration failures of four named kinds abort the commit or fail CI;
- the CI drift gate passes whenever renders match;
- an onboarded project regenerates with one documented command;
- review checks that an agent applies from text alone.

## Decision

- **One command:** `python3 scripts/regenerate_diagrams.py [ROOT ...] [--staged] [--check] [--json]`. Its modes:
  - default renders in place;
  - `--staged` is pre-commit mode: staged roots only, `git add` of the renders, and a warn-and-exit-0 when `likec4`/`d2` is not on PATH;
  - `--check` renders into a temporary directory, compares byte-for-byte, runs the review checks and writes nothing.
- **Exit codes:**
  - 0: success, or the toolchain is absent in `--staged` mode;
  - 1: regeneration failure, or drift or a FAIL finding under `--check`;
  - 2: usage error;
  - 3: toolchain absent or not the pinned version (default and `--check` modes).
- **Regeneration failures** print three stderr lines (`FAIL <kind> <view>` / `cause:` / `fix:`). The kinds are `toolchain-error`, `no-views`, `view-without-render` and `render-without-names`.
- **Findings** print to stdout as `<CHECK-ID> <VIEW> <PASS|FAIL> <evidence>` (JSON Lines with `--json`). In `--staged` mode only FAIL findings print, as non-blocking `WARN` lines on stderr.
- **CI keeps two steps:** regenerate in place, then fail on a non-empty `git status --porcelain -- docs/diagrams/`. The review checks never run inside the drift-gate job.
- **Review checks** live in one Markdown table under `## Review checks` with columns `Id | Check | Evidence | Pass condition` (ids DRC-01..DRC-12), linked directly from `rules/writing/diagram-conventions.md`.

## Considered Options

### Option 1: Single command with modes (chosen)
- **Pros:** one source for the hook, CI, template and docs (REQ-17); agents get structured findings without pixels (REQ-14); custom exit codes are documented.
- **Cons:** the hook, CI and template change together.

### Option 2: Keep per-surface shell loops and add a separate checker script
- **Pros:** smaller diff.
- **Cons:** the drift between surfaces that caused today's four incantations persists.

### Option 3: Fold the review checks into the CI drift gate
- **Pros:** mechanical enforcement.
- **Cons:** REQ-16 requires the managed drift gate to pass whenever renders match, and BA-06 runs that job's steps verbatim.

## Consequences

- **Positive:** contributors type one command; failures name the view and the fix; reviewers and agents share check ids.
- **Negative:** a managed project's CI needs the command in-repo (vendored by onboarding). Placement is the architect's decision.
- **Category:** `behavioral`. This fixes the command's interface and the guidance format. Whether a new script component exists, and where it lives, is the systems-architect's render-route decision.
