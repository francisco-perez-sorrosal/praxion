---
id: dec-draft-90086b99
title: Add "Mutable default arguments" Gotcha bullet to skills/code-review/SKILL.md
status: proposed
category: behavioral
date: 2026-04-25
summary: Append a single Gotchas bullet covering Python mutable default arguments (def f(x=[])) to the code-review skill, closing a real blind spot in the current Language Adaptation table coverage of Immutability.
tags: [hackathon, code-review, gotcha, python, skill-rewrite]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/code-review/SKILL.md
affected_reqs: []
---

## Context

The hackathon demo (see SYSTEMS_PLAN.md in `.ai-work/hackathon-skill-loop/`) is built around a real blind spot in the `code-review` skill: its Language Adaptation table maps Python's "Immutability" convention to "frozen dataclasses, tuples" but does not call out function-signature mutable defaults (`def f(x=[])`, `def f(x=set())`). PR-A in the demo plants this defect class on `events.py:14`; the skill's current Gotchas section produces no FAIL on that line. Round 1 of the demo records this miss as a `SkillRunEntry` with `error_type="missed_bug"`. The demo's improvement loop then writes a Gotcha bullet that closes the gap, and Round 2 (PR-B) catches an isomorphic defect at `cache.py:22`.

The skill change is genuine — not a manufactured demo gap. Context-engineer §1 and §6 both recommend landing this bullet as a real PR with an ADR audit anchor so (a) the sentinel does not flag the live `SKILL.md` change as undocumented and (b) the change has a discoverable rationale post-hackathon.

## Decision

Add the following bullet to the `## Gotchas` section of `skills/code-review/SKILL.md`, immediately after the existing "Structural findings belong to refactoring" bullet:

> **Mutable default arguments**: In Python, `def f(x=[])` and `def f(x=set())` share the default object across all calls — a silent state mutation bug. Flag any function signature whose default value is a list, dict, or set literal as a FAIL under the Immutability convention, citing the `file:line` and proposing `x: list[T] | None = None` with an early `if x is None: x = []` guard.

No frontmatter changes, no new sections, no other body edits. The bullet matches the existing Gotchas style verified by context-engineer §1 (bold title, active imperative voice, inline code examples, prescribed FAIL classification, file:line citation, proposed fix).

## Considered Options

### Option A: Append the Gotcha bullet (selected)

- **Pro:** addresses a real blind spot
- **Pro:** matches existing Gotchas pattern exactly (no convention drift)
- **Pro:** two-line diff, easy to review post-hackathon
- **Pro:** serves as the demo's headline artifact

### Option B: Extend the Language Adaptation table's Immutability row

- **Pro:** semantically the most "correct" location (mutable defaults are a Python Immutability concern)
- **Con:** table cells must stay short; "frozen dataclasses, tuples, no mutable default args" loses the prescriptive detail (file:line, proposed fix)
- **Con:** behavior would still need a Gotchas pointer to be effective in practice

### Option C: Defer the change and ship the demo with a fixture-only skill copy

- **Pro:** no production skill change
- **Con:** loses the genuine-improvement narrative; the demo becomes a toy
- **Con:** context-engineer §4 specifically recommends rewriting the live skill for genuine PR value

## Consequences

- Positive: closes a real Python review gap that the skill should have covered
- Positive: provides the audit anchor sentinel needs to accept the live `SKILL.md` change
- Positive: forms the headline artifact judges trace from `events.py:14` miss → `cache.py:22` catch
- Negative: introduces a small Python-specific bias to a skill that aspires to language-neutrality (mitigated — this is a Gotchas item, not a language-agnostic rule)
- Risk: replay runs of the demo overwrite this bullet; mitigated by `demo.py`'s idempotent `backup_or_restore()` protocol (AC8)
