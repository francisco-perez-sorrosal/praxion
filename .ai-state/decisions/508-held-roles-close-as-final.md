---
id: dec-508
draft_id: dec-draft-91210371
title: "The four held lean-spawn roles close as final: the verifier, context-engineer, discipline-consultant and skill-genesis keep the full arm"
status: accepted
category: behavioral
date: 2026-11-11
summary: "The startup-context diet's last role item closes without a flip. The verifier stays held because no affordable run can be decisive on the forced-stop check that twice leaned against the lean arm, and it is the pipeline's quality gate. The context-engineer, discipline-consultant and skill-genesis stay held because each needs a full eval kit and a paired run that would cost more than its spawn volume saves within a year. All four already receive the spawn split, and each names the evidence that would re-open it."
tags: [startup-context-diet, finish-line, lean-spawns, kernel-adoption, held-roles, verifier, managed-projects]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - .ai-state/kernel_adoption.yaml
  - agents/verifier.md
  - agents/context-engineer.md
  - agents/discipline-consultant.md
  - agents/skill-genesis.md
affected_reqs: []
---

## Context

The diet's finish line item 6 reads: close the verifier and the low-volume roles by recorded decision, after measuring the preloaded-skills roster (done in dec-504). Eight roles were eligible for the lean arm (the kernel plus `omitClaudeMd`). Four are switched on a passing paired run each: the researcher, implementer, test-engineer and systems-architect. Four are `held` in `.ai-state/kernel_adoption.yaml`: a trial closed without a flip, which injects nothing and keeps the full arm.

Evidence read on 2026-11-11, at $0:

- **Spawn volume, 90 days** (observation log): verifier 211, context-engineer 33, skill-genesis 15, discipline-consultant 9. The switched roles: implementer 557, test-engineer 95, systems-architect 53, researcher 35.
- **What the full arm costs now.** Since v0.60.0 (dec-495) every inheriting `praxion:` spawn, held roles included, receives the coordination protocol and the intermediate-documents rule without their orchestrator-only spans. The verifier's first request fell 67,876 → 62,169 tokens on the probe. That part of the saving is already landed for all four, with no adherence risk.
- **What a flip would still save.** The verifier's run 20261031T203813Z-47ce6d read a lean first-request median of 40,902 against 54,776 for the full arm, before the split. That is roughly 8,000–14,000 tokens per spawn now, most of it cache reads. The context-engineer's smoke run read 38,509 against 57,143, before the split. The three low-volume roles together spawn about 57 times per 90 days, so a flip would save about 0.6–0.8M tokens a quarter between them.
- **What deciding would cost.**
  - The verifier has two full runs (`03a785`, `47ce6d`). Both leaned the same way on C5, the forced-stop `[PARTIAL]` title: b 6 c 0, then b 5 c 1. The second run passed only its three scored checks, with golden judge error 0.50. A run is decisive on C5 only at zero discordant pairs, and the $0 power check of 2026-11-02 found that unlikely. Its estimated session cost was 77.11 per run on the subscription.
  - The other three have smoke kits only: 4 templates and 3 runnable tasks, so no run reaches the 20 complete pairs a flip needs. Each needs a full kit built first. lean-writers built two such kits as a Full pipeline with 10 charged spawns. Each then needs a paired run: 25–82 on the subscription, going by the writers' runs.

## Decision

The four roles stay `held` as their final state for this diet. No trial re-opens, and no kit is built for them.

1. **The verifier keeps the full arm.** It is the pipeline's last quality gate, and its two runs both leaned against the lean arm on a check of how it ends under a forced stop. A third run cannot be decisive at an affordable size. Under the diet's rule (nothing is cut to meet a number), a saving that cannot be shown to keep the role's behaviour does not land.
   *Reversal trigger:* both of these hold:
   - C5 can tell a finished report cut off before its return from an unfinished one;
   - a $0 power check shows that a 24-pair run can be covered at the observed discordance.

   Or the verifier's 90-day spawn count doubles past 420.
2. **The context-engineer, discipline-consultant and skill-genesis keep the full arm.**
   - What one would buy: 9 to 33 spawns a quarter, about 13,000 tokens each, mostly cache reads.
   - What deciding would cost: a full kit (a pipeline) and a paired run per role.
   - So the decision pays back in more than a year, against an open adherence risk.

   *Reversal trigger:*
   - a role's 90-day spawn count passes 100;
   - or kits become cheap to build, at about one spawn per role, so a run costs less than a quarter of the saving.

   Either way, that role re-opens as a trial under dec-462.

## Considered Options

### Build full kits for the three low-volume roles and run them
Rejected. About 30 spawns and three paired runs, for about 0.7M cache-read tokens a quarter. The spawn split already gave those roles the part of the saving that needed no adherence evidence.

### Re-open the verifier for an early-stop re-measure with kept sandboxes
Rejected. The measured direction held across two runs, and the check that decides it cannot tell the case the runs need told apart. A run that cannot be decisive spends the subscription and leaves the role where it is.

### Leave the roles held with "a full kit comes before any new trial"
Rejected. An open item with no plan keeps the diet from finishing, and the reasons in the ledger read as owed work that no one will schedule.

## Consequences

- The diet's lean-spawn item closes with four roles switched and four held. `kernel_adoption.yaml` records the closure beside the held records, so a later reader finds the reversal triggers rather than an owed kit. No record or status changes.
- The held roles keep receiving the spawn split. A split change still reaches them through the I11 gate.
- The smoke kits for the three low-volume roles stay as they are. They are instruments for a re-open, not owed work.
