---
id: dec-204
title: Praxion self-eval v1 — `/eval-praxion` adds LLM-as-judge over completed artifacts (narrow supersession of dec-040 clause 3)
status: accepted
category: architectural
date: 2026-05-26
summary: v1 self-eval reads completed `.ai-state/` artifacts and runs LLM-as-judge calls out-of-band via `/eval-praxion`; narrowly supersedes dec-040 clause 3's implicit filesystem-only reading model; re-affirms clauses 1, 2, 4.
tags: [eval, quality, llm-as-judge, behavioral-contract, dec-040-supersession, eval-praxion]
made_by: agent
agent_type: systems-architect
branch: worktree-praxion-self-eval-v1
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/harness/
  - eval/src/praxion_evals/behavioral/
  - eval/src/praxion_evals/judges/anthropic.py
  - eval/src/praxion_evals/cli.py
  - commands/eval-praxion.md
  - .ai-state/praxion_eval_reports/
supersedes: dec-040
---

## Context

dec-040 (2026-04-13) established that the eval framework is strictly out-of-band — invoked only via the `/eval` slash command (user-initiated) or an opt-in CI job, never from any Claude Code lifecycle hook. Its four binding clauses, paraphrased:

1. Invocation via slash command or CI (opt-in).
2. No eval code invoked from any Claude Code lifecycle hook.
3. Evals *read completed artifacts* — never mutate live pipeline state, never start agents, never run during a pipeline.
4. Future eval tiers must preserve the out-of-band invocation pattern.

The `judges/anthropic.py` stub explicitly cites dec-040 as the deferral reason for Claude-as-judge:

```python
raise NotImplementedError("Tier 2 — Claude-as-judge deferred (dec-040)")
```

Two follow-on facts now drive a re-visit:

- **`td-005` (re-evaluated 2026-05-23)** records that the existing `eval/src/praxion_evals/regression/` package is shipped-but-broken (slug-keyed baselines with no comparison target, plus a `arize-phoenix` dep gap that silently swallows errors). The td-005 row anticipates "a new ADR partially superseding `dec-040` invocation discipline" as part of resolution.
- **Praxion's own pipeline outputs are eval-able today**: 5 archived `.ai-state/specs/SPEC_*.md`, 203 finalized ADRs, and `VERIFICATION_REPORT.md` artifacts emitting a standard behavioral-contract failure-mode tag vocabulary (`[UNSURFACED-ASSUMPTION]` / `[MISSING-OBJECTION]` / `[NON-SURGICAL]` / `[SCOPE-CREEP]` / `[BLOAT]` / `[DEAD-CODE-UNREMOVED]`). Both surfaces are *completed artifacts*, not live pipeline state — which is the strict letter of clause 3 — but evaluating them via an LLM-as-judge call to the Anthropic API extends the *reading model* implied by clause 3 beyond pure filesystem inspection.

The question is whether this LLM-as-judge extension constitutes (a) a behavioral coherent continuation of dec-040 needing no ADR action, (b) a partial supersession of clause 3, or (c) a full supersession of dec-040. It is (b).

## Decision

Add a new slash command `/eval-praxion` to the Praxion repo that:

1. Resolves a target (default = `main` branch HEAD via `git show`; arg-resolver order: existing path → known worktree name → valid git ref → error).
2. Reads completed artifacts from `.ai-state/specs/`, `.ai-state/decisions/`, and `.ai-work/<slug>/VERIFICATION_REPORT.md` (and equivalents via git-show plumbing for non-worktree targets).
3. Runs an LLM-as-judge call (Claude, structured-output JSON Schema) against each artifact under a published rubric.
4. Emits `.ai-state/praxion_eval_reports/PRAXION_EVAL_REPORT_<timestamp>.md` + appends a row to a sibling `PRAXION_EVAL_LOG.md`.

Auth is **hybrid (Path C)**: env-var detection picks Agent SDK (`CLAUDE_CODE_OAUTH_TOKEN`) or direct Messages API (`ANTHROPIC_API_KEY`) at runtime. A single `JudgeClient` adapter encapsulates the seam; eval families never branch on auth mode.

