---
id: dec-448
draft_id: dec-draft-654284cd
title: Merge command-crafting into skill-crafting — one reference owns user-invoked skill authoring
status: accepted
category: architectural
date: 2026-10-10
summary: "skills/command-crafting/ is deleted; its still-valid content becomes skills/skill-crafting/references/user-invoked-skills.md plus three runtime sections in plugin-and-troubleshooting.md, written from the live-probed harness facts rather than copied."
tags: [skill-crafting, command-crafting, authoring, progressive-disclosure, merge]
made_by: agent
agent_type: systems-architect
branch: worktree-commands-to-skills
pipeline_tier: full
affected_files:
  - skills/skill-crafting/SKILL.md
  - skills/skill-crafting/references/plugin-and-troubleshooting.md
  - agents/context-engineer.md
  - scripts/skill_description_diet.yaml
dissent: "A separate user-invoked-skill authoring skill would keep slash-workflow guidance one hop from the listing instead of two, where an author searching for it would find it by name."
---

## Context

With commands retired as a family (dec-449), `skills/command-crafting/` (SKILL 194 lines, REFERENCE 234, two references) teaches authors to create an artifact that no longer exists. Its content is of three kinds: unique (description length by consumer, `argument-hint` rules, argument substitution), duplicated in `skill-crafting` (field table, naming, structure, best practices), and obsolete (file-versus-directory choice, `.claude/commands/` locations). It also carries two defects found by the live probe: it documents `$1` as the first argument (the harness numbers from `$0`), and its own `$ARGUMENTS` examples are substituted when the skill loads. `context-engineer` injects it whole on every spawn.

**Activation:** no — a component merge with a single credible target.

## Decision

1. New `skills/skill-crafting/references/user-invoked-skills.md` (one level deep, TOC): description length by consumer; `argument-hint` rules; arguments and dynamic context with the probed numbering, the named-arguments append gotcha, prose-placeholder substitution and the empty/literal handling; invocation modes with a caveat that `scripts/validate.py` does not yet accept `user-invocable` or `context`; runtime pointer; silent frontmatter-parse failures; a convert-a-command-file recipe.
2. `references/plugin-and-troubleshooting.md` gains the discovery/live-reload, permission-management and silent-parse sections (dates carried).
3. `skill-crafting/SKILL.md` gains one satellite line and a one-line pointer; no `$ARGUMENTS` literal is written there. Its description gains trigger terms for user-invoked skills in the same commit that deletes `command-crafting`, keeping the model-visible listing under its ceiling at every commit.
4. `skills/command-crafting/` is deleted and every reference to it repointed; `context-engineer` stops injecting it.

## Considered Options

### Option 1 — One reference plus moved runtime sections (chosen)

Smallest listing and injection cost; one canon. The caveat records a pre-existing validator gap that the skill-crafting refresh closes.

### Option 2 — Keep a renamed `user-invoked-skill-crafting` skill

Discoverable by name. Rejected: a second listing entry against 24 tokens of headroom, and two canons for one artifact type.

### Option 3 — Fold everything into `skill-crafting/SKILL.md`

One file. Rejected: pushes it further past its line warning and puts substitution-prone text into every context-engineer spawn.

### Option 4 — Extend `validate.py` now for `user-invocable` and `context`

Removes the contradiction. Rejected for this change: the contradiction predates it (the field table already teaches both keys), `validate.py` has no tests, and aligning two of the nine missing keys leaves a half-aligned validator; the refresh pipeline owns the whole set.

## Consequences

**Positive:** one place to learn every skill shape; about 2.5k tokens less per context-engineer spawn; the `$1` defect is not carried forward.

**Negative:** a two-hop path (skill → reference) to slash-workflow guidance; the validator caveat stands until the refresh pipeline lands.

## Disconfirmation

- **Falsifier:** authors writing user-invoked skills after this change repeatedly miss the reference (wrong hint quoting, missing placeholder) while the same errors were rare under `command-crafting`.
- **Steelmanned runner-up:** a dedicated `user-invoked-skill-crafting` skill whose description matches "slash command", "argument-hint" and "$ARGUMENTS" queries directly; the listing is how a model finds guidance, and a reference is invisible to it until `skill-crafting` is loaded.
- **Reversal trigger:** a description-trigger evaluation (planned for the refresh pipeline) shows `skill-crafting` failing to activate on user-invoked-skill authoring queries.
