---
id: dec-081
title: Self-host guard for /onboard-project and /new-project
status: accepted
category: behavioral
date: 2026-04-27
summary: Both onboarding commands abort when invoked on a Claude Code plugin source repo (`.claude-plugin/plugin.json` present) unless `PRAXION_ALLOW_SELF_ONBOARD=1` is set, protecting the canonical source-of-truth chain from accidental self-injection.
tags: [onboarding, self-host, guard, plugin-source, idempotency, source-of-truth]
made_by: user
pipeline_tier: lightweight
affected_files:
  - skills/onboard-project/references/detection.md
---

## Context

Praxion's `/onboard-project` and `/new-project` are the two paths by which the four canonical `CLAUDE.md` blocks (`## Agent Pipeline`, `## Compaction Guidance`, `## Behavioral Contract`, `## Praxion Process`) get injected into a consumer project. The verbatim source of those blocks lives in `commands/onboard-project.md` (with `commands/new-project.md` mirroring them per `commands/CLAUDE.md`'s "Flagship Pair — Onboarding" contract). This makes the Praxion repo itself a privileged producer of content it does not consume — it is the *source* of the blocks, not a downstream injection target.

Until now, no guard prevented an operator from accidentally invoking either command inside the Praxion repo (or inside any other Claude Code plugin source repo with the same source-of-truth shape). The accident is plausible — autocomplete, command-palette muscle memory, exploratory invocation — and the consequences are non-trivial:

- The heading predicates in `/onboard-project` Phase 6 (and `/new-project` step 10) detect each of the four blocks independently. Praxion's own `CLAUDE.md` does not contain headings literally matching `## Agent Pipeline` or `## Praxion Process` — its bespoke sections cover similar ground under different titles (`## Behavioral Contract (applied)`, `## Compaction Guidance`, `## Session Protocol`). So the predicates would fire, append the four canonical blocks on top of the bespoke sections, and produce *duplicated meaning under conflicting headings*.
- Once the blocks are injected, the canonical source (`commands/onboard-project.md` § blocks) and the injected instance (Praxion's `CLAUDE.md`) become two-source-of-truth surfaces. Edits to one silently skew from the other, because no automation reconciles them.
- Recovery would require a manual revert of the `CLAUDE.md` append, which is doable via `git` but visually noisy and easy to mis-revert (the blocks are long).

The surrounding context that prompts this guard:

- The user explicitly raised the failure mode in conversation ("can we avoid that when running praxion, if by mistake we do /onboard-project we don't screw the project").
- The `shipped-artifact-isolation` rule already constrains shipped artifacts (including these two commands) to inline rationale rather than reference specific `dec-NNN` ids — the guard's prose must follow that constraint.
- The cost of a guard is low: a single `test -f` check at pre-flight time in each command, with an env-var override for the rare-but-real case of a divergent fork that wants self-onboarding.

## Decision

Add a self-host guard to both `/onboard-project` and `/new-project` that detects `.claude-plugin/plugin.json` at the project root and aborts unless the operator has opted in via `PRAXION_ALLOW_SELF_ONBOARD=1`.

Specifically:

- **`/onboard-project`** — insert a new step 6 in §Pre-flight ("Plugin-source-repo guard") *before* the existing greenfield-shape check. Renumber the existing steps 6 → 7 (greenfield) and 7 → 8 (print pre-flight report). The new step is an abort-or-continue diagnostic that produces no writes regardless of outcome — consistent with §Pre-flight's stated contract ("writes nothing").
- **`/new-project`** — append a 5th check to §Guard: `[ "${PRAXION_ALLOW_SELF_ONBOARD:-}" = "1" ] || ! test -e .claude-plugin/plugin.json`. The single-line predicate keeps the §Guard structure uniform (five checks, single abort message). The §Guard abort message gains one sentence covering the override.
- **Override semantics** — `PRAXION_ALLOW_SELF_ONBOARD=1` is the single shared env var for both commands. When set, `/onboard-project` prints a one-line warning to chat ("Self-onboard override active — proceeding on plugin source repo at \<project-root\>.") and continues; `/new-project` proceeds silently because §Guard is binary (pass/abort).

The guard's prose in both commands inlines the rationale (per `shipped-artifact-isolation`'s self-test) — no reference to this ADR's id appears in either command body.

## Considered Options

### Option A — No guard, trust the user

Status quo. Operators must remember not to invoke `/onboard-project` or `/new-project` on plugin source repos; recovery from accidental invocation is via `git` revert.

