---
id: dec-092
title: Retire `ROADMAP.md` as living document; route content to TECH_DEBT_LEDGER and idea_ledgers
status: accepted
category: architectural
date: 2026-04-28
summary: Delete the project-root `ROADMAP.md`. Route code-anchored open items to `.ai-state/TECH_DEBT_LEDGER.md`; route strategic horizons to `.ai-state/idea_ledgers/IDEA_LEDGER_*.md`. The `/roadmap` command + `roadmap-cartographer` agent + `roadmap-synthesis` skill remain in place; if invoked, they will produce a fresh `ROADMAP.md` from a new audit, but Praxion no longer carries a stale living instance.
tags: [architecture, roadmap, living-document, lifecycle, supersession, tech-debt-ledger, idea-ledger]
made_by: user
pipeline_tier: direct
affected_files:
  - .ai-state/TECH_DEBT_LEDGER.md
  - .ai-state/idea_ledgers/IDEA_LEDGER_2026-04-29_02-52-30.md
  - CLAUDE.md
  - README.md
  - README_DEV.md
supersedes: dec-032
---

## Context

`ROADMAP.md` was established by `dec-032` as a living document at project root, mirroring the `dec-019` (`SYSTEM_DEPLOYMENT.md`) and `dec-020`/`dec-021` (`ARCHITECTURE.md`) precedents. Over time the file accumulated ~664 lines: ~400 lines of "DONE" historical entries, plus a Quality Metrics table, Guiding Principles for Execution, and ~5 open items split between concrete code-anchored debt and strategic-horizon research items.

Two distinct artifact types exist downstream of `ROADMAP.md`'s purpose:

1. **`.ai-state/TECH_DEBT_LEDGER.md`** (`dec-071`) — living, append-only ledger of grounded debt findings. Schema and producers (verifier, sentinel) are explicitly scoped *against* strategic horizons by the rule in `rules/swe/agent-intermediate-documents.md` (which says: "Promethean and roadmap-cartographer are explicitly excluded — strategic horizons, not in-flight debt").
2. **`.ai-state/idea_ledgers/IDEA_LEDGER_*.md`** — promethean-maintained ideation records covering implemented / pending / discarded / future-paths content.

The roadmap's open items naturally split between the two: file-size violations and broken-implementation items are debt; cross-tool portability research and Agent Teams evaluation are forward-looking ideation. Maintaining a third long-form living document on top of these two artifacts duplicates structure without distinct value, drifts (large parts of the roadmap had been stale for weeks), and conflicts with the "single source of truth per concern" discipline that motivated the architecture-doc deduplication immediately preceding this decision.

Once the open items are routed to the appropriate destinations, the canonical Praxion instance of `ROADMAP.md` no longer carries unique content.

## Decision

Retire the Praxion-instance `ROADMAP.md` and delete it from the project root. Route content as follows:

- **Code-anchored open items → `TECH_DEBT_LEDGER.md`** as new rows (`td-003`–`td-006`): `store.py` size violation, `otel_relay.py` size violation, eval-regression broken-design redesign, `/co` + `/cop` duplication.
- **Strategic horizons → `IDEA_LEDGER_2026-04-29_02-52-30.md`**: AGENTS.md cross-tool portability, Agent Teams integration, MCP Gateway pattern, pipeline shortcut paths, zero-duration span resolution, `/memory` alias for `/cajalogic`, `typescript-development` skill, `mcp-crafting/contexts/typescript.md`.
- **Historical "DONE" content → not migrated.** Recoverable via `git log -p ROADMAP.md` and `git show <sha>:ROADMAP.md`. The completed work itself is reflected in shipped code, ADRs `dec-022` through `dec-091`, sentinel reports, and the existing idea ledgers.
- **Guiding Principles for Execution → not migrated.** The four durable principles (token budget first-class, measure before optimize, standards convergence, curiosity over dogma) are already embedded in `CLAUDE.md` and elaborated in `README.md#guiding-principles` per `dec-027`. The execution-cadence guidance ("one phase at a time within phases, but overlap between phases") was a roadmap-shape concern that no longer applies once roadmap phases are retired.
- **Quality Metrics table → not migrated.** It tracked Phase 1 → Phase 3 progress under the prior 15,000-token budget ceiling (revised to 25,000 by `dec-050`). Future measurement runs through sentinel reports and `/project-metrics` outputs (see `dec-062`).

