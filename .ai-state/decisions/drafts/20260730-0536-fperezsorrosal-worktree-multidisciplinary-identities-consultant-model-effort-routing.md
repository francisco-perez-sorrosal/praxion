---
id: dec-draft-459098fa
title: Consultant difficulty routing — per-spawn model is real, per-spawn API effort is not settable; ultrathink is the honest fallback
status: proposed
category: architectural
date: 2026-07-30
summary: Difficulty-keyed heterogeneity for the discipline consultant uses the verified per-spawn model parameter plus the ultrathink prompt keyword; per-invocation API effort is not settable for a subagent spawn today, so no effort column enters the routing table and dec-076's 1D policy is re-affirmed rather than superseded.
tags: [multidisciplinary-identities, discipline-consultant, model-routing, effort-parameter, heterogeneity, harness-verification, dec-076]
made_by: agent
agent_type: systems-architect
branch: worktree-multidisciplinary-identities
pipeline_tier: full
re_affirms: dec-076
affected_files:
  - rules/swe/agent-model-routing.md
  - agents/discipline-consultant.md
  - skills/multi-perspective-analysis/references/discipline-registry.md
affected_reqs:
  - REQ-06
  - REQ-07
dissent: A design that answers a two-axis mandate with one real axis and one prompt keyword has substituted a soft lever for a hard one, and calling that compliance overstates it — the honest reading is that half of ruling 3 is currently unimplementable, and a caller who reads the routing table will see a difficulty policy whose depth dimension does nothing measurable at the API layer.
---

## Context

The user's binding ruling opened heterogeneity on **two axes — model AND reasoning effort** — keyed to task
difficulty, with the routing policy required to be **generic**, never per-discipline (a per-discipline row in
`rules/swe/agent-model-routing.md` would convert routing into a structural per-discipline cost and fail the
extensibility criterion).

The external evidence supports the intent strongly. Every retrieved result where diversity *improved outcomes*
varied the **model backbone**, not the persona; a single-Opus floor forecloses the one diversity axis with
replicated evidence behind it. Concurrent instances at mixed tiers also compose directly with the existing
Haiku-proposer / Opus-aggregator recipe.

Before specifying a parameter, both axes were verified against current Claude Code documentation rather than
assumed:

| Lever | Per-spawn settable? | Evidence |
|---|---|---|
| `model` | **Yes** | *"When Claude invokes a subagent, it can also pass a `model` parameter for that specific invocation"*, with documented precedence `CLAUDE_CODE_SUBAGENT_MODEL` → per-invocation → frontmatter → session |
| `effort` | **No** | Documented only as a subagent **frontmatter** field (*"Effort level when this subagent is active"*) or as session scope (`/effort`, `--effort`, `CLAUDE_CODE_EFFORT_LEVEL`, `effortLevel`). No Agent-tool per-invocation parameter is documented |
| per-subagent thinking budget | **No** | *"There is no per-subagent thinking setting"*; subagents inherit the session's extended-thinking configuration. `agent-model-routing.md` separately forbids `thinking.budget_tokens` on routed Opus |
| `ultrathink` prompt keyword | **Yes** | Recognized keyword that *"adds an in-context instruction. **The effort level sent to the API is unchanged**"*. `think hard` / `think more` are explicitly **not** keywords |
| Effort support breadth | — | Fable 5 / Opus 5 / Sonnet 5 / Opus 4.8 / 4.7 expose five levels; Opus 4.6 / Sonnet 4.6 four; **Haiku is absent from the table** and *"models not listed here do not support effort"* |

`dec-076` deferred 2D (model × effort) routing pending either telemetry showing an agent spending >30% of tokens
on easy-case workload, **or** Anthropic extending `effort` uniformly across tiers *including Haiku*. Ruling 3
forced that deferral to be re-examined.

## Decision

**Realize the model axis fully per-spawn. Do not specify a per-spawn effort parameter, because none exists.
Use `ultrathink` as the per-spawn depth lever and say plainly what it is.**

The generic routing policy — one policy for the agent, **zero rows per discipline**:

| `difficulty-hint` (from the registry row) | Per-spawn `model` | Per-spawn prompt modifier | API effort |
|---|---|---|---|
| `routine` | `sonnet` | — | session default |
| `standard` | `opus` | — | session default |
| `high-stakes` | `opus` | `ultrathink` in the spawn prompt | session default (unchanged) |

The registry row carries only a `difficulty-hint` *label*; it never carries a model alias. The mapping from
label to alias lives once, in the policy, so a new discipline adds no routing surface.

