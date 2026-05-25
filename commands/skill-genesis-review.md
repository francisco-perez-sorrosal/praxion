---
description: Disposition pending proposals from a skill-genesis report — batch multi-select; records approve/reject/refine/defer per proposal; executes approved memory proposals; surfaces delegation handoffs.
argument-hint: "[--report <path>] [--show-completed]"
allowed-tools: [Read, Glob, Grep, Bash, Edit, AskUserQuestion]
disable-model-invocation: true
---

Work through pending proposals from the most recent (or specified) skill-genesis report.
Presents every pending proposal in a single batch `AskUserQuestion` multi-select, records
each disposition in the report's `## Disposition Log` section, executes approved `memory`
proposals via the `remember` MCP tool, and surfaces delegation handoffs for skill/rule/claude.md
proposals. Re-running this command on a fully-reviewed report is a no-op.

## Flags

| Flag | Description |
|------|-------------|
| `--report <path>` | Override auto-discovery; use this specific report file. |
| `--show-completed` | Include fully-dispositioned reports in the discovery scan (default: skip completed). |

## Process

### 1. Report discovery

If `--report <path>` is given, use that file directly (exit with an error if not found).

Otherwise, scan `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_*.md` and pick the
most recent file whose frontmatter `review_status` is `pending` or `partial`. Sort by
filename descending (timestamps sort lexicographically, so newest file = highest filename).

If `--show-completed` is set, include `review_status: complete` files in the scan.

**No pending reports found**: if the scan finds no unreviewed reports, exit with:

```
No pending skill-genesis reports found.
Run /skill-genesis to produce a new harvest report.
```

This is the idempotency case: re-running after a fully-dispositioned report exits cleanly.

### 2. Parse proposals

Read the report. Extract every proposal block (`### Proposal N: ...`) where the
`**Disposition**` field is `pending` or `pending refinement`.

If no pending proposals remain (the report has `review_status: complete`):

```
Report <filename> is fully reviewed (all proposals dispositioned).
Review status: complete.

Next unreviewed report: <path> (or "none")
Run /skill-genesis to harvest new learnings.
```

Exit without presenting a multi-select.

### 3. Batch presentation

Build a single `AskUserQuestion` multi-select with one option per pending proposal.
Each option label: `Proposal N: <name> (<type>, <priority>)`.

If N > 20, paginate into groups of 10 — present one page at a time.

The question prompt explains the four disposition values:
- **approve** — accept the proposal; will be delegated or executed after this pass
- **reject** — discard the proposal; no action taken
- **refine** — keep the proposal in `pending refinement` state; revisit in the next `/skill-genesis-review` pass with a free-form note
- **defer** — postpone the decision; remains pending for a future pass (no note required)

### 4. Per-proposal disposition

For each proposal the user selected (in order):

1. Ask a four-way single-select: **approve / reject / refine / defer**.
2. If **refine** is chosen, ask a follow-up free-form `AskUserQuestion` (with
   `freeFormInputAllowed: true`) to collect the refinement note. Store the note in the
   disposition log row.
3. Record the chosen disposition internally for the batch update in step 5.

### 5. Append to the Disposition Log

Use `Edit` to append one row per dispositioned proposal to the `## Disposition Log`
section in the report file.

Row format:

```
| <ISO-8601 timestamp> | Proposal N: <name> | <disposition> | <note or —> |
```

**Never rewrite existing log rows** — append only. This append-only contract is what
makes re-running `/skill-genesis-review` on a partially-reviewed report safe: prior
disposition rows are always preserved.

### 6. Update report frontmatter and run-log

Use `Edit` to update the report file's frontmatter fields in place:

- `review_status`: recompute from remaining pending counts:
  - `pending` → `partial` if at least one disposition was recorded but ≥1 proposal is
    still pending or pending-refinement
  - `partial` → `complete` if no proposals remain pending or pending-refinement
- `disposition_count`: update each counter (pending, approved, rejected, refined, deferred)

Also update the `Review Status` column for this report's row in
`.ai-state/skill_genesis_reports/SKILL_GENESIS_LOG.md` using `Edit`.

### 7. Execute approved memory proposals

For each proposal with type `memory` that the user approved, call the `remember` MCP tool
with the proposal's description and source citations as the memory content.

Before calling `remember`, check for `PRAXION_DISABLE_MEMORY_MCP=1` and whether the
`remember` tool is available. If memory MCP is disabled or unavailable, skip silently
and note in the disposition log row: `memory MCP disabled — stored in report only`.

Record the resulting memory key in the disposition log row's Notes column.

### 8. Surface delegation handoffs

For each approved proposal whose type is `skill (new)`, `skill (update)`, `rule (new)`,
`rule (update)`, or `claude.md`:

Print a delegation command the user can run. For example:

```
Approved: Proposal 1 — Deferred Import Pattern for BDD/TDD RED Handshake (skill, new)
  → Run: context-engineer to create skills/testing-strategy/references/deferred-import-pattern.md
    Prompt: "Create the skill reference at <suggested artifact path>. Proposal: <description>"

Approved: Proposal 3 — Static Analysis Test Strategy for Markdown Agent Definitions (rule, new)
  → Run: context-engineer to create rules/swe/markdown-agent-testing.md
    Prompt: "Create the rule at <suggested artifact path>. Proposal: <description>"
```

Ask the user via `AskUserQuestion`:

```
Would you like to spawn the context-engineer delegations now, or defer to a later session?
```

Options: **spawn now** / **defer**.

If the user selects **spawn now**, invoke each delegation via `Task`. If **defer**,
print a summary of the deferred delegations for the user to action later.

### 9. Final summary

Print a final summary:

```
Disposition pass complete.

  Approved:  K proposal(s)
  Rejected:  J proposal(s)
  Refined:   R proposal(s) (remain as pending refinement for the next pass)
  Deferred:  D proposal(s) (remain pending for the next pass)
  Remaining: M proposal(s) still pending

Report: <path>
Review status: <pending | partial | complete>
```

## Proposal types and delegation routing

| Type | Delegation route | Notes |
|------|------------------|-------|
| `skill (new)` | `context-engineer` | Load skill-crafting; pass proposal description + artifact path |
| `skill (update)` | `context-engineer` | Load skill-crafting; pass proposal description + existing path |
| `rule (new)` | `context-engineer` | Load rule-crafting; pass proposal description + artifact path |
| `rule (update)` | `context-engineer` | Load rule-crafting; pass proposal description + existing path |
| `memory` | Direct `remember` call | Executed in step 7; no further delegation |
| `claude.md` | User action or `implementer` | CLAUDE.md edits may require context-specific judgment; surface for user decision |

## Idempotency contract

The command is safe to re-run:

- It only presents proposals where `Disposition` is `pending` or `pending refinement`; already-dispositioned proposals are never re-presented.
- Log rows are appended, never rewritten — the audit trail accumulates without duplication.
- A fully-reviewed report (all proposals dispositioned, none remain pending) exits immediately with a no-op summary.
