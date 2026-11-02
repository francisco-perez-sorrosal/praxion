---
paths: [agents/**, skills/agent-crafting/references/model-routing-policy.md]
codex:
  portability: claude_only
core: false
load: path_scoped
install: symlink
---

## Agent Model Routing

Tier table for Praxion subagents. Resolution order at spawn:

1. Per-spawn `model` on the Agent tool (orchestrator's lever)
2. Frontmatter `model:` (capability floor; `inherit` takes the main session model)
3. `CLAUDE_CODE_SUBAGENT_MODEL` env (a kill switch only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, which also ignores frontmatter)
4. Main session model (fallback)

Aliases: `opus`/`sonnet` track the newest generation (Opus 5 / Sonnet 5 today); `haiku` is never below Haiku 4.5. The Agent tool's per-spawn `model` takes an alias only, never a full ID; pin one in frontmatter only when version-locking.

`haiku` is Haiku 5.5 on the Anthropic API and Haiku 4.5 on Bedrock, Google Cloud's Agent Platform, Foundry and Claude Platform on AWS.

**Orchestrator directive.** A spawn that passes no `model` runs at its definition's `model:` floor, which the parity gate (`scripts/check_model_routing_parity.py`) holds equal to the Tier Table in `rules/swe/agent-model-routing.md`, so omit `model` by default. Pass a per-spawn `model` only for a sanctioned deviation listed here.

- `discipline-consultant`: pass `opus` unless the matched registry row's `difficulty-hint` is `routine`, which omits `model` and runs on the `sonnet` floor.
- `test-engineer` in `Mode: acceptance-design`, resumes included: pass `opus`.
- `verifier` in `Mode: light-review`: pass `sonnet`.
- `researcher`: its modes route up to `opus` or down to `haiku`; selection signals in the policy reference.
- `implementer`: the planner's step hint routes it, `tier: H` to `opus` and `tier: L` to `haiku`; no hint omits `model`.

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
| `discipline-consultant` | H | `opus` | Adversarial specialist judgment against a draft; frontmatter floor is `sonnet` so a `routine` consult routes down, one of two sanctioned downgrades with the verifier's light review |
| `implementation-planner` | M | `sonnet` | Feature-scoped decomposition |
| `implementer` | M | `sonnet` | Single-step execution; step-H/L override |
| `test-engineer` | M | `sonnet` | Outer-loop test judgment; acceptance-design mode spawns at `opus` |
| `context-engineer` | M | `sonnet` | Placement, conflict detection |
| `researcher` | M | `sonnet` | Default; modes route up or down |
| `cicd-engineer` | M | `sonnet` | Pipeline design, security review |
| `sentinel` | M | `sonnet` | Mechanical scan + judgment |
| `skill-genesis` | M | `sonnet` | Triage, dedup, autonomous report writing |
| `doc-engineer` | L | `haiku` | Mechanical doc verification, pattern writing |

Full policy: `skills/agent-crafting/references/model-routing-policy.md`.

Governs subagent routing inside Claude Code. For direct Claude API / SDK consumers, see [`skills/claude-ecosystem/SKILL.md`](../../skills/claude-ecosystem/SKILL.md).
