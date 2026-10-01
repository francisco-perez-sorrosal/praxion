---
id: dec-draft-5c302933
title: A stdlib footprint check script and an optional per-project footprint registry own the criteria grammars and the trigger
status: proposed
category: architectural
date: 2026-10-01
summary: "New CODE gate scripts/check_footprint_criteria.py (stdlib, 3.9-safe, stages spec|plan|verify, findings FP01-FP05) is the single owner of the spec-table, registry and measurement-log grammars; new optional .ai-state/FOOTPRINTS.md maps footprint classes to path globs and instruments so the trigger is a mechanical path-class match at plan and verify time; instruments stay measure-only, the check owns validity and freshness, the verifier owns the value-vs-limit grade; no registry and no tables means inactive, exit 0"
tags: [footprint, quantitative-criteria, gate, registry, verifier, spec-driven-development, managed-projects]
made_by: agent
agent_type: systems-architect
branch: worktree-quant-acceptance-criteria
pipeline_tier: standard
affected_files:
  - scripts/check_footprint_criteria.py
  - scripts/test_check_footprint_criteria.py
  - .ai-state/FOOTPRINTS.md
  - scripts/artifact_registry.py
  - skills/software-planning/references/artifact-inventory.md
  - agents/verifier.md
  - agents/implementation-planner.md
  - agents/systems-architect.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06]
---

## Context

REQ-04 and REQ-05 need a mechanical answer to "did this change move a footprint?". REQ-04 says a moved footprint must not pass unnoticed; REQ-05 says a footprint-free change must pay nothing. At spec time no diff exists. At plan time the steps' `Files` exist, and at verify time the diff does.

The existing instruments (`measure_selection_size.py`, `measure_token_budget.py`, `check_agent_prompt_size.py`) report numbers. None of them takes a per-change threshold, and only one compares against a reference revision. Three formats need one owner each, so that parallel implementation lanes cannot drift:
- the spec's criterion tables;
- a path-class registry;
- a measurement log.

The feature ships to managed projects. A project with no registry and no criteria must keep exactly today's behavior.

## Decision

- **New component, `scripts/check_footprint_criteria.py`.** Stdlib-only and 3.9-safe, git-rooted, exit codes 0, 1 and 2, with a `--json` envelope.
  - It is the sole parser of the spec tables, `.ai-state/FOOTPRINTS.md` and `.ai-work/<slug>/MEASUREMENTS.md`. The normative grammar lives only in its docstring.
  - Stages: `spec` (grammar), `plan` (plus FP01 over `--paths`), and `verify` (plus FP01 over the diff, and FP03 measurement validity and freshness).
  - It never executes the commands named in the tables or the registry.
- **New component, `.ai-state/FOOTPRINTS.md`.** An optional per-project registry: Footprint, include and `!`exclude globs, Command or `none`, Reading. Praxion carries its own instance. Onboarding ships none, and the check treats absence as a legal state.
- **Pass/fail split.**
  - The instruments measure and are unchanged.
  - The check decides whether each measurement is present, fresh, comparable and from the right command.
  - The verifier grades value against limit.

## Considered Options

### Check script plus optional registry (chosen)

- **Pros:**
  - One owner per grammar.
  - The trigger is mechanical where the requirements need it.
  - No-op by absence.
  - The extract and the instruments are untouched.
  - Managed projects opt in with one file.
- **Cons:**
  - Coarse path classes over-trigger.
  - A third list of the resolver sources, which needs a drift test.

### Prompt-only: the verifier reads the diff and judges

- **Pros:**
  - No new script.
  - Can use judgment about whether a change really moves a footprint.
- **Cons:**
  - It is the same LLM-attention failure that let the 36%-to-82% move through.
  - Not mechanical, so it does not satisfy the trigger constraint.
  - No plan-time detection.

### Extend `extract_spec.py` and the sentinel dispatch table

- **Pros:** reuses the spec-time gate the architect already runs.
- **Cons:**
  - Couples spec-time linting with verify-time diff and measurement data.
  - Puts the 236 byte-identity guards at risk.
  - The sentinel table is prompt-readable only.

### Threshold flags on the instruments (`--max`)

- **Pros:** a mechanical pass/fail at the source.
- **Cons:**
  - Limits are free text, per criterion and often relative to a baseline.
  - Three instruments would gain duplicated comparators.
  - Their existing consumers would change.

## Consequences

**Positive:**
- REQ-04 and REQ-05 rest on a path-class match, not on attention.
- An omitted footprint is caught at plan time as a Spec Question.
- A measurement taken before a later change to the footprint's paths is detected as stale.

**Negative:**
- A new CODE gate to keep alive. It needs canaries, plus GL04 (invoked from the verifier, planner and architect prompts), GL05 and GL06.
- A new `.ai-state` artifact to document as `optional-lazy`.
- False-positive FP01 warnings until the path classes are refined.

## Disconfirmation

**Activation:** fired — blast radius at least 5 files at Standard tier; lens sweep recorded in `SYSTEMS_PLAN.md § Risk Assessment` (Self-review).

- **Falsifier:** this decision is wrong if, over the first 10 pipelines that touch a registered footprint's paths, either of these holds:
  - most FP01 warnings are false positives that authors dismiss without adding a row;
  - a footprint regression of the 36%-to-82% kind passes verification anyway because its paths sit in no registry class.
- **Steelmanned runner-up (prompt-only):** a verifier that reads the diff could tell "agent prompt edited, description unchanged" from "description edited", which no glob can. It adds no component, no registry, no third resolver list and no new gate to keep alive. The real failure in selection-gaps was a missing threshold, not a missing detector; the threshold is fixed by the spec-template decision alone. A prompt rule plus golden bad-cases might therefore have been enough. It loses on one point. The brief and the coordinator require a mechanical trigger for REQ-04 and REQ-05, and the plan-time catch needs a deterministic tool the planner can run over `Files`.
- **Reversal trigger:** revisit in either case:
  - if FP01's false-positive rate makes authors write placeholder rows routinely (visible as many not-measured rows whose reason says "not actually moved"), refine the triggers with frontmatter or content predicates, or fall back to verifier judgment for those classes;
  - if no managed project adopts a registry within 90 days, fold the registry behavior into Praxion-only tooling.
