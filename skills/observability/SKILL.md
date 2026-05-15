---
name: observability
description: >
  Application observability strategy: structured logging, metrics design,
  distributed tracing, and alerting. Covers the three pillars, RED/USE
  methodologies, SLI/SLO/error budgets, OpenTelemetry instrumentation strategy,
  and cardinality management. Use when adding observability, choosing
  logging/metrics/tracing strategies, designing alert rules, defining SLIs/SLOs,
  instrumenting with OpenTelemetry, or reviewing observability coverage. Trigger
  keywords: monitoring, telemetry, OTel, spans, log levels, error budgets, burn
  rate alerting, Prometheus naming, Grafana dashboards, trace context
  propagation, metrics cardinality, runbooks, on-call, SLA, log aggregation,
  trace analysis.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
---

# Observability

Application observability strategy for instrumentation decisions: what to observe, at which granularity, with what tools.

**Content boundary:**
- **This skill** = observability *strategy knowledge* (what to observe, which methodology, how to instrument)
- **Rule** = none yet (extract later if always-on conventions emerge from usage)
- **Agent** = none needed (observability is advisory knowledge, not a delegated workflow)

**Satellite files** (loaded on-demand):

- [references/structured-logging.md](references/structured-logging.md) -- JSON logging, log levels, correlation IDs, Python library comparison
- [references/metrics-design.md](references/metrics-design.md) -- metric types, Prometheus naming, cardinality, RED/USE implementation
- [references/distributed-tracing.md](references/distributed-tracing.md) -- OTel SDK patterns (Python + TypeScript), span design, context propagation, Collector architecture
- [references/alerting-patterns.md](references/alerting-patterns.md) -- SLO-based alerting, burn rates, error budgets, runbook templates

Future language references (e.g., `references/typescript-observability.md`) added here without changes to this file's body.

## Gotchas

- **Cardinality explosion**: Unbounded label values in metrics (user IDs, email addresses, request paths) create millions of time series that overwhelm storage and query performance. Use route templates (`/api/users/{id}`), not actual paths. Put high-cardinality data in trace attributes or logs instead.
- **PII in structured logs**: Structured logging makes every field independently searchable -- accidental PII exposure is easier to create and harder to detect than in free-form text. Redact at the logger level, not downstream.
- **Trace sampling hides rare errors**: Head-based sampling decides at request start, before knowing if the request will fail. Rare error paths get dropped at the same rate as healthy traffic. Use tail-based sampling to retain errors and slow requests.
- **Alert fatigue from threshold alerts**: Static thresholds on infrastructure metrics generate noise during normal variance. Alert on user-facing symptoms (error rate, latency p99) instead of causes (CPU utilization). Monitor causes on dashboards, page on symptoms.
- **Cost explosion from verbose tracing**: Tracing every function call in production generates orders of magnitude more data than needed. Trace at service boundaries and business-critical operations. Use sampling in production; full tracing only in development and staging.

## Observability vs Monitoring

- **Monitoring** tells you when something is wrong -- predefined dashboards, threshold-based alerts on known failure modes
- **Observability** lets you ask arbitrary questions about system state, including questions you did not anticipate needing to ask

The three pillars -- logs, metrics, traces -- are complementary signals. Having all three does not guarantee observability; the ability to explore and correlate them does. Logs provide rich context for individual events, metrics provide aggregated trends for alerting, traces provide causal chains across service boundaries.

**Observability 2.0** (Charity Majors/Honeycomb) proposes arbitrarily-wide structured events as a single source of truth from which metrics, logs, and traces can all be derived. This is a valid aspiration gaining traction, but the three pillars model remains the practical industry default. Design for correlation across pillars today; adopt wide events as tooling matures.

## Methodology Selection

| Method | Scope | Signals | When to Use |
|--------|-------|---------|-------------|
| **RED** | Services | Rate, Errors, Duration | Every service endpoint -- APIs, gateways, microservices |
| **USE** | Resources | Utilization, Saturation, Errors | Infrastructure -- CPU, memory, disk, network |
| **Four Golden Signals** | Services | Latency, Traffic, Errors, Saturation | General service health (Google SRE) |