**Pros:** zero added complexity; no new env var; no special case in the pre-flight model.
**Cons:** the failure mode is plausible (autocomplete, command palette, exploratory invocation) and asymmetric (the cost of misfire is non-trivial revert work + a brief loss of source-of-truth coherence); the source-of-truth chain that `commands/CLAUDE.md` documents is unprotected against accidents.

### Option B — Explicit marker file (e.g., `.praxion-source` sentinel)

Add a hidden marker file to Praxion (and any other plugin source repo that wants the protection); both commands check for the marker and abort if present.

**Pros:** loud, grep-able, intent-explicit; override is "delete the file" which has obvious blast radius.
**Cons:** requires adding a new file to Praxion (and any future plugin source repo that wants the protection); doesn't auto-generalize — a fresh plugin scaffold would need to remember to add the marker; one more concept to document and maintain.

### Option C — Inferred structural check via `.claude-plugin/plugin.json` (selected)

Both commands check for `.claude-plugin/plugin.json` at the project root. The file is the universal manifest for any Claude Code plugin source repo; its presence is a strong signal that the directory is a plugin source repo, not a consumer project. Override via `PRAXION_ALLOW_SELF_ONBOARD=1` for divergent forks.

**Pros:** zero new files to maintain; generalizes to every Claude Code plugin source repo (Praxion and any future fork or unrelated plugin); the signal is structural rather than convention-based, so it can't drift; the override has clear opt-in semantics.
**Cons:** implicit — a future maintainer reading the command must infer "ah, plugin source repos shouldn't self-onboard"; the env var name is a new concept that must be documented (inlined in the command prose, per `shipped-artifact-isolation`).

### Option D — Praxion-specific name match (`plugin.json["name"] == "i-am"`)

Check both for `.claude-plugin/plugin.json` AND that its `name` field matches Praxion's plugin name.

**Pros:** very specific to Praxion; no false positives on other plugin source repos.
**Cons:** other Claude Code plugin source repos face the *same* failure mode and benefit from the same guard; specializing to Praxion leaves them exposed; the failure mode generalizes and the guard should generalize with it. Rejected as scope-too-narrow.

## Consequences

**Positive:**

- Accidental invocation of `/onboard-project` or `/new-project` on the Praxion repo (or any Claude Code plugin source repo) is blocked at pre-flight time with no writes attempted. Recovery from accident becomes "no-op required" rather than "manually revert four CLAUDE.md blocks."
- The source-of-truth chain documented in `commands/CLAUDE.md` ("Flagship Pair — Onboarding") gains a structural defense, not just a documentation contract.
- The guard generalizes to all Claude Code plugin source repos, not just Praxion. Any plugin author who clones their plugin source repo and runs `/onboard-project` inside it gets the same protection.
- The override (`PRAXION_ALLOW_SELF_ONBOARD=1`) preserves operator agency for divergent forks that genuinely want self-onboarding.

**Negative:**

- One additional pre-flight step in `/onboard-project` (re-numbering the existing greenfield-shape check from 6 to 7).
- One additional check in `/new-project`'s §Guard, lengthening the §Guard abort message by one sentence.
- A new environment variable (`PRAXION_ALLOW_SELF_ONBOARD`) that operators must learn if they hit the guard. Mitigated by inlining the override instructions in the abort message itself.
- Implicit signal: a future maintainer reading the command must understand why `.claude-plugin/plugin.json` is the canary. The inlined prose documents the rationale, but the structural choice (file existence as proxy for "plugin source repo") is a convention.

**Operational:**

- The guard is purely pre-flight: no writes, no side effects, no state mutation. Failure mode on the guard itself (e.g., `test` exit code other than 0/1) defaults to "abort," which is the safe direction.
- Existing already-onboarded user projects see zero change — they don't have `.claude-plugin/plugin.json` so the guard never fires.
- The override env var is intentionally not a CLI flag, because both commands are slash commands without argument-parsing infrastructure beyond `AskUserQuestion`. Env-var overrides are the cheapest mechanism that doesn't require touching the command tooling layer.
- The guard does not invalidate any existing test fixtures: the onboarding tests live in worktrees that do not contain `.claude-plugin/plugin.json` at their root unless one is explicitly placed there.

## Related Decision

Coupled to the source-of-truth contract documented in `commands/CLAUDE.md` ("Flagship Pair — Onboarding") and the `shipped-artifact-isolation` rule. Neither supersedes nor re-affirms a prior ADR — this is a new behavioral decision about command pre-flight scope, not a revision of an existing one.
