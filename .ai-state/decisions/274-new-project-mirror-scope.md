---
id: dec-274
title: AC7 "/new-project mirrors the install" satisfied by existing defer pattern, no new-project.md code change
status: accepted
category: implementation
date: 2026-07-22
summary: The P1 ci-autofix onboarding install (caller + policy templates) lands only in /onboard-project Phase 8e; /new-project needs no duplicate logic because its existing generic exit-handoff already defers all Phase 8e-style baseline installs (dependabot, pre-commit, CONTRIBUTING) to a subsequent /onboard-project run.
tags: [onboarding, ci-cd, autofix, scope, planning]
made_by: agent
agent_type: implementation-planner
branch: feat-self-healing-loop
pipeline_tier: standard
affected_files:
  - commands/onboard-project.md
  - commands/new-project.md
affected_reqs: [REQ-06, REQ-07]
---

## Context

`SYSTEMS_PLAN.md` AC7 states: "`/onboard-project` installs the caller + policy idempotently
... `/new-project` mirrors the install." Read literally, this implies `/new-project` needs
its own copy of the ci-autofix install logic (analogous to how it duplicates, e.g., the AaC
scaffolding sub-flow inline at its own Phase 4f/5f). Verification against the live codebase
(`commands/new-project.md` Phase Contracts table, its Guard, and its exit-handoff text)
shows this assumption does not hold for Phase-8e-class baseline assets.

`commands/new-project.md`'s own numbered phases (1–8) do not install `dependabot.yml.tmpl`,
`pre-commit-config.yaml`, `CONTRIBUTING.md.tmpl`, `.editorconfig`, or any other
`claude/project-baseline/*` asset that `/onboard-project` Phase 8e installs. Its Phase 8
exit handoff instead **prints a recommendation** to run `/onboard-project` next, with a
deliberately partial enumeration of "remaining onboarding surfaces" (git hooks, merge
driver, `.ai-state/` skeleton, `.claude/settings.json` toggles — notably omitting Phase 8e
items entirely, dependabot included). A user who runs `/new-project` and never follows up
with `/onboard-project` gets no dependabot config either — an accepted, pre-existing gap
this ADR does not change.

## Decision

Land the ci-autofix onboarding install as a **new Phase 8e sub-step only** in
`commands/onboard-project.md` (mirroring `8e.7` — dependency-scanning config — exactly).
Make **no functional change** to `commands/new-project.md`'s own phase flow. AC7's "mirrors
the install" is satisfied by the pre-existing defer-to-`/onboard-project` architecture, the
same way it already is for every other Phase 8e asset. If the exit-handoff enumeration in
`commands/new-project.md` benefits from a one-line mention of the new sub-step for
discoverability, that is a cosmetic text edit, not new logic — and is optional, not
required, since the enumeration is already deliberately partial today.

## Considered Options

### Option A — Rely on the existing defer pattern (chosen)
- **Pros:** zero new code in `commands/new-project.md`; consistent with how every other
  Phase 8e asset works today; avoids inventing a second install path that could drift from
  `/onboard-project`'s idempotency predicate over time.
- **Cons:** a literal reading of AC7 ("mirrors the install") is satisfied only by
  architecture, not by a visible diff in `new-project.md` — worth documenting so a future
  reader doesn't reintroduce duplicate logic trying to satisfy AC7 more literally.

### Option B — Duplicate the install sub-step inline in `new-project.md`'s own flow
- **Pros:** a literal, visible "mirror" of the install exists in both commands.
- **Cons:** duplicates idempotency-predicate logic across two command files (drift risk);
  no precedent for any other Phase-8e asset; violates Stay Surgical — the existing
  architecture already produces the same end state via the exit-handoff recommendation.

## Consequences

- **Positive:** smaller diff, no new duplicate-logic drift surface, consistent with the
  established dependabot precedent.
- **Negative / cost:** none identified — a greenfield user who skips `/onboard-project`
  entirely also skips ci-autofix distribution, exactly as they already skip dependabot.

## Prior Decision

None — this is a scoping clarification made during P1 step decomposition, not a
supersession of `dec-273`.
