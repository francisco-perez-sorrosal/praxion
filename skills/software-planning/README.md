# Software Planning Skill

Plan complex software tasks using a three-document model (IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md) that tracks work in small, known-good increments.

## When to Use

- Features spanning multiple sessions or many files
- Work with architectural implications or evolving requirements
- Complex tasks where you need to track progress, capture learnings, and maintain a working codebase throughout

For simple tasks (bug fixes, single-module changes), skip this skill and use Task tools (TaskCreate/TaskUpdate) instead.

## Activation

Load explicitly with `software-planning` or reference the three-document model. The skill activates when the assistant detects significant development work that benefits from structured planning.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: three-document model, step sizing, testing guidance, commit discipline, gotchas, workflow |
| `references/document-templates.md` | IMPLEMENTATION_PLAN.md, WIP.md, LEARNINGS.md templates |
| `references/decomposition-guide.md` | Feature breakdown, anti-patterns, step sizing heuristics |
| `references/agent-pipeline-details.md` | Agent boundary discipline, parallel execution, interaction reporting |
| `references/coordination-details.md` | Pipeline worktree lifecycle, BDD/TDD execution, batched improvement, context-engineer shadowing, doc-engineer parallel execution, fragment files |
| `references/adr-authoring-protocols.md` | ADR file creation, index regeneration, supersession protocol |
| `references/architecture-documentation.md` | Dual-audience architecture documentation methodology: lifecycle, section ownership, validation for architect and developer documents |
| `assets/ARCHITECTURE_TEMPLATE.md` | 8-section template for `.ai-state/ARCHITECTURE.md` architect-facing design target |
| `contexts/python.md` | Python-specific quality gates and step templates |
| `phases/refactoring.md` | Refactoring phase methodology |
| `README.md` | This file — overview and usage guide |

### Extension Directories

The skill has two extension axes that compose independently:

```
software-planning/
├── SKILL.md                      # Core planning methodology
├── contexts/                     # Horizontal: language-specific augmentation
│   └── python.md                 #   Quality gates, step templates, plan shapes
└── phases/                       # Vertical: specialized work-type delegation
    └── refactoring.md            #   Embed refactoring phases within a plan
```

**Contexts** augment *every* step with language-specific quality gates, testing patterns, and step templates. Load when the plan targets a specific tech stack.

| Context | File | Related Skills |
|---------|------|----------------|
| Python | [`contexts/python.md`](contexts/python.md) | [Python](../python-development/SKILL.md), [Python Project Management](../python-prj-mgmt/SKILL.md) |

**Phases** delegate a *group of steps* to a specialized skill's methodology. Include when the plan analysis detects preparatory work is needed before feature development.

| Phase | File | Delegated Skill |
|-------|------|-----------------|
| Refactoring | [`phases/refactoring.md`](phases/refactoring.md) | [Refactoring](../refactoring/SKILL.md) |

## Quick Start

1. **Load the skill**: reference `software-planning` when starting significant work
2. **Create IMPLEMENTATION_PLAN.md**: define goal, tech stack, acceptance criteria, and steps
3. **Add context** (optional): if working in Python, reference `contexts/python.md` for quality gates
4. **Check for phases** (optional): if existing code needs restructuring, prepend a refactoring phase from `phases/refactoring.md`
5. **Execute**: one step at a time, one commit per step, keeping WIP.md accurate
6. **Finish**: merge learnings into permanent locations, delete all three documents

## Related Skills

- [`python-development`](../python-development/) / [`python-prj-mgmt`](../python-prj-mgmt/) — Python-specific planning contexts (quality gates, project setup)
- [`refactoring`](../refactoring/) — embedding refactoring phases in plans

## Adding New Contexts and Phases

**New language context** (e.g., TypeScript, Rust):
1. Create `contexts/<language>.md` referencing the relevant language skill(s)
2. Include: quality gate commands, step templates, testing patterns, common plan shapes
3. Add a row to the contexts table in `SKILL.md` under [Language Context](SKILL.md#language-context)

**New phase** (e.g., migration, security audit):
1. Create `phases/<phase-name>.md` referencing the relevant specialized skill
2. Include: detection signals, step templates, entry/exit criteria, anti-patterns
3. Add a row to the phases table in `SKILL.md` under [Phase Delegations](SKILL.md#phase-delegations)
