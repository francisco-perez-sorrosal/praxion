---
core: false
load: always_on
install: hook-deliver
resident_of: rules/swe/agent-model-routing.md
---

## Agent Model Routing

Tier table for Praxion subagents. Resolution order at spawn:

1. `CLAUDE_CODE_SUBAGENT_MODEL` env (operator kill switch)
2. Per-spawn `model` on the Agent tool (orchestrator's lever)
3. Frontmatter `model:` (capability floor)
4. Main session model (fallback)

Aliases for `opus`/`sonnet` (they track the newest generation — Opus 5 / Sonnet 5 today). The L tier pins `claude-haiku-4-5` because the bare `haiku` alias resolves to Haiku 3.5, a silent two-generation downgrade. Otherwise pin full IDs at spawn time only when version-locking.

**Orchestrator directive.** A spawn that passes no `model` runs at its definition's `model:` floor, which the parity gate (`scripts/check_model_routing_parity.py`) holds equal to the Tier Table in `rules/swe/agent-model-routing.md`, so omit `model` by default. Pass a per-spawn `model` only for a sanctioned deviation listed here.

- `discipline-consultant`: pass `opus` unless the matched registry row's `difficulty-hint` is `routine`, which omits `model` and runs on the `sonnet` floor.
- `test-engineer` in `Mode: acceptance-design`, resumes included: pass `opus`.
- `verifier` in `Mode: light-review`: pass `sonnet`.
- `researcher`: its modes route up to `opus` or down to the L tier (identified by the pin `claude-haiku-4-5`, not a value to pass); selection signals in the policy reference.
- `implementer`: the planner's step hint routes it, `tier: H` to `opus` and `tier: L` to the L tier; no hint omits `model`.

Full effort-routing policy, researcher routing modes, kill-switch precedence, per-spawn overrides, and quality-cliff guards: `skills/agent-crafting/references/model-routing-policy.md`.
