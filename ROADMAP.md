# Praxion Spring Cleaning Roadmap

**Date**: 2026-04-12
**Scope**: Complete ecosystem evaluation and strategic roadmap
**Method**: 6 parallel deep-dive audits (skills, agents, rules/commands/hooks, infrastructure, knowledge, external state-of-art)

---

## Executive Summary

Praxion is ahead of the industry curve. The progressive disclosure model, document-mediated agent pipeline, dedicated context-engineer role, and memory-backed learning loop are all validated by the 2026 consensus on AI-assisted software development. The Anthropic Agentic Coding Trends Report specifically identifies "workflow design over tool adoption" as the key differentiator -- which is exactly Praxion's thesis.

But there are real problems. The token budget is at 96.8% capacity with zero growth headroom. Memory is write-only (147 writes, 3 reads across 55 sessions). The coordinator agent carries 30+ orchestration decisions per pipeline. Six ADRs are in production but still marked "proposed." The eval framework is a stub. CI runs zero tests. These aren't cosmetic issues -- they're structural debts that will compound.

This roadmap organizes improvements into 5 phases, each building on the previous. The phases are ordered by urgency and dependency, not calendar dates. Execute them in sequence within each phase, but phases themselves can overlap.

---

## What's Working (Preserve and Protect)

These are strengths confirmed across multiple audit dimensions. Don't fix what isn't broken.

### Architecture & Design
- **Progressive disclosure** is industry-standard and Praxion pioneered it. The three-stage skill model (metadata -> instructions -> references) is consistently applied across 30 of 33 skills
- **Document-mediated pipeline** avoids tight agent coupling and enables human review at each stage. This is a distinct pattern from the 5 major orchestration approaches (handoffs, graphs, crews, mailbox, protocol-based)
- **Context-engineer agent** -- most frameworks don't have a dedicated context management agent. This is ahead of the curve
- **Dual-layer memory** (curated JSON + append-only observations) is architecturally sound and well-implemented
- **BDD/TDD parallel execution** model (implementer + test-engineer on disjoint files) is clean and effective

### Quality Infrastructure
- **Memory MCP**: 405 tests, clean module separation, atomic file writes, process-safe locking. The best-tested component in the ecosystem
- **Chronograph**: Fail-open design, hierarchy-aware agent spanning, git context enrichment, secret redaction, deterministic port derivation
- **Hook enforcement**: 3-layer memory enforcement (commit, subagent, session), code quality gates before commit, auto-format Python on write
- **Test coverage**: 631 tests across both MCP servers (405 + 226), all passing

### Content Quality
- **Gotchas sections** are the highest-signal content across skills -- 28 of 33 skills include production-learned gotchas
- **Cross-references** form a navigable skill graph with clear boundaries (planning chain, platform chain, quality chain, architecture chain)
- **CLAUDE.md ecosystem** is coherent -- 10 files, well-scoped, non-overlapping, consistent style
- **ADR system** is well-structured with proper MADR format, sequential numbering, and automated index regeneration
- **Git merge infrastructure** handles .ai-state/ reconciliation with custom merge drivers and post-merge hooks

### Tooling
- **`chronograph-ctl`/`phoenix-ctl`**: Consistent UX patterns, robust PID management, port derivation
- **`ccwt`**: Elegant tmux-based multi-worktree Claude sessions
- **Install system**: Interactive, idempotent, health-check capable, dry-run mode

---

## Weaknesses (Critical Issues)

### W1. Token Budget at Capacity (96.8%)

Always-loaded content consumes 14,523 of the 15,000 token budget. Zero headroom for growth. The single most expensive artifact is `swe-agent-coordination-protocol.md` at 3,653 tokens -- and it's mostly **procedural workflow content**, not declarative constraints. This violates the rules-vs-skills principle: workflows belong in skills, constraints belong in rules.

**Impact**: Cannot add any new always-loaded rules. Forces increasingly aggressive content compression for any new feature. Every token saved is a token available for the projects that consume Praxion.

### W2. Memory Is Write-Only

147 `remember()` calls vs 3 `recall()` and 2 `search()` across 55 sessions. The "Apply" phase of Learn/Recall/Apply is broken. 83% of entries have never been accessed. Memory injection at session start provides bulk context, but mid-session memory consultation is essentially zero. The system learns but never recalls on demand.

Additionally: 6 entries exceed 2,000 chars (essay-length, should be docs not memories), zero user profile entries, importance inflation (76% at importance 6-8), session_count header drifted to 5 vs actual 55+.

**Impact**: Investment in memory infrastructure delivers diminishing returns if knowledge is never consulted during work.

### W3. Coordinator Burden Is Unsustainable

The main agent must make 30+ decisions per Standard pipeline: tier selection, slug generation, worktree entry, researcher skip decision, context-engineer shadowing decision, calibration log, delegation prompts with checklists, foreground/background decisions, multiplicity checks, depth checks, progress monitoring, fragment reconciliation, artifact verification, worktree exit, skill-genesis decision. The coordination rules alone consume ~62% of the token budget.

**Impact**: High cognitive load means more errors, more context used for orchestration vs actual work, longer pipelines, higher token cost.

### W4. No CI Test Pipeline

631 tests (405 + 226) across two MCP servers run only locally. No lint check, no format check, no type checking, no plugin validation in CI. The security review workflow exists but the fundamental quality gate (tests pass) does not.

**Impact**: Regressions can ship undetected. Contributors have no automated quality feedback.

### W5. Eval Framework Is a Stub

One evaluation type (ToolSelection), no tests, stale API patterns, no scheduled runs, no regression testing, no behavioral evaluation. The industry is converging on structured eval pipelines (Promptfoo, DeepEval, SWE-bench) and Praxion has almost nothing.

**Impact**: Cannot measure whether changes to skills, agents, or rules actually improve output quality. Improvement is based on intuition, not data.

### W6. Agent Pipeline Calibration Issues

