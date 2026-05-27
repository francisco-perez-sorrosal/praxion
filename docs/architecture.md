---
diataxis: reference
audience: developer
---

# Architecture Guide

<!-- Developer navigation guide. Every component name and file path in this document has been
     verified against the codebase. Only components that exist on disk are included.
     For design rationale, planned components, and architectural evolution, see .ai-state/DESIGN.md.
     Maintained by pipeline agents: created by systems-architect, updated by implementer,
     verified by doc-engineer at pipeline checkpoints.
     See skills/software-planning/references/architecture-documentation.md for the full methodology. -->

## 1. Overview

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated — system attributes live in the architect doc; this section provides developer orientation only) -->

| Attribute | Value |
|-----------|-------|
| **System** | Praxion |
| **Last verified against code** | 2026-05-19 (test-topology M2 — §9 agent wiring; other sections last verified 2026-05-12) |

This document is the **developer-facing** navigation guide: every component, file path, and interface listed here exists on disk and resolves at the cited path. It is the code-verified subset of [`.ai-state/DESIGN.md`](../.ai-state/DESIGN.md), which is the design-target architect-facing document. Use this guide to navigate the codebase; consult the architect doc for system attributes (type, language, pattern), design rationale, planned components, and architectural evolution.

## 2. System Context

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated — L0 diagram is byte-identical to architect doc) -->

