# performance-architecture

Performance architecture patterns and decisions for software systems. Covers performance as an architectural concern -- the patterns and decisions made during design and implementation, not operational monitoring.

## When to Use

- Designing systems with specific latency or throughput requirements
- Choosing caching strategies (cache-aside, write-through, write-behind, read-through)
- Sizing connection pools, thread pools, or worker pools
- Planning capacity for expected load and growth
- Setting up load testing or benchmarking methodology
- Analyzing performance bottlenecks (CPU, I/O, memory, contention)
- Reviewing systems for performance anti-patterns (N+1 queries, unbounded results, missing backpressure)
- Making scaling decisions (horizontal vs. vertical)

## Activation

The skill activates automatically when the agent detects performance architecture tasks: designing for performance, analyzing bottlenecks, choosing caching strategies, planning capacity, optimizing latency or throughput, setting up load testing, or reviewing systems for performance anti-patterns.

Trigger explicitly by mentioning "performance-architecture skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: performance thinking methodology, caching architecture, concurrency patterns, database and API performance, anti-patterns, verification checklist |
| `references/performance-patterns.md` | Detailed caching strategies, connection pooling, async patterns, batching, pagination optimization |
| `references/benchmarking.md` | Microbenchmark methodology, load testing patterns (ramp, spike, soak, breakpoint), profiling workflows, regression detection |
| `references/capacity-planning.md` | Back-of-envelope estimation, Little's law, scaling decision framework, cost-performance optimization |
| `README.md` | This file -- overview and usage guide |

## Quick Start

1. Define performance requirements (latency targets, throughput targets, resource constraints)
2. Identify the critical path -- the sequential chain determining end-to-end latency
3. Measure baseline performance before optimizing
4. Apply the appropriate technique to the measured bottleneck
5. Verify improvement and check for regressions

## Related Skills

- [`cicd`](../cicd/) -- performance regression detection in CI pipelines
- [`refactoring`](../refactoring/) -- restructuring code for better performance characteristics
- [`data-modeling`](../data-modeling/) -- schema design, indexing strategies, query patterns
- [`api-design`](../api-design/) -- pagination contracts, rate limiting, payload design
- `observability` (planned) -- monitoring, metrics, and alerting that validate performance decisions
