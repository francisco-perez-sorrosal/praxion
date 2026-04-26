---
id: dec-draft-7e8f93a3
title: Inline 4-condition sanity check replaces a separate Critic agent for skill rewrite gating
status: proposed
category: architectural
date: 2026-04-25
summary: Editor's rewrite is gated by a deterministic 4-condition Python check inside rewrite_skill.py — size delta, frontmatter unchanged, section count unchanged, no fenced python block longer than 8 lines — instead of dispatching a systems-architect invocation for a two-line diff.
tags: [hackathon, safety, rewrite-gating, simplicity]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hackathon/rewrite_skill.py
affected_reqs: []
---

## Context

The original ENHANCEMENTS.md proposal mapped a Praxion `systems-architect` invocation as "Critic" to gate the rewriter's output before it lands in `SKILL.md`. Context-engineer §2 flagged this as a scope mismatch: the architect's twelve-phase process is heavyweight for a two-line skill diff, and the invocation's contract violation cost outweighs the safety value. The use case's collapse plan already lists "drop Critic first" if time runs short. The risk to gate is narrow and structurally enumerable: (1) the rewrite must not exceed Gotchas-only bounds, (2) frontmatter must not be touched (would change skill activation triggers), (3) no new section may be added, (4) the LLM must not embed a multi-line code block disguised as a Gotcha bullet.

## Decision

Implement a four-condition deterministic check in `rewrite_skill.py`:

```python
def is_safe_rewrite(old: str, new: str) -> bool:
    new_python_blocks = [b for b in new.split("```python") if b != new.split("```python")[0]]
    longest_python_block = max(
        (b.split("```")[0].count("\n") for b in new_python_blocks), default=0
    )
    return (
        len(new) - len(old) < 400
        and new.split("---")[1] == old.split("---")[1]
        and new.count("## ") == old.count("## ")
        and longest_python_block <= 8
    )
```

If `is_safe_rewrite` returns `False`, `rewrite_skill.py` writes a rejection note to `artifacts/rewrite_log.md` and falls back to the v1 backup. The demo proceeds to Round 2 with v1 (which will miss again — that itself is observable evidence of the safety gate firing).

## Considered Options

### Option A: Inline 4-condition Python check (selected)

- **Pro:** deterministic, testable as a pure function
- **Pro:** ~10 lines total
- **Pro:** every condition maps to a structural invariant of the Gotchas section style
- **Con:** does not catch semantic issues (e.g., a syntactically-valid Gotcha bullet that contradicts existing skill content)

### Option B: Spawn a real Praxion systems-architect agent

- **Pro:** semantic review by a specialist
- **Pro:** would also catch convention drift
- **Con:** entire twelve-phase pipeline fires for a two-line diff
- **Con:** invocation overhead exceeds the rewrite cost
- **Con:** boundary mismatch — the architect produces SYSTEMS_PLAN.md, not APPROVE/REJECT verdicts

### Option C: Lightweight LLM-based critic with a focused prompt

- **Pro:** semantic review without full pipeline overhead
- **Pro:** ~30 lines
- **Con:** another LLM round-trip on the demo critical path
- **Con:** same failure mode as the rewriter — an LLM judging another LLM
- **Con:** the structural checks below already cover the high-risk attack surface

## Consequences

- Positive: rewrite gating is deterministic, fast, and inspectable
- Positive: AC2 and AC3 are unit-testable with two fixture diffs
- Positive: demo log shows the gate firing (if it fires) — judges see the safety story without prose
- Negative: semantic safety is not enforced by this gate; it relies on the rewriter's prompt being narrow
- Risk accepted: a malicious LLM response that satisfies all four conditions but mangles meaning would pass; mitigation is the rewriter prompt's narrow framing ("append exactly one Gotcha bullet about <defect>"); this is acceptable for a demo
