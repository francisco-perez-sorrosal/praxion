---
id: dec-draft-b068ad8e
title: Metrics storage schema — JSON canonical + MD derived + append-only METRICS_LOG.md
status: proposed
category: architectural
date: 2026-04-23
summary: Freeze a dual-artifact storage shape for /project-metrics (JSON canonical + MD derived rendering + append-only METRICS_LOG.md) with an explicit frozen-on-first-release aggregate block and a schema-mismatch policy for trend computation
tags: [architecture, storage, schema, ai-state, metrics, project-metrics]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - commands/project-metrics.md
  - scripts/project_metrics/schema.py
  - scripts/project_metrics/report.py
  - scripts/project_metrics/trends.py
  - scripts/project_metrics/logappend.py
  - docs/metrics/README.md
  - .ai-state/METRICS_REPORT_*.json
  - .ai-state/METRICS_REPORT_*.md
  - .ai-state/METRICS_LOG.md
---

## Context

The new `/project-metrics` slash command (see `.ai-work/project-metrics/SYSTEMS_PLAN.md`) produces a point-in-time snapshot of project complexity and health metrics. Three storage decisions are entangled:

1. **File format** — human-readable MD (sentinel precedent) vs machine-readable JSON vs YAML-frontmatter hybrid.
2. **Accumulation pattern** — living document (ARCHITECTURE.md style), timestamped archive (sentinel style), or append-only log (calibration_log style).
3. **Schema evolution** — what happens when metric definitions or the aggregate contract change over time.

Three downstream UI paths (static HTML + JSON, local server, Datasette/Grafana) all consume this artifact and have different parseability tolerances. The research findings (`RESEARCH_FINDINGS_integration-ui.md:52-87`) establish that the sentinel MD-only approach "will fossilize at 300 rows" and does not survive a UI round-trip. At the same time, the per-run richness that sentinel ships (commentary, deltas, per-artifact detail) is real value that a pure append-only log loses.

A strong internal precedent exists: `memory-mcp/src/memory_mcp/metrics.py:54-73`'s `compute_metrics()` already returns `{"store": ..., "observations": ..., "summary_markdown": ...}` — a structured-payload-plus-rendered-MD shape. Generalizing this to `/project-metrics` is additive, not novel.

The `aggregate` block has a further constraint: `METRICS_LOG.md` will chart its columns as a time series, and inconsistent columns across runs produce ragged data. The research (`RESEARCH_FINDINGS_integration-ui.md:247-249`) flags this explicitly as an open question: "Should the METRICS_LOG.md table columns be frozen on the first run or allowed to grow? Adding a new column later requires backfilling historical rows or accepting ragged data."

## Decision

Adopt a **three-file-per-run hybrid** with explicit schema versioning:

1. **`.ai-state/METRICS_REPORT_YYYY-MM-DD_HH-MM-SS.json`** — canonical machine-readable payload, the single source of truth for all downstream consumers (UI, trends, future agents).
2. **`.ai-state/METRICS_REPORT_YYYY-MM-DD_HH-MM-SS.md`** — human-readable rendering generated from the JSON; no information lives here that is not also in the JSON.
3. **`.ai-state/METRICS_LOG.md`** — append-only markdown table, one row per run, column-frozen on first release.

**Schema versioning**: a top-level `schema_version` field (semver) in the JSON and echoed into every row of `METRICS_LOG.md`. The `aggregate` block columns are **frozen on first release**; changes require explicit ADR amendment.

### Frozen aggregate-block columns (v1.0.0)

