---
id: dec-059
title: Squash-Merge Safety -- post-merge warning + `/merge-worktree` refuse-or-rebase
status: accepted
category: implementation
date: 2026-04-19
summary: A new `scripts/check_squash_safety.py` invoked by the post-merge hook detects squash-merges that erase `.ai-state/` entries and emits a loud warning with recovery steps; `/merge-worktree` refuses to invoke `git merge --squash` on `.ai-state/`-touching branches.
tags:
  - concurrency
  - git
  - hooks
  - safety
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - "scripts/check_squash_safety.py"
  - "scripts/git-finalize-hook.sh"
  - "commands/merge-worktree.md"
  - "rules/swe/vcs/pr-conventions.md"
---

## Context

Squash-merge on GitHub overwrites the target branch's `.ai-state/` with the source branch's, bypassing merge drivers and post-merge hook. Sentinel reports, calibration entries, and ADRs made on main since the branch diverged are lost. Only a user-facing warning exists in documentation; no enforcement.

Two detection points exist:

1. `git merge --squash` invoked locally (e.g., by `/merge-worktree`) -- preventable.
2. Squash-merge done in GitHub UI -- not preventable; only detectable after the fact.

User decision includes a "squash-merge pre-check (hook or command-level) that prevents erasure of `.ai-state/` on target". The question is where to place enforcement.

## Decision

Two-layer approach:

**Layer 1 -- Prevention at the command layer (`/merge-worktree`):**

- `commands/merge-worktree.md` gains Step 4.5: "If the user requests squash merge and the branch has touched `.ai-state/`, refuse; recommend either regular merge or rebase-and-merge." Enforced by the command flow, not a hook.

**Layer 2 -- Detection at the post-merge hook (GitHub UI case):**

- New `scripts/check_squash_safety.py` (pure stdlib Python). On invocation:
  1. Read `HEAD` and `HEAD~1`.
  2. Enumerate `.ai-state/**` files in each.
  3. If `HEAD` has strictly fewer `.ai-state/` entries than `HEAD~1` AND the merge commit has exactly one parent (indicator of squash), print a loud warning with recovery steps (`git reflog`, `git cherry-pick <original-branch-tip>`).
  4. Exit 0 always (non-blocking; post-merge cannot abort a completed merge).
- `scripts/git-post-merge-hook.sh` -- after the existing `reconcile_ai_state.py` and finalize calls, invoke `scripts/check_squash_safety.py`.

Documented in `rules/swe/vcs/pr-conventions.md` merge-policy section.

## Considered Options

### 1. Two-layer prevention + detection (chosen)

Covers the preventable case at the command and the unpreventable case at the hook. Loud warning surfaces when damage has already been done so recovery via reflog is possible.

### 2. Pre-commit hook that blocks squash

Rejected: squash-merge runs `git merge --squash` followed by a regular `git commit`; pre-commit fires on the commit without knowing it was a squash. Parent-count analysis happens naturally post-merge.

### 3. Command-only enforcement (no hook detection)

Rejected: misses GitHub UI squash-merges entirely. Research found this is the dominant source of `.ai-state/` loss incidents.

### 4. Hook-only enforcement (no command layer)

Rejected: detects damage after the fact, which is recoverable but not preventable for the case we CAN prevent.

### 5. Block squash in GitHub branch protection rules

Out of scope for this task (requires repo config, not a shipped artifact). Worth adopting as a complementary measure but not a substitute -- many forks of Praxion will not have branch protection configured.

## Consequences

**Positive:**

- Preventable cases prevented at the command layer.
- Unpreventable cases surfaced loudly with recovery steps, before reflog ages out.
- Non-blocking at the hook layer -- matches the existing hook's defensive posture.
- Consistent with existing post-merge-hook pattern.

**Negative:**

- Cannot prevent GitHub-UI squash-merges -- damage is already done when hook fires.
- Recovery relies on `git reflog`, which ages out after 90 days by default.

**Risks:**

- User ignores the warning. Mitigation: warning includes specific recovery commands and a direct pointer to the PR-conventions rule.
- Check script false-positive on legitimate rebase-and-merge with `.ai-state/` changes. Mitigation: rebase-and-merge preserves parent count >1 when the source branch had any merge commits; single-parent check is conservative. If false-positives occur, check script can be refined to also compare trees.
- Check script cost on every merge. Mitigation: implementation is O(filesystem diff) -- cheap; runs only when post-merge hook detects `.ai-state/` in merged files.
