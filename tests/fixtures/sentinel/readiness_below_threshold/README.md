# Fixture: readiness_below_threshold

Golden bad-case fixture for sentinel dimension **RD** / check **RD01** (Readiness feedback check).

The detector `scripts/check_readiness_feedback.py` must flag this directory as
`below_threshold: true` when given `--repo-root` pointing here: the latest
`METRICS_REPORT_*.json` has `readiness.data.adjusted_level: 2`, which is below the
Practiced production floor of 3.

## Layout

```
.ai-state/
  metrics_reports/
    METRICS_REPORT_2026-01-02_00-00-00.json   ← golden bad-case (level 2, mechanical-only)
    METRICS_REPORT_2026-01-01_00-00-00.json   ← control snapshot (level 3)
```

The detector resolves the **lexicographically newest** file by filename sort. Both files are
present in this fixture; `METRICS_REPORT_2026-01-02_00-00-00.json` (bad case) sorts after
`METRICS_REPORT_2026-01-01_00-00-00.json` (control), so the detector picks the bad case when
given this fixture as repo root.

## Gap arithmetic

| Key | Value | Explanation |
|-----|-------|-------------|
| `adjusted_level` | 2 | Developing — below the Practiced floor |
| `READINESS_FLOOR` | 3 | Practiced — CI, tests, pre-commit, contributing guide, container, observability, type-checker, dep-scanning all in place |
| `note` | `"mechanical-only"` | LLM evaluation tier was skipped; the level is a floor that a full `/project-metrics --llm` run may raise |
| `below_threshold` | `true` | 2 < 3 → RD01 fires Important |
| `mechanical_only` | `true` | note == "mechanical-only" |

## No-false-positive control

The control file `METRICS_REPORT_2026-01-01_00-00-00.json` (adjusted_level: 3) is present to
show that a project at the Practiced floor or above produces `below_threshold: false`. It is
NOT the latest file in this fixture directory; it is exercised separately via `tmp_path` in the
pytest suite (`test_check_readiness_feedback.py::test_no_false_positive_at_floor_level_3`).

## Gate type

PROMPT gate — RD01 instructs sentinel to run
`python3 scripts/check_readiness_feedback.py --json` and flag **Important** when
`below_threshold: true`, annotating the finding when `mechanical_only: true`.

The CODE-level gate-liveness proof is the pytest canary
`test_check_readiness_feedback.py::test_canary_below_floor_level_2_bites`, which feeds a
known-bad fixture via `tmp_path` and asserts `--check` exits 1.
