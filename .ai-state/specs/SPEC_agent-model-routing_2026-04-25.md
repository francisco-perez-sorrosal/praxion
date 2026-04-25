# SPEC: Per-Agent Model Routing Policy

Archived: 2026-04-25. Source: `.ai-work/agent-model-routing/SYSTEMS_PLAN.md` (since cleaned).

## Feature Summary

Praxion's main orchestrator chooses the Claude model tier (`opus` / `sonnet` / `haiku`) per spawned subagent, governed by a single always-loaded rule (`rules/swe/agent-model-routing.md`). Mechanism is hybrid: central rule table + sparing per-spawn overrides via the Agent tool's `model:` parameter (Claude Code precedence layer 2). Frontmatter pins remain as capability floors. Aliases only — full model IDs pinned at spawn time when version-locking is required. v1 ships 1D routing (model only); 2D (model × effort) deferred. Telemetry deferred (one-month review trigger).

## Acceptance Criteria

- **AC1** — Routing policy documented in exactly one authoritative location.
- **AC2** — Every Praxion agent has a declared tier (H / M / L).
- **AC3** — Frontmatter pins reconcile with the rule as *capability floors*.
- **AC4** — `researcher` invocations distinguish at least two modes with different tier defaults.
- **AC5** — Operator kill switch `CLAUDE_CODE_SUBAGENT_MODEL` documented with at least three scenarios.
- **AC6** — No full model ID in the shipped policy; aliases only.
- **AC7** — No spawn-wired code passes `thinking.budget_tokens` / `temperature` / `top_p` / `top_k`.
- **AC8** — `availableModels` rejection fallback chain named.
- **AC9** — Each tier assignment has a one-line rationale.
- **AC10** — Quality-cliff guards name at least three workload signatures.

## Traceability Matrix

| AC | Implementing artifact | Verification |
|----|----------------------|--------------|
| AC1 | `rules/swe/agent-model-routing.md` (always-loaded; no `paths:`); pointer added in `rules/swe/swe-agent-coordination-protocol.md § Agent Selection Criteria` | Catalogued in `rules/README.md` (tree + table) |
| AC2 | Tier table in `rules/swe/agent-model-routing.md` § Tier Table — 13 rows, all assigned (4 H / 8 M / 1 L) | Direct count in rule body |
| AC3 | `rules/swe/agent-model-routing.md` § Principles, item (i); reinforcement note in `skills/agent-crafting/references/configuration.md` after `**model**` bullet | 3 pinned agents (systems-architect, promethean, roadmap-cartographer) verified to keep `model: opus`; rule body declares "may route up, never below" |
| AC4 | `rules/swe/agent-model-routing.md` § Researcher Routing Modes — 3 modes (simple-lookup L, comparative M default, contested H) | Table present in rule |
| AC5 | `rules/swe/agent-model-routing.md` § Operator Kill Switch — 3 scenarios (emergency-cheap `haiku`, emergency-quality `opus`, bypass `default`) | Table present in rule |
| AC6 | Rule uses aliases only; verified by Step 8 lint check (`grep -E "claude-(opus\|sonnet\|haiku)-[0-9]"` returns 0) | LEARNINGS.md § Isolation Sanity (PASS) |
| AC7 | Step 1 audit (`grep -rn "thinking\.budget_tokens\|temperature\|top_p\|top_k"` over `hooks/` + `commands/`) returned 0 spawn-path hits; rule body states the prohibition prospectively | LEARNINGS.md § Audit Results, Step 1 (PASS) |
| AC8 | `rules/swe/agent-model-routing.md` paragraph below kill-switch table — "fall back to the next-cheaper tier (Opus → Sonnet → Haiku) and log it for the runbook" | Paragraph present in rule |
| AC9 | Rationale column populated for all 13 rows in the tier table; ≤12 words each | Direct count |
| AC10 | `rules/swe/agent-model-routing.md` § Quality-Cliff Guards — 4 signatures (deep scientific reasoning, long-horizon coding, cross-codebase refactoring, `verifier` never-downgrade) | Bullet list present in rule |

