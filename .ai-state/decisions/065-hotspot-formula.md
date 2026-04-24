---
id: dec-065
title: Hot-spot composition formula — churn_lines × max CCN, cross-language default
status: proposed
category: architectural
date: 2026-04-23
summary: Define the default hot-spot formula for /project-metrics as churn_lines_90d × per-file max cyclomatic CCN (lizard preferred, scc branch-count fallback) and explicitly reject alternatives that break cross-language comparability or are gameable
tags: [architecture, metrics, composition, hotspots, project-metrics]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - scripts/project_metrics/hotspot.py
  - scripts/project_metrics/schema.py
  - scripts/project_metrics/report.py
  - docs/metrics/README.md
---

## Context

Hot-spots (`churn × complexity`) are the flagship composite metric identified in the theory research (`RESEARCH_FINDINGS_metrics-theory.md:225`, "Hot-spots = churn(90d) × cognitive-complexity … the single highest-signal metric in this entire list"). Tornhill's 400-KLOC / 89-dev / 18K-commit study found that 4% of hot-spot files contained 72% of defects — a ratio strong enough to be load-bearing as a headline metric.

The architectural question the user raised: define "churn" (commits-touching vs lines-changed vs both) and define "complexity" (scc branch-count vs lizard CCN vs complexipy cognitive). Pick one per-dimension default and document why. Decisions here determine:

- Whether the headline metric is cross-language comparable or Python-specific.
- Whether the metric is gameable via micro-commits.
- What happens when the preferred complexity tool is unavailable (degradation interaction with dec-064).

## Decision

**Default formula: `hotspot_score(file) = churn_90d_lines(file) × max_ccn(file)`**

where:

- `churn_90d_lines(file)` = sum of `lines_added + lines_deleted` from `git log --numstat --since="90 days ago" -- <file>`, per `window_days` (default 90).
- `max_ccn(file)` = maximum cyclomatic complexity of any function in the file, from `lizard` output.

**Fallbacks:**

- If numstat data is unavailable (shallow clone with `--depth=1`): churn degrades to **commit-count-touching**, marked `churn_source: "commit_count_fallback"` in both JSON and MD. Commit count is a defensible but noisier proxy.
- If lizard is unavailable: complexity degrades to **scc branch-count per file**, marked `complexity_source: "scc_fallback"` in both JSON and MD. This is a coarse proxy (branch tokens != CFG edges) and is labeled as such.
- If both lizard AND scc are unavailable: hot-spot composition is **skipped entirely**. `hotspots.status = "skipped"`, `aggregate.hotspot_top_score = null`, `aggregate.hotspot_gini = null`. Pure git data is not enough to compute hot-spots honestly.

**Raw dimensions surfaced alongside the composed score**: Top-N hot-spot list in the MD shows `churn_90d_lines`, `max_ccn`, `hotspot_score`, and `rank` — four columns. The reader can see which dimension drove the ranking.

**`hotspot_gini`**: Gini coefficient over the distribution of `hotspot_score` across all files with non-zero score. Distinguishes "one pathological file in a clean repo" (gini near 1.0) from "everything is moderately hot" (gini near 0.0). Complements the top score with a shape signal.

### Per-dimension justifications

**Why churn-in-lines, not commit-count, by default:**

- Lines-changed captures *effort* per commit. A 500-line refactor commit that touches one file should count more than a one-line typo fix.
- Commit-count is gameable by micro-commits — a developer chasing hot-spot reduction can split one change into ten, which reduces nothing but inflates the numerator.
- Lines-changed has its own gaming vector (whitespace diffs, mass formatter runs) but these produce localized spikes that are detectable; commit-count gaming is invisible.
- All modern hot-spot literature (Tornhill; CodeScene) uses lines-changed or a weighted combination. Commit-count alone is a step backwards.

**Why max CCN (per file), not p95 or mean:**

- The signal we want is "this file contains something ugly." If a file has 30 clean helpers and one 25-CCN monster, the mean hides the monster and the p95 may too. Max surfaces it.
- The Top-N list shows the max. The per-function breakdown lives in `lizard`'s namespace for users who want to see where the max came from.
- Per-function-max loses range-of-difficulty information within a file. This is acceptable because range is not what hot-spot analysis uses; it uses "is there a problem here?"

**Why cyclomatic, not cognitive, for the cross-language default:**

