# Data Modeling Skill

Database and data model design -- relational schemas, NoSQL document modeling, migration strategies, ORM patterns, and schema evolution.

## When to Use

- Designing a new database schema or data model
- Choosing between relational, document, and graph databases
- Planning normalization levels or denormalization strategies
- Writing database migrations, especially for zero-downtime deployments
- Working with ORMs and optimizing data access patterns
- Modeling entities, relationships, and aggregates for domain-driven design
- Evolving an existing schema in production

## Activation

The skill activates automatically when the agent detects data modeling tasks: schema design, migration planning, database selection, normalization discussions, or ORM usage patterns.

Trigger explicitly by mentioning "data-modeling skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: entity identification, model selection framework, normalization decisions, schema evolution, ORM guidelines |
| `references/schema-design.md` | Relational patterns: naming conventions, constraints, indexing strategies, common schema patterns |
| `references/nosql-patterns.md` | Document modeling (embedding vs referencing), key-value, column-family, graph patterns |
| `references/migrations.md` | Expand-contract pattern, zero-downtime checklist, rollback strategies, data backfill |
| `references/orm-patterns.md` | Repository pattern, N+1 prevention, query optimization, connection pooling |

## Quick Start

1. Identify entities and relationships from domain requirements
2. Use the model selection framework to choose relational, document, or graph
3. Apply normalization decision framework (default to 3NF for transactional systems)
4. Design constraints and indexes based on access patterns
5. Plan migrations using expand-contract for any breaking changes

## Related Skills

- [`python-development`](../python-development/) -- SQLAlchemy and Pydantic model patterns
- [`cicd`](../cicd/) -- running migration checks in CI pipelines
