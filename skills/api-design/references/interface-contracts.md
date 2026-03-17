# Interface Contracts

Patterns for defining service boundaries, establishing behavioral guarantees between services, and verifying compliance through contract testing.

## What is an Interface Contract

An interface contract defines the behavioral agreement at a service boundary:

- **Operations**: what actions the service exposes (endpoints, methods, events)
- **Input/output schemas**: what data each operation accepts and returns
- **Behavioral guarantees**: preconditions, postconditions, invariants, error conditions
- **Non-functional contracts**: latency expectations, rate limits, availability guarantees
- **Evolution rules**: how the interface can change and what backward compatibility means

Interface contracts complement API specifications by adding behavioral semantics -- not just what the API accepts and returns, but what guarantees it provides about its behavior.

## Interface-First Design

Define the interface before the implementation. This applies at every service boundary:

1. **Identify the boundary** -- where two systems, teams, or deployment units interact
2. **Define operations** -- what the consumer needs the provider to do (not what the provider can do)
3. **Specify schemas** -- input and output types for each operation, including error cases
4. **Document guarantees** -- what the provider promises about behavior (idempotency, ordering, consistency)
5. **Establish evolution rules** -- how the interface can change without breaking consumers
6. **Write contract tests** -- codify the contract as executable verification

### Boundary Identification

Service boundaries exist at:

- **Synchronous service calls** -- REST/gRPC between microservices
- **Asynchronous messaging** -- events published to queues or topics
- **Shared data stores** -- database schemas accessed by multiple services
- **Third-party integrations** -- external APIs the system depends on
- **Internal module boundaries** -- public API of a library or package (within a monolith)

Each boundary should have an explicit owner. The owner defines the contract, maintains backward compatibility, and communicates changes.

## Consumer-Driven Contracts

In consumer-driven contract testing, each consumer defines the subset of provider behavior it depends on. The provider verifies it satisfies all consumer contracts.

### How It Works

```text
1. Consumer team writes a contract:
   "When I call GET /users/{id}, I expect { id, email, display_name } in the response"

2. Contract is stored in a shared location (repository, broker, registry)

3. Provider runs all consumer contracts as part of its CI pipeline

4. If the provider changes break any consumer contract, the build fails

5. Consumer updates their contract when their needs change
```

### Contract Scope

A consumer contract should specify the minimum the consumer depends on -- no more:

- **Include**: fields the consumer reads, status codes the consumer handles, error formats the consumer parses
- **Exclude**: fields the consumer ignores, internal implementation details, exact response times

Overly strict contracts break unnecessarily. Overly loose contracts miss real breaking changes. The test for each assertion: "If the provider violates this, does the consumer actually break?"

### Provider Verification

The provider runs all consumer contracts against its real implementation (not a mock):

```text
Consumer A contract: GET /users/{id} returns { id, email }
Consumer B contract: GET /users/{id} returns { id, display_name, role }
Consumer C contract: POST /users returns 201 with { id }

Provider CI: runs all three contracts --> all pass --> safe to deploy
```

If a provider change breaks any consumer contract, the provider team fixes the issue or negotiates a contract update with the affected consumer.

## Contract Testing Approaches

| Approach | Mechanism | Pros | Cons |
|----------|-----------|------|------|
| **Consumer-driven (Pact)** | Consumer defines expectations, provider verifies | Catches real breaking changes, consumer-aligned | Requires consumer teams to write contracts |
| **Provider-driven (OpenAPI)** | Provider publishes spec, consumers validate against it | Single source of truth, simple tooling | May not reflect actual consumer needs |
| **Bilateral (schema artifact)** | Shared schema owned jointly | Strong guarantees, mutual agreement | Slower evolution, coordination overhead |

### Integration with CI/CD

Run contract tests at two points in the pipeline:

1. **Consumer PR**: verify that the consumer's expectations still match the current provider (prevents consumer drift)
2. **Provider PR**: verify that the provider still satisfies all consumer contracts (prevents breaking changes)

Fail the build on any contract violation. Contract test failures are blocking -- they represent an actual compatibility break, not a flaky test.

## Service Boundary Patterns

### Facade Pattern

Expose a simplified interface that hides internal complexity. The facade translates between the consumer-friendly contract and the internal implementation:

```text
Consumer --> Facade (stable contract) --> Internal Services (free to refactor)
```

Use when internal architecture changes frequently but the consumer interface must remain stable.

### Anti-Corruption Layer

Isolate the consumer from a messy or legacy provider by translating between the consumer's model and the provider's model:

```text
Consumer --> Anti-Corruption Layer --> Legacy Provider
```

Use when integrating with third-party APIs or legacy systems whose contracts are unstable or poorly designed. The ACL absorbs provider-side changes so the consumer's code remains clean.

### Gateway Aggregation

Combine multiple provider calls into a single consumer-facing operation:

```text
Consumer --> Gateway --> Provider A (user data)
                     --> Provider B (order data)
                     --> Provider C (payment data)
```

Use when the consumer needs data from multiple providers and should not be coupled to each one individually. The gateway owns the aggregated contract.

## Non-Functional Contracts

Beyond data schemas, document these operational guarantees:

| Guarantee | Definition | Example |
|-----------|-----------|---------|
| **Latency SLO** | Maximum response time at a given percentile | p99 < 200ms |
| **Availability SLO** | Uptime target | 99.9% monthly |
| **Rate limit** | Maximum requests per time window | 1000 req/min per API key |
| **Idempotency** | Safe to retry without side effects | PUT and DELETE are idempotent |
| **Ordering** | Message delivery order guarantee | FIFO within partition key |
| **Consistency** | Data freshness guarantee | Eventually consistent, < 5s lag |

Document non-functional contracts alongside the API specification. They inform consumer retry strategies, timeout configuration, and capacity planning.

## Contract Evolution

### Adding a New Operation

Safe. Existing consumers are unaffected. Document the new operation and notify consumers.

### Modifying an Existing Operation

Follow the expand-contract pattern from [data-contracts.md](data-contracts.md):

1. Add the new behavior alongside the old
2. Migrate consumers
3. Remove the old behavior

### Removing an Operation

Breaking. Follow the deprecation workflow from [api-versioning.md](api-versioning.md):

1. Announce deprecation with timeline
2. Add deprecation headers/metadata
3. Monitor usage until zero
4. Remove after sunset date

### Changing Non-Functional Guarantees

Treat changes to SLOs, rate limits, or consistency guarantees as potentially breaking. Communicate changes through the same channels as schema changes.

## Interface Contract Checklist

- [ ] Service boundaries identified with explicit ownership
- [ ] Operations defined from the consumer's perspective (interface-first)
- [ ] Input/output schemas specified for every operation
- [ ] Error conditions and error response format documented
- [ ] Behavioral guarantees stated (idempotency, ordering, consistency)
- [ ] Non-functional contracts documented (latency, availability, rate limits)
- [ ] Evolution rules established -- what changes are safe, what requires versioning
- [ ] Contract tests written and integrated into CI for both consumer and provider
- [ ] Deprecation workflow defined for removing or changing operations
