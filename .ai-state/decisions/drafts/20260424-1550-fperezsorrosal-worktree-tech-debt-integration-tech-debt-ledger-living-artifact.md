---
id: dec-draft-e8df5e0b
title: Tech-debt ledger as a living artifact in `.ai-state/`
status: proposed
category: architectural
date: 2026-04-24
summary: Introduce `.ai-state/TECH_DEBT_LEDGER.md` as a single living, append-only ledger for grounded debt findings — one artifact, status updates in place, dedup-key for worktree merge — following the SYSTEM_DEPLOYMENT/ARCHITECTURE living-document precedent.
tags: [tech-debt, ledger, ai-state, living-document, agent-pipeline]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/TECH_DEBT_LEDGER.md
  - rules/swe/agent-intermediate-documents.md
  - .ai-state/ARCHITECTURE.md
  - skills/software-planning/references/document-templates.md
---

## Context

Praxion's debt-detection layer is strong but its **routing layer is missing**. `/project-metrics` is an orphan producer — its `METRICS_REPORT_*.md` and `METRICS_LOG.md` artifacts have zero consumers across `agents/`, `rules/`, and `skills/`. The verifier already produces per-change debt signals (`[DEAD-CODE-UNREMOVED]`, `[BLOAT]`, duplication, size/nesting), but routes them into `LEARNINGS.md ## Technical Debt`, whose end-of-feature destination per the template is "Issue tracker or CLAUDE.md" — vague and non-Praxion-native. Sentinel has no dedicated debt lens. The capability gap is integration, not signal generation.

The user reframed the design: tech debt is **"problems grounded in the current source code with respect to the current state of the system goals, and vice versa"** — bidirectional (`code-to-goals` and `goals-to-code`) — and is structurally distinct from learnings (gotchas, patterns, corrections), ideas (speculative future possibilities), and strategic roadmap items (narrated weaknesses). Conflating debt with any of these dilutes both surfaces.

The user resolved 10 questions before this ADR was drafted (see `.ai-work/tech-debt-integration/RESEARCH_FINDINGS.md` § Resolved Decisions); this ADR captures the design space those resolutions defined and adds the architect-call decisions needed to make the design implementable.

## Decision

Introduce `.ai-state/TECH_DEBT_LEDGER.md` as a **single, persistent, living artifact** — one Markdown table with stable `td-NNN` IDs, append-only rows, status-updated-in-place. Schema: 13 displayed fields (`id`, `severity`, `class`, `direction`, `location`, `goal-ref-type`, `goal-ref-value`, `source`, `first-seen`, `last-seen`, `owner-role`, `status`, `resolved-by`, `notes`) plus a 14th structural field `dedup_key` for finalize-time deduplication.

Schema, lifecycle, worktree-merge semantics, and the canonical class-to-role mapping for `owner-role` are registered in `rules/swe/agent-intermediate-documents.md` adjacent to the existing artifact registrations. The artifact is added to the §Permanent row of the Document Lifecycle table.

**Worktree concurrency** is handled by an append-only convention plus a post-merge dedupe step modeled on `scripts/finalize_adrs.py`. A new single-purpose script (`scripts/finalize_tech_debt_ledger.py`) — or a small extension to the existing post-merge hook chain, at the implementation-planner's call — wires into the post-merge hook chain after `finalize_adrs.py`. The dedupe key is a 12-char SHA1 prefix of `(class, normalize(location), direction, goal-ref-type, goal-ref-value)`. Status-tie-breaking favors the row with the newer `last-seen`; non-conflicting fields are merged.

**ID strategy** is hybrid: `td-NNN` zero-padded human-readable (referenced by humans and consumer agents in `notes` / commit messages); `dedup_key` is the structural deduplication anchor used at finalize time and invisible to most readers.

**`[DEAD-CODE-UNREMOVED]` survivors** (FAIL overridden by user, or scope-deferred) are promoted to ledger entries at `severity = suggested`, `status = open`, with `notes` flagging the survivor status — so nothing falls on the floor.

The artifact does **not** use section ownership (unlike `ARCHITECTURE.md` and `SYSTEM_DEPLOYMENT.md`). It is a single Markdown table with a small header; section ownership is unnecessary.

## Considered Options

### Option 1: Single living artifact with append-only + dedupe-at-finalize (chosen)

