# Data Structure Design Review Checklist

Verifier-facing audit of a change's representation surface: new or modified types, state shapes, domain models, or component/agent schemas. Apply when a diff introduces or alters a data structure that crosses a component boundary, has a lifecycle, or encodes a domain rule. Findings anchor to `rules/swe/coding-style.md § Data Structures and Invariants`. Back to [SKILL.md](../SKILL.md).

## Legal States

- [ ] The type's representable state space matches its legal state space (no field combinations that are illegal but constructible)
- [ ] Mutually exclusive shapes are a sum type / discriminated union, not correlated nullable fields
- [ ] No boolean pairs whose combinations include an illegal state (`is_loading` + `has_error` with both true undefined)
- [ ] Closed option sets are enums/literal unions, not raw strings
- [ ] Every match/switch over a sum type is exhaustive (compiler flag, linter, or `assert_never` in place)

Golden bad-case: a `Job` dataclass with `status: str`, `started_at: datetime | None`, `finished_at: datetime | None`, `error: str | None` where "finished jobs must have `finished_at` and failed jobs must have `error`" lives only in a comment — every consumer can construct and receive impossible jobs.

## Invariants and Construction

- [ ] Every stated invariant has a named enforcement point (type system, smart constructor, or runtime check) — none enforced only by docstring
- [ ] Constrained values use a domain type (newtype/branded type), not a bare primitive, where the language supports it cheaply
- [ ] Constrained types are constructible only through a validating constructor; the unchecked path is private or clearly marked
- [ ] Two same-typed values that must never be interchanged (e.g., two kinds of ID) are distinguished at the type level

Golden bad-case: `def transfer(from_account: str, to_account: str, amount: float)` — the compiler cannot catch swapped arguments, negative amounts, or a currency mismatch; every caller re-validates or none does.

## Boundary Parsing

- [ ] External input (HTTP, file, config, env, tool call, LLM output) is parsed once at the boundary into a validated internal type
- [ ] The interior never re-validates and never handles the raw external shape (no `dict[str, Any]`/`any` traveling deep into the call graph)
- [ ] Parse failures produce actionable errors at the boundary, not deep-stack exceptions at first use

Golden bad-case: a request body deserialized to a dict at the handler, passed through four layers, with `payload["user"]["email"]` accessed (and defensively `.get()`-ed) in each layer — shotgun parsing.

## Identity, Ownership, Lifecycle

- [ ] Each structure is deliberately an entity (identity, lifecycle, owning module) or a value (immutable, equality-compared) — not an accidental mix
- [ ] Mutable state has a named owner and a mutation surface; no shared mutable structure mutated from multiple modules
- [ ] Distinct lifecycle phases are modeled as states (sum type / state machine), with transitions as named operations
- [ ] Value-like types are immutable by default (frozen dataclass, `readonly`, records)

## Evolution and Contracts

- [ ] Shapes crossing module/process/agent boundaries have a stated evolution contract: additive-only, or version-tagged with a migration path
- [ ] Schema/parameter names are unambiguous for their consumers (`user_id`, not `user`) — for agent-tool schemas, names carry the semantics
- [ ] Error shapes are part of the contract and actionable
- [ ] Changes to pipeline-artifact section schemas are treated as contract changes (consumers named, both sites updated)

## Proportionality (anti-ceremony)

- [ ] The Representation Design Pass was applied to boundary-crossing/invariant-bearing structures — and NOT ritualized onto loop temporaries, private tuples, or throwaway script shapes
- [ ] No speculative layout optimization (struct-of-arrays, pooling) without a measured hot path
- [ ] No simulated type-system features the language cannot support cleanly

## Quick Verdict Guide

| Finding count | Verdict |
|---------------|---------|
| 0 FAIL, 0 WARN | PASS |
| 0 FAIL, 1–3 WARN | PASS WITH FINDINGS |
| 0 FAIL, 4+ WARN | PASS WITH FINDINGS (significant) |
| 1+ FAIL | FAIL |

FAIL items: constructible illegal states in a boundary-crossing type; an invariant with no enforcement point that a consumer already violates; raw external input consumed deep in the interior; shared mutable state with no owner.

WARN items: primitive obsession on domain concepts; non-exhaustive matches; missing evolution contract on a cross-boundary shape; ambiguous schema field names; ceremony applied to throwaway shapes.
