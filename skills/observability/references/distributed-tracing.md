# Distributed Tracing

OTel SDK patterns, span design, context propagation, Collector architecture, and sampling strategies for Python and TypeScript. Reference material for the [Observability](../SKILL.md) skill.

## Core Concepts

A **trace** represents the end-to-end journey of a single request through a distributed system. Each trace is a directed acyclic graph of **spans**.

A **span** is a single named operation within a trace. Every span has:

- A name describing the operation
- Start and end timestamps
- A set of key-value attributes
- A parent span (except for the root span)
- An optional status (OK, ERROR, UNSET)
- Zero or more events (timestamped annotations)

Spans form a tree via parent-child relationships. The root span represents the outermost operation (e.g., an HTTP request handler). Child spans represent sub-operations (database queries, downstream calls, business logic).

**Context** is the carrier that links spans across threads, processes, and services. It holds the current trace ID and span ID, enabling newly created spans to become children of the active span.

## OTel Architecture Overview

The OpenTelemetry tracing pipeline follows a layered design:

```
TracerProvider --> Tracer --> Span
                              |
                    SpanProcessor (batch)
                              |
                        SpanExporter
                              |
                    Backend (OTLP, Jaeger, Zipkin)
```

- **TracerProvider**: Creates and configures Tracers. One per application, set globally.
- **Tracer**: Creates Spans. Obtained from TracerProvider with a name (typically the instrumentation library or module name) and version.
- **SpanProcessor**: Receives finished spans and forwards them to exporters. `BatchSpanProcessor` batches spans and exports asynchronously (recommended for production). `SimpleSpanProcessor` exports synchronously (useful for testing).
- **SpanExporter**: Sends span data to a backend. Common exporters: `OTLPSpanExporter` (OTLP/HTTP or gRPC), `JaegerExporter`, `ZipkinExporter`, `ConsoleSpanExporter` (debugging).
- **Resource**: Metadata about the entity producing telemetry (`service.name`, `service.version`, `deployment.environment`).

## Python SDK Patterns

### TracerProvider Initialization

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "my-service",
    "service.version": "1.2.0",
    "deployment.environment": "production",
})

provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("my-service", "1.2.0")
```

### Span Creation

**Context manager** (preferred -- automatic start/end, exception recording):

```python
with tracer.start_as_current_span("process_order") as span:
    span.set_attribute("order.id", order_id)
    span.set_attribute("order.item_count", len(items))
    result = process(items)
    span.set_attribute("order.total", result.total)
```

**Decorator** (convenient for wrapping entire functions):

```python
@tracer.start_as_current_span("validate_input")
def validate_input(data: dict) -> bool:
    # Span is automatically the current span inside this function
    current_span = trace.get_current_span()
    current_span.set_attribute("input.field_count", len(data))
    return all(required in data for required in REQUIRED_FIELDS)
```

### Recording Exceptions

```python
with tracer.start_as_current_span("risky_operation") as span:
    try:
        result = call_external_service()
    except TimeoutError as exc:
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
        span.record_exception(exc)
        raise
```

### Nested Spans

Nested spans create parent-child relationships automatically through context. No explicit parent passing is needed:

```python
with tracer.start_as_current_span("handle_request") as parent:
    # This span becomes a child of "handle_request"
    with tracer.start_as_current_span("validate") as child:
        validate(request)
    # This span is also a child of "handle_request"
    with tracer.start_as_current_span("persist") as child:
        save_to_db(request)
```

## TypeScript SDK Patterns

### NodeSDK Setup

```typescript
import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { Resource } from "@opentelemetry/resources";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";