| Column | JSON path | Type | Unit | Why it's in the aggregate (rather than buried in a namespace) |
|---|---|---|---|---|
| `schema_version` | `aggregate.schema_version` | string (semver) | — | **Required** — every row in METRICS_LOG.md must carry it so schema-mismatch delta policy can fire without re-reading the full JSON |
| `timestamp` | `aggregate.timestamp` | string (ISO 8601 UTC) | — | **Required** — time axis of the log chart. Filename timestamp is not machine-authoritative (user-rename tolerant); JSON is |
| `commit_sha` | `aggregate.commit_sha` | string | — | **Required** — ties every row to a concrete code state; enables point-in-history regression analysis |
| `window_days` | `aggregate.window_days` | integer | days | **Required** — churn/entropy/truck-factor results depend on window; comparing a 30-day run to a 90-day run without this field silently lies |
| `sloc_total` | `aggregate.sloc_total` | integer | lines | **Size baseline** — denominator for every density-style derived metric; universally computable (scc or stdlib fallback) |
| `file_count` | `aggregate.file_count` | integer | files | **Navigation scale** — reviewer's "surface" number; trivially computable |
| `language_count` | `aggregate.language_count` | integer | langs | **Project-shape signal** — monolingual vs polyglot repos diverge in everything else; must be visible at aggregate level |
| `ccn_p95` | `aggregate.ccn_p95` | number \| null | — | **Flagship complexity** — cross-language (lizard); p95 is the tail the reviewer cares about; null when lizard unavailable |
| `cognitive_p95` | `aggregate.cognitive_p95` | number \| null | — | **Python-specific complexity** — null on non-Python or when complexipy unavailable; worth the column because when Python is the primary language, cognitive is the better signal |
| `cyclic_deps` | `aggregate.cyclic_deps` | integer \| null | SCCs | **Architecture health** — 0 or non-0 is informative on its own; gaming-resistant; null when pydeps unavailable |
| `churn_total_90d` | `aggregate.churn_total_90d` | integer | lines | **Effort signal** — git-only so always available; feeds hot-spot denominator |
| `change_entropy_90d` | `aggregate.change_entropy_90d` | number | shannon bits | **Process-focus signal** — single-number summary of how scattered development is; research flagged as outperforming product metrics for defect prediction |
| `truck_factor` | `aggregate.truck_factor` | integer | authors | **Organizational risk** — Bird/Avelino method; most projects have never measured theirs and the result is usually uncomfortable |
| `hotspot_top_score` | `aggregate.hotspot_top_score` | number | composed | **Headline composite** — max of churn × complexity across files; the one number that says "there is something that needs attention" |
| `hotspot_gini` | `aggregate.hotspot_gini` | number | 0.0–1.0 | **Distribution shape** — distinguishes "one bad file" from "everything is mid-hot"; cheap to compute; strongly complements the top-score |
| `coverage_line_pct` | `aggregate.coverage_line_pct` | number \| null | percent | **Test-health scale** — null when no coverage artifact (common); when present, a scale marker, not a quality gate |

Every column has a specific justification — they are not a dump of every metric we can compute. The rule for inclusion in `aggregate` is: does it belong on the time-series chart that `METRICS_LOG.md` will back? If yes, it goes here. If it's useful only in the per-run deep dive (e.g., per-function CCN histograms, change-coupling edge lists), it lives in its collector namespace in the full JSON, not in the aggregate.

### Namespace block (non-aggregate, per-collector)

Full-fidelity per-collector data lives in namespace blocks:

```
{
  "schema_version": "1.0.0",
  "aggregate": { ...frozen columns above... },
  "tool_availability": {
    "git":       {"status": "available", "version": "2.45.1"},
    "scc":       {"status": "available", "version": "3.7.0"},
    "lizard":    {"status": "available", "version": "1.22.0"},
    "complexipy":{"status": "unavailable", "reason": "uvx_not_found", "hint": "install uv"},
    "pydeps":    {"status": "not_applicable", "reason": "no_python_sources_detected"},
    "coverage":  {"status": "no_artifact", "hint": "run pytest --cov && coverage xml"}
  },
  "git":        { ...raw churn, ownership, entropy... },
  "scc":        { ...language breakdown, per-file SLOC... },
  "lizard":     { ...per-function CCN, top-N highest... },
  "complexipy": { ...per-function cognitive... },
  "pydeps":     { ...coupling, SCC list... },
  "coverage":   { ...per-file line pct... },
  "hotspots":   { "top_n": [...], "gini": 0.74 },
  "trends":     { ...delta block, see schema-mismatch policy below... },
  "run_metadata": {
    "command_version": "...", "python_version": "...", "wall_clock_seconds": 12.3,
    "window_days": 90, "top_n": 10
  }
}
```

Namespace blocks are not frozen — collectors may evolve their internal shape across schema versions. Only the aggregate is load-bearing for downstream consumers.

### METRICS_LOG.md columns (frozen, v1.0.0)

`METRICS_LOG.md` carries exactly the aggregate-block columns, in declaration order, plus a final `report_file` link column. First-run creates the file with a header; subsequent runs append.

### Schema-mismatch policy for trend deltas

When the most-recent-prior `METRICS_REPORT_*.json`'s `schema_version` major or minor differs from the current run:

1. **Do not compute numeric deltas.** Fabricating a comparison across incompatible schemas is worse than reporting no delta.
2. **Emit a `trends: {"status": "schema_mismatch", "prior_schema": "...", "current_schema": "...", "prior_report": "<filename>"}` block.**
3. **Render a one-line warning in the MD**: `⚠ Trend delta deferred — prior report used schema <X>, current is <Y>.`
4. **METRICS_LOG.md still gets a row** — the row stands alone; its delta columns (if any are added in the future) are marked `—`.

Patch-version differences (e.g., `1.0.0` → `1.0.1`) are treated as compatible and proceed with normal delta computation — patch versions are reserved for bug fixes that do not change column semantics.

First-run policy: `trends: {"status": "first_run", "prior": null}`; MD renders "first run — no deltas". This is distinct from `status: "no_prior_readable"` (which would indicate corruption or a deletion) — deliberate, so the user can distinguish "new project" from "someone deleted my reports."

### Schema-evolution rules (amendment policy)

