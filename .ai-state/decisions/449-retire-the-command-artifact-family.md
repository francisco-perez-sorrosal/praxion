---
id: dec-449
draft_id: dec-draft-83d80fb8
title: Retire the command artifact family — every Praxion slash workflow is a skill under its own name
status: accepted
category: architectural
date: 2026-10-10
summary: "The 44 commands/*.md workflows move to skills/<name>/SKILL.md with unchanged names, invocation modes, tools and procedures; commands/, the plugin.json commands key and the knowledge.commands C4 element are removed, and no surface teaches a command family."
tags: [commands, skills, plugin-manifest, architecture-model, migration, retirement]
made_by: agent
agent_type: systems-architect
branch: worktree-commands-to-skills
pipeline_tier: full
retires_elements:
  - praxion.knowledge.commands
affected_files:
  - .claude-plugin/plugin.json
  - skills/README.md
  - skills/CLAUDE.md
  - scripts/sync_canonical_blocks.py
  - docs/diagrams/architecture/src/architecture.c4
  - .ai-state/DESIGN.md
  - docs/architecture.md
  - claude/canonical-blocks/hackathon-mode.md
supersedes_in_part: [dec-014, dec-015, dec-029, dec-055, dec-153]
re_affirms: [dec-340, dec-434, dec-437]
dissent: "commands/ was the one assistant-agnostic source the Cursor and Codex exporters read; retiring it bets that every supported assistant keeps invoking skills by name."
---

## Context

Praxion carries 44 user- or model-invoked workflows as flat files in `commands/`, registered by `"commands": ["./commands/"]` in the plugin manifest and modelled as `knowledge.commands` in the C4 model. Claude Code merged custom commands into skills (2.1.3): a command file and a skill directory both create `/<name>`, the skill wins a name clash, and the platform docs call commands the older format. The remaining reason Praxion kept the family — `commands/` as the assistant-agnostic source its Cursor and Codex exporters read — no longer holds: Cursor loads `.cursor/skills/` and honours `disable-model-invocation`; Codex invokes skills as `$name` and Praxion already wraps every skill for it. Four workflows already moved (onboarding, step-loop, ralph-lite, lens-fanout) and tests assert their command files stay absent. The user asked to "completely deprecate the creation of new custom/slash commands … and preserve all the semantics when moving commands to skills".

**Activation:** no — a family move whose options were settled by the user at intake; the design space is the commit ordering, recorded in the plan.

## Decision

1. Each workflow becomes `skills/<name>/SKILL.md` under the same name (`git mv`), with `name:` first, its invocation mode, tool set and argument hint preserved (one-line forms), its body normalized only in form; the only behaviour changes restore what the old form intended (first-token positional arguments in two workflows, the dashboard's root argument, escaped dollar amounts).
2. `commands/` (its readme rows move to the skills catalog), the manifest `commands` key, keyword and description word, and the `knowledge.commands` element with its §3a row are removed; the rework-loop and installer edges re-point to `knowledge.skills`.
3. The always-loaded set, agents, rules and the published hackathon block describe slash-invoked workflows as skills; Claude Code's own built-in commands stay platform vocabulary. Managed projects receive the block change as ordinary drift once the hackathon block joins the refreshable set, a separate decision recorded as a tech-debt deferral (td-403); until then the reworded block reaches only new onboardings.
4. A file placed back in a `commands/` directory fails the test suite (the harness scans that location by default once the manifest stops naming it).

## Considered Options

### Option 1 — Move every workflow to a skill and retire the family (chosen)

One artifact family, one authoring canon, one adapter path; identical slash names. Cost: about 150 files repointed across gates, tests, docs and the model.

### Option 2 — Keep `commands/` as the export source and generate skills from it

Preserves the exporters' input. Rejected: two representations of every workflow, a generator to maintain, and the concept the user asked to remove stays alive.

### Option 3 — Keep thin command stubs that dispatch into skills

Preserves file paths for anything that reads them. Rejected: two names per workflow (the skill wins anyway), and the stubs teach that commands still exist.

## Consequences

**Positive:** one place to author and find a workflow; Cursor shows each workflow once; workflows may now carry supporting files; gates watch skill bodies uniformly; the plugin validator stops loading the catalog files as phantom commands.

**Negative:** a large one-time repoint; existing Cursor/Codex installs need one reinstall to sweep stale projections; managed projects see one canonical-block drift; the `commands/` directory is no longer a browse surface (the catalog group replaces it).

## Disconfirmation

- **Falsifier:** a supported assistant (Claude Code, Cursor or Codex) cannot invoke a Praxion workflow by name as a skill, or a migrated workflow behaves differently from its frozen before-state beyond the three restorations.
- **Steelmanned runner-up:** keep `commands/` as the assistant-agnostic export source (the rationale `command-crafting` recorded): a flat, frontmatter-light file is the lowest common denominator every assistant can read, so the source stays portable even if a future assistant drops skills; exporting from it insulates Praxion from any one vendor's skill format. It loses because all three targets now read the same skill directory natively, so the "portable" layer would be a second copy feeding converters that only re-create what the targets already load.
- **Reversal trigger:** a target assistant Praxion supports ships without skill invocation, or Claude Code deprecates user-invoked skills in favour of another surface.

## Prior Decision

- **dec-014, dec-015, dec-029, dec-153 (partially superseded):** each composes a methodology skill (and, for dec-029/dec-153, an agent) with a *command* as the user trigger. The narrowed clause is only the artifact kind of the trigger: `/report-upstream`, `/explore-project`, `/roadmap` and `/review-interface` are now user-invoked skills. The compositions themselves — no dedicated agent for interactive, main-conversation workflows; an agent when the work needs its own context window (dec-153's rule) — survive unchanged.
- **dec-055 (partially superseded):** the hybrid split (bash for deterministic prerequisites, a Claude layer for the conversation) stands; the clause naming that layer "a slash command, a first-class Praxion artifact" is narrowed to a user-invoked skill. dec-340 already made that move for onboarding; this decision retires the family the clause named.
- **dec-340, dec-434, dec-437 (re-affirmed):** each moved one workflow into a skill or ruled a loop entry is never a command; this decision re-examines that direction for the whole family and finds it holds. dec-340's dissent (keep thin command stubs) is Option 3 above, rejected again for the same reason.
