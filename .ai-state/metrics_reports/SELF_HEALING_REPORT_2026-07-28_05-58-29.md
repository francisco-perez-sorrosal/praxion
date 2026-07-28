# Self-Healing Loop Metrics

- **Generated:** 2026-07-28T05:58:29.137586+00:00
- **Window:** last 90 days (since 2026-04-29T05:58:29.137586+00:00)
- **Commit:** `14b0c57`
- **Schema:** 1.0.0

## Fix success

| Metric | Value |
| --- | --- |
| CI autofix attempts (non-skipped) | 17 |
| — of which failed | 12 |
| CI autofix runs (total, incl. skips) | 200 |
| Issue autofix attempts (non-skipped) | 2 |
| Declines (`autofix:declined`) | 0 |
| Fix PRs opened (new-branch) | 1 |
| Fix PRs merged (new-branch) | 0 |
| Fix success rate (new-branch) | 0.00 |

- CI autofix by conclusion: {'success': 5, 'failure': 12, 'skipped': 170, 'cancelled': 13}
- _fix_prs_* = new-branch fixes (ci-autofix/, issue-autofix/) only; in-place P3a fixes (Autofix-Attempt trailer on the PR branch) are uncounted pending trailer-scan wiring._

## Cross-model gate

- Runs (total): **15** — by conclusion: {'success': 15}
- Verdict classification: _n/a_ — Verdict (request-changes vs approve vs unavailable) lives in the PR review comment, not the run conclusion; classification wiring is deferred to the recalibration pass once real gate comments exist to pattern-match. Baseline reports run counts only.

## Time-to-green

- Sample size: 0; median: _n/a_ h
- Proxy = mergedAt − createdAt of merged fix PRs; refine to first-failing-run → merge in the recalibration pass.

## Deferred / operator-supplied

- **Credit burn:** Cursor's credit pool is not GitHub-queryable; operator-supplied (brief §7 [U]).
- **Override rate:** Requires correlating gate request-changes verdicts with human merges; deferred with gate-verdict classification.
- **Cost per fix:** credit_burn / fix_prs_merged; null until credit burn is operator-supplied.

## Collection warnings

- Sources at the fetch limit (200) — counts are a floor, not exact: autofix_runs.
