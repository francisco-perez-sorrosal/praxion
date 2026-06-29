# P06 gate-liveness — no committed fixture (by design)

`P06` (TASK_BRIEF mandatory at Standard/Full) flags any `.ai-work/<slug>/`
directory that contains `SYSTEMS_PLAN.md` but no `TASK_BRIEF.md`.

Unlike sibling CODE gates (`SH08`/`spec_archival_gap`, whose fixtures live under
the committable `.ai-state/` tree), the P06 bad-case input is inherently a
`.ai-work/<slug>/` structure — and `.ai-work/` is globally gitignored
(`.gitignore:50`). A committed fixture file under `.ai-work/` would never reach
a fresh checkout or CI, so the canary would pass locally but fail in CI.

The gate-liveness proof (dec-252) therefore **builds its known-bad input in
`tmp_path` at runtime** rather than reading a committed fixture. gitignore
affects only git, not filesystem reads, so `tmp_path` construction works
everywhere.

- Checker: `scripts/check_p06_task_brief.py` (`run_p06(repo_root)`)
- Canary: `scripts/test_check_p06_task_brief.py`
  (`test_canary_p06_fires_on_known_bad_input` builds
  `tmp_path/.ai-work/test-slug/SYSTEMS_PLAN.md` with no `TASK_BRIEF.md` and
  asserts a `check="P06"`, `severity="warn"` row).

This directory holds only this README — there is no committed bad-case input.
