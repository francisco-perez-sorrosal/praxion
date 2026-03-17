---
name: data-modeling
description: Database and data model design covering relational schema design, NoSQL
  document modeling, normalization strategies, migration planning, ORM patterns, and
  schema evolution. Use when designing database schemas, choosing between relational
  and NoSQL, planning data migrations, modeling entities and relationships, designing
  indexes, working with ORMs, normalizing or denormalizing data, creating ER diagrams,
  defining aggregates for domain-driven design, or evolving schemas in production.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Data Modeling

Guidance for designing data models, database schemas, and data access patterns across relational, document, and graph paradigms.

**Satellite files** (loaded on-demand):

- [references/schema-design.md](references/schema-design.md) -- relational schema patterns, naming conventions, constraints, indexing strategies
- [references/nosql-patterns.md](references/nosql-patterns.md) -- document modeling, key-value, column-family, graph data models
- [references/migrations.md](references/migrations.md) -- expand-contract pattern, zero-downtime migrations, rollback strategies
- [references/orm-patterns.md](references/orm-patterns.md) -- repository pattern, N+1 prevention, query optimization, raw SQL escape hatches

## Core Principles

**Model from behavior, not from storage.** Start with the domain's entities, relationships, and access patterns. Let the data model serve the application's needs rather than fitting application logic around a schema. Entity-relationship modeling comes first; physical schema design follows.

**Access patterns drive structure.** Understand how data will be read and written before choosing normalization levels, index strategies, or embedding vs referencing. A schema that optimizes for writes at the expense of reads (or vice versa) creates accidental complexity.

**Evolve incrementally.** Schemas change over time. Design for additive evolution -- new columns, new tables, wider types -- rather than breaking changes. Use the expand-contract pattern for structural migrations.

**Constraints are documentation that the database enforces.** Primary keys, foreign keys, unique constraints, and check constraints encode business rules at the storage layer. Prefer database-level constraints over application-only validation for invariants that must always hold.

## Data Modeling Methodology

### Entity Identification

1. Extract nouns from domain requirements -- these are candidate entities
2. Distinguish entities (have identity and lifecycle) from value objects (defined by attributes alone)
3. Identify relationships: one-to-one, one-to-many, many-to-many
4. Map cardinality and optionality for each relationship
5. Define aggregate boundaries -- clusters of entities that change together as a consistency unit

### Relationship Mapping

| Relationship | Relational | Document DB | Graph DB |
| --- | --- | --- | --- |
| One-to-one | FK with unique constraint | Embed in parent document | Edge between nodes |
| One-to-many | FK on child table | Embed array or reference | Edges from parent |
| Many-to-many | Junction table | Reference arrays on both sides | Edges between nodes |
| Hierarchical | Self-referencing FK, closure table, or materialized path | Nested documents or ancestor array | Native traversal |

### Domain-Driven Design Aggregates

An aggregate is a cluster of entities treated as a single unit for data changes. Design aggregates around consistency boundaries:

- Each aggregate has exactly one root entity
- External references point only to the aggregate root
- Transactions should not span multiple aggregates
- Size aggregates for the smallest consistency boundary that satisfies business invariants
- In microservices, one service typically owns one or more aggregates -- never share an aggregate across services

## Model Selection Framework

Choose the data model based on the domain's characteristics, not technology preference.

| Signal | Relational | Document | Graph |
| --- | --- | --- | --- |
| **Data relationships** | Well-defined, stable relationships | Hierarchical, self-contained entities | Highly interconnected, variable-depth |
| **Schema stability** | Known schema, evolves slowly | Schema varies per entity or evolves rapidly | Relationships evolve; node properties stable |
| **Query patterns** | Complex joins, aggregations, reporting | Single-entity reads, nested access | Traversals, path finding, pattern matching |
| **Consistency needs** | Strong ACID transactions | Eventual consistency acceptable | Varies by engine |
| **Scale pattern** | Vertical + read replicas | Horizontal sharding | Vertical or specialized clusters |
| **Examples** | Financial systems, ERP, inventory | Content management, user profiles, catalogs | Social networks, fraud detection, recommendations |

When signals are mixed, default to relational -- it handles the widest range of access patterns and provides the strongest consistency guarantees. Add document or graph stores for specific subdomains that clearly benefit.

## Normalization Decision Framework

Normalize to the level that balances integrity against query performance for the specific workload.

