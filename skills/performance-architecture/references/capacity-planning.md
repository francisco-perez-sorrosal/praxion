# Capacity Planning

Back-of-envelope estimation, Little's law, scaling decisions, and cost-performance optimization. Back to [SKILL.md](../SKILL.md).

## Back-of-Envelope Estimation

Rough calculations that get within an order of magnitude. Useful for system design, sizing infrastructure, and validating whether an architecture can meet requirements before building it.

### Reference Latencies

Memorize these orders of magnitude:

| Operation | Approximate Latency |
| --- | --- |
| L1 cache reference | 1 ns |
| L2 cache reference | 4 ns |
| Main memory reference | 100 ns |
| SSD random read | 16 us |
| HDD random read | 4 ms |
| Network round-trip (same datacenter) | 0.5 ms |
| Network round-trip (cross-continent) | 150 ms |
| Read 1 MB sequentially from SSD | 50 us |
| Read 1 MB sequentially from network (1 Gbps) | 10 ms |

### Estimation Method

1. **Identify the dominant operation** -- the one repeated most or with the highest per-unit cost
2. **Estimate per-unit cost** using reference latencies or measured data
3. **Multiply by volume** -- requests per second, records to process, data to transfer
4. **Add overhead** -- serialization, network hops, GC pauses. Rule of thumb: multiply by 2-3x for real-world overhead
5. **Compare against requirements** -- is the result within budget? If not, identify which factor to improve

### Example: Can This Database Handle the Load?

```
Target: 10,000 reads/sec, 1,000 writes/sec
Single SSD random read: ~16 us = ~62,500 reads/sec capacity
Single SSD random write: ~100 us = ~10,000 writes/sec capacity

Read headroom: 62,500 / 10,000 = 6.25x margin (comfortable)
Write headroom: 10,000 / 1,000 = 10x margin (comfortable)

With 2-3x overhead factor: still within capacity on a single node.
```

### Common Estimation Shortcuts

- **1 million requests/day** ~ 12 requests/second (peak: 2-3x average)
- **1 GB of data per day** ~ 12 KB/second sustained, ~40 KB/second peak
- **1 billion records at 1 KB each** = 1 TB storage
- **80/20 rule**: 80% of traffic hits 20% of data (size caches for the hot 20%)

## Little's Law

**L = lambda * W**

- **L** = average number of items in the system (in-flight requests, connections in use, jobs in queue)
- **lambda** = average arrival rate (requests/second)
- **W** = average time each item spends in the system (latency, processing time)

### Application to Software Systems

**Sizing connection pools**: If average request rate is 100 req/s and average database query time is 50ms, then `L = 100 * 0.05 = 5` connections are needed on average. Size the pool to handle peak load: if peak is 3x average, provision 15 connections.

**Queue depth estimation**: If a worker processes messages at 200/s and average processing time is 100ms, then `L = 200 * 0.1 = 20` messages are in-flight at any time. If the arrival rate temporarily exceeds 200/s, the queue grows.

**Thread pool sizing**: If the service handles 500 req/s with average latency of 200ms, then `L = 500 * 0.2 = 100` concurrent requests. The thread pool (or async concurrency limit) must accommodate at least 100 concurrent operations.

### Rearranging for Planning

- **What throughput can I sustain?** lambda = L / W (given pool size and latency)
- **What latency will users experience?** W = L / lambda (given pool size and arrival rate)
- **How many resources do I need?** L = lambda * W (given arrival rate and target latency)

## Throughput vs. Latency Trade-Offs

Throughput and latency are often in tension:

- **Batching** increases throughput but increases latency (items wait to fill the batch)
- **Larger thread pools** sustain higher throughput but increase contention and tail latency
- **Caching** improves throughput and latency on hits, but cache misses may be slower than no-cache
- **Compression** reduces network time (lower latency) but adds CPU time (higher CPU latency)

### Optimization Strategy

1. Optimize latency first for user-facing requests (p99 latency determines perceived performance)
2. Optimize throughput for background processing (cost-efficiency matters more than individual item speed)
3. When both matter, find the knee of the curve -- the point where adding more throughput starts significantly degrading latency

## Horizontal vs. Vertical Scaling

### Decision Framework

| Factor | Vertical (Scale Up) | Horizontal (Scale Out) |
| --- | --- | --- |
| **State management** | Simpler (single node) | Requires distributed state or stateless design |
| **Failure mode** | Single point of failure | Partial failure (more resilient) |
| **Cost curve** | Linear then exponential (hardware limits) | Linear (add commodity nodes) |
| **Latency** | Lower (no network hops between nodes) | Higher (coordination overhead) |
| **Maximum capacity** | Hardware ceiling | Theoretically unlimited |
| **Operational complexity** | Lower | Higher (orchestration, service discovery, load balancing) |
| **Time to implement** | Minutes (resize instance) | Days to weeks (architect for distribution) |

### When to Scale Vertically

- Application is stateful and state is expensive to distribute
- Workload is single-threaded or poorly parallelizable (high serial fraction)
- Current hardware is underutilized -- the cheapest optimization is using what you have
- Rapid response needed -- scaling up is faster than re-architecting

### When to Scale Horizontally

- Approaching hardware limits on a single node
- Availability requirements demand redundancy
- Workload is stateless or state is already distributed
- Growth trajectory will exceed single-node capacity within 6-12 months
- Cost of large instances exceeds cost of multiple smaller ones

### Hybrid Approach

Start vertical. Scale up until cost becomes non-linear or hardware ceiling approaches. Then architect for horizontal scaling. This avoids premature complexity while leaving room to grow.

## Cost-Performance Optimization

### Principles

- **Measure cost per unit of work** (cost per request, cost per GB processed, cost per user) -- not just total cost
- **Right-size instances** -- monitor utilization and downsize over-provisioned resources. A 50% utilized instance is paying double per unit of work
- **Use reserved/committed capacity** for baseline load, on-demand for peaks
- **Cache aggressively** where it reduces expensive operations (database queries, external API calls, compute-heavy transformations)
- **Prefer algorithms over hardware** -- a 10x algorithm improvement is cheaper and more sustainable than 10x more servers

### Cost Modeling

For capacity planning decisions, estimate:

```
Monthly cost = (baseline instances * reserved price) + (peak instances * on-demand price * peak hours/month)
Cost per request = monthly cost / monthly request volume
```

Compare architectures by cost per request at projected load levels. The cheapest architecture at 100 req/s may not be cheapest at 100,000 req/s.
