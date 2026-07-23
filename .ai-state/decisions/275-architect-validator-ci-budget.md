---
id: dec-275
title: Align the architect-validator CI gate's allowlist + turn budget with its pre-merge protocol
status: accepted
category: configuration
date: 2026-07-22
summary: The dsl-validate CI job denied the architect-validator's own protocol commands (uv run lint-imports, aac_fence_validator.py, likec4 MCP) and capped it at 15 turns, so it burned out on permission denials and failed CLOSED without a verdict; widen the allowlist to the protocol, raise the turn budget, and arm the no-likec4 fallback.
tags: [ci-cd, architect-validator, claude-code-action, allowlist, turn-budget, dsl-validate, flaky-gate, github-actions]
made_by: agent
agent_type: orchestrator
branch: fix-dsl-validate-turn-budget
pipeline_tier: direct
affected_files:
  - .github/workflows/architecture.yml
---

## Context

The `dsl-validate` job in `.github/workflows/architecture.yml` runs the `architect-validator`
agent in `--mode=pre-merge` via `claude-code-action` with `--max-turns 15` and the allowlist
`Read,Glob,Grep,Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(find:*)`.

Observed on PR #39 (the self-healing-loop P1 branch) and on at least two recent `main` runs
(both doc-heavy PRs touching architectural paths): the job failed with
`##[error]Reached maximum number of turns (15)` and `"permission_denials_count": 10`, never
producing a verdict — a **fail-CLOSED flake**, not a real structural-drift finding.

Root cause: the agent's documented pre-merge protocol (`agents/architect-validator.md`) runs
`uv run lint-imports --config fitness/import-linter.cfg --no-cache` (import-graph check),
`python3 scripts/aac_fence_validator.py <file>` (fence validity), and *prefers* the `likec4`
MCP tools (absent in CI). None of those are in the allowlist, so every core step was denied;
the agent retried, flailed, and exhausted its 15-turn budget before it could report.

## Decision

Align the CI gate with the agent's actual protocol:

1. **Widen `--allowedTools`** to add `Bash(uv run lint-imports:*)`,
   `Bash(python scripts/aac_fence_validator.py:*)`, and
   `Bash(python3 scripts/aac_fence_validator.py:*)` — the read-only analysis commands the
   protocol runs. The existing `git`/`find`/`Read`/`Glob`/`Grep` entries stay.
2. **Raise `--max-turns` 15 → 30** — even with zero denials the multi-step sweep (git diff →
   find `.c4` → import-linter → read decisions → per-file fence check → analyze → structured
   output) is tight at 15 for a substantial diff.
3. **Set `AAC_FENCE_VALIDATOR_LIKEC4=disabled` on the agent step** so its `aac_fence_validator.py`
   subcalls take the documented no-likec4 fallback (find + direct `.c4` reads, WARN not FAIL)
   cleanly instead of hanging on a missing binary — mirroring the mechanical fence step above it.

Job permissions stay read-only (`contents: read`, `pull-requests: read`, `id-token: write`).

## Considered Options

- **A — Align allowlist + raise turns + disable likec4 (chosen).** Targets the root cause
  (denials + budget) minimally; restores the gate's value.
- **B — Raise `--max-turns` only.** Rejected: denials still waste turns and the agent still
  cannot run its import-graph/fence checks — it would just fail slower.
- **C — Configure the `likec4` MCP in CI.** Rejected: heavier setup; the agent already ships a
  documented no-likec4 fallback, and MCP-in-CI is out of scope for a flake fix.
- **D — Make `dsl-validate` advisory (non-blocking).** Rejected: that discards the gate's
  purpose. The fix restores the gate rather than muting it.

## Consequences

- **Positive:** the gate stops failing-closed on architecturally-substantial diffs; it can
  actually execute its import-graph + fence + ADR-cross-reference checks; the read-only
  permission set is unchanged, so no new write surface is introduced.
- **Negative / cost:** the allowlist is broader (still command-scoped to read-only analysis
  commands, not blanket `Bash(python:*)`); a doc-heavy PR still costs more turns (30 is margin,
  not unbounded); `uv run lint-imports` imports the project's modules — a pre-existing property
  of the fitness check, not introduced here.

## Disconfirmation

- **Falsifier:** `dsl-validate` still turn-exhausts at 30 on a genuine diff → raise further or
  split the sweep into narrower per-check steps.
- **Reversal trigger:** `claude-code-action` ships first-class MCP-in-CI plus a turn model that
  makes the manual allowlist/turn tuning unnecessary.
