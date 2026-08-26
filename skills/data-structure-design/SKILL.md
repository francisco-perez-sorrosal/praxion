---
name: data-structure-design
description: >
  Program-level data-structure and representation design: choosing the types,
  invariants, state shapes, and schemas at the heart of every component before
  writing the behavior that consumes them. Triggers: defining or changing a core
  domain type or data model, designing state machines or lifecycle phases,
  choosing sum vs product types, making illegal states unrepresentable,
  parse-don't-validate boundaries, newtypes/smart constructors for constrained
  values, designing schema contracts between components or agent tools, deciding
  a representation before its operations. Persistence-layer schema design
  (databases, ORMs, migrations) belongs to the data-modeling skill, not here.
allowed-tools: [Read, Grep, Glob]
compatibility: Claude Code
metadata:
  principle: CLAUDE.md§Data Structures First
---

# Data Structure Design

Choose the representation before writing the behavior. The shape of a
component's data — its types, invariants, states, and the schemas it exposes —
determines how hard the component is to build correctly, how much validation
scatters through the code, and how safely it evolves. This skill is the
program-level canon: in-memory structures, domain types, state machines, and
inter-component/agent-tool schemas. The persistence layer (database schemas,
normalization, migrations) is the `data-modeling` skill's territory.

**Satellite files** (loaded on-demand):

- [references/python-patterns.md](references/python-patterns.md) -- Python idioms: frozen-dataclass sum types, `assert_never` exhaustiveness, `NewType` vs wrapper decision guide, pydantic boundary parsing, Python-specific gotchas
- [references/typescript-patterns.md](references/typescript-patterns.md) -- TypeScript idioms: discriminated unions, branded types, literal unions over `enum`, zod boundary parsing, `satisfies`, TS-specific gotchas
- [references/schema-contract-patterns.md](references/schema-contract-patterns.md) -- language-neutral schema contracts for model consumers: tool JSON-schemas, error shapes, evolution policy, pipeline-artifact schemas
- [references/design-review-checklist.md](references/design-review-checklist.md) -- verifier-facing review checklist with golden bad-cases, keyed to the Representation Design Pass

Load only the language reference matching the project's language (detect per the language-context conventions the pipeline already uses); load `schema-contract-patterns.md` when designing a tool/agent/artifact schema regardless of language. For other languages, apply the SKILL body's techniques through the language's native mechanisms — sum types and boundary parsing exist in every ecosystem worth shipping in.

## Gotchas

- **A product type silently multiplies states.** A struct/dataclass of N
  independent fields has the *product* of each field's range as its state
  space — almost always including illegal combinations. If two fields' legality
  depends on each other, that is a sum-type smell: model the mutually exclusive
  shapes explicitly
- **An invariant with no named enforcer is not an invariant.** "The list is
  always sorted" written in a docstring enforces nothing. Name the enforcement
  point — type system, smart constructor, or runtime check — or expect the
  invariant to be violated
- **Validation is not parsing.** Checking a predicate and then passing the
  *original* value forward discards the proof; every downstream consumer must
  re-check or blindly trust. Parse into a more precisely typed value once, at
  the boundary, and let the interior trust the type
- **Do not lead with physical layout.** Data-oriented design (struct-of-arrays,
  cache locality) is a specialization for measured hot paths over homogeneous
  data — not a default stance. Premature layout optimization is the mirror
  image of the `data-modeling` skill's premature-denormalization gotcha
- **Schemas reduce format errors, not reasoning errors.** For agent-tool
  contracts, the evidence supports schemas cutting interface/format failures;
  it does not (yet) show they improve end-task success. Design schemas for
  precision and self-description, but do not expect them to fix a semantic
  planning problem

## The One Idea: Representation Dominates

Five independent lineages spanning thirty years converge on one claim — the
data's shape determines the program's tractability, more than control flow does:

> "Show me your flowcharts and conceal your tables, and I shall continue to be
> mystified. Show me your tables, and I won't usually need your flowcharts;
> they'll be obvious." — Fred Brooks, *The Mythical Man-Month* (1975)

> "Bad programmers worry about the code. Good programmers worry about data
> structures and their relationships." — Linus Torvalds (git mailing list, 2006)

The same conclusion is Wirth's book title (*Algorithms + Data Structures =
Programs*, 1976), Rob Pike's Rule 5 ("Data dominates. If you've chosen the
right data structures and organized things well, the algorithms will almost
always be self-evident"), and Raymond's Rule of Representation ("Fold knowledge
into data, so program logic can be stupid and robust"). Parnas (1972) supplies
the structural corollary: a data structure's internal representation is the
paradigm example of a design decision to hide behind a module boundary, because
it is the decision most likely to change.

The consequence for practice: **representation is a design act, not an
implementation detail.** Behavior defines *what* to build (BDD); the
representation is the first — and most leveraged — decision about *how*.

## The Representation Design Pass

Walk this pass for every data structure that crosses a component boundary, has
a lifecycle, or encodes a domain rule. Skip it for genuinely local throwaway
shapes (a loop temporary, a private tuple) — applying it there is ceremony.