**Narrow supersession scope.** The new behavior narrows **only clause 3** of dec-040, and only its implicit "evals = filesystem-only reading" assumption. Clauses 1, 2, and 4 are re-affirmed verbatim. dec-040 stays `accepted` (not flipped to `superseded`) but carries a `superseded_by: dec-204` field pointing at this ADR's clause-3 narrowing; the prose `## Prior Decision` section below names exactly what is narrowed vs. re-affirmed.

**Scope re-affirmation in detail:**

- **Clause 1 — invocation via slash command or CI:** re-affirmed. `/eval-praxion` IS a slash command. Out-of-band invocation discipline is preserved.
- **Clause 2 — no hooks:** re-affirmed. `/eval-praxion` is never wired into any hook. The existing `commands/eval.md` invariant ("if any hook or agent script references `praxion_evals`, flag it as a bug") extends to the new command.
- **Clause 3 — "evals read completed artifacts":** narrowed. The original framing implied filesystem-only reads (`Phoenix traces` is named, but Phoenix is itself a completed-trace store). The narrowed model: completed artifacts may be *passed to an LLM-as-judge call* over the network for semantic judgment. The artifact content is the only input; no live pipeline state is read, no agents are spawned, no pipeline is interrupted. The LLM call is a *reading transformation*, not a mutation. Cost and rate-limit budgets are owned by the user's auth choice (subscription quota or API key billing).
- **Clause 4 — preserve out-of-band pattern for future work:** re-affirmed. Any Phase 5+ eval addition still inherits the slash-command-or-CI invocation contract.

**Out of scope of this ADR** — the full td-005 regression-mode redesign (tier/shape-keyed envelope baselines + Phoenix corpus question). This ADR resolves only the LLM-as-judge deferral; td-005's broader full redesign remains deferred. v1's contribution to td-005 is retiring the broken `regression/` package (448 LOC clean removal) and migrating the td-005 row to `TECH_DEBT_RESOLVED.md` with `resolved-by: dec-NNN` (the finalize step rewrites `dec-204` to `dec-NNN`).

## Considered Options

### Option 1 — Treat LLM-as-judge as a coherent continuation of dec-040; no ADR action

The stub's `raise NotImplementedError("...deferred (dec-040)")` is interpreted as scheduling, not prohibition. Just fill in the stub; the `commands/eval.md` invariant covers the invocation contract; nothing in dec-040 explicitly bans network calls.

- Pros: zero ADR ceremony; the simplest path.
- Cons: dec-040's clause 3 is structurally ambiguous about network reads; future readers will hit the same ambiguity. The stub citing dec-040 deserves a documented closure. Silent drift between rule-as-written and rule-as-practiced is a behavioral-contract failure mode the verifier and sentinel explicitly catch — Praxion's own eval framework should not normalize that pattern.

### Option 2 — Full supersession of dec-040

Replace dec-040 entirely. Re-state the full out-of-band model with explicit LLM-as-judge support.

- Pros: a single canonical ADR for the eval framework's invocation model.
- Cons: clauses 1, 2, 4 are unchanged — re-writing them adds drift risk and breaks all citations of dec-040 in the eval code (`judges/anthropic.py:7`, `commands/eval.md`, `eval/src/praxion_evals/tiers.py`). The narrow change does not warrant a wide rewrite.

### Option 3 — Narrow supersession of dec-040's clause 3 only (chosen)

Author this ADR. Set `supersedes: dec-040` in frontmatter, flag `superseded_by: dec-204` on dec-040, leave dec-040's `status: accepted` (the partial-supersession pattern from `~/.claude/agent-memory/i-am-systems-architect/partial_supersession_clause_pattern.md`). Use a `## Prior Decision` section to scope exactly which clause is narrowed vs. re-affirmed. Per the partial-supersession pattern, dec-040 can carry BOTH `superseded_by: dec-204` (for clause 3) AND `re_affirmed_by: [dec-204]` (for clauses 1, 2, 4) — the new ADR's body discriminates the scope of each link.

