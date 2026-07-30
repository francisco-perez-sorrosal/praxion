# Consult — statistician (multidisciplinary-identities)

**Discipline:** statistician  **Convened by:** systems-architect  **Model:** opus  **Round reached:** 1

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
- **Disposition:** <!-- convener, Round 2 -->
- **Rationale:** <!-- convener, Round 2 -->

## Not Challenged

The judge-agreement measurement methodology itself (rubric, scoring scale) is sound and
not in question.
