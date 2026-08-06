# Consult — evidence-appraiser (caching-benchmark-claim)

**Discipline:** evidence-appraiser  **Convened by:** systems-architect  **Model:** opus  **Round reached:** 1
**Round-0 HEAD:** 4c1f9ab7e2d05836aa1b7fe30c9d4471e6b82f5c

## Independent Reading

The draft imports a vendor benchmark reporting a 3.4× throughput improvement and treats it
as transferable to this project's workload without restating the conditions under which the
number was produced.

## Sources Read

- `docs/caching-evidence.md` § Imported Benchmarks
- `SYSTEMS_PLAN.md` § Performance Targets

## Challenges

### CH-01 — The 3.4× figure is a vendor self-report with no independent replication

- **Decision it would change:** Whether the performance target is set from the vendor number
  or from a locally measured baseline.
- **Test that would settle it:** Locate a third-party reproduction, or run the vendor's own
  published harness against this project's workload shape and compare.
- **Confidence:** high — vendor marketing material is a distinct evidentiary class and the
  draft cites it with the same weight as a peer-reviewed result.

### CH-02 — The benchmark's workload does not resemble this project's

- **Decision it would change:** Whether the number transfers at all, and therefore whether
  the target is achievable rather than merely aspirational.
- **Test that would settle it:** Compare the benchmark's request-size distribution and
  cache-hit ratio against this project's production traces.
- **Confidence:** med — the vendor publishes enough workload detail to judge transfer, and
  what it publishes does not match.

## Not Challenged

The measurement methodology *within* the vendor's harness is sound; the objection is to
transfer and to provenance, not to instrumentation.

## Disposition Summary

| Challenge | Disposition | Rationale |
|---|---|---|
| CH-01 | <!-- convener --> | <!-- convener --> |
| CH-02 | <!-- convener --> | <!-- convener --> |
