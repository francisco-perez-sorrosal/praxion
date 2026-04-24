# SPEC: `/project-metrics` Command — Project Complexity/Health Metrics

**Task slug**: `project-metrics`
**Tier**: Full (escalated from Standard — decomposition yielded 18 steps, exceeding the ~10-step threshold; file breadth is wide but depth remains shallow)
**Archived**: (pipeline in flight — archival at merge-to-main)
**Status**: Planned
**ADRs**: `dec-draft-b068ad8e` (storage schema), `dec-draft-c566b978` (collector protocol), `dec-draft-8b26adef` (graceful degradation), `dec-draft-ad8b8286` (hotspot formula). Promoted to stable `dec-NNN` at merge-to-main via `scripts/finalize_adrs.py`.

## Feature Summary

Adds a user-invoked `/project-metrics` slash command that computes a curated set of project complexity / health metrics on any Praxion-onboarded repository. Each invocation produces a timestamped artifact triple: a canonical JSON payload, a derived human-readable MD rendering, and a row appended to `.ai-state/METRICS_LOG.md`. The command degrades gracefully per-collector when optional tooling is unavailable, with only `git` + Python 3.11+ stdlib as the hard floor. The aggregate column contract is frozen on v1.0.0 so `METRICS_LOG.md` remains a stable time series; additive schema changes bump minor version, breaking changes require a superseding ADR and fork a `METRICS_LOG_v2.md`.

V1 scope: Tier 0 (git + stdlib; optional `scc` enrichment) + Tier 1 Python (`lizard`, `complexipy`, `pydeps`, `coverage.py` artifact read). TS / Go / Rust collectors deferred to v2 via the same protocol. No HTML UI in v1; `docs/metrics/README.md` ships as a complete JSON schema reference so static HTML (Path A), local server (Path B), or Datasette/Grafana (Path C) consumers can be written against the frozen contract without reading the implementation.

## Behavioral Specification (REQ-PM-01 through REQ-PM-16)

The 12 acceptance criteria in `SYSTEMS_PLAN.md` expand into 16 REQs below. One-to-one where the AC already names a single behavior; one-to-many where the AC covers JSON and MD surfaces that are validated separately.

### Command surface

