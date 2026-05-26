# Refactoring Patterns & Scenarios

Detailed patterns and common refactoring scenarios with full examples. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Refactoring Patterns](#refactoring-patterns)
  - [Extract Module](#extract-module)
  - [Introduce Abstraction](#introduce-abstraction)
  - [Eliminate Circular Dependencies](#eliminate-circular-dependencies)
  - [Extract Data Structure](#extract-data-structure)
  - [Inline Over-Abstraction](#inline-over-abstraction)
- [Common Scenarios](#common-scenarios)
  - [God Object/Module](#god-objectmodule)
  - [Feature Envy](#feature-envy)
  - [Primitive Obsession](#primitive-obsession)
  - [Utils Hell](#utils-hell)
  - [Deep Nesting](#deep-nesting)
- [Dependency Analysis](#dependency-analysis)

## Refactoring Patterns

### Extract Module

**When**: A file or class has multiple responsibilities.

**How**:
1. Identify cohesive groups of functions/methods
2. Create new module for each group
3. Move functions maintaining their signatures
4. Update imports
5. Run tests

### Introduce Abstraction

**When**: Concrete dependencies make code hard to test or change.

**How**:
1. Define Protocol or abstract base class
2. Make dependent code accept the abstraction
3. Keep concrete implementation separate
4. Inject dependency

```python
from typing import Protocol

class Database(Protocol):
    def save(self, order: Order) -> None: ...

class Emailer(Protocol):
    def send(self, recipient: str, message: str) -> None: ...

class OrderProcessor:
    def __init__(self, db: Database, emailer: Emailer):
        self.db = db
        self.emailer = emailer

    def process(self, order: Order) -> None:
        self.db.save(order)
        self.emailer.send(order.customer.email, order.format_message())
```

### Eliminate Circular Dependencies

**When**: Module A imports B, B imports A (or longer cycles).

**How**:
1. Identify the cycle with dependency analysis
2. Extract common dependencies to new module
3. Use dependency inversion (depend on abstractions)
4. Consider if modules should be merged

### Extract Data Structure

**When**: Functions pass many related parameters around.

```python
# Before
def create_user(name: str, email: str, age: int, city: str, country: str) -> User:
    ...

# After
@dataclass(frozen=True)
class UserData:
    name: str
    email: str
    age: int
    city: str
    country: str

def create_user(data: UserData) -> User:
    ...
```

### Inline Over-Abstraction

**When**: Abstraction serves only one use case or adds no value.

**How**:
1. Identify abstractions with single implementation
2. Inline the abstraction
3. Simplify the code
4. Add abstraction back if second use case appears

**Remember**: Abstractions have cost. Only add when multiple concrete cases exist.

## Common Scenarios

### God Object/Module

**Signs**: One class/module doing everything, hundreds of lines, many dependencies.

**Solution**:
1. List all responsibilities
2. Group by cohesion
3. Extract each group to focused module
4. Use composition to reconnect

### Feature Envy

**Signs**: Method uses more data/methods from another class than its own.

**Solution**:
1. Move method to the class it envies
2. Or extract the envied data into its own concept
3. Reduce coupling by passing only needed data

### Primitive Obsession

**Signs**: Using primitives (strings, ints) where domain concepts exist.

**Solution**: Create value object/dataclass for the concept.

```python
# Before
def process_email(email: str) -> None:
    if "@" not in email:
        raise ValueError("Invalid email")
    normalized = email.lower().strip()
    ...

# After
@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError("Invalid email")
        object.__setattr__(self, 'value', self.value.lower().strip())

def process_email(email: Email) -> None:
    ...  # email is guaranteed valid and normalized
```

### Utils Hell

**Signs**: Growing utils module with unrelated functions.

**Solution**:
1. Audit what's actually used
2. Delete unused functions
3. Move functions to domain modules they support
4. Only keep truly generic utilities

### Deep Nesting

**Signs**: Many levels of indentation, hard to follow logic.

**Solution**: Extract nested blocks, invert conditions, use guard clauses.

```python
# Before
def process_order(order):
    if order.is_valid():
        if order.customer.is_active():
            if order.payment.is_authorized():
                if order.inventory_available():
                    ...  # Deep nested logic

# After
def process_order(order: Order) -> None:
    if not order.is_valid():
        raise InvalidOrderError()
    if not order.customer.is_active():
        raise InactiveCustomerError()
    if not order.payment.is_authorized():
        raise PaymentNotAuthorizedError()
    if not order.inventory_available():
        raise InsufficientInventoryError()

    ...  # Logic at top level
```

## Dependency Analysis

Use the Grep tool to find import dependencies and coupling hotspots:

- Search for `^import\|^from` patterns in Python files to map dependencies
- Count imports per module to identify high-coupling files
- Use tools like `pydeps` or `import-linter` for circular dependency detection (install via your project's package manager)
