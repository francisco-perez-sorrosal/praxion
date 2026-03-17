# Relational Schema Design

Patterns and conventions for designing relational database schemas. Language- and database-agnostic unless noted.

## Naming Conventions

### Tables

- Plural nouns: `users`, `orders`, `line_items`
- Snake_case for multi-word names
- Junction tables: `<table_a>_<table_b>` in alphabetical order (e.g., `roles_users`)

### Columns

- Snake_case: `created_at`, `order_total`, `is_active`
- Primary key: `id` (or `<table_singular>_id` when clarity requires it)
- Foreign key: `<referenced_table_singular>_id` (e.g., `user_id` in the `orders` table)
- Booleans: prefix with `is_`, `has_`, or `should_` (e.g., `is_active`, `has_verified_email`)
- Timestamps: suffix with `_at` (e.g., `created_at`, `updated_at`, `deleted_at`)

### Constraints and Indexes

- Primary key: `pk_<table>`
- Foreign key: `fk_<table>_<referenced_table>`
- Unique: `uq_<table>_<column(s)>`
- Check: `ck_<table>_<description>`
- Index: `ix_<table>_<column(s)>`

## Constraint Design

### Primary Keys

- Every table must have a primary key
- Prefer surrogate keys (`id` as auto-incrementing integer or UUID) for most tables
- Use natural keys only when the natural identifier is truly immutable and unique (e.g., ISO country codes)
- UUIDs: use UUID v7 (time-ordered) for clustered index friendliness; avoid UUID v4 for primary keys in B-tree indexes due to random insertion overhead

### Foreign Keys

- Always define foreign key constraints -- they enforce referential integrity and document relationships
- Set appropriate `ON DELETE` behavior:

| Behavior | Use When |
| --- | --- |
| `RESTRICT` (default) | Parent must not be deleted while children exist |
| `CASCADE` | Children are meaningless without the parent (e.g., order line items) |
| `SET NULL` | Relationship is optional and orphaned records are acceptable |
| `SET DEFAULT` | Fallback value exists (rare) |

- Avoid `ON DELETE CASCADE` on tables with audit significance -- use soft deletes instead

### Unique Constraints

- Apply to natural identifiers: email, username, SKU, external API ID
- Use partial unique indexes for conditional uniqueness (e.g., unique active email: `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`)

### Check Constraints

- Encode domain invariants: `CHECK (quantity > 0)`, `CHECK (end_date > start_date)`
- Prefer check constraints over application-only validation for rules that must never be violated

## Indexing Strategies

### Index Types

| Type | Use Case |
| --- | --- |
| **B-tree** (default) | Equality and range queries, sorting |
| **Hash** | Equality-only lookups (PostgreSQL, MySQL NDB) |
| **GIN** | Full-text search, array containment, JSONB operators |
| **GiST** | Geometric data, range types, nearest-neighbor |
| **Partial** | Subset of rows (e.g., `WHERE is_active = true`) |
| **Covering** | Include non-key columns to enable index-only scans |

### Indexing Decision Process

1. Identify the most frequent and performance-critical queries
2. Index columns that appear in `WHERE`, `JOIN ON`, and `ORDER BY` clauses
3. Prefer composite indexes over multiple single-column indexes for multi-column filters (leftmost prefix rule)
4. Add covering indexes (`INCLUDE` columns) for queries that need index-only scans
5. Avoid over-indexing -- every index slows writes and consumes storage
6. Review index usage periodically; drop unused indexes

### Composite Index Column Order

Place columns in this order of priority:
1. Equality conditions first (`WHERE status = 'active'`)
2. Range conditions next (`WHERE created_at > '2025-01-01'`)
3. Sort columns last (`ORDER BY name`)

## Common Schema Patterns

### Soft Delete

Add a `deleted_at` timestamp column instead of physically removing rows.

```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP NULL;
CREATE UNIQUE INDEX uq_users_email_active ON users(email) WHERE deleted_at IS NULL;
```

- All queries must filter `WHERE deleted_at IS NULL` (enforce via application layer or database views)
- Enables audit trail and easy undo
- Consider a periodic hard-delete job for data retention compliance

### Audit Trail

Track who changed what and when:

```sql
CREATE TABLE audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    old_values JSONB,
    new_values JSONB
);
```

Implement via database triggers or application-level middleware. Triggers are more reliable (cannot be bypassed) but harder to maintain.

### Polymorphic Associations

When multiple entity types share a relationship (e.g., comments on posts, photos, and videos):

**Preferred: Separate FK columns**
```sql
CREATE TABLE comments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    body TEXT NOT NULL,
    post_id BIGINT REFERENCES posts(id),
    photo_id BIGINT REFERENCES photos(id),
    video_id BIGINT REFERENCES videos(id),
    CHECK (
        (post_id IS NOT NULL)::int +
        (photo_id IS NOT NULL)::int +
        (video_id IS NOT NULL)::int = 1
    )
);
```

**Avoid: Generic `commentable_type` + `commentable_id`** -- this pattern cannot use foreign key constraints and breaks referential integrity.

### Entity-Attribute-Value (EAV)

Use only when the set of attributes is truly unbounded and varies per entity (e.g., product specifications across categories). For known attribute sets, prefer dedicated columns or JSONB.

EAV trade-offs:
- Flexible schema for heterogeneous attributes
- Poor query performance, no type safety, no constraints
- Consider JSONB columns as a modern alternative with indexing support

## Normalization Examples

### Unnormalized (0NF)

```
orders: [order_id, customer_name, customer_email, item1_name, item1_qty, item2_name, item2_qty]
```

Problems: repeating groups, update anomalies, fixed number of items.

### First Normal Form (1NF)

Eliminate repeating groups -- one value per column, one row per item:

```
order_items: [order_id, item_name, quantity]
orders: [order_id, customer_name, customer_email]
```

### Second Normal Form (2NF)

Remove partial dependencies -- every non-key column depends on the entire primary key:

```
orders: [order_id, customer_id, order_date]
customers: [customer_id, name, email]
order_items: [order_id, item_id, quantity]
items: [item_id, name, price]
```

### Third Normal Form (3NF)

Remove transitive dependencies -- non-key columns depend only on the primary key, not on other non-key columns. If `orders` had `customer_name` derived from `customer_id`, remove it. The 2NF example above is already in 3NF.
