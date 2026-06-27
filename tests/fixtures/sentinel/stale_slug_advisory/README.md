# Fixture: stale_slug_advisory

Golden bad-case fixture for sentinel gate **P08** (Stale `.ai-work/` slugs accumulating
without cleanup).

## What P08 checks

P08 runs `python3 scripts/clean_work_safety.py --json` and reads `summary.stale_safe`.
If `stale_safe >= 3`, it emits an advisory: "N stale safe task directories in `.ai-work/`
— consider running `/clean-work`." It skips with INFO when `.ai-work/` is absent or
`stale_safe < 3`.

`stale_safe` counts task directories that are classified `SAFE` (no blocking or warning
artifacts) and have `age_days >= 14` (idle at least two weeks). These are prime cleanup
candidates that the operator has not yet swept.

## Files in this fixture

| File | Role | `summary.stale_safe` | Expected P08 result |
|------|------|----------------------|---------------------|
| `clean_work_safety_stale.json` | **Golden bad-case** | 3 | P08 must emit advisory |
| `clean_work_safety_clean.json` | **No-false-positive control** | 0 | P08 must NOT emit advisory |

## Bad-case description

`clean_work_safety_stale.json` represents a project with three completed task directories
(`auth-flow`, `cache-layer`, `email-templates`), each classified SAFE with no blocking or
warning artifacts, and idle for 21–42 days. All three are stale. `summary.stale_safe = 3`
meets the P08 advisory threshold.

The JSON mirrors the exact schema emitted by `clean_work_safety.py --json` (see
`scripts/clean_work_safety.py` → `render_json`):
```
{
  "ai_work_root": ...,
  "task_dirs": [ { "slug", "classification", "reasons", "age_days" }, ... ],
  "summary": { "total", "block", "warn", "safe", "stale_safe" }
}
```

## Control description

`clean_work_safety_clean.json` represents a project whose `.ai-work/` is empty — no task
directories at all. `summary.stale_safe = 0` is below the advisory threshold, so P08 must
emit no advisory. This models both a freshly cleaned workspace and one where every slug is
active or recently used.

## Gate liveness

Per `rules/swe/gate-liveness.md` (PROMPT gates are proven by a documented golden bad-case,
not a pytest canary). This directory is that proof for P08. The no-false-positive control
here satisfies AC3.
