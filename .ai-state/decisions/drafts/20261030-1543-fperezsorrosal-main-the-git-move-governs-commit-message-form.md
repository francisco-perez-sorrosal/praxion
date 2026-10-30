---
id: dec-draft-8d92b698
title: The git-conventions move governs commit message form alone; staging by name leaves its governed checks
status: proposed
category: behavioral
date: 2026-10-30
summary: The git-conventions kit's declaration drops staging by name, which its floor run never saw fail, so a paired run can cite that kit's floor; the grader, its fixture traps and the resident kernel lines stay, and a declaration file can govern the check again.
tags: [eval, adherence, main-session, moves, git-conventions, floor-run, governed-checks]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - eval/src/praxion_evals/adherence/moves/kits/git-conventions/declaration.json
  - eval/EVAL_PLAN.md
  - .ai-state/specs/SPEC_main-session-adherence_2026-10-28.md
affected_reqs: [REQ-12]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: null
superseded_in_part_by: null
dissent: null
---

## Context

REQ-12 of the main-session-adherence spec gave the git-conventions move two governed checks: commit message form and staging by name. A paired run must cite a floor run that failed every governed check it declares (`moves/lineage.py`); a floor that never fails a check shows no room for the move to lose anything there.

The first floor, on tasks without traps (`20261029T052039Z-9703ec`), saw neither check fail. The fixtures then gained the traps the rule targets. The second floor (`20261030T054933Z-a402e2`: opus at medium effort, eight sessions, from a checkout frozen at `5d1cdfb3`) failed commit message form in all eight sessions and staging by name in none. With no line of the rule anywhere, every session committed exactly the files its request named, so as declared the move could never run its pairs.

The lines staging by name reads (stage specific files by name, review `git diff --staged`, verify the staged diff matches intent) are in the lean arm's resident kernel. The move keeps them at session start in both arms and relocates none of them.

## Decision

The kit's `declaration.json` governs commit message form alone. Nothing else changes:

- `moves/checks_git.py` still grades staging by name for any declaration that governs it, which a run can pass with `--declaration`.
- The kit's fixtures keep the staging traps.
- The tests keep a declaration that governs the check: `eval/tests/staging_check_support.py`, and the acceptance variant "staging by name governed too".

The git move's floor is run again from a checkout frozen at the commit that lands this decision, and its paired run cites that floor.

## Considered Options

### Drop the check from the kit's declaration (chosen)

- Pro: the move becomes measurable, and no rule text changes.
- Pro: the check measured lines the move does not relocate, so its verdict would have spoken for the resident kernel, not for the move.
- Con: the move's evidence covers commit message form only.

### Design a trap that a session without the rule falls into

- Pro: keeps REQ-12 as written.
- Con: making opus stage unnamed files without the rule would take wording that invites staging everything. That sits close to stating the rule's opposite in the task, which REQ-06 forbids.
- Con: it costs another design pass and another floor.
- Con: even a sensitive check would measure the resident kernel, the same text both arms carry.

### Keep both checks

- Con: no floor can be cited, so the move never runs its pairs.

## Consequences

- The git move's paired run can cite a floor once a floor run on the new declaration fails commit message form.
- Staging adherence under the lean arm goes unmeasured by this move. It rests on the resident kernel, the text the full arm also carries at session start.
- REQ-12's "two governed checks" is amended by this record. The archived spec stays as written.
- If a later move relocates the staging lines out of the kernel, that move needs its own staging check and a trap its floor can fail, before its pairs can run.
