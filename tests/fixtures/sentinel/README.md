# Sentinel Fixtures

Fixtures for sentinel-dimension checks. Each file is a golden bad-case the
named check MUST flag, paired per `rules/swe/gate-liveness.md`.

- `pre_refactor_plan_malformed_missing_loopback.md` — `PR01` (Pre-Refactor
  Plan Integrity): a `PRE_REFACTOR_PLAN.md` that is well-formed in every
  required section EXCEPT it omits `## Loop-Back Conditions`. The sentinel
  must FAIL on it.
