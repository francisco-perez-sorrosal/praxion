---
id: dec-332
title: TASK_BRIEF obligation enforced by a non-blocking spawn-time advisory, not a gate
status: accepted
category: architectural
date: 2026-08-07
summary: 'Add hooks/remind_task_brief.py — a stderr-only PreToolUse(Agent|Task) advisory that fires when a brief-consuming stage is spawned without a TASK_BRIEF.md — and bind the orchestrator to the canonical document schema when it authors a pipeline artifact itself'
tags: [pipeline, hooks, gate-liveness, intake-clarity-gate, task-brief, orchestrator, always-loaded]
made_by: agent
agent_type: context-engineer
branch: main
pipeline_tier: full
dissent: 'A reminder the orchestrator can ignore may leave the 100% lapse rate untouched, buying a new component and a new maintenance surface for no measured change in compliance.'
affected_files:
  - hooks/remind_task_brief.py
  - hooks/test_remind_task_brief.py
  - hooks/hooks.json
  - rules/swe/swe-agent-coordination-protocol.md
---

## Context

An ecosystem audit measured `TASK_BRIEF.md` absent in **2 of 2** task slugs that carried a `SYSTEMS_PLAN.md` — a 100% lapse rate over the whole eligible population. The Intake Clarity Gate's Standard/Full obligation is written as *unconditional* ("capture `.ai-work/<task-slug>/TASK_BRIEF.md` … unconditionally before the first agent spawn"), but nothing intervened at the moment it applied, so it lapsed silently and completely. The same shape had already been seen once, in the calibration-log append lapse.

Two facts constrain the fix. First, detection already exists: an after-the-fact sentinel check flags the absence, so the ecosystem is not blind — it is just late. Second, the missing brief is what seeds downstream stages and the verifier's rubric, so the obligation is not ceremonial and downgrading it to "capture when useful" would quietly weaken verification.

A sibling finding in the same audit established a second instance of the same defect class from the other direction: a pipeline where no architect was ever spawned, and the orchestrator wrote `SYSTEMS_PLAN.md` itself under a bespoke schema. No agent violated its contract; the contract simply never bound the orchestrator. Both are *obligations that bind nobody in exactly the case where they matter most*.

## Decision

**Add a non-blocking advisory at the moment the obligation applies, and keep the existing after-the-fact check as the durable backstop.**

`hooks/remind_task_brief.py` registers on `PreToolUse(Agent|Task)`. When the spawned `subagent_type` is a brief-consuming pipeline stage (`systems-architect`, `implementation-planner`), the prompt carries a `Task slug: <slug>`, and `.ai-work/<slug>/TASK_BRIEF.md` does not exist, it writes one advisory line to stderr and exits 0.

It is advisory by construction, three independent ways:

1. **It never writes stdout.** `inject_subagent_context.py` is the single `updatedInput` emitter registered on this same matcher, deliberately consolidated from two hooks because whether the harness chains multiple `updatedInput` emissions was an unverified assumption. A hook that cannot write stdout cannot reintroduce that contention.
2. **It exits 0 unconditionally**, including on internal error. The harness treats any PreToolUse exit other than 2 as approval.
3. **It never emits `permissionDecision`** — no deny, no ask.

Separately, the orchestrator is bound to the canonical document schema in `rules/swe/swe-agent-coordination-protocol.md § Delegation Checklists`: when it authors a pipeline artifact itself rather than spawning its owning agent — legitimate at any tier — **the schema binds the path, not the author**. The remedy is stated alongside the prohibition: write that agent's canonical section skeleton, or pick a filename it does not own. This sits in the delegation section because that is where an orchestrator deciding *not* to delegate is already reading, and it references the obligation rather than restating the section list, whose single source of truth is the owning agent's own definition.

### Scope of the trigger set

