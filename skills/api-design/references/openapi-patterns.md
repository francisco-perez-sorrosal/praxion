# OpenAPI 3.1 Specification Patterns

Patterns and conventions for writing effective OpenAPI 3.1 specifications. OpenAPI 3.1 aligns fully with JSON Schema Draft 2020-12, enabling richer schema composition and validation.

## Document Structure

Organize OpenAPI documents with this top-level structure:

```yaml
openapi: "3.1.0"
info:
  title: Service Name API
  version: "1.0.0"
  description: Brief description of what this API does

servers:
  - url: https://api.example.com/v1
    description: Production
  - url: https://api.staging.example.com/v1
    description: Staging

paths:
  # Endpoint definitions

components:
  schemas:
    # Reusable data models
  parameters:
    # Reusable parameters
  responses:
    # Reusable response definitions
  securitySchemes:
    # Authentication mechanisms
```

Keep `info.description` concise -- one or two sentences about the API's purpose. Use `servers` to declare all environments consumers might target.

## Schema Design

### Define Schemas Globally

Place all schemas in `components/schemas` with descriptive names. Reference them with `$ref` throughout the spec. Avoid inline schema definitions -- they produce poor names in code generators and create duplication.

```yaml
components:
  schemas:
    User:
      type: object
      required: [id, email, created_at]
      properties:
        id:
          type: string
          format: uuid
          description: Unique identifier
          examples: ["550e8400-e29b-41d4-a716-446655440000"]
        email:
          type: string
          format: email
        display_name:
          type: string
          maxLength: 100
        role:
          $ref: "#/components/schemas/UserRole"
        created_at:
          type: string
          format: date-time

    UserRole:
      type: string
      enum: [admin, member, viewer]
      description: Access level assigned to the user
```

### Schema Composition

Use `allOf`, `oneOf`, and `anyOf` for schema composition:

- **`allOf`** -- combine base schemas (inheritance/extension). Use for shared fields across request and response variants.
- **`oneOf`** -- exactly one schema matches (discriminated unions). Use for polymorphic types with a `discriminator`.
- **`anyOf`** -- at least one schema matches. Use sparingly -- `oneOf` is usually more precise.

```yaml
# Base + extension pattern
OrderResponse:
  allOf:
    - $ref: "#/components/schemas/OrderBase"
    - type: object
      required: [id, status, created_at]
      properties:
        id:
          type: string
          format: uuid
        status:
          $ref: "#/components/schemas/OrderStatus"
        created_at:
          type: string
          format: date-time

# Discriminated union pattern
PaymentMethod:
  oneOf:
    - $ref: "#/components/schemas/CreditCard"
    - $ref: "#/components/schemas/BankTransfer"
    - $ref: "#/components/schemas/DigitalWallet"
  discriminator:
    propertyName: type
    mapping:
      credit_card: "#/components/schemas/CreditCard"
      bank_transfer: "#/components/schemas/BankTransfer"
      digital_wallet: "#/components/schemas/DigitalWallet"
```

### Separate Create/Update/Response Schemas

Define distinct schemas for different operations on the same resource:

- **`UserCreate`** -- fields the client sends when creating (no `id`, no `created_at`)
- **`UserUpdate`** -- fields the client may modify (all optional for PATCH)
- **`UserResponse`** -- full representation returned to the client (includes server-generated fields)

This prevents consumers from sending fields the server ignores and clarifies which fields are writable versus read-only.

## Endpoint Design

### Path and Operation Patterns

```yaml
paths:
  /users:
    get:
      summary: List users
      operationId: listUsers
      tags: [Users]
      parameters:
        - $ref: "#/components/parameters/PageCursor"
        - $ref: "#/components/parameters/PageLimit"
        - name: status
          in: query
          schema:
            $ref: "#/components/schemas/UserStatus"
      responses:
        "200":
          description: Paginated list of users
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserListResponse"
    post:
      summary: Create a user
      operationId: createUser
      tags: [Users]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UserCreate"
            examples:
              basic:
                summary: Minimal user creation
                value:
                  email: "user@example.com"
                  display_name: "Jane Doe"
      responses:
        "201":
          description: User created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserResponse"
        "422":
          $ref: "#/components/responses/ValidationError"
```

### Reusable Components

Extract common parameters, responses, and headers into `components`:

```yaml
components:
  parameters:
    PageCursor:
      name: cursor
      in: query
      description: Pagination cursor from a previous response
      schema:
        type: string
    PageLimit:
      name: limit
      in: query
      description: Maximum items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20

  responses:
    ValidationError:
      description: Request validation failed
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/ErrorResponse"
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/ErrorResponse"
```

## Security Schemes

Define authentication at the component level and apply globally or per-operation:

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
    OAuth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.example.com/authorize
          tokenUrl: https://auth.example.com/token
          scopes:
            read:users: Read user data
            write:users: Modify user data

# Apply globally
security:
  - BearerAuth: []
```

Override security per-operation when an endpoint has different requirements (e.g., public endpoints use `security: []`).

## Specification Quality Checklist

- [ ] All schemas defined in `components/schemas` with `$ref` usage -- no inline schemas
- [ ] Every schema has `description` on non-obvious fields
- [ ] `required` arrays present on all object schemas
- [ ] `format` specified for strings (date-time, email, uuid, uri)
- [ ] Numeric constraints applied (`minimum`, `maximum`, `multipleOf`)
- [ ] String constraints applied where relevant (`maxLength`, `pattern`)
- [ ] `examples` provided for every request body and non-trivial response
- [ ] `operationId` set on every operation (required for code generation)
- [ ] `tags` applied to group related endpoints
- [ ] Error responses defined for all applicable status codes (400, 401, 403, 404, 422, 500)
- [ ] Pagination parameters reused from `components/parameters`
- [ ] Security schemes defined and applied