The `/roadmap` command, the `roadmap-cartographer` agent, and the `roadmap-synthesis` skill are **preserved unchanged**. The cartographer pipeline can still be invoked on demand and would produce a fresh `ROADMAP.md` from a new audit cycle. This decision retires only the current stale instance, not the regeneration capability.

## Considered Options

### Option 1 — Schema-compliant split (chosen)

Migrate code-anchored items to the tech-debt ledger as proper rows; migrate strategic horizons to a new idea ledger; delete the file.

**Pros:** Honors the ledger schema's exclusion rule on strategic horizons. Routes each item to the artifact whose semantics fit. Preserves the cartographer pipeline for future regeneration. Removes ~580 lines of stale duplication. Continues the deduplication-by-pointer pattern from the immediately-preceding architecture-doc refactor.

**Cons:** Requires updating cross-references in `CLAUDE.md`, `README.md`, `README_DEV.md`. Requires this supersession ADR. The "DONE" entries' rationale is recoverable only via git history, not via filesystem browsing.

### Option 2 — Migrate everything to the tech-debt ledger

Put all open items, including strategic horizons, into the ledger.

**Pros:** One destination; literal reading of the user's request.

**Cons:** Violates the ledger's documented exclusion rule (strategic horizons → idea ledgers, by rule). Pollutes the debt ledger with research-grade items that consumer agents (systems-architect, implementation-planner, etc.) will incorrectly filter on `owner-role`. Inverts the rule's "permission, not obligation" semantics — a Pipeline Shortcut Paths research item is not an item any consumer agent should be expected to "address."

### Option 3 — Trim ROADMAP.md to open-items-only, do not delete

Strip historical content; keep the file as a lightweight open-items list.

**Pros:** Minimal blast radius. No ADR supersession. No cross-reference updates. Preserves the cartographer's canonical output target.

**Cons:** Maintains a third long-form artifact alongside the ledger and idea ledgers. Over time the same drift recurs. Doesn't honor the user's "get rid of `ROADMAP.md`" intent.

### Option 4 — Move ROADMAP.md to `.ai-state/` and keep as living document

Like option 3 but in the hidden state directory.

**Pros:** Removes from user-visible surface. Aligns with sentinel-report / spec-archive precedent.

**Cons:** Same maintenance and drift concerns as option 3. dec-032 explicitly considered and rejected this in its Option 2; reverting would re-litigate that without new evidence.

## Consequences

**Positive:**

- Single source of truth per concern: code-anchored debt → ledger; strategic horizons → idea ledgers.
- ~580 lines of stale duplication removed from the project root.
- The deduplication-by-pointer pattern established for the architecture docs in the same session is now applied consistently to the strategic-planning surface.
- Cartographer pipeline remains operational; regeneration is on-demand rather than mandated.

**Negative:**

- The "DONE" historical entries with their commit SHAs and ADR cross-references are no longer browsable as a single chronicle. Recoverable via `git show <sha>:ROADMAP.md`.
- Cross-references in `CLAUDE.md`, `README.md`, `README_DEV.md` must be updated in the same commit to avoid temporary breakage.
- This supersedes `dec-032` after only ~16 days — short-lived ADRs are themselves a noise signal about decision stability. Mitigation: this supersession is grounded in a concrete observation (drift accumulated faster than the cartographer pipeline ran), not a re-litigation of the original framing.

**Operational:**

- The `roadmap-cartographer` agent description (`agents/roadmap-cartographer.md`) and the `/roadmap` command (`commands/roadmap.md`) remain unchanged. They produce `ROADMAP.md` if invoked. After this decision, the steady-state expectation is that `ROADMAP.md` does *not* exist at the project root unless a deliberate cartographer run has just produced one.
- The `skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md` template stays untouched — it remains the schema for any future regeneration.
- `dec-032`'s status flips to `superseded` and gains `superseded_by: dec-092` per the supersession protocol.

## Prior Decision

This supersedes `dec-032` (`ROADMAP.md` at project root as living document with preserved Decision Log). `dec-032` established the location and lifecycle for `ROADMAP.md` as a single living file at project root with section ownership and a preserved Decision Log section. That framing assumed `ROADMAP.md` carried unique content not better served by other artifacts; the present decision observes that the open-items content of the Praxion roadmap is fully covered by the tech-debt ledger and the idea ledgers, leaving only historical record (covered by git) and embedded principles (covered by `CLAUDE.md` + `README.md`). The cartographer pipeline that `dec-032` was implicitly designed to support is preserved; only the requirement to keep a living instance is retired.