const sdk = new NodeSDK({
  resource: new Resource({
    [ATTR_SERVICE_NAME]: "my-service",
    [ATTR_SERVICE_VERSION]: "1.2.0",
  }),
  traceExporter: new OTLPTraceExporter({
    url: "http://localhost:4318/v1/traces",
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();
```

**Critical gotcha**: The OTel SDK must be initialized before any application code loads. Instrumentation libraries work by monkey-patching modules at import time -- if application code imports `http` or `pg` before the SDK initializes, those modules will not be instrumented. Use the `--import` flag (Node.js v20+):

```bash
node --import ./instrumentation.ts src/main.ts
```

**Meta-package note**: `@opentelemetry/auto-instrumentations-node` bundles all Node.js instrumentations. Convenient for getting started, but pulls a large dependency graph. For production, prefer individual packages (e.g., `@opentelemetry/instrumentation-http`, `@opentelemetry/instrumentation-pg`) for the libraries you actually use.

Always set `service.name` and `service.version` on the SDK resource. These are the minimum attributes for meaningful trace data.

## Span Naming Conventions

Use descriptive operation names that identify the component and action:

- HTTP operations: `HTTP GET /api/users`, `HTTP POST /api/orders`
- Database operations: `db.query SELECT users`, `db.query INSERT orders`
- Message queue operations: `messaging.send orders.created`, `messaging.receive payments.process`
- Custom operations: `{component}.{operation}` format -- `auth.validate_token`, `cache.lookup`

Follow OTel semantic convention patterns when they exist. For custom operations without a matching convention, prefer `{component}.{operation}` over vague names like `process` or `handle`.

Keep span names low-cardinality. Use route templates (`/api/users/{id}`) not actual paths (`/api/users/12345`). High-cardinality span names degrade backend query performance.

## Attribute Naming

Based on the OTel blog "How to Name Your Span Attributes":

**Check semantic conventions first.** If an OTel semconv attribute exists for what you want to express, use it -- do not invent a duplicate.

**Hierarchy with dots:** Structure attributes as `{domain}.{component}.{property}`:

- `http.request.method` -- not `httpMethod` or `method`
- `db.system` -- not `database_type`
- `messaging.destination.name` -- not `queue_name`

**Multi-word with underscores:** When a component or property is multi-word, use underscores:

- `http.response.status_code` -- not `http.response.statusCode`
- `db.query.text` -- not `db.queryText`

**Domain-first ordering:** Start with the broadest category, narrow toward specifics. `user.id` not `id.user`. `payment.method` not `method.payment`.

**Never use `otel.*`:** This namespace is reserved for the OpenTelemetry SDK itself.

**Custom attributes are fine.** When semantic conventions do not cover your domain, define application-specific attributes: `payment.method`, `workflow.step.name`, `feature_flag.key`, `tenant.id`.

## Semantic Conventions

OTel semantic conventions define standard attribute names and values for common operations. Using them ensures cross-tool and cross-language consistency.

Key namespaces:

- `http.*` -- HTTP client and server operations
- `db.*` -- database client operations
- `messaging.*` -- message queue producers and consumers
- `rpc.*` -- RPC/gRPC operations
- `gen_ai.*` -- generative AI / LLM operations (experimental)

Install the conventions package for type-safe attribute access: `opentelemetry-semantic-conventions` (Python) or `@opentelemetry/semantic-conventions` (TypeScript).

**Version note:** Semantic conventions v1.40.0 as of latest release. Some namespaces (notably `gen_ai.*`) are still experimental and may change. Use semconv attributes whenever they match your use case instead of inventing duplicates.

## OpenInference

[OpenInference](https://github.com/Arize-ai/openinference) extends OTel for AI/LLM observability. Developed by Arize, it defines span kinds and attributes for tracing AI application workflows.

**Span kinds:** `CHAIN`, `AGENT`, `TOOL`, `LLM`, `RETRIEVER`, `EMBEDDING`, `RERANKER`, `GUARDRAIL`

**Key attributes:**

| Attribute | Purpose | Example |
|-----------|---------|---------|
| `openinference.span.kind` | AI operation type | `AGENT`, `LLM`, `TOOL` |
| `input.value` | Input to the operation | Prompt text, tool input |
| `output.value` | Output from the operation | LLM response, tool result |
| `llm.model_name` | Model identifier | `claude-sonnet-4-20250514` |
| `llm.token_count.prompt` | Input token count | `1024` |
| `llm.token_count.completion` | Output token count | `512` |

OpenInference spans are standard OTel spans with additional attributes -- they are compatible with any OTel backend. Phoenix (by Arize) natively understands these attributes for AI-specific visualization.

**Practical example:** Praxion's `task-chronograph` MCP server uses OpenInference span kinds (CHAIN for session root, AGENT for pipeline agents) to create hierarchical traces of AI agent sessions.

## Context Propagation

Context propagation carries trace identity across service boundaries, enabling spans from different services to join the same trace.

**Defaults:** W3C Trace Context (`traceparent` / `tracestate` headers) + W3C Baggage (`baggage` header). These are the OTel defaults and the industry standard.

**Override for legacy systems:** Set `OTEL_PROPAGATORS=b3multi` for B3 multi-header format (Zipkin ecosystem) or `OTEL_PROPAGATORS=b3` for B3 single-header.

Auto-instrumentation libraries handle propagation automatically for HTTP calls -- they inject headers on outgoing requests and extract them on incoming requests. No manual code needed for standard HTTP communication.

**Manual propagation** is required for non-HTTP transports: message queue headers, custom binary protocols, or background job systems. Use the `inject` and `extract` functions from the propagation API:

```python
from opentelemetry import propagate

# Inject into carrier (outgoing)
headers = {}
propagate.inject(headers)
send_message(payload, headers=headers)

# Extract from carrier (incoming)
context = propagate.extract(incoming_headers)
with tracer.start_as_current_span("process_message", context=context):
    handle(message)
```

## Auto vs Manual Instrumentation

| Aspect | Auto-instrumentation | Manual instrumentation |
|--------|---------------------|----------------------|
| Setup effort | Low (install + configure) | High (code changes) |
| Coverage | Framework/library operations | Business logic |
| Granularity | Coarse (HTTP, DB, queue boundaries) | Fine (any code path) |
| Maintenance | Library updates may change spans | You control everything |
| Typical packages | `opentelemetry-instrumentation-flask`, `opentelemetry-instrumentation-sqlalchemy` | `opentelemetry-api`, `opentelemetry-sdk` |

**Auto-instrumentation** patches libraries at import time. It covers HTTP clients/servers, database drivers, and message queue clients with zero code changes. Install the relevant `opentelemetry-instrumentation-*` package and enable it in the TracerProvider setup.

**Manual instrumentation** gives full control over span names, attributes, and events. Use it for business-critical operations where auto-instrumentation does not provide enough detail.

**Recommended hybrid approach:** Start with auto-instrumentation for baseline coverage of infrastructure operations. Add manual spans for business-critical paths (checkout, payment, authentication, data pipeline stages). This provides both breadth and depth with minimal code overhead.

```python
# Auto-instrumentation handles Flask/FastAPI HTTP spans automatically.
# Add manual spans for business logic inside the handler:
@app.post("/api/orders")
def create_order(request):
    # Auto: HTTP span created by Flask instrumentation
    with tracer.start_as_current_span("validate_order") as span:
        validate(request.data)
    with tracer.start_as_current_span("charge_payment") as span:
        span.set_attribute("payment.method", request.data["method"])
        charge(request.data)
    with tracer.start_as_current_span("send_confirmation") as span:
        notify(request.data["email"])
```

## OTel Collector Architecture

The OTel Collector is a vendor-agnostic proxy that receives, processes, and exports telemetry data. It decouples applications from backend-specific exporters.

### Pipeline Model

```
Receivers --> Processors --> Exporters
```

- **Receivers** accept data in various formats: OTLP (gRPC/HTTP), Jaeger, Zipkin, Prometheus
- **Processors** transform data in-flight: batching, filtering, attribute enrichment, tail-based sampling
- **Exporters** send data to backends: OTLP, Jaeger, Zipkin, Prometheus remote write, vendor-specific

Multiple pipelines can run in parallel. A single Collector can process traces, metrics, and logs through separate pipelines with different processor and exporter configurations.

### Deployment Patterns

**Agent model** (sidecar or daemonset): Runs near application workloads. Handles retries, batching, and basic processing. Keeps application export paths short and fast. Low resource allocation per instance.

**Gateway model** (centralized): One or a few Collector instances serving many applications. Performs heavy processing: tail-based sampling, cross-service aggregation, enrichment. Higher resource allocation.

**Best practice:** Use both. Agents collect locally with minimal processing (batching, memory limiting). Agents forward to a gateway for centralized processing (sampling decisions, aggregation, routing to multiple backends).

### Key Configuration

- **Batching**: The `batch` processor prevents OOM errors and usage spikes by buffering spans before export. Configure `send_batch_size` and `timeout` based on throughput.
- **Memory limiter**: The `memory_limiter` processor sets a hard cap on Collector memory usage. Essential for production -- prevents runaway memory from unexpected traffic spikes.
- **Compression**: OTLP exporters use `gzip` compression by default. Keep it enabled -- it reduces network bandwidth significantly.
- **TLS/mTLS**: Always configure TLS on receivers (ingress) and exporters (egress) in production. Use mTLS when Collector-to-Collector communication crosses trust boundaries.

## Sampling Strategies

Sampling reduces telemetry volume and cost by exporting only a subset of traces. The trade-off is always: cost savings vs. visibility loss.

### Head-Based Sampling

Decision made at the start of a trace, before any spans are recorded. Simple and predictable -- the application decides immediately whether to record this trace.

- **Pros**: Low overhead, predictable cost, easy to implement
- **Cons**: Uniform sampling rate means rare events (errors, slow requests) are dropped at the same rate as common ones

Configure via `TraceIdRatioBased` sampler: `TraceIdRatioBased(0.1)` samples 10% of traces.

### Tail-Based Sampling

Decision made after the full trace is collected. The Collector examines completed traces and keeps only those matching criteria (errors, high latency, specific attributes).

- **Pros**: Keeps all interesting traces (errors, slow requests), drops routine ones
- **Cons**: Requires Collector gateway (must see the full trace), higher resource cost, added latency before export

Configure in the Collector via the `tail_sampling` processor with policies for error status, latency thresholds, and attribute matches.

### Production Recommendation

Combine both strategies:

1. **Head-based**: Sample 10-20% of all traces for baseline visibility
2. **Tail-based**: Always retain traces that contain errors, exceed latency thresholds, or match debug attributes
3. **Always-sample**: New deployments (first hour), canary traffic, synthetic health checks

This provides cost-controlled baseline coverage while guaranteeing that no error or performance anomaly is lost.