A Markdown table with stable IDs; producers append rows; consumers update status in place; post-merge dedupe handles worktree concurrency.

**Pros.** Reuses the proven dec-019/dec-020 living-document pattern. Markdown table is the cheapest possible merge surface — flat text, one row per line. Reuses `scripts/finalize_adrs.py` shape (idempotent + advisory file lock + bounded scope). Familiar mental model — users who already understand the ADR finalize transfer that mental model directly.

**Cons.** Brief window where two pipelines write the same item with the same `dedup_key` before merge — acceptable per Assumption 3 in `SYSTEMS_PLAN.md`. If `dedup_key` collides for genuinely-different items, two unrelated rows could merge — vanishingly unlikely given the five-component key.

### Option 2: Timestamped ledgers per pipeline (rejected — user-resolved)

Per-run `TECH_DEBT_LEDGER_YYYY-MM-DD_HH-MM-SS.md`, accumulating the way `SENTINEL_REPORT_*.md` does.

**Pros.** No worktree-concurrency challenge; each pipeline writes its own file.

**Cons.** Status updates require cross-file mutation — the consumer would need to find the latest row across N timestamped files for the same `dedup_key`, which defeats the simplicity goal. Loses the living-document affordance. Was rejected by the user during reframing.

### Option 3: Ledger-as-database with schema versioning (rejected — overengineering)

JSON or SQLite ledger with explicit migrations.

**Pros.** Deterministic schema validation; query support without pandas.

**Cons.** Eliminates human-readability, defeats consumer agents that read the ledger inline, requires migration tooling for a use case where Markdown table evolution is forgiving. Disproportionate.

### Option 4: Semantic merge driver (rejected — heavyweight)

Custom git merge driver for `.ai-state/TECH_DEBT_LEDGER.md` mirroring the `memory.json` / `observations.jsonl` reconcilers.

**Pros.** Conflict-free at merge by construction.

**Cons.** Drivers are project-local and require setup; two reconcilers already exist in `scripts/` and the user prefers the lower-ceremony `finalize_adrs.py` shape. The append-only + dedupe approach matches the data shape (one row per finding) better than a row-level diff merge.

## Consequences

**Positive:**
- Tech debt has a structurally distinct home, separating it from learnings (LEARNINGS.md), ideation (IDEA_LEDGER), and strategic narration (ROADMAP.md). Each surface stays focused.
- The ledger is human-browsable — markdown tables render in any viewer. Future code-derived dashboards can parse the markdown trivially.
- Reuses the proven living-document recipe; no new pattern to learn.
- The `dedup_key` field is invisible to humans who read the table casually but load-bearing for finalize-time correctness.
- Supersession-aware: the ledger preserves resolved rows as a debt-fix audit trail, supporting future "did this debt come back?" queries.

**Negative:**
- Concurrent worktrees can briefly produce duplicate rows; resolved at merge but the temporary duplication is observable inside an in-flight worktree.
- The hybrid `id + dedup_key` discipline requires both producers (verifier, sentinel) to compute `dedup_key` correctly; a producer that omits `dedup_key` files non-dedupable rows. Mitigation: schema validation in producer prompts is explicit; sentinel TD05 (next ADR) audits ledger health.
- `wontfix` rows persist forever; the ledger grows unboundedly. This is the same shape as `SENTINEL_REPORT_*.md` accumulation and is acceptable at the 1–10K-row scale Praxion operates at.

## Prior Decisions Referenced

- **dec-019** (Living `SYSTEM_DEPLOYMENT.md` artifact) — established the living-document-in-`.ai-state/` pattern.
- **dec-020** (Living `ARCHITECTURE.md` artifact) — extended dec-019 with section ownership and template-driven creation. The ledger reuses the persistence pattern but does NOT use section ownership (single-table artifact).
- **dec-013** (Layered duplication prevention; no new agent) — sets the precedent for solving cross-cutting debt concerns by composing existing agents rather than introducing a new one. The ledger integration follows this directly: no new agent, two existing producers, five existing consumers.
- **dec-061** (ADR finalize protocol at merge-to-main) — `scripts/finalize_adrs.py` is the structural template for the new `scripts/finalize_tech_debt_ledger.py` (or post-merge hook extension): bounded walk scope, advisory file lock, idempotent, dry-run flag.