| Level | Rule | When to Stop Here |
| --- | --- | --- |
| **1NF** | Atomic values, no repeating groups | Logging tables, append-only event stores |
| **2NF** | No partial dependencies on composite keys | Tables with single-column primary keys (already 2NF if 1NF) |
| **3NF** | No transitive dependencies | Default target for OLTP -- good balance of integrity and performance |
| **BCNF** | Every determinant is a candidate key | Tables with overlapping candidate keys or complex constraints |
| **Denormalized** | Controlled redundancy for read performance | Read-heavy reporting, materialized views, data warehouse fact tables |

**Decision process:**

1. Start at 3NF for transactional systems
2. Measure query performance against access patterns
3. Denormalize selectively with materialized views or summary tables when 3NF queries are too slow
4. Document every denormalization decision with the trade-off rationale

--> See [references/schema-design.md](references/schema-design.md) for normalization worked examples, constraint design, and indexing strategies.

## Schema Evolution

Design schemas for forward-compatible change. Prefer additive operations that do not break existing consumers.

### Safe Changes (backward-compatible)

- Add a new column with a default value or nullable
- Add a new table
- Add a new index
- Widen a data type (e.g., `VARCHAR(50)` to `VARCHAR(100)`, `INT` to `BIGINT`)

### Unsafe Changes (require migration strategy)

- Rename or remove a column
- Change a column's data type to a narrower or incompatible type
- Add a NOT NULL constraint to an existing column
- Split or merge tables

### Column Deprecation Lifecycle

1. **Mark deprecated** -- add a code comment and documentation note; stop writing new code that references the column
2. **Dual-write** -- write to both old and new columns during the transition period
3. **Migrate readers** -- update all read paths to use the new column
4. **Stop writing** -- remove writes to the deprecated column
5. **Drop** -- remove the column after confirming zero reads and writes (verify with query logs or column usage tracking)

Set explicit deprecation windows (e.g., 30-90 days) and communicate them to all consumers.

--> See [references/migrations.md](references/migrations.md) for the expand-contract pattern, zero-downtime migration checklist, and rollback strategies.

## ORM Usage Guidelines

ORMs reduce boilerplate for standard CRUD operations. Use them as a starting point, not a ceiling.

**Use the ORM for:**
- Standard CRUD operations
- Schema definition and migration generation
- Relationship loading with explicit eager/lazy control
- Type-safe query building

**Drop to raw SQL for:**
- Complex analytical queries with window functions or CTEs
- Bulk operations (batch inserts, mass updates)
- Database-specific features (full-text search, JSON operators, recursive queries)
- Performance-critical queries where the ORM generates suboptimal SQL

**Always:**
- Monitor generated SQL in development (enable query logging)
- Set connection pool sizes based on the application's concurrency model
- Use parameterized queries for all user input, whether through ORM or raw SQL

--> See [references/orm-patterns.md](references/orm-patterns.md) for the repository pattern, N+1 prevention, and query optimization strategies.

## Integration with Other Skills

- **[API Design](../api-design/SKILL.md)** -- data models inform API resource surfaces; schema evolution rules complement API versioning
- **[Python Development](../python-development/SKILL.md)** -- SQLAlchemy and Pydantic model patterns when working in Python
- **[CI/CD](../cicd/SKILL.md)** -- running migration checks and schema validation in CI pipelines

## Resources

- [Database Design (Adrienne Watt)](https://opentextbc.ca/dbdesign01/) -- open textbook on relational database design
- [Use The Index, Luke](https://use-the-index-luke.com/) -- SQL indexing and tuning
- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) -- official document modeling guide
- [Evolutionary Database Design (Fowler)](https://martinfowler.com/articles/evodb.html) -- incremental schema evolution
- [Designing Data-Intensive Applications (Kleppmann)](https://dataintensive.net/) -- comprehensive data systems reference

## Checklist

Before finalizing a data model:

### Model Quality

- [ ] Entities identified from domain requirements, not implementation assumptions
- [ ] Relationships mapped with correct cardinality and optionality
- [ ] Aggregate boundaries defined around consistency requirements
- [ ] Access patterns documented and schema supports them efficiently

### Schema Design

- [ ] Naming conventions consistent across all tables and columns
- [ ] Primary keys defined on every table
- [ ] Foreign keys enforce referential integrity
- [ ] Appropriate constraints (unique, check, not null) encode business rules
- [ ] Indexes support the documented access patterns
- [ ] Normalization level chosen deliberately with documented rationale

### Evolution Readiness

- [ ] Schema changes are additive where possible
- [ ] Migration strategy identified for any breaking changes
- [ ] Rollback plan exists for each migration step
- [ ] Deprecated columns have explicit removal timelines
