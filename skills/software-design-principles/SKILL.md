---
name: software-design-principles
description: >
  Software design principles for the AI era — SOLID reframed as heuristics in
  service of balanced coupling (managing knowledge flow between components), plus
  the agent-as-consumer lens. Covers single responsibility, open/closed, Liskov
  substitution, interface segregation, dependency inversion, low coupling / high
  cohesion, integration strength vs distance vs volatility, and why generation
  speed raises the stakes. Triggers: applying or reviewing SOLID, deciding
  whether to introduce an abstraction, reducing coupling, improving cohesion,
  designing module/interface boundaries, designing a surface an AI agent will
  consume, judging whether a design will accrue debt under fast code generation.
  Use up-front during architecture and design, not only during refactoring.
allowed-tools: [Read, Grep, Glob]
compatibility: Claude Code
metadata:
  principle: CLAUDE.md§Balanced Coupling
---

# Software Design Principles (AI Era)

One idea sits under all of these: **design is the management of knowledge flow
between parts.** SOLID, low coupling, and high cohesion are not separate rules to
memorize — they are heuristics that all serve this single concern. This skill is
the canonical home for that discipline. Two pipeline skills *compose* with it:
[`software-planning`](../software-planning/SKILL.md) applies it **up-front**
(choosing boundaries before code exists); [`refactoring`](../refactoring/SKILL.md)
applies it **reactively** (restoring it in code that already drifted).

**Satellite files** (loaded on-demand):

- [references/solid-heuristics.md](references/solid-heuristics.md) — the five SOLID principles, each reframed through balanced coupling, with the knowledge-flow failure each one prevents and language-agnostic before/after sketches.
- [references/agent-as-consumer.md](references/agent-as-consumer.md) — design principles when the consumer is an AI agent: machine-interpretable contracts, composable capabilities, context-as-coupling, spec-as-source-of-truth.

## The One Idea: Balanced Coupling

Every dependency between two parts is **shared knowledge**. Modularity is not
"fewer dependencies" — it is *balanced* dependencies, along two axes plus a
modulator:

| Dimension | Question | Imbalance symptom |
|---|---|---|
| **Integration strength** | How much must A know about B's internals to work with it? | High strength = intrusive coupling (B's change forces A's change). |
| **Distance** | How far apart do A and B live (same function → same module → same service → different team)? | Knowledge shared across large distance is the expensive kind. |
| **Volatility** | How often, and for what reasons, does each part change? | Co-locating parts with *different reasons to change* = low cohesion. |

The design target: **strength and distance in balance.** Deep shared knowledge is
fine between things that are close and change together (high cohesion); it is
poison between things that are far apart (tight coupling). Two failure poles:

- **Tight coupling** — high strength **+** high distance. A ripple in a remote part breaks you.
- **Low cohesion** — low strength **+** low distance (or scattered intent). Related logic lives apart; one change touches many places.

Three operational rules fall straight out of this, and they are all you need to
remember if you remember nothing else:

1. **Gather what changes together; separate what changes for different reasons.** (cohesion / SRP)
2. **Depend on abstractions, not details — and point dependencies toward stability.** (DIP / OCP)
3. **Expose only the knowledge a consumer actually needs.** (ISP / LSP)

## Why the AI Era Raises the Stakes

The physics of software complexity did not change when agents started writing
code — *"the author changed; the physics did not."* Software is still sequence,
selection, and iteration, and knowledge that flows the wrong way still costs.
What changed is **velocity**: generation makes code cheap, so a poor structural
decision now propagates and compounds faster than a human could ever have typed
it. The discipline that used to be "nice to have for maintainability" is now the
load-bearing constraint on whether a fast-built system stays buildable.

Two consequences specific to agentic development:

- **Bad modularity accrues debt at machine speed.** An agent will happily
  generate ten more callers of a leaky abstraction before you notice. Boundaries
  must be right *earlier*, because the cost of being wrong scales with generation
  throughput.
- **The agent is also a consumer.** A well-bounded module protects an agent's
  *context window* from the pollution of unrelated concerns exactly as it
  protects a human reader's attention — coupling at the code level becomes
  coupling at the context level. See [references/agent-as-consumer.md](references/agent-as-consumer.md).

