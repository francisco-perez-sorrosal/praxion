## Agent Model Routing

Tier table for Praxion subagents. Resolution order at spawn:

1. `CLAUDE_CODE_SUBAGENT_MODEL` env (operator kill switch)
2. Per-spawn `model` on the Agent tool (orchestrator's lever)
3. Frontmatter `model:` (capability floor)
4. Main session model (fallback)

Aliases only (`opus`/`sonnet`/`haiku`); pin full IDs at spawn time only when version-locking.

**Orchestrator directive.** When spawning any agent in the table below, pass `model: <alias>` from that row as the Agent tool's `model` parameter on every spawn. Do not skip: an agent without an explicit override falls through to the session model and defeats the policy. Use a per-spawn override that differs from the table only on the sanctioned cases (researcher modes, implementer step-level hint) documented below.

### Tier Table

| Agent | Tier | Alias | Rationale |
|-------|------|-------|-----------|
| `systems-architect` | H | `opus` | Trade-offs, ADRs, cross-codebase reasoning |
| `promethean` | H | `opus` | Ideation, multi-lens synthesis, long-horizon framing |
| `roadmap-cartographer` | H | `opus` | Multi-phase synthesis, 6-way fan-out |
| `verifier` | H | `opus` | Quality-critical gate; structural reasoning |
| `implementation-planner` | M | `sonnet` | Feature-scoped decomposition |
| `implementer` | M | `sonnet` | Single-step execution; step-H/L override |
| `test-engineer` | M | `sonnet` | Per-step judgment paired with implementer |
| `context-engineer` | M | `sonnet` | Placement, conflict detection |
| `researcher` | M | `sonnet` | Default; modes route up or down |
| `cicd-engineer` | M | `sonnet` | Pipeline design, security review |
| `sentinel` | M | `sonnet` | Mechanical scan + 10-dimension judgment |
| `skill-genesis` | M | `sonnet` | Triage, dedup, interactive proposals |
| `doc-engineer` | L | `haiku` | Mechanical doc verification, pattern writing |

### Principles

1. **Frontmatter `model:` is a capability floor** — minimum tier; the rule may route up, never below.
2. **Fan-out amplifiers** — `researcher` (up to 6×), `implementer` + `test-engineer` (2–3×) multiply mis-routes.
3. **Aliases only in always-loaded surfaces** — full IDs decay; pin at spawn time only when version-locking.
4. **Override precedence is the lever** — per-spawn `model:` beats frontmatter; reach for it sparingly.

### Researcher Routing Modes

| Mode | Tier | Mechanism | Selection signals |
|------|------|-----------|-------------------|
| Simple lookup | L (`haiku`) | per-spawn override | single file/URL named in the prompt; single grep target; "find/read/check X" framing; no comparison |
| Default (comparative analysis, multi-source synthesis) | M (`sonnet`) | rule-table tier | external research; ≥2 sources to weigh; codebase exploration that returns prose synthesis; broad "how does X work" framing |
| Contested evidence, heavy multi-option judgment | H (`opus`) | per-spawn override | ≥3 plausible options with conflicting evidence; trade-off resolution required; downstream architect explicitly asks for "feasibility verdict" or "decision rationale" |

**Implementer step-level override.** Planner annotates `WIP.md` with `tier: H` (cross-cutting refactor) or `tier: L` (typo/mechanical); no hint = `sonnet`.

**Direct-invocation entry points.** Slash commands and user-driven spawns (e.g. `/sentinel`, `/roadmap`, `/eval`, ad-hoc `Agent` calls) bypass the main orchestrator. The entry point is responsible for applying this rule: read the row for the agent being spawned and pass the listed alias as the Agent tool's `model:` parameter. `sentinel` and `skill-genesis` are the agents most often invoked this way; both default to `sonnet` unless the entry point overrides up.

### Operator Kill Switch — `CLAUDE_CODE_SUBAGENT_MODEL`

| Scenario | Value | Effect |
|----------|-------|--------|
| Emergency cost cap | `haiku` | All spawns on Haiku; accept quality degradation |
| Emergency quality boost | `opus` | All spawns on Opus; accept cost spike |
| Disable kill switch | (unset / not set) | Layer-1 disengages; per-spawn / frontmatter / session resume control per layers 2–4 |

**`availableModels` fallback.** If a routed alias is rejected by `availableModels`, fall back to the next-cheaper tier (Opus → Sonnet → Haiku). Log each fallback event: in-pipeline, append a one-line entry to `LEARNINGS.md` § Edge Cases naming the rejected alias, the chosen fallback, and the spawning agent; outside a pipeline, the orchestrator surfaces the fallback in its session text so the operator can correct the managed setting.

**Opus breaking-change note.** Some Opus versions reject `thinking.budget_tokens` and non-default `temperature`/`top_p`/`top_k` with HTTP 400; never pass these on routed Opus spawns. *Specific to Opus 4.7 as of 2026-04-25 — verify against `claude-ecosystem` skill before relaxing if a later version restores the params.*

### Quality-Cliff Guards

- **Deep scientific or math reasoning** — do not downgrade below Opus.
- **Long-horizon autonomous coding (>10 tool calls)** — do not downgrade below Sonnet.
- **Cross-codebase refactoring** — Opus when planner flags `tier: H`.
- **`verifier`** — never downgrade; structural-coherence reasoning is load-bearing.

Governs subagent routing inside Claude Code. For direct Claude API / SDK consumers, see [`skills/claude-ecosystem/SKILL.md`](../../skills/claude-ecosystem/SKILL.md).
