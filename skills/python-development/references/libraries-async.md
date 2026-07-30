# Essential Libraries: Async / Event-Driven Services

Part of the [Essential Libraries](essential-libraries.md) catalog.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Async runtime abstraction | **anyio** | Structured-concurrency abstraction over both `asyncio` and `trio`; lets libraries stay backend-agnostic | Simple scripts that only ever run on `asyncio` gain little from the abstraction layer |
| HTTP client (async) | **httpx** | First-class async support, sync/async parity — the consensus pick for new client code | — |
| HTTP client (async, alt) | **aiohttp** | Still a solid, mature, widely-deployed async HTTP client/server; useful when you also need an async web server without a full framework | `httpx` is generally preferred for new client-only code |
| Message queue / event streaming | **Kafka** (via `aiokafka`/`confluent-kafka`) or **NATS** (via `nats-py`) | Kafka for durable, high-throughput event-log semantics; NATS for lightweight, low-latency pub/sub | Don't reach for Kafka's operational complexity for a simple in-process pub/sub need — consider `asyncio.Queue` or Redis Streams first |
| Async task queue | **Taskiq** | Async-native, type-safe, integrates cleanly with async web frameworks, built-in scheduling | Established Celery-based teams with complex existing workflow investment |
