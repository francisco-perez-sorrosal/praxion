---
id: dec-039
title: Share memory-gate EXEMPT_AGENTS via _hook_utils single source of truth
status: accepted
category: implementation
date: 2026-04-12
summary: Move EXEMPT_AGENTS frozenset to hooks/_hook_utils.py and import from both validate_memory.py and remind_memory.py; avoids duplication drift
tags: [hooks, memory, dry, single-source-of-truth, refactoring]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - hooks/_hook_utils.py
  - hooks/validate_memory.py
  - hooks/remind_memory.py
affected_reqs: []
---

## Context

`validate_memory.py` (SubagentStop gate) defines `EXEMPT_AGENTS = frozenset({"Explore", "i-am:sentinel", "i-am:doc-engineer", "Plan"})`. `remind_memory.py` (PreToolUse gate triggered on `git commit`) has no equivalent list. ROADMAP.md Phase 2.4 prescribes adding the same list to `remind_memory.py`.

Naively, this is a two-line copy-paste. The design question: **duplicate the literal, or centralize it?** Duplication will drift — the next agent added/removed from the SubagentStop exemption list will be forgotten in `remind_memory.py`, and the two gates will silently disagree. The two gates fire in different contexts, but the *rationale* for exemption (read-only agent, no meaningful "work" to persist) is the same in both cases.

## Decision

Move `EXEMPT_AGENTS` to `hooks/_hook_utils.py` as a module-level `frozenset` constant. Both `validate_memory.py` and `remind_memory.py` import it from there. Neither hook defines its own copy.

The exemption list is **identical** in both hooks — `Explore`, `i-am:sentinel`, `i-am:doc-engineer`, `Plan`. The rationale (read-only agent; no production-affecting work) is context-independent: whether the trigger is SubagentStop or pre-commit, these agents have nothing to `remember()`. A divergence would be a bug, not a feature.

`remind_memory.py` checks the exemption in addition to its existing `git commit` detection. Lookup uses `payload.get("agent_type", "")` — the same key `validate_memory.py` uses. For `remind_memory.py`, the agent_type field may be absent in PreToolUse payloads for the main agent; absence means "main agent" which is **not** exempt, so the default-empty-string behavior naturally keeps the gate active in the common case.

## Considered Options

### Option A — Duplicate the frozenset literal in both files

- **Pros**: Minimal blast radius; each file self-contained.
- **Cons**: Two sources of truth that must be kept in sync manually. A future agent addition (e.g., adding `i-am:roadmap-cartographer` to the exemption) will land in one file and not the other. Silent divergence bug.

### Option B — Module-level constant in _hook_utils.py, imported by both (chosen)

- **Pros**: One source of truth. Matches the existing pattern — `_hook_utils.py` already houses `REMEMBER_PROMPT`, `scan_transcript`, `is_memory_system_active` used by both hooks. Low friction: one line in each hook changes from `EXEMPT_AGENTS = frozenset({...})` to `from _hook_utils import EXEMPT_AGENTS`.
- **Cons**: Slightly indirect — a reader of `validate_memory.py` must open `_hook_utils.py` to see the list. Mitigation: the import is explicit and the constant name is unambiguous.

### Option C — Divergent lists (different exemptions per gate)

- **Pros**: Allows fine-grained per-gate policy (e.g., "sentinel is exempt at SubagentStop but not at commit").
- **Cons**: No real-world rationale supports divergence today — all four exempt agents are read-only by design, and the reason they have nothing to persist is the same at both gates. Designing for a hypothetical future divergence complicates the current system for zero present benefit. If divergence is ever needed, introduce two constants then; until then, one constant is the correct simplification.

### Option D — Config file (e.g., hooks/exempt_agents.json)

- **Pros**: User-editable without touching Python.
- **Cons**: Adds a file-load at every hook invocation (hooks run per-event; keep them fast). Memory-gate exemptions are an ecosystem-level invariant, not user configuration — they belong in code.

## Consequences

**Positive**:

- Future changes to exempt agents touch one line in one file. No drift possible between the two gates.
- `_hook_utils.py` grows a tiny, discoverable constant alongside the other shared utilities it already exposes.
- `remind_memory.py`'s behavior is now consistent with `validate_memory.py`: read-only agents are not nagged to remember.

**Negative**:

- Adds a module-level symbol to `_hook_utils.py`. Negligible — the module already houses shared utilities; this is its purpose.

**Neutral**:

- Agent set is unchanged at time of this ADR. When the set needs to change, update `_hook_utils.EXEMPT_AGENTS` once; both gates pick it up automatically.
