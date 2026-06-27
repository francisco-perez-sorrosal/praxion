---
id: dec-draft-e6199a12
title: Retire the historical-retained lifecycle state with its sole member token_budgeting
status: proposed
category: configuration
date: 2026-06-27
summary: Delete the dead .ai-state/token_budgeting/ dir and retire the historical-retained lifecycle state it was the only member of, reversing a prior-audit sanction.
tags: [artifact-store, lifecycle-states, hygiene, token-budgeting, waste-pruning]
made_by: user
branch: wave4a-waste-pruning
pipeline_tier: standard
affected_files:
  - .ai-state/token_budgeting/
  - rules/swe/agent-intermediate-documents.md
  - skills/software-planning/references/artifact-inventory.md
---

## Context

`.ai-state/token_budgeting/` held two `TOKEN_BUDGETING_*.md` audits from 2026-02-09 and no
active producer — the token-budgeting feature that wrote them is long inert. The prior
artifact-lifecycle audit deliberately classified it `historical-retained` ("present only in
older projects / as history") and sanctioned keeping it. The later process-flow analysis
(`docs/independent-analysis/praxion-artifact-process-flow-analysis.md`, finding C4 / R17) flagged
it as a dead directory in the live store and deferred the keep-vs-delete call to Wave 4 because
removing it conflicts with that sanctioned state.

`token_budgeting/` was the **sole member** of the `historical-retained` lifecycle state, so the
decision is really two coupled questions: delete the directory, and what to do with a lifecycle
state that would then have zero members.

## Decision

**Delete `.ai-state/token_budgeting/` and retire the `historical-retained` lifecycle state.**
Git history is the archive — the two files remain recoverable from history; they simply leave the
live working tree. The lifecycle-state taxonomy drops from five states to four (`active`,
`optional-lazy`, `threshold-lazy`, `future-designed`) in both `rules/swe/agent-intermediate-documents.md`
(the canonical tree + state table) and `skills/software-planning/references/artifact-inventory.md`
(the state definitions + per-artifact assignment).

## Considered Options

### Option A — Keep + re-affirm historical-retained

- **Pros:** zero churn; honors the prior audit's deliberate sanction; two tiny files are harmless.
- **Cons:** keeps a dead directory and an empty-but-for-one-member lifecycle state in the live store
  indefinitely; the "live store is only live artifacts" invariant stays muddied; every future reader
  re-litigates "why is this here?"

### Option B — Delete + retire the state (CHOSEN)

- **Pros:** the live `.ai-state/` holds only artifacts with a present-or-future producer; the
  lifecycle taxonomy loses a state with no members (simpler model); history still archives the files.
- **Cons:** reverses a sanctioned state; a future project that wants a "retained history, no producer"
  category would have to reintroduce it.

### Option C — Defer again

- **Pros:** no decision risk.
- **Cons:** the same unresolved dead-dir question rolls forward; deferral was already the prior outcome.

## Consequences

**Positive:**
- The live store contract tightens: every `.ai-state/` directory now has an active or designed-future producer.
- One fewer lifecycle state to teach and reason about.

**Negative / costs:**
- Reverses a prior-audit sanction (see Prior Decision); if a genuine "retained history" need reappears,
  the state must be reintroduced with a real member.
- `historical-retained` references survive only in frozen history (older sentinel reports, the prior
  audit doc, `dec-050`) — intentionally untouched as factual history.

## Prior Decision

This reverses the prior **artifact-lifecycle audit's** sanction of `historical-retained` for
`token_budgeting/` (an audit finding, not a formal ADR, so this is a reversal of a sanctioned state
rather than an ADR supersession). The reversal is warranted because the sanction's premise — "retained
because it may matter as history" — is better served by git history than by a live-store directory with
no producer. A future reintroduction would need an artifact that is genuinely retained-with-no-producer
*and* whose history must live in the working tree rather than git — neither holds for token-budgeting.