## Key Decisions (Cross-Reference)

- `dec-draft-8cbfa312` — Hybrid routing: central rule + sparing per-spawn overrides.
- `dec-draft-3f54371e` — Frontmatter `model:` is a capability floor; rule is authoritative.
- `dec-draft-1178a4ea` — Routing policy lives in a new always-loaded rule.
- `dec-draft-43104bf3` — 1D routing (model only); 2D deferred.
- `dec-draft-063470df` — Routing telemetry deferred; one-month review trigger.

(Draft IDs will be rewritten to `dec-NNN` at merge-to-main by the finalize protocol.)

## Implementation Notes (beyond architect's scope)

- **Mid-pipeline rebase**: branch was rebased onto `origin/main` after the architect designed the budget. Main had gained ~5,000 tokens of always-loaded content from the new tech-debt-ledger system. The new rule's contribution remained 1,013 tokens — exactly as designed. The proxy AC1 budget target (16,200) became stale; the hard ceiling (25,000) remained satisfied.
- **Org usage limit**: encountered during Step 3 implementer dispatch. Pivoted from spawn-per-step to direct main-agent edits for compaction and Group B. Step structure unchanged; spawn topology adapted. See LEARNINGS § Edge Cases.
- **Step 9 deferred**: live smoke test for layer-2 override is operator-in-the-loop; runnable pattern recorded in LEARNINGS § Model Routing for the user to execute when convenient. Research-grounded mechanism confidence is HIGH; smoke elevates to VERY-HIGH.
- **External review and post-review fix-packs**: an independent review surfaced 11 items spanning safety (verifier floor pin, imperative orchestrator directive), correctness (kill-switch unverified `default` value, orphan log-runbook claim, baseline-measurement provenance), and quality (researcher mode-selection signals, inline floor comments, direct-invocation entry points, Opus 4.7 staleness marker, ADR cost-claim hedge). All 11 items addressed via two fix-pack commits before merge — the self-verification gap (item #9) is closed by the external review having occurred and its findings having been folded into the shipped artifacts.

## Post-Ship Follow-ups (tracked for v2)

1. ~~**Refresh always-loaded budget baseline** in `CLAUDE.md`~~ — RESOLVED in this PR via the post-review fix-pack. The 16,200-token AC1 target was a point-in-time figure recorded in `.ai-work/` pipeline docs (which don't ship); CLAUDE.md never carried a stale baseline. The fix-pack adds a measurement procedure to `rules/CLAUDE.md` so future readers compute current headroom against the 25K hard ceiling rather than referencing decay-prone baselines.
2. **`skills/claude-ecosystem/SKILL.md` model-catalog refresh** — references stale models (Opus 4.6 / Sonnet 4.5) while current is 4.7 / 4.6 / Haiku 4.5. 32 hits across 15 skill files. Lightweight task, separate scope.
3. **Routing telemetry revisit** — one month from ship, or sooner if cost overshoot or retry loops observed (especially on `doc-engineer` at Tier L or cartographer's 6-way researcher fan-out). Build transcript-scraper if Anthropic hasn't shipped a resolved-model API by then.
4. **2D routing (model × effort) revisit** — when telemetry shows a specific agent spending most tokens on an easy-case pattern, OR Anthropic extends `effort` uniformly across tiers.
5. **Floor-vs-rule drift check** — file as a `.ai-state/TECH_DEBT_LEDGER.md` row by sentinel (post-ship tech-debt-ledger system supports this without new sentinel logic).
6. **Step 9 smoke completion** — user runs the recorded pattern; appends transcript snippet to LEARNINGS § Model Routing § Smoke Result; elevates mechanism confidence to VERY-HIGH.
7. ~~**Independent verifier dispatch**~~ — RESOLVED via the external review that produced fix-pack items 1–11. The independent review served the same role as an `i-am:verifier` dispatch would have: surfaced safety, correctness, and quality findings against the shipped artifacts. All findings folded into the shipped surface or this SPEC's follow-up list before merge.
