---
name: performance-architecture
description: >
  Architectural patterns and decisions for performant software systems. Triggers:
  designing for performance, analyzing bottlenecks, choosing caching strategies,
  planning capacity, optimizing latency/throughput, setting up load testing,
  defining performance budgets, reviewing for performance anti-patterns;
  performance budgets, latency analysis, throughput, caching, connection
  pooling, async/concurrent patterns, database query optimization, load testing,
  benchmarking, capacity planning, scaling/scalability.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Performance Architecture

Architectural patterns and decisions for building performant software systems. Performance is a design concern -- address it during architecture, not after deployment.

**Satellite files** (loaded on-demand):

- [references/performance-patterns.md](references/performance-patterns.md) -- caching strategies, connection pooling, async patterns, batching, pagination optimization
- [references/benchmarking.md](references/benchmarking.md) -- microbenchmark methodology, load testing patterns, profiling workflows, regression detection
- [references/capacity-planning.md](references/capacity-planning.md) -- back-of-envelope estimation, Little's law, scaling decisions, cost-performance optimization

## Core Principles

**Measure Before Optimizing**: Never optimize without profiling data. Intuition about bottlenecks is wrong more often than right. Profile first, identify the hot path, then optimize the measured bottleneck. Premature optimization is not just wasteful -- it often makes code harder to optimize later.

**Performance Budgets**: Define quantitative limits before building. A performance budget is a contract: "This endpoint responds in under 200ms at p99 under expected load." Budget allocation forces architectural decisions early -- when they are cheap to change.

**Amdahl's Law**: The maximum speedup from parallelizing a system is bounded by its serial fraction. If 20% of work is serial, maximum speedup is 5x regardless of how many cores are added. Before parallelizing, measure the serial fraction. If it dominates, optimize the serial path instead.

**Critical Path First**: Identify the longest sequential chain of operations that determines end-to-end latency. Optimizing anything not on the critical path has zero impact on total latency. Map the critical path before investing in optimization.

**Right-Size the Solution**: Match the optimization technique to the scale of the problem. A single-server application does not need distributed caching. An internal tool serving 10 users does not need connection pooling. Over-engineering performance creates complexity without proportional benefit.

## Performance Thinking Methodology

### Step 1: Define Performance Requirements

Establish measurable targets before design begins:

- **Latency**: p50, p95, p99 response times for each endpoint or operation
- **Throughput**: requests per second, messages per second, or records per second the system must sustain
- **Resource constraints**: memory ceiling, CPU budget, cost budget, connection limits
- **Degradation behavior**: what happens under overload -- reject, queue, degrade gracefully?

### Step 2: Identify the Critical Path

Map the end-to-end request flow. For each operation on the path:

1. Classify as CPU-bound, I/O-bound, or waiting (lock contention, queue delay)
2. Measure or estimate duration
3. Identify which operations are sequential vs. parallelizable
4. Sum the sequential chain -- this is the theoretical latency floor

### Step 3: Measure Baseline

Establish current performance before making changes:

- Run benchmarks under realistic conditions (representative data, concurrent users, warm caches)
- Record p50, p95, p99 latency and throughput at target load
- Capture resource utilization (CPU, memory, I/O, network, connections)

### Step 4: Optimize the Bottleneck

Apply the appropriate technique to the measured bottleneck:

| Bottleneck Type | Techniques |
| --- | --- |
| **CPU-bound** | Algorithm optimization, caching computed results, parallelization (if serial fraction is low) |
| **I/O-bound** | Async I/O, batching, connection pooling, caching, read replicas |
| **Memory-bound** | Streaming instead of loading, pagination, object pooling, data structure optimization |
| **Contention** | Reduce lock scope, use lock-free structures, partition data, increase pool sizes |
| **Network** | Compression, request coalescing, edge caching, protocol optimization (HTTP/2, gRPC) |

### Step 5: Verify and Iterate

Re-measure after each change. Confirm the optimization improved the target metric without regressing others. Stop when performance requirements are met -- do not over-optimize.

## Caching Architecture

### When to Cache