The system-boundary L0 diagram is rendered in [`.ai-state/DESIGN.md` §2](../.ai-state/DESIGN.md#2-system-context). External actors: Developer, Claude Code, Claude Desktop, Cursor, Arize Phoenix, GitHub.

> **Component detail:** [Components](#3-components)

## 3. Components

<!-- OWNER: implementer (as-built), doc-engineer (verification) | LAST UPDATED: 2026-04-28 by implementer (migrated L1 Mermaid block to LikeC4-sourced SVG — structurizr-d2-diagrams pipeline) -->
<!-- L1 diagram: major building blocks and their relationships.
     Every component listed here MUST exist on disk — verify with ls/Glob before including.
     Source: docs/diagrams/architecture/src/architecture.c4 | Generated: docs/diagrams/architecture/rendered/components.d2
     Regen: likec4 gen d2 docs/diagrams/ -o docs/diagrams/architecture/ && d2 docs/diagrams/architecture/rendered/components.d2 docs/diagrams/architecture/rendered/components.svg -->

![Praxion Components (L1) — four layers: Knowledge (skills, rules, commands, agents — the authored Markdown family), Orchestration (agent pipeline runtime, hooks, .ai-work/), Persistence (.ai-state/, memory-mcp), Tooling (scripts, dashboard_app); each layer's components and their cross-layer relationships, with knowledge.agents -> orchestration.pipeline "spawns" linking the two sides of agent representation](diagrams/architecture/rendered/components.svg)

*LikeC4 source: [`docs/diagrams/architecture/src/architecture.c4`](diagrams/architecture/src/architecture.c4). The pre-commit hook (`scripts/diagram-regen-hook.sh`) regenerates the SVG above when the source changes.*

| Component | Responsibility | Key Files |
|-----------|---------------|-----------|
| Skills | Delivers domain expertise via progressive disclosure (metadata at startup, body on activation, references on demand). 49 skills on disk (2026-05-12); recent additions: `llm-prompt-engineering`, `ml-training`, `llm-training-eval`, `neo-cloud-abstraction`, `experiment-tracking`, `web-ui-design`, `tui-design`, `agentic-interface-design`, `api-design-craft` | `skills/*/SKILL.md`, `skills/*/references/`, `skills/llm-prompt-engineering/`, `skills/ml-training/`, `skills/llm-training-eval/`, `skills/neo-cloud-abstraction/`, `skills/experiment-tracking/`, `skills/web-ui-design/`, `skills/tui-design/`, `skills/agentic-interface-design/`, `skills/api-design-craft/` |
| Polyglot Skills (TypeScript / Node) | Language-agnostic skill bodies with per-language `contexts/<language>.md` (and `references/<language>.md` for some skills), formalized by the polyglot skill template ADR at `.ai-state/decisions/<NNN>-polyglot-skill-template.md`. Covers Python and TypeScript (Node.js, React, Vue). Two satellite directories per polyglot skill: `references/` for language-agnostic conceptual depth, `contexts/` for runnable language-specific mechanics. Frontend-framework nesting (React, Vue) layers above `contexts/typescript.md` inside the language-rooted `typescript-development` skill. Cross-skill version conflicts (e.g., Zod v3/v4) housed in `node-prj-mgmt`. | `skills/node-prj-mgmt/` (with `contexts/typescript.md`), `skills/typescript-development/` (with `contexts/typescript.md`, `contexts/react.md`, `contexts/vue.md`), `skills/architectural-fitness-functions/contexts/typescript.md`, `skills/deployment/contexts/typescript.md`, `skills/mcp-crafting/contexts/typescript.md`, `skills/software-planning/contexts/typescript.md`, `skills/agent-evals/references/typescript.md`, `skills/test-coverage/references/typescript.md` |
| Agent runtime / Pipeline | Runs the **runtime** side of agents: spawned subprocesses each in their own context window, executing definitions from the Knowledge layer. Coordinates through shared `.ai-work/<task-slug>/` documents and persists to `.ai-state/`. This row is the Orchestration-layer counterpart to the "Agents (authored definitions)" Knowledge row below — see the dual-representation note. Receives skill / rule / command / agent injection from the Knowledge layer and lifecycle enforcement from Hooks | `.ai-work/<task-slug>/`, agent-spawning protocol in `rules/swe/swe-agent-coordination-protocol.md` |
| Rules | Two-channel delivery: 5 core rules + 14 path-scoped rules symlinked into `~/.claude/rules/`; 3 always-loaded hook-deliver rules injected via SessionStart hook `inject_rules.py`. Per-project `.claude/praxion-rules.yaml` disable list reaches both channels uniformly — hook-deliver rules filtered from `additionalContext`; symlinked rules suppressed via `claudeMdExcludes` reconciliation into `.claude/settings.json`. Core rules remain non-disableable. Manifest-driven taxonomy via auto-generated `rules/_manifest.yaml`. ML-specific rules added under `rules/ml/` (ai-training-onramp v1) | `rules/swe/`, `rules/writing/`, `rules/ml/`, `rules/_manifest.yaml`, `hooks/inject_rules.py`, `scripts/regenerate_rules_manifest.py`, `docs/rules-taxonomy.md` |
| Commands | Exposes user-invoked slash commands for repeatable workflows; ai-training-onramp v1 added `/run-experiment` and `/check-experiment` | `commands/*.md`, `commands/run-experiment.md`, `commands/check-experiment.md` |
| Agents (authored definitions) | The `.md` family on disk under `agents/` — peer authoring surface to skills/rules/commands. Each file is a subprocess *specification* (system prompt, tool/skill access, model tier) that installers deploy alongside the other Knowledge-layer surfaces. 15 agents on disk (2026-05-12); recent addition: `interface-designer` (interface-layer design specialist, peers with systems-architect for UI/API/MCP surface decisions). Distinguished from the Orchestration-layer "Agent runtime / Pipeline" row above — Praxion's LikeC4 model dual-represents these two axes; see `.ai-state/DESIGN.md` §3 for the rationale | `agents/*.md`, `agents/interface-designer.md` |
| Hooks | Executes Python/shell scripts on Claude Code lifecycle events for enforcement and observability | `hooks/*.py`, `hooks/*.sh`, `hooks/hooks.json` |
| Praxion-as-first-class enforcement | Three-layer enforcement that carries Praxion's behavioral contract to every subagent including host-native ones. `inject_subagent_context.py` fires on PreToolUse(Agent\|Task) and prepends a compact preamble to every subagent prompt via `updatedInput.prompt`. `inject_process_framing.py` fires on UserPromptSubmit and emits a compact `additionalContext` reminder for non-trivial prompts in Praxion projects. Both hooks fast-skip on absent `.ai-state/` and opt-out env vars, exiting 0 unconditionally on any error | `hooks/inject_subagent_context.py`, `hooks/inject_process_framing.py`, `hooks/hooks.json` |
| Install-path completeness | First-session auto-completion that converges marketplace-only installs on the same end state as clone installs. `auto_complete_install.py` fires on SessionStart, checks for missing global surfaces, and runs the completion logic using git-config defaults or an interactive prompt with 30-second timeout-accept. Idempotent — fast-skips in <50 ms after the first successful run via a marker file. `render_claude_md.py` provides the shared template-substitution helper used by both the install scripts and this hook | `hooks/auto_complete_install.py`, `scripts/render_claude_md.py`, `hooks/hooks.json` |
| Memory MCP | Stores persistent dual-layer memory: curated knowledge (JSON) + automatic observations (JSONL) | `memory-mcp/src/memory_mcp/` |
| Chronograph MCP | Provides agent pipeline observability via OpenTelemetry spans | `task-chronograph-mcp/src/task_chronograph_mcp/` |
| `.ai-state/` | Holds persistent project intelligence: ADRs, specs, sentinel reports, architecture docs, memory | `.ai-state/decisions/`, `.ai-state/memory.json` |
| `.ai-work/` | Contains ephemeral pipeline documents scoped by task slug | `.ai-work/<task-slug>/` |
| Installers | Deploys target-specific configurations (Claude Code, Claude Desktop, Cursor) | `install.sh`, `install_claude.sh`, `install_cursor.sh` |
| Scripts | Provides developer tooling: worktree management, merge drivers, daemon control | `scripts/` |
| Greenfield project onboarding | Scaffolds a Claude-ready project into an empty directory and hands off to an interactive Claude session pre-loaded with `/new-project`. Bash handles deterministic prereqs + minimal scaffold; the slash command runs the conversational flow, generates the default Python + `uv` + Claude Agent SDK + FastAPI app, writes a per-run `onboarding_for_mushi_busy_ppl.md`, and chains to `/onboard-project` for the remaining surfaces (git hooks, merge drivers, `.ai-state/` skeleton, `.claude/settings.json` toggles). Integration-tested via bash. See [docs/greenfield-onboarding.md](greenfield-onboarding.md) for the user-facing guide | `new_project.sh` (repo root), `commands/new-project.md`, `docs/greenfield-onboarding.md`, `tests/new_project_test.sh` |
| Existing-project onboarding | Phased, gated `/onboard-project` slash command that retrofits an existing repo with Praxion's surfaces: `.gitignore` AI-assistants block, `.ai-state/` skeleton (`decisions/drafts/`, `DECISIONS_INDEX.md`, `TECH_DEBT_LEDGER.md`, `calibration_log.md`), `.gitattributes` + `git config` merge driver registration, git hooks (pre-commit id-citation discipline + post-merge ADR finalize/tech-debt dedupe/squash-safety), `.claude/settings.json` PRAXION_DISABLE_* toggles via multi-select, `CLAUDE.md` blocks (Agent Pipeline + Compaction Guidance + Behavioral Contract). Each phase has an idempotency predicate so re-runs are no-ops. Pre-flight detects greenfield-shape and redirects to `/new-project`. See [docs/existing-project-onboarding.md](existing-project-onboarding.md) for the user-facing guide | `commands/onboard-project.md`, `docs/existing-project-onboarding.md` |
| Concurrency & collaboration model | Unifies multi-worktree and multi-user coordination around shared primitives: fragment-named draft ADRs under `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` promoted to `<NNN>-<slug>.md` at merge-to-main, unified worktree home at `.claude/worktrees/`, two-layer squash-merge safety (command refuse + post-merge warn), opt-in auto-memory orphan cleanup. Post-merge hook runs reconcile → finalize → squash-safety in that order | `scripts/finalize_adrs.py`, `scripts/check_squash_safety.py`, `scripts/migrate_worktree_home.sh`, `scripts/git-finalize-hook.sh`, `commands/clean-auto-memory.md`, `commands/create-worktree.md`, `commands/merge-worktree.md`, `rules/swe/vcs/pr-conventions.md`, `rules/swe/adr-conventions.md`, `.ai-state/decisions/drafts/` |
| Project metrics command | `/project-metrics` slash command computes curated complexity/health metrics (SLOC, CCN, cognitive complexity, cyclic deps, churn, entropy, truck factor, hotspots, coverage) on any Praxion-onboarded repo. Two-tier collector plugin architecture: Tier 0 universal (`git` + stdlib, optional `scc`) and Tier 1 Python (`lizard` / `complexipy` / `pydeps` / `coverage.py` artifact parse) for v1. Produces a per-run JSON+MD artifact pair under `.ai-state/metrics_reports/METRICS_REPORT_YYYY-MM-DD_HH-MM-SS.{json,md}` plus an append-only sibling `.ai-state/metrics_reports/METRICS_LOG.md`. Frozen aggregate-block column contract; graceful degradation with uniform skip markers when optional tools are absent. Draft ADRs under `.ai-state/decisions/drafts/` carry the design rationale (storage-schema-for-project-metrics, collector-protocol, graceful-degradation-policy, hotspot-formula) and finalize to stable NNN at merge-to-main | `commands/project-metrics.md`, `scripts/project_metrics/` (package: `cli.py`, `schema.py`, `runner.py`, `hotspot.py`, `trends.py`, `report.py`, `logappend.py`, `collectors/` with six collectors), `scripts/project_metrics/tests/` (16 test modules + `build_fixtures.py`-generated fixture repos), `docs/metrics/README.md` (complete JSON schema reference) |
| Tech-debt ledger | Living, append-only `.ai-state/TECH_DEBT_LEDGER.md` — single Markdown table with stable `td-NNN` IDs and a 15-field schema (14 row fields + structural `dedup_key`). Producers: verifier (per-change Phase 5/5.5 writes) and sentinel (repo-wide TD dimension TD01–TD04 writes; TD05 audits only). Consumers: five existing agents (`systems-architect`, `implementation-planner`, `implementer`, `test-engineer`, `doc-engineer`) read the ledger, filter by their `owner-role`, and update `status` in place — framed as permission-not-obligation, not a mandate. Promethean, roadmap-cartographer, `/project-metrics`, and `/project-coverage` are signal sources only and never write ledger rows. Notes-merge separator is ` // ` (chosen to avoid collision with the Markdown table column delimiter `|`). Worktree concurrency handled by append-only convention plus a post-merge dedupe step (`scripts/finalize_tech_debt_ledger.py`, modeled on `scripts/finalize_adrs.py`; chained into `scripts/git-finalize-hook.sh` after `finalize_adrs.py`). Schema, owner-role heuristic, and worktree-merge dedupe semantics are canonical in `skills/software-planning/references/tech-debt-ledger.md`; design rationale lives in the draft ADRs under `.ai-state/decisions/drafts/` (promoted to stable `dec-NNN` at merge-to-main; see `.ai-state/decisions/DECISIONS_INDEX.md`). Ledger file exists on disk (empty header-only at first producer write); producer wiring (`agents/verifier.md` Phase 5/5.5 + `agents/sentinel.md` TD dimension), consumer contracts (single-line input on the five reader agents), and template migration (`## Technical Debt` removed from `skills/software-planning/references/document-templates.md`) all landed in the tech-debt-integration pipeline | `.ai-state/TECH_DEBT_LEDGER.md`, `rules/swe/agent-intermediate-documents.md`, `scripts/finalize_tech_debt_ledger.py`, `scripts/git-finalize-hook.sh`, `agents/verifier.md`, `agents/sentinel.md`, `agents/{systems-architect,implementation-planner,implementer,test-engineer,doc-engineer}.md`, `skills/software-planning/references/document-templates.md` |
| ML training subsystem (v1) | Skill set, rules, and command extensions for managing ML/AI pre-training projects — Praxion's third project archetype. **Skills**: `ml-training` (pre-training conventions, distributed training, operational modes A/B/C), `llm-training-eval` (eval methodology, val_bpb/perplexity, `TRAINING_RESULTS.md` schema), `experiment-tracking` (MLflow / W&B / Aim conventions; distinct from app observability). **Reference extensions**: `gpu-compute-budgeting` under `deployment`; `ml-experiment-ci` under `cicd`. **Rules**: `rules/ml/eval-driven-verification.md` (always-loaded), `rules/ml/gpu-budget-conventions.md` (always-loaded), `rules/ml/experiment-tracking-conventions.md` (path-scoped). **Rule extensions**: determinism waiver in `rules/swe/testing-conventions.md`; experiment-mode addendum in `rules/swe/vcs/git-conventions.md`. **Agent extensions**: verifier Phase 3a (eval-aware sub-branch); cicd-engineer ML detection step. **Commands**: `/run-experiment`, `/check-experiment`. **Command extension**: `/onboard-project` Phase 8c (ML detection + scaffold). **Artifact categories**: `program.md` (project-local meta-prompt) and `TRAINING_RESULTS.md` (training run result, archival to `.ai-state/training_runs/`) | `skills/ml-training/SKILL.md`, `skills/llm-training-eval/SKILL.md`, `skills/experiment-tracking/SKILL.md`, `skills/deployment/references/gpu-compute-budgeting.md`, `skills/cicd/references/ml-experiment-ci.md`, `rules/ml/eval-driven-verification.md`, `rules/ml/gpu-budget-conventions.md`, `rules/ml/experiment-tracking-conventions.md`, `commands/run-experiment.md`, `commands/check-experiment.md`, `agents/verifier.md` (Phase 3a), `agents/cicd-engineer.md` (ML detection step) |
| Neo-cloud abstraction | Mode-invariant abstraction surface for ML training compute lifecycle. Defines `training_job_descriptor` schema (shared across modes A/B/C; no `mode:` field — backend inferred from project config) and 8 lifecycle operations (create, start, status, log_stream, cancel, artifact_fetch, list, pricing_query). Tiered backend strategy: local default (modes A/B), SkyPilot 0.12.1 default-remote (mode C, 20+ providers), RunPod direct adapter v1 reference | `skills/neo-cloud-abstraction/SKILL.md`, `skills/neo-cloud-abstraction/references/local-backend.md`, `skills/neo-cloud-abstraction/references/skypilot-backend.md`, `skills/neo-cloud-abstraction/references/runpod-direct-adapter.md` |
| Pipeline Dashboard | Next.js App Router + TypeScript dashboard service providing the per-project visual entry point. Seven surfaces (Architecture / Workshops / ADRs / Sentinel / Roadmap / Metrics / Documentation) read `.ai-state/`, `.ai-work/<task-slug>/`, and selected project-root surfaces directly — no new persistence layer; read-only by design. Served through `scripts/praxion-dashboard` with deterministic per-project ports and a user-scoped Node home under `~/.praxion-dashboard/`. Redesign layer: interactive SVG diagram viewer (pan/zoom, `usePanZoom`), ADR relationship graph and workshop step DAG (`DecisionGraph`), recharts trend charts (`TrendChart`, `Sparkline`), Diátaxis-typed renderer registry, server-side SVG sanitization (`sanitize-html`), `/api/diagram` route handler streaming allowlisted project-root SVGs. CSS is split into six cascade-ordered layer files — `globals.css` is now an `@import` manifest of `tokens.css` / `base.css` / `app-chrome.css` / `surfaces.css` / `widgets.css` / `pages-and-viz.css` (td-030). Replaced an earlier Streamlit prototype (`streamlit_app/`, removed in commit `313a50e`). | `dashboard_app/` (incl. `src/app/{globals,tokens,base,app-chrome,surfaces,widgets,pages-and-viz}.css`, `src/app/api/diagram/route.ts`, `src/components/viz/`, `src/components/shells/`, `src/components/chrome/`, `src/components/registry.ts`, `src/server/diagrams/`, `src/server/aac/`, `src/server/sentinel/`), `scripts/praxion-dashboard`, `commands/dashboard.md` |
| Roadmap cartographer | Project-level audit-to-roadmap generator: a project-derived evaluation-lens set drives a parallel multi-lens audit, then synthesis, then user-gated `ROADMAP.md` emission for any project (deterministic / agentic / hybrid). SPIRIT is one exemplar lens set among DORA / SPACE / FAIR / CNCF Platform Maturity / Custom. Invoked via `/roadmap` (modes: fresh / diff / `<focus-area>`); per `dec-092` Praxion itself does not carry a living `ROADMAP.md` instance — the cartographer regenerates on demand | `agents/roadmap-cartographer.md`, `skills/roadmap-synthesis/`, `commands/roadmap.md` |
| Eval framework — LLM-as-judge harness | Out-of-band quality evaluation via two commands: `/eval` (Tier 1 behavioral artifact-manifest check) and `/eval-praxion` (Tier 2 LLM-as-judge over completed artifacts). The `harness/` sub-package runs Family 1 (pipeline-outcome fidelity: ADR structure, supersession reciprocity, traceability, option-depth substantiveness via LLM) and Family 2 (behavioral-contract adherence: reads `VERIFICATION_REPORT.md`, judges the four-behavior rubric via LLM). A single `JudgeClient` adapter encapsulates the auth-mode seam (`CLAUDE_CODE_OAUTH_TOKEN` → Agent SDK; `ANTHROPIC_API_KEY` → Messages API); family code never imports SDKs directly. The Agent SDK route is bounded and guarded: `AgentSdkJudgeClient.__init__()` refuses construction (three-part `RuntimeError`) when `CLAUDECODE=1` (nested-Claude-Code-session deadlock, SDK issue #573); `AgentSdkJudgeClient.judge()` enforces a 120 s ceiling via `asyncio.wait_for`, with an `API_TIMEOUT_MS` defense-in-depth on the subprocess. The orchestrator emits per-family and per-LLM-check progress via `print(..., flush=True)`. The `eval/` package is in the CI matrix alongside `memory-mcp` and `task-chronograph-mcp`. Reports land in `.ai-state/praxion_eval_reports/` with an append-only log. The `regression/` sub-package was retired (448 LOC, broken-by-design per td-005). Invocation is strictly out-of-band per dec-040 clause 1 and 2; dec-204 narrows clause 3 to allow LLM-as-judge calls over completed artifacts; dec-206 re-affirms dec-204 and adds the refusal/bounding behavior. | `eval/src/praxion_evals/harness/` (`schemas.py`, `judge_client.py`, `corpus_reader.py`, `orchestrator.py`, `cli.py`, `report_writer.py`, `families/family1_pipeline_fidelity.py`, `families/family2_bc_adherence.py`), `eval/src/praxion_evals/behavioral/`, `commands/eval.md`, `commands/eval-praxion.md`, `.ai-state/praxion_eval_reports/`, `.github/workflows/test.yml` |

## 4. Interfaces

<!-- OWNER: implementer (as-built) | LAST UPDATED: 2026-04-12 -->
<!-- Key APIs, contracts, and integration points between components.
     Only interfaces that are implemented and callable. -->

| Interface | Type | Provider | Consumer(s) | Contract |
|-----------|------|----------|-------------|----------|
| Plugin manifest | JSON | `plugin.json` | Claude Code plugin system | Skills/commands via directory globs, agents via explicit paths, MCP via command+args |
| Hook lifecycle | JSON (stdin/stdout) | Claude Code | `hooks/*.py` | Exit 0 = allow + process stdout JSON; exit 2 = block + stderr feedback |
| Hook events HTTP | HTTP POST | `hooks/send_event.py` | Chronograph MCP | `localhost:8765/api/events` with event payload |
| Memory MCP | stdio (MCP) | `memory-mcp` | Claude Code, agents, hooks | 18 tools + 2 resources; schema v2.0 |
| Chronograph MCP | stdio (MCP) + HTTP | `task-chronograph-mcp` | Claude Code (stdio), hooks (HTTP) | 3 MCP tools; HTTP daemon on port 8765 |
| OTLP export | HTTP | Chronograph MCP | Arize Phoenix | OTLP HTTP to `localhost:6006/v1/traces` |
| Pipeline documents | Markdown files | Upstream agents | Downstream agents | Shared `.ai-work/<task-slug>/` directory; fragment files for parallel writes |
| Skill progressive disclosure | YAML frontmatter + Markdown | `SKILL.md` files | Claude Code skill loader | 3 tiers: metadata (startup), body (activation), references (on-demand) |
| Hook registration | JSON | `hooks/hooks.json` | Claude Code plugin system | Event type, command, timeout, sync/async per hook |
| Git post-merge hook chain | Shell | `scripts/git-finalize-hook.sh` | Git (post-merge event) | Runs `reconcile_ai_state.py --post-merge`, then `finalize_adrs.py --merged`, then `check_squash_safety.py`. Load-bearing order — reconcile handles memory/observations, finalize promotes drafts, squash-safety is diagnostic-only |
| Draft ADR lifecycle | Markdown + YAML | Pipeline agents (architect, planner) | `scripts/finalize_adrs.py` | Drafts at `.ai-state/decisions/drafts/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md` with `id: dec-draft-<8-char-hash>` and `status: proposed`; finalize renames to `<NNN>-<slug>.md`, rewrites cross-references across sibling ADRs, `.ai-work/*/LEARNINGS.md`, `SYSTEMS_PLAN.md`, `IMPLEMENTATION_PLAN.md`; idempotent |

## 5. Data Flow

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated — diagrams are byte-identical to architect doc) -->

The agent-pipeline execution sequence, the memory + observability flow, and the tech-debt ledger flow are diagrammed in [`.ai-state/DESIGN.md` §5](../.ai-state/DESIGN.md#5-data-flow). The architect doc additionally diagrams the ADR finalize flow.

For developers: the entry point for tracing a pipeline run is `EnterWorktree` (main agent) → researcher → systems-architect → implementation-planner → (implementer ∥ test-engineer) → verifier, with all artifacts under `.ai-work/<task-slug>/`. Memory and observation correlation goes through the OpenInference `session.id` attribute and W3C trace-context (`traceparent`) — see [`task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py`](../task-chronograph-mcp/src/task_chronograph_mcp/otel_relay.py) and [`memory-mcp/src/memory_mcp/correlation.py`](../memory-mcp/src/memory_mcp/correlation.py).

## 6. Dependencies

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated — single source of truth is the architect doc) -->

External dependencies, versions, and criticality classifications are listed in [`.ai-state/DESIGN.md` §6](../.ai-state/DESIGN.md#6-dependencies). Verified against `pyproject.toml` and project config.

## 7. Constraints

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated — developer-relevant constraints were a strict subset of the architect doc's; the architect doc is the single source) -->

System constraints (performance, compatibility, technical, behavioral, architectural) are listed in [`.ai-state/DESIGN.md` §7](../.ai-state/DESIGN.md#7-constraints). Three additional architect-only rows live there: the four-behavior agent contract, git as the sole synchronization substrate, and ADR fragment-naming.

## 8. Decisions

<!-- OWNER: doc-engineer (verification) | LAST UPDATED: 2026-04-28 (deduplicated per dec-021's "never duplicate ADR rationale" intent) -->

Architectural decisions are recorded as ADRs in [`.ai-state/decisions/`](../.ai-state/decisions/). The canonical, auto-generated cross-reference is [`DECISIONS_INDEX.md`](../.ai-state/decisions/DECISIONS_INDEX.md). For design-target rationale, see [`.ai-state/DESIGN.md`](../.ai-state/DESIGN.md) — this developer guide intentionally does not summarize decisions inline.

## 9. Test Topology

<!-- Developer-facing navigation guide. Components named in this section have been verified
     against the codebase. Items marked Planned are not on disk and will be created by
     consumer projects, not Praxion.
     For design rationale and ADR cross-references, see .ai-state/DESIGN.md §9.
     Last verified against code: 2026-05-19. -->

### 9.1 Where to find what

The test-topology subsystem lets each implementation step run only the tests covering its affected subsystems plus their integration boundaries. Three execution tiers (`step` / `phase` / `pipeline`) and a sentinel-driven refactor trigger emerge from a per-project topology declaration. At M2 the six pipeline agents are wired to author and honor the topology when a project has one.

| You want to... | Look at | Status |
|---|---|---|
| Read the language-agnostic schema | `skills/testing-strategy/references/test-topology.md` | Built |
| Read the Python-specific tooling concretization | `skills/testing-strategy/references/python-testing.md` (test-topology section) | Built |
| Read the growth-trigger policy and `--init` path | `skills/testing-strategy/references/test-topology.md` §"Growth-Trigger Policy" | Built (M2) |
| See whether your project has populated its topology | `.ai-state/TEST_TOPOLOGY.md` (per-project) | Planned (no Praxion population by design) |
| Read the sentinel checks for topology health | `agents/sentinel.md` `### Test Topology (TT)` (TT01–TT06) | Built |
| See the debt class for topology drift | `rules/swe/agent-intermediate-documents.md` (`class` enum) | Built (`topology-drift`) |
| Add a Tests: field to a step in your IMPLEMENTATION_PLAN.md | `skills/software-planning/SKILL.md` step schema | Built |
| Create or refresh a project's topology | `commands/refresh-topology.md` (`--init` / default) | Built (M2) |

### 9.2 Activation status in Praxion

Praxion ships the schema, conventions, agent wiring, and the `/refresh-topology` command, but does **not** populate `.ai-state/TEST_TOPOLOGY.md` for itself — Praxion's ~35 s test fleet is below the growth-trigger thresholds, and the behavioral pilot is deliberately deferred to the first consumer project that crosses the gate. A consumer project that adopts the i-am plugin and grows past the thresholds runs `/refresh-topology --init` to create its topology.

For Praxion development today, this means:

- The implementer continues to run the project's default test command (`uv run pytest` or `cd <pocket> && uv run pytest`) per pocket. The `Tests:` step-schema field is not emitted in Praxion plans because Praxion has no populated topology.
- Sentinel TT01–TT05 self-deactivate (no `.ai-state/TEST_TOPOLOGY.md` to check). TT06 (advisory growth trigger) is evaluated but does not fire — Praxion's runtime is below threshold.
- The systems-architect's Phase 2 topology-readiness check is evaluated but does not fire.
- The full-suite integration checkpoint at the end of each pipeline remains today's behavior.

### 9.3 Adding a new language leaf (procedure)

If a future contributor extends the test-topology to a new language (Go, TypeScript, Rust, etc.), the procedure is purely additive:

1. Create `skills/testing-strategy/references/<language>-testing.md` (or extend an existing language reference).
2. In the trunk reference (`skills/testing-strategy/references/test-topology.md`), append rows to the two registry tables:
   - `selector_strategy` — at minimum one identifier (e.g., `go-test-packages`) with its argument shape.
   - `parallel_runner` — at minimum one identifier (e.g., `go-test-parallel`) with its concrete invocation.
3. Document the leaf's `shared_fixture_scope` mapping (which language-framework scope keyword maps to each of `none / per-test / per-file / per-process / per-suite`).
4. Provide a worked invocation example.

No edits to the trunk schema, the sentinel TT01–TT06 wording, the closure semantics, or any agent definition are required. The hypothetical Go module worked example in the trunk reference (`skills/testing-strategy/references/test-topology.md` §"Go Module — Portability Proof") is the proof artifact.

### 9.4 Caveats developers should know

- **Marker name shape**: when a project does populate the topology and its language leaf is Python, group ids in `TEST_TOPOLOGY.md` are kebab-case (`memory-store-core`) but the corresponding pytest marker is snake_case (`memory_store_core`). The kebab → snake mapping is mechanical (`-` → `_`).
- **Reserved marker names**: do NOT use `parametrize`, `skipif`, `usefixtures`, `xfail`, `xdist_group`, `parallel_unsafe`, or any of `unit / integration / contract / e2e` as group ids — they collide with built-in or reserved markers. Sentinel TT05 enforces this.
- **`integration_boundaries` are one-hop**: a `phase`-tier selection runs the named groups plus their direct boundary neighbors, not the transitive closure. The `pipeline`-tier (full suite) covers the transitive case.
- **Lightweight tier**: the protocol does NOT activate at Lightweight tier. Lightweight tasks run today's default test command. If a Lightweight task grows beyond 3 files, escalate to Standard rather than half-engaging the topology.

For the design rationale behind any of the above, see [`.ai-state/DESIGN.md` §9](../.ai-state/DESIGN.md#9-test-topology).

## 10. Pipeline Feedback Loops

<!-- OWNER: doc-engineer (verification), systems-architect (loop semantics) | LAST UPDATED: 2026-05-14 — pipeline-loops-docs pipeline -->

Praxion's agent pipeline is no longer linear. Two feedback edges close the forward flow into a graph:

- **Forward-feeding (CIS)** — the researcher's Hat 2 surfaces a strictly-better library or framework and writes it into `RESEARCH_FINDINGS.md § Continuous Improvement Signals`; the systems-architect dispositions each signal during Phase 7 trade-off analysis. See [§10.2](#102-continuous-improvement-signals-cis-loop).
- **Backward-feeding (Rework)** — the verifier's Phase 12.5 clusters FAIL/WARN findings into `REWORK_MANIFEST.md` rows; the main agent spawns rework worktrees and `/resume-rework` dispatches `systems-architect` (always first per the routing invariant). See [§10.1](#101-verifier-rework-loop).

Both loops share a single disposition vocabulary — `switch-now` / `defer-with-rationale` / `dismiss-with-rationale` — defined in [`skills/software-planning/references/disposition-vocabulary.md`](../skills/software-planning/references/disposition-vocabulary.md) and consumed by both surfaces ([`dec-179`](../.ai-state/decisions/179-verifier-rework-loop-shared-disposition-vocabulary.md)).

<!-- aac:generated source=docs/diagrams/architecture/src/architecture.c4 view=agent_pipeline last-regen=2026-05-14 -->
![Agent Pipeline (L2) — forward flow from promethean through researcher, systems-architect, implementation-planner, parallel implementer / test-engineer / doc-engineer, and verifier; sentinel and architect-validator branch off as independent audits](diagrams/architecture/rendered/agent_pipeline.svg)
<!-- aac:end -->

<!-- aac:generated source=docs/diagrams/architecture/src/architecture.c4 view=feedback_loops last-regen=2026-05-14 -->
![Pipeline Feedback Loops (L2) — CIS forward edge (researcher → systems-architect) overlaid with the Rework backward edge (verifier → main agent → /resume-rework → systems-architect); both share the disposition vocabulary](diagrams/architecture/rendered/feedback_loops.svg)
<!-- aac:end -->

### 10.1 Verifier Rework Loop

<!-- OWNER: implementer (as-built) | LAST UPDATED: 2026-05-14 — Step 24 Group H, verifier-rework-loop pipeline -->
<!-- Only Built components appear here. For the Designed-phase narrative and data-flow diagrams,
     see .ai-state/DESIGN.md §3 (Verifier rework loop row) and §5 (Verifier Rework Loop sub-section). -->

Automated self-healing loop that replaces today's manual user action after a failed verification. When the verifier's `VERIFICATION_REPORT.md` contains FAIL/WARN findings, Phase 12.5 clusters them into rework rows and emits a `REWORK_MANIFEST.md`. The main agent reads the manifest, spawns one rework worktree per row via `EnterWorktree`, and writes a `VERIFIER_FINDINGS.md` into each worktree. The user opens a fresh session in the rework worktree, where the SessionStart banner hook surfaces the `/resume-rework` command. That command auto-discovers the findings file and dispatches `systems-architect` (always first, per routing invariant); for implementation-class clusters the architect's `SYSTEMS_PLAN.md` feeds the standard pipeline. Subagent isolation is enforced by `hooks/worktree_guard.py` and verified by the controlled-test harness before GA.

<!-- aac:generated source=docs/diagrams/architecture/src/architecture.c4 view=rework_loop_detail last-regen=2026-05-14 -->
![Rework Loop Detail (L2) — verifier Phase 12.5 emits REWORK_MANIFEST.md, main agent spawns per-row worktrees via EnterWorktree, /resume-rework dispatches systems-architect (always-first), and the standard pipeline runs to closure with td-NNN status migrating open → in-flight → resolved](diagrams/architecture/rendered/rework_loop_detail.svg)
<!-- aac:end -->

| Component | File | Role |
|-----------|------|------|
| Verifier Phase 12.5 | `agents/verifier.md` (lines 317–448) | Cluster FAIL/WARN findings; emit `REWORK_MANIFEST.md` with stable `rw-<8-char-hash>` row IDs |
| Manifest helper module | `scripts/rework_manifest.py` | Pure functions: `compute_row_id`, `parse_json_blocks`, `render_table_from_rows` |
| Architect Phase 1 intake adapter | `agents/systems-architect.md` (line 47) | One sentence: accept `VERIFIER_FINDINGS.md` as primary intake when no `RESEARCH_FINDINGS.md` exists |
| Planner Phase 1 intake adapter | `agents/implementation-planner.md` (line 45) | One sentence: same intake contract as the architect, preserving `SYSTEMS_PLAN.md`-required invariant |
| `/resume-rework` command | `commands/resume-rework.md` | Fresh-session entry point; cwd-driven auto-discovery of `VERIFIER_FINDINGS.md`; validates schema + manifest-match; dispatches `systems-architect` |
| Banner affordance | `hooks/inject_worktree_banner.py` (lines 107–138) | SessionStart hook detects `VERIFIER_FINDINGS.md` under `.ai-work/*/`; appends two-line `/resume-rework` hint to the worktree banner |
| Subagent isolation test harness | `hooks/test_worktree_guard_subagent.py` + `hooks/MANUAL_VERIFICATION.md` | td-034 SHIP GATE — controlled-test Path A + manual-fallback Path B |
| Hybrid dispatch script | `scripts/dispatch-reworks` | Default `--bg` headless mode (`claude --bg /resume-rework` per row, marker-file correlation, osascript Stop hook) + opt-in `--terminals` mode (`claude-cli://` fan-out); `--dry-run` previews the dispatch plan |
| Notification hook | `hooks/notify_bg_session_state.py` | macOS `display notification` via osascript on `--bg` session Stop; correlates the Stop event's `session_id` against `~/.claude/rework_sessions/<short_id>` markers written by the dispatcher |
| Slash command wrapper | `commands/dispatch-reworks.md` | `/dispatch-reworks` with flag passthrough to the script |

**See also**: [`rework-dispatch.md`](rework-dispatch.md) — user-facing how-to for dispatching reworks, monitoring `--bg` sessions in a fresh Cursor pane via `claude agents`, handling mid-rework prompts, and troubleshooting the notification path.
| Disposition vocabulary | `skills/software-planning/references/disposition-vocabulary.md` | Shared reference for `switch-now` / `defer-with-rationale` / `dismiss-with-rationale`; cited by verifier, researcher, architect, and `/resume-rework` |

**Data flow:** verifier Phase 12.5 emits `REWORK_MANIFEST.md` → main agent reads manifest, calls `EnterWorktree` per row, writes `VERIFIER_FINDINGS.md` into each rework worktree, and flips linked `td-NNN` rows from `open` to `in-flight` → user opens a fresh Claude Code session inside the rework worktree → `inject_worktree_banner.py` appends the `/resume-rework` hint → user runs `/resume-rework` → command validates the findings file and dispatches `systems-architect` with absolute paths → architect produces `SYSTEMS_PLAN.md` (reading `VERIFIER_FINDINGS.md` as primary intake) → implementation-planner decomposes into steps → implementer + test-engineer execute → verifier re-runs on the parent task slug to confirm clean → `/merge-worktree` promotes the fix and `scripts/finalize_tech_debt_ledger.py` migrates `td-NNN` to resolved.

**Last verified against code:** 2026-05-14

**Built:** all components above resolve to files on disk; subagent-isolation manual verification pending per `hooks/MANUAL_VERIFICATION.md` before GA.

### 10.2 Continuous Improvement Signals (CIS) Loop

<!-- OWNER: doc-engineer (verification), systems-architect (loop semantics) | LAST UPDATED: 2026-05-14 — pipeline-loops-docs pipeline -->
<!-- Only Built components appear here. CIS is forward-feeding: it adds an edge from the
     researcher stage to the systems-architect stage that does not change what is built in
     the current task. The disposition vocabulary is shared with the rework loop (§10.1)
     so the ecosystem speaks with one voice across forward and backward flows. -->

Forward-feeding loop that turns ecosystem opportunity into recorded architectural intent. During Phase 3 external research the researcher wears **Hat 2** — a continuous-improvement obligation to surface a library, framework, or approach that appears strictly better than the incumbent for the same capability, **even when the current task does not require switching**. Each such opportunity becomes a row in `RESEARCH_FINDINGS.md § Continuous Improvement Signals` with explicit criteria and trade-offs. The systems-architect reads that section during Phase 7 (Trade-off Analysis) and **must** record an explicit disposition for every surfaced signal — `switch-now`, `defer-with-rationale`, or `dismiss-with-rationale` — in `SYSTEMS_PLAN.md` (and, for load-bearing decisions, in an ADR fragment under `.ai-state/decisions/drafts/`). Silent dismissal is a behavioral-contract violation. A `defer-with-rationale` disposition is the canonical input for a future `.ai-state/TECH_DEBT_LEDGER.md` row, filed by the verifier, sentinel, orchestrator, or architect-validator from the documented rationale.

<!-- aac:generated source=docs/diagrams/architecture/src/architecture.c4 view=cis_loop_detail last-regen=2026-05-14 -->
![CIS Loop Detail (L2) — researcher Hat 2 writes Continuous Improvement Signals into RESEARCH_FINDINGS.md, systems-architect Phase 7 dispositions each signal as switch-now / defer-with-rationale / dismiss-with-rationale, and deferred signals become eligible inputs for tech-debt-ledger rows filed by verifier or sentinel](diagrams/architecture/rendered/cis_loop_detail.svg)
<!-- aac:end -->

| Component | File | Role |
|-----------|------|------|
| Researcher Hat 2 obligation | `agents/researcher.md` (lines 44–52, 101, 133) | Hat 2 — External Researcher; mandatory modern library/framework survey when selection is in scope; current-stack contrast that escalates to CIS when one or more candidates appear strictly better |
| `## Continuous Improvement Signals` section | `agents/researcher.md` (lines 203–220) | Authored into `RESEARCH_FINDINGS.md`; included only when Hat-2 research surfaced strictly-better candidates; bar is "strict improvement on multiple criteria the project demonstrably cares about, with trade-offs honestly stated" |
| Architect Phase 7 disposition obligation | `agents/systems-architect.md` (lines 121, 184–188) | Phase 5 alternatives evaluation acknowledges CIS signals; Phase 7 trade-off analysis resolves them with an explicit disposition; silent dismissal flagged as Register Objection violation |
| Disposition vocabulary | `skills/software-planning/references/disposition-vocabulary.md` | Shared reference for `switch-now` / `defer-with-rationale` / `dismiss-with-rationale`; one vocabulary across CIS (forward) and rework (backward) surfaces |
| Tech-debt ledger eligibility | `.ai-state/TECH_DEBT_LEDGER.md` + `skills/software-planning/references/tech-debt-ledger.md` | Deferred CIS dispositions are the canonical input for `defer-with-rationale` debt rows; ledger writers (verifier, sentinel, orchestrator, architect-validator) file from the recorded rationale |

**Data flow:** researcher Phase 3 external research surfaces a strictly-better library/framework via Hat 2 → researcher Phase 4 comparative-analysis grades the incumbent against modern candidates on equal axes → researcher Phase 5 emits `## Continuous Improvement Signals` into `RESEARCH_FINDINGS.md` (one row per signal: candidate name, current-stack incumbent, evaluation axes, recommendation framing) → architect Phase 5 acknowledges signals in alternatives evaluation, deferring resolution to Phase 7 → architect Phase 7 (Trade-off Analysis) records a disposition for each signal in `SYSTEMS_PLAN.md`; load-bearing dispositions also land in an ADR fragment under `.ai-state/decisions/drafts/` → for `switch-now`, the migration work is added to the implementation plan; for `defer-with-rationale`, the architect documents the future-switch criteria and the signal becomes eligible for a tech-debt-ledger row; for `dismiss-with-rationale`, the architect states the reason the comparison does not hold under the project's constraints.

**Last verified against code:** 2026-05-14

**Built:** all components above resolve to files on disk; CIS semantics canonical in the researcher and systems-architect agent definitions, with the shared disposition vocabulary in [`disposition-vocabulary.md`](../skills/software-planning/references/disposition-vocabulary.md) ([`dec-179`](../.ai-state/decisions/179-verifier-rework-loop-shared-disposition-vocabulary.md)).

## 11. Hackathon Mode

<!-- OWNER: implementer (as-built) | LAST UPDATED: 2026-05-15 — hackathon-mode pipeline Step 14; diagram added by doc-engineer -->
<!-- Only Built components appear here — every path was verified with `test -e` before listing.
     For the design-target rationale (four-channel activation, independence guarantee), see
     .ai-state/DESIGN.md §3 (Hackathon Mode row). -->

### 11.1 Where to find what

Hackathon mode is a project-scoped, opt-in **second process path**. When a project sets `PRAXION_HACKATHON_MODE=1`, the 5-tier Direct/Lightweight/Standard/Full/Spike selector is replaced by the **Hackathon Spine** — a fixed-order, variable-membership pipeline (`promethean → researcher → systems-architect → implementation-planner → (implementer ∥ test-engineer) → verifier`) the user enters at a natural-language-inferred entry point, moves around in freely, and exits. With the env var unset, every agent, hook, and rule behaves byte-identically to the pre-hackathon baseline.

The mode activates through **four channels**: the `PRAXION_HACKATHON_MODE=1` env var (runtime source of truth for hooks), the `## Hackathon Mode` CLAUDE.md block (instruction text every agent reads each session — the spine definition), the `praxion-rules.yaml` hackathon preset (suppresses three non-core rules), and the `praxion-hackathon` wrapper script (launch-time skill-surface trim). For the design rationale, see [`.ai-state/DESIGN.md` §3](../.ai-state/DESIGN.md#3-components) (Hackathon Mode row) and [`dec-189`](../.ai-state/decisions/189-hackathon-mode-activation-and-tier-integration.md).

![Hackathon Spine — user declares an entry point (ideate → promethean, research → researcher, design → systems-architect, plan & build → implementation-planner, fix / implement → implementer); everything upstream of the entry point is skipped; the spine runs left-to-right through the selected stage onward; implementer and test-engineer run in parallel; the verifier is the default-on tail (skippable only on explicit user request); free mid-task movement between any stages is user-driven at any time](diagrams/hackathon-spine/rendered/hackathon-spine.svg)

| Component | File | Role |
|-----------|------|------|
| Canonical block | `claude/canonical-blocks/hackathon-mode.md` | Source of truth for the `## Hackathon Mode` CLAUDE.md block; embedded into the two onboarding commands and sync-checked by `scripts/sync_canonical_blocks.py` |
| Spine definition channel | `commands/onboard-project.md` (Phase 5b), `commands/new-project.md` (`--hackathon`) | Phase 5b idempotently writes the six hackathon artifacts on opt-in; `/new-project --hackathon` auto-enables the mode end-to-end |
| Always-loaded pointer | `rules/swe/swe-agent-coordination-protocol.md` | ~25-token pointer sentence after the Tier Selector fast-path block — the single always-loaded exception to the independence guarantee |
| AaC template set | `claude/aac-templates/praxion-rules.hackathon-preset.yaml`, `claude/aac-templates/praxion-hackathon.sh.tmpl`, `claude/aac-templates/hackathon-directive.md.tmpl`, `claude/aac-templates/hackathon-settings.json.tmpl`, `claude/aac-templates/hackathon-mode.md.tmpl` | Install-time payloads Phase 5b copies into an opted-in project to produce the six artifacts |
| Praxion-dogfooding companions | `scripts/praxion-hackathon` (executable wrapper), `.claude/hackathon-directive.md`, `.claude/hackathon-settings.json` | The project-local copies Praxion itself uses when a developer works on Praxion in hackathon mode |
| ADR-reminder silencing | `hooks/remind_adr.py` | Early-exits when `PRAXION_HACKATHON_MODE=1`, suppressing the ADR advisory in hackathon mode |
| Exit-procedure consistency check | `hooks/inject_process_framing.py` | When the env var is off but the `## Hackathon Mode` block is still present, emits a consistency warning and a test-discipline-reactivated reminder |
| Graduation advisory | `agents/sentinel.md` (`HK01` check) | Advisory finding when a hackathon project exceeds the PoC-size threshold (>40 source files OR >150 commits); inert on non-hackathon projects |
| Behavioral test suite | `tests/test_hackathon_mode.py` | Exercises the hackathon path and the flag-OFF independence guarantee; verifies the canonical block passes `sync_canonical_blocks.py --check` |

**Last verified against code:** 2026-05-15 — every path above confirmed present on disk with `test -e`.

**Built:** all components above resolve to files on disk.