1. **Legal states first.** Enumerate the states the structure may legally
   occupy. If the field-combination space is larger than the legal-state space,
   restructure: mutually exclusive shapes become a sum type / discriminated
   union, not correlated nullable fields or boolean flags
2. **Invariants and their enforcer.** Name every invariant and its enforcement
   point: type system > smart constructor > runtime check — prefer the
   strongest mechanism the language offers. An unenforced invariant is
   documentation, not design
3. **Identity vs value.** Entity (tracked by identity across time — needs a
   lifecycle, an owning module, and a mutation surface) or value (defined by
   contents — default to immutable, comparable by equality, freely copyable)?
4. **Ownership and mutation discipline.** For anything that is not a pure
   value, name who may mutate it and through what surface. Shared mutable state
   without a named owner is the failure mode this step prevents
5. **Lifecycle as a state machine.** Distinct phases (pending → active →
   closed) become a sum type or explicit state machine — never a cluster of
   nullable fields and booleans that happen to correlate with phase
6. **Cardinality and access patterns.** How many, how looked up, how iterated?
   Choose the container (map vs list vs set vs queue) from the dominant access
   pattern, not habit
7. **Parse at the boundary.** Anything crossing a process, network, file, or
   trust boundary is parsed *once* into a validated internal type at the edge.
   The interior never re-validates and never handles the raw external shape
8. **Evolution contract.** Decide up front: additive-only (new optional
   fields), or version-tagged with a migration path? The discipline is the same
   for an in-process type crossing a module boundary and a wire schema crossing
   a network — only the mechanism differs
9. **Layout last, and only when measured.** Physical layout (struct-of-arrays,
   pooling, contiguity) earns attention only after the shape is correct for
   invariants/states/ownership *and* profiling shows a hot path

Record the outcome of this pass in the architecture document's data-structures
section (see Composition with the Pipeline below) — shape, invariants +
enforcement point, ownership, lifecycle, evolution contract.

## Core Techniques

| Technique | What it does | Reach for it when |
| --- | --- | --- |
| **Sum type / discriminated union** | State space = exactly the legal states | Mutually exclusive shapes; fields whose legality co-varies; lifecycle phases |
| **Newtype / branded type** | Bare primitive gains domain identity (`Email`, `UserId`, `PositiveInt`) | Primitive obsession; two same-typed values that must never be interchanged |
| **Smart constructor** | The only way to build the type validates and returns `Result`/`Option`; raw constructor unexported | Any constrained value; pairs with newtypes |
| **Parse, don't validate** | Boundary input becomes a precisely typed value carrying its proof of validity | Every IO/HTTP/config/tool-call boundary |
| **State machine as type** | Transitions are functions from one state type to another; illegal transitions don't compile / fail loudly | Lifecycles, protocols, multi-step workflows |
| **Immutable value default** | Values are time-independent; no defensive copying, safe sharing | Anything without identity; concurrent reads |
| **Exhaustiveness checking** | Compiler/linter flags unhandled variants when a sum type grows | Every match/switch over a sum type |

Worked examples and per-language idioms: [references/python-patterns.md](references/python-patterns.md) or [references/typescript-patterns.md](references/typescript-patterns.md) — load only the one matching the project's language.

**Enforcement point is language-relative, not doctrinal.** The type-driven camp
(Minsky, King, Wlaschin) enforces at compile time; the data-oriented dynamic
camp (Hickey/Clojure) enforces with runtime specs over immutable generic data.
Both agree illegal states must not be silently representable — the live
disagreement is only *where* enforcement lives. Use the strongest mechanism the
project's language offers (types in TypeScript/Rust/Go, type hints + runtime
validation such as pydantic in Python) and do not fight the language.

## Schemas as Agent Contracts

In agentic systems the consumers of a representation include models, not just
code. Tool JSON-schemas, pipeline-artifact section formats, and inter-agent
message shapes are data structures whose consumers parse with attention, not a
compiler — which raises, not lowers, the design bar:

- **Names carry the semantics types can't.** `user_id`, not `user`; an
  unambiguous field name is the schema-level newtype
- **Return meaning, not internals.** Semantically meaningful identifiers over
  raw UUIDs/MIME codes measurably improve model precision in downstream use
- **Errors are part of the shape.** An actionable error contract steers agent
  behavior; an opaque one produces retry loops
- **Artifact schemas are load-bearing.** A pipeline document's required
  sections are a wire format between agents — the schema binds the path, not
  the author. Treat changes to them as contract changes with an evolution story
- **State the evidence honestly.** Schema constraints demonstrably reduce
  interface-format errors; controlled evidence that they improve end-task
  success does not yet exist. Do not justify schema work with the stronger claim

Worked schema shapes, error contracts, and evolution policy: [references/schema-contract-patterns.md](references/schema-contract-patterns.md).

## Failure Modes

