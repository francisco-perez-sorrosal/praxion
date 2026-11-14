---
id: dec-draft-e1541d69
title: "The refactoring skill reaches a marked spawn through the single prompt-rewrite emitter, not a preload"
status: proposed
category: architectural
date: 2026-11-14
summary: "A new hook-side delivery module decides per Agent call whether a delegation to the implementer or test-engineer carries the refactoring phase marker in its own words (or is a step-loop request for a tagged step) and, when the role's definition no longer preloads the skill, the single PreToolUse emitter appends the skill body as one labelled block; the marker grammar stays in the plan reader, which the module re-exports; the preload's removal is a held, reversible move."
tags: [refactoring, skill-delivery, preload, spawn, hooks, updated-input, step-loop, startup-context]
made_by: agent
agent_type: systems-architect
branch: feat-refactoring-delivery
pipeline_tier: standard
affected_files:
  - hooks/_skill_delivery.py
  - hooks/inject_subagent_context.py
  - hooks/_observation_log/registry.py
  - scripts/_plan_steps.py
  - scripts/refactoring_move.py
  - agents/implementer.md
  - agents/test-engineer.md
  - skills/software-planning/references/coordination-details.md
  - skills/software-planning/phases/refactoring.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-21]
supersedes_in_part: [dec-504]
---

## Context

The implementer and the test-engineer preload `skills/refactoring/SKILL.md` on every spawn. Its body measures 4,184 tokens on the current ruler, over 557 implementer and 95 test-engineer spawns in 90 days. Only a delegation of a step tagged `[Phase: Refactoring]` needs the skill. `dec-504` kept every preload because no kit could show that a lighter delivery keeps the semantics, and its reversal trigger is "a definition gains a mode switch the spawn prompt names deterministically; then the move runs as a paired run of that kit". The user decided a deterministic push, not a pointer, and named the `SubagentStart` channel the kernels use, subject to first verifying that the spawn payload carries what is needed to see the marker.

The hooks reference (read 2026-11-13) settles that verification negatively. `SubagentStart` input has no delegation text. `PreToolUse` on the Agent tool sees `tool_input.prompt`, and its `updatedInput` replaces the call's input. Praxion already rewrites the prompt there, through one emitter (`dec-266`), and the rewrite is observed reaching the spawn's first turn. The documented 10,000-character cap names `additionalContext`, `systemMessage`, `initialUserMessage` and plain stdout; "for JSON output, each field is measured separately", and `updatedInput` is not named. The block is about 12,100 characters; no recorded rewrite exceeds 7,834.

## Decision

1. **A new component, `hooks/_skill_delivery.py`, owns the delivery decision.** It holds:
   - the marker grammar, as a re-export (`MARKER_PATTERN`) of its single definition, which stays in the plan reader `scripts/_plan_steps.py` as `REFACTORING_TAG_PATTERN`. That is plan-heading grammar, and the plan reader's pinned purity forbids it any new import. The module imports it through `<CLAUDE_PLUGIN_ROOT>/scripts`. If that import fails, the interim is unaffected (the preload check comes first) and every end-state spawn of the two roles fails loudly as `grammar-unavailable`: a notice, a `failed` row and stderr, never a second copy of the grammar;
   - the classifier: the marker in the delegation's own words, outside code spans, fenced blocks and block quotes, or a step-loop pointer whose rendered request's `<step>` heading carries the marker;
   - the preload-state reader: the role's own `skills:` list in the same installation;
   - the block renderer, the failure notice, the arrival matcher and the `skill_delivery` observation row.
2. **The single emitter `hooks/inject_subagent_context.py` gains a trailing segment slot.** For a marked spawn of either role whose definition does not preload the skill, it appends the skill body as one passage. The body is framed by a label carrying its digest and by a `Base directory for this skill:` line, so its links resolve against the installation the body came from. It is still one `updatedInput`, and every other role and every unmarked spawn is untouched.
3. **The delivery is silent while a definition preloads the skill.** The move is two `skills:` entries plus the state-dependent definition sentences, applied by a bidirectional, drift-refusing move tool (`scripts/refactoring_move.py`). It is held as the plan's last step until a user-approved paired run shows the semantics arrive.
4. **Failures fail open and are never silent.** No refusal ever. A notice segment where the input parsed, a `failed` row where a log serves the project, and a stderr line.

