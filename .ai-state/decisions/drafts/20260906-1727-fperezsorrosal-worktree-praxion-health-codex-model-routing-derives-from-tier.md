---
id: dec-draft-41df8a7a
title: The Codex model adapter keys on the routing rule's Tier column, never on a Claude alias literal
status: proposed
category: architectural
date: 2026-09-06
summary: CODEX_MODEL_TIER_ADAPTER is re-keyed from the Alias column (opus/sonnet/haiku) to the Tier column (H/M/L), so a Claude-side alias change or full-ID pin can never desynchronise the Codex export from rules/swe/agent-model-routing.md.
tags: [codex, model-routing, adapter, export, coupling, fitness]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-health
pipeline_tier: full
dissent: Re-keying moves the fail-loud boundary. Under the alias keying, an unrecognised alias raised immediately and pointed at the exact desync; under tier keying, the adapter accepts any alias silently, so a genuinely wrong alias in the rule (a typo, a model that does not exist) now flows into the export unremarked and is caught only downstream, if at all. The exchange is real, not free.
affected_files:
  - codex/config/export-codex-pipeline-adapter.py
  - codex/config/export-codex-agents.py
  - scripts/test_export_codex_pipeline_adapter.py
  - rules/swe/agent-model-routing.md
---

## Context

`rules/swe/agent-model-routing.md` § Tier Table is the canonical subagent routing table. Its
columns are `Agent | Tier | Alias | Rationale`. The `Tier` cell (`H` / `M` / `L`) is the
*semantic* unit — the statement about how much capability an agent's work warrants. The
`Alias` cell is a *Claude-side resolution detail*: which string Claude Code's Agent tool
accepts to reach that tier today.

`codex/config/export-codex-pipeline-adapter.py:53` keys `CODEX_MODEL_TIER_ADAPTER` on the
Alias cell (`{"opus", "sonnet", "haiku"}`), and `export_model_routing()` raises
`PipelineAdapterError: missing Codex model adapter for alias: <x>` for any alias outside that
set (line 193). On 2026-08-30, commit `a6984b73` pinned the L tier to `claude-haiku-4-5`
because the bare `haiku` alias silently resolves to Haiku 3.5 — a correct, necessary,
Claude-side fix. It broke the Codex export, and through it eight tests: two in
`scripts/test_export_codex_pipeline_adapter.py`, two in `scripts/test_export_codex_agents.py`
(which loads routes through this exporter), and five in `scripts/test_install_codex.py`.

The desync is structural, not incidental. The adapter's dependency on the rule is an edge
whose payload is the most volatile cell in the table. The rule's own § Principles #3 already
says aliases decay and warns that the L-tier pin is a standing exception forced by that decay
— the adapter binds to exactly the column the rule declares unstable. `scripts/test_export_codex_pipeline_adapter.py:63`
compounds it by asserting `doc_engineer["canonical_alias"] == "haiku"`, encoding the stale
alias in the test rather than deriving the expectation from the rule.

## Decision

**Key the Codex model adapter on the `Tier` column.** `CODEX_MODEL_TIER_ADAPTER` becomes
`{"H": {...}, "M": {...}, "L": {...}}`; `export_model_routing()` looks up
`row["tier"]` and raises `missing Codex model adapter for tier: <x>` when the rule introduces
a tier the adapter does not know. Consequences of the re-key, stated explicitly so the
implementer does not have to infer them:

1. **`codex_tier` becomes a derived function of the `Tier` column** — `H → high`, `M → medium`,
   `L → low`. Its *values* are unchanged, so `export-codex-agents.py`'s
   `CODEX_MODEL_SETTINGS_BY_TIER` lookup (`codex/config/export-codex-agents.py:171-172`)
   is untouched. Only the adapter's key vocabulary changes.
2. **`canonical_alias` stays in `model_routing.json` as an opaque pass-through.** It is
   informational provenance — "this is what the Claude-side rule says today" — and the adapter
   makes no decision from it. It must be copied verbatim, including a full model ID.
3. **`tier_mapping` is re-keyed `H`/`M`/`L`** in the emitted `model_routing.json`. This is a
   schema change to a generated artifact; the only in-repo reader is
   `export-codex-agents.py`, which reads `agent_routes[].codex_adapter.codex_tier` and never
   `tier_mapping`. The exporter's `notes` array must be amended to state that the mapping is
   keyed by canonical *tier*, not by Claude alias.
