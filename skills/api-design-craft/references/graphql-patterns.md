# GraphQL Patterns

GraphQL quality guidance — the taste layer above `api-design`'s methodology. This file covers when GraphQL is the right choice and what a well-designed GraphQL API looks like. Back to [SKILL.md](../SKILL.md).

## When GraphQL Is the Right Choice

GraphQL is not "better REST." It solves specific problems. Choose it when:

**Client-driven field selection is the actual bottleneck.** Many consumers with different data needs; REST endpoints return too much or too little for different clients. GraphQL's field selection eliminates over-fetch at the API level.

**N+1 round-trip elimination is needed.** Deeply nested data where the client needs to make multiple REST calls to assemble one view. GraphQL can resolve the full tree in one query.

**Many consumers with varying shapes.** Mobile app, web app, and internal tooling all need different field subsets. A single REST endpoint that satisfies all of them would be massively over-fetched for each.

Do NOT choose GraphQL when:
- REST would work fine and you're choosing GraphQL to "be modern"
- Your team is small and doesn't have GraphQL expertise
- You need aggressive HTTP caching (GraphQL's caching story is more complex)
- Your API is consumed by third-party developers who expect REST (reach matters)

## Schema-First Design with Taste

The GraphQL schema is the contract. Design it with the same rigor as a REST API contract.

**Strong typing**: every field has a type. Use non-nullable (`!`) for fields that are always present; use nullable for optional fields. This is the type system's way of encoding your data guarantees.

```graphql
# Good: types encode the contract
type Order {
  id: ID!                    # always present
  customer: Customer!        # always present
  items: [OrderItem!]!       # always present, items non-null
  status: OrderStatus!       # always present
  cancelledAt: DateTime      # nullable: only present when cancelled
  cancelReason: String       # nullable: only present when cancelled
}

# Bad: everything nullable hides the contract
type Order {
  id: ID
  customer: Customer
  items: [OrderItem]
  status: String
}
```

**Consistent mutation patterns**:

```graphql
# Good: consistent input/payload pattern
type Mutation {
  createOrder(input: CreateOrderInput!): CreateOrderPayload!
  cancelOrder(input: CancelOrderInput!): CancelOrderPayload!
}

input CreateOrderInput {
  customerId: ID!
  items: [OrderItemInput!]!
}

type CreateOrderPayload {
  order: Order
  errors: [UserError!]!
}
```

## Relay Connections — The Standard Pagination Shape

Use the Relay Connection spec for all list fields. This is the correct default for GraphQL pagination.

```graphql
type Query {
  orders(
    first: Int          # forward pagination: return first N items
    after: String       # cursor: return items after this cursor
    last: Int           # backward pagination
    before: String      # cursor for backward pagination
    filter: OrderFilter
  ): OrderConnection!
}

type OrderConnection {
  edges: [OrderEdge]!
  pageInfo: PageInfo!
  totalCount: Int!       # total matching records (for UI: "showing 1-20 of 847")
}

type OrderEdge {
  node: Order!
  cursor: String!        # opaque cursor for this item's position
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
```

The `totalCount` field is not in the core Relay spec but is universally needed. Add it.

## Errors in the Type System

The Linear pattern: `union { Success | Error }` return types from mutations. This is better than:
- HTTP error codes (not a thing in GraphQL over a single HTTP endpoint)
- Exceptions only (can't type-check failure modes)
- `errors` field on the root payload (coerces callers to check nulls on both)

```graphql
# Good: typed error union
type CreateOrderPayload {
  result: CreateOrderResult!
}

union CreateOrderResult = Order | ValidationError | InventoryError

type ValidationError {
  message: String!
  fields: [FieldError!]!
}

type InventoryError {
  message: String!
  unavailableItems: [String!]!
}

# Calling code pattern-matches on type:
# ... on Order { id, status }
# ... on ValidationError { fields { field, message } }
# ... on InventoryError { unavailableItems }
```

Also include a top-level `errors` array for system errors (network, auth, internal) — this is the GraphQL spec's built-in error mechanism.

## DataLoader — N+1 Is a Schema Design Problem

The schema structure encourages N+1 resolution (fetching a list, then for each item fetching a related resource). The execution layer must batch-load related data.

Rule: **never resolve a list field without a DataLoader or equivalent batching mechanism behind it.**

```javascript
// Bad: N+1 queries
// Resolving customer for 20 orders = 20 database queries
Order.customer = (order) => db.customers.findById(order.customerId)

// Good: DataLoader batches
const customerLoader = new DataLoader(async (customerIds) => {
  const customers = await db.customers.findManyByIds(customerIds)
  return customerIds.map(id => customers.find(c => c.id === id))
})

Order.customer = (order) => customerLoader.load(order.customerId)
// DataLoader batches all customer IDs from the current request into one query
```

This is an implementation concern, but it starts with API design: if your schema encourages loading nested data, you must plan for DataLoader.

## Subscriptions

Use subscriptions for real-time updates that must be pushed from server to client. Don't use polling when subscriptions are available.

Subscription design rules:
- Subscribe to specific events, not entire resource state
- Filter subscriptions at the server side (not all events to all subscribers)
- Handle client reconnection gracefully (resume from last event)
- Design the payload as the minimal event, not the full resource state

```graphql
type Subscription {
  orderStatusChanged(orderId: ID!): OrderStatusChangedEvent!
}

type OrderStatusChangedEvent {
  order: Order!
  previousStatus: OrderStatus!
  newStatus: OrderStatus!
  changedAt: DateTime!
}
```

## Application-Layer Caching

HTTP caching doesn't work well with GraphQL's default POST-all-queries approach. Caching strategies:

**Persisted queries**: hash queries on the client side, send only the hash, execute the full query at the hash on the server. Allows CDN caching of GET requests (hash → result). Apollo, Relay, and most major frameworks support this.

**Response normalization** (Apollo Client, Relay): cache objects by their `id` field in a normalized store. Cache hits are at the object level, not the query level.

**Field-level caching**: `@cacheControl` directive (Apollo) to specify per-field or per-type max age.

For most projects: normalized client-side cache + persisted queries for high-traffic scenarios. Full response caching is rarely worth the complexity.

## Cross-Reference: Methodology

This file covers the quality/taste layer. For the step-by-step process of designing a GraphQL schema, writing the schema file, and setting up type-checking — see `api-design/references/graphql-patterns.md` (the methodology layer).

Both files are named `graphql-patterns.md` but serve different purposes: the `api-design` one is about building; this one is about quality.
