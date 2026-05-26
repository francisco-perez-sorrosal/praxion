# Benchmarking and Profiling

Methodology for microbenchmarks, load testing, profiling, and performance regression detection. Back to [SKILL.md](../SKILL.md).

## Microbenchmark Methodology

Microbenchmarks measure the performance of isolated code paths. Done poorly, they produce misleading results. Follow these rules:

### Warm-Up

Runtimes with JIT compilation (JVM, V8, .NET CLR) optimize code paths after repeated execution. Always run warm-up iterations before measurement iterations. The warm-up phase allows:

- JIT compilation and optimization of hot paths
- Cache population (CPU caches, OS page cache)
- Memory allocation stabilization (GC settling)

Verify warm-up sufficiency: plot iteration times -- measurements should plateau. If they keep changing, extend warm-up.

### Statistical Rigor

A single benchmark run is meaningless. Measure across multiple iterations and runs:

- **Minimum iterations**: 30+ measurement iterations per benchmark (more for high-variance operations)
- **Multiple runs**: Execute the full benchmark suite 3-5 times on separate JVM/process invocations
- **Report percentiles**: p50, p95, p99 -- not just mean. Mean hides tail latency
- **Confidence intervals**: Report results as `mean +/- margin of error` at 95% confidence. Results overlapping within confidence intervals are not statistically different
- **Coefficient of variation (CV)**: If CV > 5%, results are unstable -- investigate sources of variance before drawing conclusions

### Isolation

- Disable CPU frequency scaling (turbo boost, power saving) during benchmarks
- Close competing processes
- Pin to specific CPU cores to avoid NUMA effects on multi-socket systems
- Use consistent heap sizes and GC settings across comparisons
- Benchmark with representative data sizes -- performance often varies non-linearly with input size

### Common Pitfalls

| Pitfall | Why It Misleads | Mitigation |
| --- | --- | --- |
| Dead code elimination | Compiler removes unused computation, showing 0ns | Use the result (return it, write to volatile, use a blackhole) |
| Constant folding | Compiler pre-computes constant expressions | Use runtime-generated inputs |
| Loop hoisting | Compiler moves invariant code outside the loop | Vary inputs per iteration |
| Measuring startup cost | Cold-start included in measurement | Separate warm-up and measurement phases |
| GC pauses in measurement | Sporadic GC inflates individual iterations | Report percentiles, run with fixed heap, force GC between runs |

## Load Testing Patterns

### Ramp Test

Gradually increase load from zero to target. Identify the throughput ceiling and the load level where latency degrades.

```text
Load: 0 --> 100 --> 200 --> ... --> target RPS
Duration: 2-5 minutes per step
Measure: latency percentiles, error rate, resource utilization at each step
```

Use to find the system's sustainable throughput and identify the saturation point.

### Spike Test

Instantly jump to a high load level. Validates the system's behavior under sudden traffic surges.

```text
Load: baseline --> 5-10x baseline (instant) --> hold 5-10 min --> baseline
Measure: error rate during spike, recovery time after spike, queue depth
```

Use to verify autoscaling response time, circuit breaker behavior, and graceful degradation.

### Soak Test (Endurance)

Run at sustained moderate load for an extended period (hours to days). Detect memory leaks, connection exhaustion, log file growth, and gradual degradation.

```text
Load: 60-80% of max sustainable throughput
Duration: 4-24 hours
Measure: memory trend, latency drift, error rate trend, resource utilization slope
```

Use before major releases. A system that passes a 10-minute test may fail at hour 8 due to resource leaks.

### Breakpoint Test

Increase load until the system fails. Identify the breaking point and the failure mode.

```text
Load: increment by 10% every 5 minutes until failure
Measure: the load level at first error, at p99 > SLA, at complete failure
```

Use to establish safety margins and inform capacity planning.

### Load Test Checklist

- [ ] Test data is representative (size, distribution, cardinality)
- [ ] Test environment matches production (or differences are documented and accounted for)
- [ ] Warm-up phase before measurement (populate caches, establish connections)
- [ ] Monitor both client-side and server-side metrics
- [ ] Record system resource utilization alongside application metrics
- [ ] Test from multiple geographic locations if latency requirements are global

## Profiling Workflows

### CPU Profiling

Identify functions consuming the most CPU time.

1. Run the application under representative load
2. Capture a CPU profile (sampling profiler preferred over instrumentation -- lower overhead)
3. Examine the flame graph -- wide bars indicate functions consuming significant CPU
4. Focus on the widest bars at the top of the call stack (leaf functions doing the actual work)
5. Distinguish between self time (time in the function itself) and total time (including callees)

### Memory Profiling

Identify allocation hotspots and memory leaks.

1. Capture heap snapshots at intervals under load
2. Compare snapshots -- growing object counts indicate leaks
3. Identify allocation-heavy code paths (high allocation rate causes GC pressure even without leaks)
4. Look for retained objects that should have been collected (common: event listeners, caches without size limits, closures capturing large scopes)

### I/O Profiling

Identify slow I/O operations and contention.

1. Trace database queries (log query text, duration, row count)
2. Trace HTTP client calls (URL, duration, response size)
3. Monitor file I/O (read/write throughput, IOPS)
4. Check for synchronous I/O on async threads (blocks the event loop)

### Flame Graph Interpretation

```text
Wide bar at top    = function using significant CPU directly
Wide bar at bottom = function called by many paths (framework overhead)
Narrow tall tower  = deep call stack, possibly recursion
Plateau            = single function dominating execution
```

Read flame graphs top-down to find the actual work, bottom-up to find which callers contribute most to a hot function.

## Performance Regression Detection

### Establishing Baselines

Record performance metrics for the current state before changes:

- Key operation latencies (p50, p95, p99)
- Throughput at standard load
- Resource utilization under standard load
- Benchmark suite results

Store baselines in version control or a metrics store with commit SHA for traceability.

### CI Integration

Run performance benchmarks in CI pipelines on every merge to main (or on a schedule if benchmarks are expensive):

1. Execute the benchmark suite with fixed configuration
2. Compare results against the stored baseline
3. Flag regressions exceeding the threshold (e.g., > 5% latency increase, > 10% throughput decrease)
4. Require human review for flagged regressions -- do not auto-block (benchmarks in CI have higher variance than dedicated environments)

### Alerting Thresholds

| Metric | Warning | Critical |
| --- | --- | --- |
| p50 latency | > 10% above baseline | > 25% above baseline |
| p99 latency | > 15% above baseline | > 50% above baseline |
| Throughput | > 5% below baseline | > 15% below baseline |
| Error rate | > 0.1% | > 1% |

Adjust thresholds based on the system's SLA and acceptable variance. Tighter thresholds for user-facing critical paths, looser for background jobs.
