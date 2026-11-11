---
id: dec-504
draft_id: dec-draft-cab0fdc7
title: "The startup-context diet closes its preload, catalogue and manifest-axis items by recorded decision"
status: accepted
category: behavioral
date: 2026-11-11
summary: "Six remaining roadmap items close without a move. Agent skill preloads stay as each role's anchors (no kit exercises the mode-specific candidates). Near-miss skills are not merged (the harness already ranks the listing by use). No pointer hook or catalogue search (no gap measured). Domain packs leave the diet as the next initiative. The activation manifest gets no scope or trigger columns (the rules manifest and paths: carry both). The ML rules keep their pipeline globs. Each item names its reversal trigger."
tags: [startup-context-diet, finish-line, catalogue, preload, skills-listing, domain-packs, activation-manifest, managed-projects]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - agents/
  - skills/
  - rules/_manifest.yaml
  - rules/_audience.yaml
  - rules/ml/
affected_reqs: []
---

## Context

The diet finishes when every roadmap component has landed with a measured before and after, or been closed by a recorded decision. Six items remained without either. Each was read again on 2026-11-11, at $0, against the tree, the observation log and the current Claude Code docs (`code.claude.com/docs/en/skills.md`, `plugins/manifest-reference.md`):

1. **"The preload roster: one anchor skill per agent, plus pointers that say when to read the rest."** The full body of every skill an agent's `skills:` names is injected at its start (skills docs: "the full skill content is injected at startup"). Measured with the offline estimate (bytes/3.6) over the 17 definitions: about 152K tokens of preloaded bodies in all. The implementer carries 10,897 tokens per spawn (`software-planning` 5,488, `code-review` 2,121, `refactoring` 3,286) over 557 spawns in 90 days, about 6.1M tokens. The verifier carries 6,744 over 211, and the test-engineer the implementer's three skills over 95.
2. **Merge near-miss skills.**
3. **A capped pointer hook, or catalogue search, if a gap remains.**
4. **Core plugin plus domain packs, enabled per project by onboarding.**
5. **The activation-mode manifest's project-scope and trigger axes, and its Cursor export.**
6. **The Hygiene phase's held item: the ML rules' pipeline globs.** Agent descriptions, held beside it, are the catalogue's description trim, decided on its own.

## Decision

1. **Preloads stay.** The only mode-specific preloads are `refactoring` in the implementer and test-engineer definitions, used on `[Phase: Refactoring]` steps. No eval kit has a refactoring-mode task, so no paired run could show that a pointer carries the same semantics. Under the diet's rule (nothing is cut to meet a number; a reduction lands only when the same semantics are shown arriving by another path), the cut cannot land. Every other preload is a role's anchor: the planning skill for the writers' `WIP.md` work, `code-review` for the self-review and verification phases, and the crafting skills for the context-engineer and skill-genesis. *Reversal trigger:* a role's kit gains tasks in a preload's mode, or a definition gains a mode switch the spawn prompt names deterministically. Then the move runs as a paired run of that kit.
2. **Near-miss skills are not merged.** The skills docs say the listing always keeps every skill's name and, when over budget, drops descriptions starting with the least-invoked skills, so the most-used keep their full text. The harness already ranks what was meant to be fixed by merging. A merge would also change progressive disclosure and every path that cites the merged skills. *Reversal trigger:* the routing check (`scripts/check_agent_routing.py`) shows a stable confusion between two skills that description wording cannot fix.
3. **No pointer hook and no catalogue search.** No gap is measured. The evidence the diet rests on says model-initiated pull fails at the trigger. Vercel's skill went uninvoked in 56% of runs; Praxion saw 9 `Skill` activations in 67 sessions, none by a subagent. *Reversal trigger:* the same routing check shows a skill's description dropped from the listing in a case it must win.
4. **Domain packs leave the diet** as the candidate next initiative, "the catalogue adapts to the kind of project". The docs now give its mechanisms: a marketplace entry may list specific `skills` directories, a plugin may declare `dependencies` and `defaultEnabled`, and a project's settings enable plugins per project. It is a restructuring of the plugin and the onboarding contract, not a startup-context move, and it is measured by the listing's per-project content, not the always-loaded budget.
5. **The activation manifest gets no scope or trigger columns.** Scope is carried by the rules manifest (`rules/_manifest.yaml`, `install: symlink` against `install: hook-deliver`) together with the project-gating predicate. Trigger is carried by `paths:` frontmatter and the gates. A manifest column would be a second source of truth for both. Cursor has no spawn-start channel, so the audience axis has nothing to export there. With no hooks, the managed process falls back to the constitution plus the project's `CLAUDE.md`, as project gating set out. *Reversal trigger:* a channel gains a trigger that neither `paths:` nor a gate can express.
6. **The ML rules keep their pipeline globs.** They are path-scoped on purpose, so they load where training code is touched. *Reversal trigger:* none; it is closed as by design.

## Considered Options

### Move the implementer's `refactoring` preload behind a pointer now
Rejected. The implementer kit has no refactoring step, so the paired run would pass on tasks that never needed the skill and prove nothing about the steps that do.

### Leave the six items open until a later pass
Rejected. An open item with no plan keeps the diet from finishing, and each item now has evidence enough to decide.

## Consequences

- The roadmap's preload, catalogue and manifest-axis rows close by decision. The final startup probe measures what the diet left in place.
- Domain packs carry the "projects of one kind" scope forward as a separate initiative, with its own intake.
- Each closure names what would reopen it, so the decision is reversible on evidence.