Narrower than "every agent that reads the brief", on purpose. The verifier consumes it, but a reminder at verification time cannot be acted on — the pass is already applying the rubric the brief would have seeded. The implementer and test-engineer fan out N-wide on one plan, so reminding there would emit N stderr lines for a single lapse. The two chosen stages are the earliest deterministic Standard/Full signal and the last point at which writing the brief still changes a downstream artifact. They also match the measured eligible population exactly (slugs carrying a `SYSTEMS_PLAN.md`).

## Considered Options

### A. Hard block — refuse the first agent spawn without a brief (rejected)

**Pros:** compliance becomes structural rather than probabilistic.

**Cons:** the hook cannot know the tier, and tier is the entire precondition. A wrong guess strands the user at the start of a pipeline, with no obvious escape and the failure landing on the highest-friction surface there is. A gate that refuses work on an inference it cannot make is worse than the lapse it prevents.

### B. Add a second detector (rejected)

**Pros:** cheap; no new component.

**Cons:** the ecosystem already detects this. A second detector reports the same lapse twice and still reports it after the fact. Nothing about the timing changes, which is the only thing that was wrong.

### C. Downgrade the obligation from unconditional to conditional (rejected)

**Pros:** honest — a rule complied with 0% of the time is not a rule, and silent 100% non-compliance is the worst of both.

**Cons:** on reading, the unconditional form *was* justified: the brief seeds every downstream stage and the verifier's rubric, so making it conditional makes the rubric conditional. The evidence shows the obligation was never *surfaced*, not that it was never *warranted* — two slugs is also a thin basis on which to weaken a verification input.

### D. Non-blocking advisory at the moment of the lapse, detector retained (chosen)

**Pros:** intervenes at the only point where the correction is free; costs nothing on the compliant path (silent when the brief exists); the durable backstop is untouched; a kill switch (`PRAXION_DISABLE_TASK_BRIEF_REMINDER`) exists for anyone who disagrees.

**Cons:** advisory, therefore ignorable. Adds a component and a maintenance surface. The trigger set is a proxy for tier, not tier itself, so a Lightweight run that spawns an architect will see a spurious line.

## Consequences

**Positive.** The obligation now has an intervention at the moment it applies, not only a report after the fact. The compliant path is silent and costs one `stat`. The stdout-empty invariant is asserted in tests, so the single-`updatedInput`-emitter property of this matcher is now protected by a test rather than by convention. The orchestrator-authored-artifact case is bound for the first time, closing the sibling half of the same defect class.

**Negative.** A new hook module to maintain, and a second registration on a matcher that was deliberately consolidated to one hook — mitigated by the stdout-empty construction, but the registration count did grow. The trigger set proxies for tier and will occasionally misfire. Compliance remains voluntary; if the lapse rate does not move, this decision bought a component for nothing (see `dissent`).

**Neutral.** No always-loaded tokens were spent describing the hook. Its existence is discoverable from this record, from `hooks/hooks.json`, and from the advisory itself when it fires; a session that never spawns an architect never needs to know it exists.

## Disconfirmation

**Falsifier.** The next audit measures the `TASK_BRIEF.md` lapse rate over eligible slugs and it has not fallen. If the advisory fires and the brief still is not written, the diagnosis "the obligation was never surfaced" was wrong, the real cause is that the orchestrator does not value the brief, and the correct move is option C — downgrade the obligation honestly — not a stronger gate.

**Steelmanned runner-up.** Option C is stronger than it first appears. A 100% lapse rate is the loudest possible evidence that an obligation is not carrying its weight, and the ecosystem's own principle is that process can be added later but overhead cannot be reclaimed. If two more slugs land with no brief and no downstream stage is observably worse for it, the honest conclusion is that the unconditional form was aspirational and the conditional form is true.

**Reversal trigger.** Two consecutive audits showing no improvement in the lapse rate; or any report of the advisory firing on a Lightweight run, which would show the trigger set is a bad tier proxy and should be replaced by an explicit tier signal in the spawn prompt rather than an agent-name inference.
