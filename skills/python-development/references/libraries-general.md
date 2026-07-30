# Essential Libraries: General-Purpose

Part of the [Essential Libraries](essential-libraries.md) catalog. Useful in nearly any
Python project regardless of archetype.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Testing | **pytest** | The unambiguous standard — see the skill's own [testing-and-tooling.md](testing-and-tooling.md) | — |
| Property-based testing | **Hypothesis** | Complements pytest for edge-case discovery on pure functions/parsers — see the [testing-strategy](../../testing-strategy/SKILL.md) skill for advanced usage | Overkill for simple CRUD glue code with no interesting invariants |
| Logging | **structlog** or **loguru** | structlog: processor-pipeline architecture, fast JSON serialization, best OpenTelemetry/OTLP integration story — favored for microservices/observability-heavy systems. loguru: best pure developer experience, simpler `bind()`-based context, less friction to adopt in a small project | loguru's OTLP path needs extra indirection through stdlib's `InterceptHandler` — pick structlog directly for OTel-heavy shops |
| Config management | **pydantic-settings** | Type-safe, validated settings from env vars/files/CLI with fail-fast startup validation; tight Pydantic v2 integration | Simple scripts with 1-2 env vars don't need the dependency — a plain `os.environ.get()` is fine |
| Config management (multi-environment) | **dynaconf** | Named alternative when layered multi-environment config (dev/staging/prod files + secrets) is the dominant need rather than typed validation per se | `pydantic-settings` covers most projects' needs; `dynaconf` adds value mainly for complex multi-source layering |