- **Systems-architect** runs on default Sonnet despite making the most consequential decisions (technology selection, system boundaries, data model). For Standard/Full tier tasks, Opus is justified
- **Sentinel** prompt at 479 lines exceeds its own T03 check threshold. The check catalog (~200 lines, ~3,000 tokens) is embedded in the prompt instead of a reference file
- **Phase numbering** was chaotic with decimal and letter-suffixed phases across systems-architect and verifier, causing misleading progress signals (resolved 2026-04-12 by pipeline-hardening task 2.1 — both agents now use sequential integer numbering)
- **Test results** have no formal handoff between implementer and verifier -- the verifier "does not run tests" but needs results
- **skill-genesis** has `background: true` in frontmatter but uses `AskUserQuestion` (interactive)
- **Researcher** lacks `Edit` tool despite using incremental writing pattern
- **Turn budget awareness** missing from 6 of 12 agents despite known maxTurns exhaustion issues

---

## Improvement Roadmap

### Phase 1: Foundation Repair (Critical Path)

These fixes address structural debts that block everything else. Do them first.

#### 1.1 Reclaim Token Budget — Phase 1A ✅ DONE (2026-04-11)

**Status**: Phase 1A complete. Phase 1B Point #2 (path-scope `coding-style.md`) shipped 2026-04-13; Point #1 (delegation-checklist extraction) deferred.

**Phase 1A — Safe-first extraction (shipped)**

Completed via full Standard-tier pipeline with context-engineer shadowing both architect and planner stages. ADR: `dec-022`.

**What was done:**
- Created new on-demand reference file `skills/software-planning/references/coordination-details.md` (13,755 chars) with 7 anchor sections: Pipeline Worktree Lifecycle (link-out to `agent-pipeline-details.md` per D-01 anti-duplication), Task Slug Propagation, BDD/TDD Execution, Batched Improvement Execution, Context-Engineer Shadowing, Doc-Engineer Parallel Execution, Parallel Execution Fragment Files
- Slimmed `rules/swe/swe-agent-coordination-protocol.md` (14,612 → 12,577 chars, −13.9%) with summary-plus-pointer stubs; preserved `#process-calibration` and `#pipeline-isolation` anchors via stub sections with `<!-- Anchor preserved -->` HTML comments
- Slimmed `rules/swe/agent-intermediate-documents.md` (9,699 → 8,946 chars, −7.8%); preserved `#parallel-execution` and `#task-slug-convention` anchors
- Registered new reference in `skills/software-planning/SKILL.md` satellite list; synced `skills/software-planning/README.md` Skill Contents table
- Closed `claude/config/CLAUDE.md` implementer-deliverables gap (symmetric 4-agent block)

**What was kept always-loaded (decision-driving content — NOT extracted):**
- Process Calibration tier table (every task starts here)
- Available Agents inventory (agent awareness)
- Delegation Checklists (per-agent "always include in prompt" bullets — see Phase 1B)
- Proactive Agent Usage triggers (drives proactive spawning)
- Pipeline diagram + core principles ("Do not skip stages", "Sentinel is independent")
- Agent Selection Criteria, Delegation Depth, Background Agents

**Results:**
- Always-loaded budget: 57,444 chars → 52,130 chars (−5,314 chars / ~1,500 tokens reclaimed)
- Budget utilization: 109.4%/95.7% → **99.3% conservative / 86.9% optimistic** (under 15,000-token ceiling at both chars/token ratios)
- 10/10 acceptance criteria PASS, verifier PASS WITH FINDINGS (1 WARN remediated in same pipeline)
- All 11 anchors (4 preserved + 7 new) resolve; zero broken agent-prompt references; both slimmed rules coherent standalone

