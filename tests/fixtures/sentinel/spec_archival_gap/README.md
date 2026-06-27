# Fixture: spec_archival_gap

Golden bad-case fixture for sentinel SH08 (Spec-archival gap check).

The detector `scripts/check_spec_archival_gap.py` must flag this directory
as a gap when given `--repo-root` pointing here: the newest `SPEC_*` is more
than 90 days older than a cluster of ≥3 finalized ADRs sharing a tag.

## Layout

```
.ai-state/
  specs/
    SPEC_old-auth-feature_2025-01-01.md   ← stale spec (2025-01-01)
  decisions/
    001-auth-session.md                    ← recent ADR, tag: auth (2026-05-01)
    002-auth-token.md                      ← recent ADR, tag: auth (2026-05-15)
    003-auth-middleware.md                 ← recent ADR, tag: auth (2026-06-01)
```

Gap arithmetic (now = 2026-06-26):
- Newest SPEC date: 2025-01-01
- Cluster of 3 ADRs tagged `auth`, all dated 2026-05-xx to 2026-06-xx
- Each ADR is 485–541 days newer than the SPEC → far exceeds N_DAYS=90 threshold

## No-false-positive control

A fresh-spec scenario (SPEC dated 2026-06-20, same ADR cluster) is exercised
via `tmp_path` in the test suite (`test_no_gap_when_spec_is_fresh`), not as
a fixture file, because the control's purpose is isolation of the date variable
rather than a file the sentinel checks by path.

## Gate type

PROMPT gate — SH08 instructs sentinel to run
`python3 scripts/check_spec_archival_gap.py --json` and flag when `gap: true`.
The pytest canary `test_canary_known_gap_fixture_flags_gap` feeds this directory
via the Python API (`detect_gap(repo_root=FIXTURE_DIR, now=...)`) and asserts
`gap is True`, constituting the CODE-level gate-liveness proof.