**Frontmatter `model:` is `sonnet`, not `opus`.** A frontmatter pin is a *capability floor* by this repository's
own routing principle, so pinning `opus` would foreclose the cheap-proposer half of the ruling and the
Haiku-proposer / Opus-aggregator composition. The frontier-tier evidence (frontier-only synergy for
multi-persona collaboration; the standing quality-cliff guard *"deep scientific or math reasoning — do not
downgrade below Opus"*) is honoured at the **policy** layer instead: the `statistician` row carries
`difficulty-hint: standard` as its minimum, so it routes to `opus` by default and reaches `sonnet` only on an
explicitly `routine` consult. The agent's tier-table row is **H / `opus`**, preserving the orchestrator
directive; `sonnet` is reachable only through the sanctioned per-spawn override, and the chosen `model` is
recorded in the disposition ledger so routing becomes auditable against outcomes.

The consultant sets **no** frontmatter `effort:`, inheriting the operator-controlled session level. A static
`effort:` would apply to every instance including cheap routine ones — blowing the ≤3×-routine cost envelope in
exchange for no difficulty-keying at all.

**Registered objection to ruling 3 as literally stated.** The ruling mandates per-instance reasoning-effort
selection. That is not settable for a plain subagent spawn today, and both obvious fallbacks are closed
(per-subagent thinking is explicitly absent; `thinking.budget_tokens` is forbidden on routed Opus). Specifying a
per-spawn `effort` parameter would be an unimplementable design that fails at first use. The ruling's **intent**
— two difficulty-keyed levers, generic policy, never per-discipline — is complied with using the levers that
verifiably exist, and the gap is disclosed rather than papered over.

## Considered Options

### Option 1 — Per-spawn `model` + per-spawn `effort` (ruling 3 as literally written)

- **Pros:** exactly what was asked for; two genuinely orthogonal cost-quality levers; API-measurable.
- **Cons:** not implementable. No Agent-tool per-invocation `effort` parameter is documented; the design would
  fail at first spawn and the failure would be silent (an unrecognized parameter, not an error).

### Option 2 — Per-spawn `model` + static frontmatter `effort:` on the consultant

- **Pros:** uses a real API-level effort setting; frontmatter `effort` is *not* in the list of fields ignored for
  plugin subagents, so it would take effect.
- **Cons:** static per definition, so it is not difficulty-keyed at all — it raises cost on every instance
  including routine ones, breaching the cost envelope while delivering none of the ruling's variation.

### Option 3 — Per-spawn `model` + `ultrathink` prompt keyword (chosen)

- **Pros:** both levers are per-spawn and verified; the model axis is the one with actual outcome evidence
  behind it; zero change to the routing table's dimensionality; composes with the existing heterogeneous
  orchestration recipe; the honest limitation is stated in the design rather than discovered later.
- **Cons:** `ultrathink` is a soft lever — it changes in-context instruction only and its effect is not
  observable in the API request, so the "depth" dimension of the policy is not measurable.

### Option 4 — Two agent definitions, one per effort band, to fake per-instance effort

- **Pros:** would deliver genuinely different API effort per instance.
- **Cons:** doubles the always-loaded `description:` cost and manufactures exactly the MAST duplicate-role
  failure the single-agent design exists to avoid. Rejected outright.

## Consequences

**Positive:** an implementable policy; the evidence-backed axis is fully realized; the global routing table stays
1D with no new column and no per-agent effort row; `difficulty-hint` labels keep the per-discipline routing cost
at zero; recording `model` in the ledger makes the real axis correlatable with disposition outcomes.

**Negative:** no genuine per-instance API-level effort variation, so half of the ruling's stated mechanism is
unavailable; a reader of the policy table could over-read what the `high-stakes` row buys.

**Risks accepted:** `ultrathink`'s effect is unmeasurable from the request, so the depth dimension cannot be
validated empirically the way the model dimension can. Also, `sonnet` as a frontmatter floor means an operator
misconfiguration could route statistical reasoning below the quality cliff; the `difficulty-hint: standard`
minimum on the `statistician` row is the guard, and it is policy rather than mechanism.

## Prior Decision

`dec-076` ("Routing dimensionality — 1D now, defer 2D (model × effort)") is **re-affirmed, not superseded**.
Re-examined at ruling 3's prompt, neither of its two named re-open triggers has fired:

- **Trigger (b) — uniform effort support across tiers including Haiku: not fired.** Haiku still does not appear
  in the effort-support table, and *"models not listed here do not support effort"*. The asymmetry `dec-076`
  cited has if anything widened, since newer models expose five levels while Opus 4.6 / Sonnet 4.6 expose four.
- **Trigger (a) — telemetry showing an agent spending >30% of tokens on easy-case workload: not fired.** No such
  telemetry exists.

Further, the harness constraint `dec-076` did not know about strengthens its conclusion rather than weakening it:
effort is not settable per-invocation at all, so a 2D *routing* policy could not be expressed per-spawn even if
support were uniform. The global table therefore **stays 1D**: no second column, no effort column, no per-agent
effort row. This design's difficulty axis is expressed entirely through the existing 1D mechanism — the
per-spawn `model` override, already sanctioned by `dec-076`'s own policy and by the rule's Per-Spawn Overrides
table — plus a prompt-level keyword that is explicitly **not** an API effort parameter.

The evidence a future supersession of `dec-076` would require, restated for the next reader: **a documented
Agent-tool per-invocation `effort` parameter**, or **uniform effort support across all routed tiers including
Haiku**. Either alone is sufficient to reopen; neither is present as of 2026-07-30.

## Disconfirmation

- **Falsifier:** ledger rows showing that `high-stakes` consults (routed `opus` + `ultrathink`) produce
  challenges with no better accepted rate than `standard` consults (`opus`, no keyword). That would mean the
  keyword lever is inert and the policy's third row is ceremony — collapsing the table to two rows keyed on
  model alone.
- **Steelmanned runner-up:** Option 2 (static frontmatter `effort:`). It is the only option that sets a *real*
  API effort value, and the argument for it is that a genuinely high effort floor on an agent whose entire job is
  deep methodological reasoning may be worth more than difficulty-keying — the consultant is convened rarely and
  behind a gate, so the routine-instance cost objection may be overstated in practice. If the ledger shows
  consults are overwhelmingly `standard`/`high-stakes` in reality and `routine` is almost never used, Option 2
  becomes the better design and the cost objection evaporates.
- **Reversal trigger:** Claude Code documenting a per-invocation `effort` parameter on the Agent tool, **or**
  extending effort support uniformly across all routed tiers including Haiku. Either fires both this ADR's
  revision and `dec-076`'s supersession, and the `difficulty-hint` label already in the registry becomes the
  input to a genuine 2D policy without any registry change.
