---
id: dec-172
title: inject_rules.py schema version > 1 behavior is fail-open
status: accepted
category: implementation
date: 2026-05-13
summary: When .claude/praxion-rules.yaml carries version > 1, inject_rules.py logs a clear error to stderr but injects ALL blacklistable rules rather than blocking or injecting nothing.
tags: [rules, blacklist, hook, schema-version, fail-open]
made_by: agent
agent_type: implementation-planner
branch: worktree-rules-reorg-blacklist
pipeline_tier: full
affected_files:
  - hooks/inject_rules.py
  - hooks/test_inject_rules.py
affected_reqs:
  - REQ-01
  - REQ-07
re_affirms: null
supersedes: null
---

## Context

`SYSTEMS_PLAN.md` § Interfaces specifies that `.claude/praxion-rules.yaml` carries a `version:` field for future-proofing, and that "the hook refuses to load schema > 1 with a friendly message." The implementation must decide: when an unsupported schema version is encountered, what does the hook inject?

Two failure modes exist: fail-open (inject all blacklistable rules, ignore the blacklist) or fail-closed (inject nothing, or block session start).

## Decision

The hook **fails open**: when `version > 1`, it logs a structured error to stderr and then injects all blacklistable rules (treating the blacklist as empty). Session start is never blocked.

Stderr message format:
```
[inject_rules] ERROR: .claude/praxion-rules.yaml schema version {N} is not supported
  (this version of inject_rules.py understands schema 1 only).
  Update the i-am plugin or remove the `version:` field to use schema 1.
  Falling back: all blacklistable rules injected (disable list ignored).
```

## Considered Options

### Option 1 — Fail closed (inject nothing)

When schema > 1, output no `additionalContext`. Project gets only core rules (native symlinks).

**Pros:** User will notice immediately (rules missing from session) and update the plugin.
**Cons:** Silently drops 3 rules that the user expected. Violates AC-01 (backward compat) in the edge case where the user bumped the schema version without updating the plugin — they now get a degraded session with no explanation in the session context itself. The error is in stderr only; Claude never sees it in-context.

### Option 2 — Hard fail (block session start)

Exit non-zero to block session start.

**Pros:** Forces immediate attention.
**Cons:** Completely incompatible with the hook's non-fatal contract (established by `SYSTEMS_PLAN.md`: "Hook is non-fatal: catches all exceptions, logs to stderr, returns empty additionalContext on failure"). Blocking SessionStart on a config version mismatch is a denial-of-service risk.

### Option 3 — Fail open (inject all, ignore blacklist) — chosen

**Pros:** User still gets a functional session with all blacklistable rules available. The error message is visible in stderr/transcripts. Consistent with the hook's non-fatal contract. The user's disable list is temporarily ignored, not lost.
**Cons:** The user's blacklist is not honored until they update the plugin. Acceptable: the schema version is a future-proofing mechanism; schema 2 does not exist yet, so this edge case cannot occur in current usage.

## Consequences

**Positive:**
- Non-fatal behavior preserved. Session always starts.
- Degraded mode (all rules injected) is better than silent loss of rules.
- Clear stderr error points to the fix (update plugin or remove version field).

**Negative:**
- A user with `version: 2` and intentional blacklists will have their blacklist ignored silently (from Claude's perspective) until they update the plugin.

**Operational:**
- Implemented in `hooks/inject_rules.py` after parsing the `version:` field.
- Test case 7 in `hooks/test_inject_rules.py` validates this behavior.

**Cross-cutting:**
- Pairs with the general non-fatal hook contract from `dec-167`.
