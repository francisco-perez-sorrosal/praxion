# Dependency Mapping

Identify, visualize, and sequence dependencies between roadmap items. Load this reference when building a dependency graph or when the dependency mapping step in the core workflow needs more depth.

## Dependency Types

| Type | Symbol | Definition | Sequencing Impact |
|------|--------|-----------|-------------------|
| **Hard (blocking)** | `A --> B` | B cannot start until A completes | B must follow A in the roadmap |
| **Soft (enhancing)** | `A -.-> B` | B benefits from A but can proceed without it | Prefer A before B; not mandatory |
| **Shared resource** | `A <--> B` | A and B compete for the same resource | Cannot run in parallel |

**Hard dependencies** drive the critical path. **Soft dependencies** inform preferred ordering. **Shared resource** dependencies constrain parallelism.

## Building the Dependency Graph

### Step 1: List All Items

Extract candidate items from the roadmap. Each item becomes a node.

### Step 2: Identify Dependencies

For each pair of items, ask three questions:

1. **Does A produce something B needs?** (data, API, infrastructure) --> hard dependency
2. **Does A make B easier or better?** (shared patterns, reduced scope) --> soft dependency
3. **Do A and B need the same constrained resource?** (same person, same system) --> shared resource

### Step 3: Draw the Graph

Use markdown text notation for the dependency graph:

```markdown
## Dependency Graph

sentinel-fix --> roadmap-planning --> memory-v2
                                  \-> typescript-skill
memory-v2 -.-> multi-project-memory
```

Convention:
- `-->` hard dependency (blocking)
- `-.->` soft dependency (enhancing)
- Items with no incoming arrows are **roots** (can start immediately)
- Items with no outgoing arrows are **leaves** (nothing depends on them)

### Step 4: Identify the Critical Path

The critical path is the longest chain of hard dependencies from any root to any leaf.

**Procedure**:

1. List all hard-dependency chains from roots to leaves
2. Sum the effort estimates along each chain
3. The chain with the highest total effort is the critical path

**Example**:

```
Chain 1: sentinel-fix (S) --> roadmap-planning (M) --> memory-v2 (L)
         Total: S + M + L = ~6 weeks

Chain 2: sentinel-fix (S) --> roadmap-planning (M) --> typescript-skill (M)
         Total: S + M + M = ~4 weeks

Critical path: Chain 1
```

Items on the critical path cannot be delayed without delaying the entire roadmap. Prioritize critical-path items and allocate slack to non-critical items.

## Sequencing Strategies

### Strategy 1: Critical Path First

Sequence all critical-path items before non-critical items. Maximizes the chance of completing the roadmap on time.

**When to use**: committed delivery dates, external dependencies, or when the critical path is significantly longer than alternatives.

### Strategy 2: Highest Value First

Sequence by priority score, respecting dependency constraints. Delivers maximum value earliest.

**When to use**: no fixed deadline; goal is to maximize cumulative value delivered over time.

### Strategy 3: Risk-First

Sequence items with highest uncertainty or most dependencies first. Surfaces problems early when there is still time to adapt.

**When to use**: novel domains, architectural unknowns, or when several items depend on the outcome of one risky item.

### Strategy 4: Quick Wins First

Sequence small, high-value, low-dependency items first. Builds momentum and delivers visible progress.

**When to use**: team morale, stakeholder confidence, or when the backlog has many small items alongside a few large ones.

### Choosing a Strategy

| Situation | Strategy |
|-----------|----------|
| Fixed deadline | Critical Path First |
| No deadline, maximize impact | Highest Value First |
| High uncertainty or unknowns | Risk-First |
| Need to demonstrate progress | Quick Wins First |
| Mixed constraints | Combine: quick wins at start, then critical path |

## Parallelism Assessment

Items can run in parallel when they have:

- No hard dependencies between them
- No shared resource constraints
- Disjoint file sets (different skills, agents, or modules)

**Parallelism table** (include in ROADMAP.md when applicable):

```markdown
## Parallel Execution Opportunities

| Group | Items | Constraint |
|-------|-------|-----------|
| A | typescript-skill, doc-management-update | Disjoint: different skills |
| B | memory-v2, roadmap-planning | Sequential: roadmap-planning depends on memory patterns |
```

## Dependency Notation in ROADMAP.md

When writing the dependency graph section of ROADMAP.md, use this notation:

```markdown
## Dependency Graph

### Hard Dependencies
- sentinel-fix --> roadmap-planning (roadmap needs healthy baseline)
- roadmap-planning --> memory-v2 (memory benefits from prioritization patterns)

### Soft Dependencies
- typescript-skill -.-> cicd-improvements (CI benefits from TS skill but not blocked)

### Parallel Groups
- Group A (no dependencies): typescript-skill, doc-management-update
- Group B (sequential): sentinel-fix, roadmap-planning, memory-v2

### Critical Path
sentinel-fix --> roadmap-planning --> memory-v2
Estimated duration: ~6 weeks
```

## Common Dependency Patterns

### Fan-out

One item enables multiple downstream items. The enabling item is high-priority regardless of individual downstream scores.

```
        /--> B
A ──►──+--> C
        \--> D
```

### Fan-in

Multiple items must complete before one item can start. All upstream items are on the critical path for the downstream item.

```
A --\
B --+--> D
C --/
```

### Chain

Linear sequence. Each item blocks the next. The entire chain is the critical path.

```
A --> B --> C --> D
```

### Island

Items with no dependencies in either direction. Schedule freely based on priority and capacity.

## Maintaining the Graph

Update the dependency graph when:

- New items are added to the roadmap
- Items complete (remove them; update downstream items)
- Scope changes reveal new dependencies
- A soft dependency proves to be hard (or vice versa)

Stale dependency graphs mislead more than missing ones. If the graph is not maintained, remove it from the roadmap rather than leaving it inaccurate.