- Cognitive complexity (via `complexipy`) is the theoretically better metric for readability. Research agrees.
- But `complexipy` is Python-only. Making the default Python-specific would break cross-language comparability for the headline hot-spot chart.
- Cyclomatic is what every language has via `lizard`. The headline chart must be comparable across a monorepo's Python + TypeScript + Go subdirectories.
- Cognitive complexity is NOT discarded. When a Python project runs `/project-metrics`, cognitive is in the JSON (`complexipy.*`) and in a per-language MD section. It is simply not the flagship composer.

**Why a 90-day churn window:**

- The theory research establishes that churn signals stabilize around 90 days; shorter is noisy, longer masks recent pathology.
- Configurable via `--window-days` so users can adjust for fast-moving or slow-moving projects. Non-default windows are flagged in `aggregate.window_days` so trend comparisons catch the mismatch (see schema ADR).

### Gaming analysis

| Vector | Collapse severity | Mitigation |
|---|---|---|
| Developer chases lower hot-spot score by extracting helpers from a hot file | Low — this is usually the correct response to a hot-spot flag; the "gaming" is a real improvement | None needed; feature, not bug |
| Micro-commits to dilute per-commit churn | None — churn is summed lines, not commits | — |
| Whitespace-only diffs inflating churn | Low — shows up as a localized spike, detectable by inspection | Optional future: `git log -w` for whitespace-agnostic churn; not in v1 scope |
| Generated files committed to history pollute the top-N | Medium — can drown real hot-spots | Documented in `docs/metrics/README.md`; users can add `.gitattributes linguist-generated=true` or filter post-hoc. v1 does not auto-detect generated files. |
| Extracting methods mechanically to lower per-file max CCN without solving the problem | Medium — max drops, score drops, but the underlying complexity moved not solved | Hot-spot is a symptom metric, not a verdict. MD language is "files that combine high churn and high complexity" not "files that are bad." This framing is explicit in `docs/metrics/README.md`. |

No metric survives a determined gaming effort; these defaults are resistant to accidental and casual gaming, which is the realistic threat model.

## Considered Options

### Option 1: `commit_count × mean_ccn` (CodeScene-classic variant)

**Pros:** Widely documented in the hot-spot literature.

**Cons:** Commit-count is gameable via micro-commits; mean_ccn is washed out by helpers. Two compounding weaknesses.

### Option 2: `churn_lines × mean_ccn`

**Pros:** Better than commit-count variant on effort signal.

**Cons:** Mean hides outliers; a file with one awful function and many clean ones scores low.

### Option 3: `churn_lines × max_ccn` (chosen)

**Pros:** Captures effort (churn_lines) and per-file worst case (max_ccn); cross-language via lizard; Top-N reader can see the contributing dimensions.

**Cons:** Single-function outlier can dominate a file's score even if the rest is clean — but that is the signal we want. The file with one 25-CCN function needs attention.

### Option 4: `churn_lines × cognitive_max` (cognitive complexity)

**Pros:** Cognitive is the better readability metric.

**Cons:** Python-only. Breaks the cross-language comparability of the flagship metric.

### Option 5: Multi-dimensional hot-spot (include test-coverage, ownership, age)

**Pros:** Richer signal.

**Cons:** Over-specified for v1; each added dimension introduces nullability and interpretation complexity. Keep the headline simple; the raw per-dimension data is in the JSON for anyone who wants to compose their own.

## Consequences

**Positive:**

- Hot-spot is a honest cross-language composite; the headline MD chart is comparable across polyglot monorepos.
- Top-N presentation surfaces all three numbers (churn, complexity, score) so readers can judge whether the ranking matches their intuition.
- `hotspot_gini` adds distribution shape cheaply; distinguishes concentrated from diffuse complexity debt.
- The fallback chain (lizard → scc branch-count → skipped) means hot-spots either ship with an honest source label or don't ship at all; no silent proxy.

**Negative:**

- Per-file max CCN is a strong signal but ignores within-file distribution; a reader who wants "most files in this folder are moderately complex" needs to read the `lizard` namespace directly.
- Cognitive complexity is relegated to per-language breakdown, which is suboptimal for pure-Python projects. The trade is cross-language comparability; accepted.
- Scc branch-count as a complexity fallback is documented as coarse, but users who rely on it for ranking may draw wrong conclusions from the ordering. Mitigated by the explicit `complexity_source: "scc_fallback"` marker in every JSON and MD line.
- Hot-spot score has no absolute scale — "50" means nothing without context. The Gini coefficient and Top-N ranking are the interpretable signals; the raw score is a ranking key. Documented in `docs/metrics/README.md`.
