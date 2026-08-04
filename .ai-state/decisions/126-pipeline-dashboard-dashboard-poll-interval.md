---
id: dec-126
title: Pipeline Dashboard auto-refresh interval — 15s default, env-overridable
status: accepted
category: implementation
date: 2026-05-07
summary: Hardcoded 15-second default auto-refresh on Workshops page, override via PRAXION_DASHBOARD_POLL_SECONDS env var; per-page configurability deferred to v2.
tags: [dashboard, polling, fragment, refresh, configurability]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - dashboard_app/src/lib/config.ts
affected_reqs: [REQ-05]
---

## Context

`st.fragment(run_every="15s")` is the modern, first-party auto-refresh primitive. Only the Workshops page (in-flight pipelines) needs this — Architecture, ADRs, and Roadmap are static between user actions; Sentinel and Metrics update only on `/sentinel` or `/project-metrics` invocations (minutes apart).

The 15-second figure is from the research finding's "guess for in-flight pipelines." It is reasonable for the use case — pipeline steps typically take 30+ seconds, so 15 s is one-half-step latency at worst. But "reasonable" is not "right" — different users may want tighter or looser polling.

Configurability has costs:
- `.streamlit/config.toml` is the canonical Streamlit config but it lives in the project root, not the dashboard's home — config drift across projects is a real risk.
- A separate `~/.praxion-dashboard/config.toml` adds a new config surface to design.
- Hardcoded with env override gives flexibility for the rare power user without fixing a project-coupled config.

## Decision

**Hardcode 15-second default; allow override via env var `PRAXION_DASHBOARD_POLL_SECONDS`** (positive integer, 1–300). The `praxion-dashboard start` ctl reads the env var and propagates it through to `streamlit_app/config.py`. The Workshops fragment uses:

```python
import os
POLL = int(os.environ.get("PRAXION_DASHBOARD_POLL_SECONDS", "15"))

@st.fragment(run_every=f"{POLL}s")
def live_pipeline_status(): ...
```

Per-page configurability and `.streamlit/config.toml` integration deferred to v2.

## Considered Options

### Option A — Hardcoded 15s, no override

**Pros**: Simplest. **Cons**: Power users with longer pipelines (LLM training, eval) want 60 s+ to reduce flicker; users debugging a stuck pipeline want 5 s.

### Option B — Hardcoded 15s, env-var override (chosen)

**Pros**: Default works for 95% of use; env var handles the long-tail; no new config surface; aligned with `PHOENIX_PORT` precedent in phoenix-ctl.

**Cons**: Power users must set the env var in their shell or in the launchd plist — not as discoverable as a config file. Acceptable for v1.

### Option C — `.streamlit/config.toml` per project

**Pros**: Streamlit's native config mechanism. **Cons**: Couples dashboard config to project repo; users would commit it (or gitignore it ad-hoc); collisions with user's own Streamlit config; adds discovery complexity.

### Option D — Adaptive polling (back off when no changes detected)

**Pros**: Zero-config; minimizes load. **Cons**: Streamlit fragments do not support dynamic `run_every`; would require custom session-state machinery; over-engineered for v1.

## Consequences

**Positive**: One line in `config.py`; one env var to document; covers the common case; opens the door to v2 config-file work without reshaping the API. The `st.fragment` semantic is preserved exactly.

**Negative**: Power users must remember the env-var name. Mitigation: `praxion-dashboard status` prints the active poll interval. The dashboard's sidebar shows "Refresh: 15s (PRAXION_DASHBOARD_POLL_SECONDS)" so the override is discoverable from the UI.

**Risks accepted**: A user with a 60-step pipeline at 5-second/step churn might want 1-s polling; cap at 1 s prevents file-system thrashing. Lower bound enforced.
