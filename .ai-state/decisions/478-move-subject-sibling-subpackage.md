---
id: dec-478
draft_id: dec-draft-b9d1c991
title: A rule move is a second subject kind in a sibling subpackage over the adherence eval's shared kernel
status: accepted
category: architectural
date: 2026-10-27
summary: The adherence eval measures a main-session rule move through a new subpackage, praxion_evals.adherence.moves, that composes the role path's pure kernel (verdict over pairs, stop failure identity and streak, lineage chain, arm-copy diff, atomic writer); the entry parses --role or --move into a Subject and dispatches; the role shell and every role results file stay unchanged.
tags: [eval, adherence, main-session, moves, subject-kind, startup-context-diet]
made_by: agent
agent_type: systems-architect
branch: main-session-adherence
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/moves/
  - eval/src/praxion_evals/adherence/cli.py
  - eval/src/praxion_evals/adherence/infra_stop.py
  - eval/src/praxion_evals/adherence/lineage.py
affected_reqs: [REQ-01, REQ-02, REQ-05, REQ-07, REQ-15]
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

REQ-01 asks that a move (one rule's text relocated out of session-start residency) be measured by the same verdict, stop, continuation, close, allowance and earlier-runs machinery as a spawned role (dec-462), while every role run, every recorded results file and the kernel flip gate read exactly as before. The landed eval is role-keyed throughout: `model.Role` is a closed set of agents, `model.Arm` is full or lean, `SessionSetup`, `infra_stop.StopReason`, `lineage.pending_stop`, `results.RunResults` and the run index key on a role, and six of its modules are at 615 to 772 lines against an 800-line ceiling. A move needs a third arm, multi-file arm builds and a main-session record reader the role path does not have.

## Decision

Add a component: the subpackage `eval/src/praxion_evals/adherence/moves/`, which owns everything a move adds (declaration, three-arm build, host reach, pinning, main-session record, take, trigger record, git kit, stop fold, lineage and floor citation, results and index, verdict adapter, report, runner, its half of the entry). It reaches the role path only through pure kernel functions: `verdict.role_verdict` over `model.Pair`, `infra_stop`'s failure identity and a shared `trailing_streak`, a public `lineage.chain_of`, `arms.verify_copy_diff`, and the results writer's atomic write. The subject kind is a value parsed once at the entry (`Subject = RoleSubject | MoveSubject`, from a mutually exclusive `--role`/`--move`) and persisted as the results directory a file lives in. The role shell is not edited beyond the entry's dispatch and the two behaviour-preserving extractions.

**Activation:** no -- two shapes were weighed directly against REQ-01's unchanged-role clause and the file ceilings; no lens sweep was needed.

## Considered Options

### A sibling subpackage over the shared kernel (chosen)

Pros: the role path, its wire form and the flip gate's read surface are untouched; no file nears the ceiling; the move's three arms and main-session record never leak into role types. Cons: two shells over one kernel, so a feature that spans subjects lands twice; the stop fold and the lineage reader exist in two shells.

### A `Subject` sum type threaded through the role shell

Pros: one shell, one results schema, one index, one listing; a third subject kind costs less. Cons: edits `model`, `results`, `lineage`, `session_loop`, `run_index` and `cli`, most near 800 lines; changes the role results' wire form or forces a legacy branch on every reader; widens the flip gate's contract for subjects the adoption ledger never cites.

## Consequences

- Positive: REQ-01's non-regression clauses hold by construction; each new module stays small; the move's representation (three arms, deliveries, trigger record) is typed for moves alone.
- Negative: cross-subject changes touch both shells; the two stop folds and lineage readers must stay in step, which the shared `trailing_streak` and `chain_of` and a parity test each enforce.

## Disconfirmation

- **Falsifier:** if the move half needs to edit a role-shell module beyond the entry's dispatch and the two extractions (P1, P2), or if a parity test between the two stop folds ever has to be relaxed, the seam is in the wrong place and the sum-type option was right.
- **Steelmanned runner-up:** a single shell is what dec-462's "one instrument, no second machinery to drift" points at; the drift this design accepts is exactly the drift that clause names, and Phase 3's later moves (decision context, model routing) will each pay the double landing again. Threading the subject once, behind a refactor-first mini-pipeline, would pay that cost a single time.
- **Reversal trigger:** a third subject kind, or a second cross-subject feature landing in both shells, reopens this decision in favour of the sum type.
