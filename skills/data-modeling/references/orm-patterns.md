# ORM Patterns

Patterns for using Object-Relational Mappers effectively, avoiding common pitfalls, and knowing when to bypass the ORM. Language-agnostic -- examples use pseudocode.

## Repository Pattern

Encapsulate data access logic behind an interface that presents a collection-like API. Keeps domain logic free of query details.

```
interface UserRepository:
    find_by_id(id) -> User | None
    find_by_email(email) -> User | None
    find_active(limit, offset) -> list[User]
    save(user) -> User
    delete(user) -> void
```

### When to Use

- Application has multiple data access patterns for the same entity
- Domain logic should not depend on ORM-specific APIs
- Testing requires swapping real data access for in-memory fakes

### When to Skip

- Simple CRUD with no domain logic -- the ORM's built-in query API is sufficient
- Prototypes or scripts where abstraction adds overhead without benefit

### Guidelines

- One repository per aggregate root, not per table
- Keep repository methods focused -- return domain objects, not raw query results
- Avoid generic `Repository<T>` base classes that expose the entire query surface; define only the methods the domain needs
- Place query complexity inside the repository; callers should not construct queries

## Unit of Work

Coordinate multiple repository operations within a single transaction. Track changes across entities and commit them atomically.

```
with unit_of_work() as uow:
    user = uow.users.find_by_id(user_id)
    user.deactivate()
    uow.users.save(user)
    uow.audit_logs.save(AuditLog(action="deactivate", entity_id=user_id))
    uow.commit()
```

- Most ORMs implement unit of work implicitly via the session/context (SQLAlchemy Session, Entity Framework DbContext, Hibernate Session)
- Make transaction boundaries explicit -- do not rely on auto-commit
- Keep units of work short-lived to avoid holding database connections and locks

## N+1 Query Detection and Prevention

The N+1 problem occurs when loading a collection of N entities triggers N additional queries to load related data.

### Detection

- Enable query logging in development and watch for repeated similar queries
- Use ORM-specific tools: SQLAlchemy `echo=True`, Django `django-debug-toolbar`, Hibernate `hibernate.show_sql`
- Automated detection: some ORMs offer N+1 warnings (Rails `bullet` gem, Django `nplusone`)

### Prevention Strategies

| Strategy | Mechanism | When to Use |
| --- | --- | --- |
| **Eager loading** | `joinedload` / `includes` / `Include` | Always need the related data together |
| **Subquery loading** | Separate SELECT with `IN` clause | Related collections are large; avoid Cartesian product |
| **Batch loading** | Load related data in batches of N IDs | Many parent entities, moderate related data |
| **Select only needed columns** | Projection | Only a few fields from the related entity are needed |
| **Data loader** | Batch and cache within a request | GraphQL resolvers or similar per-request contexts |

### Example: Eager vs Lazy

```
# N+1: loads each user's orders in a separate query
users = query(User).all()
for user in users:
    print(user.orders)   # triggers a query per user

# Fixed: eager load orders with the initial query
users = query(User).options(joinedload(User.orders)).all()
for user in users:
    print(user.orders)   # already loaded, no additional query
```

## Eager vs Lazy Loading Decision

| Factor | Eager | Lazy |
| --- | --- | --- |
| **Always accessed together** | Yes | No |
| **List/collection context** | Yes (prevents N+1) | Only for single-entity access |
| **Related data is large** | Use subquery load | Acceptable if rarely accessed |
| **API response** | Load everything the response needs upfront | Never -- lazy loading outside a session causes errors |

Default to **explicit eager loading** for known access patterns. Use lazy loading only for optional relationships that are accessed in less than 20% of cases.

## Query Optimization

### Projection

Select only the columns needed instead of loading full entities:

```
# Instead of loading full User objects
users = query(User).all()

# Select only what's needed
names = query(User.id, User.name).filter(User.is_active == True).all()
```

Projection reduces memory usage and network transfer, especially for entities with large text or binary columns.

### Pagination

Always paginate unbounded queries. Use cursor-based pagination for large datasets:

```
# Offset-based (simple, but slow for large offsets)
query(User).order_by(User.id).offset(100).limit(20)

# Cursor-based (consistent performance at any depth)
query(User).filter(User.id > last_seen_id).order_by(User.id).limit(20)
```

Cursor-based pagination avoids the `OFFSET` performance cliff where the database must scan and discard rows.

### Bulk Operations

ORMs are inefficient for bulk inserts and updates. Use bulk APIs or raw SQL:

```
# ORM bulk insert (bypasses per-row hooks but uses ORM connection)
session.bulk_insert_mappings(User, [{"name": "Alice"}, {"name": "Bob"}])

# Raw SQL for maximum throughput
session.execute("INSERT INTO users (name) VALUES (:name)", [{"name": "Alice"}, {"name": "Bob"}])
```

- Bulk operations bypass ORM change tracking and hooks -- use deliberately
- For very large datasets (100k+ rows), use database-native bulk loading tools (PostgreSQL `COPY`, MySQL `LOAD DATA INFILE`)

## When to Use Raw SQL

Drop to raw SQL when the ORM adds friction rather than value:

| Scenario | Reason |
| --- | --- |
| Window functions (`ROW_NUMBER`, `RANK`) | Most ORMs lack native support |
| Recursive CTEs | Tree/graph traversal not expressible in ORM query builders |
| Database-specific features | Full-text search, JSON operators, array operations |
| Complex reporting queries | Multi-table aggregations with grouping sets |
| Performance-critical paths | ORM-generated SQL is suboptimal after tuning attempts |
| Bulk data operations | ORM per-row overhead is unacceptable |

### Raw SQL Guidelines

- Use parameterized queries -- never concatenate user input into SQL strings
- Wrap raw SQL in repository methods so callers remain ORM-agnostic
- Document why raw SQL was chosen over the ORM (performance benchmark, missing feature)
- Map raw SQL results to domain objects or typed DTOs, not raw dictionaries

## Connection Pooling

### Configuration Guidelines

| Parameter | Guidance |
| --- | --- |
| **Pool size** | Start with `2 * CPU cores + disk spindles` (PostgreSQL recommendation); tune from there |
| **Max overflow** | Allow 50-100% overflow for burst traffic; set a hard ceiling |
| **Connection timeout** | 5-10 seconds; fail fast rather than queue indefinitely |
| **Idle timeout** | Reclaim idle connections after 5-10 minutes |
| **Max connection lifetime** | Recycle connections every 30-60 minutes to handle DNS changes and server restarts |

### Common Pitfalls

- **Connection leak**: Always close/return connections, even on error paths; use context managers or try-finally
- **Pool exhaustion**: Monitor active connections; set alerts at 80% capacity
- **Long-running transactions**: Hold connections for the minimum time; move computation outside the transaction
- **Async mismatch**: Use async-compatible pools (e.g., `asyncpg`) with async frameworks; mixing sync and async pools causes blocking
