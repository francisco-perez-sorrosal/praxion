# NoSQL Data Modeling Patterns

Patterns for designing data models in document, key-value, column-family, and graph databases. Focus on access-pattern-driven design rather than normalization.

## Document Modeling

Document databases (MongoDB, DynamoDB, Firestore, CouchDB) store data as self-contained documents, typically JSON/BSON.

### Embedding vs Referencing

The fundamental design decision in document modeling. Choose based on access patterns, not relational instincts.

| Factor | Embed | Reference |
| --- | --- | --- |
| **Access pattern** | Always read together | Accessed independently |
| **Cardinality** | One-to-few (< ~100) | One-to-many or many-to-many |
| **Update frequency** | Rarely changes | Frequently updated |
| **Document size** | Stays well under size limit | Would exceed size limit |
| **Data duplication** | Acceptable (read-optimized) | Unacceptable (write-optimized) |
| **Atomicity** | Needs atomic update with parent | Independent lifecycle |

### Embedding Patterns

**One-to-few: Embed directly**
```json
{
  "user_id": "u123",
  "name": "Alice",
  "addresses": [
    { "type": "home", "city": "Portland", "zip": "97201" },
    { "type": "work", "city": "Seattle", "zip": "98101" }
  ]
}
```

**One-to-many with bounded growth: Embed array**
```json
{
  "order_id": "o456",
  "items": [
    { "product_id": "p1", "quantity": 2, "price": 29.99 },
    { "product_id": "p2", "quantity": 1, "price": 49.99 }
  ]
}
```

**Avoid embedding when:** the embedded array grows unbounded, the embedded data is updated independently, or multiple parent documents share the same embedded data and consistency matters.

### Referencing Patterns

**One-to-many: Store reference in child**
```json
// comments collection
{ "comment_id": "c1", "post_id": "p100", "text": "Great post" }
{ "comment_id": "c2", "post_id": "p100", "text": "Thanks" }
```

**Many-to-many: Reference arrays on both sides (or one side)**
```json
// students collection
{ "student_id": "s1", "course_ids": ["c1", "c2"] }
// courses collection
{ "course_id": "c1", "student_ids": ["s1", "s3"] }
```

Maintain reference arrays on the side that is queried more frequently. Accept eventual consistency between the two sides, or enforce consistency at the application layer.

### Extended Reference Pattern

Store a subset of referenced data to avoid frequent lookups:

```json
{
  "order_id": "o456",
  "customer": {
    "customer_id": "u123",
    "name": "Alice",
    "email": "alice@example.com"
  }
}
```

Use when the referenced fields rarely change and are always needed with the parent document. Accept that updates to the source require propagation to all extended references.

## Key-Value Design

Key-value stores (Redis, DynamoDB in KV mode, etcd) provide fast lookups by key. All design effort goes into key structure.

### Key Design Principles

- Use hierarchical, delimited keys: `user:{user_id}:profile`, `order:{order_id}:items`
- Include entity type as prefix for namespace isolation
- Use consistent delimiters (`:` is conventional)
- Keep keys short -- they are stored with every entry

### Common Patterns

| Pattern | Key Structure | Value |
| --- | --- | --- |
| Entity lookup | `user:{id}` | Serialized entity |
| One-to-many | `user:{id}:orders` | List/set of order IDs |
| Counter | `page:{url}:views` | Integer |
| Session | `session:{token}` | Session data with TTL |
| Cache-aside | `cache:{entity}:{id}` | Cached query result with TTL |

## Column-Family Patterns

Column-family stores (Cassandra, HBase, ScyllaDB) optimize for write-heavy, time-series, and wide-row workloads.

### Design Principles

- **Query-first design**: Define all queries before designing tables; create one table per query pattern
- **Denormalize aggressively**: Joins do not exist; duplicate data across tables optimized for different queries
- **Partition key selection**: Choose partition keys that distribute data evenly and avoid hotspots; time-based keys create hotspots unless bucketed
- **Clustering columns**: Define sort order within a partition for range queries

### Time-Series Pattern

```cql
CREATE TABLE sensor_readings (
    sensor_id TEXT,
    bucket TEXT,        -- e.g., '2025-03' for monthly bucketing
    recorded_at TIMESTAMP,
    value DOUBLE,
    PRIMARY KEY ((sensor_id, bucket), recorded_at)
) WITH CLUSTERING ORDER BY (recorded_at DESC);
```

Bucketing prevents unbounded partition growth. Choose bucket granularity based on write volume and query time ranges.

## Graph Modeling

Graph databases (Neo4j, Amazon Neptune, ArangoDB) model entities as nodes and relationships as edges. Best suited for domains where relationships are first-class citizens.

### When to Use Graph Modeling

- Queries involve variable-depth traversals (e.g., "friends of friends within 3 hops")
- Relationship types or properties are as important as entity properties
- Schema includes many-to-many relationships with attributes on the relationship itself
- Path-finding, centrality, or pattern matching are core operations

### Design Principles

- **Nodes**: Represent entities with labels (`:User`, `:Product`) and properties
- **Edges**: Represent relationships with types (`:PURCHASED`, `:FOLLOWS`) and properties (timestamp, weight)
- **Direction**: Model edges as directed; query in either direction
- **Avoid supernodes**: Nodes with millions of edges degrade traversal performance; partition or categorize edges

### Common Graph Patterns

| Pattern | Structure | Use Case |
| --- | --- | --- |
| Social graph | `(User)-[:FOLLOWS]->(User)` | Social networks, influence analysis |
| Access control | `(User)-[:MEMBER_OF]->(Group)-[:HAS_ACCESS]->(Resource)` | Authorization, RBAC |
| Recommendation | `(User)-[:PURCHASED]->(Product)<-[:PURCHASED]-(User)` | Collaborative filtering |
| Knowledge graph | `(Entity)-[:RELATED_TO {type}]->(Entity)` | Semantic search, ontologies |

## Denormalization Strategies

Controlled denormalization trades write complexity for read performance. Apply deliberately, not by default.

### When to Denormalize

- Read-to-write ratio exceeds 10:1 for the affected queries
- Join queries span multiple partitions or collections
- Latency requirements cannot be met with normalized access
- Data is append-mostly (historical records, logs, events)

### Denormalization Techniques

| Technique | Mechanism | Trade-off |
| --- | --- | --- |
| **Materialized view** | Precomputed query result stored as a table | Stale reads unless refreshed; storage cost |
| **Summary table** | Aggregated data updated on write | Write amplification; eventual consistency |
| **Embedded copy** | Snapshot of related data in parent | Propagation on source update |
| **Computed column** | Derived value stored alongside source | Must be kept in sync on update |

### Consistency Management

When denormalized copies exist:

1. Identify the single source of truth for each piece of data
2. Update copies synchronously (in the same transaction) or asynchronously (via events/CDC)
3. Monitor for drift between source and copies
4. Document which data is denormalized and where copies live
