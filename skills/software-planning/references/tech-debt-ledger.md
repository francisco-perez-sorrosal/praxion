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

### Architect Phase 2.5 — consumer-only flip protocol (no writer-set expansion)

The systems-architect's Phase 2.5 (Pre-Refactor Assessment) operates as a **consumer**, not a writer — the four-writer policy is preserved. When Phase 2.5 emits `PRE_REFACTOR_PLAN.md`, the architect systematically flips matching existing rows from `open → in-flight` at plan-write time and records the affected `td-NNN` IDs under `## Affected td-NNN rows` in the plan. Row-selection eligibility is mechanical: each claimed row must be `status: open` AND its `location` must overlap the documented refactor scope AND its `owner-role` must be in `{systems-architect, implementation-planner}`. No new rows are created during Phase 2.5; the architect cannot fabricate debt.

At mini-pipeline completion (verifier PASS, or user accepts a verifier-bypass per `## Verifier Bypass Criteria`), the orchestrator — or the re-entered architect in `post-refactor-adaptation` mode — flips the same rows `in-flight → resolved`, populating `resolved-by` with the pipeline/PR reference. The standard `scripts/finalize_tech_debt_ledger.py` migration at post-merge moves resolved rows to `TECH_DEBT_RESOLVED.md` per the lifecycle conventions below; no Phase 2.5-specific finalize logic is needed.

This is a *clarification* of the existing consumer contract — not a schema change, not a writer-set expansion, and not a new field. The same in-place `status` update mechanism documented above is the one Phase 2.5 uses; the architect merely applies it systematically across a scoped row set rather than ad-hoc per finding.

## Lifecycle conventions

- **Append-only at write** — producers append new rows to the **active LEDGER** (never to RESOLVED.md directly)
- **Status updates in place** — consumers update `status`, `resolved-by`, and `last-seen` in whichever file currently holds the row
- **Migration on terminal-status** — when a row's `status` transitions to `resolved` or `wontfix`, the entire row moves (cut + paste) from LEDGER to RESOLVED. The move is performed by `scripts/finalize_tech_debt_ledger.py`, which the finalize hook chain runs on **any on-main commit** (post-commit, post-checkout, or post-merge) — independent of whether ADR drafts are present — and it may also be done in-commit by the resolving agent or human
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

## Producer overlays

Field definitions, enums, and `dedup_key` live in § Schema above. Each writer populates **all** fields from that table, then applies only its overlay below for triggers, finding-to-field mapping, and producer-specific defaults. Do not duplicate the schema table in agent prompts.

**De-duplication at write time (all producers).** Before appending, scan the ledger pair for an existing row with the same `dedup_key`. If one exists, update its `last-seen` to today rather than appending a duplicate. Do not change its `status`, `notes`, or `owner-role` — consumers own those fields.

### verifier (Phase 5 / 5.5)

**When to write.** For each per-change debt finding surfaced during convention compliance (Phase 5) or behavioral-contract compliance (Phase 5.5): `[DEAD-CODE-UNREMOVED]`, `[BLOAT]`, duplication, function-size or file-size ceiling breaches, nesting-depth violations.

**Producer defaults** (all other fields per § Schema):

| Field | Value |
|-------|-------|
| `source` | `verifier` |
| `status` | `open` |
| `resolved-by` | empty |
| `direction` | `code-to-goals` (default); `goals-to-code` only when the finding is code not yet meeting a stated goal |
| `goal-ref-type` | `code-quality` (default); `adr` / `spec-req` / `architecture` / `claude-md` only when anchored to a Praxion-native goal |
| `goal-ref-value` | empty when `goal-ref-type = code-quality` |
| `owner-role` | from § Owner-role heuristic — lookup; do not re-derive |
| `first-seen` / `last-seen` | today (`YYYY-MM-DD`) on creation |
| `notes` | one sentence; cite the tag (`[BLOAT]` / `[DEAD-CODE-UNREMOVED]`) or the breached ceiling (e.g. "function 63 lines, ceiling 50") |

**Severity** (verifier tiering — maps finding impact, not the schema enum definition):

| Tier | When |
|------|------|
| `critical` | correctness risk or contract violation |
| `important` | quality ceiling breach or systemic duplication |
| `suggested` | surviving overrides, low-impact cleanup |

**Class** (finding → `class`):

| Finding | `class` |
|---------|---------|
| duplication | `duplication` |
| function/file size or nesting-depth breach | `complexity` |
| `[BLOAT]` | `complexity`, unless the bloat is a dedicated unused symbol → `dead-code` |

**Phase 5.5 survivor override.** When a `[DEAD-CODE-UNREMOVED]` FAIL is overridden by the user or scope-deferred, file a row with `severity = suggested`, `status = open`, and a survivor flag in `notes` — survivors must persist as tracked debt rather than be lost.

**Report vs ledger.** A single finding produces both a `VERIFICATION_REPORT.md` entry (current pipeline review) and a ledger row (persistence beyond the pipeline). Do not write debt findings into `LEARNINGS.md` or into report sections intended as the persistence surface.

### architect-validator (Phase 7)

**When to write.** For each FAIL finding in `ARCHITECTURE_VALIDATION.md`.

