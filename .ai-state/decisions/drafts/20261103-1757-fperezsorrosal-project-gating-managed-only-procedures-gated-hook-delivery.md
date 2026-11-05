---
id: dec-draft-b7e3ef71
title: Managed-only procedures reach sessions and inheriting spawns by gated hooks, decided by one project predicate
status: proposed
category: architectural
date: 2026-11-03
summary: The coordination protocol, intermediate-documents rule and ADR resident leave the user-scope symlink set; with the routing resident they are delivered by the rule injector only where locate() finds .ai-state/, over SessionStart for the main session and SubagentStart for inheriting spawns, in labelled parts under the 10,000-character cap; every managed-only gate uses the same predicate.
tags: [rules, hooks, project-gating, sessionstart, subagentstart, token-budget, predicate]
made_by: agent
agent_type: systems-architect
branch: project-gating
pipeline_tier: full
supersedes_in_part: [dec-167]
affected_files:
  - hooks/inject_rules.py
  - hooks/hooks.json
  - hooks/_project_scope.py
  - hooks/_rule_delivery.py
  - hooks/_observation_log/location.py
  - hooks/inject_decisions.py
  - hooks/inject_process_framing.py
  - hooks/inject_subagent_context.py
  - scripts/regenerate_rules_manifest.py
  - rules/_manifest.yaml
  - lib/install_shared.sh
  - scripts/measure_token_budget.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-09, REQ-10, REQ-11, REQ-13, REQ-14]
---

## Context

dec-167 split rule delivery in two: blacklistable always-loaded rules by a SessionStart hook, core and path-scoped rules by user-scope symlinks that load natively in every directory. The user decided (2026-11-03) that the pipeline procedures are managed-only: a project without `.ai-state/` should not pay about 9.5K tokens per session and per inheriting spawn for them, while managed projects keep exactly today's process. Three of the five units (coordination protocol, intermediate-documents rule, ADR resident) are core and symlinked, so they reach every directory and every inheriting spawn natively. Probes of 2026-11-03 (Claude Code 2.1.317): an unapproved external `@` import is dropped silently under `-p`; SessionStart text reaches the main session but not a spawn; SubagentStart text reaches a spawn. The memory doc (fetched 2026-11-03) loads instruction files from the start directory and every directory above it.

## Decision

Channel A+. The three symlinked units stop being linked at user scope. `hooks/inject_rules.py` delivers them, with the routing resident, only when `scope_of(cwd)` is `Managed`: to the main session over SessionStart and to inheriting spawns (not Explore, Plan or roles whose definition omits instruction files) over SubagentStart, in self-labelled parts of at most 10,000 characters from N slot registrations per event. Core managed units bypass the injection kill switch and the PyYAML/manifest dependency, as core rules cannot be blacklisted. The managed set is a frontmatter key `project_scope: managed` (with `install: hook-deliver`), copied into the manifest and pinned by id in the generator; rule bodies are not edited. When no Praxion hook runs at all, managed sessions keep the constitution and the project's own CLAUDE.md (the user's F1 floor). `locate()` moves to `hooks/_project_scope.py` and becomes the one predicate for the injector, the decision context, the prompt reminder, the host-native spawn preamble and the budget instrument; the Codex bridge keeps its own test (exports frozen).

## Considered Options

- **A (SessionStart only)** — silently strips about 8.7K tokens of procedure from every inheriting spawn in managed projects. Rejected.
- **B (project CLAUDE.md imports the procedures, hook fallback)** — dropped silently in every headless session of an unapproved project (probe g1a); does nothing for lagging projects; needs A anyway. Rejected.
- **C (real copies in the project's `.claude/rules/`, hook bridge)** — native and approval-free, but loads in nested repositories and directories that `locate` calls unmanaged (instruction files load from every directory above the start), needs a writer, refresher and same-session-load probe, and still needs A+ for fresh worktrees and lagging projects. Kept as floor option F3.
- **Keep the symlinks** — no reduction for the three units. Kept as floor option F2.

## Consequences

- Unmanaged sessions and inheriting spawns stop receiving the procedures; managed sessions and spawns receive the same text by a different carrier (a system-reminder block instead of a user rule). The paired channel run that was to re-measure adherence was declined by the user on 2026-11-05: the move eval cannot express a project-gating move (no task kit, a channel that reaches no line, no governed checks for the protocol, the intermediate-documents rule or the routing resident; td-579). What is established is text parity (every statement a managed session and inheriting spawn received before arrives, checked by content) and the token bounds; equivalence of adherence is unmeasured, and nothing beyond bounded non-regression of the text is claimed.
- When no Praxion hook runs at all, managed sessions no longer receive the three units (today they do natively); the user accepted this floor (F1).
- Subdirectory sessions of a managed project gain the decision context, prompt reminder and preamble.
- dec-167's clause "core rules continue using native symlinks" is narrowed: core rules with `project_scope: managed` are hook-delivered.

## Disconfirmation

- **Falsifier:** probe P1 or the REQ-04 scenarios show any SubagentStart part missing, truncated or unreadable in an inheriting spawn, or a paired channel run, once the instrument can express this move (td-579), shows a regression on a check beyond its allowance.
- **Steelmanned runner-up (C):** native project copies are the only carrier that survives a session in which no hook runs, keeps the exact user-rule-like position in the instruction hierarchy, and avoids slot-order risk; its nested-directory over-reach costs little, since a project's own CLAUDE.md already reaches those directories today.
- **Reversal trigger:** P1 fails at the needed size, or the user answers SQ-7 with F3; then C becomes the primary carrier for managed projects and A+ shrinks to the bridge.
- **Activation:** fired (spawn delivery at size 6/10; process loss is user-visible). Tier-B not run: reversible by one manifest table edit and a relink.

## Prior Decision

dec-167 (accepted) delivers blacklistable always-loaded rules by a SessionStart hook and keeps core and path-scoped rules on native user-scope symlinks. This record narrows one clause: core rules whose manifest record carries `project_scope: managed` (the coordination protocol, the intermediate-documents rule, the ADR resident) are no longer symlinked; they are hook-delivered, gated on the project predicate, to the main session and to inheriting spawns. dec-167's blacklist mechanism, its core-rule immunity (dec-168) and the symlink channel for every-project core and path-scoped rules stand unchanged. The reciprocal `superseded_in_part_by` on dec-167 is set at finalize.
