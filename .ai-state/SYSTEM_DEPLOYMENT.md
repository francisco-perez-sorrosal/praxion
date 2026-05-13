# System Deployment

<!-- Living deployment architecture document. Maintained by pipeline agents via section ownership.
     Created by systems-architect, updated by implementer/cicd-engineer, validated by verifier/sentinel.
     See skills/deployment/references/deployment-documentation.md for the full methodology. -->

## 1. Overview

<!-- OWNER: systems-architect | LAST UPDATED: 2026-05-13 by systems-architect (doc-arch-sync reconciliation — rewrote pipeline-dashboard service rows: Designed→Built, Streamlit→Next.js, venv→Node home; replaced Streamlit-specific FMA risk rows; bumped Last-verified) | PRIOR: 2026-05-03 by systems-architect (created during ai-training-onramp; established Praxion's own deployment surface plus a new "compute backend (taught)" section) -->

| Attribute | Value |
|-----------|-------|
| **System** | Praxion |
| **Primary runtime** | Claude Code plugin (npm package `i-am@bit-agora`) plus secondary targets for Claude Desktop and Cursor; one bundled long-lived service — the pipeline dashboard (`dashboard_app/`, a Next.js App Router app) |
| **Deployment level** | Plugin distribution (npm + git clone) + per-project install scripts + lifecycle hooks + a user-scoped dashboard runtime under `~/.praxion-dashboard/` |
| **Last verified** | 2026-05-13 by systems-architect (doc-arch-sync reconciliation — pipeline-dashboard rows brought current with the Next.js runtime); prior: 2026-05-03 (initial creation as part of ai-training-onramp) |

Praxion is a meta-project distributed as a Claude Code plugin. There is no traditional web/backend deployment topology (no Docker Compose, no reverse proxy, no databases): Praxion ships as Markdown skills/agents/rules/commands plus two Python MCP servers (memory-mcp, task-chronograph-mcp) launched on-demand by the Claude Code host, and one optional bundled long-lived service — the **pipeline dashboard** (`dashboard_app/`, a Next.js App Router + TypeScript app), a read-only local web window over a project's `.ai-state/` / `.ai-work/` / selected project-root artifacts. This document captures (a) Praxion's own deployment surface and (b) the **compute backend story Praxion teaches** for the ML/AI training archetype that landed in v1 of the ai-training-onramp work — a structural concept this document anchors so future ML-archetype refinements have a home.

## 2. System Context

<!-- OWNER: systems-architect | LAST UPDATED: 2026-05-03 by systems-architect -->
<!-- L0 diagram: system boundary + external actors. -->

![Deployment System Context — developer, Claude Code host, Praxion plugin, managed project](diagrams/deployment-system-context/rendered/deployment-system-context.svg)

> **Detail views:** [Service Topology](#3-service-topology)

### External Dependencies

| Dependency | Type | Strong/Weak | Shared SLO? | Notes |
|---|---|---|---|---|
| Claude Code | External (host) | Strong | No (host runtime) | Plugin cannot run without it |
| Python 3.13+ | External (runtime) | Strong | No | MCP server runtime; hooks |
| Git 2.x+ | External (runtime) | Strong | No | Worktree management, merge drivers |
| `uv` | External (tooling) | Weak | No | MCP server launch; Python project management |
| Arize Phoenix | External (observability) | Weak | No | Optional OTLP endpoint for traces; pipeline degrades gracefully without it |
| `chub` (context-hub) | External (knowledge) | Weak | No | Curated API docs; MCP and CLI; fallback to web/training data when absent |

### Compute backend (taught — for ML/AI training archetype)

This subsection documents the **compute backend story Praxion teaches** projects in the ML/AI training archetype. Praxion itself does not deploy training jobs; the project does. Praxion ships the conventions and the abstraction.

| Tier | Backend | Serves operational modes | Praxion ships in v1 | Reference |
|---|---|---|---|---|
| Default — local | `subprocess.run` semantics | Modes A (co-located on owned GPU) and B (co-located on rented GPU) | Yes — ~0 LOC | `skills/neo-cloud-abstraction/references/local-backend.md` (designed) |
| Default — remote | SkyPilot 0.12.1 (PyPI) | Mode C (Praxion separated) — covers 20+ providers | Yes — one adapter | `skills/neo-cloud-abstraction/references/skypilot-backend.md` (designed) |
| Specialization | RunPod direct via `@runpod/mcp-server` 1.1.0 (npm) | Mode C committed to RunPod | Yes — v1 reference recipe | `skills/neo-cloud-abstraction/references/runpod-direct-adapter.md` (designed) |
| Specialization (v2) | Lambda direct (REST), Crusoe direct (REST), CoreWeave direct (K8s) | Mode C committed to those providers | No — deferred | (v2 references) |

The contract — `training_job_descriptor` schema and 8 lifecycle operations — is invariant across modes. See `dec-118` for the full rationale and `.ai-state/DESIGN.md` Components/Interfaces sections for the schema.

## 3. Service Topology

<!-- OWNER: systems-architect (skeleton), implementer (as-built) | LAST UPDATED: 2026-05-13 by systems-architect (doc-arch-sync — pipeline-dashboard row rewritten: Built, Next.js, Node home, port range unchanged; Streamlit description removed) | PRIOR: 2026-05-03 (initial skeleton) -->

Praxion has no servers in the traditional deployment sense. Two stdio MCP servers launch per Claude Code session; one of them additionally serves an HTTP daemon on `localhost:8765` for hook event ingestion. One bundled long-lived web service — the pipeline dashboard — runs per developer machine, one process per managed project on a deterministic per-project port.

![Deployment Service Topology — developer machine, Praxion plugin surface, MCP servers, Phoenix](diagrams/deployment-service-topology/rendered/deployment-service-topology.svg)

> The L1 topology diagram above shows the Claude Code extension surface (plugin assets + the two MCP servers + hooks). The pipeline dashboard is deliberately not drawn there — it is a separate long-lived service with no runtime coupling to Claude Code; its topology is the single-row table entry below. Regenerating the diagram to add a dashboard node is tracked as a low-priority follow-up (see the `## Diagram Regen Spec` in the doc-arch-sync `SYSTEMS_PLAN.md`).

| Service | Image/Build | Ports (host:container) | Health Check | Restart Policy |
|---|---|---|---|---|
| memory-mcp | local Python via `uv run` | none (stdio only) | n/a (per-session lifecycle) | n/a |
| task-chronograph-mcp | local Python via `uv run` | `8765:8765` (HTTP daemon) | HTTP `GET /health` (informational) | n/a (per-session lifecycle) |
| pipeline-dashboard | Next.js App Router (`dashboard_app/`, TypeScript) — `next start` from a per-user install at `~/.praxion-dashboard/app/`; `pnpm install --frozen-lockfile` + `next build` performed once by `praxion-dashboard install`; pnpm store at `~/.praxion-dashboard/store/` | `8501–9500` (per-project sha256-derived: `8501 + sha256(project_abs_path) % 1000`); override `PRAXION_DASHBOARD_PORT`; binds `127.0.0.1` only | HTTP `GET /` returns 200 when up | macOS launchd `KeepAlive=true` (v1); `praxion-dashboard restart [path]` for manual cycle |

Praxion has two long-lived service classes: (1) MCP processes (memory-mcp, task-chronograph-mcp) start when Claude Code spawns them and exit when the session ends; (2) the **pipeline-dashboard service** (Built — the active runtime is the Next.js app `dashboard_app/`; the original Streamlit prototype `streamlit_app/` was removed in commit `313a50e`) outlives Claude Code sessions, managed by `scripts/praxion-dashboard` ctl + macOS launchd. The dashboard reads `.ai-state/`, `.ai-work/<task-slug>/`, and selected project-root surfaces strictly read-only — its one HTTP surface (`GET /api/diagram?path=<rel>`) streams allowlisted `.svg` files per request through a path-allowlist gate; nothing in the dashboard writes to project state and it never invokes an LLM. Runtime dependencies live under `~/.praxion-dashboard/` (Node modules, build artifacts, pidfiles, logs), keyed by the per-project port — never inside the managed project tree. The target project is selected via the `PRAXION_PROJECT_ROOT` env var (the `praxion-dashboard` ctl sets it; `validateProjectRoot` requires only `.ai-state/` to exist). macOS-only daemon v1; Linux/Windows users set `PRAXION_PROJECT_ROOT` and run `~/.praxion-dashboard/app/node_modules/.bin/next start --hostname 127.0.0.1 --port <port>` manually (systemd v2). New runtime deps relative to the Streamlit prototype: Next.js 16, React 19, `recharts`, `sanitize-html`, `react-markdown` + remark/rehype plugins (full set in `dashboard_app/package.json`); pnpm 11 and Node ≥ 20.9 are the only host prerequisites. See dec-draft-bcaea27e (process model — bash ctl + macOS launchd), dec-draft-dd356bb0 (port allocation — sha256 per-project), dec-draft-78f800c9 (dependency isolation — dedicated user-scoped home), dec-draft-df080384 (cross-platform scope — macOS v1), plus the dashboard-redesign drafts (diagram-serving-and-svg-sanitization, charting-recharts, renderer-registry-and-diataxis-shells, validate-project-root-relaxation, design-token-layer).

## 4. Configuration

<!-- OWNER: implementer | LAST UPDATED: 2026-05-03 (skeleton — implementer fills in as-built configuration during pipeline) -->

### Environment Variables

| Variable | Required | Default | Description | Sensitive |
|---|---|---|---|---|
| `PRAXION_DISABLE_MEMORY_MCP` | No | unset | Skip memory persistence in this project | No |
| `PRAXION_DISABLE_CHRONOGRAPH_MCP` | No | unset | Skip span emission in this project | No |
| `PRAXION_INJECT_NATIVE_SUBAGENTS` | No | `0` | Inject Praxion-process preamble into Praxion-native subagents (default off) | No |
| `CHUB_TELEMETRY` | No | `0` | context-hub telemetry off by default | No |
| `CLAUDE_CODE_SUBAGENT_MODEL` | No | unset | Operator kill switch for subagent model routing | No |

### Compute backend env vars (taught)

| Variable | Required | Default | Description | Sensitive |
|---|---|---|---|---|
| `RUNPOD_API_KEY` | Yes (when using RunPod direct) | -- | RunPod API key for `@runpod/mcp-server` | Yes |
| SkyPilot config | Yes (when using SkyPilot) | -- | Provider-specific via `~/.aws/`, `~/.gcp/`, etc. (per SkyPilot conventions) | Yes |

### Secrets Management

Secrets are project-scoped, not Praxion-scoped. Praxion does not store credentials; it teaches projects to use `.env` patterns from the `deployment` skill's `references/secrets-management.md`. For ML training compute backends, secrets are passed through `subprocess.Popen` env (local), SkyPilot's per-cloud auth (default-remote), or the RunPod MCP server's `RUNPOD_API_KEY` (RunPod direct).

### Environment Differences

Praxion has no production/staging/dev split. It runs identically on every developer machine.

## 5. Deployment Process

<!-- OWNER: cicd-engineer | LAST UPDATED: 2026-05-03 (skeleton — cicd-engineer fills in as-deployed) -->

Praxion deployment is plugin distribution. Two paths:

1. **Marketplace install**: `claude plugin install i-am@bit-agora` (npm-backed)
2. **Clone + install script**: `git clone <repo> && ./install.sh code` (developer / contributor path)

Per-project onboarding via `/onboard-project` (existing project) or `/new-project` (greenfield) is post-install configuration, not deployment per se.

### CI/CD Integration

GitHub Actions for Praxion's own repo handle skill linting, hook tests, MCP server integration tests, version bumping (Commitizen), and changelog generation. Populated by cicd-engineer when relevant changes land.

## 6. Failure Analysis

<!-- OWNER: systems-architect | LAST UPDATED: 2026-05-13 by systems-architect (doc-arch-sync — replaced the five Streamlit-era pipeline-dashboard (Designed) risk rows with Next.js/Node equivalents; status now Built) | PRIOR: 2026-05-03 (skeleton + ML training risks) -->

### Failure Mode Analysis

| Component | Risk | Likelihood | Impact / Mitigation | Outage Level |
|---|---|---|---|---|
| memory-mcp | MCP server crash | Low | Memory persistence breaks for current session; Claude Code surfaces error; restart MCP server. Hook gates protect against partial writes. | Degraded |
| task-chronograph-mcp HTTP daemon | Port 8765 conflict | Low | Hooks cannot post events; spans silently lost. Daemon restart resolves. | Degraded (observability only) |
| Hook script failure | Pre-commit hook bug | Low | Commit blocked; user fixes hook input or bypasses with `--no-verify` (discouraged) | Local only |
| ML compute backend (taught) — local | Wall-clock budget exceeded; runaway training process | Medium | `wall_clock_seconds_max` enforced via `signal.alarm` or equivalent in `/run-experiment` local backend | Per-experiment |
| ML compute backend (taught) — SkyPilot | SkyPilot YAML schema drift between v0.12 and a future major | Medium | Pin SkyPilot to `~=0.12` in skill body; sentinel staleness check on the skill | Skill-content currency |
| ML compute backend (taught) — RunPod direct | `@runpod/mcp-server` upstream maintenance lapse | Low | Reference is reference-only; abstraction's contract is what matters; v2 specializations are alternatives | Reference rotation |
| pipeline-dashboard (Next.js) | `next start` process crash | Low | macOS launchd `KeepAlive=true` restarts the process; `~/.praxion-dashboard/<port>.log` captures the crash trace; `praxion-dashboard restart [path]` recovers if KeepAlive loops | Per-developer-machine |
| pipeline-dashboard (Next.js) | sha256 port collision across concurrent projects (~25% at ~24 projects) | Low | Override via `PRAXION_DASHBOARD_PORT`; widen `mod 1000 → mod 2000` if telemetry shows real collisions; `praxion-dashboard status [path]` reports the active port | Per-project (one project unreachable until override) |
| pipeline-dashboard (Next.js) | Next.js / React major-version drift between the pinned `dashboard_app/package.json` and a future upgrade (e.g., Next 16 → 17) breaks the build at `praxion-dashboard install` time | Medium | `pnpm-lock.yaml` pins the full dependency closure; `pnpm install --frozen-lockfile` fails loudly rather than silently resolving a newer tree; bump deliberately and re-run `next build` in CI before shipping; API/version drift detection via `external-api-docs` skill at upgrade time | Dashboard install fails until pins reconciled; existing installs unaffected |
| pipeline-dashboard (Next.js) | User-scoped Node home `~/.praxion-dashboard/` is stale relative to the plugin source (`dashboard_app/` changed but `praxion-dashboard install` not re-run) | Low | `praxion-dashboard start` rsyncs `dashboard_app/` into `~/.praxion-dashboard/app/` (excluding `node_modules`) on each start; `praxion-dashboard install` is the explicit full re-provision (re-runs `pnpm install` + `next build`); `praxion-dashboard uninstall --yes` resets the home | Per-developer-machine; stale UI until re-provisioned |
| pipeline-dashboard (Next.js) | `.ai-work/<task-slug>/` cleaned up while the Workshops surface is open | Medium | Workshops reads are mtime-keyed with a `FileNotFoundError → empty-state` fallback; the surface refreshes on the `PRAXION_DASHBOARD_POLL_SECONDS` interval (15 s default) and reports "Workshop ended" | Page-level UX only; service healthy |
| pipeline-dashboard (Next.js) | Linux/Windows user runs `praxion-dashboard install` | Medium | ctl detects the platform and prints the manual-launch recipe (`PRAXION_PROJECT_ROOT=... ~/.praxion-dashboard/app/node_modules/.bin/next start --hostname 127.0.0.1 --port <port>`); systemd support is v2; `commands/dashboard.md` documents the fallback | macOS-managed daemon unavailable on non-macOS; manual launch works |
| pipeline-dashboard (Next.js) | Untrusted SVG injected via a managed project's diagram files | Low | The one HTTP surface serves only `.svg` files via `<img src>` (script-inert in modern browsers, served unsanitized by design); any SVG inlined into the page (e.g. the diagram viewer) is passed through server-side `sanitize-html` first; the `/api/diagram` route additionally enforces a path allowlist and extension check | Page-level only; no host compromise |

### Dependency Classification

| Dependency | Type | Strong/Weak | Failure Impact |
|---|---|---|---|
| Claude Code | External (host) | Strong | Plugin does not run |
| Python 3.13+ | External (runtime) | Strong | MCP servers and hooks fail |
| Git 2.x+ | External (runtime) | Strong | Worktree, merge driver, ADR finalize all fail |
| Arize Phoenix | External (observability) | Weak | Spans not exported; pipeline continues |
| `chub` | External (knowledge) | Weak | API doc fetch falls back to web/training data |
| SkyPilot (taught) | External (taught backend) | Weak (project-side) | Project user installs and configures; Praxion teaches conventions |
| `@runpod/mcp-server` (taught) | External (taught backend) | Weak (project-side) | Same — project-side concern |

## 7. Monitoring & Observability

<!-- OWNER: systems-architect (skeleton); implementer fills in -->

### Health Checks

Praxion has no traditional health-check endpoints. The Chronograph MCP HTTP daemon serves `/health` for informational purposes. MCP server health is implicit in Claude Code's MCP lifecycle (failure surfaces in the host).

### Logging

| Service | Log Driver | Access |
|---|---|---|
| memory-mcp | stderr | Claude Code error log; per-session |
| task-chronograph-mcp | stderr | Claude Code error log; per-session |
| Hooks | stderr | Claude Code displays on hook block (exit 2) |

### Service Level Indicators (if defined)

Not applicable. Praxion has no user-facing SLOs; it is developer tooling running per-session.

## 8. Scaling

Not applicable. Praxion runs per-developer-session; scaling is a per-machine concern (Claude Code's responsibility).

For taught ML training compute, scaling guidance lives in `skills/deployment/references/gpu-compute-budgeting.md` (designed) and `skills/ml-training/SKILL.md` (designed) — covers GPU memory arithmetic, mixed precision, gradient accumulation tradeoffs, and the scale-up heuristics from autoresearch (5-minute experiment → full-scale decision).

## 9. Decisions

Deployment-relevant decisions are recorded as ADRs in [`.ai-state/decisions/`](decisions/). Quick cross-reference for ai-training-onramp:

| ADR | Decision | Impact on Deployment |
|---|---|---|
| [dec-118](decisions/118-ai-training-tiered-backend-strategy.md) | Tiered backend strategy for ML compute | Praxion teaches three backends; ships SkyPilot + local as defaults; RunPod direct as v1 reference specialization |
| [dec-116](decisions/116-ai-training-results-schema-owner.md) | `TRAINING_RESULTS.md` schema ownership | Skill-defined schema means deployment-doc fields above (compute backend env vars, FMA rows) reference the skill, not duplicated here |
| dec-draft-bcaea27e | Pipeline Dashboard process model — bash ctl + macOS launchd, not MCP-bound | Adds the first long-lived Praxion service; ctl mirrors phoenix-ctl |
| dec-draft-dd356bb0 | Pipeline Dashboard port allocation — sha256 per-project derivation | Per-project port 8501–9500 in the service topology table |
| dec-draft-df080384 | Pipeline Dashboard cross-platform scope — macOS-only v1 | macOS launchd v1; Linux/Windows manual `next start` fallback documented in the runbook |
| dec-draft-78f800c9 | Pipeline Dashboard dependency isolation — dedicated user-scoped home | `~/.praxion-dashboard/` (`app/` for the Next.js install, `store/` for the pnpm store, plus per-port pidfiles/logs) keeps the dashboard's Node toolchain off the managed project and the Praxion repo root. *(Originally specified as a Python venv at `~/.praxion-dashboard/venv/` when the dashboard was a Streamlit prototype; the runtime is now Next.js, so the isolation boundary is a Node home rather than a venv — the decision's intent, "dashboard deps live in a dedicated per-user home, not in any project," is unchanged.)* |

Pre-existing dec-NNN entries continue to live in `DECISIONS_INDEX.md`; this section names only the deployment-relevant ai-training-onramp ADRs (dec-115..120 cover the full set) and the pipeline-dashboard fragment ADRs (the original pipeline-dashboard set plus the dashboard-redesign drafts that supersede dec-125/dec-129/dec-130 — all finalize to stable `dec-NNN` at merge-to-main).

## 10. Runbook Quick Reference

<!-- OWNER: implementer | LAST UPDATED: 2026-05-03 (skeleton — populated as runbook procedures emerge) -->

### Common Operations

| Task | Command |
|---|---|
| Install plugin (clone path) | `./install.sh code` |
| Install plugin (marketplace) | `claude plugin install i-am@bit-agora` |
| Onboard existing project | `/onboard-project` |
| Scaffold greenfield project | `/new-project` |
| Run experiment (taught) | `/run-experiment` (designed; available after ai-training-onramp lands) |
| Check experiment (taught) | `/check-experiment` (designed) |

### Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| MCP server fails to start | `which uv`, Python version | Ensure `uv` and Python 3.13+ are installed |
| Hook event lost | `lsof -i :8765` | Restart Chronograph MCP daemon |
| ADR draft not promoting | post-merge hook fired? | `scripts/finalize_adrs.py --merged` manually |
| Tech-debt ledger conflict | merge driver registered? | `git config --get merge.tech_debt_ledger.driver` |
| ML compute budget exceeded (taught) | training wall-clock vs `gpu_hours_budget` | Review `WIP.md` budget; the ledger's signal is informational; `/run-experiment` enforces hard cap |
