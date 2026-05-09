---
diataxis: explanation
audience: architect
---

# Architecture

<!-- Design-target architecture document. Abstracts above concrete code to define the space of valid
     implementations. Component names may be abstract; file paths are illustrative; planned components
     are included with Status markers. For code-verified developer navigation, see docs/architecture.md.
     Created by systems-architect, updated by implementer, validated by verifier/sentinel.
     See skills/software-planning/references/architecture-documentation.md for the full methodology. -->

## 1. Overview

<!-- OWNER: systems-architect | LAST UPDATED: 2026-04-12 by systems-architect -->

| Attribute | Value |
|-----------|-------|
| **System** | Praxion |
| **Type** | AI development meta-framework (plugin + MCP servers + knowledge artifacts) |
| **Language / Framework** | Python 3.13+ (MCP servers), Markdown (skills/agents/rules/commands), Shell/Python (hooks, scripts) |
| **Architecture pattern** | Plugin-based knowledge ecosystem with progressive disclosure and agent pipeline orchestration |
| **Source stage** | Phase 5 creation, 2026-04-10 by systems-architect |
| **Last verified** | 2026-05-07 — pipeline-dashboard (Designed): new component Pipeline Dashboard, ten draft ADRs (`dec-121`..`dec-131`); see [ARCHITECTURE_CHANGELOG.md](ARCHITECTURE_CHANGELOG.md) for verification history |

Praxion is a meta-project that provides the operational infrastructure for AI-assisted software development. Rather than being an application itself, it is an ecosystem of reusable skills, specialized agents, declarative rules, slash commands, lifecycle hooks, and MCP servers that compose into a coherent development workflow. It ships as the `i-am` Claude Code plugin, with secondary targets for Claude Desktop and Cursor.

The architecture is organized around three core concerns: **knowledge delivery** (skills and rules that bring domain expertise into agent context windows), **agent orchestration** (a pipeline of specialized agents that collaborate through shared documents), and **persistent intelligence** (MCP servers that maintain memory and observability state across sessions). This document defines the design space — the set of valid implementations and their relationships — rather than documenting what currently exists on disk. For code-verified navigation, see [docs/architecture.md](../docs/architecture.md).

## 2. System Context

<!-- OWNER: systems-architect | LAST UPDATED: 2026-04-30 by implementer (migrated Mermaid block to LikeC4-sourced SVG — structurizr-d2-diagrams pipeline Step 6) -->
<!-- L0 diagram: system boundary + external actors/dependencies. -->

<img src="../docs/diagrams/architecture/rendered/context.svg" alt="Praxion System Context (L0)" />

*LikeC4 source: [`docs/diagrams/architecture/src/architecture.c4`](../docs/diagrams/architecture/src/architecture.c4). The pre-commit hook (`scripts/diagram-regen-hook.sh`) regenerates the SVG above when the source changes.*

