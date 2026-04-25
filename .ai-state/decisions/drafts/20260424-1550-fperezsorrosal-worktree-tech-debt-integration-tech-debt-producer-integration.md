---
id: dec-draft-e9a055bb
title: Tech-debt producers — verifier migration + sentinel TD dimension
status: proposed
category: behavioral
date: 2026-04-24
summary: Verifier migrates per-change debt entries off `LEARNINGS.md ## Technical Debt` and onto the new tech-debt ledger; sentinel gains a dedicated TD dimension (TD01–TD05) that LLM-judges metric breaches into ledger entries; both producers share a single owner-role heuristic anchored in `agent-intermediate-documents.md`.
tags: [tech-debt, ledger, verifier, sentinel, producer, agent-pipeline]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
supersedes:
re_affirms:
affected_files:
  - agents/verifier.md
  - agents/sentinel.md
  - skills/software-planning/references/document-templates.md
  - rules/swe/agent-intermediate-documents.md
---

## Context

The ledger artifact ADR (dec-draft-e8df5e0b) defines the destination. This ADR defines the **two producers** that fill it.

Today, the **verifier** writes per-change debt signals (`[DEAD-CODE-UNREMOVED]`, `[BLOAT]`, duplication, size/nesting violations) into `LEARNINGS.md ## Technical Debt`. That section's end-of-feature destination per the LEARNINGS template is "Issue tracker or CLAUDE.md" — vague, non-Praxion-native, and conceptually wrong (debt is not a learning). The verifier's per-change scope is correct; the destination is the weak link.

**Sentinel** today has no debt lens. CH01 samples cross-module duplication (a code-health check, not a debt audit); F07–F09 catch documentation staleness; T01/T03 cover token efficiency. None of these is framed as "tech debt per the user's operating definition." Sentinel has the right vantage point (repo-wide, on-demand, LLM-mediated synthesis of metric output) but no canonical surface to write to.

**`/project-metrics`** is an orphan producer. Its `METRICS_REPORT_*.md` and `METRICS_LOG.md` are read by zero agents/rules/skills. The user resolved that `/project-metrics` is **never** a direct ledger writer — sentinel pulls from it.

The **owner-role heuristic** must be identical across both producers. Without a single anchor, verifier and sentinel can drift into producing rows that the consumer-side filter cannot reliably route.

## Decision

### Verifier migration (per-change producer)

Phase 5/5.5 of `agents/verifier.md` is updated to write debt entries to `.ai-state/TECH_DEBT_LEDGER.md` instead of `LEARNINGS.md ## Technical Debt`. For every per-change finding, verifier appends one row with:

- `source = verifier`, `first-seen = today`, `last-seen = today`
- `class` derived from the verifier tag (`[DEAD-CODE-UNREMOVED]` → `dead-code`; `[BLOAT]` → `complexity`; duplication detection → `duplication`; size/nesting → `complexity`)
- `direction` set per the finding's framing (most verifier findings are `code-to-goals`)
- `goal-ref-type` and `goal-ref-value` populated when an anchor exists (an ADR, a REQ, an architecture invariant); `code-quality` value used otherwise
- `owner-role` from the canonical class-to-role mapping in `rules/swe/agent-intermediate-documents.md`
- `dedup_key` computed at write time

If a row with the same `dedup_key` already exists, verifier updates the existing row's `last-seen` instead of duplicating.

`[DEAD-CODE-UNREMOVED]` survivors (FAIL overridden by user, or out-of-scope deferment) are written at `severity = suggested`, `status = open`, with the survivor status flagged in `notes`.

The `## Technical Debt` section is removed from `skills/software-planning/references/document-templates.md` (lines 121–123). The "Technical debt | Issue tracker or CLAUDE.md | Track future improvements" row is removed from the End-of-Feature merge table in the same template.

### Sentinel TD dimension (repo-wide producer)

A new TD dimension is added to `agents/sentinel.md` with five checks:

| Check | Purpose | Read | Write |
|-------|---------|------|-------|
| **TD01 — Hotspots** | Top-N hotspot files (churn × complexity); LLM judges which warrant ledger entries | `METRICS_REPORT_*.md` `hotspots` array | Ledger row(s); `class = complexity` (default) or sentinel-judged class |
| **TD02 — Cyclic SCCs** | Non-trivial cyclic dependency components | `METRICS_REPORT_*.md` `pydeps.cyclic_sccs` | Ledger row(s); `class = cyclic-dep` |
| **TD03 — Coverage floor** | Coverage-percent breaches against a project-defined floor (default 60%). Treats `coverage.status = stale` identically to stale `METRICS_LOG.md` row age — WARN, proceed with available data. The opt-in `--refresh-coverage` flag (committed in `1f4720c` upstream) explains why staleness is a normal state, not a failure | `METRICS_REPORT_*.md` `coverage` namespace | Ledger row(s); `class = coverage-gap` |
| **TD04 — Complexity p95 crossings** | Files crossing complexity p95 threshold relative to repo aggregate | `METRICS_REPORT_*.md` `lizard` / `complexipy` namespaces | Ledger row(s); `class = complexity` |
| **TD05 — Status-update discipline** | Audits ledger health: stale `in-flight` (>30 days), `unassigned` rows older than 30 days, `open` rows in resolved-feature areas | `.ai-state/TECH_DEBT_LEDGER.md` itself | Sentinel report (WARN); never writes ledger rows |

Sentinel applies LLM judgment before writing: a numeric threshold breach is necessary but not sufficient. The sentinel's report explicitly explains why each ledger row was filed.

