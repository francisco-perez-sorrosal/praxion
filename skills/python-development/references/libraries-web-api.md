# Essential Libraries: Web API / Backend Service

Part of the [Essential Libraries](essential-libraries.md) catalog.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Framework | **FastAPI** | Dominant ecosystem, huge third-party plugin surface, best docs/DX for teams that value velocity; async-native | Extreme throughput/serialization-bound workloads where Pydantic's validation overhead dominates |
| Framework (perf-alternative) | **Litestar** | Uses `msgspec` instead of Pydantic for serialization — materially faster in benchmarks; more batteries-included (DI, caching, ORM plugin) with less "magic" than FastAPI | Smaller ecosystem/community; fewer third-party integration recipes; steeper unfamiliarity cost for teams standardized on FastAPI patterns |
| Framework (batteries-included) | **Django** (5.x, async-capable) | Still the default when you need an admin UI, batteries-included auth, and a mature ORM out of the box; async support across views/middleware/ORM has matured | Overkill for a pure JSON API microservice with no admin/templating needs |
| ORM | **SQLAlchemy 2.x** | The safe default for anything beyond trivial CRUD — native async engine/session, typed Core API, dialect-agnostic | Steeper learning curve than SQLModel for simple CRUD-only services |
| ORM (Pydantic-integrated) | **SQLModel** | Wraps SQLAlchemy + Pydantic so the same model is your DB table and your validator/serializer — less boilerplate for FastAPI-shaped CRUD apps | Drops to raw SQLAlchemy for exotic queries/dialect features; less mature than SQLAlchemy alone |
| Validation | **Pydantic v2** | De facto standard; Rust-core performance, tight FastAPI/SQLModel/pydantic-settings integration | Extremely hot-path serialization where `msgspec` (used by Litestar) measurably outperforms it |
| Background jobs | **Taskiq** or **Dramatiq** | Taskiq: async-first, type-safe, built-in scheduling, clean FastAPI integration. Dramatiq: simpler mental model, faster for straightforward sync workloads, better graceful-shutdown semantics | Celery remains the safer choice for teams with complex existing workflows/monitoring investment — don't migrate off Celery without a concrete pain point |
| HTTP client | **httpx** | Sync+async in one API, HTTP/2 support, `requests`-compatible surface — the consensus pick for any new code that might need async later | `requests` is still fine for trivial one-off sync scripts with zero async surface |
