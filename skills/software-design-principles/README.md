# Software Design Principles (AI Era)

The canonical home for software *design* discipline in Praxion: SOLID reframed as
heuristics in service of **balanced coupling** (managing knowledge flow between
components), plus the agent-as-consumer lens for the AI era. Operationalizes the
`CLAUDE.md§Balanced Coupling` principle.

## When to Use

- Applying or reviewing SOLID (SRP, OCP, LSP, ISP, DIP) on any unit — function, module, service, or agent tool.
- Deciding whether an abstraction earns its place, or reducing coupling / improving cohesion.
- Designing module and interface boundaries **up-front**, before code exists.
- Designing a surface an AI agent will consume (MCP tool, API, contract).
- Judging whether a fast-generated design will accrue debt at machine speed.

Not for: reactive code cleanup (use `refactoring`) or step decomposition (use
`software-planning`) — both *compose with* this skill rather than replace it.

## Activation

Auto-activates on design-principle vocabulary (SOLID, coupling, cohesion,
dependency inversion, modularity, balanced coupling, "design for agents"). The
skill is guidance, applied with judgment under Pragmatism and Incremental
Evolution — heuristics, not commandments.

## Skill Contents

- `SKILL.md` — the one idea (balanced coupling: strength × distance × volatility), the AI-era stakes, SOLID-as-heuristics table, when-to-apply / when-not, enforcement seam, pipeline composition, gotchas.
- `references/solid-heuristics.md` — each SOLID principle reframed through knowledge flow, with the failure it prevents and language-agnostic sketches.
- `references/agent-as-consumer.md` — design when the consumer is an AI agent: machine-interpretable contracts, composable capabilities, context-as-coupling, spec-as-source-of-truth.

## Related Skills

- `software-planning` — applies this canon **up-front** (boundary choice during architecture).
- `refactoring` — applies it **reactively** (its Four Pillars are this canon restored in drifted code).
- `architectural-fitness-functions` — makes a chosen invariant executable; cites `CLAUDE.md§Balanced Coupling`.
- `agentic-interface-design`, `api-design-craft` — the craft of the agent- and client-facing surfaces this skill reasons about at the principle level.
