# gRPC Patterns

gRPC quality guidance — when to use it and what a well-designed gRPC API looks like. This is one of the least-documented areas in Praxion's skill set. Back to [SKILL.md](../SKILL.md).

## When gRPC Is the Right Choice

gRPC solves specific problems. Choose it when:

**Internal service-to-service communication.** gRPC is not designed for public-facing APIs or third-party consumption. It excels at internal microservice communication where you control both sides.

**High-throughput or streaming.** The ~25ms median latency (vs ~250ms for REST) matters at scale. Bidirectional streaming is native.

**Schema enforcement is required.** Protobuf schemas are always required — there is no optional schema like OpenAPI for REST. This is a feature: schema drift is impossible.

**Bidirectional streaming.** gRPC's bidirectional streaming mode has no equivalent in REST (SSE is server-to-client only; WebSocket is protocol-level, not schema-enforced).

Do NOT choose gRPC when:
- The consumers are browsers (gRPC-web proxy required — adds complexity)
- The consumers are third-party developers who expect REST
- The team lacks Protobuf toolchain experience
- Caching is important (gRPC over HTTP/2 doesn't have HTTP caching semantics)

## Protobuf Schema Design with Taste

The Protobuf schema is the API contract. Design it with the same discipline as an OpenAPI schema.

### Message Naming

Clear, singular nouns for messages (same principle as REST resource naming):

```protobuf
// Good
message Order {}
message CreateOrderRequest {}
message CreateOrderResponse {}
message ListOrdersRequest {}
message ListOrdersResponse {}

// Bad
message OrderData {}          // "Data" suffix adds nothing
message GetOrder {}           // Mixing verbs and nouns
message OrdersList {}         // Plural on a message, not a field
```

### Field Numbering — Never Renumber

Field numbers are wire-format identifiers. They are permanent.

Rules:
- **Never renumber fields.** Changing a field number breaks all existing serialized data.
- **Never reuse field numbers.** Once a number is used for a field (even if the field is removed), that number is retired.
- **Reserve removed field numbers.** Use `reserved` to prevent accidental reuse:

```protobuf
message Order {
  reserved 3, 5;             // These numbers were removed; never reuse them
  reserved "old_field_name"; // Also reserve old names to prevent reuse

  uint64 id = 1;
  string customer_id = 2;
  // field 3 was removed (reserved)
  repeated OrderItem items = 4;
  // field 5 was removed (reserved)
  OrderStatus status = 6;
}
```

### Additive-Only Changes

Forward and backward compatibility requires additive-only changes within a major version:

**Safe changes:**
- Add new fields with new field numbers
- Add new enum values
- Add new RPC methods

**Breaking changes (require major version bump):**
- Remove or rename fields (even if reserved)
- Change a field's type
- Change a field number
- Remove RPC methods
- Change RPC method signatures

### `FieldMask` for Sparse Fieldsets

For update operations and selective reads, use `google.protobuf.FieldMask`:

```protobuf
message UpdateOrderRequest {
  Order order = 1;
  google.protobuf.FieldMask update_mask = 2;  // which fields to update
}
```

Client specifies exactly which fields to update:
```
update_mask.paths = ["status", "estimated_ship_date"]
```

This is the gRPC equivalent of JSON Merge Patch — partial updates without replacing the entire resource. Required for any mutable resource.

## Streaming Modes

| Mode | Use case | Pattern |
|------|----------|---------|
| **Unary** | Standard request-response | Most RPCs |
| **Server streaming** | Server sends multiple responses; client reads stream | Large data exports, log streaming, real-time updates |
| **Client streaming** | Client sends multiple requests; server aggregates | Bulk uploads, chunked file transfers |
| **Bidirectional streaming** | Full-duplex real-time | Chat, collaborative editing, game state sync |

```protobuf
service OrderService {
  // Unary: single request, single response
  rpc GetOrder(GetOrderRequest) returns (Order);

  // Server streaming: single request, stream of responses
  rpc StreamOrderEvents(StreamOrderEventsRequest) returns (stream OrderEvent);

  // Bidirectional streaming: both sides stream
  rpc TrackShipment(stream ShipmentUpdate) returns (stream ShipmentStatus);
}
```

## Google AIP Resource-Oriented Design

The [Google API Improvement Proposals (AIP)](https://aip.dev) provide resource-oriented design patterns for RPC APIs. They are worth following when designing large gRPC APIs.

**Standard methods** (same as REST but in RPC form):

| Method | HTTP equivalent | Signature |
|--------|----------------|-----------|
| `GetOrder` | `GET /orders/{id}` | `(GetOrderRequest) → Order` |
| `ListOrders` | `GET /orders` | `(ListOrdersRequest) → ListOrdersResponse` |
| `CreateOrder` | `POST /orders` | `(CreateOrderRequest) → Order` |
| `UpdateOrder` | `PATCH /orders/{id}` | `(UpdateOrderRequest) → Order` |
| `DeleteOrder` | `DELETE /orders/{id}` | `(DeleteOrderRequest) → google.protobuf.Empty` |

**Custom methods** for operations that don't fit the standard model:
```protobuf
rpc CancelOrder(CancelOrderRequest) returns (Order);
rpc BatchGetOrders(BatchGetOrdersRequest) returns (BatchGetOrdersResponse);
```

**Long-running operations**: the AIP pattern uses `google.longrunning.Operation`:
```protobuf
rpc ExportOrders(ExportOrdersRequest) returns (google.longrunning.Operation);
// Operation metadata typed to ExportOrdersMetadata
// Operation result typed to ExportOrdersResponse
```

## Channels and Connection Pooling

gRPC channels are persistent TCP connections. Design for connection reuse:

- One channel per service is the default pattern for most use cases
- Pool channels for high-throughput services (multiple channels in a pool)
- Configure `keepalive_time_ms` and `keepalive_timeout_ms` for long-lived connections
- gRPC's HTTP/2 multiplexing means multiple concurrent RPCs on one channel — don't create a channel per RPC call

## Browser Caveat

gRPC is not natively browser-friendly. HTTP/2 with binary framing requires a gRPC-web proxy (Envoy is the standard choice) to translate between browser-compatible HTTP/1.1 requests and gRPC's binary protocol.

If browser support is required:
1. Deploy an Envoy gRPC-web proxy
2. Or consider using REST (or GraphQL) for the public-facing layer, gRPC for internal services

## Tooling Reality

gRPC tooling is less mature than REST:

- `grpcurl` — curl for gRPC (CLI testing)
- `Evans` — interactive gRPC client
- Reflection must be enabled on the server for these tools to work without Protobuf files
- IDE support (Postman, Insomnia) exists but is less integrated than REST tooling
- Documentation generation requires dedicated tools (grpc-gateway Swagger generation, buf.build)

Factor tooling maturity into the choice — a REST API that your operations team can debug with curl may be better than a gRPC API they need specialized tooling to interact with.
