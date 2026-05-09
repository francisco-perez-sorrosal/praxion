# Tech-Debt Ledger Schema and Lifecycle

Reference for `.ai-state/TECH_DEBT_LEDGER.md` (active) + `.ai-state/TECH_DEBT_RESOLVED.md` (terminal). Loaded on demand by the agents that read or write the ledger pair (verifier, sentinel, orchestrator, architect-validator, and the consumer agents that update existing rows).

Back-link: [`../SKILL.md`](../SKILL.md) · Index entry in [`../../../rules/swe/agent-intermediate-documents.md`](../../../rules/swe/agent-intermediate-documents.md#tech_debt_ledger-summary) (5-line summary).

## Overview

`.ai-state/TECH_DEBT_LEDGER.md` and its sibling `.ai-state/TECH_DEBT_RESOLVED.md` form a **two-file pair** holding grounded debt findings — problems anchored in current source code against current system goals (or vice versa). Structurally distinct from `LEARNINGS.md` (gotchas/patterns), idea ledgers (speculative work), and roadmap narration (strategic weaknesses). Active ledger holds `status ∈ {open, in-flight}`; resolved file holds `status ∈ {resolved, wontfix}`. One logical namespace: `id` (`td-NNN`) and `dedup_key` are unique across both files; cross-references cite `td-NNN` regardless of which file holds it.

## Writers (only four)

- **verifier** — appends per-change findings (dead-code survivors, bloat, duplication, size/nesting breaches) during Phase 5/5.5
- **sentinel** — appends repo-wide findings via its TD dimension (hotspots, cyclic SCCs, coverage-floor breaches, p95 complexity crossings); TD05 audits the ledger but never writes
- **orchestrator** — the main agent appends rows under explicit user direction when a grounded finding fits neither verifier's per-change nor sentinel's periodic-audit scope. Exception, not routine; verifier/sentinel may re-source orchestrator rows on later runs
- **architect-validator** — appends per-PR drift findings (`class: drift`, `goal-ref-type: architecture`, `owner-role: systems-architect`) in `--mode=pre-merge` or `--mode=on-demand`. Reserved for code↔DSL↔ADR triangle validation

Consumer agents (systems-architect, implementation-planner, implementer, test-engineer, doc-engineer) read the ledger, filter by their `owner-role`, and update `status` / `resolved-by` / `last-seen` on existing rows when they address an item. No agent outside the four writers above creates new ledger rows.

## Lifecycle conventions

- **Append-only at write** — producers append new rows to the **active LEDGER** (never to RESOLVED.md directly)
- **Status updates in place** — consumers update `status`, `resolved-by`, and `last-seen` in whichever file currently holds the row
- **Migration on terminal-status** — when a row's `status` transitions to `resolved` or `wontfix`, the entire row moves (cut + paste) from LEDGER to RESOLVED. The move is performed by `scripts/finalize_tech_debt_ledger.py` at post-merge, and may also be done in-commit by the resolving agent or human
- **Re-open on recurrence** — if a producer files a new active row whose `dedup_key` matches a row in RESOLVED, the resolved row moves back to LEDGER with `status = open`, `last-seen = today`, and `notes` suffixed `// recurrence: re-opened YYYY-MM-DD`. The newly-filed row is collapsed into it (preserving the historical row's `id` and `first-seen`)
- **Audit trail preserved** — both files are committed to git; rows are never deleted from the pair as a whole. `wontfix` is a tombstone in RESOLVED.md (sentinel may re-surface but never removes)
- **Reclassification recomputes `dedup_key`** — when a producer changes a row's `class` (e.g., `other` → `token-budget`), the producer recomputes `dedup_key` from the new field set so future findings can match
- **No section ownership** — each file is a single Markdown table with a small header; section ownership is unnecessary

## Schema (14 row fields + 1 structural `dedup_key` field)

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| `id` | string | `td-NNN` zero-padded sequence | Stable across status updates; assigned at write time by next-available-NNN scan |
| `severity` | enum | `critical` \| `important` \| `suggested` | Aligned with sentinel severity tiering |
| `class` | enum | `duplication` \| `complexity` \| `dead-code` \| `drift` \| `stale-todo` \| `coverage-gap` \| `cyclic-dep` \| `topology-drift` \| `token-budget` \| `other` | `other` is an escape hatch — propose a new enum value when `other` rows exceed 5. Re-classify into a named class when notes match (e.g., test-topology staleness → `topology-drift`; always-loaded budget cut → `token-budget`); recompute `dedup_key` on reclassification |
| `direction` | enum | `code-to-goals` \| `goals-to-code` | The two debt directions in the operating definition |
| `location` | list | Affected file paths + optional `:start-end` line ranges | One path per list entry; ranges use `path/to/file.py:42-58` syntax |
| `goal-ref-type` | enum | `adr` \| `spec-req` \| `architecture` \| `claude-md` \| `code-quality` | `code-quality` covers universal engineering principles with no Praxion-specific anchor |
| `goal-ref-value` | string | ADR id (`dec-NNN`) \| REQ id (`REQ-NN`) \| DESIGN.md section path \| CLAUDE.md principle name \| empty (only when `goal-ref-type = code-quality`) | |
| `source` | enum | `verifier` \| `sentinel` \| `orchestrator` \| `architect-validator` | Producer identity. `orchestrator` is reserved for explicit-user-direction main-agent writes; `verifier` and `sentinel` remain the canonical producers. `architect-validator` is reserved for per-PR structural-drift findings. |
| `first-seen` | ISO date | `YYYY-MM-DD` | Set once at row creation; never updated |
| `last-seen` | ISO date | `YYYY-MM-DD` | Updated on every re-detection by the same `source` |
| `owner-role` | enum | `systems-architect` \| `implementation-planner` \| `implementer` \| `test-engineer` \| `doc-engineer` \| `unassigned` | Assigned by producer per the heuristic below; downstream consumer MAY re-assign with notes |
| `status` | enum | `open` \| `in-flight` \| `resolved` \| `wontfix` | Updated in place by consumer agents |
| `resolved-by` | string | ADR id, commit SHA, or PR URL when `status = resolved`; empty otherwise | `wontfix` SHOULD populate `notes` with rationale rather than `resolved-by` |
| `notes` | string | Short prose — intent, rationale, scope hints, override-survivor flag | One sentence preferred; multi-line discouraged |
| `dedup_key` | string | `sha1(f"{class}\|{normalize(location)}\|{direction}\|{goal-ref-type}\|{goal-ref-value}")[:12]` | Computed at write time; structural; used by post-merge dedupe |

`normalize(location)` is the sorted, comma-joined list of paths (no line ranges) — so two rows that differ only in line range or path order produce the same `dedup_key`.

## Owner-role heuristic (canonical class-to-role mapping)

Both producers reference this single table when assigning `owner-role` to a new row. Downstream consumers may re-assign with a note in the `notes` field.

| `class` enum value | Default `owner-role` | Override conditions |
|-------------------|---------------------|---------------------|
| `duplication` | `implementer` | `architecture` goal-ref → `systems-architect`; cross-module systemic → `implementation-planner` |
| `complexity` | `implementer` | Module restructuring required (interface split, layer reshuffle) → `implementation-planner`; invariant violation → `systems-architect` |
| `dead-code` | `implementer` | In `tests/` directory → `test-engineer`; doc-only → `doc-engineer` |
| `drift` | `doc-engineer` | `goal-ref-type = adr` or `architecture` → `systems-architect` |
| `stale-todo` | `unassigned` | `notes` field tags an owner explicitly → that role; location in `tests/` → `test-engineer` |
| `coverage-gap` | `test-engineer` | None — coverage is always test-engineer-owned |
| `cyclic-dep` | `implementation-planner` | Always — module-graph reshuffle is a planning concern |
| `topology-drift` | `implementation-planner` | Always — topology refresh requires a planning-level decision (group splits, merges, or integration_boundary changes) |
| `token-budget` | `implementer` | Doc-style edits to rule files; escalate to `implementation-planner` only when the cut requires coordinating skill frontmatter or agent injection |
| `other` | `unassigned` | Producer's `notes` field SHOULD propose an owner; downstream consumers may re-assign |

## Worktree concurrency

Pipelines in separate worktrees write independently; conflicts reconcile at merge-to-main via `scripts/finalize_tech_debt_ledger.py` (modeled on `scripts/finalize_adrs.py`: idempotent, advisory `fcntl` lock, bounded scope, dry-run flag). On collapse: status precedence `resolved > in-flight > open > wontfix`, tie-break by newer `last-seen`; non-conflicting fields merge (notes concatenated with ` // ` — separator chosen to avoid collision with Markdown table delimiter `|`; locations union-sorted; earliest `first-seen` preserved). Re-open semantics: when a new active row's `dedup_key` matches a row in RESOLVED, the resolved row moves back to LEDGER as `status = open` with a recurrence note, and the new row collapses into it.

## Consumer-contract framing

The ledger's input contract on its five consumer agents is **permission, not obligation** — non-action is a valid outcome. The contract line does not make every consumer process every open item on every run, which would degrade per-agent phase-budget discipline.
