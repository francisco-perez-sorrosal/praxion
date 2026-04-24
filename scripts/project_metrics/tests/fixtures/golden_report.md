# Project Metrics Report

Generated at 2026-04-23T12:00:00Z

- Commit: `abcdef1234567890abcdef1234567890abcdef12`
- Schema version: `1.0.0`

## Tool Availability

| Tool | Status | Version | Detail |
| --- | --- | --- | --- |
| git | available | 2.43.0 | — |
| scc | available | 3.3.0 | — |
| lizard | available | 1.17.10 | — |
| complexipy | unavailable | — | not installed |
| pydeps | available | 1.12.20 | — |
| coverage | not_applicable | — | no Python sources |

## Install to improve

- `complexipy`: `uv tool install complexipy` (cognitive complexity per function)

## Aggregate Summary

The repository carries 1234 SLOC across 42 files in 3 languages; 90-day churn totals 567 changes with change entropy 2.10. Truck factor is 2; top hot-spot score is 123.40 with Gini 0.75. Coverage is not computed.

| Column | Value |
| --- | --- |
| schema_version | 1.0.0 |
| timestamp | 2026-04-23T12:00:00Z |
| commit_sha | abcdef1234567890abcdef1234567890abcdef12 |
| window_days | 90 |
| sloc_total | 1234 |
| file_count | 42 |
| language_count | 3 |
| ccn_p95 | 7.50 |
| cognitive_p95 | _not computed — install complexipy_ |
| cyclic_deps | 0 |
| churn_total_90d | 567 |
| change_entropy_90d | 2.10 |
| truck_factor | 2 |
| hotspot_top_score | 123.40 |
| hotspot_gini | 0.75 |
| coverage_line_pct | _not applicable for this repository_ |

## Top-5 Hot-spots

| # | Path | Churn | Complexity | Score |
| --- | --- | --- | --- | --- |
| 1 | `src/core/engine.py` | 120 | 18.0 | 2160.00 |
| 2 | `src/core/parser.py` | 80 | 14.0 | 1120.00 |
| 3 | `src/api/routes.py` | 60 | 12.0 | 720.00 |
| 4 | `src/util/cache.py` | 30 | 9.0 | 270.00 |
| 5 | `src/util/log.py` | 20 | 6.0 | 120.00 |

## Trends

| Metric | Current | Prior | Delta | Delta % |
| --- | --- | --- | --- | --- |
| sloc_total | 1234 | 1200 | 34 | 2.83% |
| file_count | 42 | 40 | 2 | 5.00% |
| churn_total_90d | 567 | 500 | 67 | 13.40% |
| coverage_line_pct | — | — | — | — |

## Per-collector Deep Dive

### git

- Total commits in window: 250
- Unique authors: 6
- Change entropy: 2.10

### scc

- Files counted: 42
- SLOC total: 1234
- Languages: Python, Markdown, YAML

### lizard

- Functions analyzed: 210
- CCN p95: 7.50
- CCN max: 18.0

### complexipy

_not computed — install complexipy_

### pydeps

- Modules: 48
- Cyclic SCCs: 0

### coverage

_not applicable for this repository_

## Per-language Breakdown

| Language | Files | SLOC | CCN p95 | Cognitive p95 |
| --- | --- | --- | --- | --- |
| Python | — | — | 7.50 | _not computed — install complexipy_ |
| Markdown | — | — | — | — |
| YAML | — | — | — | — |

## Run Metadata

- Command version: 0.2.1.dev0
- Python version: 3.11.7
- Wall clock: 4.20s
- Window days: 90
- Top-N: 5
