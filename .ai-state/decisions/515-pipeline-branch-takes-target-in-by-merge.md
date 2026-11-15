---
id: dec-515
draft_id: dec-draft-c4957d75
title: "A pipeline branch may take the target in by a merge commit just before its fast-forward merge"
status: accepted
category: behavioral
date: 2026-11-15
summary: "The merge procedure keeps fast-forward as the only way the target branch moves, and gains one exception on the branch's side: a pipeline branch whose state files cite its own commit hashes may merge the target into itself as its last change instead of rebasing, so the cited hashes stay valid, the final merge is still a fast-forward, and the head tree that was tested is the tree that lands."
tags: [merge, fast-forward, rebase, worktree, pipeline, ai-state, process]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: direct
affected_files:
  - skills/merge-worktree/SKILL.md
  - rules/swe/vcs/pr-conventions.md
---

## Context

The merge policy is fast-forward only, and a diverged branch is told to rebase onto the target first. A pipeline branch commits `.ai-state/` files that cite its own commit hashes: a ledger row's `resolved-by`, a state commit naming the commits it records, a spec's footprint log. A rebase rewrites those hashes into dangling references, and a long pipeline almost always diverges, because the target keeps moving while it runs.

Three pipelines in a row (the process principles, the memory-to-artifacts move and the refactoring delivery, merged 2026-11-12 to 2026-11-15) solved this the same way without a rule that allowed it: each merged the target into the branch as its last change, ran its integration run on that head, and then fast-forwarded the target. The user was asked on 2026-11-15 whether to keep the rule's default alone or to write the practice down, and delegated the call.

## Decision

Fast-forward stays the only way the target moves. One exception is written into the merge procedure, on the branch's side: a pipeline branch whose state files cite its own commit hashes may take the target in with a merge commit, as its last change before the merge, instead of rebasing. The integration run on that head is the pre-merge run, so no trial merge is needed, and nothing is committed on the target between that run and the merge.

## Considered Options

### Rebase only (the rule as it stood)

Keeps the target's history linear. It dangles every hash the branch's state files cite, unless each is rewritten by hand after the rebase, which the merge procedure already describes as a recovery, not a path.

### Merge the target into the branch, then fast-forward (chosen)

Keeps every cited hash valid and makes the tested tree and the landed tree the same tree. It puts one merge commit per such pipeline into the target's history.

### A true merge commit on the target

Also keeps the hashes. The tree that lands is then one no run has tested, and the post-merge hooks see a different shape of merge.

## Consequences

- The target's history is no longer strictly linear: it holds one merge commit for each pipeline that used the exception.
- The integration run of such a pipeline counts as its pre-merge run only if the target has not moved since; the procedure says so.
- The rule file's merge paragraph still names only the rebase. Its text is pinned by frozen export fixtures, so the sentence that points at this exception rides the next change that re-pins them; a ledger row tracks it.
