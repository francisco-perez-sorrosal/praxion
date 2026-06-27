# Sentinel Fixtures

Fixtures for sentinel-dimension checks. Each file is a golden bad-case the
named check MUST flag, paired per `rules/swe/gate-liveness.md`.

- `pre_refactor_plan_malformed_missing_loopback.md` — `PR01` (Pre-Refactor
  Plan Integrity): a `PRE_REFACTOR_PLAN.md` that is well-formed in every
  required section EXCEPT it omits `## Loop-Back Conditions`. The sentinel
  must FAIL on it.
- `p06_missing_task_brief/` — `P06` (TASK_BRIEF mandatory at Standard/Full):
  a pipeline slug directory containing `SYSTEMS_PLAN.md` but no `TASK_BRIEF.md`.
  The sentinel must WARN on it. PROMPT-kind gate — golden bad-case proof, not a
  deterministic canary. Wire to automated test once a mechanical P06 checker lands.