Cache when data is read more often than written, expensive to compute or fetch, and tolerant of staleness within a defined window. Do not cache when data changes frequently, must always be fresh, or when cache hit rates would be low (< 80%).

### Strategy Selection Framework

| Strategy | Consistency | Write Performance | Read Performance | Complexity | Best For |
| --- | --- | --- | --- | --- | --- |
| **Cache-aside** | Eventual | Unchanged | High (on hit) | Low | General-purpose, read-heavy workloads |
| **Read-through** | Eventual | Unchanged | High (on hit) | Medium | Centralizing cache logic away from app code |
| **Write-through** | Strong | Lower (sync write) | High (on hit) | Medium | Consistency-critical, low write volume |
| **Write-behind** | Eventual | Higher (async write) | High (on hit) | High | Write-heavy workloads tolerant of data loss risk |

Default to **cache-aside** unless a specific requirement drives a different choice. Cache-aside is the simplest, most resilient pattern -- the system degrades gracefully on cache failure.

### Cache Invalidation

Cache invalidation is one of the hardest problems in computing. Choose a strategy:

- **TTL (time-to-live)**: Simplest. Set expiration based on acceptable staleness. Good default
- **Event-driven invalidation**: Publish invalidation events on data changes. Stronger consistency, higher complexity
- **Version-based**: Include a version key in cache entries. Increment version on changes, ignore stale versions

When in doubt, prefer short TTLs over complex invalidation logic. The consistency vs. complexity trade-off almost always favors simplicity.

### Multi-Tier Caching

Layer caches from fastest/smallest to slowest/largest:

1. **In-process** (application memory): sub-microsecond, limited by heap
2. **Distributed** (Redis, Memcached): sub-millisecond, shared across instances
3. **CDN/Edge**: closest to the user, for static or semi-static content

Each tier should have independent TTLs. Inner tiers use shorter TTLs to limit staleness amplification.

--> See [references/performance-patterns.md](references/performance-patterns.md) for detailed strategy descriptions, trade-offs, and sizing guidance.

## Concurrency and Async Patterns

### Connection Pooling

Reuse connections instead of creating new ones for every operation. Pool sizing rule of thumb:

```
pool_size = number_of_concurrent_operations * avg_operation_duration / avg_time_between_operations
```

Start conservative (connections = 2 * CPU cores for database pools), measure under load, and adjust. Oversized pools waste resources and can overwhelm downstream services. Set maximum wait time -- fail fast rather than queue indefinitely.

### Async I/O

Use async I/O when the workload is I/O-bound and the system needs high concurrency. Async does not help CPU-bound work -- it just adds overhead.

Patterns:
- **Fan-out/fan-in**: Issue multiple independent I/O operations concurrently, aggregate results
- **Pipeline**: Chain async stages where output of one feeds input of the next
- **Event-driven**: React to I/O completion events rather than polling

### Backpressure

When a producer generates work faster than a consumer can process it, the system must apply backpressure -- signaling the producer to slow down. Without backpressure, queues grow unbounded, memory exhausts, and the system crashes.

Implement backpressure through:
- Bounded queues with rejection on overflow
- Rate limiting at ingress points
- Flow control protocols (TCP backpressure, reactive streams)
- Load shedding -- intentionally dropping low-priority work under overload

### Batching

Combine multiple operations into a single round-trip. Effective for database inserts, API calls, message publishing, and cache operations. Batch size is a trade-off: larger batches amortize overhead but increase latency and memory.

--> See [references/performance-patterns.md](references/performance-patterns.md) for async pattern details, batching strategies, and pagination optimization.

## Database Performance

Focus on access patterns, not schema design (see the [data-modeling](../data-modeling/SKILL.md) skill for schema-level optimization).

### Query Optimization Principles

- **Minimize round-trips**: Fetch all needed data in one query rather than N+1 queries. Use JOINs, subqueries, or batch fetches
- **Index the access pattern**: Create indexes that match the WHERE, ORDER BY, and JOIN clauses of frequent queries. Every index speeds reads but slows writes
- **Limit result sets**: Always paginate. Never return unbounded results. Use LIMIT/OFFSET for simple cases, cursor-based pagination for large datasets
- **Explain before optimizing**: Use EXPLAIN/EXPLAIN ANALYZE to understand the query plan before adding indexes or rewriting queries

