# Representation Patterns

Worked techniques from the Representation Design Pass, in Praxion's primary target languages (Python, TypeScript). Each pattern shows the failure shape first, then the corrected representation. Back to [SKILL.md](../SKILL.md).

## Sum Types: Model the Legal States Only

**Failure shape — correlated nullables (product type):**

```python
@dataclass
class Job:
    status: str                       # "pending" | "running" | "done" | "failed"... hopefully
    started_at: datetime | None       # must be set iff status != "pending"
    result: bytes | None              # must be set iff status == "done"
    error: str | None                 # must be set iff status == "failed"
```

Four fields, each independently optional: dozens of representable combinations, four legal ones. The legality rules live in comments; every consumer defends or trusts.

**Corrected — one type per legal state:**

```python
@dataclass(frozen=True)
class Pending:
    pass

@dataclass(frozen=True)
class Running:
    started_at: datetime

@dataclass(frozen=True)
class Done:
    started_at: datetime
    result: bytes

@dataclass(frozen=True)
class Failed:
    started_at: datetime
    error: str

Job = Pending | Running | Done | Failed
```

A `Done` without a `result` is now unconstructible. Transitions become functions between state types (`start(j: Pending) -> Running`), so an illegal transition has no signature.

**TypeScript — discriminated union with exhaustiveness:**

```typescript
type Job =
  | { kind: "pending" }
  | { kind: "running"; startedAt: Date }
  | { kind: "done"; startedAt: Date; result: Uint8Array }
  | { kind: "failed"; startedAt: Date; error: string };

function describe(job: Job): string {
  switch (job.kind) {
    case "pending": return "queued";
    case "running": return `running since ${job.startedAt}`;
    case "done": return "finished";
    case "failed": return job.error;
    default: {
      const unreachable: never = job;   // compile error when a variant is added
      return unreachable;
    }
  }
}
```

Python's equivalent exhaustiveness guard: `typing.assert_never(job)` in the final `case _:` of a `match` — type checkers flag missing variants.

## Newtypes: Give Primitives Domain Identity

**Failure shape — swappable same-typed arguments:**

```python
def transfer(from_account: str, to_account: str, amount: float) -> None: ...
transfer(target, source, -50.0)   # type-checks; wrong in three ways
```

**Corrected — Python (`NewType` for zero-cost distinction, dataclass when validation is needed):**

```python
from typing import NewType

AccountId = NewType("AccountId", str)     # distinct to the type checker, free at runtime

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Money amount must be non-negative")
```

**Corrected — TypeScript (branded types; structural typing needs the brand):**

```typescript
type AccountId = string & { readonly __brand: "AccountId" };
type OrderId = string & { readonly __brand: "OrderId" };

function accountId(raw: string): AccountId {
  if (!/^acc_[a-z0-9]{12}$/.test(raw)) throw new Error(`invalid account id: ${raw}`);
  return raw as AccountId;              // the single sanctioned cast, here only
}
```

An `OrderId` passed where an `AccountId` is expected is now a compile error, though both are strings underneath.

## Smart Constructors: Validation as the Only Door

The newtype carries the proof; the smart constructor is the only way to obtain it. Do not export the raw constructor.

```python
@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:      # dataclass path: constructor IS the validator
        if "@" not in self.value:
            raise ValueError(f"not an email: {self.value!r}")

# Result-style alternative when failure is expected and handled, not exceptional:
def parse_email(raw: str) -> Email | None: ...
```

```typescript
// Export the type and the parse function; never the cast.
export type Email = string & { readonly __brand: "Email" };
export function parseEmail(raw: string): Email | null {
  return raw.includes("@") ? (raw as Email) : null;
}
```

Rule of thumb: raise/throw at boundaries where malformed input is a caller bug; return `Result`/`Option`/`null` where malformed input is an expected domain case the caller must handle.

## Parse, Don't Validate: One Boundary, One Conversion

**Failure shape — shotgun parsing:** the handler deserializes to `dict`/`any`, passes it down, and each layer does its own `.get("user", {}).get("email")` with its own defaults.

**Corrected — Python (pydantic at the boundary, domain types inside):**

```python
class CreateUserRequest(BaseModel):       # wire shape: exactly what arrives
    email: str
    display_name: str = Field(min_length=1, max_length=80)

def handle_create_user(raw: bytes) -> UserId:
    req = CreateUserRequest.model_validate_json(raw)   # parse ONCE, fail here
    user = User(email=Email(req.email), name=DisplayName(req.display_name))
    return user_service.create(user)      # interior sees only domain types
```

**Corrected — TypeScript (zod or equivalent):**

```typescript
const CreateUserRequest = z.object({
  email: z.string().email(),
  displayName: z.string().min(1).max(80),
});
type CreateUserRequest = z.infer<typeof CreateUserRequest>;

// handler: CreateUserRequest.parse(json) — beyond this line, no `any`, no re-checks
```

The wire type and the domain type are allowed to differ — parsing is exactly the place where one becomes the other. This is also the seam where this skill hands off to `data-modeling`: a stored row is parsed into a domain type at the repository boundary the same way a request body is at the HTTP boundary.

## State Machines: Transitions as the API

When phases carry different data AND transitions are constrained, expose transitions — not setters:

```python
@dataclass(frozen=True)
class DraftOrder:
    items: tuple[LineItem, ...]

    def submit(self, payment: PaymentMethod) -> "SubmittedOrder":
        if not self.items:
            raise ValueError("cannot submit an empty order")
        return SubmittedOrder(items=self.items, payment=payment, submitted_at=now())

@dataclass(frozen=True)
class SubmittedOrder:
    items: tuple[LineItem, ...]
    payment: PaymentMethod
    submitted_at: datetime
    # no .submit() — submitting twice has no representation
```

Each state type offers only the operations legal in that state. The state diagram and the API are the same artifact.

## Immutable Values by Default

- Python: `@dataclass(frozen=True)`, tuples over lists in value types, `Mapping` over `dict` in signatures that must not mutate
- TypeScript: `readonly` fields, `ReadonlyArray<T>`, `as const` for literal shapes
- Mutation is a design event: it belongs on entities, behind the owning module's surface, never on values passed across boundaries

## Agent-Tool Schema Shapes

The same pass applied to a JSON-schema contract whose consumer is a model:

```json
{
  "name": "get_customer_orders",
  "input_schema": {
    "type": "object",
    "properties": {
      "customer_id": { "type": "string", "description": "Customer ID, format cus_XXX" },
      "status": { "type": "string", "enum": ["pending", "shipped", "delivered"] },
      "page_size": { "type": "integer", "minimum": 1, "maximum": 20, "default": 10 }
    },
    "required": ["customer_id"]
  }
}
```

- `customer_id`, not `id` or `customer` — the name is the newtype
- `enum` for the closed set — the schema-level sum type (a bare `"type": "string"` status is stringly-typed at the contract level)
- Bounded pagination with a default — the schema encodes the invariant instead of trusting the caller
- Error responses are shaped and actionable ("status must be one of pending|shipped|delivered"), because the error contract steers retry behavior
