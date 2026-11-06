---
id: dec-draft-276d3f8c
title: "Adherence kit modes: declared by the template, read back from the task's identity"
status: proposed
category: implementation
date: 2026-11-06
summary: "A writer role's kit tasks carry a mode declared in each template's manifest, held on TaskSpec and TaskFacts, printed on the dry-run line, resolved by the grader from the task's slug and by the report from the recorded template id; no prompt is re-parsed."
tags: [eval, adherence, kits, test-engineer, systems-architect]
made_by: agent
agent_type: systems-architect
branch: lean-writers
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/model.py
  - eval/src/praxion_evals/adherence/tasks.py
  - eval/src/praxion_evals/adherence/role_kits.py
  - eval/src/praxion_evals/adherence/grade.py
  - eval/src/praxion_evals/adherence/cli.py
  - eval/src/praxion_evals/adherence/report.py
---

## Context

The test-engineer's and the systems-architect's full kits must cover each mode carrying at least 20 percent of the role's spawns: acceptance design and paired test writing for the test-engineer, spec and feature for the architect. A switch sets `omitClaudeMd` on the whole definition, so a flip measured in one mode would switch the others unmeasured. The dry run must name each task's mode, the role checks of one mode must not bind on another, and the report must state a flip claim's per-mode coverage. The bound acceptance drivers fix three facts. Each dry-run line carries `"mode"`. A results file names a mode only through the session's task id and template id. A grader receives a recorded envelope whose spawn prompt carries no mode directive, plus the task's slug.

## Decision

The mode is a property of the template. Each template's `template.toml` declares `mode`, which is parsed once into the closed `KitMode` literal. `ROLE_MODES` names each moded role's covered and unmeasured modes. `MODED_KITS` holds one existing-shape `RoleKit` (brief, prompt, fixture inputs) per covered mode, so the existing paired and feature prompts are reused verbatim.

Kit load enforces three invariants: every template of a moded role declares a covered mode, every covered mode has at least two templates, and every mode shares the role's fixtures and overlays. `TaskSpec.mode` and `TaskFacts.mode` carry the value; `TaskFacts` is the grader's only task input. `evidence_from_recording` fills it from `tasks.mode_of_slug(role, slug)` with its signature unchanged. The report resolves `tasks.mode_of(role, setup.template_id)`. A new gate, `in_task_mode`, decides both a check's binding and its outcome from `TaskFacts.mode`.

## Considered Options

- **Template manifest plus task identity (chosen).** One declared source, invariants at load, and a binding decidable from facts.
- **Re-parse the spawn prompt (extend `in_mode`).** Rejected: the recorded envelopes the bound driver grades carry a generic prompt with no directive, and a live prompt is the relayed copy of a fact the eval already holds.
- **Encode the mode as a template-id prefix.** Rejected: stringly-typed knowledge in a naming convention, and the existing templates would be renamed, changing their task ids.

## Consequences

- The grader now depends on the kit (`grade` asks `tasks` for a mode).
- A session whose template a later kit no longer holds reads as mode-unknown and counts under no covered mode.
- The results file and the task-id shape are unchanged, and the dry-run line gains one additive key.
- The researcher's, implementer's and verifier's kits, task ids and checks are untouched; the prompt-based `in_mode` stays for the parallel-mode checks.
