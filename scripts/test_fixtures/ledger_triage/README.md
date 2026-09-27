# `ledger_triage` fixtures

Frozen ledger + ADR corpus snapshots for `scripts/test_ledger_snapshot.py` and
`scripts/test_ledger_health.py`. **Never** point a test at the live
`.ai-state/TECH_DEBT_LEDGER.md` — it moves on `main` in parallel with this
pipeline (see `LEARNINGS.md`).

## `base/` — frozen at commit `cac1ba2e`

`TECH_DEBT_LEDGER.md` and `TECH_DEBT_RESOLVED.md` are copied byte-for-byte via
`git show cac1ba2e:<path>` (header + the subset of rows below), **not** from
the working tree. `main` has since resolved td-185/264/276/170/223 in
parallel; a working-tree copy would silently break the `td-185`/`td-264`
ground truth.

**Active rows** (17): td-064, td-084, td-086, td-088, td-156, td-162, td-172,
td-173, td-185, td-186, td-211, td-213, td-257, td-260, td-264, td-270,
td-281.

**RESOLVED peers** (2): td-095 (`possible-duplicate` peer of td-270, same
base key: class=`coverage-gap`, location=`scripts/check_gate_liveness.py`,
direction=`code-to-goals`, goal-ref-type=`code-quality`), td-261 (present
for corpus realism; not a ground-truth peer).

**Ground truth** (`SYSTEMS_PLAN.md § Acceptance Criteria` AC-02/AC-03/AC-04):

- Candidates, `self-amended`: td-064, td-086, td-088, td-162, td-186,
  td-211, td-213.
- Candidate, `possible-duplicate` (peer td-095): td-270.
- Asserted miss (NOT a candidate — a correct premise, mechanically
  unreachable): td-156.
- Negative, no evidence at all: td-185 (links to 4 ADRs by file overlap
  only — dec-160/305/310/364 in this fixture's stub corpus — never
  evidence).
- Candidate, `decision-drift` (`cited-decision-changed`): td-084 (notes cite
  `dec-310`, which is `superseded_in_part_by: dec-375`), td-172 (notes cite
  `dec-364`, `superseded_in_part_by: dec-366`), td-173 (notes cite `dec-160`,
  `status: superseded`, `superseded_by: dec-374`).
- `key.status == "discriminated"`: td-257, td-264, td-270, td-281 (per the
  live ledger's `--backfill` history — unchanged here).

**ADR stubs** (`base/.ai-state/decisions/`, frontmatter only, reproducing
live statuses/edges as of `cac1ba2e`):

| File | id | status | edges |
|---|---|---|---|
| `160-overview-landing-surface.md` | dec-160 | superseded | `superseded_by: dec-374` |
| `305-project-local-discipline-registry-overlay.md` | dec-305 | accepted | — |
| `310-sealed-consult-prior.md` | dec-310 | accepted | `superseded_in_part_by: dec-375` |
| `364-sidecar-placement-axis.md` | dec-364 | accepted | `superseded_in_part_by: dec-366` |
| `366-sidecar-state-mount-worktree.md` | dec-366 | accepted | `supersedes_in_part: dec-364` |
| `375-seal-witness-none-tombstone-exemption.md` | dec-375 | accepted | `supersedes_in_part: dec-310` |
| `387-intentional-compaction-handoff.md` | dec-387 | accepted | — |
| `394-per-tier-pipeline-envelope.md` | dec-394 | accepted | `supersedes_in_part: dec-261`; `affected_files` includes `hooks/remind_calibration.py` — overlaps td-257/td-264/td-261's location, context-only (REQ-04) |

`dec-374`, `dec-261` are cited only as successor/superseded ids in the
stubs above — no file for them exists in this fixture, which is correct:
a notes citation to an id absent from the corpus is ignored, never flagged
(`SYSTEMS_PLAN.md § Data Structures` DS-1, `DecisionCitation`).

**Location paths must be stubbed as real files** in the `tmp_path` git repo
a test builds around this fixture — every `location` cell across both
ledger files and the ADR `affected_files` lists above — so that
`location-decay` never fires spuriously on a fixture-only path. Test
builders create these via `_touch_locations()` (see
`scripts/test_ledger_snapshot.py`).

## `td264_post_rebase/` — the post-rebase re-key case

A **second, separate** minimal ledger: td-264's row as it reads on `main`
after the parallel session's rebase (key re-minted `f41a094f3fd4` ->
`898240af0a2e` by `--backfill`, notes carrying a
`// [orchestrator, low-hanging batch 2026-09-27] Part fixed by 4b9e8462`
suffix appended after the row's prior state), alongside td-257 (its
possible-duplicate peer, unchanged). This is a real `notes-amended-in-place`
+ re-key case — distinct from the `base/` snapshot's td-264, and never
combined with it in the same parsed ledger (two rows sharing one id would
not be a legal ledger state).
