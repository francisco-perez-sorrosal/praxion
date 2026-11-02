---
core: false
load: always_on
install: hook-deliver
resident_of: rules/swe/agent-model-routing.md
---

## Agent Model Routing

Tier table for Praxion subagents. Resolution order at spawn:

1. Per-spawn `model` on the Agent tool (orchestrator's lever)
2. Frontmatter `model:` (capability floor; `inherit` takes the main session model)
3. `CLAUDE_CODE_SUBAGENT_MODEL` env (a kill switch only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, which also ignores frontmatter)
4. Main session model (fallback)

Aliases: `opus`/`sonnet` track the newest generation on the Anthropic API (Opus 5.5 / Sonnet 5.5 today); `haiku` is never below Haiku 4.5. The Agent tool's per-spawn `model` takes an alias only, never a full ID; pin one in frontmatter only when version-locking.

**Orchestrator directive.** A spawn that passes no `model` runs at its definition's `model:` floor, which the parity gate (`scripts/check_model_routing_parity.py`) holds equal to the Tier Table in `rules/swe/agent-model-routing.md`, so omit `model` by default. Pass a per-spawn `model` only for a sanctioned deviation listed here.

- `discipline-consultant`: pass `opus` unless the matched registry row's `difficulty-hint` is `routine`, which omits `model` and runs on the `sonnet` floor.
- `test-engineer` in `Mode: acceptance-design`, resumes included: pass `opus`.
- `verifier` in `Mode: light-review`: pass `sonnet`.
- `researcher`: its modes route up to `opus` or down to `haiku`; selection signals in the policy reference.
- `implementer`: the planner's step hint routes it, `tier: H` to `opus` and `tier: L` to `haiku`; no hint omits `model`.

Full policy: `skills/agent-crafting/references/model-routing-policy.md`.
