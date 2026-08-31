---
id: dec-347
title: ADR retrieval ships as a standalone affected_files query script, not index-schema or hook-scoring changes
status: accepted
category: architectural
date: 2026-08-30
summary: affected_files-gated ADR retrieval lands as scripts/query_adrs.py (stdlib-capable, current-streamline default view) plus one Discovery Protocol line; index schema and inject_decisions.py scoring stay unchanged
tags: [adr, retrieval, discovery-protocol, affected-files, context-cost, query-tool]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/query_adrs.py
  - scripts/test_query_adrs.py
  - rules/swe/adr-conventions.md
dissent: "Hook-scoring integration would need no agent compliance at all — a convention-plus-tool read path can be ignored by the very agents it exists to discipline, while SessionStart scoring fires unconditionally."
---

## Context

The adr-compaction spike (2026-08-30) established that the ADR context problem is the read path, not the corpus: `DECISIONS_INDEX.md` is ~44K tokens and growing ~127 tokens/ADR, while the SessionStart injection hook is already capped and corpus-independent. The Discovery Protocol was rewritten retrieval-first (grep-pre-scan mandatory). The remaining gap: grep over index rows matches only tags/title/summary text; it cannot answer the highest-value agent question — *"which decisions govern the files I am about to touch?"* A measured probe showed the substrate for that query already ships: `affected_files` frontmatter is 99% populated across accepted ADRs (median 4 paths, zero globs, 94% of concrete paths existing after the 2026-08-31 remediation).

## Decision

Ship `affected_files`-gated retrieval as a **standalone read-only query script**, `scripts/query_adrs.py`:

- Selectors: `--paths` (normalized exact or directory-prefix containment, both directions), `--staged` (derive paths from git), `--tags`, `--grep`; AND-combined.
- Default view is the **current streamline**: `accepted` + `re-affirmation` only; terminal statuses require `--all`. This delivers the originally requested "filter the list" capability as a query-time view — zero mutation of records or ids.
- Scans finalized ADRs and `drafts/` (authoritative in-flight).
- PyYAML when available, honest stdlib fallback parser otherwise (managed projects' ambient Python may lack PyYAML); repo-root from `git rev-parse`, never `__file__` (plugin-cache execution).
- Wiring: one line in the Discovery Protocol naming the script as the preferred pre-scan when file scope is known. No index-schema change; no `inject_decisions.py` change.

## Considered Options

### A — Standalone query script (chosen)
Pros: zero token cost (script I/O, not context); zero always-loaded growth beyond one protocol line; generalizes to managed projects by shipping with the plugin; the current-streamline default view implements filtering without touching any record. Cons: relies on agent compliance with the protocol; `affected_files` staleness degrades recall (mitigated: 94% path validity measured, and sentinel DH checks police decay).

### B — Add an affected_files column to DECISIONS_INDEX.md
Pros: single artifact for all row data. Cons: grows every index row (the artifact whose size is the measured problem); median 4 paths/row would roughly double row width; benefits only consumers that already read the index.

### C — Extend inject_decisions.py relevance scoring with affected_files intersection
Pros: automatic — no agent compliance needed; hook already builds session-path signal. Cons: requires reading 346 frontmatter blocks every SessionStart (latency in a hook that must stay fast); improves a channel that is already capped and healthy; helps only session start, not mid-task discovery. Deferred, not rejected — see Reversal trigger.

### D — MCP server for ADR queries
Pros: richest ergonomics. Cons: a running process + registration per project for what a script answers in one invocation; violates Simplicity First at this scale.

## Consequences

Positive: mid-task "what governs these files?" becomes a one-command, zero-token operation; the current-streamline filter exists without archive moves, renumbering, or body rewrites (all rejected by the spike on integrity evidence); drafts participate in discovery.

Negative: a new component to maintain and ship; recall bounded by `affected_files` hygiene, which becomes mildly load-bearing (it already feeds sentinel DH checks, so the policing exists); convention-dependent adoption.

## Disconfirmation

- **Falsifier**: observations/telemetry showing agents continuing ungated full-index reads (or never invoking the tool) after the protocol change would prove the convention-plus-tool path insufficient.
- **Steelmanned runner-up**: Option C is structurally superior on compliance — hooks fire unconditionally, agents forget instructions; if adoption telemetry disappoints, C is the correct escalation and its cost (frontmatter reads at SessionStart) could be amortized with a tiny generated sidecar cache.
- **Reversal trigger**: a sentinel or metrics report showing the query tool unused while index full-reads persist for ~4+ weeks → implement Option C alongside (not instead of) the script.
