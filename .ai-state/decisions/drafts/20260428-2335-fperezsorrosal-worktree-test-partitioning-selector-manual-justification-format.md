---
id: dec-draft-ea2aa5fd
title: selector=manual justification is a closed enum with an "other" escape hatch
status: proposed
category: implementation
date: 2026-04-28
summary: When the implementation-planner overrides auto-derived group selection (selector=manual), the step body includes a one-line justification drawn from a closed enum (scope-mismatch, cross-pocket-bridge, topology-stale, tier-escalation-debug, other) plus an optional free-form note when "other". This makes manual-override frequency parseable for future sentinel checks while preserving an escape hatch for unexpected reasons.
tags: [test-topology, selector, manual-override, schema, audit, sentinel]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - skills/software-planning/SKILL.md
  - skills/software-planning/references/document-templates.md
  - agents/verifier.md
---

## Context

Open Question 4 from `RESEARCH_FINDINGS.md` §E.4. The step schema's `Tests:` field includes a `selector=<auto|manual>` value. `auto` means the planner derived the group set from the step's `Files` field; `manual` means the planner overrode the auto-derivation. §C.2.1 says: "a `manual` selection requires a 1-line justification in the step's body." The architect was asked to choose between:

- A closed enum of justification reasons (parseable, enforceable)
- Free-form prose (flexible, reader-friendly, but unstructured)
- Some hybrid

The downstream consumer is the verifier (today: cross-references `Tier` and `Groups` per `agents/verifier.md` Phase 5 extension; future: a possible "manual override frequency" sentinel check that flags topology rot when manual selection becomes routine).

## Decision

**Closed enum with an "other" escape hatch + optional one-line note.**

The enum:

| Value | Meaning |
|-------|---------|
| `scope-mismatch` | The auto-derived groups do not match the step's actual scope (e.g., the step touches a file outside any group's `file_dependencies` and a manually-added group is the right answer). |
| `cross-pocket-bridge` | The step touches a cross-pocket bridge file (e.g., `hooks/inject_memory.py`) and the planner is manually adding the bridged group's tests because the auto-derivation missed the bridge. |
| `topology-stale` | The planner is overriding because the topology is known to be stale (e.g., a recent renamed subsystem); a `topology-drift` ledger row should follow. |
| `tier-escalation-debug` | The planner is escalating to a higher tier (or wider group set) for debugging or risk-mitigation reasons specific to this step. |
| `other` | None of the above; an inline one-line note is required. |

Schema in the step body:

```markdown
**Tests**: groups=[memory-store-core, hooks-inject-memory] tier=phase selector=manual reason=cross-pocket-bridge
```

When `reason=other`, an inline note is required:

```markdown
**Tests**: groups=[memory-store-core] tier=step selector=manual reason=other note="planner uncertain whether new test belongs in this group; pending architect input"
```

## Considered Options

### Option A — Free-form prose

Single sentence in the step body, no structure.

**Pros:**
- Flexible — covers any imaginable reason.
- Reader-friendly — no enum lookup to interpret.

**Cons:**
- Not parseable. Verifier cannot count "how many manual overrides this pipeline" without LLM-based judgment.
- Sentinel cannot meaningfully flag "manual override frequency" — the criterion would be "the count of manual override prose lines is high," which is fragile against rephrasing.
- Drift over time: prose conventions decay; reasons become repetitive ("planner judgment"); the audit value erodes.

### Option B — Closed enum (no escape hatch)

Strict enum with no "other" case.

**Pros:**
- Maximally parseable.
- Forces classification.

**Cons:**
- Brittle. Real-world override reasons emerge that don't fit the enum, and the planner has to either lie (pick a wrong reason) or block (await an ADR to expand the enum). Both are bad.
- Premature freezing — at M1 we don't have empirical data on what override reasons actually arise. A frozen enum encodes today's guesses as tomorrow's constraints.

### Option C — Closed enum with "other" escape hatch + optional note (chosen)

**Pros:**
- Parseable for the common cases (the four enum values cover the empirically-expected reasons from the researcher's analysis).
- Escape hatch handles novel reasons without blocking work.
- The `other` count is itself a metric: if `other` becomes the most common value, the enum is wrong and an ADR should expand it. Sentinel can monitor this.
- The optional `note=` field on `other` is parseable as a key=value pair, so "list all `other` reasons" is a single grep.

**Cons:**
- Two-state field (enum value vs free-form note); slightly more complex than pure prose. Mitigation: small overhead, recovered by parseability.
- The four enum values are educated guesses. They may be wrong in subtle ways. Mitigation: the enum is purely additive; new reasons land via ADR. Removing a reason is also additive (mark deprecated, leave in place for historical entries).

## Consequences

### Positive

- The `Tests:` schema field has a complete parseable surface.
- Manual overrides are auditable — a future "manual override frequency by reason" check is implementable as a one-line sentinel.
- The `other` escape hatch keeps developer experience friction low.
- The enum can grow over time with explicit ADR governance, matching the rest of the protocol's evolution model.

### Negative

- Adds enum lookup to the planner's step-decomposition workflow. Mitigation: the four values are short and memorable; the planner's existing step-schema knowledge already includes more complex decisions.
- The implementation-planner SKILL must document the enum (one short table). Acknowledged.

### Reversibility

Easily reversible per direction:
- Adding a new enum value: trivial ADR.
- Removing a value: deprecate-then-remove pattern (additive deprecation, then a cleanup ADR after a release window).
- Switching to pure free-form: would require migrating all historical `selector=manual` entries; the cost is the cost. But since the migration is forward-only (you can always read old prose), it's not catastrophic.

## Prior Decision

None.