## SOLID as Heuristics (not commandments)

Each SOLID principle is a named lever on knowledge flow. Quick reference; full
treatment in [references/solid-heuristics.md](references/solid-heuristics.md).

| Principle | Knowledge-flow framing | The failure it prevents |
|---|---|---|
| **SRP** — single responsibility | Keep one reason-to-change per unit | Low cohesion: unrelated change vectors entangled |
| **OCP** — open/closed | Extend without editing; new behavior is added, not patched | Modification coupling: every feature edits the same code |
| **LSP** — Liskov substitution | A substitute must honor the contract with no hidden assumptions | Implicit knowledge leaking from impl to caller |
| **ISP** — interface segregation | Expose only methods a client uses | Coupling overhead: clients depend on what they don't need |
| **DIP** — dependency inversion | High-level policy depends on abstractions, not low-level detail | Upward knowledge flow: policy bound to mechanism |

## When to Apply — and When Not To

These are heuristics, governed by Pragmatism and Incremental Evolution. Applying
SOLID blindly produces a different pathology — ceremony, premature abstraction,
indirection no one needs.

**Apply when:**

- Two parts that change for different reasons are entangled (split — SRP).
- A second or third implementation of something is real or imminent (invert — DIP/OCP).
- A change keeps rippling across modules that should be independent (find the leaking knowledge).
- A surface will be consumed by an agent or external client (tighten the contract — ISP/LSP).

**Do not apply when** (let it stay simple):

- There is exactly one implementation and no concrete second one in sight — an interface here is speculative coupling, not decoupling. (Incremental Evolution: *don't abstract for futures you don't need.*)
- The parts genuinely change together — splitting them lowers cohesion and raises coupling.
- The abstraction would hide behavior the caller must reason about (a leaky abstraction is worse than none).

**Self-test:** *Does this change reduce coupling that actually hurts, or am I
adding structure for a change that will never come?*

## Enforcement (optional, opt-in)

When an invariant from this canon is worth making executable, encode it as an
architectural fitness function (see the
[`architectural-fitness-functions`](../architectural-fitness-functions/SKILL.md)
skill) and cite the principle: `CLAUDE.md§Balanced Coupling`. Examples worth a
fitness rule: "the domain layer must not import infrastructure" (DIP), "modules A
and B must not import each other" (cohesion/independence). Add a rule only when
the invariant is load-bearing and drift is plausible — not for every SOLID
heuristic.

## Composition with the Pipeline

| Skill | Phase | How it uses this canon |
|---|---|---|
| `software-planning` | Up-front design / architecture | Choose module and interface boundaries so strength and distance balance *before* code exists. |
| `refactoring` | Reactive cleanup | The "Four Pillars" (modularity, low coupling, high cohesion, pragmatic structure) are this canon applied to code that already drifted. |
| `architectural-fitness-functions` | Enforcement | Make a chosen invariant executable; cite `CLAUDE.md§Balanced Coupling`. |
| `agentic-interface-design` / `api-design-craft` | Boundary surfaces | ISP/LSP for tool, MCP, and API contracts — the agent-as-consumer lens. |
| `data-structure-design` | Up-front design / representation | The representation lens beside this coupling lens: coupling measures how much two parts know about each other; representation decides what shape that shared knowledge takes. A well-chosen type shrinks integration strength (cite `CLAUDE.md§Data Structures First`). |

## Gotchas

- **SOLID is not OOP-only.** "Class" in the classic statements reads as "unit of deployment of behavior" — function, module, service, or agent tool. Don't dismiss a principle because the code isn't object-oriented.
- **DIP ≠ "add an interface everywhere."** Invert a dependency when policy must outlive mechanism, not reflexively. One implementation behind an interface is usually speculative coupling.
- **Cohesion is about *reasons to change*, not topical similarity.** A `utils` module groups by "these are all helpers" — that is topical, not cohesive. Group by what changes together.
- **"More abstraction" can increase coupling.** An abstraction that leaks, or that everything must import, is a coupling amplifier. Measure the heuristic by the coupling it removes, not by the indirection it adds.
- **Generation speed is the multiplier, not a new principle.** Don't invent AI-specific design rules; apply the durable ones earlier and more deliberately because the blast radius of being wrong is larger.
