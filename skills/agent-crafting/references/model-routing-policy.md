# Model Routing Policy

Effort routing, researcher routing modes, kill-switch precedence, per-spawn overrides, and quality-cliff guards for Praxion subagent model selection — the operational detail behind [`../SKILL.md`](../SKILL.md) and the resident Tier Table in `rules/swe/agent-model-routing.md`.

## Effort Routing

Per-agent `effort:` lives in agent frontmatter (single source of truth — this rule states only the policy): `xhigh` for H-tier judgment work plus the implementation-planner (plan quality gates the whole pipeline), `high` for M-tier execution, `medium` for cost-tolerant triage (`skill-genesis`), and none for the L tier — Haiku 4.5 rejects the `effort` parameter. `max` is prone to overthinking; request it per-spawn only when correctness outweighs cost. Precedence: `CLAUDE_CODE_EFFORT_LEVEL` env > settings `effortLevel` > frontmatter `effort` > model default (`high`).

## Principles

1. **Frontmatter `model:` is a capability floor** — minimum tier; the rule may route up, never below.
2. **Fan-out amplifiers** — `researcher` (up to 6×), `implementer` + `test-engineer` (2–3×) multiply mis-routes.
3. **Aliases only in always-loaded surfaces** — full IDs decay; pin at spawn time only when version-locking. Sole standing exception: the L tier's `claude-haiku-4-5` pin, forced by the stale `haiku` alias.
4. **Override precedence is the lever** — per-spawn `model:` beats frontmatter; reach for it sparingly.

## Researcher Routing Modes

| Mode | Tier | Mechanism | Selection signals |
|------|------|-----------|-------------------|
| Simple lookup | L (`claude-haiku-4-5`) | per-spawn override | single file/URL named in the prompt; single grep target; "find/read/check X" framing; no comparison |
| Default (comparative analysis, multi-source synthesis) | M (`sonnet`) | rule-table tier | external research; ≥2 sources to weigh; codebase exploration that returns prose synthesis; broad "how does X work" framing |
| Contested evidence, heavy multi-option judgment | H (`opus`) | per-spawn override | ≥3 plausible options with conflicting evidence; trade-off resolution required; downstream architect explicitly asks for "feasibility verdict" or "decision rationale" |

**Implementer step-level override.** Planner annotates `WIP.md` with `tier: H` (cross-cutting refactor) or `tier: L` (typo/mechanical); no hint = `sonnet`.

**Direct-invocation entry points.** Slash commands and user-driven spawns (e.g. `/sentinel`, `/roadmap`, `/eval`, `/eval-praxion`, ad-hoc `Agent` calls) bypass the orchestrator, so the entry point applies this rule: read the agent's row and pass its alias as the `model:` parameter. `sentinel` and `skill-genesis` are most often invoked this way; both default to `sonnet` unless overridden up.

## Operator Kill Switch — `CLAUDE_CODE_SUBAGENT_MODEL`

| Scenario | Value | Effect |
|----------|-------|--------|
| Emergency cost cap | `claude-haiku-4-5` | All spawns on Haiku 4.5 (never the bare `haiku` alias — that lands on 3.5); accept quality degradation |
| Emergency quality boost | `opus` | All spawns on Opus; accept cost spike |
| Disable kill switch | (unset / not set) | Layer-1 disengages; per-spawn / frontmatter / session resume control per layers 2–4 |

**`availableModels` fallback.** If a routed alias is rejected, fall back to the next-cheaper tier (Opus → Sonnet → Haiku) and log it: in-pipeline, a one-line `LEARNINGS.md` § Edge Cases entry naming the rejected alias, the fallback, and the spawning agent; outside a pipeline, surface it in session text so the operator can fix the managed setting.

**Model-generation note.** The Claude 5 family (Opus 5, Sonnet 5) rejects `thinking.budget_tokens` and non-default `temperature`/`top_p`/`top_k` with HTTP 400 — thinking is adaptive by default; control depth via `effort`, never via those params on routed spawns. Haiku 4.5 additionally rejects `effort`. *Verified 2026-08-30 against the `claude-api` skill; re-verify there before relaxing.*

## Per-Spawn Overrides

| Scenario | Agent | Override | Rationale |
|----------|-------|----------|-----------|
| Intra-step pair-review (`Mode: light-review`) | `verifier` | `sonnet` | Step-scoped diff review only; not a whole-pipeline quality gate. Sanctioned per-spawn override below the `opus` floor. |

## Quality-Cliff Guards

- **Deep scientific or math reasoning** — do not downgrade below Opus.
- **Long-horizon autonomous coding (>10 tool calls)** — do not downgrade below Sonnet.
- **Cross-codebase refactoring** — Opus when planner flags `tier: H`.
- **`verifier`** — never downgrade; structural-coherence reasoning is load-bearing.