- **REQ-PM-01** — `/project-metrics` is registered as a Claude Code slash command, appears under `commands/`, and runs end-to-end on the Praxion repo itself, producing a `.ai-state/METRICS_REPORT_*.json` + `.md` artifact pair and appending a new row to `.ai-state/METRICS_LOG.md`. *(AC1)*
- **REQ-PM-02** — The command completes successfully on a minimal fixture repository that has only `git` and Python 3.11 stdlib available — no `uv`/`uvx`, no `scc`, no `npx`, no third-party packages — producing an artifact triple with Tier 0 data and skip markers for every unavailable collector. *(AC2)*
- **REQ-PM-03** — The command accepts `--window-days <N>` (default 90) and `--top-n <N>` (default 10); invalid values (non-integer, negative, zero) produce a clear error message on stderr and exit non-zero without writing any artifact file (no partial writes). *(AC9)*
- **REQ-PM-04** — The Python package is importable under stdlib alone (`python -c "import scripts.project_metrics"` succeeds with no third-party installs); all optional tooling (`lizard`, `complexipy`, `pydeps`) is invoked via subprocess, never `import`-ed. *(AC10)*
- **REQ-PM-05** — Running the command on a Praxion-installed *downstream* project (a project that uses the `i-am` plugin but does not vendor Praxion's own source) works end-to-end. The shipped command and package must not reference any path specific to this repo or any concrete filename/timestamp; shipped-artifact-isolation check (`scripts/check_shipped_artifact_isolation.py`) passes against both `commands/project-metrics.md` and `scripts/project_metrics/`. *(AC11)*

### JSON contract

- **REQ-PM-06** — The JSON artifact carries a top-level `schema_version` field (semver), a top-level `timestamp` (ISO 8601 UTC), and an `aggregate` block whose keys exactly match the `METRICS_LOG.md` table header. *(AC3, part 1)*
- **REQ-PM-07** — The JSON artifact contains a `tool_availability` block naming every optional tool that was considered for the run, with one of five documented statuses: `available`, `unavailable`, `not_applicable`, `error`, `timeout`. *(AC3, part 2)*
- **REQ-PM-08** — Every metric skipped because an optional tool was unavailable appears in the JSON with a machine-readable marker (`{"status": "skipped", "reason": "tool_unavailable", "tool": "<name>"}` in its namespace block) so downstream consumers can treat all skips uniformly. *(AC4, JSON surface)*
- **REQ-PM-09** — The `aggregate` block column set exactly matches the 16 columns declared in the Schema ADR (dec-draft-b068ad8e), in declaration order. Any attempt to add or reorder columns fails the test that asserts the header against the frozen list. *(AC7, v1.0.0 freeze)*

### MD rendering

- **REQ-PM-10** — For every metric skipped because an optional tool was unavailable, the MD report surfaces a human-readable `_not computed — install <tool>_` line, with an "Install to improve" section enumerating actionable one-liners for each Unavailable tool. `NotApplicable` collectors are listed in a Tool Availability section but omitted from the Install section. *(AC4, MD surface)*

### Trends

- **REQ-PM-11** — On a second run, the MD report surfaces deltas against the most-recent-prior `METRICS_REPORT_*.json`: for each aggregate-block field, a `| metric | current | prior | delta | delta_pct |` table. On first run (no prior), the MD reads "first run — no deltas" and the JSON `trends` block is `{"status": "first_run", "prior": null}`. *(AC5)*
- **REQ-PM-12** — When the prior report's `schema_version` major or minor differs from the current run, numeric deltas are NOT computed. The JSON `trends` block is `{"status": "schema_mismatch", "prior_schema": "...", "current_schema": "...", "prior_report": "<filename>"}` and the MD surfaces a one-line warning. Patch version differences proceed with normal delta computation. *(AC6)*

### Hot-spots

- **REQ-PM-13** — The MD report lists a Top-N hot-spot table (default N=10) with exactly four columns per row: file path, `churn_90d_lines`, `max_ccn` (labeled `complexity_source: scc_fallback` when lizard was unavailable), `hotspot_score`, and `rank`. Given the same git SHA and file-system state, the list is byte-deterministic. *(AC8)*

### Documentation

- **REQ-PM-14** — `docs/metrics/README.md` documents the JSON schema completely: all 16 frozen aggregate columns with type + unit + source, the namespace block shapes for every collector, the tool_availability statuses, the trend block variants (first_run / schema_mismatch / normal), and the skip-marker uniform shape. A third party can write a static HTML UI (Path A) against this document without consulting the SYSTEMS_PLAN or the ADRs. *(AC12)*

### Determinism and safety

- **REQ-PM-15** — Every collector is deterministic given the same git SHA and file-system state; the byte-exact JSON output of two successive runs on an unchanged repo differs only in `aggregate.timestamp` and `run_metadata.wall_clock_seconds`. *(derived from AC8 and the collector-protocol ADR's determinism clause)*
- **REQ-PM-16** — The command never invokes the test suite. `CoverageCollector` reads pre-existing `coverage.xml` or `lcov.info` only; if neither artifact exists, `coverage.status = "no_artifact"` with an install hint and `aggregate.coverage_line_pct = null`. *(derived from the graceful-degradation ADR's non-negotiable)*

## Acceptance Criteria → REQ Mapping

| AC | Description (abbrev.) | REQ(s) |
|----|-----------------------|--------|
| AC1 | End-to-end on Praxion | REQ-PM-01 |
| AC2 | Works on stdlib-only fixture | REQ-PM-02 |
| AC3 | JSON schema_version + timestamp + aggregate + tool_availability | REQ-PM-06, REQ-PM-07 |
| AC4 | Skip markers in JSON + MD | REQ-PM-08 (JSON), REQ-PM-10 (MD) |
| AC5 | Deltas on second run; N/A on first | REQ-PM-11 |
| AC6 | Schema-mismatch delta policy | REQ-PM-12 |
| AC7 | Aggregate column freeze | REQ-PM-09 |
| AC8 | Deterministic Top-N hot-spots with four columns | REQ-PM-13 (+ REQ-PM-15 for determinism) |
| AC9 | CLI arg validation | REQ-PM-03 |
| AC10 | Package importable under stdlib alone | REQ-PM-04 |
| AC11 | Works on downstream Praxion projects | REQ-PM-05 |
| AC12 | docs/metrics/README.md is a complete contract | REQ-PM-14 |
| (implicit: never run tests) | CoverageCollector discipline | REQ-PM-16 |

## Traceability Matrix

The per-REQ traceability map (tests + implementation files) is maintained in `.ai-work/project-metrics/traceability.yml` during the pipeline and rendered into this section at feature-end archival. **Code and tests do not embed REQ IDs** (per `rules/swe/id-citation-discipline.md`) — the YAML is the canonical source of truth during the pipeline.

_Matrix rendered at feature-end from `traceability.yml` and `TEST_RESULTS.md`._

## Key Decisions (Cross-Reference)

See the four draft ADRs for full rationale. Summary:

1. **Storage schema** (dec-draft-b068ad8e): JSON canonical + MD derived + append-only `METRICS_LOG.md`; 16-column aggregate frozen on v1.0.0; schema-mismatch policy defers deltas rather than fabricating.
2. **Collector protocol** (dec-draft-c566b978): three-method protocol (`resolve` / `collect` / `describe`) with three resolution outcomes (`Available` / `Unavailable` / `NotApplicable`) and error isolation at the runner.
3. **Graceful degradation** (dec-draft-8b26adef): only `git` + Python 3.11+ stdlib are hard floor; every other tool is soft with uniform skip markers in JSON and MD; never runs the test suite.
4. **Hotspot formula** (dec-draft-ad8b8286): `churn_90d_lines × max_ccn`; lizard preferred, scc branch-count fallback, both unavailable → hotspots skipped; cross-language via cyclomatic, cognitive reserved for per-language Python breakdown.

## Implementation-Planner Decisions (beyond architect's scope)

1. **Tier escalation to Full** — 18 steps exceed the Standard ~10-step threshold. The breadth is wide (6 collectors, 4 composition modules, CLI, command, docs, tests) though depth remains shallow.
2. **Test layout: `scripts/project_metrics/tests/` inside the package**, not `tests/scripts/project_metrics/`. Precedent: `task-chronograph-mcp/tests/` keeps a package's tests self-contained; the monolithic-script `scripts/test_finalize_adrs.py` precedent does not generalize to a multi-module package.
3. **Sequential collector execution in v1** — per architect's recommended default. ThreadPoolExecutor deferred to v2 where parallelization can be measured, not guessed.
4. **Committed fixture repo at `scripts/project_metrics/tests/fixtures/minimal_repo/`** — tiny git repo with known SHAs, checked in, so integration tests are byte-reproducible. Matches `test_finalize_adrs.py`'s style of deterministic setup.
5. **No `--dry-run` in v1** — defer to v2. Keeps v1 CLI surface minimal per Simplicity First.
6. **No self-clean of `.ai-work/project-metrics/`** — matches `/roadmap` precedent; forensic state preserved; cleanup via `/clean-work`.
7. **No auto-stage of generated files** — command prints the three written paths; user stages explicitly. Matches sentinel's model.

## Post-Ship Follow-ups (tracked for v2)

Deferred non-goals from the SYSTEMS_PLAN that become candidates for v2:

- Tier 1 TS/Go/Rust collectors (protocol already shaped for extension).
- `osv-scanner` / `pip-audit` for dependency freshness (network-dependent, separate command).
- `jscpd` duplicate detection (lower-tier signal per research).
- Parallel collector execution with measured latency budgets.
- `--dry-run` mode.
- Mid-history report pruning — document lexicographic-timestamp selection policy in `docs/metrics/README.md` when the schema ADR finalizes.
