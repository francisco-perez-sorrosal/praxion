# Performance Patterns

Detailed patterns for caching, connection pooling, async I/O, batching, and pagination. Back to [SKILL.md](../SKILL.md).

## Caching Strategies

### Cache-Aside (Lazy Loading)

The application manages the cache directly. On read, check the cache first. On miss, fetch from the data source, store in cache, return. On write, update the data source, then invalidate or update the cache.

```text
Read path:  App --> Cache (hit?) --> yes: return
                                 --> no: App --> DB --> App --> Cache (store) --> return
Write path: App --> DB (update) --> Cache (invalidate)
```

**Trade-offs**: Simple to implement. Resilient to cache failures (falls back to data source). First request after miss is slow. Risk of stale data between write and invalidation.

**Sizing**: Start with items that have the highest read-to-write ratio. Monitor hit rate -- below 80% indicates poor cache candidate selection or insufficient TTL.

### Read-Through

The cache itself fetches from the data source on miss. The application only interacts with the cache, never directly with the data source for reads.

```text
Read path:  App --> Cache (hit?) --> yes: return
                                 --> no: Cache --> DB --> Cache (store) --> return
```

**Trade-offs**: Centralizes cache population logic. Application code is simpler. Cache becomes a critical dependency -- failure means no reads. Requires cache infrastructure that supports loader callbacks.

### Write-Through

Writes go to the cache first, which synchronously writes to the data source before acknowledging. Guarantees cache and data source are consistent.

```text
Write path: App --> Cache (store) --> DB (sync write) --> return
```

**Trade-offs**: Strong consistency. Higher write latency (two synchronous writes). Pair with read-through for a fully cache-mediated architecture. Suitable for low-write, consistency-critical workloads.

### Write-Behind (Write-Back)

Writes go to the cache, which asynchronously flushes to the data source. The application receives acknowledgment after the cache write, before the data source write completes.

```text
Write path: App --> Cache (store) --> return
            Background: Cache --> DB (async flush)
```

**Trade-offs**: Fastest write performance. Risk of data loss if cache fails before flush. Complex failure handling. Use only when write throughput is critical and temporary data loss is acceptable. Implement with write-ahead logs or persistent queues to reduce loss risk.

### Cache Sizing Guidelines

- **In-process cache**: 5-20% of heap. Use LRU or LFU eviction. Monitor eviction rate -- high eviction means the cache is too small or TTL is too long
- **Distributed cache**: Size based on working set (frequently accessed items), not total dataset. Start at 2x working set to absorb bursts
- **TTL selection**: Match to business-acceptable staleness. 1-5 minutes for frequently changing data, 1-24 hours for reference data, days/weeks for static content

## Connection Pooling

### Pool Lifecycle

```text
Initialize (min connections) --> Acquire (from pool or create) --> Use --> Release (return to pool) --> Idle timeout --> Close
```

### Sizing Guidelines

**Database connections**: Start with `pool_size = 2 * cpu_cores + disk_spindles` (for traditional databases). Cloud databases may have different constraints -- check provider limits. More connections does not mean more throughput past a saturation point.

**HTTP client connections**: Match to the number of concurrent outbound requests. Set per-host limits to prevent overwhelming a single upstream service.

**Health checks**: Validate connections before use (test-on-borrow) or periodically (background validation). Stale connections cause intermittent failures that are hard to diagnose.

### Pool Configuration Checklist

- Minimum pool size (pre-warmed connections)
- Maximum pool size (hard ceiling)
- Maximum wait time for connection acquisition (fail fast > queue forever)
- Idle connection timeout (reclaim unused connections)
- Maximum connection lifetime (prevent long-lived connection issues)
- Validation query or health check mechanism

## Async Patterns

### Fan-Out/Fan-In

Issue multiple independent operations concurrently, then wait for all (or a subset) to complete.

```text
Request --> [Op A, Op B, Op C] (concurrent) --> Aggregate --> Response
```

Use when: multiple independent data sources, independent computations, or independent I/O operations contribute to a single response.

Guard with: overall timeout (do not wait forever for the slowest), partial result fallback (return what succeeded if some fail), concurrency limits (do not fan out to 1000 operations simultaneously).

### Worker Pool

A fixed number of workers process items from a shared queue. Controls concurrency and prevents resource exhaustion.

```text
Queue --> [Worker 1, Worker 2, ..., Worker N] --> Results
```

**Sizing**: Start with CPU cores for CPU-bound work, higher for I/O-bound work (2-4x cores). Measure throughput vs. pool size and find the knee of the curve -- adding workers past this point adds overhead without throughput gains.

### Pipeline (Staged Processing)

Chain stages where each stage processes and forwards to the next. Each stage can have its own concurrency and buffering.

```text
Stage 1 (parse) --> Buffer --> Stage 2 (transform) --> Buffer --> Stage 3 (write)
```

Use when: processing has distinct phases with different resource profiles. Size each stage's concurrency independently based on its bottleneck type.

## Batching and Bulk Operations

### When to Batch

Batch when the per-operation overhead (network round-trip, transaction setup, API call overhead) dominates the actual work. Batching amortizes this fixed cost across N items.

### Batch Size Trade-offs

| Factor | Smaller Batches | Larger Batches |
| --- | --- | --- |
| Latency per item | Higher (more overhead per item) | Lower (overhead amortized) |
| Time to first result | Faster | Slower |
| Memory usage | Lower | Higher |
| Error blast radius | Smaller (fewer items affected) | Larger |
| Recovery granularity | Finer | Coarser |

Start with batches of 100-1000 items, measure throughput, and adjust. The optimal size depends on the specific overhead being amortized.

### Data Loader Pattern

Collect individual requests within an execution frame (event loop tick, request lifecycle), then issue a single batched request. Solves N+1 problems at the application level without restructuring query logic.

```text
Tick 1: collect [request A, request B, request C]
Tick 2: batch fetch [A, B, C] --> distribute results
```

## Pagination Optimization

### Offset/Limit

```sql
SELECT * FROM items ORDER BY id LIMIT 20 OFFSET 100
```

The database scans and discards `OFFSET` rows. At offset 1,000,000, performance is poor regardless of indexes. Acceptable for small datasets or when users rarely paginate deeply.

### Cursor-Based

```sql
SELECT * FROM items WHERE id > :last_seen_id ORDER BY id LIMIT 20
```

Constant performance at any depth. The cursor (last seen ID) acts as a bookmark. Requires a stable, unique sort key. Clients pass the cursor from the previous response.

### Keyset Pagination

```sql
SELECT * FROM items WHERE (created_at, id) > (:last_ts, :last_id) ORDER BY created_at, id LIMIT 20
```

Extension of cursor-based for composite sort keys. Efficient with a composite index on `(created_at, id)`. Use for time-series data, event logs, and audit trails.

### Choosing a Strategy

- **< 10,000 items total**: Offset is fine
- **10,000 - 1,000,000 items**: Cursor-based
- **> 1,000,000 items or time-series**: Keyset with composite index
- **Need random page access**: Offset (accept the trade-off) or pre-computed page boundaries
