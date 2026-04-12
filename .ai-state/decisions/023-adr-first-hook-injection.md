---
id: dec-023
title: ADR-first budget allocation with memory filling remainder for hook injection
status: accepted
category: architectural
date: 2026-04-12
summary: SubagentStart hook injection prioritizes ADRs (2,000-char soft cap) with memory filling the remainder; supersedes dec-011 which mis-described the implementation as memory-first
tags: [memory, adr, hooks, budget, injection]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/inject_memory.py
  - .ai-state/decisions/011-adr-injection-memory-first-budget.md
supersedes: dec-011
---

## Context

`dec-011` (2026-04-04) titled *"Memory-first budget allocation with ADR soft cap for hook injection"* described a scheme in which the SubagentStart hook built memory context first against the full `MAX_INJECT_CHARS` budget, and ADRs filled the remainder up to a 2,000-char soft cap. The shipping code, however, does the opposite: it constructs the ADR context first and then fills the remaining budget with memory. This inversion is not a bug — the code is the canonical, tested, production behavior — but the ADR body, title, and option comparison all read "memory-first."

Evidence of the inversion:

- `hooks/inject_memory.py:18` (module docstring) — "ADRs get first priority in the shared `MAX_INJECT_CHARS` budget -- architectural decisions are hard constraints that should never be dropped. Memory fills the remaining space."
- `hooks/inject_memory.py:417` (inline comment) — "ADR context (first priority: architectural decisions are hard constraints)."
- `hooks/inject_memory.py:418-424` — builds ADR block first, subject to a 2,000-char soft cap.
- `hooks/inject_memory.py:426-440` — memory block is built against `MAX_INJECT_CHARS - adr_len`.

Leaving `dec-011` in place would preserve an audit-trail record that contradicts the live architecture — a trap for every future agent that consults the ADR while reasoning about injection behavior.

## Decision

Write this ADR (`dec-023`) as the canonical statement of the hook's budget allocation policy, and mark `dec-011` as superseded by `dec-023`. The shipping code is not modified. `dec-011`'s body is left intact to preserve its audit trail; only its frontmatter changes (`status: proposed` → `status: superseded`, add `superseded_by: dec-023`).

Specifically:

- ADR context is built first, capped by a soft limit (`ADR_SOFT_CAP = 2_000` chars). The soft cap only trims when the aggregate ADR summary would otherwise exceed it; when total ADR content is under the cap, all ADRs are included verbatim.
- Memory context fills the remaining budget (`MAX_INJECT_CHARS - adr_len`), using the existing importance-tiered selection.
- ADR summaries are read from `DECISIONS_INDEX.md`, parsed by simple string splitting on `|` (no regex, no new imports).
- Only `accepted` and `proposed` ADRs are injected; `superseded` and `rejected` entries are filtered out.

Rationale: architectural decisions are compact and function as hard constraints for downstream agent behavior. Memory is elastic and degrades gracefully through the importance ordering. Prioritizing ADRs is the right axiology; the original ADR text simply mis-stated which artifact comes first.

## Considered Options

### Option X1 — Fix the ADR via supersession (chosen)

Write `dec-023` as the correct statement of the policy and set `dec-011` to `status: superseded` with `superseded_by: dec-023`. Add a `## Prior Decision` section to `dec-023` summarizing what `dec-011` originally framed and why the framing was inverted.

**Pros:**
- Zero code risk — production behavior is unchanged.
- Preserves the audit trail (git blame still shows `dec-011` as the original decision; `dec-011`'s body still reads as it did when written).
- Correct documentation from this point forward — every agent consulting `DECISIONS_INDEX.md` gets the live behavior.
- One ADR number consumed (cheap).

**Cons:**
- Two ADR files on the same topic (superseded and superseding) — slight reader overhead until `dec-011` drops out of the active index view.

### Option X2 — Flip the code to match `dec-011`

Rewrite `hooks/inject_memory.py` so memory is built first and ADRs fill the remainder. Keep `dec-011` title/body, promote to `accepted`.

**Pros:**
- No new ADR; fewer frontmatter edits.

**Cons:**
- Breaks the hard-constraint property of architectural decisions — under memory pressure (50+ high-importance entries), ADR context gets squeezed out entirely.
- Contradicts the shipping behavior that was validated by tests at `memory-mcp/tests/test_inject_memory.py` and by months of observed pipeline runs.
- Higher test and integration risk for a purely documentation benefit.

### Option X3 — Split into two ADRs (one documentation, one behavioral)

Write a new ADR narrowly covering the doc-fix and leave `dec-011` as-is for behavior.

**Pros:**
- None substantive.

**Cons:**
- Confuses readers with two overlapping ADRs describing the same injection mechanism.
- Violates supersession protocol (no clear semantic boundary).
- Does not actually resolve the contradiction — `dec-011`'s body still reads "memory-first."

## Consequences

**Positive:**

- Live architecture and ADR record are consistent. Injection behavior remains ADR-first (hard-constraint semantics preserved).
- Agents consuming `DECISIONS_INDEX.md` henceforth read the correct title and body when looking up hook injection policy.
- No code change; no test change; no deployment — this is pure documentation remediation.
- Memory entries referencing hook behavior by mechanism (not by ADR ID) continue to apply without edits.

**Negative:**

- One additional ADR number consumed (`dec-023`).
- `DECISIONS_INDEX.md` status distribution includes a new `superseded` row (`dec-011` → `dec-023`). The index rendering pipeline already handles superseded entries; no tooling change needed.
- Readers encountering `dec-011` in isolation (without the index) must follow the `superseded_by: dec-023` link to reach the live semantics. Mitigated by keeping `dec-011`'s title visible in git history.

**Operational:**

- No runtime or deployment impact — `hooks/inject_memory.py` is untouched.
- `scripts/regenerate_adr_index.py` must be re-run after `dec-011`'s frontmatter flip (handled in Step B7 of the Phase 1 plan).
- Future ADR authors should favor supersession over in-place body edits when a decision's record diverges from reality — this establishes the pattern.

## Prior Decision

`dec-011` (2026-04-04) was titled *"Memory-first budget allocation with ADR soft cap for hook injection."* Its Decision section framed the budget allocation as memory-first: memory output built against the full budget, ADRs filling the remainder under a 2,000-char soft cap. Its Option 3 ("Memory-first with soft cap") was marked as the chosen option.

`dec-011` was written during the design phase of the hook. During implementation, the engineer recognized that ADRs express hard constraints (architectural decisions should never be dropped from agent context) while memory expresses elastic recall, and inverted the order — ADRs first, memory filling the remainder. The code and its tests shipped with that ordering, and the documentation was left unchanged.

`dec-023` supersedes `dec-011` because the record must match the behavior, not the original intent. The axiology change (ADRs as hard constraints) is preserved in the code; the ADR record catches up via supersession.
