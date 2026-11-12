# Python Patterns and Examples

Code patterns and examples for common Python constructs. Reference material for the [Python Development](../SKILL.md) skill.

## Common Patterns

**Dataclasses** for simple data containers:
```python
from dataclasses import dataclass

@dataclass(frozen=True)  # Immutable
class Config:
    host: str
    port: int
    debug: bool = False
```

**Pydantic models** for data validation and parsing:
```python
from pydantic import BaseModel, Field, ConfigDict, field_validator

class UserInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    email: str
    age: int = Field(ge=0, le=150)
    username: str = Field(min_length=3, max_length=50)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower()

# Automatic validation on instantiation
user = UserInput(email="USER@EXAMPLE.COM", age=25, username="john")
# user.email == "user@example.com"
```

**Dataclasses vs Pydantic: When to use each**

Use **dataclasses** when:
- Simple data containers with no validation needs
- Internal data structures within your codebase
- Performance-critical paths (dataclasses have less overhead)
- No need for JSON/dict serialization/deserialization
- Working with pure Python without external dependencies

Use **Pydantic** when:
- Parsing external input (API requests, config files, user input)
- Complex validation rules are required
- Need automatic type coercion (e.g., `"123"` → `123`)
- Serialization to/from JSON or dicts is frequent
- Working with settings/configuration management
- Building APIs (FastAPI integration)

```python
# Example: Combining both approaches
from dataclasses import dataclass
from pydantic import BaseModel

# Pydantic for external input validation
class CreateUserRequest(BaseModel):
    email: str
    username: str
    age: int

# Dataclass for internal domain model
@dataclass(frozen=True)
class User:
    id: int
    email: str
    username: str
    age: int

    @classmethod
    def from_request(cls, user_id: int, request: CreateUserRequest) -> "User":
        return cls(
            id=user_id,
            email=request.email,
            username=request.username,
            age=request.age,
        )
```

**Protocols** for structural typing:
```python
from typing import Protocol

class Serializable(Protocol):
    def to_json(self) -> str: ...

def save(obj: Serializable) -> None:
    data = obj.to_json()
    # ... save data
```

**Literal types lost in comprehensions** (pyright, observed 2026-10-20): a comprehension or generator over `Literal`-typed values is inferred as `str`, and `x in that_set` narrows `x` to `str`, so the result no longer fits a field typed with the `Literal`. Annotating the container (`reasons: set[Reason] = {...}`) and picking with an explicit `for` loop that returns the literal fixes it; `next(gen, default)` does not, because the generator element and the default both widen. When one fix does not stick, run `reveal_type` on a scratch copy to see where the type widens before a second guess.

**Context managers** for resource management:
```python
from contextlib import contextmanager
from typing import Iterator

@contextmanager
def managed_resource(name: str) -> Iterator[Resource]:
    resource = acquire_resource(name)
    try:
        yield resource
    finally:
        resource.cleanup()
```

**Structural pattern matching** (Python 3.10+):
```python
from dataclasses import dataclass

@dataclass
class Command:
    action: str
    name: str = ""

def handle_command(command: Command) -> str:
    match command:
        case Command(action="quit"):
            return "Goodbye"
        case Command(action="greet", name=name):
            return f"Hello, {name}"
        case _:
            return "Unknown command"
```

## Async Patterns

**Basic async/await**:
```python
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

**Async context managers** for resource lifecycle:
```python
@asynccontextmanager
async def managed_connection(url: str) -> AsyncIterator[Connection]:
    conn = await connect(url)
    try:
        yield conn
    finally:
        await conn.close()
```

**Testing**: Use `pytest-asyncio` for async test functions:
```python
import pytest

@pytest.mark.asyncio
async def test_fetch_data():
    result = await fetch_data("https://api.example.com/data")
    assert "id" in result
```

**Common async libraries**: `asyncio` (stdlib), `httpx` (async HTTP client), `aiohttp` (HTTP client/server), `anyio` (structured concurrency).

## Error Handling

**Be explicit** about error conditions:
```python
class InvalidConfigError(ValueError):
    """Raised when configuration is invalid."""
    pass

def load_config(path: str) -> Config:
    if not Path(path).exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        data = parse_config_file(path)
    except ParseError as e:
        raise InvalidConfigError(f"Invalid config format: {e}") from e

    return Config(**data)
```
