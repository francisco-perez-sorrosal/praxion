# Design When the Consumer Is an Agent

Agent-era lens for the [`software-design-principles`](../SKILL.md) skill.

Classic SOLID assumed the consumer of a module was a human programmer or another
module. In agentic development a *third* consumer matters: an AI agent that reads,
composes, and extends the surface at runtime. The durable principles still apply —
this reference shows how each maps onto agent ergonomics, and where the agent
case sharpens a heuristic that humans tolerate.

The throughline: **for an agent, coupling at the code level becomes coupling at
the context level.** Knowledge an agent must hold to use a surface consumes its
context window — the agent's scarcest resource. A leaky or fat contract doesn't
just risk a bug; it pollutes the reasoning budget. This is
`CLAUDE.md§Context Engineering` expressed at the boundary of code.

## The four agent-era design pressures

1. **Machine-interpretable contracts (LSP + ISP, sharpened).**
   An agent cannot infer an unwritten convention the way a human teammate can. The
   contract must be *explicit*: typed parameters, named operations, semantic
   descriptions, and clear state transitions. Hidden assumptions (an LSP
   violation) that a human would catch in review become silent agent failures.
   Make the contract say everything the caller is allowed to assume — nothing
   implicit.

2. **Composable capabilities over coarse features (SRP + OCP).**
   Agents plan by composing small, well-named capabilities. Prefer many cohesive,
   single-purpose operations the agent can combine over a few god-operations with
   mode flags. A coarse `do_everything(mode=...)` forces the agent to encode
   branching knowledge it shouldn't need; cohesive verbs let it assemble paths.

3. **Context-as-coupling (the agentic restatement of cohesion).**
   A well-bounded module lets an agent load *only* the slice relevant to its
   subtask, protecting its context from the "pollution" of unrelated concerns.
   Modular design improves not just maintainability but the *interpretability* of
   system behavior — an agent (and a human) can reason about a bounded part in
   isolation. Low cohesion forces the agent to load more to understand less.

4. **Spec-as-source-of-truth (the regenerable-code corollary).**
   When generation makes code cheap, the durable artifact shifts from the
   implementation to the *contract*. Design discipline concentrates on the spec:
   the interface, the error grammar, the invariants. Code may be regenerated
   against a stable contract; a sloppy contract makes every regeneration a new
   negotiation. Invest design effort where it persists — the boundary, not the body.

## Practical mapping

| Surface | SOLID lever | Agent-era expression |
|---|---|---|
| MCP / function-calling tool | ISP | Thin, role-specific tools; don't expose twenty optional params the model must reason over. Progressive disclosure of detail. |
| Tool / API error responses | LSP | Explicit, typed, consistent error grammar (e.g. RFC 9457). No surprising failure modes the caller couldn't anticipate. |
| Tool naming & decomposition | SRP | One clear responsibility per tool, named for intent; fat-vs-thin is a cohesion decision. |
| Capability set | OCP | New capability = new composable tool, not a new flag on an existing one. |
| Service dependencies behind a tool | DIP | The agent-facing contract depends on an abstraction; swap the backing mechanism without changing the agent's mental model. |

## Where to go deeper

This reference is the *principle-level* bridge. For the craft of designing the
surfaces themselves, compose with:

- [`agentic-interface-design`](../../agentic-interface-design/SKILL.md) — MCP tools, function-calling schemas, A2A contracts, fat-vs-thin decomposition, idempotency, pagination, error grammar.
- [`api-design-craft`](../../api-design-craft/SKILL.md) — API quality and taste, RFC 9457 errors, cursor pagination, paradigm selection.

## Self-test for an agent-consumed surface

- Could an agent use this correctly from the contract alone, with no tribal knowledge?
- Does each operation have one clear responsibility, or does it hide modes?
- Does using this surface force the agent to load knowledge unrelated to its task?
- Is the contract stable enough that the implementation could be regenerated beneath it without breaking callers?