**Producer defaults** (populate all other fields per § Schema):

| Field | Value |
|-------|-------|
| `class` | `drift` |
| `direction` | `code-to-goals` (default); `goals-to-code` when the ADR or model declares something the code does not implement |
| `location` | file:line or DSL element id |
| `goal-ref-type` | `architecture` (or `adr` when anchored to a specific ADR) |
| `goal-ref-value` | DESIGN.md section path or `dec-NNN` |
| `source` | `architect-validator` |
| `severity` | `critical` (model-edge or ADR-dangling), `important` (generated-region), `suggested` (suppressed) |
| `owner-role` | `systems-architect` |
| `status` | `open` |
| `notes` | one-line context |

### sentinel (TD01–TD04, TT04, EC07)

**When to write.** Repo-wide audit signals from `.ai-state/metrics_reports/METRICS_REPORT_*.md` and targeted dimension checks — not per-change verification (verifier) or per-PR structural drift (architect-validator):

| Check | Signal source | Overlay key |
|-------|---------------|-------------|
| TD01 | `hotspots` (churn × complexity) | TD01 |
| TD02 | `pydeps.cyclic_sccs` (SCC size > 1) | TD02 |
| TD03 | `coverage` namespace (module below project floor; default 70%) | TD03 |
| TD04 | `lizard` / `complexipy` p95 complexity crossings | TD04 |
| TT04 | per-group P95 > 1.5× declared `expected_runtime_envelope` for ≥ 3 consecutive reports | TT04 |
| EC07 | `scripts/check_aac_golden_rule.py --mode=audit` important-severity findings | EC07 |

TD05 audits ledger discipline only — **never writes rows**. TT03 reads `topology-drift` counts but does not write.

**Policies (all sentinel writes).**

- **LLM-judgment gating:** a numeric threshold breach is necessary but not sufficient. The Tech-Debt Findings report subsection must explain why each filed row was warranted — mechanical dumps flood the ledger.
- **Staleness:** when `METRICS_LOG.md` latest row is older than 14 days OR `coverage.status = stale`, emit a TD-dimension WARN and write from available data — never block.
- **`source`:** `sentinel`; **`status`:** `open`; **`direction`:** `code-to-goals` (default); **`goal-ref-type`:** `code-quality` unless anchored to ADR/architecture; **`owner-role`:** from § Owner-role heuristic unless the table below overrides.

**Finding → field mapping:**

| Overlay key | `class` | `severity` | `owner-role` |
|-------------|---------|------------|--------------|
| TD01 | `complexity` | `important` (top-3 hotspot impact), `suggested` otherwise | `implementer`; → `implementation-planner` when restructuring required |
| TD02 | `cyclic-dep` | `important` | `implementation-planner` |
| TD03 | `coverage-gap` | per finding impact | `test-engineer` |
| TD04 | `complexity` | per finding impact | `implementer` |
| TT04 | `topology-drift` | `important` | `implementation-planner` |
| EC07 | `drift` | `important` | `implementer` |

Populate `location`, dates, `notes` (one sentence + why-filed), and remaining schema fields per § Schema.

### orchestrator (main agent)

**When to append rows (exception, not routine).** Only when:

1. **Explicit user direction** — the user asks to file a grounded finding as tracked debt.
2. **`defer-with-rationale` disposition** — the architect recorded defer on a Continuous Improvement Signal per [`disposition-vocabulary.md`](disposition-vocabulary.md); the documented defer criteria become the row's `notes`. Verifier or sentinel remain preferred if the finding fits their scope on a later pass.
3. **Scope gap** — a grounded finding fits neither verifier's per-change scope (Phase 5/5.5) nor sentinel's periodic-audit scope (TD/TT/EC dimensions). File with honest `source: orchestrator` rather than misattributing to verifier or sentinel.

**When NOT to append.** Per-change findings during verification → § Producer overlays → **verifier**. Metrics/repo-wide audit signals → **sentinel**. Per-PR structural drift → **architect-validator**. Verifier and sentinel may **re-source** orchestrator rows on subsequent runs.

**Producer defaults** (populate all other fields per § Schema):

| Field | Value |
|-------|-------|
| `source` | `orchestrator` |
| `status` | `open` |
| `resolved-by` | empty |
| `direction` | `code-to-goals` (default) |
| `goal-ref-type` | best anchor (`adr`, `architecture`, `code-quality`, …) per finding |
| `goal-ref-value` | anchor id/path when applicable; empty when `goal-ref-type = code-quality` |
| `owner-role` | § Owner-role heuristic; `unassigned` + proposed owner in `notes` when unclear |
| `class` | best-fit enum; `other` when no slot fits — `notes` SHOULD propose a named class |
| `first-seen` / `last-seen` | today on creation |
| `notes` | one sentence citing user direction, defer rationale, or scope-gap reason |

**Consumer-only (not new rows).** Rework worktree creation: flip linked `td-NNN` rows `open → in-flight` with `notes` suffix `// in-flight via rework worktree <name>` (notes-field linkage — no schema change). Pre-refactor mini-pipeline completion: flip affected rows `in-flight → resolved`. These are in-place status updates on existing rows, not producer appends.