### N+1 Query Detection

The N+1 problem: fetching a list of N items, then issuing one query per item for related data. Detect by:
- Enabling query logging in development
- Counting queries per request (flag when count exceeds threshold)
- Using ORM-level detection tools

Fix with eager loading (JOIN or IN clause), batch fetching, or data loader patterns.

### Connection Management

- Use connection pooling (see above)
- Set idle connection timeouts to prevent stale connections
- Configure maximum connection limits per service -- prevent any single service from monopolizing the database
- Use read replicas for read-heavy workloads, routing writes to the primary

## API Performance

### Pagination Strategies

| Strategy | Pros | Cons | Best For |
| --- | --- | --- | --- |
| **Offset/limit** | Simple, supports random access | Inconsistent on data changes, slow at high offsets | Small datasets, admin UIs |
| **Cursor-based** | Consistent, performant at any depth | No random access, cursor management | Feeds, timelines, large datasets |
| **Keyset** | No cursor state, database-efficient | Requires sortable unique key | Time-series, log data |

Default to cursor-based pagination for APIs. Offset pagination degrades at scale -- scanning and discarding rows is O(offset).

### Request Coalescing

When multiple clients request the same data simultaneously, serve a single backend request and fan out the response. Effective for cache misses on popular keys. Implement with singleflight/request deduplication patterns.

### Compression

Compress API responses (gzip, brotli, zstd). Most frameworks support transparent compression. The CPU cost is almost always worth the bandwidth savings, especially for JSON payloads.

### Rate Limiting as Architecture

Rate limiting is not just protection -- it is a performance architecture tool. Use it to:
- Prevent individual clients from monopolizing shared resources
- Shape traffic to match downstream capacity
- Provide predictable degradation under load

## Anti-Patterns

| Anti-Pattern | Why It Hurts | Fix |
| --- | --- | --- |
| **Optimizing without profiling** | Wastes effort on non-bottlenecks | Profile first, then optimize the measured hot path |
| **Unbounded queries** | Memory exhaustion, timeout cascading | Always paginate, set result limits |
| **Cache everything** | Low hit rates waste memory, stale data causes bugs | Cache only high-read, low-write, staleness-tolerant data |
| **Synchronous calls in series** | Latency = sum of all calls | Parallelize independent calls, use async I/O |
| **Ignoring tail latency** | p50 looks fine, p99 is 10x worse | Measure and optimize p95/p99, not averages |
| **Oversized connection pools** | Overwhelms downstream, wastes resources | Size pools to match actual concurrency |
| **Missing backpressure** | Unbounded queues exhaust memory | Bound queues, reject or shed load on overflow |
| **Premature distributed caching** | Complexity without proportional benefit | Start with in-process caching, add distributed when needed |
| **N+1 queries** | Database round-trips dominate latency | Eager load, batch fetch, use data loaders |

## Integration with Other Skills

- **[Data Modeling](../data-modeling/SKILL.md)** -- schema design, indexing strategies, query patterns at the data layer
- **[API Design](../api-design/SKILL.md)** -- pagination contracts, rate limiting policies, payload design
- **[Observability](../observability/SKILL.md)** -- monitoring validates performance decisions; metrics, traces, and alerts
- **[CI/CD](../cicd/SKILL.md)** -- performance regression detection in CI pipelines

## Verification Checklist

Before considering performance work complete:

- [ ] Performance requirements defined with measurable targets (latency, throughput, resource limits)
- [ ] Critical path identified and measured
- [ ] Baseline established before optimization
- [ ] Each optimization addresses a measured bottleneck (not intuition)
- [ ] Cache strategy selected with explicit consistency and invalidation approach
- [ ] Connection pools sized based on measured concurrency
- [ ] No unbounded queries or result sets
- [ ] Backpressure mechanism in place for async pipelines
- [ ] N+1 queries eliminated or mitigated
- [ ] Performance verified under realistic load conditions
- [ ] No regressions in non-target metrics
