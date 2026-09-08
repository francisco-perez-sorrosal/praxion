---
codex:
  portability: claude_only
core: false
load: always_on
install: hook-deliver
---

## Agent Model Routing

Tier table for Praxion subagents. Resolution order at spawn:

1. `CLAUDE_CODE_SUBAGENT_MODEL` env (operator kill switch)
2. Per-spawn `model` on the Agent tool (orchestrator's lever)
3. Frontmatter `model:` (capability floor)
4. Main session model (fallback)

Aliases for `opus`/`sonnet` (they track the newest generation — Opus 5 / Sonnet 5 today). The L tier pins `claude-haiku-4-5` because the bare `haiku` alias resolves to Haiku 3.5, a silent two-generation downgrade. Otherwise pin full IDs at spawn time only when version-locking.

**Orchestrator directive.** When spawning any agent below, pass that row's `model: <alias>` as the Agent tool's `model` parameter on every spawn. Skipping it lets the agent fall through to the session model, defeating the policy. Deviate from the table only on the sanctioned cases documented in `skills/agent-crafting/references/model-routing-policy.md` (researcher modes, implementer step-level hint).

### Tier Table

| Agent | Tier | Alias | Rationale |
|-------|------|-------|-----------|
| `systems-architect` | H | `opus` | Trade-offs, ADRs, cross-codebase reasoning |
| `promethean` | H | `opus` | Ideation, multi-lens synthesis, long-horizon framing |
| `roadmap-cartographer` | H | `opus` | Multi-phase synthesis, 6-way fan-out |
| `verifier` | H | `opus` | Quality-critical gate; structural reasoning |
| `architect-validator` | H | `opus` | Structural reasoning across DSL + code graph + ADR set; pre-merge gate |
| `interface-designer` | H | `opus` | Design taste under trade-offs across web/TUI/API/agentic surfaces; like systems-architect/verifier, value is quality judgement across a broad space |
| `agentic-transactions-architect` | H | `opus` | Domain-expert shadow sub-architect: mandate/finality/ToS/HITL judgment in a regulated, high-stakes, fast-moving domain; peers with systems-architect and interface-designer |
| `discipline-consultant` | H | `opus` | Adversarial specialist judgment against a draft; frontmatter floor is `sonnet` so a `routine` consult can route down — the only sanctioned downgrade |
| `implementation-planner` | M | `sonnet` | Feature-scoped decomposition |
| `implementer` | M | `sonnet` | Single-step execution; step-H/L override |
| `test-engineer` | M | `sonnet` | Per-step judgment paired with implementer |
| `context-engineer` | M | `sonnet` | Placement, conflict detection |
| `researcher` | M | `sonnet` | Default; modes route up or down |
| `cicd-engineer` | M | `sonnet` | Pipeline design, security review |
| `sentinel` | M | `sonnet` | Mechanical scan + judgment |
| `skill-genesis` | M | `sonnet` | Triage, dedup, autonomous report writing |
| `doc-engineer` | L | `claude-haiku-4-5` | Mechanical doc verification, pattern writing; pinned full ID (see alias note above) |

Full effort-routing policy, researcher routing modes, kill-switch precedence, per-spawn overrides, and quality-cliff guards: `skills/agent-crafting/references/model-routing-policy.md`.

Governs subagent routing inside Claude Code. For direct Claude API / SDK consumers, see [`skills/claude-ecosystem/SKILL.md`](../../skills/claude-ecosystem/SKILL.md).
