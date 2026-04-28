# Project Metrics — Storage Schema and Consumption Reference

Authoritative reference for the `/project-metrics` artifact format. This document is the contract a third party relies on to write a UI, ingest the log into a time-series store, or consume the JSON from another tool. If the code and this document disagree, treat that as a documentation bug and file it.

## 1. Overview

`/project-metrics` produces a point-in-time snapshot of a project's complexity and health metrics (SLOC, cyclomatic complexity, cognitive complexity, cyclic imports, churn, change entropy, truck factor, hot-spots, coverage). Each invocation emits a **three-file artifact triple** — one canonical JSON payload, one derived human-readable Markdown rendering, and one append-only row in a shared log.

**Audience.**

- **Developers** auditing their own project: read the MD, skim the log.
- **UI implementers** (static HTML, local server, Datasette/Grafana): read the JSON and the log.
- **Future agents** comparing runs over time: read the JSON directly — never re-parse the MD.

**Source-of-truth hierarchy.** When the three artifacts differ, the JSON is authoritative. The MD is a rendering of the JSON; the log row is a projection of `aggregate`. Regenerating either from the JSON must be lossless.

**Related design documents.**

- `.ai-state/ARCHITECTURE.md` — where this feature fits in the Praxion architecture (row: "Project metrics command" in §3 Components).
- Architectural decision records (reference by slug; the concrete IDs are assigned at merge-to-main):
  - `storage-schema-for-project-metrics` — freezes the three-file artifact triple, the 16 aggregate columns, and the schema-mismatch policy.
  - `collector-protocol` — defines the `resolve()` / `collect()` / `describe()` extension seam used by every tool wrapper.
  - `graceful-degradation-policy` — establishes the hard floor (git + stdlib) and the per-collector skip-marker contract.
  - `hotspot-formula` — defines `hotspot_score = churn_90d_lines × max_ccn` and the lizard → scc-fallback → skipped degradation chain.

## 2. The artifact triple

Every successful run writes exactly three files to `.ai-state/metrics_reports/`:

| File | Role | Content |
|------|------|---------|
| `.ai-state/metrics_reports/METRICS_REPORT_<timestamp>.json` | Canonical machine-readable payload | Full report — aggregate, tool_availability, every collector namespace, hotspots, trends, run_metadata |
| `.ai-state/metrics_reports/METRICS_REPORT_<timestamp>.md` | Derived human-readable rendering | Deterministic nine-section layout; no information that is not also in the JSON |
| `.ai-state/metrics_reports/METRICS_LOG.md` | Append-only table | One row per run, columns match the frozen aggregate block plus a trailing `report_file` link |

**Naming convention.** `<timestamp>` is `YYYY-MM-DD_HH-MM-SS` in UTC — no colons (portable across macOS, Linux, Windows). The log filename has no timestamp; it accumulates across every run.