> **Component detail:** [Components](#3-components)
> **Code-verified paths:** [docs/architecture.md](../docs/architecture.md)

## 3. Components

<!-- OWNER: systems-architect (skeleton), implementer (as-built) | LAST UPDATED: 2026-04-30 by implementer (migrated Mermaid block to LikeC4-sourced SVG — structurizr-d2-diagrams pipeline Step 6) -->
<!-- L1 diagram: major building blocks and their relationships.
     Status values: Designed (interface defined, not yet implemented), Built (code exists on disk),
     Planned (roadmap item, no interface yet), Deprecated (scheduled for removal). -->

<img src="../docs/diagrams/architecture/rendered/components.svg" alt="Praxion Components (L1)" />

*LikeC4 source: [`docs/diagrams/architecture/src/architecture.c4`](../docs/diagrams/architecture/src/architecture.c4). The pre-commit hook (`scripts/diagram-regen-hook.sh`) regenerates the SVG above when the source changes.*

| Component | Responsibility | Status | Key Files (illustrative) |
|-----------|---------------|--------|--------------------------|
| Skills | Domain expertise delivered via progressive disclosure (metadata, body, references). The skill catalog is enumerated by filesystem scan, not in this row. | Built | `skills/*/SKILL.md`, `skills/*/references/` |
| Agents | Autonomous subprocesses with distinct specialties for multi-step software engineering work | Built | `agents/*.md` |
| Rules | Declarative conventions auto-loaded by relevance into every session | Built | `rules/swe/`, `rules/writing/` |
| Commands | User-invoked slash commands for repeatable workflows | Built | `commands/*.md` |
| Hooks | Python/shell scripts triggered by Claude Code lifecycle events for enforcement and observability | Built | `hooks/*.py`, `hooks/*.sh`, `hooks/hooks.json` |
| Memory MCP | Persistent dual-layer memory: curated institutional knowledge (JSON) + zero-cost automatic observations (JSONL). `session_start()` auto-rotates observations.jsonl above 10 MiB (best-effort, never blocks) | Built | `memory-mcp/src/memory_mcp/` |
| Chronograph MCP | Agent pipeline observability via OpenTelemetry spans with HTTP event ingestion and OTLP export | Built | `task-chronograph-mcp/src/task_chronograph_mcp/` |
| `.ai-state/` | Persistent project intelligence: ADRs, specs, sentinel reports, architecture docs, memory store | Built | `.ai-state/decisions/`, `.ai-state/memory.json` |
| `.ai-work/` | Ephemeral pipeline documents scoped by task slug; gitignored, worktree-isolated | Built | `.ai-work/<task-slug>/` |
| Installers | Target-specific deployment scripts (Claude Code, Claude Desktop, Cursor) | Built | `install.sh`, `install_claude.sh`, `install_cursor.sh` |
| Scripts | Developer tooling: worktree management, merge drivers, daemon control, ADR index generation | Built | `scripts/` |
| Roadmap-cartographer | Project-level roadmap generator orchestrating **project-derived lens-set** parallel audit, synthesis, and user-gated ROADMAP.md emission for any project (deterministic / agentic / hybrid); SPIRIT is one exemplar lens set among DORA / SPACE / FAIR / CNCF Platform Maturity / Custom | Designed | `agents/roadmap-cartographer.md`, `skills/roadmap-synthesis/` (dec-029, dec-030, dec-035, dec-036) |
| Eval framework | Out-of-band quality measurement via `/eval` command and CI; tiered (behavioral + regression first, cost + decision-quality + LLM-judge as Tier 2 stubs); reads completed artifacts and Phoenix traces without mutating live pipeline state | Built | `eval/pyproject.toml`, `eval/src/praxion_evals/`, `commands/eval.md`, `.ai-state/evals/` (dec-040, dec-041) |
| Greenfield project onboarding | Top-level entry point that scaffolds a Claude-ready project then hands off to an interactive Claude session pre-loaded with `/new-cc-project`. Hybrid bash + slash-command orchestration (dec-055) with prompt-over-template discipline (dec-053): Praxion ships prose specifications and a discovery hook (`external-api-docs`), no code templates, no pinned SDK signatures. Default app is Python + `uv` + Claude Agent SDK + FastAPI; per-run `onboarding_for_mushi_busy_ppl.md` is generated against real on-disk paths | Built | `new_cc_project.sh` (repo root, 101 L, +x), `commands/new-cc-project.md` (259 L), `docs/project-onboarding.md` (123 L), `tests/new_cc_project_test.sh` (230 L, +x) (dec-053, dec-054, dec-055) |
| Concurrency & collaboration model | Unified three-mode story (solo-on-main / multi-session-solo / multi-user-team) over shared primitives: fragment ADR naming, unified `.claude/worktrees/`, finalize-at-merge protocol, two-layer squash-merge safety, opt-in auto-memory orphan cleanup. Git is the only shared synchronization substrate; author identity from `git config` for multi-user forward compatibility. See dec-056..dec-061. | Built | `.ai-state/decisions/drafts/`, `scripts/finalize_adrs.py`, `scripts/check_squash_safety.py`, `commands/clean-auto-memory.md`, `rules/swe/vcs/pr-conventions.md` |
| Tech-debt ledger | Living `.ai-state/TECH_DEBT_LEDGER.md` + `TECH_DEBT_RESOLVED.md` pair holding grounded debt findings — one logical namespace by `td-NNN` / `dedup_key`. Producers: verifier (per-change), sentinel (repo-wide), orchestrator (user-direction), architect-validator (per-PR drift). Consumers: five reader agents (permission-not-obligation per dec-069). Worktree concurrency reconciles via post-merge `scripts/finalize_tech_debt_ledger.py`. Schema (14 fields + `dedup_key`) and owner-role heuristic canonical in `skills/software-planning/references/tech-debt-ledger.md`. See dec-070..dec-072, dec-114. | Built | `.ai-state/TECH_DEBT_LEDGER.md`, `.ai-state/TECH_DEBT_RESOLVED.md`, `rules/swe/agent-intermediate-documents.md`, `scripts/finalize_tech_debt_ledger.py`, `agents/{verifier,sentinel,systems-architect,implementation-planner,implementer,test-engineer,doc-engineer}.md` |
| Project metrics command | `/project-metrics` slash command computing project complexity/health metrics (SLOC, CCN, cognitive, cyclic deps, churn, entropy, truck factor, ownership, hot-spots, coverage) on any Praxion-onboarded repo. Tier 0 universal (`git` + Python stdlib, optional `scc`) + Tier 1 Python collectors (`lizard`, `complexipy`, `pydeps`, `coverage.py`); TS/Go/Rust deferred to v2 via the same collector protocol. Per-run JSON+MD pair in `.ai-state/metrics_reports/` plus append-only `METRICS_LOG.md` with frozen aggregate-block column contract. Graceful degradation per-collector. See dec-062..dec-066. | Built | `commands/project-metrics.md`, `scripts/project_metrics/`, `docs/metrics/README.md` |
| Praxion-as-First-Class enforcement surfaces | Three-layer enforcement of the principle that Praxion's process is the default mode. L1: existing always-loaded rules. L2: `§Praxion Process` canonical block in onboarded `CLAUDE.md` (byte-identically mirrored across `commands/onboard-project.md` Phase 6 and `commands/new-project.md`). L3: `hooks/inject_subagent_context.py` (PreToolUse `Agent\|Task`; ~180-char preamble; host-native always, Praxion-native opt-in) + `hooks/inject_process_framing.py` (UserPromptSubmit; ~120-char `additionalContext` gated on `.ai-state/` + non-continuation + non-trivial). Always-loaded surface stays under 25k. See dec-075. | Built (2026-04-26) | `hooks/inject_subagent_context.py`, `hooks/inject_process_framing.py`, `hooks/hooks.json`, `commands/onboard-project.md`, `commands/new-project.md` |
| Install-path completeness mechanism | First-session auto-completion converges all install paths (clone / marketplace+complete-install / marketplace-only) on the same end state. `hooks/auto_complete_install.py` (SessionStart) detects missing global surfaces and runs completion non-interactively (git-config defaults) or with a 30-second timeout-accept confirm. Idempotent fast-skip after first success via marker file. `install_claude.sh::render_claude_md()` extracted to `scripts/render_claude_md.py`. `/praxion-complete-install` retained for explicit re-invocation (`--reconfigure`, recovery). See dec-074. | Built (2026-04-26) | `hooks/auto_complete_install.py`, `hooks/hooks.json`, `scripts/render_claude_md.py`, `install_claude.sh`, `commands/praxion-complete-install.md` |
| Project archetype catalog | Conceptual classification of the kinds of project Praxion can manage. Three archetypes after this onramp: **Traditional SWE** (existing — covered by the full skill catalog), **Agentic-AI apps** (existing — `agentic-sdks`, `agent-evals`, `mcp-crafting`, `communicating-agents`), and **ML/AI training** (NEW — pre-training v1; post-training v2; multimodal later). Composition: `karpathy/autoresearch` is the v1 proof target *because* it sits at the intersection of agentic-AI and ML training — managing it tests the *composition* of both archetypes simultaneously. The catalog is a vocabulary layer above the skill catalog, not a runtime component. See `dec-117`. | Built | `skills/ml-training/`, `skills/llm-training-eval/`, `skills/neo-cloud-abstraction/` (all new); existing skills compose unchanged for the SWE and agentic-AI archetypes |
| ML training subsystem (v1) | Skills, rules, and command extensions enabling Praxion to manage ML/AI pre-training projects. New skills: `ml-training`, `llm-training-eval` (owns the `TRAINING_RESULTS.md` schema), `experiment-tracking` (standalone — distinct from app observability per Q3). New rules under `rules/ml/` (eval-driven-verification, gpu-budget-conventions both always-loaded; experiment-tracking-conventions path-scoped). Rule extensions: scoped determinism waiver in `testing-conventions.md`; experiment-mode addendum in `git-conventions.md`. New commands: `/run-experiment`, `/check-experiment`. `/onboard-project` Phase 8c scaffolds ML projects. `program.md` is the project-local meta-prompt sibling of CLAUDE.md. See dec-115..dec-120. | Built | `skills/{ml-training,llm-training-eval,experiment-tracking}/`, `rules/ml/`, `commands/{run-experiment,check-experiment}.md`, `commands/onboard-project.md` (Phase 8c), `agents/verifier.md` (Phase 3a) |
| Neo-cloud abstraction | Praxion-native abstraction for ML training compute lifecycle. Defines mode-invariant `training_job_descriptor` schema and 8 lifecycle operations (create, start, status, log_stream, cancel, artifact_fetch, list, pricing_query). Tiered backend strategy: local default (modes A/B), SkyPilot default-remote (mode C; 20+ providers), opt-in direct adapters (RunPod v1 reference; Lambda/Crusoe/CoreWeave v2). Descriptor has no `mode:` field — backend inferred from project config. See dec-118. | Built | `skills/neo-cloud-abstraction/` |
| Pipeline Dashboard | Praxion-bundled Streamlit dashboard providing a per-project visual entry point. Six surfaces (Architecture / Workshops / ADRs / Sentinel / Roadmap / Metrics) read `.ai-state/` + `.ai-work/<task-slug>/` directly — no new persistence layer; read-only by design. Process model mirrors `phoenix-ctl` (standalone bash ctl + macOS launchd plist) + `chronograph-ctl` (per-project sha256-derived port 8501–9500); dedicated `~/.praxion-dashboard/venv/` isolation. Workshops surface uses `st.fragment(run_every=15s)` mtime-keyed live refresh. macOS daemon v1; Linux/Windows manual-launch documented; systemd v2. Soft-deprecates `metrics-viewer.html.tmpl`. See dec-121..dec-130. | Built | `streamlit_app/`, `scripts/praxion-dashboard`, `commands/dashboard.md` |

## 4. Interfaces

<!-- OWNER: systems-architect (design), implementer (as-built) | LAST UPDATED: 2026-04-12 by systems-architect -->
<!-- Key APIs, contracts, and integration points between components. -->

| Interface | Type | Provider | Consumer(s) | Contract |
|-----------|------|----------|-------------|----------|
| Plugin manifest | JSON | `plugin.json` | Claude Code plugin system | Skills/commands via directory globs, agents via explicit paths, MCP via command+args |
| Hook lifecycle | JSON (stdin/stdout) | Claude Code | `hooks/*.py` | Exit 0 = allow + process stdout JSON; exit 2 = block + stderr feedback. Sync PreToolUse Python hooks (`check_code_quality`, `remind_adr`, `remind_memory`, `promote_learnings`) are fronted by shell-gate wrappers (`commit_gate.sh`, `cleanup_gate.sh`) that skip Python startup on non-matching Bash payloads |
| Hook events HTTP | HTTP POST | `hooks/send_event.py` | Chronograph MCP | `localhost:8765/api/events` with event payload |
| Memory MCP | stdio (MCP) | `memory-mcp` | Claude Code, agents, hooks | 18 tools + 2 resources; schema v2.0 |
| Chronograph MCP | stdio (MCP) + HTTP | `task-chronograph-mcp` | Claude Code (stdio), hooks (HTTP) | 3 MCP tools; HTTP daemon on port 8765 |
| OTLP export | HTTP | Chronograph MCP | Arize Phoenix | OTLP HTTP to `localhost:6006/v1/traces` |
| Pipeline documents | Markdown files | Upstream agents | Downstream agents | Shared `.ai-work/<task-slug>/` directory; fragment files for parallel writes |
| Skill progressive disclosure | YAML frontmatter + Markdown | `SKILL.md` files | Claude Code skill loader | 3 tiers: metadata (startup), body (activation), references (on-demand) |
| Hook registration | JSON | `hooks/hooks.json` | Claude Code plugin system | Event type, command, timeout, sync/async per hook |
| `/roadmap` command | Slash command | `commands/roadmap.md` | User | Modes: fresh (default), diff (incremental re-run), `<focus-area>` (scoped audit); delegates to `roadmap-cartographer` (dec-029). Per `dec-092`, Praxion does not carry a living `ROADMAP.md` instance — the cartographer regenerates one on demand if invoked. |
| `/eval` command | Slash command | `commands/eval.md` | User | Tiers: `behavioral --task-slug <slug>`, `regression --baseline <path>`, `judge`, `list` (default); shells to `uv run --project eval praxion-evals <tier>` (dec-040) |
| Scripts install filter | Shell predicate | `install_claude.sh::relink_all` | User running install | Links only files matching `[ -f && -x ]` AND not matching `merge_driver_*` or `git-*-hook.sh`; `clean_stale_symlinks` sweeps `~/.local/bin/` for orphaned symlinks on upgrade (dec-042) |
| `new_cc_project.sh` CLI | Bash positional args | Repo-root script | User | `<project-name>` required; `[target-dir]` defaults `$PWD`; exit codes `0`/`2`/`3`/`4`/`5`/`6` for success/usage/no-claude/no-plugin/no-git/target-collision; `exec`s `claude --permission-mode acceptEdits "/new-cc-project"` (dec-054, dec-055) |
| `/new-cc-project` slash command | Slash command | `commands/new-cc-project.md` | User (post-handoff) | Single user question ("what to build?"); branches default-app vs custom-app; prose specs only — no code or pinned SDK signatures; mandates `external-api-docs` lookup before generating SDK or `uv` code (dec-053) |
| Canonical Praxion paragraph | Markdown sentinel-fenced block | `commands/new-cc-project.md` | Slash command flow + generated `onboarding_for_mushi_busy_ppl.md` | Copied verbatim by sentinel marker — never paraphrased — into each generated mushi doc (dec-053) |
| `training_job_descriptor` | YAML schema (designed) | `neo-cloud-abstraction` skill | `/run-experiment`, `/check-experiment`, three backends (local, SkyPilot, RunPod direct) | Mode-invariant schema with `resources`, `container`, `storage`, `budget`, `entry` sections; **no `mode:` or `backend:` field** (mode is inferred from project config). 8 lifecycle ops: create / start / status / log_stream / cancel / artifact_fetch / list / pricing_query. See dec-118. |
| `TRAINING_RESULTS.md` | YAML frontmatter + Markdown body | `/run-experiment` (writer); autoresearch experiment loop (writer when self-driven) | `verifier` Phase 3 eval-aware sub-branch; `/check-experiment` | Schema versioned (schema_version 1.0); fields: `run_tag`, `git_commit`, `descriptor`, `backend`, `metrics{val_bpb,val_loss,perplexity,custom}`, `resources_used{gpu_hours,wall_clock_seconds,actual_cost_usd}`, `status`, `acceptance{evaluated_against,outcome}`. Owned by `llm-training-eval` skill. See dec-116. |
| `program.md` | Markdown (project-local) | Human author | `systems-architect`, `implementation-planner`, `verifier` (read as input context for ML projects); `/onboard-project` (scaffold writer when missing) | Project root location, sibling of CLAUDE.md. Required content: Goal, Constraints, Hypothesis space, Simplicity criterion, Autonomy contract. Path: `<project-root>/program.md`. See dec-115. |

## 5. Data Flow

<!-- OWNER: systems-architect | LAST UPDATED: 2026-04-12 by systems-architect -->

### Agent Pipeline Execution (Standard/Full Tier)

![Agent Pipeline Execution — Standard/Full Tier sequence diagram](diagrams/agent-pipeline-execution/rendered/agent-pipeline-execution.svg)

### Memory and Observability Flow

![Memory and Observability Flow — hooks, memory MCP, chronograph MCP, Phoenix](diagrams/memory-observability-flow/rendered/memory-observability-flow.svg)

**Cross-layer correlation (dec-048).** Observations (`observations.jsonl`) and chronograph spans both carry the canonical OpenInference `session.id` attribute — the chronograph relay emits it on every span type including tool spans (formerly `praxion.session_id`). Observations additionally carry top-level `trace_id`, `span_id`, `traceparent`, and `parent_span_id` fields populated from W3C trace-context. Flow: the MCP tool request envelope surfaces `params._meta.traceparent`; the memory-mcp `remember()` / `recall()` handlers parse it via `correlation.parse_traceparent()` and forward the parsed IDs through the response `additionalContext`; the `capture_memory.py` hook reads `additionalContext` and writes those IDs into the observation row. `ObservationStore.query(trace_id=...)` supports exact-match filtering. Historical JSONL rows lacking these fields deserialize as `None` via `dict.get`, preserving backward compatibility.

### ADR Finalize Flow

![ADR Finalize Flow — draft creation, git merge, finalize_adrs.py promotion sequence](diagrams/adr-finalize-flow/rendered/adr-finalize-flow.svg)

The finalize flow activates only when `.ai-state/decisions/drafts/` has entries; the concurrency-model component (Section 3) describes the full primitive set. `scripts/finalize_adrs.py` is idempotent and guarded by an advisory `fcntl` lock.

### Tech-Debt Ledger Flow

![Tech-Debt Ledger Flow — producers (verifier, sentinel) write rows; five consumers filter by owner-role](diagrams/tech-debt-ledger-flow/rendered/tech-debt-ledger-flow.svg)

Two producers write rows, five consumers read and filter by `owner-role`. `/project-metrics` and `/project-coverage` are signal sources for the sentinel TD dimension — their `METRICS_REPORT_*.md` outputs feed sentinel's `TD01–TD04` checks but neither command writes to the ledger directly. Promethean (project-level ideation) and roadmap-cartographer (lens-set audit synthesis) are explicitly excluded — strategic horizons, not in-flight debt. Append-only writes plus the post-merge dedupe sequence (`scripts/finalize_tech_debt_ledger.py` — see `rules/swe/agent-intermediate-documents.md § TECH_DEBT_LEDGER.md`) keep concurrent worktree pipelines safe.

## 6. Dependencies

<!-- OWNER: systems-architect (initial), implementer (as-built) | LAST UPDATED: 2026-04-12 by systems-architect -->
<!-- External dependencies the system relies on. -->

| Dependency | Version | Purpose | Criticality |
|-----------|---------|---------|-------------|
| Claude Code | latest | Host runtime for plugin, hooks, agents, commands | Critical |
| Python | 3.13+ | MCP server runtime, hook execution | Critical |
| uv | latest | Python project management, MCP server launch | Critical |
| FastMCP | latest | MCP server framework (memory, chronograph) | Critical |
| OpenTelemetry SDK | latest | Span creation and OTLP export in chronograph | Non-critical (observability degrades) |
| Arize Phoenix | latest | Trace storage and visualization | Non-critical (external, optional) |
| Commitizen | latest | Version bumping and changelog generation | Non-critical (manual workflow) |
| ruff | latest | Python formatting and linting in hooks | Non-critical (code quality degrades) |
| Git | 2.x+ | Worktree management, merge drivers, version control | Critical |
| Cursor | latest | Secondary installation target | Non-critical (alternative IDE) |

## 7. Constraints

<!-- OWNER: systems-architect | LAST UPDATED: 2026-04-12 by systems-architect -->
<!-- Known limitations, performance boundaries, quality attributes, and compatibility requirements. -->

| Constraint | Type | Rationale |
|-----------|------|-----------|
| Always-loaded content under 25,000 tokens | Performance | Root CLAUDE.md + rules share a finite context window budget; exceeding it degrades all sessions |
| Skills target under 500 lines per SKILL.md | Performance | Progressive disclosure keeps activation cost manageable; overflow goes to `references/` |
| 10-12 nodes max per Mermaid diagram | Quality | Readability ceiling for architecture and flow diagrams |
| Hooks must have finite timeouts | Performance | Runaway hooks block the agent lifecycle; all hooks in hooks.json specify timeout |
| Async hooks cannot deliver agent feedback | Technical | Exit code and stderr from async hooks are silently dropped by Claude Code |
| Memory schema v2.0 required | Compatibility | MCP server crashes on v1.x files in non-praxion projects without migration |
| Python 3.13+ for MCP servers | Compatibility | uv venv with system Python 3.11 causes import failures in MCP subprojects |
| No `isolation: "worktree"` on Agent tool | Technical | Creates nested worktrees with opaque names when session is already in a worktree; use `EnterWorktree` instead |
| Single `hooks.json` authority | Configuration | All hooks registered in `hooks/hooks.json`; duplicating in `settings.json` causes double-firing |
| Agent depth 3+ requires user confirmation | Quality | Prevents runaway agent chains from compounding hallucination risk |
| Four-behavior agent behavioral contract applies to all write/plan/review agents | Behavioral | Surface Assumptions, Register Objection, Stay Surgical, Simplicity First — enforced via `rules/swe/agent-behavioral-contract.md` (always loaded) and six named failure-mode tags in verifier reports; sentinel checks BC01–BC04 audit integrity. Cross-cutting layer, not a component |
| Git is the only shared synchronization substrate for inter-session and inter-user coordination | Architectural | CRDTs, real-time broadcast, and shared MCP daemons explicitly rejected for artifact reconciliation; git's offline eventual-consistency is fit-for-purpose at file-granularity, minute-to-day convergence scale — see draft ADRs under `.ai-state/decisions/drafts/` (promoted to `dec-NNN` at merge-to-main) |
| ADRs created in a pipeline use fragment naming; stable NNN assigned at merge-to-main | Architectural | Prevents sequential-NNN cross-branch collisions and broken cross-references; author identity encoded from day one for multi-user forward-compatibility — draft filename schema `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`, finalized via `scripts/finalize_adrs.py` |
| `training_job_descriptor` is mode-invariant — no `mode:` or `backend:` field | Architectural | Praxion's three operational modes (A: co-located on owned GPU; B: co-located on rented GPU; C: separated) share one descriptor schema; backend is inferred from project config. If the descriptor needs to know its mode, the abstraction is leaking. The local backend's `pricing_query` returning `0.0` is the canonical "no-op" pattern proving the abstraction's correctness. See dec-118. |
| ML training-loop code is exempt from the `testing-conventions.md` determinism rule | Behavioral | Stochastic data shuffles, dropout, and CUDA non-determinism are inherent to training; the rule retains force for data-pipeline and model-architecture code. Path-scoped waiver in `rules/swe/testing-conventions.md`. |
| Compute budget declaration is mandatory for ML training projects | Architectural | `gpu_hours_budget` declared in `WIP.md` per step; budget-consumed is a step gate; open-ended training runs are prohibited. Enforced by `rules/ml/gpu-budget-conventions.md` (always-loaded). See dec-119. |

## 8. Decisions

<!-- OWNER: systems-architect | LAST UPDATED: 2026-04-28 by systems-architect (deduplicated per dec-021's "never duplicate ADR rationale" intent) -->

Architectural decisions are recorded as ADRs in [`.ai-state/decisions/`](decisions/). The canonical, auto-generated cross-reference is [`DECISIONS_INDEX.md`](decisions/DECISIONS_INDEX.md) (regenerated from frontmatter; never edited manually). In-flight pipeline ADRs live as fragments under [`decisions/drafts/`](decisions/drafts/) and are promoted to stable `dec-NNN` at merge-to-main by `scripts/finalize_adrs.py`.

Inline `dec-NNN` references in this document's component, interface, and constraint rows are the sole architectural cross-references — sentinel AC04 validates that they resolve.

## 9. Test Topology

<!-- OWNER: systems-architect (skeleton, ownership boundaries) | LAST UPDATED: 2026-04-28 by systems-architect -->
<!-- Architect-facing design-target view of the test-topology subsystem. The artifact at
     .ai-state/TEST_TOPOLOGY.md is created on first-write by whichever agent populates the first group;
     this section names ownership boundaries, sentinel/ledger integration, and ADR cross-references.
     For the developer-facing code-verified view, see docs/architecture.md §9. -->

### 9.1 Purpose

The test-topology subsystem makes test selection and execution a first-class concern of the agent pipeline. It declares **what** tests cover **which** subsystems, **how** they execute (parallel-safe, fixture scope, runtime envelope), and **which integration boundaries** they cross. Three execution tiers (`step` / `phase` / `pipeline`) and a sentinel-driven refactor trigger emerge from this declaration.

The subsystem is **language-agnostic at the trunk** and **per-language at the leaves** — see ADR `dec-091` for the registry primitive that makes this true.

### 9.2 Artifact Map

| Artifact | Path | Status | Owner | Purpose |
|---|---|---|---|---|
| Trunk reference | `skills/testing-strategy/references/test-topology.md` | Designed (this pipeline) | testing-strategy skill maintainer | Schema, identifier registries, document conventions, refactor-trigger semantics |
| Python leaf | `skills/testing-strategy/references/python-testing.md` (extension) | Designed (this pipeline) | testing-strategy skill maintainer | pytest-globs, pytest-markers registry rows; xdist scheduler; filelock recipe; pyproject snippet |
| Project topology | `.ai-state/TEST_TOPOLOGY.md` | **Planned** (no population in Praxion per ADR `dec-087`) | systems-architect (Subsystems table) + test-engineer (groups) + implementation-planner (per-pipeline integration_boundaries) | Per-project populated topology; first consumer project's M2 pipeline creates it |
| Sentinel TT family | `agents/sentinel.md` Check Catalog `### Test Topology (TT)` | Designed (this pipeline) | sentinel agent maintainer | TT01 subsystem cross-ref, TT02 glob expansion, TT03 coupling drift, TT04 envelope drift, TT05 marker-id consistency |
| Tech-debt class | `rules/swe/agent-intermediate-documents.md` `class` enum row | Designed (this pipeline) | rule maintainer | New `topology-drift` value; producer = sentinel; owner-role = implementation-planner |
| Document-schema additions | `IMPLEMENTATION_PLAN.md` `**Tests:**` field; `WIP.md` `Tests:`; `TEST_RESULTS.md` `Tier:` `Groups:` `Parallelism:` `Per-group results:` lines | Designed (this pipeline) | software-planning skill + agent-pipeline-details reference maintainer | Optional additive fields; absence preserves today's full-suite behavior |

### 9.3 Section Ownership (per `.ai-state/TEST_TOPOLOGY.md`)

When a project populates the topology, the file's sections are governed by section ownership:

| Section | Owner | Edit conditions |
|---|---|---|
| `## 2. Subsystems` (cross-reference table) | systems-architect | Updated when ARCHITECTURE.md §3 components change |
| `## 3. Groups` per-group YAML blocks | test-engineer | Updated when test code is added/refactored within an existing group |
| Per-group `integration_boundaries` field | implementation-planner | Updated during a pipeline when a step crosses a previously-undeclared bridge |
| `## 1. Overview` metadata | systems-architect | Updated alongside Subsystems table |

### 9.4 Cross-References

- **Components (§3)** — every `subsystems` value in `TEST_TOPOLOGY.md` resolves to a `Status: Built` component in this document's §3 (sentinel TT01 enforces).
- **Constraints (§7)** — the four-behavior contract row applies to test-topology agents; the "no leaf code in trunk artifacts" rule from `HANDOFF_CONSTRAINTS.md` is registered as an additional behavioral expectation in the trunk reference file.
- **Decisions (§8)** — eight test-topology ADRs (`dec-091`, `dec-088`, `dec-086`, `dec-084`, `dec-089`, `dec-085`, `dec-090`, `dec-087`) — each row appears in §8 above.

### 9.5 Trunk / Leaf Boundary

The architect's primary structural commitment, restated:

- **Trunk** owns the schema fields, the `tier` vocabulary, the `integration_boundaries` closure semantics (one-hop), the registries' existence and shape, the document conventions (`Tests:` field, `TEST_RESULTS.md` extension), the sentinel TT01–TT05 wording, the tech-debt-ledger `topology-drift` class.
- **Leaves** own the registered identifier rows (e.g., Python's `pytest-globs`, `pytest-markers`, `pytest-xdist-loadfile`), the marker registration recipe (Python: pyproject markers list), the parallel runner's concrete invocation, and any per-language helper recipes (Python: `filelock` for session fixtures).

A new language leaf is purely additive: a new reference file, new registry rows, no trunk modifications. The hypothetical Go module worked example in `.ai-work/test-partitioning/SYSTEMS_PLAN.md` is the proof.

### 9.6 Activation State

At this milestone (M1, post-this-pipeline), the test-topology subsystem is structurally complete but behaviorally inert in Praxion:

- All trunk and leaf artifacts exist (`Built`).
- Sentinel TT01–TT05 dimensions are defined (`Built`) but **conditionally inactive** — they self-deactivate when `.ai-state/TEST_TOPOLOGY.md` does not exist.
- `IMPLEMENTATION_PLAN.md` `**Tests:**` field is documented as optional in the schema (`Built`); current Praxion pipelines do not emit it.
- No populated `.ai-state/TEST_TOPOLOGY.md` exists in Praxion (`Planned`); the first consumer project that adopts the protocol creates it.

This dual state (Built schema + Planned activation) is the load-bearing record. It allows future agents to find the structural surface without confusing the "schema exists" signal with a "Praxion uses this protocol" signal.
