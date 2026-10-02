---
id: dec-421
draft_id: dec-draft-65e11d84
title: A step tagged mutation on completes only on a mutation reading; the step-completion reconciler owns the block and the step-document schema owns the Mutation line
status: accepted
category: architectural
date: 2026-10-01
summary: "The Mutation: line grammar moves into scripts/_step_schema.py (MutationReading sum type, parse/render, DECLARED_LIMIT_REASONS = {not-flat-layout}, mutation_block_reason); the sensor renders through it. reconcile_pipeline_state.py scans the plan's mutation: on|off tag and reports a new blocked verdict (exit 2) for an otherwise-done tagged step whose latest run has no line, an unreadable line, or a refusal other than not-flat-layout. The writer returns [BLOCKED], /resume-pipeline surfaces it and never auto-marks, and the verifier grades it FAIL. This narrows dec-388's 'a refusal is recorded, never a failure' disposition"
tags: [mutation-sensor, step-completion, reconciler, step-schema, verifier, gate]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-liveness-prod
pipeline_tier: standard
affected_files:
  - scripts/_step_schema.py
  - scripts/mutation_sensor.py
  - scripts/reconcile_pipeline_state.py
  - commands/resume-pipeline.md
  - agents/verifier.md
  - agents/implementer.md
  - agents/test-engineer.md
  - skills/software-planning/references/agent-pipeline-details.md
  - skills/software-planning/references/decomposition-guide.md
  - skills/testing-strategy/references/python-testing.md
affected_reqs: [REQ-10, REQ-11]
supersedes_in_part: [dec-388]
---

## Context

dec-388 made the mutation sensor "a sensor, never a gate". A refusal (`Mutation: unavailable reason=<code>`) was recorded with no finding, and a tagged step with no line drew an advisory WARN. When the suite went parallel, every sensor run refused with `run-failed` for four days, and every tagged step passed. REQ-10 (orchestrator intent, with a spec resume) makes a missing reading and every refusal except the declared `not-flat-layout` limit block the step. REQ-11 keeps `not-flat-layout` and untagged steps exactly as before.

Three components read the line: the sensor (producer), the step gate and the liveness probe. No script parsed it before this change; only an LLM verifier did. BA-02 fixes the judgment's boundary: given a checkout's plan, `WIP.md`, `TEST_RESULTS.md` and a base ref, report whether a step may complete and, if blocked, name the step and the reason or the missing line. That is exactly the input set and the question of `scripts/reconcile_pipeline_state.py`.

**Activation:** no. A single enforcement point is chosen among three researched options, and the consequences are contained to pipeline documents.

## Decision

- **Grammar owner: `scripts/_step_schema.py`** (extending dec-393's one step-document schema module). It provides:
  - the `MutationReading` sum type: `MutationRan`, `MutationRefused` (an open reason set, so an unseen code still blocks) and `MutationMalformed`;
  - `parse_mutation_line` and `render_mutation_line`;
  - `DECLARED_LIMIT_REASONS = frozenset({"not-flat-layout"})`;
  - `step_mutation_reading` (the step's own latest block wins);
  - `mutation_block_reason`, the single policy function.
  The sensor renders through it. Pinning tests hold the sensor's golden lines.
- **Enforcement point: the reconciler.** It scans each step's `mutation: on`/`off` line. An otherwise `verified-complete` tagged step whose reading blocks becomes the new `blocked` verdict. Its evidence starts `Step <id>:`, and exit 2 now means "unknown or blocked: needs a decision".
- **Readers**:
  - The canonical `TEST_RESULTS.md` writer (implementer or test-engineer) leaves the checkbox unflipped and returns `[BLOCKED]`, so the completion handshake does not advance.
  - `/resume-pipeline` surfaces `blocked` and never auto-marks it.
  - The verifier runs the reconciler and grades `blocked` as FAIL.
- **The shape checker is unchanged.** A refusal line is well formed, and a block is a completion fact.

## Considered Options

### Option 1: producer-prompt `[BLOCKED]` only

- **Pro**: two prompt sentences.
- **Con**: an LLM-interpreted gate relying on the same writer that copied the dead line for four days. It cannot be canaried mechanically, and BA-02 needs a mechanical judgment.

### Option 2: a shape-checker finding in `check_test_results_shape.py`

- **Pro**: deterministic and already in the verifier's path.
- **Con**: it takes only `FILE` arguments and would need the plan; the verifier treats its findings as advisory; and "blocked" is not a shape property. A well-formed refusal line would become "malformed" in a shape tool.

### Option 3: a reconciler verdict plus the writer `[BLOCKED]` plus a verifier FAIL (chosen)

- **Pro**: one deterministic judgment shared by three readers; reuses the plan and test-result parsing the reconciler already does; fits `/resume-pipeline`.
- **Con**: the reconciler, a truncation-recovery reader, gains a test-evidence condition (about +40 lines), and exit 2 widens.

## Consequences

**Positive**:

- A refusal or a missing line can no longer pass a tagged step silently.
- The grammar has one owner and pinned producer and consumer tests.
- Untagged pipelines pay nothing.

**Negative**:

- An environment problem (`toolchain-missing`, an offline `run-failed`) now stops a tagged step until a human or a re-run resolves it. That is the intended cost.
- Six prompt and reference documents change, and `docs/architecture.md` follows when the change is built.

## Disconfirmation

- **Falsifier**: in the first ten tagged steps after merge, at least half are blocked by environmental refusals (`toolchain-missing`, `run-timeout`) that a re-run clears without any code change. The block would then be training people to re-run, not surfacing dead readings.
- **Steelmanned runner-up**: only the writer's `[BLOCKED]`, with the verifier FAIL as the mechanical backstop. That gives a smaller blast radius and no change to the reconciler's exit-code meaning. It loses because BA-02 needs a mechanical, per-step judgment that `/resume-pipeline` can act on between agent spawns, and the verifier runs only once, at the end.
- **Reversal trigger**: if the falsifier fires, add bounded automatic re-run of environmental refusals (one retry, recorded) before the block. Do not retire the block.

## Prior Decision

dec-388 decided the sensor is "a sensor, never a gate": `unavailable` recorded with no finding, and a tagged step with no line a WARN, advisory during rollout. This decision **narrows** that clause only for steps tagged `mutation: on`. Every refusal except `not-flat-layout`, and a missing or unreadable line, now blocks the step. The sensor itself is unchanged: it still exits 0 on any completed run and 2 on a refusal, and it still never fails on survivors. dec-388's runner, recipe, line shapes and planner tag all stand.
