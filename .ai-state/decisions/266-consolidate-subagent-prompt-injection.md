---
id: dec-266
title: Consolidate subagent prompt injections into a single PreToolUse(Agent) emitter
status: accepted
category: architectural
date: 2026-07-02
summary: Merge inject_worktree_paths.py into inject_subagent_context.py so exactly one hook emits updatedInput per Agent spawn — eliminating the unverifiable multi-hook chaining assumption (td-049) and adding briefed-root detection for the canonical-session-to-worktree direction (td-051).
tags: [hooks, subagents, worktree, updatedinput, reliability]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/inject_subagent_context.py
  - hooks/inject_worktree_paths.py
  - hooks/hooks.json
  - hooks/test_inject_subagent_context.py
  - hooks/test_inject_worktree_paths.py
dissent: "Verification beats avoidance: if the harness DOES chain updatedInput correctly, consolidation traded a clean two-concern separation for a fatter hook on an untested fear — and the chaining answer would have been reusable knowledge for every future hook pair."
---

## Context

Two PreToolUse(Agent) hooks can both emit `updatedInput` for the same spawn: `inject_subagent_context.py` (Praxion preamble for host-native agents) and `inject_worktree_paths.py` (absolute worktree-root briefing line for any agent when the spawning session is inside a linked worktree, added for the td-034 residual). Whether the harness chains multiple `updatedInput` emissions — or silently drops one (first- or last-writer-wins) — is an undocumented harness contract (td-049). This exact class of unverified hook-harness assumption produced the same-day Explore-spawn breakage (the wrapped-envelope defect behind td-021): a hook validated against its own expectation, not the harness's. A second gap surfaced live the same day (td-051): the worktree hook fires only when the *session* is in a worktree, so a canonical-checkout session briefing an agent INTO a worktree gets no deterministic injection — and a haiku doc-engineer committed to the wrong tree despite an absolute-path briefing.

## Decision

Merge the worktree-path briefing into `inject_subagent_context.py` as the single PreToolUse(Agent) `updatedInput` emitter, and delete `inject_worktree_paths.py` (registered for only a few hours, never loaded by any live session). The consolidated hook emits at most one `updatedInput`, composing up to three prompt additions ahead of the original prompt:

1. The Praxion preamble — unchanged gating (host-native agents in Praxion projects; i-am:* skipped unless opted in).
2. The session-worktree briefing line — when the spawning session's `--git-dir` differs from `--git-common-dir` (the td-034 direction), for ALL agent types.
3. The briefed-root briefing line — when the outgoing prompt names a `.claude/worktrees/<name>` path that is not the session's own root (the td-051 direction), for ALL agent types.

When none of the three conditions hold (e.g. an i-am agent, canonical session, no worktree briefing), the hook emits nothing — preserving the existing gate contract. Emission uses the direct `updatedInput` params-object shape (the harness contract fixed the same day).

## Considered Options

1. **Consolidate into one emitter (chosen)** — the chaining question becomes structurally moot; one place to test prompt-composition; covers both bifurcation directions symmetrically. Cost: `inject_subagent_context.py` gains a second concern; its i-am skip gate becomes conditional (skip applies to the preamble, not the worktree lines).
2. **Keep both hooks; live-verify chaining from a fresh session (td-049's original resolution path)** — preserves separation of concerns and yields reusable harness knowledge. Cost: the risk window stays open until someone runs the probe; if chaining fails, one injection is silently dropped in exactly the sessions that need it most; and td-051 needs a third injection site, compounding the same question.
3. **Keep both hooks; make one advisory-only (stderr, no updatedInput)** — avoids chaining but demotes the worktree briefing to a hint the model may never see (stderr visibility to subagents is itself unverified).

## Consequences

- Positive: exactly one `updatedInput` per Agent spawn, ever; both cwd-bifurcation directions covered by deterministic injection; one test file's composition matrix replaces cross-hook interaction unknowns; hooks.json loses a row.
- Negative: the consolidated hook is bigger and mixes two concerns (accepted: they share the trigger point, the emission mechanics, and the fail-open contract); the harness chaining behavior remains unknown (accepted: it is now irrelevant to Praxion).

## Disconfirmation

- **Falsifier**: a future need for a second, independent PreToolUse(Agent) `updatedInput` emitter that genuinely cannot live in the consolidated hook — that would force answering the chaining question anyway, proving elimination only deferred it.
- **Steelmanned runner-up**: Option 2 — a one-time probe from a fresh worktree session would convert an assumption into reusable platform knowledge benefiting every future hook author, at near-zero code cost; consolidation spends real code churn to avoid a question one experiment could answer.
- **Reversal trigger**: the harness documents (or a probe proves) well-defined multi-hook `updatedInput` chaining semantics, AND a second injection concern arrives that would be cleaner as its own hook — then split again along concern lines.
