# Praxion Pipeline Dashboard

> [!IMPORTANT]
> `streamlit_app/` remains as a temporary migration reference. The active
> dashboard runtime is `dashboard_app/` (Next.js App Router + TypeScript),
> served through `scripts/praxion-dashboard`.

A multi-page dashboard control room for Praxion-onboarded projects. It turns
each project's `.ai-state/` and `.ai-work/` filesystem into a visual,
educational entry point covering architecture, in-flight workshops, ADRs,
sentinel health, roadmap, metrics, and documentation.

**Read-only.** The dashboard never writes to `.ai-state/` or `.ai-work/`,
calls no external APIs, and makes no LLM calls.

---

## Install

```bash
# One-time install per user (creates ~/.praxion-dashboard/venv/)
scripts/praxion-dashboard install
```

Requirements: Python 3.11+, macOS (v1; Linux manual-launch supported).
Requirements: Python 3.11+ for the lifecycle ctl, macOS (v1; Linux manual-launch supported), and the user-scoped Node home under `~/.praxion-dashboard/` created by `scripts/praxion-dashboard install`.

## Run

```bash
# Via lifecycle ctl (recommended)
scripts/praxion-dashboard start /path/to/project
```

Work on `dashboard_app/` directly when changing the UI or server layer, but
keep `scripts/praxion-dashboard` as the stable launch contract.

The port is derived deterministically from the project root path
(sha256-based, range 8501–9500), so the URL is stable across restarts.

## Lifecycle commands

```
praxion-dashboard install    # create venv, install deps, register launchd plist
praxion-dashboard start      # launch the dashboard server and open browser
praxion-dashboard stop       # terminate the running process
praxion-dashboard restart    # stop + start
praxion-dashboard status     # show running/stopped + URL
praxion-dashboard uninstall  # remove plist and venv
```

## Pages

| Page           | Source artifacts                                  | REQ   |
|----------------|---------------------------------------------------|-------|
| Architecture   | `.ai-state/DESIGN.md` + LikeC4 SVG         | REQ-03 |
| Workshops      | `.ai-work/<slug>/WIP.md` + `PROGRESS.md`          | REQ-04, REQ-05 |
| ADRs           | `.ai-state/decisions/` (finalized + drafts)       | REQ-06 |
| Sentinel       | `.ai-state/sentinel_reports/`                     | REQ-07 |
| Roadmap        | `ROADMAP.md`                                      | REQ-08 |
| Metrics        | `.ai-state/metrics_reports/`                      | REQ-09 |
| Documentation  | `docs/architecture.md`, `docs/*.md`               | REQ-10 |

All pages degrade gracefully to an empty-state widget when their source
artifact is absent.

## Key constraints

- **Single install, per-project usage**: set `PRAXION_PROJECT_ROOT` to select
  the project; the app never uses `os.getcwd()` as the root.
- **No data writing**: purely read-only filesystem access.
- **Auto-refresh on Workshops only**: uses the dashboard server's refresh
  loop with a default 15 s interval, override via
  `PRAXION_DASHBOARD_POLL_SECONDS`. Other pages require a manual browser
  refresh.
- **No Mermaid in v1**: deferred to v2 per ADR dec-draft-d57dc712.

## Development

```bash
# Run tests
python -m pytest streamlit_app/tests/ -v

# Verify data layer isolation (no rendering primitives in discovery/parsers)
grep -r "^import streamlit\|^from streamlit" streamlit_app/data/
# Expected: only cache.py appears

# Shell lifecycle tests
bash streamlit_app/tests/test_ctl.sh
```

## Package layout

```
streamlit_app/  — migration reference only; retained until retirement
```

## Links

- Coordination protocol: `rules/swe/swe-agent-coordination-protocol.md`
- ADR conventions: `rules/swe/adr-conventions.md`
- Dashboard conventions: `rules/swe/dashboard-conventions.md`
- Architecture as code: `skills/architecture-as-code/SKILL.md`
