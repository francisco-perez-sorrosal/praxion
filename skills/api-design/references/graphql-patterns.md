# GraphQL Schema Design Patterns

Patterns for designing maintainable GraphQL schemas. Covers type system conventions, query/mutation design, error handling, and federation basics for microservices.

## Schema Structure

Organize the schema with clear separation between types, queries, mutations, and subscriptions:

```graphql
type Query {
  user(id: ID!): User
  users(filter: UserFilter, pagination: PaginationInput): UserConnection!
}

type Mutation {
  createUser(input: CreateUserInput!): CreateUserPayload!
  updateUser(id: ID!, input: UpdateUserInput!): UpdateUserPayload!
  deleteUser(id: ID!): DeleteUserPayload!
}

type Subscription {
  orderStatusChanged(orderId: ID!): OrderStatusEvent!
}
```

## Type Design

### Naming Conventions

- **Types**: PascalCase nouns -- `User`, `OrderItem`, `PaymentMethod`
- **Fields**: camelCase -- `firstName`, `createdAt`, `orderItems`
- **Enums**: PascalCase type, SCREAMING_SNAKE_CASE values -- `enum UserRole { ADMIN, MEMBER, VIEWER }`
- **Inputs**: suffix with `Input` -- `CreateUserInput`, `UserFilter`
- **Payloads**: suffix with `Payload` -- `CreateUserPayload`, `DeleteUserPayload`

### Use Non-Nullable by Default

Mark fields as non-nullable (`!`) unless there is a specific reason the field can be null. Nullable fields should represent genuinely optional data, not implementation laziness.

```graphql
type User {
  id: ID!
  email: String!
  displayName: String!
  bio: String          # Genuinely optional
  avatarUrl: String    # Genuinely optional
  createdAt: DateTime!
}
```

### Custom Scalars

Define custom scalars for domain-specific types that need consistent validation and serialization:

```graphql
scalar DateTime    # ISO 8601 date-time
scalar Email       # RFC 5322 email
scalar URL         # RFC 3986 URI
scalar UUID        # RFC 4122 UUID
```

Document the expected format for each custom scalar in the schema description.

## Query Patterns

### Connection Pattern for Pagination

Use the Relay connection specification for cursor-based pagination:

```graphql
type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type UserEdge {
  node: User!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}

input PaginationInput {
  first: Int
  after: String
  last: Int
  before: String
}
```

Apply the connection pattern to every list that can grow beyond a trivial size. Use simple lists (`[Item!]!`) only for bounded, small collections (enum-like data, configuration items).

### Filtering

Accept filter inputs as structured objects rather than individual arguments:

```graphql
input UserFilter {
  status: UserStatus
  role: UserRole
  createdAfter: DateTime
  searchTerm: String
}
```

## Mutation Patterns

### Input/Payload Convention

Wrap all mutation arguments in a single `input` object. Return a dedicated payload type that includes the result and potential errors:

```graphql
input CreateUserInput {
  email: String!
  displayName: String!
  role: UserRole = MEMBER
}

type CreateUserPayload {
  user: User
  errors: [UserError!]!
}

type UserError {
  field: String
  message: String!
  code: ErrorCode!
}
```

This pattern provides a stable mutation signature -- adding optional fields to the input does not break existing consumers.

### Error Handling

Return domain errors in the payload rather than relying solely on GraphQL errors. Reserve GraphQL-level errors for infrastructure problems (authentication failure, rate limiting, server errors).

```graphql
# Domain errors in payload -- the consumer can handle them
type CreateUserPayload {
  user: User
  errors: [UserError!]!     # EMAIL_TAKEN, INVALID_ROLE, etc.
}

# Infrastructure errors -- thrown as GraphQL errors
# 401 Unauthorized, 500 Internal Server Error, etc.
```

## Interface and Union Types

Use interfaces for types that share a common set of fields. Use unions for types that are fundamentally different but appear in the same context.

```graphql
interface Node {
  id: ID!
}

interface Timestamped {
  createdAt: DateTime!
  updatedAt: DateTime!
}

union SearchResult = User | Order | Product
```

Prefer interfaces when types share behavior. Prefer unions when types only share a context (search results, activity feeds).

## Federation Basics

Federation composes multiple GraphQL services (subgraphs) into a single unified API (supergraph). Each subgraph owns specific types and extends types owned by other subgraphs.

### Entity Ownership

An entity is a type that spans multiple subgraphs. One subgraph defines the type; others extend it:

```graphql
# Users subgraph -- defines User
type User @key(fields: "id") {
  id: ID!
  email: String!
  displayName: String!
}

# Orders subgraph -- extends User with order data
type User @key(fields: "id") {
  id: ID!
  orders: [Order!]!
}
```

### Federation Design Rules

- **Single owner per type**: one subgraph owns each entity's core fields. Other subgraphs extend with their domain-specific fields.
- **Key fields**: use simple scalar keys (`id`) where possible. Compound keys add resolver complexity.
- **Minimize cross-subgraph dependencies**: each subgraph should be deployable independently. Avoid circular entity references.
- **Shared types**: define enums and value objects in a shared schema package when multiple subgraphs need them.

### When to Federate

Federate when:
- Multiple teams own different parts of the domain and deploy independently
- The schema has grown beyond what a single team can maintain
- Different parts of the graph have different scaling requirements

Do not federate prematurely -- a monolithic GraphQL server is simpler to operate and sufficient for most projects until team or scale constraints demand separation.

## Schema Evolution

GraphQL schemas evolve through additive changes:

| Change | Safe? | Notes |
|--------|-------|-------|
| Add field | Yes | Existing queries ignore new fields |
| Add optional argument | Yes | Existing queries continue to work |
| Add type/enum value | Yes | But consumers with exhaustive switches may break |
| Deprecate field | Yes | Mark with `@deprecated(reason: "...")` |
| Remove field | No | Breaking -- deprecate first, monitor usage, then remove |
| Make nullable field non-nullable | No | Breaking -- existing data may contain nulls |
| Make non-nullable field nullable | Yes | Consumers already handle the non-null case |
| Rename field | No | Breaking -- add new field, deprecate old, then remove |

Use the `@deprecated` directive with a clear reason and migration path:

```graphql
type User {
  name: String! @deprecated(reason: "Use displayName instead")
  displayName: String!
}
```

## Schema Quality Checklist

- [ ] Non-nullable by default -- only nullable when the field is genuinely optional
- [ ] Connection pattern for all unbounded lists
- [ ] Input/payload convention for all mutations
- [ ] Domain errors in payloads, infrastructure errors as GraphQL errors
- [ ] Custom scalars for domain types (DateTime, Email, UUID)
- [ ] Consistent naming (PascalCase types, camelCase fields, SCREAMING_SNAKE enums)
- [ ] `@deprecated` with reason on all deprecated fields
- [ ] Descriptions on types, fields, and arguments
