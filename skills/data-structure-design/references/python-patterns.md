# Python Representation Patterns

Python idioms for the Representation Design Pass: sum types, newtypes, smart constructors, boundary parsing, state machines, immutability. Load only when the project language is Python. Back to [SKILL.md](../SKILL.md).

## Sum Types: Union of Frozen Dataclasses

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

**Corrected — one frozen dataclass per legal state:**

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

**Exhaustiveness** — close every `match` with `assert_never` so type checkers flag a newly added variant at every consumption site:

```python
from typing import assert_never

def describe(job: Job) -> str:
    match job:
        case Pending():
            return "queued"
        case Running(started_at=t):
            return f"running since {t}"
        case Done():
            return "finished"
        case Failed(error=e):
            return e
        case _:
            assert_never(job)
```

## Closed Option Sets: Enum and Literal

- `Literal["asc", "desc"]` — lightweight, zero-runtime closed set for a function parameter or a field with no behavior
- `enum.Enum` / `enum.StrEnum` — when the set carries behavior, needs iteration, or crosses a serialization boundary (`StrEnum` round-trips as its string value)
- Never a bare `str` compared against literals scattered through the code — that is stringly-typed at the call-site level even when the values happen to be consistent

## Newtypes: `NewType` vs Wrapper Dataclass

Decision guide:

| Mechanism | Runtime cost | Validation | Use when |
| --- | --- | --- | --- |
| `typing.NewType("AccountId", str)` | zero — checker-only | none | two same-repr values must not be interchanged, and validity is guaranteed elsewhere |
| `@dataclass(frozen=True)` wrapper with `__post_init__` | one object | at construction | the value has rules (`Email`, `Money`, `PositiveInt`) |
| `Annotated[str, Field(pattern=...)]` (pydantic) | at parse | at the boundary | the constraint only matters at the wire edge |

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

`def transfer(source: AccountId, target: AccountId, amount: Money)` still permits swapped source/target (same type); when that matters, introduce distinct types or a keyword-only signature (`*, source: ..., target: ...`).

## Smart Constructors

The wrapper carries the proof; the constructor is the only door.

```python
@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:      # constructor IS the validator
        if "@" not in self.value:
            raise ValueError(f"not an email: {self.value!r}")

# Result-style alternative when failure is an expected domain case, not a caller bug:
def parse_email(raw: str) -> Email | None: ...
```

Rule of thumb: raise where malformed input is a programming error at an internal call site; return `None`/a result type where malformed input is an expected case the caller must handle (user input, external data).

## Parse, Don't Validate: pydantic at the Boundary

**Failure shape — shotgun parsing:** the handler deserializes to `dict`, passes it down, and each layer does its own `.get("user", {}).get("email")` with its own defaults.

**Corrected — wire model at the edge, domain types inside:**

```python
class CreateUserRequest(BaseModel):       # wire shape: exactly what arrives
    email: str
    display_name: str = Field(min_length=1, max_length=80)

def handle_create_user(raw: bytes) -> UserId:
    req = CreateUserRequest.model_validate_json(raw)   # parse ONCE, fail here
    user = User(email=Email(req.email), name=DisplayName(req.display_name))
    return user_service.create(user)      # interior sees only domain types
```

- The wire type and the domain type are allowed to differ — parsing is exactly where one becomes the other. This is also the seam with the `data-modeling` skill: a stored row is parsed into a domain type at the repository boundary the same way
- `TypedDict` describes a dict's shape to the checker but validates nothing at runtime — fine for annotating trusted internal dicts, never a substitute for boundary parsing
- Beyond the boundary, no `dict[str, Any]` in signatures: if a function accepts one deep in the interior, the parse happened too late

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

## Immutability Defaults

- `@dataclass(frozen=True, slots=True)` for value types — `slots` also blocks accidental attribute injection
- `tuple[...]` over `list[...]` inside value types; `Mapping`/`Sequence` (not `dict`/`list`) in signatures that must not mutate their input
- Mutation is a design event: it belongs on entities, behind the owning module's surface, never on values passed across boundaries

## Python-Specific Gotchas

- **Mutable default arguments** (`def f(items: list = [])`) — the classic shared-mutable-state trap; use `None` + guard, or `field(default_factory=list)` in dataclasses
- **`Optional` creep** — a field made `| None` "for flexibility" is a nullable whose legality rules will end up in comments; ask whether the `None` case is a distinct *state* that belongs in a sum type
- **Boolean parameters** at call sites (`render(True, False)`) — replace with `Literal`/`Enum` parameters or keyword-only arguments; two bools whose combinations include an illegal one are a sum type in disguise
- **Type hints enforce nothing at runtime** — Python's checker-only types mean every invariant needs either a validating constructor or a boundary parse; a hint alone is documentation
