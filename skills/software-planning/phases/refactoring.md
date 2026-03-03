# Refactoring Phase

Embed a refactoring phase within a plan when existing code structure must change before new functionality can be built cleanly. This phase delegates to the [Refactoring](../../refactoring/SKILL.md) skill for methodology.

## When to Include a Refactoring Phase

Detection signals during plan analysis:

- **Structural obstacle**: The target module/area has low cohesion or high coupling that would make the new feature brittle
- **God object**: A class or module does too many things and the feature would add yet another responsibility
- **Shotgun surgery risk**: The feature would require touching many unrelated files due to poor boundaries
- **Test gap**: No tests cover the area being changed, and the change is non-trivial — write characterization tests first
- **Naming/organization mismatch**: The domain concepts don't match the code structure, making the plan steps confusing

If none of these signals are present, skip the refactoring phase and proceed directly with feature steps.

## Phase Structure in PLAN.md

A refactoring phase is a **group of consecutive plan steps** marked with `[Phase: Refactoring]`. Each step within the phase follows the refactoring skill's safe refactoring workflow (green bar → small change → run tests → commit).

```markdown
## Steps

### Step 1: [Phase: Refactoring] Assess current structure of <area>

**Skill**: [Refactoring](../../refactoring/SKILL.md)
**Implementation**: Analyze coupling, cohesion, and responsibilities in <area>. Document findings.
**Done when**: Clear list of what needs to change and why, captured in LEARNINGS.md

### Step 2: [Phase: Refactoring] Extract <concern> from <source>

**Skill**: [Refactoring](../../refactoring/SKILL.md)
**Implementation**: Move <concern> to dedicated module, update imports, preserve behavior
**Testing**: All existing tests pass unchanged
**Done when**: `<concern>` is self-contained, no behavior changes

### Step 3: [Phase: Refactoring] Introduce <abstraction> for <dependency>

**Skill**: [Refactoring](../../refactoring/SKILL.md)
**Implementation**: Define Protocol, refactor dependents to accept abstraction, inject concrete impl
**Testing**: Existing tests pass, dependency is swappable
**Done when**: Concrete dependency is behind abstraction boundary

### Step 4: Implement <new feature> on clean foundation

**Implementation**: Build feature on the refactored structure
**Testing**: New tests for feature behavior
**Done when**: Feature works, all tests pass
```

## Entry Criteria

Before starting the refactoring phase:

- [ ] Existing tests pass (or characterization tests are written as first step)
- [ ] Refactoring goal is clear: what structural improvement enables the feature
- [ ] Phase steps are scoped — no open-ended "clean up everything"

## Exit Criteria

The refactoring phase is complete when:

- [ ] All refactoring steps are committed
- [ ] No behavior changes — same tests, same results
- [ ] All consumers re-wired — every call site, import, config entry, and indirect reference points to the new locations
- [ ] Dead code cleaned up — orphaned functions, stale imports, compatibility shims, and transitional scaffolding removed
- [ ] The structural obstacle that motivated the phase is resolved
- [ ] The codebase is ready for the feature steps that follow

## Refactoring Skill Quick Reference

The [Refactoring skill](../../refactoring/SKILL.md) provides the methodology used within each phase step:

| Concept | Use in phase steps |
|---------|--------------------|
| **Four Pillars** (modularity, low coupling, high cohesion, pragmatic structure) | Guide what to improve |
| **Extract Module** | When splitting responsibilities |
| **Introduce Abstraction** | When decoupling dependencies |
| **Eliminate Circular Dependencies** | When untangling import cycles |
| **Extract Data Structure** | When parameter lists are unwieldy |
| **Inline Over-Abstraction** | When simplifying premature abstractions |
| **Decision Framework** | When deciding whether to create module, add abstraction, or split package |

## Combining with Language Contexts

Refactoring phases often pair with a language context. When both apply, the language context provides the quality gates and the refactoring phase provides the methodology:

```markdown
### Step 2: [Phase: Refactoring] Extract validation from user_service

**Skill**: [Refactoring](../../refactoring/SKILL.md)
**Implementation**: Move validation functions to `user_validation.py`, use Protocol for abstraction
**Testing**: Existing tests pass unchanged
**Quality gates**: `ruff check .`, `mypy src/`, `pytest` (from [Python context](../contexts/python.md))
**Done when**: `user_service` has single responsibility, validation is reusable
```

## Anti-Patterns

- **Refactoring without a goal**: Every refactoring step must serve the plan's feature goal
- **Unbounded scope**: "Clean up the module" is not a step — be specific about what changes
- **Behavior changes hidden in refactoring**: Refactoring steps must preserve behavior; new behavior belongs in feature steps
- **Skipping assessment**: Always start with an assessment step to avoid surprises mid-phase