**Lifecycle.** All three files are committed to git. Deleting a `metrics_reports/METRICS_REPORT_*.json` after the fact affects trend computation on the next run — see [§9 Mid-history pruning policy](#9-mid-history-pruning-policy).

**Atomicity.** The three files are written as a unit. A run that fails partway through does not leave a half-written JSON + a fresh log row — argparse rejection exits before any file is touched, and the final write sequence is JSON → MD → log row. If the JSON write fails, no MD or log row lands.

## 3. Frozen aggregate-block columns

The `aggregate` block is the **time-series axis** of `METRICS_LOG.md`. Its 16 columns are **frozen on first release** by the storage-schema ADR: adding a column bumps the minor version and requires an ADR amendment, renaming or removing a column is a major bump.

Declaration order below matches `AGGREGATE_COLUMNS` in `scripts/project_metrics/schema.py` verbatim. The log's column order matches this order exactly, followed by a trailing `report_file` link column.

| # | Column | JSON path | Type | Unit | Source | Nullable | Rationale |
|---|--------|-----------|------|------|--------|----------|-----------|
| 1 | `schema_version` | `aggregate.schema_version` | string (semver) | — | runner constant | No | Every log row must carry the schema tag so schema-mismatch delta policy fires without re-reading the full JSON. |
| 2 | `timestamp` | `aggregate.timestamp` | string (ISO 8601 UTC) | — | runner (`datetime.now(UTC)`) | No | Time axis of the log chart. Filename timestamp is user-rename tolerant; this field is machine-authoritative. |
| 3 | `commit_sha` | `aggregate.commit_sha` | string | — | `git rev-parse HEAD` | No | Ties every row to a concrete code state; enables point-in-history regression analysis. |
| 4 | `window_days` | `aggregate.window_days` | integer | days | CLI `--window-days` | No | Churn/entropy/truck-factor all depend on window; comparing a 30-day to a 90-day run without this field silently lies. |
| 5 | `sloc_total` | `aggregate.sloc_total` | integer | lines | scc (preferred) or stdlib fallback | No | Size baseline; denominator for every density-style derived metric. |
| 6 | `file_count` | `aggregate.file_count` | integer | files | scc or git ls-files | No | Navigation scale — the reviewer's "surface" number. |
| 7 | `language_count` | `aggregate.language_count` | integer | langs | scc (0 when scc unavailable) | No | Monolingual vs polyglot repos diverge in everything else; must be visible at aggregate level. |
| 8 | `ccn_p95` | `aggregate.ccn_p95` | number \| null | — | lizard | Yes | Flagship complexity (cross-language via lizard); null when lizard is unavailable. |
| 9 | `cognitive_p95` | `aggregate.cognitive_p95` | number \| null | — | complexipy | Yes | Python-specific complexity; null on non-Python repos or when complexipy is unavailable. |
| 10 | `cyclic_deps` | `aggregate.cyclic_deps` | integer \| null | non-trivial SCCs | pydeps | Yes | Architecture health; gaming-resistant; null when pydeps is unavailable or the repo has no `__init__.py`. |
| 11 | `churn_total_90d` | `aggregate.churn_total_90d` | integer | lines | git (hard floor) | No | Effort signal; git-only so always present; feeds hot-spot denominator. |
| 12 | `change_entropy_90d` | `aggregate.change_entropy_90d` | number | Shannon bits | git | No | Process-focus signal; single-number summary of how scattered development is; outperforms product metrics for defect prediction. |
| 13 | `truck_factor` | `aggregate.truck_factor` | integer | authors | git (Avelino 2016 greedy removal) | No | Organizational risk; most projects have never measured theirs. |
| 14 | `hotspot_top_score` | `aggregate.hotspot_top_score` | number \| null | composed | `hotspot.py` composer | Yes | Headline composite — max of churn × complexity across files; null when both lizard and scc are unavailable. |
| 15 | `hotspot_gini` | `aggregate.hotspot_gini` | number \| null | 0.0–1.0 | `hotspot.py` composer | Yes | Distribution shape — distinguishes "one pathological file" from "everything is mid-hot"; null under the same conditions as the top score. |
| 16 | `coverage_line_pct` | `aggregate.coverage_line_pct` | number \| null | 0.0–1.0 | coverage collector (artifact parse) | Yes | Test-health scale; null when no coverage artifact is present. |

Inclusion rule (explicit): a column lives in `aggregate` iff it belongs on a time-series chart. Full-fidelity per-file and per-function data lives in the collector namespaces, not here. Blacklisted from the aggregate (known gameable or low-signal): raw comment density, test-to-code ratio, TODO count.

## 4. Tool availability shape

The `tool_availability` block is a mapping from collector name to a per-tool record. The `status` field takes one of exactly five canonical values:

| Status | Meaning | Renders in MD as |
|--------|---------|------------------|
| `available` | Tool is present; `collect()` ran | version number |
| `unavailable` | Tool is applicable but absent; user can fix by installing | `_not computed — install <tool>_` |
| `not_applicable` | Tool does not apply to this repo (e.g., pydeps on zero-Python) | `_not applicable for this repository_` |
| `error` | Tool crashed or produced unparseable output | `_not computed — <reason>_` |
| `timeout` | Tool exceeded its deadline | `_not computed — timed out after <N>s_` |

**One example per status:**

```json
"git":        {"status": "available",     "version": "2.45.1"}
"complexipy": {"status": "unavailable",   "reason": "uvx_not_found", "install_hint": "install uv"}
"pydeps":     {"status": "not_applicable","reason": "no_importable_packages"}
"lizard":     {"status": "error",         "reason": "xml_parse_failed", "traceback_excerpt": "..."}
"scc":        {"status": "timeout",       "timeout_seconds": 60}
```

`available` records carry `version`; `unavailable` carries `reason` and `install_hint`; `not_applicable` carries `reason`; `error` carries `reason` and a truncated `traceback_excerpt`; `timeout` carries `timeout_seconds`. Additional tool-specific fields land under `details` and are informational.

**Content states vs availability states.** `no_artifact` and `stale` describe what the *coverage* tool found, not whether the tool ran. They live inside the `coverage` namespace (`coverage.status`), not inside `tool_availability`. See [§7 Skip-marker uniform shape](#7-skip-marker-uniform-shape).

## 5. Collector namespace blocks

Each collector writes into its own top-level JSON namespace key. Namespace shapes are **not** frozen across schema versions — only the aggregate is load-bearing for downstream consumers. The shapes below are current as of schema version 1.0.0.

### 5.1 `git` namespace — hard floor

```json
"git": {
  "churn_90d":          {"<path>": <int>, ...},
  "churn_total_90d":    <int>,
  "change_entropy_90d": <number>,
  "change_coupling":    [{"file_a": "...", "file_b": "...", "cochange_count": <int>}, ...],
  "ownership":          {"<path>": {"major": [...], "minor": [...]}, ...},
  "truck_factor":       <int>,
  "age_days":           {"<path>": <int>, ...},
  "file_count":         <int>,
  "churn_source":       "numstat" | "commit_count_fallback"
}
```

`churn_source = "commit_count_fallback"` indicates a shallow clone (numstat unavailable); the churn field counts commits touching the file instead of lines changed, and downstream consumers must weight the comparison accordingly.

### 5.2 `scc` namespace — Tier 0 soft dependency

```json
"scc": {
  "language_breakdown": {"<language>": {"sloc": <int>, "file_count": <int>}, ...},
  "per_file_sloc":      {"<path>": <int>, ...},
  "sloc_total":         <int>,
  "language_count":     <int>,
  "file_count":         <int>
}
```

When `scc` is unavailable the namespace is replaced by a uniform skip marker (see [§7](#7-skip-marker-uniform-shape)); `sloc_total` and `file_count` are still populated in `aggregate` via a Python stdlib fallback.

### 5.3 `lizard` namespace — cross-language cyclomatic CCN

```json
"lizard": {
  "files": {
    "<path>": {
      "max_ccn":        <int>,
      "p75_ccn":        <number> | null,
      "p95_ccn":        <number> | null,
      "function_count": <int>,
      "ccns":           [<int>, ...]
    }, ...
  },
  "aggregate": {
    "ccn_p95":             <number> | null,
    "ccn_p75":             <number> | null,
    "total_function_count": <int>
  }
}
```

Empty function set yields null percentiles (not zero) so "no signal" is distinguishable from "trivial one-liners only".

### 5.4 `complexipy` namespace — Python cognitive complexity

Same shape as `lizard` with `cognitive_*` field names:

```json
"complexipy": {
  "files": {
    "<path>": {
      "max_cognitive":     <int>,
      "p75_cognitive":     <number> | null,
      "p95_cognitive":     <number> | null,
      "function_count":    <int>,
      "cognitive_scores":  [<int>, ...]
    }, ...
  },
  "aggregate": {
    "cognitive_p95":        <number> | null,
    "cognitive_p75":        <number> | null,
    "total_function_count": <int>
  }
}
```

Renders as `not_applicable` when no `.py` files are present in the committed file set.

### 5.5 `pydeps` namespace — Python coupling and cyclic SCCs

```json
"pydeps": {
  "modules": {
    "<dotted.module.name>": {
      "afferent_coupling": <int>,
      "efferent_coupling": <int>,
      "instability":       <number> | null
    }, ...
  },
  "cyclic_sccs": [["mod_a", "mod_b", "mod_c"], ...],
  "aggregate": {
    "cyclic_deps":   <int>,
    "total_modules": <int>
  }
}
```

`instability = Ce / (Ca + Ce)` clamped to `[0.0, 1.0]`; isolated modules (Ca = Ce = 0) yield `null` rather than 0.0 — "undefined" is the honest signal for a module with no import edges. `cyclic_sccs` lists only non-trivial SCCs (size > 1); the count becomes `aggregate.cyclic_deps`. Renders as `not_applicable` when no `__init__.py` is present in the committed tree.

### 5.6 `coverage` namespace — line coverage (reads existing artifact)

```json
"coverage": {
  "status":          "ok" | "stale",
  "artifact_path":   "coverage.xml",
  "artifact_format": "cobertura" | "lcov",
  "line_pct":        <number>,
  "per_file":        {
    "<path>": {
      "line_pct":      <number>,
      "lines_total":   <int>,
      "lines_covered": <int>
    }, ...
  }
}
```

The coverage collector **never invokes a test runner**. It reads pre-existing `coverage.xml` (Cobertura) or `lcov.info` (LCOV) from the repo root or a `coverage/` subdirectory. The `status` field is `"stale"` when the artifact's git-commit timestamp is strictly older than the HEAD commit timestamp; the collector still extracts the line percentage but the MD renderer flags it with `(stale — regenerate)`. When no artifact is present, the whole namespace is replaced by a uniform skip marker with `install_hint: "generate a coverage report (coverage.xml or lcov.info) before running /project-metrics"`.

### 5.7 `hotspots` namespace — composed (not a collector)

```json
"hotspots": {
  "status":             "ok" | "skipped",
  "top_n":              [
    {
      "path":       "<path>",
      "churn_90d":  <int>,
      "complexity": <number>,
      "hotspot_score": <number>,
      "rank":       <int>
    }, ...
  ],
  "complexity_source":  "lizard" | "scc_fallback"
}
```

The composer reads churn from the `git` namespace and complexity from the `lizard` namespace (preferred) or the `scc` namespace (fallback). When both complexity sources are skipped, `status = "skipped"`, `top_n = []`, and the two aggregate hotspot columns become null. Files tied on score sort lexicographically ascending by path so the Top-N list is deterministic across identical-input runs.

## 6. Trends block

The `trends` block reports the delta between the current run and the most-recent-strictly-prior `METRICS_REPORT_*.json` found in `.ai-state/metrics_reports/`. It is a tagged union discriminated by `status` — one of four values.

### `first_run`

No usable prior report on disk.

```json
"trends": {"status": "first_run"}
```

### `schema_mismatch`

Prior report's major or minor schema version differs from the current run. Numeric deltas are **intentionally suppressed** — a delta across incompatible schemas would fabricate a comparison.

```json
"trends": {
  "status":         "schema_mismatch",
  "prior_report":   "METRICS_REPORT_<timestamp>.json",
  "prior_schema":   "0.9.0",
  "current_schema": "1.0.0"
}
```

The MD renders `⚠ Trend delta deferred — prior report used schema <X>, current is <Y>.` The log row still lands; its future delta columns (none in v1) would be rendered as `—`.

### `computed`

Prior schema is compatible (same major.minor; patch differences are ignored). Deltas are populated for each nullable-safe numeric aggregate column.

```json
"trends": {
  "status":       "computed",
  "prior_report": "METRICS_REPORT_<timestamp>.json",
  "deltas": {
    "sloc_total":      <int>,
    "ccn_p95":         <number> | null,
    "cognitive_p95":   <number> | null,
    "cyclic_deps":     <int> | null,
    "churn_total_90d": <int>,
    "truck_factor":    <int>
  }
}
```

When a column was null in either run, its delta is null rather than a spurious zero.

### `no_prior_readable`

A prior file exists but failed to parse — corruption, truncation, missing `aggregate` block, or missing `schema_version`. Distinct from `first_run` so users notice a pathology rather than assume a fresh start.

```json
"trends": {
  "status":       "no_prior_readable",
  "prior_report": "METRICS_REPORT_<timestamp>.json",
  "error":        "prior report is missing required 'aggregate' block"
}
```

## 7. Skip-marker uniform shape

Two layers of skip state, deliberately separated:

**Tool availability level** — whether the tool ran. Values: `available`, `unavailable`, `not_applicable`, `error`, `timeout` (see [§4](#4-tool-availability-shape)).

**Namespace level** — what the tool found. When a collector's resolution is anything but `available`, its whole namespace is replaced by:

```json
"<namespace>": {
  "status": "skipped",
  "reason": "tool_unavailable",
  "tool":   "<collector-name>"
}
```

Three keys, always the same three. The UI never has to distinguish "is this a git skip or a lizard skip?" — it treats every `status == "skipped"` block identically.

**Coverage-specific content states.** The coverage namespace has two content states inside its own block: `no_artifact` (the install hint goes into `tool_availability`, the namespace carries the uniform skip marker) and `stale` (the namespace is `status: "stale"` with the `line_pct` still extracted, because the number is useful even if out of date). Both states are coverage-specific because only coverage reads an existing artifact rather than invoking a tool.

## 8. Schema versioning

The top-level `schema_version` field carries a semver string. v1 ships `1.0.0`.

| Change type | Example | Version bump | Policy |
|-------------|---------|--------------|--------|
| **Additive-minor** | New aggregate column; new collector namespace | `1.0.0 → 1.1.0` | Old consumers still work; the new column is `null` in their view. Trend deltas proceed normally. |
| **Breaking-major** | Renaming an aggregate column; changing a unit; dropping a column | `1.0.0 → 2.0.0` | Requires a superseding ADR. A new `METRICS_LOG_v2.md` is created; the old log gets a one-line pointer appended. Trend deltas across the boundary land in `schema_mismatch`. |
| **Patch** | Bug fix; clearer `_source` annotation; fallback-order tweak | `1.0.0 → 1.0.1` | Trend deltas proceed normally. |

**Never silently change a column's meaning.** Redefining "churn" from line-sum to commit-count without renaming the column is a breaking change even if the field name is unchanged. The semver contract is on semantics, not syntax.

## 9. Mid-history pruning policy

If a user deletes a `metrics_reports/METRICS_REPORT_<timestamp>.json` between runs, the next run's trend computation selects the **most-recent-strictly-prior** surviving report by its embedded `aggregate.timestamp` — not the filename, not the filesystem mtime. This means:

- Deleting the most recent prior report causes the next run to compare against the one before it; deltas widen but stay coherent.
- Deleting every prior report causes the next run to report `status: "first_run"` — indistinguishable on the wire from a genuinely new project.
- Trend computation skips any candidate whose embedded timestamp is greater than or equal to the current run's timestamp. That single rule covers both the current run's own already-on-disk file and any clock-skew anomalies.
- Selection order is by **embedded `aggregate.timestamp`** (lexicographic over ISO 8601 strings), not by filename lexicographic order. The two agree in the common case but diverge if a user renames files.

Users who prune deliberately should understand that deltas in the next run span a wider gap than they might expect. The log preserves every row — so the full history is still visible there even if the JSONs are gone.

## 10. UI consumption paths

Three candidate UI implementations, ordered from simplest to richest. All three read the JSON directly; none parse the MD.

### Path A — Zero-install static HTML

One file, no build step, no framework. Drop it next to the JSON directory, serve with `python -m http.server`, point a browser at it. The `file://` protocol blocks `fetch()` for cross-origin reads, so a simple HTTP server is required.

```html
<!DOCTYPE html>
<meta charset="utf-8">
<title>Project metrics — time series</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<canvas id="chart" width="800" height="400"></canvas>
<script>
async function loadAll() {
  // Hardcoded index: in practice, generate `index.json` listing every
  // METRICS_REPORT_*.json at write time, or let the server return a directory listing.
  const index = await fetch('index.json').then(r => r.json());
  const reports = await Promise.all(
    index.files.map(f => fetch(f).then(r => r.json()))
  );
  reports.sort((a, b) => a.aggregate.timestamp.localeCompare(b.aggregate.timestamp));
  const labels = reports.map(r => r.aggregate.timestamp);
  const ccn = reports.map(r => r.aggregate.ccn_p95);
  const hotspot = reports.map(r => r.aggregate.hotspot_top_score);
  new Chart(document.getElementById('chart').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {label: 'CCN p95',       data: ccn,     spanGaps: true},
        {label: 'Hotspot top',   data: hotspot, spanGaps: true}
      ]
    },
    options: {spanGaps: true}  // null values (unavailable metrics) leave gaps
  });
}
loadAll();
</script>
```

Nullable columns (`ccn_p95`, `coverage_line_pct`, etc.) render as gaps in the chart because `spanGaps: true` is set. Downgrading a line to a gap is the honest rendering when a tool was absent for that run.

### Path B — Local MCP-driven server

A few-hundred-line FastAPI or Streamlit app that watches the `.ai-state/metrics_reports/` directory and serves REST endpoints. Useful when the UI needs to filter, search, or combine multiple projects. Minimal FastAPI stub:

```python
# metrics_mcp.py
from fastapi import FastAPI
from pathlib import Path
import json

app = FastAPI()
METRICS_DIR = Path(".ai-state/metrics_reports")

@app.get("/history")
def history():
    reports = []
    for p in sorted(METRICS_DIR.glob("METRICS_REPORT_*.json")):
        with p.open() as f:
            data = json.load(f)
        reports.append({
            "timestamp":   data["aggregate"]["timestamp"],
            "schema":      data["aggregate"]["schema_version"],
            "ccn_p95":     data["aggregate"]["ccn_p95"],
            "hotspot_top": data["aggregate"]["hotspot_top_score"],
            "commit_sha":  data["aggregate"]["commit_sha"],
        })
    return {"reports": reports}
```

Serve with `uvicorn metrics_mcp:app --port 8787`, then render the JSON response in any frontend.

### Path C — Datasette + SQLite

For richer querying (joins across runs, SQL filters, per-commit drill-down). Convert the JSON directory to a SQLite database once, then let Datasette serve the result.

```bash
# Convert every JSON to one row in a single SQLite table.
python - <<'PY'
import json, sqlite3
from pathlib import Path
conn = sqlite3.connect("metrics.db")
conn.execute("""
  CREATE TABLE IF NOT EXISTS aggregate (
    timestamp TEXT PRIMARY KEY, commit_sha TEXT, schema_version TEXT,
    sloc_total INTEGER, ccn_p95 REAL, cognitive_p95 REAL,
    cyclic_deps INTEGER, churn_total_90d INTEGER,
    truck_factor INTEGER, hotspot_top_score REAL, hotspot_gini REAL,
    coverage_line_pct REAL
  )
""")
for p in Path(".ai-state/metrics_reports").glob("METRICS_REPORT_*.json"):
    agg = json.loads(p.read_text())["aggregate"]
    conn.execute(
      "INSERT OR REPLACE INTO aggregate VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (agg["timestamp"], agg["commit_sha"], agg["schema_version"],
       agg["sloc_total"], agg["ccn_p95"], agg["cognitive_p95"],
       agg["cyclic_deps"], agg["churn_total_90d"],
       agg["truck_factor"], agg["hotspot_top_score"], agg["hotspot_gini"],
       agg["coverage_line_pct"]))
conn.commit()
PY

# Serve.
datasette metrics.db --port 8001
```

Datasette gives faceted search, SQL console, per-row permalinks, and an auto-generated chart view on any numeric column.

### UI path selection

- **Path A** — single-project audits, occasional check-ins, zero build tooling. Lowest effort.
- **Path B** — multi-project dashboards, filtering, search, or programmatic access. Needs a Python runtime.
- **Path C** — historical trend analysis with SQL, longest retention, cross-project joins. Needs SQLite familiarity.

All three consume the same JSON. No UI path is painted into a corner by the storage contract.

## 11. Gaming analysis summary

Every metric has a gaming vector; the hotspot ADR enumerates the full table for the composed hot-spot score. Summary here to guide interpretation:

**Most gaming-resistant (good headline metrics).**

- `truck_factor` — requires coordinated author activity across many files; gaming is indistinguishable from actually distributing knowledge (which is the goal).
- `cyclic_deps` — the import graph tells the truth; reducing the count requires real decoupling.
- `change_entropy_90d` — rewards focus; gaming requires faking work distribution, which is easier to solve the underlying problem than to fake.

**Moderately gameable.**

- `hotspot_top_score` and `hotspot_gini` — can be gamed by mechanically extracting helpers to lower per-file `max_ccn`. The score drops, but the underlying complexity moved rather than being solved. Framing in the MD is "files that combine high churn and high complexity," not "files that are bad."
- `ccn_p95` / `cognitive_p95` — extract-method refactors lower the number without solving readability. Usually a net win anyway.

**Most gameable (never made the aggregate).**

- Raw SLOC counts — trivially inflated by dead code.
- Coverage percentage — inflated by low-quality tests that execute lines without asserting behaviour. `coverage_line_pct` *is* in the aggregate, but as a scale marker, not a quality gate.
- TODO density, comment-to-code ratio, test-to-code ratio — all explicitly blacklisted from the aggregate.

**Future-work mitigations** (not in v1). Whitespace-agnostic churn (`git log -w`); generated-file filtering via `linguist-generated`; libyears as a dependency-freshness signal that is uniformly gaming-resistant. Tracked in the roadmap.

## 12. Generated-files confound

**The problem.** Generated files — compiler output, protobuf descriptors, minified JS, vendored third-party code, Bazel-gen targets — inflate `file_count`, `sloc_total`, and `churn_total_90d` when they are committed to git. A repo with 100K lines of hand-written code and 500K lines of committed compiler output reports a `sloc_total` of 600K, and its top churn files are likely to be the generated ones.

**v1 policy: the command does not apply the `linguist-generated` heuristic.** Every committed file is treated as source. This is deliberate: auto-detecting generated files is a correctness hazard (false positives on hand-written scaffolding, false negatives on novel generators), and the honest reading is that every line a project commits is a line a project maintains.

**What this means for users.**

- If your repo commits protobuf-generated `_pb2.py` files, they will appear in the top-N hotspots and inflate the aggregate. This is accurate — your git history *does* rewrite those files repeatedly.
- If your repo commits Bazel build artifacts or minified JS, the `sloc_total` will be dominated by them. The count is truthful; whether the count is *useful* depends on whether you treat those files as part of the project.
- Baseline ratios (e.g., "churn per SLOC") will look strange on repos with heavy generated content.

**Workarounds available today.**

- Add generated paths to `.gitignore` so they are not committed in the first place.
- Accept the inflation and interpret the metrics with the generated-file overhead in mind — a repo reviewer reading the MD should notice the top-N hotspots and apply their own filter.
- Use the raw per-file data in the `scc.per_file_sloc`, `git.churn_90d`, and `lizard.files` namespaces to compute custom aggregates with generated files excluded. The JSON gives you everything you need to do this without re-running the command.

**v2 consideration.** A future version may respect `.gitattributes linguist-generated=true` annotations when they are present, effectively asking the user to mark generated paths explicitly. This avoids the auto-detection hazard while giving projects that want the filtering a principled way to ask for it.

---

**Feedback.** If any shape in this document disagrees with what `/project-metrics` actually writes, the writer is the authority — file it as a documentation bug.
