# Consult — statistician (caching-benchmark-claim)

**Discipline:** statistician  **Convened by:** systems-architect  **Model:** opus  **Round reached:** 2
**Round-0 HEAD:** 4c1f9ab7e2d05836aa1b7fe30c9d4471e6b82f5c

## Independent Reading

The claim under review reports a 12% reduction in mean judge-disagreement rate between
two prompt-caching configurations, based on five paired evaluation runs, and treats the
difference as a stable improvement worth adopting project-wide.

## Sources Read

- `docs/multidisciplinary-identities-evidence.md` §14
- `SYSTEMS_PLAN.md` § Acceptance Criteria

## Challenges

### CH-01 — The 12% delta has no reported confidence interval or run-to-run variance

- **Decision it would change:** Whether the caching configuration is adopted project-wide
  versus held pending a properly powered comparison.
- **Test that would settle it:** Re-run both configurations at least 10 times each and
  report a bootstrap 95% confidence interval on the mean delta; adopt only if the
  interval excludes zero.
- **Confidence:** high — five paired runs is below the sample size a mean-difference
  claim of this magnitude needs to distinguish signal from evaluation noise.
- **Disposition:** switch-now
- **Rationale:** Accepted. The adoption claim is withdrawn from the plan and restated as a
  provisional reading pending the 10-run comparison; the acceptance criterion now names the
  interval rather than the point estimate.

### CH-02 — Five paired runs cannot distinguish a configuration effect from run ordering

- **Decision it would change:** Whether the comparison design needs randomised ordering
  before any number from it is quotable.
- **Test that would settle it:** Re-run with configuration order randomised per pair and
  check whether the delta survives.
- **Confidence:** med — ordering effects are plausible here but not demonstrated, and the
  harness does not currently record run order.
- **Disposition:** defer-with-rationale
- **Rationale:** Deferred to the measurement pass that implements CH-01's 10-run design,
  where randomised ordering is nearly free. Residual risk recorded as a tech-debt row rather
  than left in this fragment; deferring is not dismissing.

## Not Challenged

The judge-agreement measurement methodology itself (rubric, scoring scale) is sound and
not in question.
