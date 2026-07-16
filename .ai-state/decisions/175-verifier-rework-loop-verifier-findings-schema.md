---
id: dec-175
title: VERIFIER_FINDINGS.md is a self-contained problem statement consumed by stock systems-architect / implementation-planner
status: accepted
category: architectural
date: 2026-05-14
summary: VERIFIER_FINDINGS.md carries a fixed-section markdown schema (Problem / Scope / Evidence / Success Criteria / Ledger Links / Suggested Tier / Provenance) that the receiving agent reads as if it were any other task-intake document — no rework-specific dispatching logic in agents/.
tags: [verifier, rework, findings, agentic-contract, hard-to-misuse]
made_by: agent
agent_type: interface-designer
branch: worktree-verifier-rework-loop
pipeline_tier: standard
affected_files:
  - agents/verifier.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - commands/resume-rework.md
re_affirmed_by:
  - dec-178
---

## Context

The feature's load-bearing hypothesis: `VERIFIER_FINDINGS.md` is engineered as a *self-contained problem statement* — receiving agents (architect or planner) need no rework-specific logic to act on this file.

Two design forces:

1. **Bloch — hard to misuse.** The agent reading the file must not need a rework codepath. If a stock pipeline-Phase-1 read of `RESEARCH_FINDINGS.md` / `SYSTEMS_PLAN.md` works, a stock pipeline-Phase-1 read of `VERIFIER_FINDINGS.md` should also work. That means the file must contain the same kinds of fields the agent already knows how to read.
2. **Agentic-interface — names are the interface.** Section headings (`## Problem`, `## Scope`, `## Success Criteria`) carry semantic load equal to a tool's `description`. The LLM re-reads these headings every turn and decides what to do. The names must be unambiguous on a single read.

## Decision

`VERIFIER_FINDINGS.md` carries seven fixed top-level sections, written verbatim, in this order. The receiving agent (architect or planner) is dispatched from `/resume-rework` and immediately enters its own Phase 1 with no rework-specific instructions in its prompt — the file IS the prompt.