- Pros: surgical; preserves the load-bearing parts of dec-040; mirrors the project's existing partial-supersession idiom (e.g., dec-125 and dec-130 superseding fragments of earlier dashboard ADRs); makes the eval-framework history readable in three months.
- Cons: introduces a `## Prior Decision` section that future readers must read carefully to discern the narrowing scope. Mitigation: explicit "re-affirms clauses X" / "narrows clause Y" prose in this section.

## Consequences

**Positive:**

- Closes the `judges/anthropic.py` stub's `dec-040` citation with a documented ADR transition.
- Unblocks Praxion's self-eval roadmap for v1 without re-litigating settled out-of-band invocation discipline.
- Sets a precedent for narrowing one clause of a still-load-bearing ADR — a documented pattern future architects can mirror when dec-040-class ADRs evolve.
- Migrates `td-005`'s row from `TECH_DEBT_LEDGER.md` to `TECH_DEBT_RESOLVED.md` with `resolved-by: dec-NNN` (the finalize protocol rewrites `dec-204` to `dec-NNN`). td-005's *broader* full redesign (tier/shape-keyed envelopes + Phoenix corpus) remains deferred; the LLM-as-judge piece is resolved.
- Hybrid auth (Path C) means the framework runs cleanly across the user's machines regardless of which auth env var is exported, with one adapter encapsulating the seam.

**Negative:**

- LLM-as-judge calls cost real money (Sonnet ~$0.003-0.015/call, Haiku ~$0.0003-0.0015/call) — or draw from the user's subscription credit budget post-June-15-2026 if `CLAUDE_CODE_OAUTH_TOKEN` is the active auth path. The user pays this every `/eval-praxion` invocation; budget needs to be visible in the report output.
- The PASS-only family-#2 corpus available today (1 VERIFICATION_REPORT.md, all PASS, no BC violations observed) cannot calibrate the LLM judge for false-negative detection. v1 ships with this gap acknowledged in `SYSTEMS_PLAN.md`; the adversarial-fixture corpus is deferred to v2.
- The Agent SDK auth path via `CLAUDE_CODE_OAUTH_TOKEN` is explicitly discouraged for third-party developer tools by current Anthropic policy ("Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products"). The hybrid design honors the user's directive to keep this path available for personal-use env portability, but the policy note is recorded here so future maintainers can revisit if Anthropic enforces the constraint more strictly.

**Binding constraint preserved:** Adding hook-triggered eval-praxion (or any other future eval tier) still requires a fresh supersession ADR, per dec-040 clause 4.

## Prior Decision

This ADR **narrows only clause 3** of dec-040 and **re-affirms clauses 1, 2, and 4**.

- **Clause 1** (invocation via `/eval` or CI): re-affirmed. `/eval-praxion` is a new slash command alongside `/eval`; both are out-of-band, user-initiated. No CI integration in v1.
- **Clause 2** (no hooks): re-affirmed verbatim. No `praxion_evals.harness.*` or `praxion_evals.judges.*` symbol is ever imported from a hook.
- **Clause 3** (evals read completed artifacts): **narrowed**. The original wording — *"Evals read completed artifacts ... they never mutate live pipeline state, never start agents, never run during a pipeline"* — is preserved on its mutation/agent/pipeline-interruption guarantees. The narrowing is on the reading model only: *completed artifact content may be passed to an LLM-as-judge call over the network*. This makes the family-#2 BC-adherence judge legal (it reads `VERIFICATION_REPORT.md` content and asks Claude to apply the rubric) and makes the family-#1 ADR-option-depth LLM check legal (it reads ADR `## Considered Options` prose and asks Claude to score depth). No other clause-3 semantics change.
- **Clause 4** (preserve out-of-band for future work): re-affirmed. Any Phase 5+ eval tier (including v2's adversarial-fixture LLM judge for family #2, the eventual full td-005 envelope-baseline redesign, and any future cost or decision-quality tier) still inherits the slash-command-or-CI contract.

dec-040 retains `status: accepted`. The two cross-references it carries — `superseded_by: dec-204` and `re_affirmed_by: [dec-204]` — are scoped by THIS body, not by the link alone, per the partial-supersession-clause pattern.
