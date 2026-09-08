---
id: dec-draft-30dd031c
title: Retire the worktree guard and banner hooks in favour of the harness's native worktree isolation
status: proposed
category: architectural
date: 2026-09-08
summary: Delete hooks/worktree_guard.py and hooks/inject_worktree_banner.py (and their tests and hooks.json entries); native Claude Code worktree isolation becomes the sole write-containment layer, /merge-worktree keeps finalize + .ai-state reconciliation, and the tier-to-isolation policy row stays resident.
tags: [process-economy, hooks, worktrees, isolation, simplification, phase-1]
made_by: agent
agent_type: orchestrator
branch: worktree-process-economy-phase1
pipeline_tier: full
affected_files:
  - hooks/hooks.json
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
  - docs/onboarding.md
  - docs/architecture.md
  - docs/diagrams/architecture/src/architecture.c4
dissent: "Two things are lost, not one: the banner's /resume-rework affordance in fresh rework worktrees, and the guard's command-text heuristics were the only layer that refused a Bash heredoc or `sh -c` write into the main checkout from a worktree session; native isolation covers Write/Edit only, so a later pipeline's implementer can silently edit the wrong tree through Bash."
---

## Context

Two shipped hooks reinforce pipeline worktree isolation: `inject_worktree_banner.py` (SessionStart, announces the worktree root) and `worktree_guard.py` (PreToolUse, refuses `Write`/`Edit` whose target resolves outside the session worktree, plus command-text heuristics that also refuse Bash shapes such as heredocs, `sh -c`, `xargs`, and any command text containing the VCS name). Since they shipped, Claude Code gained native worktree isolation: the harness itself refuses `Write`/`Edit` through a symlink whose realpath leaves the worktree and outside-worktree writes, and this cannot be turned off. The two hooks now duplicate that check for `Write`/`Edit`, cost a subprocess pair on every `Write`/`Edit` call, and their command-text heuristics produce recorded false positives (any command containing "eval" or "git" in some shapes is refused; scratchpad scripts are the workaround). The process-economy roadmap (§ 6 P1.10) names them for deletion at high confidence; the plan's Phase 2 verification found six load-bearing documents and the architecture DSL still asserting the hooks exist, including `docs/onboarding.md`'s sidecar-mount rationale and `docs/architecture.md`'s sidecar-placement row.

## Decision

Delete `hooks/worktree_guard.py`, `hooks/inject_worktree_banner.py`, their three test files, `hooks/MANUAL_VERIFICATION.md`, and their two `hooks/hooks.json` entries. Native harness isolation becomes the sole write-containment layer for pipeline worktrees. `/merge-worktree` keeps its finalize and `.ai-state/` reconciliation semantics unchanged; the tier→isolation policy row (Standard/Full → worktree) stays resident in the coordination rule. Every document and DSL element that named the hooks as an enforcement layer is corrected in the same commit to name native isolation instead. The compensating control for the dropped Bash-path protection is procedural and already mandatory: pathspec-scoped commits, merge gates verified from the main checkout, and `git status` re-derivation before any resume.

## Considered Options

### Delete both hooks (chosen)

- Pros: removes ~56 KB of maintained code and one subprocess pair per Write/Edit; removes a class of false positives that forced scratchpad-script workarounds; a single enforcement layer instead of two that can disagree.
- Cons: Bash-path writes into the wrong tree are no longer refused by anything mechanical; six docs and the DSL must be corrected together.

### Keep `worktree_guard.py`, delete only the banner

- Pros: keeps the Bash-path heuristics.
- Cons: keeps the duplicate Write/Edit check and the subprocess cost; keeps the false positives that are the guard's most-recorded behaviour; the banner is the cheaper half — this option removes the wrong hook.

### Rewrite the guard as a Bash-only pre-check

- Pros: keeps exactly the protection native isolation lacks.
- Cons: the heuristics are the unreliable part (command-text matching cannot see where a script writes); the honest version of this option is a `PreToolUse` hook that refuses any Bash command in a worktree session that mentions the main checkout's path, which is a new hook, not a retained one — a Phase 2 candidate if the compensating controls prove insufficient.

## Consequences

- Positive: one enforcement layer; fewer subprocesses per edit; the documented false positives disappear; the docs stop describing a mechanism the harness already provides.
- Negative: the banner was also the SessionStart affordance that surfaced `/resume-rework` inside a fresh rework worktree; that hint is gone, so rework dispatch now relies on the orchestrator's hand-off (or the user) naming `/resume-rework` — `docs/architecture.md` § Rework Loop records the removal.
- Negative: a Bash heredoc or script run from a worktree session can write into the main checkout without refusal. Accepted, with the procedural controls above; recorded as a real behaviour change, not a regression, in the pipeline's LEARNINGS.
- The `docs/onboarding.md` sidecar-mount rationale and `docs/architecture.md` sidecar row are reworded to rest on the state mount's realpath invariant alone, which native isolation honours for the same reason the guard did.

## Disconfirmation

- **Falsifier**: a pipeline after this change lands a commit on the wrong tree through a Bash-path write that the deleted guard would have refused — observed as a cross-tree edit found at a merge gate or by `git status` re-derivation.
- **Steelmanned runner-up**: rewrite the guard as a Bash-only pre-check. If two such cross-tree writes are recorded within ninety days, this is the right option and should be implemented as a new hook with a narrow, testable predicate (command text references the main checkout's realpath while the session cwd is a worktree).
- **Reversal trigger**: the first recorded cross-tree Bash write after the deletion, or a harness change that removes or weakens native worktree isolation.