4. **The adapter must contain no alias literal.** `"opus"`, `"sonnet"`, `"haiku"` and any
   `claude-*` string disappear from `codex/config/export-codex-pipeline-adapter.py`. That is
   the property the invariant test below asserts, and it is what makes a future alias change
   a no-op for Codex.

**Invariant test (the one that would have caught this).** Two assertions, both derived from
the rule rather than hard-coded:

- **T1 — totality**: parse `rules/swe/agent-model-routing.md` § Tier Table and assert every
  row's `Tier` cell resolves through `CODEX_MODEL_TIER_ADAPTER`. This is the direct
  regression guard: it fails the moment the rule adds a tier the adapter has not been taught.
- **T2 — no alias literal**: assert the adapter source contains no Claude alias literal
  (`grep`-equivalent over the module source for `opus|sonnet|haiku|claude-`). This is the
  stronger guard, because it fails at *authoring* time if someone re-introduces alias coupling,
  rather than waiting for an alias to change.

**Tests derive expectations from the rule.** `scripts/test_export_codex_pipeline_adapter.py`
must stop asserting `canonical_alias == "haiku"`. The `doc-engineer` assertions become:
`canonical_tier == "L"` and `codex_adapter["reasoning_effort"] == "low"`, with any
alias assertion re-derived by parsing the rule's own table (the `systems-architect` row's
`canonical_alias == "opus"` assertion has the same defect and gets the same treatment). A
doc-contract test that hard-codes the value it is meant to be checking *against* is not a
contract test.

## Considered Options

### A — Widen `CODEX_MODEL_TIER_ADAPTER` to accept `claude-haiku-4-5`

Pros: one line; fixes eight tests today. Cons: fixes the instance, not the class. The next
alias change (or the `opus`/`sonnet` aliases rolling to a pinned full ID, which § Principles #3
anticipates) breaks it identically. The adapter would still bind the volatile column.

### B (chosen) — Re-key on the `Tier` column; forbid alias literals in the adapter

Pros: removes the coupling to the volatile cell entirely; the adapter depends on the rule's
stable semantic unit; T2 makes the property structurally enforced rather than remembered.
Cons: `tier_mapping`'s keys change in a generated artifact; the fail-loud boundary moves (see
`dissent:`); one exporter and three test modules change together.

### C — Key on tier but keep a secondary alias validation table

Pros: preserves the fail-loud-on-unknown-alias behaviour the `dissent:` misses. Cons:
reintroduces the exact coupling this decision removes, on a second surface. Validating that
the rule's aliases are *real Claude models* is a Claude-side concern that belongs in a rule
fitness check, not in the Codex export path — a different component's job.

## Consequences

**Positive.** Eight tests go green from one root-cause change. The rule and the Codex export
can no longer desynchronise on an alias; the only way to break the export is to add a *tier*,
which is a deliberate, rare, semantically loaded act — and T1 fails loudly on it. T2 prevents
regression by construction rather than by discipline. `codex/` stops carrying Claude-side
vocabulary, which is the stated intent of the exporter's own `notes` ("Canonical Claude
aliases remain source semantics; Codex model IDs are intentionally not pinned here").

**Negative.** A generated artifact's schema changes (`tier_mapping` keys). An invalid alias in
the rule now reaches `model_routing.json` unvalidated — see `dissent:`; the mitigation is that
the Claude-side rule is where alias validity belongs and Codex was never the right place to
learn about it. Three test modules change in the same commit as the exporter.

## Disconfirmation

**Falsifier.** A future change that must vary Codex model selection *within* one tier —
e.g. routing `doc-engineer` and `researcher`-simple-lookup, both L, to different Codex models.
Tier keying cannot express that; alias keying accidentally could. If that requirement lands,
the tier is the wrong grain and this decision is wrong.

**Steelmanned runner-up (Option A).** The cheapest correct-today fix is one dictionary key.
Praxion's Codex surface is secondary — an export path with no known external consumer — and
this decision spends an ADR, an exporter rewrite and three test-module edits on a surface that
breaks roughly once per alias change (twice in the project's life). "Add the key, move on" is
a defensible reading of Simplicity First, and the strongest thing against this decision is that
the coupling it removes has cost ~20 minutes of repair, twice.

**Reversal trigger.** Either (i) the falsifier above lands — a per-agent Codex model
distinction inside one tier; or (ii) the routing rule's `Tier` column is itself removed or
stops being the semantic unit (e.g. routing moves to per-agent effort budgets with no tier
letter), at which point the adapter should re-key to whatever the new semantic unit is, not
fall back to aliases.
