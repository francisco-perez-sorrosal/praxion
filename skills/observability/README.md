# observability

Application observability strategy: what to observe, at which granularity, and with what tools. Covers the three pillars (logs, metrics, traces), RED/USE methodology, SLI/SLO/error budgets, OpenTelemetry instrumentation, cardinality management, and SLO-based alerting.

## When to Use

- Adding observability to a service (logging, metrics, or tracing)
- Choosing logging strategy (log levels, structured fields, correlation IDs)
- Designing metric types and Prometheus naming conventions
- Avoiding cardinality explosions from unbounded label values
- Instrumenting OpenTelemetry (Python or TypeScript)
- Defining SLIs, SLOs, and error budgets
- Designing alert rules (burn-rate alerting, runbooks, on-call practices)
- Reviewing observability coverage for a service or architecture
- Understanding eBPF, continuous profiling, or AI-assisted observability patterns

## Activation

Activates automatically when discussing monitoring, telemetry, OTel, spans, log levels, burn-rate alerting, Prometheus naming, Grafana dashboards, trace context propagation, metrics cardinality, runbooks, SLI/SLO/SLA, log aggregation, or trace analysis.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core strategy: three pillars, RED/USE/Four Golden Signals, SLI/SLO framework, instrumentation strategy, anti-patterns, emerging patterns |
| `references/structured-logging.md` | JSON logging best practices, field conventions, correlation patterns, Python library selection, OTel integration |
| `references/metrics-design.md` | Metric type selection, Prometheus naming conventions, cardinality management, RED/USE implementation |
| `references/distributed-tracing.md` | OTel SDK patterns (Python + TypeScript), span design, context propagation, Collector architecture, sampling strategies |
| `references/alerting-patterns.md` | SLO-based alerting, burn rate alerting, error budgets, runbook templates, on-call practices |
| `references/typescript-observability.md` | OTel instrumentation, structured logging, and metrics for TypeScript/Node.js applications |

## Related Skills

- [`performance-architecture`](../performance-architecture/) -- SLIs naturally bridge both skills; performance budgets define targets, observability validates them
- [`cicd`](../cicd/) -- DORA metrics for pipeline observability; application SLIs covered here
- [`hook-crafting`](../hook-crafting/) -- fire-and-forget hooks as an observability emission mechanism
- [`agentic-sdks`](../agentic-sdks/) -- OTel tracing patterns in AI agent architectures
- [`testing-strategy`](../testing-strategy/) -- testing observable behavior; observability validates test assumptions in production