`METRICS_LOG.md` row staleness policy: if the latest row is older than 14 days, emit a TD-dimension-wide WARN and proceed with the report's available data. **Never block on staleness.**

The TD dimension is **net-new** — not a re-routing of CH01. CH01 stays a duplication-specific code-health check; TD01–TD05 cover debt under the user's operating definition.

### Detector inventory: routing helpers vs detectors

`rules/swe/agent-intermediate-documents.md` (or wherever the producer-side documentation lands) gains a "Routing helpers (not detectors)" subsection that names the `test-coverage` skill explicitly. The skill is a dispatcher+renderer (locate + invoke + render) — its output feeds `coverage_collector.py` upstream, not the ledger. This is documented to prevent boundary erosion in future changes.

### Owner-role heuristic — single source of truth

The class-to-role mapping table (canonical, both producers reference):

| `class` | Default `owner-role` | Override conditions |
|---------|---------------------|---------------------|
| `duplication` | `implementer` | `architecture` goal-ref → `systems-architect`; cross-module systemic → `implementation-planner` |
| `complexity` | `implementer` | If item requires module restructuring → `implementation-planner`; if invariant violation → `systems-architect` |
| `dead-code` | `implementer` | If in `tests/` → `test-engineer`; if doc-only → `doc-engineer` |
| `drift` | `doc-engineer` | If goal-ref-type=`adr` or `architecture` → `systems-architect` |
| `stale-todo` | `unassigned` | If `notes` field tags an owner explicitly → that role; if location is in `tests/` → `test-engineer` |
| `coverage-gap` | `test-engineer` | None — coverage is always test-engineer-owned per dec-067 |
| `cyclic-dep` | `implementation-planner` | Always — module-graph reshuffle is a planning concern |
| `other` | `unassigned` | Producer's `notes` field SHOULD propose an owner |

This table lives in `rules/swe/agent-intermediate-documents.md` adjacent to the ledger schema. Both producer agent prompts reference this single anchor.

## Considered Options

### Option 1: Verifier-only producer (rejected)

Sentinel stays out of the debt-writing loop; only verifier writes.

**Pros.** Single producer, no cross-producer consistency burden.

**Cons.** Verifier is per-change-scoped — it cannot detect debt that spans the repo (hotspots, cyclic SCCs, p95 crossings). Repo-wide debt would never enter the ledger. Defeats half the value.

### Option 2: Sentinel-only producer (rejected)

Sentinel periodically scans and writes; verifier keeps writing to LEARNINGS.md.

**Pros.** Fewer mutating agents on the ledger.

**Cons.** Per-change debt has no immediate path to the ledger; verifier's signal continues going to the wrong destination. Rejects the user-resolved migration.

### Option 3: Verifier + sentinel, single owner-role heuristic anchor (chosen)

Both producers write; both reference the same canonical class-to-role table.

**Pros.** Captures both per-change and repo-wide debt; single anchor prevents drift.

**Cons.** Two producers means two prompt surfaces to keep in sync. Mitigated by both pointing at the same rule file.

### Option 4: Verifier + sentinel + `/project-metrics` (rejected — user-resolved)

`/project-metrics` directly writes ledger rows from numeric breaches.

**Cons.** Mechanical dumps without LLM judgment produce noise. User rejected this; sentinel mediation preserves the LLM-judgment gate.

## Consequences

**Positive:**
- Per-change debt and repo-wide debt land in the same ledger with consistent schema.
- Owner-role consistency is structural — both producers grep the same anchor.
- `/project-metrics` stays a signal source; its existing schema (frozen per dec-062) is not coupled to ledger schema.
- TD05 (status-update discipline) is built into the producer side, monitoring the consumer side. The system audits its own contract.
- The `## Technical Debt` removal from LEARNINGS template eliminates the ambiguous "Issue tracker or CLAUDE.md" routing.

**Negative:**
- Verifier prompt grows by ~10 lines (write protocol). Acceptable.
- Sentinel prompt grows by a new dimension (~30 lines including TD01–TD05 definitions). The sentinel is already the largest agent file; this is a meaningful addition but not disproportionate.
- The "LLM judgment before writing" requirement on sentinel is qualitative; sentinel may underwrite (miss real debt) or overwrite (file noise). Mitigation: TD05 surfaces persistent miss patterns; sentinel report explains each filed row.
- Verifier-to-LEARNINGS migration removes a familiar entry point. Old pipelines mid-flight at the rollout boundary may have orphan `## Technical Debt` entries; the migration commit should sweep them into the ledger or delete them.

## Prior Decisions Referenced

- **dec-draft-e8df5e0b** (Tech-debt ledger as living artifact) — defines the ledger that this ADR's producers write to.
- **dec-013** (Layered duplication prevention; no new agent) — affirms that adding capability to existing agents is preferred over introducing a new agent. This ADR continues that pattern: no new producer agent, just extensions to verifier and sentinel.
- **dec-062** through **dec-066** (proposed `/project-metrics` ADRs) — schema, collector protocol, graceful degradation, hotspot formula, planning conventions. Sentinel TD01–TD04 read against the schema dec-062 froze; the freeze rule keeps this ADR's read protocol stable.
- **dec-067** (test-coverage skill scope) — establishes that `coverage-gap` items are owned by `test-engineer`; this ADR's owner-role heuristic codifies that as a no-override entry.
- **dec-046** (Staleness detection system) — the precedent for marker+frontmatter+sentinel-check integration; sentinel TD05's status-discipline audit is shape-similar (sentinel-check that audits the ledger's own health markers).
