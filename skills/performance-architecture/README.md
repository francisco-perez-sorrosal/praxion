# performance-architecture

Architectural patterns and decisions for building performant software systems. Performance is a design concern addressed during architecture, not after deployment — covering performance budgets, caching strategies, concurrency patterns, database access optimization, API pagination, and capacity planning.

## When to Use

- Designing systems with specific latency or throughput requirements
- Choosing caching strategies (cache-aside, write-through, write-behind, read-through)
- Sizing connection pools, thread pools, or worker pools
- Planning capacity for expected load and growth
- Setting up load testing or benchmarking methodology
- Analyzing performance bottlenecks (CPU-bound, I/O-bound, memory-bound, contention)
- Reviewing systems for performance anti-patterns (N+1 queries, unbounded results, missing backpressure)
- Making scaling decisions (horizontal vs. vertical, caching tier selection)

## Activation

Activates automatically when discussing performance budgets, latency analysis, throughput, caching, connection pooling, async/concurrent patterns, database query optimization, load testing, benchmarking, capacity planning, or scalability.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: performance thinking steps, caching architecture, concurrency and async patterns, database performance, API pagination, anti-patterns, verification checklist |
| `references/performance-patterns.md` | Detailed caching strategies, connection pooling, async I/O, batching, pagination optimization |
| `references/benchmarking.md` | Microbenchmark methodology, load testing patterns (ramp, spike, soak, breakpoint), profiling workflows, regression detection |
| `references/capacity-planning.md` | Back-of-envelope estimation, Little's law, scaling decision framework, cost-performance optimization |

## Quick Start

1. Define performance requirements (latency targets, throughput targets, resource constraints)
2. Identify the critical path — the sequential chain determining end-to-end latency
3. Measure baseline performance before optimizing
4. Apply the appropriate technique to the measured bottleneck
5. Verify improvement and check for regressions

## Related Skills

- [`observability`](../observability/) -- metrics, traces, and alerts that validate performance decisions
- [`cicd`](../cicd/) -- performance regression detection in CI pipelines
- [`data-modeling`](../data-modeling/) -- schema design, indexing strategies, query patterns
- [`api-design`](../api-design/) -- pagination contracts, rate limiting policies, payload design