1. **Additive changes** (new aggregate column, new collector namespace) bump minor version (`1.0.0 → 1.1.0`). Old consumers still work; the new column is `null` in their view.
2. **Breaking changes** (renaming an aggregate column, changing a unit, dropping a column) bump major version (`1.0.0 → 2.0.0`). This requires a superseding ADR. When a major bump lands, `METRICS_LOG.md` is not mutated in place; a new `METRICS_LOG_v2.md` is created, and a one-line pointer is appended to the old log.
3. **Never silently change a column's meaning.** A "churn" redefinition that changes the number without changing the column name is a major break.
4. **Patch changes** (bug fixes, clearer `_source` annotations) bump patch. Trend deltas proceed normally.

## Considered Options

### Option 1: MD-only with structured tables (sentinel precedent)

**Pros:** Zero infrastructure; matches existing precedent; no new `.ai-state/` convention.

**Cons:** Regex-dependent parsing; brittle under table edits; UI round-trip is a slog; duplicates numbers across rows. Research explicitly flags this as the thing to avoid for a new command.

### Option 2: JSON-only with no MD rendering

**Pros:** Smallest artifact per run; machine-friendliest.

**Cons:** The MD rendering is what a developer actually *reads*; omitting it is like omitting the interface of a library. Forces every consumer to build their own renderer.

### Option 3: MD-with-YAML-frontmatter

**Pros:** Single file per run; frontmatter is machine-parseable.

**Cons:** YAML handles nested arrays of dicts verbosely; long frontmatter pushes prose below the fold; forces every UI path to strip frontmatter before parsing; editor-hostile for the JSON-shaped data we actually have.

### Option 4: JSON canonical + MD derived + append-only log (chosen)

**Pros:** Three consumption patterns each get their ideal format; JSON is the canonical source of truth so the MD can be regenerated if conventions change; append-only log is the fast path for charting; aligns with `memory-mcp`'s existing `compute_metrics() -> {..., "summary_markdown": ...}` shape.

**Cons:** Three files per run instead of one or two; teaches a new `.ai-state/` convention (the first JSON artifact in `.ai-state/`); aggregate-column freeze constrains v2 evolution.

### Option 5: SQLite database as canonical storage

**Pros:** Natural time-series; Datasette reads it directly; atomic transactions; built-in indexing.

**Cons:** Binary artifact in `.ai-state/` is a convention break (everything in `.ai-state/` today is human-browsable text); git diffs are opaque; merge conflicts in the DB file are intractable; forces Datasette on everyone who wants to look. Simpler to emit JSON and let Datasette ingest it separately (Path C in the research).

## Consequences

**Positive:**

- Downstream UI paths A (static HTML + JSON) and B (local server) read the JSON directly; Path C (Datasette/Grafana) ingests with a 15-line script. No UI path is painted into a corner.
- Frozen aggregate columns mean `METRICS_LOG.md` charts remain stable across runs; a single row is parseable with a one-line regex and charts trivially.
- Schema versioning means the trend-delta computation is safe-by-default: when comparison is unreliable, we say so instead of fabricating numbers.
- The `summary_markdown` pattern is now projected across two places in the codebase (`memory-mcp/metrics.py` and `scripts/project_metrics/report.py`), strengthening it as a local idiom rather than a one-off.
- Developers working with the artifact can round-trip: edit the JSON, regenerate the MD. No information loss.

**Negative:**

- Three files per run triples the `.ai-state/` file count growth rate compared to sentinel's two-file model. At one run per week over a year this is still <200 files total — acceptable, but worth noting.
- The aggregate column freeze is a real constraint. When v2 adds TS/Go/Rust collectors, any aggregate addition is a minor bump and needs an ADR amendment. This is a feature of the design (forces deliberate thinking) not a bug, but it does slow v2.
- New `.ai-state/` JSON convention: this is the first structured-JSON artifact in `.ai-state/` (observations.jsonl is JSONL, different convention). Downstream tooling expecting MD-only must learn to ignore `.json` files during readership.
- `METRICS_LOG.md` and the report JSON duplicate the aggregate-block numbers. The log is the fast path; the JSON is authoritative. If they ever disagree, the JSON wins — documented in `docs/metrics/README.md`.

## Notes on frozen columns (self-critique)

I pushed back on my own earlier draft that included `comment_density` and `test_to_code_ratio` in the aggregate — both are in the research blacklist (§10). They are absent here deliberately. I also considered including `duplication_pct` — excluded because v1 does not run `jscpd` (explicit non-goal), and including a column that is always null is worse than omitting it.

The `hotspot_gini` column is my addition beyond the research shortlist. Justification: without it, the reader sees only `hotspot_top_score` and cannot distinguish "one bad file in an otherwise clean repo" from "many bad files and the top one is merely the worst." Gini over the hot-spot score distribution is cheap to compute and qualitatively different from the top-score. It is included with full acknowledgment that it is a judgment call; if the implementation-planner disagrees, it can be moved to the hotspots namespace and out of the frozen aggregate — but that requires changing this ADR before code ships.