**Phase 1B — Bold extraction (Point #2 shipped 2026-04-13; Point #1 deferred)**

Rationale: the safe-first Phase 1A delivered clean structural reclamation (~1,500 tokens) and validated that progressive disclosure works for pipeline coordination. Delegation checklists were explicitly kept always-loaded in Phase 1A (D-02 decision) because they drive every delegation prompt and redundancy is cheap at that frequency.

Phase 1B candidates:

1. **Extract Delegation Checklists** (~500 tokens savings) — **deferred**. Would move the per-agent "always include in prompt" bullets from the coordination protocol rule to `coordination-details.md`, leaving a pointer. Mitigation already in place: `claude/config/CLAUDE.md` now has condensed deliverables for all 4 pipeline agents (implementer added in Phase 1A), so the main agent retains always-loaded access to the essential deliverables list without the per-agent detail. Risk: medium — the detailed checklists carry conditional deliverables (deployment doc, architecture doc) that the condensed list omits.

2. **Path-scope `coding-style.md`** ✅ DONE (2026-04-13). Added `paths:` frontmatter with 24 code-file globs (ADR `dec-044`) so the rule loads only on code sessions. Delivered as commit 1 of the Behavioral Contract Layer rollout to fund commit 2's ~949-byte `agent-behavioral-contract.md` addition. Measured delta: −6,730 bytes / ~−1,923 tokens on always-loaded content; net after commit 2: ~−5,360 bytes / ~−1,531 tokens (949 B new rule + 421 B project `CLAUDE.md` anchor − 6,730 B path-scoped). Risk proved low as predicted — safety audit on BC-S02 confirmed all runtime callers are code-session-scoped or documentary-only.

Phase 1B recovery delivered: ~1,923 tokens from Point #2 alone (of the original ~2,400 combined estimate). Point #1 remains available for future pressure.

**Dependencies for Phase 1B Point #1 (if ever pursued)**: Phase 1A validation — observe sentinel T02 trend and main-agent orchestration quality for a few sessions before deciding.

**Follow-up from Phase 1A (low priority, not blocking):**
- Sentinel T02 command scope mismatch (`agents/sentinel.md:281`) — includes scoped `testing-conventions.md`, excludes `claude/config/CLAUDE.md` and scoped writing rules. Align sentinel T02 measurements with actual always-loaded scope.
- Plan-arithmetic lesson learned: "under N chars" done-when targets should be computed against the "Keep unchanged" directives' total size, not set independently. Documented in LEARNINGS for future planners.

#### 1.2 Add CI Test Pipeline ✅ DONE (2026-04-12)

**Shipped**: `.github/workflows/test.yml` with SHA-pinned `actions/checkout@v6.0.2` + `astral-sh/setup-uv@v8.0.0`; matrix `project: [memory-mcp, task-chronograph-mcp]`; per-cell `uv sync` → `ruff format --check` → `ruff check` → `pytest`; workflow-level `permissions: contents: read`, `timeout-minutes: 15`, concurrency group. ADR: `dec-024`. First real CI run validation is deferred to post-merge (verifier AC 1.2.d).

**Follow-up**: also fixed a pre-existing import-sort error in `task-chronograph-mcp/src/task_chronograph_mcp/__main__.py` surfaced by the new `ruff check` step.

#### 1.3 Promote 6 Proposed ADRs to Accepted ✅ DONE (2026-04-12)

**Shipped**: dec-009, dec-010, dec-015, dec-016, dec-019 flipped to `accepted`. dec-019 gained a Consequences note documenting that the Praxion instance of `.ai-state/SYSTEM_DEPLOYMENT.md` is intentionally deferred (Praxion is an ecosystem library, not a deployable service). dec-011 was discovered to contradict its own implementation in `hooks/inject_memory.py` (the code is ADR-first; the ADR said memory-first) and was **superseded by dec-023**; dec-011 body preserved for audit trail. `DECISIONS_INDEX.md` regenerated via `scripts/regenerate_adr_index.py`.

**Post-pipeline state**: 28 ADRs total (22 pre-existing + 6 new: dec-023 through dec-028). 26 `accepted`, 2 `superseded` (dec-011 new, dec-020 pre-existing), 0 `proposed`.

#### 1.4 Memory Hygiene Sprint ✅ DONE (2026-04-12)

**Shipped**: formalized as deterministic rules R1–R7 in `dec-025` (condense oversized, preserve no-authority, consolidate overlap, preserve distinct angles, supersede stale initiatives, fix doc-drift, skip user-profile invention).

- **Condensed** 6 entries from 2,036–7,425 chars down to ≤400 chars each, each citing the authoritative source (SKILL.md, ADR, or code path)
- **Archived** 9 duplicate-cluster entries (ecosystem-health, architecture-docs, memory-enforcement) and 3 stale-initiative entries; no hard deletes — `status: archived` preserves history
- **Fixed session_count drift** by deriving the count from `observations.jsonl` (distinct `session_id` via new `ObservationStore.count_sessions()`) rather than the stale in-file counter; metrics reader updated; 3 new tests in `test_metrics.py`. ADR: `dec-026`.
- **Corrected `memory-mcp/CLAUDE.md`** and `store.py:88` docstring — both claimed "no migration code" while `_migrate_v1_to_v2` runs on every load.

**Not done (deferred)**: user-profile entry creation — R7 explicitly excludes inventing profile content without the user's agency. Flagged as a follow-up.

#### 1.5 Fix Documentation Counts ✅ DONE (2026-04-12)

**Shipped**: added `writing/diagram-conventions.md` to `rules/README.md` (tree + table). Retired `SOLID_FOUNDATION_IMPROVEMENTS.md` entirely (every count was stale; ROADMAP Deprecation table already tagged it). Confirmed the "19 slash commands" claim in `README.md` was already correct (filesystem = 19, not 20); no change needed.

**Scope addition**: narrowed `rules/writing/diagram-conventions.md` `paths:` frontmatter from the effectively-always-loaded `**/*.md` to 10 doc-authoring surfaces (ADR: `dec-028`) — reclaims ~2,584 chars on non-doc sessions and buys the headroom for principles embedding.

#### 1.6 Guiding Principles Embedding ✅ DONE (2026-04-12)

**Shipped**: added `## Guiding Principles (Praxion-specific)` block to `CLAUDE.md` (~320 chars cross-reference style) pointing to rich prose in `README.md#guiding-principles` (~1,400 chars). Four durable principles: **token budget first-class**, **measure before optimize**, **standards convergence as opportunity**, **curiosity over dogma**. Principle #3 ("one phase at a time") was intentionally excluded — it's a roadmap-execution rule, not a durable project principle. ADR: `dec-027` (embedding strategy) + `dec-028` (budget lever precondition).

#### 1.7 Opportunistic Deprecations ✅ DONE (2026-04-12)

Closed from the Deprecation & Cleanup table (Phase-1-tagged): deleted `claude/config/CLAUDE_OLD.md` and `claude/config/CLAUDE_UNPOLISHED.md` (historical trial-version prompts the user was iterating on). Confirmed `**/__pycache__/` in `.gitignore`. `TODO.md` disposition deferred.

**Kept intentionally**: `claude/config/CLAUDE.md` is a versioned mirror of the user's `~/.claude/CLAUDE.md` that the project preserves under git on purpose. It was initially deleted in commit `a4440e1` based on a bad inference ("byte-identical duplicate ⇒ safe to delete"); restored in a follow-up commit. The Deprecation & Cleanup entry below has been corrected.

---

### Phase 2: Agent Pipeline Hardening

Build on the recovered token budget and CI foundation.

#### 2.1 Agent Prompt Improvements (Batch) ✅ DONE (2026-04-12)

**Outcome**: Landed all items except sentinel catalog extraction. systems-architect gained `model: opus`; researcher added `Edit` to tools; skill-genesis lost `background: true`; test-engineer `maxTurns` raised to 60; cicd-engineer moved to language-detection with `skills: [cicd]`; six agents gained 2-bullet Turn Budget in `## Constraints` (per RECONCILIATION — not a dedicated section, avoiding cargo-cult from sentinel); systems-architect phases renumbered 1..10, verifier 1..12, with 13 dependent files phase-synced. Sentinel catalog stays inline (dec-021 addendum pattern; T03 deviation documented in LEARNINGS — `agents/references/` is not portable, and a new skill over-builds for a single consumer). See `.ai-work/pipeline-hardening/RECONCILIATION.md`.

**Actions** (all low-effort, high-impact):

| Agent | Fix | Effort |
|-------|-----|--------|
| systems-architect | Add `model: opus` to frontmatter for consequential decisions | Trivial |
| sentinel | Extract check catalog (~200 lines) to reference file, bring prompt under 400 lines | Small |
| systems-architect, verifier | Renumber phases sequentially (no more decimal/letter-suffixed phases) | Small |
| researcher | Add `Edit` to tools list | Trivial |
| skill-genesis | Remove `background: true` or add non-interactive mode | Trivial |
| researcher, test-engineer, doc-engineer, context-engineer, cicd-engineer, skill-genesis | Add turn budget awareness sections | Small |
| test-engineer | Increase maxTurns from 50 to 60 (align with implementer) | Trivial |
| cicd-engineer | Replace hardcoded Python skills with language detection | Small |

**Dependencies**: 1.1 (token budget recovery enables larger agent prompts where needed).
**Risk**: Low. Each change is independent and testable.

#### 2.2 Formalize Test Result Handoff ✅ DONE (2026-04-12)

**Outcome**: `TEST_RESULTS.md` declared at `.ai-work/<task-slug>/TEST_RESULTS.md`. Implementer writes at new sub-step 7.8 (after `docs/architecture.md` update); test-engineer is canonical writer when paired with implementer (BDD/TDD); verifier reads at renumbered Phase 10 with WARN-not-FAIL on missing file. Fragment pattern `TEST_RESULTS_<agent-type>.md` documented in `skills/software-planning/references/agent-pipeline-details.md`. Schema per ADR-038 (with addendum reconciling implementation landing points).

**Problem**: Implementer runs tests, results are ephemeral. Verifier needs results but "does not run tests."

**Action**: Define a lightweight `TEST_RESULTS.md` artifact written by the implementer after running tests. Contents: test command, pass/fail counts, failure details, coverage summary. The verifier reads this instead of relying on implicit handoff.

**Dependencies**: 2.1 (agent prompt improvements).
**Risk**: Low. Adds one file to the pipeline but provides formal handoff.

#### 2.3 Reduce Coordinator Burden

**Problem**: 30+ decisions per Standard pipeline.

**Actions**:
- **Move delegation checklists** from always-loaded rules to a `software-planning/references/delegation-checklists.md` reference file (loaded when main agent activates software-planning skill for Standard+ tiers)
- **Create tier templates**: Pre-built prompt templates for Standard pipeline that auto-include the slug, deliverables, and sequential agent invocations. Reduces cognitive load from "construct each prompt" to "fill in the template"
- **Better-define Lightweight tier**: Add inline acceptance criteria format, specify which agents are available, where findings go. Close the steep jump between Lightweight and Standard

**Dependencies**: 1.1 (token budget), 2.1 (agent improvements).
**Risk**: Medium. Tier templates must be flexible enough for varied tasks.

#### 2.4 Harmonize Memory Gate Exemptions ✅ DONE (2026-04-12)

**Outcome**: `EXEMPT_AGENTS` centralized as frozenset + `is_exempt(agent_type) -> bool` helper in `hooks/_hook_utils.py` (single source of truth). `validate_memory.py` and `remind_memory.py` both import the helper; `remind_memory.py` gained early-return short-circuit after `agent_type` retrieval. Smoke test green. ADR-039 captures the rationale.

**Problem**: `validate_memory.py` exempts doc-engineer/sentinel/Explore/Plan at SubagentStop, but `remind_memory.py` (commit gate) exempts nobody.

**Action**: Add exemption list to `remind_memory.py` matching `validate_memory.py`'s EXEMPT_AGENTS.

**Dependencies**: None.
**Risk**: None.

---

### Phase 3: Quality & Automation

Invest in systematic quality measurement and automation gaps.

#### 3.1 Eval Framework Overhaul ⚠️ SHIPPED BUT BROKEN (2026-04-12; limitation surfaced 2026-04-13)

**Outcome**: New `eval/` uv workspace package with Tier 1 behavioral (artifact manifest check) and regression (Phoenix trace diff against baseline) evaluations landed. `/eval` slash command (scoped to `Bash(uv run --project eval praxion-evals:*)`); Tier 2 stubs (cost, decision-quality, claude-as-judge) deferred per user's "scope carefully" guidance. 30/30 eval tests pass. OUT-OF-BAND invariant enforced: `grep -rn praxion_evals hooks/` returns empty (dec-040). Existing `trajectory_eval.py` preserved as Tier 1 OpenAI-judge shim.

> ⚠️ **Critical limitation discovered 2026-04-13**: The shipped **regression** implementation is effectively useless for Praxion's actual workflow. It keys baselines by `task_slug` (e.g., `.ai-state/evals/baselines/architecture-doc.json`), which assumes pipelines can be re-run on the same slug for comparison. But Praxion's slug semantics are **one-shot**: each feature generates a unique slug (`architecture-doc`, `deployment-skill`, `spring-cleaning`), runs exactly once, then `.ai-work/<slug>/` is deleted. There is no "next run" on that slug to compare against any captured baseline — so drift detection is meaningless in this model. The only narrow cases it fits are deliberately stable "smoke-test" slugs or retries of the same feature.
>
> **Additional bug found the same day**: `eval/pyproject.toml` depends on `arize-phoenix-evals` but not `arize-phoenix`, so `phoenix.Client()` raises `AttributeError`, is swallowed by the broad `except Exception` in `trace_reader.py`, and the CLI surfaces a misleading "Phoenix returned empty traces" instead of the real error. Live Phoenix capture never actually works.
>
> **Status of the three Tier 1 modes**:
> - `behavioral` — **works** (filesystem check against `.ai-work/<slug>/`; independent of slug recurrence)
> - `regression` — **useless** for general drift detection; see [3.7](#37-eval-framework-redesign-tiershape-keyed-baselines) for the replacement design
> - `judge --provider openai` — preserved shim, works as documented
>
> Treat `/eval regression` as a proof-of-concept only until 3.7 lands. Downstream follow-ups (ADR-040 scope correction, CLI warning on invocation) live under 3.7.

**Problem**: Stub framework with one eval type, no tests, stale patterns.

**Actions**:
- Migrate to `pyproject.toml` with uv (align with project conventions)
- Add **behavioral evaluation**: Does the agent produce expected artifacts? Does the pipeline complete with correct deliverables?
- Add **cost/token evaluation**: Token efficiency per task complexity tier
- Add **regression testing**: Compare current traces against baseline traces
- Add **decision quality evaluation**: ADR accuracy, consistency with prior decisions
- Support **Claude as judge model** (not just OpenAI)
- Add tests for the eval framework itself
- Create `/eval` command for easy invocation

**Dependencies**: 1.2 (CI pipeline for running evals).
**Risk**: High effort. Scope carefully -- start with behavioral eval and regression testing, expand incrementally.

#### 3.2 Add Shell Gate for `promote_learnings.py` ✅ DONE (2026-04-12)

**Outcome**: `hooks/cleanup_gate.sh` created mirroring `commit_gate.sh` structure; `hooks/hooks.json` routes `promote_learnings.py` through the gate. Conservative regex per context-engineer hardening — false-negative is the failure mode, so ambiguous cleanup patterns fall through to Python. Non-matching Bash commands skip Python startup (~200-500ms saved). 12/12 shell-gate tests pass.

**Problem**: Python startup (~200-500ms) on every Bash call without fast-path filtering.

**Action**: Create `cleanup_gate.sh` matching `rm.*ai-work` pattern, similar to `commit_gate.sh`. Only invoke Python when the Bash command matches cleanup patterns.

**Dependencies**: None.
**Risk**: None.

#### 3.3 Add Large-File Warning Hook ❌ WON'T DO (2026-04-12)

**Rationale**: User directive — the 800-line coding-style rule should remain advisory; implementing a hook (even one that only warns) adds PostToolUse latency on every Write/Edit and introduces noise without enforcement value. Existing sentinel code-health dimension already flags large files during ecosystem audits, which is the right level of intervention for an advisory rule. Closed as out-of-scope by user decision, not a deferred item.

**Problem**: Coding-style 800-line rule is advisory only.

**Action**: PostToolUse hook that checks line count after Write/Edit. Warn (exit 0) when a file exceeds 800 lines.

**Dependencies**: None.
**Risk**: Low. Advisory only, does not block.

#### 3.4 Add Type Checking to MCP Servers ✅ DONE (2026-04-12)

**Outcome**: Pyright (basic mode) added to both `memory-mcp` and `task-chronograph-mcp` dev deps; `[tool.pyright]` config scoped to `src/`; CI step wired between ruff and pytest. Staged rollout per dec-041 (observe → fix → enforce) completed in one pipeline: all observed errors fixed, then `continue-on-error: true` removed. Both servers at **0 errors, 0 warnings**. Full test suites still green (memory-mcp 418, task-chronograph-mcp 226).

**Problem**: Both servers use type hints extensively but never validate them.

**Action**: Add `mypy` or `pyright` to dev dependencies and CI. Fix any type errors found.

**Dependencies**: 1.2 (CI pipeline).
**Risk**: Medium. May surface latent type issues.

#### 3.5 Automatic Observation Rotation ✅ DONE (2026-04-12)

**Outcome**: `memory-mcp/src/memory_mcp/server.py::session_start()` now calls `_get_observation_store().rotate_if_needed()` wrapped in try/except so rotation failure never blocks session start. Hot-path safe: measured p95 = **0.023 ms** (2 orders of magnitude under the 2 ms EC-3.5.2 budget). 39/39 tests in `tests/test_observations.py::TestSessionStartRotationWiring` green.

**Problem**: `observations.jsonl` grows unbounded. Rotation exists but is never called.

**Action**: Call `rotate_if_needed()` during `session_start()` in the memory MCP server.

**Dependencies**: None.
**Risk**: Low.

#### 3.6 Fix Scripts Linking ✅ DONE (2026-04-12)

**Outcome**: `install_claude.sh::relink_all()` filters via combined predicate (`[ -f && -x ]` AND `case "$name" in merge_driver_*|git-*-hook.sh) continue ;;` — per dec-042). `scripts/regenerate_adr_index.py` made executable in same commit (prevents silent regression). `clean_stale_symlinks()` extended to sweep `~/.local/bin/` for orphaned symlinks on upgrade. 14/14 install-filter tests pass. User-level install preserved: each project still operates on its own `$CWD`; no global config bleed.

**Problem**: `install_claude.sh` links ALL files in `scripts/` to `~/.local/bin/`, including test files and CLAUDE.md.

**Action**: Filter to only executable scripts: `[ -f "$script" ] && [ -x "$script" ] || continue`.

**Dependencies**: None.
**Risk**: None.

#### 3.7 Eval Framework Redesign: Tier/Shape-Keyed Baselines

**Status**: TODO — replaces the broken slug-keyed regression model shipped in 3.1. Blocks meaningful use of `/eval regression`.

**Problem**: The regression model shipped in 3.1 keys baselines by `task_slug`. This assumes pipelines can be re-run on the same slug for comparison, which is false in Praxion. Each feature produces a unique one-shot slug (`architecture-doc`, `deployment-skill`, `spring-cleaning`), runs once, and is cleaned up. A captured baseline has no corresponding "next run" to diff against. For the actual question users want to ask — "does today's standard-tier pipeline look structurally different from a typical one?" — slug-keyed baselines are the wrong primitive because every slug-keyed baseline has a sample size of exactly one.

**Root cause**: Real-world benchmark-regression systems (CI flakiness dashboards, performance envelopes) use **tier-keyed** or **shape-keyed** baselines — a statistical envelope built from many past pipelines of the same *category*, not a point snapshot of one specific run. Praxion runs dozens of standard-tier pipelines a month; that accumulated population is where the statistical signal lives.

**Proposed design**:

1. **Tier-keyed baselines** — stored as `.ai-state/evals/baselines/tier-<name>.json` (replacing `.ai-state/evals/baselines/<slug>.json`). Represents the envelope across all past pipelines of that tier:
   ```json
   {
     "tier": "standard",
     "captured_from_n_pipelines": 47,
     "captured_window": "last-90-days",
     "span_count":      { "p50": 120, "p95": 220 },
     "tool_call_count": { "p50": 28,  "p95": 55  },
     "agent_count":     { "p50": 5,   "p95": 6   },
     "duration_ms_p95": { "p50": 4500, "p95": 8200 }
   }
   ```

2. **Shape-keyed baselines** — finer signature within a tier when tier alone is too coarse. Shape is a tuple of structural characteristics: implementation-step count, use of test-engineer, parallel-pair count, use of refactoring. Files named `tier-standard__steps-small.json`, `tier-full__parallel-true__refactor-true.json`, etc. Regression picks the matching shape at runtime by inspecting the current pipeline's metadata.

3. **Aggregate capture** — `capture-baseline` evolves from "snapshot one Phoenix project" to "sample N most recent pipelines matching tier/shape, compute p50/p95 percentiles". Requires either:
   - Querying Phoenix across projects filtered by a `praxion.tier` / `praxion.shape` span attribute (preferred — requires chronograph span enrichment), or
   - Reading `.ai-state/` history to collect past pipeline metadata plus Phoenix trace links

4. **Regression check semantics** — "is this new run inside the envelope for its tier/shape?" Findings become percentile-based: "span_count = 340, outside p95 envelope of 220 (sampled from 47 standard-tier pipelines)". This is the drift detection users actually want.

**Actions**:
- Write ADR for the shift from slug-keyed to tier/shape-keyed baselines (partial supersession of dec-040 scope — invocation discipline stays; baseline keying changes)
- Add `praxion.tier` and `praxion.shape.*` span attributes to chronograph OTel relay (requires chronograph change)
- Refactor `BaselineSummary` → envelope schema (`p50` / `p95` per field instead of point values); update `diff.py` to percentile comparisons; rewrite `capture.py` for aggregate capture across N pipelines
- Deprecate per-slug baseline files; migration plan for existing baselines (likely delete — the one existing baseline is not meaningful)
- Fix the `arize-phoenix` dep gap in `eval/pyproject.toml` (precondition — without live Phoenix connectivity, no real capture is possible)
- Surface Phoenix connectivity errors in the CLI instead of swallowing them in the `notes` tuple
- Add a CLI banner on `/eval regression` and `/eval capture-baseline` warning that the current implementation is a preview pending 3.7

**Dependencies**:
- Chronograph span attribute enrichment (new sub-task in whichever phase owns chronograph changes)
- No blocking dependencies from this phase; 3.1 was self-contained

**Risk**: Medium. Core schema change retires the shipped 3.1 regression design. Behavioral and judge tiers are unaffected.

**What stays from 3.1**:
- `behavioral` eval (filesystem manifest check) — fully compatible, no redesign needed
- OUT-OF-BAND invocation discipline (`dec-040`) — unchanged
- `trajectory_eval.py` OpenAI judge shim — unchanged
- CLI scaffolding, test harness, tier registry, `praxion-evals` entrypoint — reused

---

### Phase 4: Ecosystem Evolution

New capabilities informed by external research and gap analysis.

#### 4.1 AGENTS.md Cross-Tool Portability

**Problem**: Praxion's CLAUDE.md serves a similar purpose to the AGENTS.md standard (now under AAIF), but is Claude-specific.

**Action**: Create a generator that produces an `AGENTS.md` file from Praxion's CLAUDE.md + skills metadata for cross-tool compatibility (Cursor, Copilot, etc.). This is low-effort, high-visibility for ecosystem adoption.

**Dependencies**: None.
**Risk**: Low. Additive -- doesn't change existing CLAUDE.md system.

#### 4.2 Skill Coverage Expansion

**Priority gaps** identified in the skills audit:

| Skill | Priority | Rationale |
|-------|----------|-----------|
| `llm-prompt-engineering` | High | Most surprising gap for an AI-focused ecosystem. Few-shot patterns, chain-of-thought, structured output design, prompt versioning, prompt testing |
| `typescript-development` | Medium | Closes the biggest language coverage gap. Full-stack projects need TS equivalent of `python-development` |
| `mcp-crafting` TypeScript context | Medium | Only Python context exists. TypeScript is a first-class MCP SDK language |

Also: Move `github-star` from skill to command (it's a procedure, not domain expertise).

**Dependencies**: 1.1 (token budget for new skills).
**Risk**: Low for each individual skill. Total effort is significant.

#### 4.3 Staleness Detection System

**Problem**: Version-sensitive skills (claude-ecosystem, agentic-sdks, communicating-agents, deployment, python-prj-mgmt) have no staleness markers.

**Action**: Add `<!-- last-verified: YYYY-MM-DD -->` HTML comments to version-sensitive sections. Add a sentinel check that flags sections where last-verified exceeds a configurable threshold (e.g., 90 days).

**Dependencies**: 2.1 (sentinel improvements).
**Risk**: Low. Non-breaking addition.

#### 4.4 Cross-Reference Validation in CI

**Problem**: Skills reference other skills, rules, and agents. No automated check that references resolve.

**Action**: Extend `validate.py` to parse markdown links in SKILL.md files and verify targets exist. Run in CI.

**Dependencies**: 1.2 (CI pipeline).
**Risk**: Low.

#### 4.5 Compress Token-Inefficient Skills

**Actions**:
- `external-api-docs`: Consolidate MCP/CLI parallel sections (~60 lines savings)
- `python-prj-mgmt`: Consolidate pixi/uv parallel examples (~100 lines savings)
- `rule-crafting`: Compress verbose sections (~50 lines savings)

**Dependencies**: None.
**Risk**: Low. Content preservation with better structure.

#### 4.6 Observation Layer Correlation

**Problem**: Memory MCP's observations.jsonl and chronograph's OTel traces capture overlapping events with different schemas and no shared identifiers.

**Action**: Add a shared `trace_id` or `correlation_id` field to observation records. Enable "show me the memory operations for this Phoenix trace" queries.

**Dependencies**: None.
**Risk**: Medium. Schema change to observations requires migration consideration.

---

### Phase 5: Strategic Horizons

Longer-term investments that position Praxion for the next evolution.

#### 5.1 Agent Teams Integration (Experimental)

Claude Code's Agent Teams feature (peer-to-peer mailbox, direct teammate communication) could evolve Praxion's parallel execution model. The current fragment-file approach works but is indirect -- agents write to files and hope the supervisor merges correctly. Agent Teams would enable implementer + test-engineer to communicate directly about interface contracts.

**Action**: When Agent Teams stabilizes (currently experimental), create a proof-of-concept replacing the fragment-file pattern for implementer+test-engineer pairs. Keep document-mediated pipeline for sequential stages.

**Timeline**: Monitor Claude Code releases. Target evaluation when Agent Teams exits experimental.
**Risk**: Experimental feature may change significantly or be deprecated.

#### 5.2 HTTP Hook Handler for Chronograph

The hooks system now supports `http` handler type, which could simplify chronograph integration (direct POST instead of command-line wrapper with Python startup overhead per event).

**Action**: Evaluate replacing `send_event.py` (command handler) with an `http` handler pointing directly at chronograph's `/api/events` endpoint. This eliminates Python startup, git subprocess calls, and wrapper overhead for every hook event.

**Dependencies**: Verify `http` handler supports the required event payload format.
**Risk**: Low. Performance improvement with simpler architecture.

#### 5.3 MCP Gateway Pattern

MCP Gateways are emerging as an enterprise pattern for centralized access control, audit, and routing. If Praxion targets broader adoption, a gateway layer over MCP servers would address security, observability, and governance.

**Action**: Research. Evaluate whether a gateway between Claude Code and Praxion's MCP servers would provide value (centralized auth, request logging, rate limiting).

**Timeline**: Q3 2026 evaluation.
**Risk**: Over-engineering risk if adoption stays individual-developer-scale.

#### 5.4 Pipeline Shortcut Paths

The current pipeline is sequential and heavyweight. For well-understood tasks, shortcuts would improve velocity:

- **Direct-to-planner**: User provides acceptance criteria inline, skip researcher and architect
- **Partial pipeline**: User specifies "just plan" or "just implement step N" without full pipeline
- **Resumable pipelines**: Pick up from where a prior session left off using WIP.md state

**Dependencies**: 2.3 (coordinator burden reduction).
**Risk**: Must not compromise quality. Shortcuts must be opt-in, not default.

#### 5.5 Zero-Duration Span Resolution

All OTel spans are ended immediately for Phoenix visibility, making duration metrics meaningless. This is a known design trade-off.

**Action**: Investigate options:
- Phoenix in-progress span rendering (can Phoenix show started-but-not-ended spans?)
- Two-span approach (start marker + end marker with duration attribute)
- Deferred end with background timer

**Dependencies**: 3.1 (eval framework to measure impact).
**Risk**: High complexity. The current approach works; this is an improvement, not a fix.

#### 5.6 Extract `store.py` and `otel_relay.py`

Both files exceed the 800-line coding conventions ceiling:
- `store.py` (947 lines): Extract auto-link logic, helper functions, incoming-link scanning
- `otel_relay.py` (921 lines): Extract span creation methods to `span_factory.py`, agent context tracking to `context_tracker.py`

**Dependencies**: 3.4 (type checking) -- refactor with type safety.
**Risk**: Medium. Refactoring core modules requires thorough test verification.

---

## Deprecation & Cleanup

Items to remove or retire during the roadmap execution:

| Item | Action | Phase |
|------|--------|-------|
| `claude/config/CLAUDE.md` | **KEEP** — intentionally versioned mirror of `~/.claude/CLAUDE.md`; project preserves it under git so the user-level philosophy travels with the repo | — |
| `claude/config/CLAUDE_OLD.md`, `CLAUDE_UNPOLISHED.md` | Deleted in Phase 1.7 (historical trial-version prompts) | 1 ✅ |
| `github-star` skill | Move to command (procedure, not domain expertise). The `/star-repo` command already exists | 4 |
| `TODO.md` | Either expand as canonical tracker or retire in favor of this ROADMAP | 1 |
| `SOLID_FOUNDATION_IMPROVEMENTS.md` | Retire. Open items migrated to this ROADMAP. Done items are historical record | 1 |
| `task-chronograph-mcp/.ai-work/` | Delete leftover pipeline artifacts | 1 |
| `/co` + `/cop` duplication | Refactor: extract shared commit process, `/cop` adds push step | 2 |
| `scripts/__pycache__` | Delete and add to `.gitignore` | 1 |
| Rename `/cajalogic` | Create `/memory` alias for discoverability (keep `/cajalogic` for backward compatibility) | 2 |

---

## Quality Metrics

How we'll know the roadmap is working:

| Metric | Baseline | After Phase 1.1 | After Phase 1.2–1.7 | Phase 1 Target | Phase 3 Target |
|--------|----------|-----------------|---------------------|----------------|----------------|
| Token budget utilization | 95.7% / 109.4%† | 86.9% / 99.3%† | **76.0% / 86.9%†** ✅ (non-doc) / **80.9% / 92.5%†** ✅ (doc) | <80% | <75% |
| Always-loaded rules token count‡ | 10,715 / 12,247† | 10,019 / 11,450† | **10,019 / 11,450† (doc) · 7,299 / 8,342† (non-doc)** ✅ | <8,500 | <8,000 |
| Always-loaded total chars | 57,444 | 52,130 (−5,314) | **45,686 non-doc / 48,572 doc** ✅ | <50,000 | <45,000 |
| Memory recall/search usage | 3+2=5 | 5 (unchanged) | 5 (unchanged — Phase 1.4 addresses entry quality, not recall UX) | >20 per 50 sessions | >50 per 50 sessions |
| Memory entries never accessed | 83% | 83% | **18 entries archived** (6 condensed + 12 status=archived); active surface reduced, access rate TBD | <60% | <40% |
| CI test coverage | 0% of commits | 0% | **`test.yml` matrix workflow shipped** (first real run deferred post-merge) ✅ | 100% of PRs | 100% of PRs + type checking |
| ADR status accuracy | 71% (15/21 correct) | 68% (15/22 correct)§ | **100% (28/28 correctly classified: 26 accepted + 2 superseded + 0 proposed)** ✅ | 100% | 100% |
| Agent turn budget exhaustion rate | Unknown | Unknown | Unknown (deferred to Phase 2.1) | Measured | <10% of invocations |
| Eval pipeline coverage | 1 eval type | 1 eval type | 1 eval type (deferred to Phase 3.1) | 3 eval types | 5+ eval types |
| Skill staleness markers | 0 skills | 0 skills | 0 skills (deferred to Phase 4.3) | 5 version-sensitive skills | All version-sensitive skills |

**Footnotes:**

† Two numbers shown: `(optimistic 4.0 chars/token) / (conservative 3.5 chars/token)`. The original ROADMAP baseline of "96.8%" was between these ratios; `CONTEXT_REVIEW.md` F3 established that actual baseline was 109.4% conservative / 95.7% optimistic. Subsequent metrics are reported at both ratios for honesty. Post-1.2–1.7 numbers are split because Phase 1.5 narrowed `rules/writing/diagram-conventions.md` from always-loaded to doc-authoring-only, so non-doc sessions see ~2,886 fewer chars than doc-authoring sessions.

‡ Always-loaded rules only (excludes CLAUDE.md files). Total always-loaded budget is the "Always-loaded total chars" row.

§ Phase 1.1 added dec-022 (accepted). Phase 1.3 added dec-023 through dec-028 (6 new ADRs) and flipped 5 previously-proposed ADRs to accepted; dec-011 was superseded by dec-023 after the audit found its body contradicted the shipping code. Final state: 28 ADRs / 26 accepted / 2 superseded / 0 proposed.

**Phase 1.1 delivered:**
- Token budget: pulled under the 15,000-token ceiling at both tokenizer ratios (was at or over ceiling pre-refactor depending on ratio)
- Always-loaded chars: 5,314-char reduction (~9.3% of pre-refactor budget)
- Progressive disclosure pattern extended: coordination procedural content now lives in `skills/software-planning/references/coordination-details.md`, loaded only when agents execute the procedures
- CLAUDE.md deliverables block made symmetric across all 4 pipeline agents (was missing implementer)

**Phase 1.2–1.7 delivered (2026-04-12):**
- **CI test pipeline**: SHA-pinned GitHub Actions matrix workflow runs `ruff` + `pytest` across both MCP servers on every push-to-main and PR (1.2)
- **ADR consistency**: 100% correctly classified; dec-011 → dec-023 supersession corrects a documented-vs-implemented contradiction for ADR-first hook injection (1.3)
- **Memory hygiene**: 6 entries condensed from 2K–7.4K chars to ≤400 chars; 12 duplicate/stale entries archived (history preserved); `session_count` fixed via derivation from `observations.jsonl`; stale `memory-mcp/CLAUDE.md` + `store.py:88` migration claim corrected (1.4)
- **Documentation hygiene**: `rules/README.md` gained `writing/diagram-conventions.md`; `SOLID_FOUNDATION_IMPROVEMENTS.md` retired entirely (every count was stale) (1.5)
- **Principles embedding**: `CLAUDE.md` gains a 4-principle cross-reference block; `README.md` gains rich prose anchor (1.6)
- **Cleanup**: `claude/config/CLAUDE_OLD.md` + `CLAUDE_UNPOLISHED.md` deleted (1.7). `claude/config/CLAUDE.md` was initially deleted in error and restored — it is an intentionally versioned mirror of `~/.claude/CLAUDE.md`.
- **Budget relief for Phase 4+ growth**: narrower `diagram-conventions.md` scope reclaims ~2,886 chars on non-doc sessions; total non-doc budget now at 76.0% / 86.9% (well under Phase 1 target of <80%)

**Still needed to reach Phase 3 targets**: Phase 2.1 (turn-budget measurement + systems-architect on Opus); Phase 3.1 (eval framework expansion); Phase 3.4 (type checking in CI); Phase 4.3 (staleness markers).

---

## Guiding Principles for Execution

These principles should govern how the roadmap items are implemented:

1. **Token budget is a first-class constraint**. Every artifact added must justify its token cost. Every artifact removed is a gift to every project that consumes Praxion.

2. **Measure before optimizing**. The eval framework (Phase 3) should inform Phase 4 and 5 decisions. Don't guess what improves quality -- measure it.

3. **One phase at a time within phases, but overlap between phases**. Phase 1 items are independent and can be parallelized. Phase 2 depends on Phase 1 completion. Phase 3 and 4 can overlap.

4. **Preserve what works**. The progressive disclosure model, document-mediated pipeline, and memory enforcement loop are strengths. Evolve them, don't replace them.

5. **Standards convergence is an opportunity**. MCP + AGENTS.md + A2A under AAIF means Praxion's patterns can reach beyond Claude Code. Cross-tool portability increases Praxion's value.

6. **Curiosity over dogma**. Agent Teams, HTTP hooks, MCP Gateways -- these are emerging patterns that may reshape assumptions. Keep the architecture open to evolution. The goal is not to predict the future but to remain responsive to it.

---

*Generated from 6 parallel deep-dive audits covering: skills (33 skills, 7,312 total SKILL.md lines), agents (12 agents, ~55,000 tokens of prompts), rules/commands/hooks (10 rules, 19 commands, 15 hook scripts), infrastructure (2 MCP servers, 631 tests, 9 scripts, 2 CI workflows), knowledge (109 memory entries, 4,358 observations, 21 ADRs, 10 CLAUDE.md files), and external research (10 topic areas, 60+ sources).*