| Anti-pattern | What it looks like | The technique that prevents it |
| --- | --- | --- |
| **Primitive obsession** | `string`/`int`/`bool` for concepts with rules; validation repeated at every call site | Newtype + smart constructor |
| **Boolean blindness** | Two booleans with four combinations, one illegal (`is_loading` + `has_error`) | Sum type over the legal states |
| **Stringly-typed code** | Raw strings for closed option sets; scattered string comparison | Enum / literal union + exhaustiveness |
| **Correlated nullables** | `started_at`, `finished_at`, `error` all optional; legality rules live in comments | Lifecycle sum type |
| **Shotgun parsing** | Ad hoc checks sprinkled through the interior; raw input travels deep | Parse once at the boundary |
| **Anemic model** | Data as a bag of getters/setters, every rule externalized to services; one rule change touches every service | Invariants enforced in/at the type |

Empirical anchor, stated with its caveats: adding static types to real,
already-shipped JavaScript bugs would have caught ~15% of them (95% CI
11.5–18.5%, ICSE 2017) — a conservative lower bound (those bugs had already
survived testing and review), but not a cost-effectiveness proof. The stronger
argument for representation design is structural, not statistical: every
illegal state made unrepresentable is a class of test cases and runtime checks
that no longer needs to exist.

## When NOT to Apply

- **Throwaway and glue code** — a script's intermediate dict does not need a
  newtype. The pass applies to structures that cross boundaries, carry
  invariants, or live long enough to evolve
- **Exploratory spikes** — while the domain is still being discovered, premature
  type rigor freezes a model you don't yet believe in; harden the
  representation when behavior stabilizes (Incremental Evolution governs)
- **Fighting the language** — do not simulate a dependent type system in
  Python; use the strongest *native* mechanism and a runtime check beyond it
- **Hot-path layout by default** — data-oriented layout concerns activate on
  measured evidence only (Design Pass step 9)

## Composition with the Pipeline

- **systems-architect** owns the pass at design time: core domain structures
  land in `SYSTEMS_PLAN.md § Architecture ### Data Structures` (shape,
  invariants + enforcement point, ownership, lifecycle, evolution) — omitted
  only when a task genuinely has no representation surface
- **implementation-planner** orders representation-defining steps before the
  behavior steps that consume them ("data model before operations on that
  model") and tags them `[Architecture]`
- **implementer** loads this skill when a step defines or alters a type,
  state shape, or schema, and self-reviews against the Design Pass
- **verifier** runs [references/design-review-checklist.md](references/design-review-checklist.md)
  when representation surface is in scope; findings anchor to
  `rules/swe/coding-style.md § Data Structures and Invariants`
- **test-engineer** turns declared invariants into property-based tests —
  every invariant named in the Design Pass is a property candidate
- **discipline-consultant** (`Discipline: data-structure-specialist`) provides
  gated adversarial challenge when a load-bearing representation decision
  warrants it — see the discipline registry

## Related Skills

- **[`data-modeling`](../data-modeling/SKILL.md)** -- the persistence-layer
  counterpart: database schemas, normalization, migrations, ORMs. Boundary
  rule: if it lives in a database, start there; if it lives in memory or on a
  wire between components/agents, start here. The two meet at the repository/
  serialization boundary, where a stored row is parsed into a domain type
- **[`software-design-principles`](../software-design-principles/SKILL.md)** --
  the coupling lens: how much two parts know about each other. This skill is
  the representation lens: what shape the shared knowledge takes. A well-chosen
  type shrinks integration strength; the two skills compose
- **[`refactoring`](../refactoring/SKILL.md)** -- the reactive path: Extract
  Data Structure recovers a representation after the fact; this skill chooses
  it up front
- **[`testing-strategy`](../testing-strategy/SKILL.md)** -- property-based
  testing and stateful protocol testing verify the invariants and state
  machines this skill declares
- **[`api-design`](../api-design/SKILL.md)** -- consumer-oriented wire
  representations and interface contracts at public API surfaces

## Resources

- [Parse, Don't Validate (Alexis King, 2019)](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) -- the boundary-parsing argument, primary source
- [Domain Modeling Made Functional (Wlaschin)](https://pragprog.com/titles/swdddf/domain-modeling-made-functional/) -- sum types, newtypes, smart constructors as a method
- [On the Criteria to Be Used in Decomposing Systems into Modules (Parnas, 1972)](https://dl.acm.org/doi/10.1145/361598.361623) -- representation as the decision to hide
- [Writing effective tools for AI agents (Anthropic, 2025)](https://www.anthropic.com/engineering/writing-tools-for-agents) -- schema and naming discipline for model consumers
- [To Type or Not to Type (Gao, Bird, Barr, ICSE 2017)](https://ieeexplore.ieee.org/document/7985711) -- the 15%-of-bugs study behind the empirical anchor
- [Epigrams on Programming (Perlis, 1982)](https://www.cs.yale.edu/homes/perlis-alan/quotes.html) -- "100 functions on one data structure" (often misattributed to Hickey, who cites it)