**Activation:** fired. A load-bearing structural choice under honest uncertainty: the size limit of a rewritten prompt is undocumented and unobserved above 7,834 characters.

## Considered Options

### Option 1: `SubagentStart` `additionalContext`, as item E1 names it

Pros: a documented 10,000-character cap per string; the kernel slot machinery; a system-reminder slot like other start-time context; the harness re-injects only when absent on a resume. Cons: it cannot see the marker. Both ways to give it the marker are non-deterministic:
- A `PreToolUse` note has no documented shared key with `SubagentStart` (`tool_use_id` against `agent_id`), and same-role spawns fan out N-wide.
- Reading the spawn's own first message from its transcript at start time depends on undocumented flush timing.

The body would also need two strings whose arrival order across parallel slots is not guaranteed.

### Option 2: a trailing segment in the single prompt-rewrite emitter (chosen)

Pros: it sees the delegation; it is decided per call, so it is concurrency-safe; the channel is shipped and observed; it keeps one emitter. Cons: the undocumented size limit (handled below); the text arrives inside the first user turn, not as its own message; the delegation and the block are compacted together.

### Option 3: a second `updatedInput` emitter

Rejected. How the harness combines several emissions is undocumented, which is why `dec-266` made one emitter.

### Option 4: a pointer the model follows

Rejected by the user and by `dec-504` (3): "model-initiated pull fails at the trigger".

## Consequences

Positive:
- Every unmarked spawn of the two roles saves at least 4,184 tokens once the move lands, and a marked spawn still holds one whole copy.
- The marker has one definition, the plan reader's, shared by the delivery.
- The step-loop driver's pinned three-line prompt is untouched.
- The interim merges with no change to any real spawn.

Negative:
- The delivery knows the driver's pointer grammar and its `<step>` element. That coupling is tested against the driver's own golden fixture.
- A hand delegation that omits the marker is not served (an accepted residual).
- One more file read per marked spawn.
- The skill text shares the first turn's compaction exposure.

## Disconfirmation

- **Falsifier:** in the size probe or the paired run's delivered arm, the spawn's own first user message does not hold the label line and the whole body. That means the harness capped, truncated or dropped the rewritten prompt. This design is then wrong for a 12 KB block.
- **Steelmanned runner-up:** `SubagentStart` delivery reading the spawn's own first message from `<session>/subagents/agent-<agent_id>.jsonl`, through `hooks/_agent_transcript.py`'s `first_user_text`.
  - It is keyed by `agent_id`, so it is unique per spawn and concurrency-safe.
  - It delivers two labelled strings, each under the documented 10,000-character cap, split at a section heading so each half is coherent whatever its order.
  - It honours the user's named channel exactly, never touches the delegation text, and survives resume by the harness's absent-only re-injection.
  - Its one premise, that the first message is filed before `SubagentStart` fires, can be checked at $0 from recorded transcripts and observation rows.

  If that premise holds and the prompt limit bites, it is the better design.
- **Reversal trigger:** the size probe or the delivered arm's proof fails on the length of the rewritten prompt. Or Claude Code documents an `updatedInput` limit below the block's length. Then keep the move held, check the runner-up's flush premise at $0, and if it holds, move the trailing segment to a `SubagentStart` delivery with two labelled parts. The classifier, preload reader, renderer and matcher carry over unchanged.

## Prior Decision

`dec-504` (accepted, behavioral) closed the diet's preload item: "Agent skill preloads stay as each role's anchors". This record narrows that clause for **one preload only**: `refactoring` in the implementer and the test-engineer, once the move lands. Clauses that survive unchanged:
- every other preload of every role;
- the rule that a reduction lands only when the same semantics are shown arriving by another path, which is why the move is held behind the paired run;
- the rejection of pointer hooks and catalogue search;
- the domain-packs, manifest and ML-glob items.

`dec-266` (one `updatedInput` emitter) is applied, not changed.
