---
id: dec-437
draft_id: dec-draft-533770d5
title: The step-loop relay procedure is the skill skills/step-loop/SKILL.md, invocable by the user and the model, never a command
status: accepted
category: architectural
date: 2026-10-07
summary: The orchestrator's relay procedure for the step-loop driver lands as skills/step-loop/SKILL.md (/praxion:step-loop <task-slug>, user- and model-invocable, slug through $ARGUMENTS, narrow allowed-tools, a description of about 25 tokens), named in the coordination protocol's Plan ready bullet; commands/step-loop.md is never created, and the driver's stop and handoff text names the skill. Narrows dec-432's clause naming the procedure a command; the rest of dec-432 stands.
tags: [step-loop, skill, command, relay, orchestrator, plan-ready, listing-budget]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-dogfood
pipeline_tier: full
affected_files:
  - skills/step-loop/SKILL.md
  - skills/README.md
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/_manifest.yaml
  - scripts/_step_loop_render.py
  - .ai-state/DESIGN.md
affected_reqs: [REQ-05, REQ-06, REQ-07]
supersedes_in_part: [dec-432]
dissent: []
---

## Context

dec-432 placed the orchestrator's relay procedure, which runs `next`, executes the request unchanged and calls `record`, in `commands/step-loop.md`, and made it model-invocable. The command was never built: it moved to this pipeline with the split. Since then:

- The user ruled on 2026-10-07 that a loop entry is never a command ("commands have been deprecated even in Claude Code in favor of skills").
- dec-434 bound that ruling for the goal mode's own entry.
- The live skills documentation, read raw on 2026-10-07, says "custom commands have been merged into skills".

A skill gives every property the command was chosen for. `/praxion:step-loop <slug>` is user-invocable, and the model can invoke it unless `disable-model-invocation` is set. The typed slug reaches the body through `$ARGUMENTS`. A skill also offers what a command cannot: `allowed-tools` scoped to the invoking turn, and a directory for supporting files.

**Activation:** no. A family move of one Markdown component; the two options do the same work, and the user has already ruled.

## Decision

1. The relay procedure is `skills/step-loop/SKILL.md`. Frontmatter:
   - `name: step-loop`;
   - a one-line `description` of about 25 tokens (the listing ceiling leaves 99);
   - `argument-hint: "<task-slug>"`;
   - a narrow `allowed-tools`: the Agent tool, Read, and the driver's two invocations.

   There is no `disable-model-invocation`, no `user-invocable: false`, no `arguments:` and no `when_to_use`. The body takes the slug through `$ARGUMENTS`, cites no identifier and states no numeric attempt cap.
2. The body is the relay procedure only:
   - an exit-code table, the `not-driven` hand-back, and the marker vocabulary;
   - five relay rules: pass the spawn request to the Agent tool unchanged; call `record` only after the completion notification; relay the request id, the agent id and the marker; never edit the rendered prompt; never commit;
   - three prohibitions: never compose an implementer prompt, never read the rendered prompt, never edit an `Attempts:` line;
   - a link to the spawn-budget procedure.

   The driver's contract stays in its module docstring and `--help`.
3. The coordination protocol's "Plan ready" bullet names `/praxion:step-loop <slug>` as the way implementer steps run.
4. The driver's stop and handoff text names the skill.
5. No `commands/step-loop.md` exists.

## Considered Options

### Option 1 — Skill (chosen)
- **Pros:** the user's ruling and the vendor's current guidance; user- and model-invocable under one name; the bare `/step-loop` also works when no command takes it; a turn-scoped tool grant; consistent with the goal mode's skill entry, so the loop's two entries live in one family.
- **Cons:** the description counts against the listing ceiling. Since a tool grant clears at the user's next message, a user interjection mid-loop re-prompts for permission.

### Option 2 — Command as dec-432 wrote it
- **Pros:** it was already designed; an identical body.
- **Cons:** contradicts the user's ruling and the vendor's direction; a second family for the loop's entries once goal mode lands as a skill.

### Option 3 — No invocable entry; prose in a planning reference read by path
- **Pros:** zero listing cost.
- **Cons:** the model cannot discover it where it decides how steps run; the "Plan ready" bullet would point at a file, not an action.

## Consequences

**Positive:** one family for every loop entry; the orchestrator reaches the procedure by name from the always-loaded bullet; the slug is substituted rather than typed into prose.

**Negative:** about 25 listing tokens. A session that loads an older installed plugin does not list the new skill. This is the case for the session that builds it: the building orchestrator reads the file by path, and a nested `--plugin-dir` session proves the invocation live. The stop text's one unit pin changes, as a named pure-text exception.

## Disconfirmation

- **Falsifier:** in this pipeline's live check, the typed slug does not reach the skill body, or the model does not list `praxion:step-loop`. Or, over the next two pipelines, the orchestrator enters the loop without the skill (it composes the relay from memory or from the planning references).
- **Steelmanned runner-up:** Option 3. The orchestrator is the only consumer and enters the loop once per pipeline, so a referenced procedure costs nothing in the listing, a budget with 99 tokens left. Invocability buys little when the "Plan ready" bullet already names the file.
- **Reversal trigger:** if the live check shows the slug dropped or the skill hidden on the harness in use, and a frontmatter correction does not fix it, move the body to a planning reference and make the bullet name the path.

## Prior Decision

dec-432 is narrowed in one clause. Clause 1's last sentence ("the loop procedure is `commands/step-loop.md`") and clause 7's naming of the procedure as `/step-loop <slug>` now read: the procedure is the skill `skills/step-loop/SKILL.md`, invoked as `/praxion:step-loop <slug>`, still model-invocable. The rest of dec-432 stands unchanged: the driver and its three verbs, the pure core and the I/O shell, no private state, the hand-back of steps outside the loop, the stops and their handoffs, the spawner seam, and the echoed invocation.
