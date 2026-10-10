---
id: dec-draft-59b24004
title: Gates, dev-link, argument handling and the pull-request rule scope follow the workflows into skills
status: proposed
category: behavioral
date: 2026-10-10
summary: "GL04/GL05/S04 scan skills/*/SKILL.md and C04 is re-scoped to skills rather than retired; S04 no longer counts harness path variables as argument use; --dev-link links skills; create-simple-python-prj and document-api read $ARGUMENTS with a documented token order; pr-conventions loads for exactly review-pr, merge-worktree and release."
tags: [gate-liveness, artifact-conformance, dev-link, arguments, pr-conventions, skills]
made_by: agent
agent_type: systems-architect
branch: worktree-commands-to-skills
pipeline_tier: full
affected_files:
  - scripts/check_gate_liveness.py
  - scripts/check_artifact_conformance.py
  - scripts/check_registry_projection.py
  - agents/sentinel.md
  - install_claude.sh
  - rules/swe/vcs/pr-conventions.md
  - rules/_manifest.yaml
re_affirms: [dec-173]
---

## Context

Moving the workflows into `skills/` would blind the checks that watched them: GL04 and GL05 read ambient script calls only in `agents/*.md` and `commands/*.md` (16 ambient calls move), S04 checked argument-hint use only in commands and counted `${CLAUDE_*}` path variables as argument use, C04 checked command descriptions only. `--dev-link` linked `commands` but not `skills`. Two workflows used `$1` as the first argument while the harness numbers from `$0` (probed live, 2026-10-10), and the dashboard's `${ARGUMENTS:-$(pwd)}` never received its argument. The pull-request rule's `commands/*pr*.md` glob over-matched, and a mechanical move would have extended the over-match to unrelated skills.

## Decision

1. GL04 and GL05 add `skills/*/SKILL.md` before any file moves and drop `commands/*.md` when the directory is retired; scope is `SKILL.md` only (ambient calls in `references/` are deferred). Simulation over the tree showed no newly visible finding.
2. S04 and C04 read `skills/*/SKILL.md`; C04 is re-scoped, not retired (the check registry is append-only and C02 checks presence only); S04 accepts only `$ARGUMENTS` or an indexed placeholder as argument use. Sentinel rows mirror each scope in the same commit as its script; the conformance JSON uses new key names for the new scope.
3. `--dev-link` links `hooks`, `scripts` and `skills`.
4. `create-simple-python-prj` and `document-api` read `$ARGUMENTS` with an explicit token table, each optional token defaulting when empty or left literal; the dashboard assigns `$ARGUMENTS` and falls back to the current directory; literal dollar amounts are escaped.
5. `rules/swe/vcs/pr-conventions.md` scopes to exactly `skills/review-pr/SKILL.md`, `skills/merge-worktree/SKILL.md`, `skills/release/SKILL.md`, `.github/**/*.md` and `rules/swe/vcs/git-conventions.md` (user decision, 2026-10-10): the rule no longer loads for, say, `project-metrics`.

## Considered Options

- **Retire C04 as subsumed** — rejected: nothing else flags an empty or placeholder skill description.
- **`skills/*pr*/SKILL.md` globs** — rejected: they match `llm-prompt-engineering`, `project-exploration`, `python-prj-mgmt`, `onboard-project` and others, injecting a 6.7k-character rule on each read.
- **Keep `$1` because it was the old text** — rejected: it delivered the second token, never the intended first; restoring intent is the one behaviour change the semantics constraint allows.

## Consequences

**Positive:** the liveness and conformance discipline follows the workflows; a path variable can no longer pass for argument use; development edits to any workflow are live without reinstall; the two positional workflows receive what users type.

**Negative:** interim gate scopes carry both families for a few commits; the rule narrowing is a deliberate behaviour change outside the workflows themselves.

## Prior Decision

**dec-173 (re-affirmed):** `/resume-rework` takes no positional argument and reads `VERIFIER_FINDINGS.md` from the worktree. The move re-examined every argument contract; this one survives unchanged, and the skill keeps its help text and `--findings` / `--dry-run` levels.
