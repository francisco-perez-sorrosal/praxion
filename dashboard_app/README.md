# Praxion Pipeline Dashboard

> [!NOTE]
> The active dashboard runtime is `dashboard_app/` (Next.js App Router +
> TypeScript), served through `scripts/praxion-dashboard`. It replaced an
> earlier Streamlit prototype (`streamlit_app/`, removed in commit `313a50e`).

The active per-project dashboard runtime — turns a Praxion-onboarded
project's `.ai-state/`, `.ai-work/<slug>/`, and selected project-root
surfaces (`docs/`, `ROADMAP.md`) into a visual, educational, read-only
entry point covering architecture, in-flight workshops, ADRs, sentinel
health, roadmap, metrics, and documentation.

**Read-only.** The dashboard never writes to the target project, calls no
external APIs, and makes no LLM calls.

---

## Install

```bash
# One-time install per user (syncs source, installs deps, builds)
scripts/praxion-dashboard install
```

Requirements: Node ≥ 20.9, pnpm; macOS (daemon v1; Linux/Windows
manual-launch supported via `~/.praxion-dashboard/app/node_modules/.bin/next start`).

The install command creates the user-scoped Node home under
`~/.praxion-dashboard/` and produces a production build there. Run it once;
subsequent `start` calls use the built output.

## Run

```bash
# Via lifecycle ctl (recommended)
scripts/praxion-dashboard start /path/to/project
```

For dashboard development only (when changing UI or server layer):

```bash
cd dashboard_app
PRAXION_PROJECT_ROOT=/path/to/project pnpm dev
```

Keep `scripts/praxion-dashboard` as the stable launch contract for
all non-development use.

The port is derived deterministically from the absolute project path
(sha256-based, range 8501–9500), so the URL is stable across restarts.
The server binds to `127.0.0.1`. On macOS, `start` opens the URL in
the default browser after launch.

## Lifecycle commands

```
praxion-dashboard install    # sync source, install deps, build; create ~/.praxion-dashboard/
praxion-dashboard start      # launch the dashboard server for a project; opens browser on macOS
praxion-dashboard stop       # terminate the running process
praxion-dashboard restart    # stop + start
praxion-dashboard status     # show running/stopped + URL
praxion-dashboard uninstall  # remove home directory and all state
```

All commands accept an optional `[project-path]` argument (default: cwd).

## Surfaces

| Surface | Source artifacts | Notes |
|---------|-----------------|-------|
| Architecture | `.ai-state/DESIGN.md` + `docs/architecture.md` + rendered SVGs from `docs/diagrams/**/rendered/` and `.ai-state/diagrams/**/rendered/` | Interactive pan/zoom diagram viewer; AaC fence regions get badges; diagram refs served via `/api/diagram` route |
| Workshops | `.ai-work/<slug>/WIP.md` + `PROGRESS.md` | Step DAG; 15 s live refresh (this surface only) |
| ADRs | `.ai-state/decisions/` (finalized + drafts) + `DECISIONS_INDEX.md` | Interactive relationship graph from `supersedes`/`re_affirms` frontmatter; status/category/tag filters; full metadata chips |
| Sentinel | `.ai-state/sentinel_reports/` + `SENTINEL_LOG.md` | Health-grade sparkline from log; latest report split into Critical/Important/Suggested collapsibles |
| Roadmap | `ROADMAP.md` | — |
| Metrics | `.ai-state/metrics_reports/` | Recharts trend charts from `METRICS_LOG.md`/per-run JSON; hotspot table; collectors summary |
| Documentation | `.ai-state/doc_manifest.yaml` | Dispatched through the Diátaxis-typed renderer registry |

Every surface degrades gracefully to an informative empty/error state when
its source artifact is absent — a freshly-onboarded project with only
`.ai-state/` renders every page.

## Key constraints

- **Single install, per-project usage**: `PRAXION_PROJECT_ROOT` selects the
  target project. The dashboard never uses `cwd` as the project root.
- **Read-only**: filesystem access is purely read; no writes to the target project.
- **Auto-refresh on Workshops only**: default 15 s interval; override via
  `PRAXION_DASHBOARD_POLL_SECONDS`. All other pages require a manual browser refresh.
- **Server-only filesystem access**: Node `fs` stays in `src/server/` modules
  and route handlers. Client components never import server readers.
- **Diagram security**: the `/api/diagram` route streams only allowlisted `.svg`
  files; inline-injected SVGs are sanitized server-side via `sanitize-html`.

## Development

```bash
# Run tests (server view-models, parsers, helpers, pan/zoom math)
cd dashboard_app && ./node_modules/.bin/vitest run

# Type-check
cd dashboard_app && ./node_modules/.bin/tsc --noEmit

# Production build (verifies the full build pipeline)
cd dashboard_app && ./node_modules/.bin/next build

# Dev server (requires PRAXION_PROJECT_ROOT)
cd dashboard_app && pnpm dev
```

React component-render tests are deferred — see `.ai-state/TECH_DEBT_LEDGER.md`.

## Package layout

```
dashboard_app/
  src/
    app/                  # Next.js App Router pages
      api/diagram/        # /api/diagram route — streams allowlisted SVGs
      architecture/       # Architecture page
      adrs/               # ADRs page
      workshops/          # Workshops page (live refresh)
      sentinel/           # Sentinel page
      roadmap/            # Roadmap page
      metrics/            # Metrics page
      documentation/      # Documentation page
      error.tsx           # App-level error boundary
    components/
      viz/                # Data-viz: diagram-viewer, sparkline, trend-chart, adr-graph, pan/zoom
      shells/             # Diátaxis shells: default, reference, explanation (+ index)
      chrome/             # Reusable chrome: ArtifactCard, EmptyState, Tabs, Chip, ErrorState
      registry.ts         # Renderer registry — maps diataxis/content-type → shell component
    server/
      view-models/        # Per-surface server data functions (architecture, adrs, workshops, …)
      artifacts/          # Project-root resolution, path allowlist, content readers
      parsers/            # Pure parsers: markdown tables, workshops, content
      diagrams/           # SVG rewriting (rewriteRelativeImageRefs) and sanitization
      aac/                # AaC fence parsing and badge injection
      sentinel/           # Sentinel log and report parsing
  tests/server/           # Server-side unit tests
```

## Links

- Coordination protocol: `rules/swe/swe-agent-coordination-protocol.md`
- ADR conventions: `rules/swe/adr-conventions.md`
- Launcher contract (entrypoint, env vars, port range, bind, runtime home): `.ai-state/decisions/165-praxion-dashboard-launcher-contract.md`
- Dashboard runtime conventions (filesystem-as-source-of-truth, server-only fs access, frontmatter stripping, narrow live refresh, empty-state degradation): `rules/writing/html-output-conventions.md`
- Diagram conventions: `rules/writing/diagram-conventions.md`
- Architecture-as-Code fence convention: `rules/writing/aac-dac-conventions.md`
