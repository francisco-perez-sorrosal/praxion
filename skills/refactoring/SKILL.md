---
description: Pragmatic refactoring practices emphasizing modularity, low coupling, high cohesion, and incremental improvement. Use when restructuring code, improving design, reducing coupling, organizing codebases, extracting modules, eliminating code smells, or discussing refactoring patterns and code organization.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Pragmatic Refactoring

Systematic approach to refactoring that prioritizes modularity, low coupling, high cohesion, and maintainable structure.

## Core Principles

**Pragmatism First**: Every refactoring must have a clear purpose. Never refactor for the sake of refactoring.

**Small, Safe Steps**: Make incremental changes that keep the system working. Each step should be independently committable.

**Behavior Preservation**: Refactoring changes structure, not behavior. Tests should pass before and after.

**Simplicity Over Cleverness**: The simplest solution that solves the problem is the best solution.

## The Four Pillars

### 1. Modularity

Break systems into self-contained units with clear responsibilities. Each module should have a single, well-defined purpose and be understandable in isolation.

```python
# Before: Everything in one module
class UserManager:
    def validate_email(self, email): ...
    def hash_password(self, password): ...
    def send_welcome_email(self, user): ...
    def store_in_database(self, user): ...

# After: Separated by concern
# user_validation.py / password_security.py / email_service.py / user_repository.py
```

### 2. Low Coupling

Minimize dependencies between modules. Depend on abstractions, use dependency injection, avoid circular dependencies.

```python
# Before: Tightly coupled
class OrderProcessor:
    def __init__(self):
        self.db = PostgresDatabase()       # Concrete dependency
        self.emailer = SmtpEmailer()       # Concrete dependency

# After: Loosely coupled via abstractions
class OrderProcessor:
    def __init__(self, db: Database, emailer: Emailer):
        self.db = db
        self.emailer = emailer
```

### 3. High Cohesion

Keep related things together, unrelated things apart. Group by what changes together, not by technical category.

```python
# Before: Low cohesion (catch-all utils.py)
def format_date(date): ...
def validate_email(email): ...
def calculate_discount(price, percent): ...

# After: High cohesion (grouped by domain concept)
# date_formatting.py / email_validation.py / pricing.py
```

### 4. Pragmatic Structure

Organize code to match domain concepts, not technical layers.

```text
# Before: Layer-based (technical grouping)
project/
├── models/
├── controllers/
└── services/

# After: Feature-based (domain grouping)
project/
├── users/
├── orders/
└── catalog/
```

## Refactoring Workflow

### 1. Understand Current State

- Read and understand the code
- Identify what's working, what's painful
- Run existing tests (or write characterization tests)

### 2. Plan the Change

- Define clear goal: "Extract payment processing from order service"
- Break into small steps, each safe and testable

### 3. Execute Incrementally

1. **Green Bar**: Ensure all tests pass
2. **Small Change**: One small refactoring
3. **Run Tests**: Verify behavior unchanged
4. **Review**: Check coupling/cohesion improved
5. **Commit**: Save working state
6. **Repeat**: Next small step

If tests fail after a change, revert and try a smaller step.

### 4. Verify Re-Wiring and Clean Up

After restructuring, systematically verify that **every consumer** of the changed code is correctly reconnected:

- **Trace all call sites**: Search for every reference to moved/renamed/extracted code — imports, function calls, type references, configuration entries
- **Verify integration points**: Run the full test suite, not just unit tests for the changed modules — integration and end-to-end tests catch broken wiring that unit tests miss
- **Check indirect consumers**: Templates, config files, CLI entry points, plugin registrations, dependency injection containers — anything that references code by name or path
- **Remove dead code**: Delete unused imports, orphaned functions, abandoned classes, and stale configuration that the refactoring made obsolete — don't leave corpses behind
- **Clean up transitional scaffolding**: Remove compatibility shims, re-exports, and forwarding functions that were only needed during the transition
- **Final sweep**: `grep`/search for old names, old paths, old module references — if anything still points to pre-refactoring locations, it's a bug

## Decision Framework

### Should I Create a New Module?

**Yes, if**: Clear boundary and single responsibility, used by multiple modules, natural cohesion, reduces coupling.

**No, if**: Only one use case, creates artificial separation, increases complexity without benefit.

### Should I Add an Abstraction?

**Yes, if**: Multiple implementations exist or will soon, need to swap implementations, reducing coupling.

**No, if**: Only one implementation exists and likely will, abstraction doesn't hide complexity, YAGNI.

### Should I Split This Package?

**Yes, if**: Multiple unrelated responsibilities, different parts change for different reasons, too large to grasp.

**No, if**: Everything changes together, high cohesion across all parts, splitting would increase coupling.

## Patterns & Scenarios Reference

See [references/patterns.md](references/patterns.md) for detailed refactoring patterns and common scenarios with full code examples:

**Patterns**: Extract Module, Introduce Abstraction, Eliminate Circular Dependencies, Extract Data Structure, Inline Over-Abstraction

**Scenarios**: God Object/Module, Feature Envy, Primitive Obsession, Utils Hell, Deep Nesting

## Anti-Patterns

| Anti-Pattern | Fix |
| --- | --- |
| **Over-Abstraction** — interfaces without multiple implementations | Start concrete, extract when second use case appears |
| **Anemic Models** — data classes with no behavior | Move behavior into the class |
| **Shotgun Surgery** — one change touches many files | Group things that change together |
| **Speculative Generality** — flexibility for hypothetical needs | Implement for current requirements only |
| **Premature Optimization** — optimizing without measurements | Profile first, optimize hot paths only |

## When to Refactor

**Don't refactor if**:

- No tests exist and behavior is unclear (write tests first)
- Code is about to be deleted
- Working code with no current pain point

**Do refactor when**:

- Adding feature and current structure is an obstacle
- Bug reveals structural problem
- Code duplication reaches three instances
- Coupling prevents testing

## Code Metrics

Monitor these thresholds:

- **Module size**: >500 lines needs review
- **Cyclomatic complexity**: Functions >10 need simplification
- **Coupling**: Count dependencies per module
- **Cohesion**: Measure internal relatedness

## Language-Specific Notes

### Python

- Use Protocols for abstractions (PEP 544)
- Dataclasses for immutable data (`frozen=True`)
- Prefer composition over inheritance
- Type hints enable safe refactoring

See the [Python](../python-development/SKILL.md) skill for detailed type hint patterns, testing, and code quality tools.

### General (Language Agnostic)

```typescript
// Before: Mutable state couples callers to internal changes
class ShoppingCart {
  items: Item[] = [];
  addItem(item: Item) { this.items.push(item); }
}

// After: Immutable updates — callers can reason locally
class ShoppingCart {
  constructor(readonly items: ReadonlyArray<Item> = []) {}
  addItem(item: Item): ShoppingCart {
    return new ShoppingCart([...this.items, item]);
  }
}
```

## Verification Checklist

Before committing refactoring:

- [ ] All tests pass (unit, integration, and end-to-end)
- [ ] No behavior changes
- [ ] All call sites re-wired — no references to old names, paths, or modules
- [ ] Indirect consumers updated (config, templates, CLI entry points, DI registrations)
- [ ] Coupling reduced or unchanged
- [ ] Cohesion improved
- [ ] No dead code remains — orphaned functions, classes, and imports deleted
- [ ] No transitional scaffolding left (compatibility shims, re-exports, forwarding functions)
- [ ] Imports are clean
- [ ] Each module has clear purpose
- [ ] Can explain why each change improves design
