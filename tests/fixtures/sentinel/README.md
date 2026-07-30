# Sentinel Fixtures

Fixtures for sentinel-dimension checks. Each file is a golden bad-case the
named check MUST flag, paired per `rules/swe/gate-liveness.md`.

- `pre_refactor_plan_malformed_missing_loopback.md` — `PR01` (Pre-Refactor
  Plan Integrity): a `PRE_REFACTOR_PLAN.md` that is well-formed in every
  required section EXCEPT it omits `## Loop-Back Conditions`. The sentinel
  must FAIL on it.
- `p06_missing_task_brief/` — `P06` (TASK_BRIEF mandatory at Standard/Full):
  **README-only, no committed bad-case input.** The P06 input shape is a
  `.ai-work/<slug>/` directory, and `.ai-work/` is globally gitignored
  (`.gitignore:50`), so a committed fixture there would never reach CI. The
  CODE-kind canary `scripts/test_check_p06_task_brief.py` therefore builds the
  bad-case (`SYSTEMS_PLAN.md` present, no `TASK_BRIEF.md`) in `tmp_path` at
  runtime and asserts a `check="P06"`, `severity="warn"` row
  (`test_canary_p06_fires_on_known_bad_input`). See the directory's `README.md`.
- `challenge_no_disposition/` — `P07` (Undisposed Architecture Challenges):
  a minimal `INTERFACE_DESIGN.md` carrying a non-empty `## Architecture Challenges`
  section with no disposition paragraph ("Status:", "Decision:", or "Resolved:"). The
  sentinel must flag **Important** on it. Control: `INTERFACE_DESIGN_no_challenge.md`
  (no `## Architecture Challenges` section) — sentinel must NOT warn.
  PROMPT-kind gate — golden bad-case proof per `rules/swe/gate-liveness.md`.
- `consult_no_disposition/` — `P07`'s discipline-consultant extension: a minimal
  `CONSULT_statistician.md` carrying a non-empty `## Challenges` section whose `### CH-01`
  entry left `**Disposition:**` as the `<!-- convener, Round 2 -->` placeholder. The
  sentinel must flag **Important** on it. Control: `CONSULT_statistician_no_challenge.md`
  (no `## Challenges` section) — sentinel must NOT warn. PROMPT-kind gate — golden
  bad-case proof per `rules/swe/gate-liveness.md`.
- `stale_slug_advisory/` — `P08` (Stale `.ai-work/` slugs accumulating without cleanup):
  a synthetic `clean_work_safety.py --json` output (`clean_work_safety_stale.json`)
  with `summary.stale_safe = 3` (threshold for advisory). The sentinel must emit an
  advisory. Control: `clean_work_safety_clean.json` with `stale_safe = 0` — sentinel
  must NOT emit advisory. PROMPT-kind gate — golden bad-case proof per
  `rules/swe/gate-liveness.md`.
- `spec_archival_gap/` — `SH08` (Spec-archival gap): a fake `.ai-state/specs/`
  containing `SPEC_old-auth-feature_2025-01-01.md` (stale, 541 days before 2026-06-26)
  alongside a `.ai-state/decisions/` cluster of 3 ADRs dated 2026-05 to 2026-06 sharing
  the `auth` tag. The detector `check_spec_archival_gap.py` and sentinel SH08 must flag
  this as a gap. PROMPT+CODE gate — the pytest canary
  `test_canary_known_gap_fixture_flags_gap` feeds this directory and asserts `gap=True`.
