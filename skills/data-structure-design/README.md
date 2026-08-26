# data-structure-design

Program-level representation design: choose the types, invariants, state shapes, and schemas at the heart of every component **before** writing the behavior that consumes them. Operationalizes the `Data Structures First` principle.

- **What it covers** — the Representation Design Pass (legal states → invariants → identity/ownership → lifecycle → access patterns → boundary parsing → evolution → layout-last); sum types, newtypes, smart constructors, parse-don't-validate, state machines; schemas as agent-tool contracts.
- **What it does not cover** — database schemas, normalization, ORMs, migrations: that is [`data-modeling`](../data-modeling/). Boundary rule: in a database → `data-modeling`; in memory or on a wire between components/agents → here.
- **Pipeline integration** — systems-architect fills `SYSTEMS_PLAN.md § Architecture ### Data Structures`; the planner orders representation steps before behavior steps; the implementer loads this skill for type/schema-defining steps; the verifier audits with [references/design-review-checklist.md](references/design-review-checklist.md); the discipline-consultant can be convened as `data-structure-specialist` for load-bearing decisions.

Start at [SKILL.md](SKILL.md); worked Python/TypeScript patterns in [references/representation-patterns.md](references/representation-patterns.md).