```markdown
# Rework: <one-line problem statement>

## Problem

[Plain-language narrative of what's wrong. 1–3 paragraphs. Apply
the X-failed-because-Y agent-error grammar but adapted for code review:
"<area> failed verification because <root cause>. The simplest
plausible fix is <Z>, but the architect/planner is the deciding voice."]

## Scope

### In scope
- <file:line ranges or module names — what the rework session may touch>

### Out of scope
- <file:line ranges or modules — explicitly off-limits>

## Evidence

- `<path>:<line>` — `<short snippet or behavior description>` — from `[VERIFICATION_REPORT.md#fail-N]`
- `<path>:<line>` — ...

## Success Criteria

- [ ] <criterion 1: the observable behavior that proves the smell is resolved>
- [ ] <criterion 2>

(These are NOT acceptance criteria — they will become acceptance criteria
when the architect or planner writes SYSTEMS_PLAN.md / IMPLEMENTATION_PLAN.md.
They are the verifier's claim of what "resolved" looks like.)

## Ledger Links

- td-NNN — <one-line summary> — `[TECH_DEBT_LEDGER.md#td-NNN]`
- (or "No tech-debt-ledger rows linked")

## Suggested Tier

`<direct|lightweight|standard|full>` — <one-line reason>

(Advisory only. The receiving agent re-applies the tier selector itself.)

## Provenance

- Source report: `[VERIFICATION_REPORT.md](#)` (path relative to the parent worktree)
- Parent worktree: `<name>`
- Parent task slug: `<slug>`
- Rework ID: `rw-<8-char-hash>` (matches REWORK_MANIFEST.md row id)
- Verifier confidence: `<high|medium|low>`
- Generated: `<ISO-8601>`
```

### Why these exact section names

| Section | Why this name (Bloch / agentic-interface) |
|---------|-----------|
| `## Problem` | Already what the architect reads at Phase 1 ("clarify the goal — restate it in one sentence"); zero new vocabulary. |
| `## Scope` (In scope / Out of scope) | Already the architect's Phase 1 "Identify scope boundaries"; mirrors the systems-architect's own output schema. |
| `## Evidence` | Verifier's voice — concrete `file:line` references. Anchors back to `VERIFICATION_REPORT.md` for full context if needed. |
| `## Success Criteria` | Deliberately NOT "acceptance criteria" — that term is reserved for `SYSTEMS_PLAN.md`. "Success criteria" signals "the architect/planner will translate these". |
| `## Ledger Links` | Cross-references the persistent debt ledger by `td-NNN`. The receiving agent reads the ledger row directly for full context. |
| `## Suggested Tier` | Advisory — explicitly framed so the receiving agent re-applies tier selection. Prevents the verifier from short-circuiting calibration. |
| `## Provenance` | Hard requirement: provenance is what makes the file fail-fast — if `rw-<hash>` doesn't match a row in REWORK_MANIFEST.md, the receiving agent knows the file is stale. |

## Considered Options

### Option A — Embed a prompt for the receiving agent at the top

Pros: most explicit; receiving agent can't get lost.

Cons: ties the file format to the agent's prompt, which evolves; introduces rework-specific logic at the file level (violates the load-bearing hypothesis). Also: redundant — `/resume-rework` already dispatches to the right agent with the right context.

Rejected.

### Option B — JSON / YAML structured findings file

Pros: parseable; smaller schema.

Cons: receiving agents already consume markdown task-intake files; introducing a new format is a hard-to-misuse violation in reverse (the agent must learn a new path). The markdown above is already structured enough.

Rejected.

### Option C — Fixed-section markdown schema (chosen)

Pros: receiving agent reads it like it reads `SYSTEMS_PLAN.md` (markdown sections, Phase 1 inputs). Zero rework-specific logic in `agents/*.md`. Section names match existing pipeline vocabulary. Provenance + rework-ID lets the file fail fast if stale.

Cons: prose `## Problem` section is somewhat free-form; quality depends on the verifier's writing. Mitigation: verifier templates a stock paragraph from the finding cluster and report tags.

**Chosen.**

## Consequences

**Positive:**
- No `agents/systems-architect.md` or `agents/implementation-planner.md` changes required to add the rework loop. Confirmed by reading both files: Phase 1 already reads `SYSTEMS_PLAN.md` / `RESEARCH_FINDINGS.md` from `.ai-work/<task-slug>/` — a `VERIFIER_FINDINGS.md` in the same directory will be read by the same Phase 1.
- `/resume-rework` is a thin dispatcher (load `VERIFIER_FINDINGS.md`, pick `target_agent` from the manifest, spawn).
- Receiving agent's tier-selection logic is exercised — verifier's `Suggested Tier` is advisory, never decisive.

**Negative:**
- Verifier must learn to write the seven sections cleanly. Template + lint check at write-time mitigates this.
- The `## Problem` narrative is the highest-variance section; quality bounds the receiving agent's quality.

**Hard-to-misuse check:**
- If `## Success Criteria` is missing: receiving agent fails fast with "VERIFIER_FINDINGS.md missing § Success Criteria — re-run verifier or hand-edit".
- If `rw-<hash>` doesn't match the manifest: `/resume-rework` refuses to dispatch.
- If the verifier writes `## Acceptance Criteria` instead of `## Success Criteria` (vocabulary slip): fail at write-time with the lint check; rename in the template, not in the receiver.

**Architect / planner agent obligations (additive, minimal):**
- A single sentence in `agents/systems-architect.md` Phase 1 step 1: "If `VERIFIER_FINDINGS.md` is present and no `RESEARCH_FINDINGS.md` exists, read it as the primary task-intake document."
- Same sentence in `agents/implementation-planner.md` Phase 1.
- No new code paths, no rework-specific branches, no behavior change otherwise.