**Decision heuristic**: Apply RED to every service endpoint. Apply USE to every infrastructure resource. They are complementary, not competing.

### SLI/SLO/Error Budget Framework

- **SLI** (Service Level Indicator): A quantitative measure of service behavior from the user's perspective
- **SLO** (Service Level Objective): A target value for an SLI over a time window (e.g., 99.9% of requests under 200ms over 30 days)
- **Error budget**: The acceptable amount of unreliability (1 - SLO target) -- balances reliability investment against feature velocity
- **SLA** (Service Level Agreement): An SLO with business consequences (contractual)

| User Concern | SLI Type | Example Metric |
|-------------|----------|----------------|
| "Is it available?" | Availability | Successful requests / total requests |
| "Is it fast?" | Latency | p99 request duration < threshold |
| "Is it correct?" | Correctness | Correct responses / total responses |
| "Is it fresh?" | Freshness | Time since last successful data update |
| "Can I use it?" | Throughput | Sustained request rate at acceptable latency |

SLIs should measure what users experience, not internal system metrics. A healthy CPU with broken responses is not a healthy service.

## Instrumentation Strategy

| Approach | Effort | Coverage | Granularity |
|----------|--------|----------|-------------|
| Auto-instrumentation | Low | Framework/library level (HTTP, DB, queues) | Coarse |
| Manual instrumentation | High | Business logic, custom operations | Fine |
| **Hybrid (recommended)** | Medium | Both infrastructure and business paths | Full |

**Recommended approach**: Auto-instrumentation for baseline coverage (HTTP, database, message queues), manual instrumentation for business-critical paths (checkout, payment, auth). OpenTelemetry is the standard -- language-agnostic API, vendor-neutral, covers all three pillars.

Always set `service.name` and `service.version` as resource attributes on the OTel SDK. These are the minimum required for meaningful trace data.

## Anti-Patterns

| Anti-Pattern | Why It Hurts | Fix |
|-------------|-------------|-----|
| Log everything | Storage costs explode; signal drowns in noise | Log decisions and state changes, not routine operations |
| Log nothing | Blind during incidents; debugging requires reproduction | Instrument at service boundaries and error paths |
| Alert on causes | High noise from normal variance (CPU spikes, GC pauses) | Alert on symptoms (error rate, latency); dashboard causes |
| Use averages | Hides tail latency where real user pain lives | Use percentiles (p50, p95, p99) |
| Unbounded metric labels | Cardinality explosion, storage/query collapse | Bounded value sets only; high-cardinality data in traces |
| Instrument after deploy | Missing data when you need it most (first incident) | Instrument during development; observability is a feature |
| Dashboard without runbook | Engineer stares at graph without knowing what to do | Every alert links to a runbook with diagnostic and remediation steps |

## Emerging Patterns

- **eBPF**: Zero-instrumentation kernel-level monitoring (Pixie, Grafana Beyla). Captures system events (network, syscalls) with under 1% CPU overhead, but cannot observe application-level business logic.
- **Continuous profiling**: CPU/memory profiling as a fourth signal (Pyroscope, Parca). Answers "why is this slow?" at the function level. OTel is adding profiling support.
- **AI-assisted observability**: LLM-based log analysis and anomaly detection. Early stage -- promising for automated root cause suggestions, but requires domain-specific tuning.
- **OpenInference**: OTel extension for AI/LLM observability. Span kinds: CHAIN, AGENT, TOOL, LLM, RETRIEVER. Natively supported by Arize Phoenix.

## Related Skills

- **[Performance Architecture](../performance-architecture/SKILL.md)** -- SLIs naturally bridge both skills; performance budgets define targets, observability validates them
- **[CI/CD](../cicd/SKILL.md)** -- DORA metrics for pipeline observability; application metrics and SLIs covered here
- **[Hook Crafting](../hook-crafting/SKILL.md)** -- fire-and-forget hooks as an observability emission mechanism
- **[Agentic SDKs](../agentic-sdks/SKILL.md)** -- OTel tracing in AI agent architectures
- **[Testing Strategy](../testing-strategy/SKILL.md)** -- testing observable behavior; observability validates test assumptions in production
