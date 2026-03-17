# Data Contracts

Patterns for defining, evolving, and enforcing data schemas across service boundaries. Data contracts formalize the agreement between data producers and consumers on structure, semantics, and evolution rules.

## What is a Data Contract

A data contract is a formal agreement specifying:

- **Structure**: field names, types, required vs optional, constraints
- **Semantics**: what each field means, valid value ranges, business rules
- **Evolution rules**: how the schema can change without breaking consumers
- **Ownership**: which team or service owns the schema definition
- **Quality guarantees**: freshness, completeness, accuracy expectations

Data contracts apply to any data exchange boundary: API request/response bodies, event payloads, message queue messages, shared database schemas, data pipeline outputs.

## Schema Evolution

### Compatibility Modes

| Mode | Definition | Safe Changes | Use When |
|------|-----------|-------------|----------|
| **Backward** | New schema can read data written by old schema | Add optional fields with defaults, remove fields | Default for most systems -- consumers upgrade first |
| **Forward** | Old schema can read data written by new schema | Remove fields, add fields (ignored by old readers) | Producers upgrade first |
| **Full** | Both backward and forward compatible | Add/remove optional fields only | Producers and consumers upgrade independently |
| **None** | No compatibility guarantee | Any change | Development/prototyping only |

**Default to backward compatibility** -- it is the safest mode for production systems and the default in most schema registries.

### Safe vs Unsafe Schema Changes

| Change | Backward | Forward | Full |
|--------|----------|---------|------|
| Add optional field with default | Safe | Safe | Safe |
| Add required field | Unsafe | Safe | Unsafe |
| Remove optional field | Safe | Unsafe | Unsafe |
| Remove required field | Safe | Unsafe | Unsafe |
| Rename field | Unsafe | Unsafe | Unsafe |
| Change field type | Unsafe | Unsafe | Unsafe |
| Widen type (int32 to int64) | Depends on format | Depends on format | Depends on format |
| Add enum value | Safe | Unsafe | Unsafe |

### Expand-Contract Pattern

Evolve schemas without breaking consumers by following three phases:

1. **Expand**: add the new field alongside the old one. Producers populate both. Consumers can use either.
2. **Migrate**: consumers switch to the new field. Monitor until all consumers have migrated.
3. **Contract**: remove the old field. Only safe after confirming zero consumers depend on it.

This pattern applies to any schema change that would otherwise be breaking. It trades speed for safety -- each phase requires a separate deployment and monitoring period.

## Serialization Format Comparison

| Factor | JSON Schema | Avro | Protobuf |
|--------|-------------|------|----------|
| **Schema location** | Separate file or inline | Embedded with data or in registry | Separate `.proto` file |
| **Encoding** | Text (JSON) | Binary (compact) | Binary (compact) |
| **Schema evolution** | Manual validation | Built-in compatibility checking | Field numbering enables evolution |
| **Human readability** | High | Low (binary) | Medium (schema is readable) |
| **Code generation** | Optional | Standard | Standard |
| **Null handling** | Native `null` type | Union with `null` | Optional/wrapper types |
| **Default values** | Via `default` keyword | Required for backward compat | Proto3: zero values; Proto2: explicit |
| **Best for** | REST APIs, web services | Event streaming (Kafka), data pipelines | gRPC, high-performance services |

### Selection Guidance

- **REST/HTTP APIs**: JSON Schema (via OpenAPI). Consumers expect JSON; binary encoding adds unnecessary complexity.
- **Event streaming (Kafka, Pulsar)**: Avro with a schema registry. Binary encoding reduces message size; built-in compatibility checking prevents breaking changes.
- **gRPC / high-performance RPC**: Protobuf. Designed for this use case; field numbering provides natural schema evolution.
- **Polyglot environments**: Protobuf or Avro. Both have code generation for every major language.

## Schema Registries

A schema registry stores versioned schemas and enforces compatibility rules at write time. Producers register schemas before publishing data; consumers retrieve schemas to deserialize.

### Core Functions

- **Storage**: versioned schema repository with subject-level organization
- **Compatibility checking**: rejects schema changes that violate the configured compatibility mode
- **Serialization support**: provides schema ID in message headers for efficient deserialization
- **Audit trail**: records every schema change with timestamp and metadata

### Registry Workflow

```text
1. Producer defines schema --> registers in registry (compatibility check runs)
2. Registry assigns schema ID --> producer embeds ID in message header
3. Consumer reads message --> fetches schema by ID from registry --> deserializes
4. Schema update --> producer registers new version --> registry checks compatibility
```

### When to Use a Registry

- Multiple producers or consumers for the same data schema
- Event-driven architecture where schema enforcement at the message level is needed
- Data pipelines where schema drift causes downstream failures
- Any system where "it worked on my machine" schema mismatches are a risk

For simple request/response APIs, the OpenAPI specification serves as the schema registry. A dedicated registry adds value when data flows through asynchronous channels (queues, streams, pipelines).

## Producer-Consumer Contract Patterns

### Provider-Driven Contracts

The producer defines the schema, and consumers adapt. Best when the producer has many consumers with similar needs and cannot accommodate each one individually.

```text
Producer defines schema --> publishes to registry --> consumers adapt
```

Use when: single authoritative data source, many consumers, producer team sets the standard.

### Consumer-Driven Contracts

Consumers define the minimum schema they need, and the producer guarantees those fields. The producer may include additional fields, but the contracted fields are guaranteed.

```text
Consumer publishes expectations --> producer validates against all consumer contracts --> producer evolves without breaking any consumer
```

Use when: consumer needs vary significantly, producer team wants to evolve safely, microservices architecture where each consumer has different requirements.

### Bilateral Contracts

Both sides agree on a shared schema managed as an independent artifact. Changes require agreement from both parties.

```text
Shared schema defined collaboratively --> both sides validate against it --> changes require joint review
```

Use when: tightly coupled services, critical data paths, regulatory requirements for data format agreements.

## Contract Testing Integration

Contract testing validates that producers and consumers conform to the agreed contract at build time rather than at runtime. See [interface-contracts.md](interface-contracts.md) for detailed contract testing patterns.

Key integration points:

- **CI pipeline**: run contract tests on every PR to catch breaking changes before merge
- **Schema registry hooks**: trigger contract test runs when new schema versions are registered
- **Deployment gates**: block deployment if contract tests fail against any active consumer contract

## Data Contract Checklist

- [ ] Schema defined with explicit field types, required/optional, and constraints
- [ ] Compatibility mode selected and enforced (backward by default)
- [ ] Serialization format chosen based on transport (JSON for HTTP, binary for streaming)
- [ ] Schema ownership assigned to a specific team or service
- [ ] Evolution rules documented -- what changes are safe, what requires a new version
- [ ] Consumer contracts identified -- which consumers depend on which fields
- [ ] Schema registry in place for event-driven or multi-consumer data flows
- [ ] Contract tests integrated into CI pipeline
