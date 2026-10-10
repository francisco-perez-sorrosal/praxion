---
id: dec-draft-f9795b0a
title: The always-loaded byte ratchet honours an explicit, dated operator suspension recorded in the committed baseline
status: proposed
category: behavioral
date: 2026-10-10
summary: "`measure_token_budget.ratchet()` reads a `ratchet_suspended` block (`until`, `reason`, `set_on`, `by`) from `.ai-state/token_budget_baseline.json`; while today is on or before `until` the governed-byte delta is reported but not enforced, the frozen listing ceiling keeps biting, the gate prints the suspension on every commit, and an expired or malformed block enforces again. Set until 2026-11-30 by user decision for the commands-to-skills and skill-crafting-refresh pipelines."
tags: [token-budget, ratchet, commit-gate, always-loaded, operator-override, process-economy]
made_by: fperez
agent_type: orchestrator
branch: main
pipeline_tier: Direct
affected_files:
  - scripts/measure_token_budget.py
  - scripts/test_measure_token_budget.py
  - .ai-state/token_budget_baseline.json
affected_reqs: []
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

The byte ratchet (`check_token_ratchet.py`, a blocking PreToolUse commit gate) compares today's always-loaded byte count against the oldest surviving sample of a 35-day window. On 2026-10-10 the governed set measured 65,708 bytes against an oldest sample of 67,031 (2026-09-07), so the gate passed. That sample ages out on 2026-10-13, after which the comparison point becomes 65,505 and, from 2026-10-18, 64,860 bytes: every `git commit` in the repository would be blocked for roughly a month by the calendar alone, not by any change in flight. The growth that created the gap landed on 2026-10-08, unrelated to the migration pipeline that was about to start.

The user was offered three handlings (trim at least 848 bytes early in the pipeline; re-seed the baseline; wait for the block) and chose a fourth: "I want explicitly to circumvent the rule for this session and the next ones."

## Decision

The ratchet gains one explicit, reviewable, self-expiring operator override. A `ratchet_suspended` object in the committed baseline (`until` ISO date, `reason`, `set_on`, `by`) waives only the governed-byte delta while today is on or before `until`. The gate still records today's sample, still enforces the frozen listing ceiling, and prints the suspension with its reason on every commit, so the waiver is visible in every diff and every commit log. An expired block enforces again and says so; a malformed block fails closed (enforces) rather than being silently honoured or silently ignored. The baseline on main now carries the block until 2026-11-30 with the user's reason; the migration pipeline's own footprint bound (bytes at or below the pre-change 65,708) is graded by its verifier instead.

## Considered Options

### Trim 848 bytes in the pipeline
Pros: keeps the ratchet honest, advances context economy. Cons: adds scope and a deadline to an unrelated pipeline; the user declined.

### Re-seed the baseline
Pros: no code. Cons: blesses the 10-08 growth without review; the window re-arms after 30 days and the same block recurs; the user declined.

### `disableAllHooks`
Pros: immediate. Cons: disables observability, every other commit gate and the session hooks; unacceptable.

### Reset the sample history
Pros: data-only, immediate. Cons: erases 35 days of readings; the same 30-day warm-up trick would be needed again; indistinguishable from an accident in the diff.

### A dated operator suspension in the baseline (chosen)
Pros: explicit, dated, attributed and reasoned in a committed file; self-expiring; announced on every commit; the listing tripwire survives; a broken block cannot silently widen the waiver. Cons: the installed plugin runs its cached copy of the gate, so the new behaviour reaches a session only through `./install.sh --dev-link` or the next plugin refresh.

## Consequences

- Positive: commits proceed through the pipelines without the gate going silent or being removed; the override is one object in one committed file; expiry is automatic.
- Negative: until the plugin cache is refreshed or dev-linked, sessions running the cached gate still block from 2026-10-13; the orchestrator surfaces that step to the user.
- The listing ceiling (9,243 tokens, 24 tokens of headroom on 2026-10-10) is unaffected and remains the binding constraint on model-visible descriptions.
- Follow-up: when the window has rolled past (after 2026-11-12 at the current size), remove or extend the block; the gate's expiry note is the reminder.
