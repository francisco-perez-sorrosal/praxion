---
id: dec-127
title: Pipeline Dashboard port allocation — sha256 per-project derivation
status: accepted
category: architectural
date: 2026-05-07
summary: Per-project port derived from sha256(abs_path) % 1000 + 8501 to enable concurrent multi-project use; mirrors chronograph-ctl pattern.
tags: [dashboard, port, multi-project, chronograph, sha256]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - scripts/praxion-dashboard
affected_reqs: [REQ-01]
---

## Context

A user with multiple Praxion-onboarded projects open simultaneously must be able to view each project's dashboard concurrently. A fixed port (e.g., 8501) blocks this — the second project's dashboard fails to bind. Streamlit's auto-increment behavior (8501 → 8502 → ...) works but breaks predictability: the URL is not stable across sessions, the user cannot bookmark a project's dashboard, and `praxion-dashboard status` cannot tell which port belongs to which project.

The repo already has a working precedent: `scripts/chronograph-ctl::_derive_port` derives a per-project port from `sha256(abs_path) % 1000 + 8765`. This pattern is proven and the human cost is zero — the user never sees the port; the URL is opened automatically.

## Decision

The dashboard derives its port from the project's absolute path:

```
PORT = 8501 + (int.from_bytes(sha256(abs_path).digest()[:2], 'big') % 1000)
```

Range: `8501–9500`. Deterministic per project. Override available via env var `PRAXION_DASHBOARD_PORT`. The ctl script's `status` subcommand prints the derived port and PID for the project the script was invoked from.

## Considered Options

### Option A — Fixed port (8501) with auto-increment fallback

**Pros**: Simplest; matches Streamlit default. **Cons**: Breaks multi-project; URL is unstable; `status` cannot identify project ownership.

### Option B — User-configurable in `.streamlit/config.toml`

**Pros**: Flexible. **Cons**: User must configure; conflicts when two projects pick the same value; defeats the "one command, just works" goal.

### Option C — Per-project sha256 derivation (chosen)

**Pros**: Deterministic; identical pattern to chronograph already in production; multi-project works automatically; URL stable across sessions; the user gets a different port per project without ever picking one.

**Cons**: Birthday-bound collision risk: at ~24 concurrent projects, ~25% chance of a collision in a 1000-port range. For a single developer this is irrelevant; for very wide users it is mitigated by the env-var override.

### Option D — UNIX socket per project

**Pros**: No port at all; perfectly scoped. **Cons**: Streamlit does not natively support UNIX sockets; would require a reverse proxy. Disproportionate complexity for a v1.

## Consequences

**Positive**: Multi-project concurrent use works on day one. Pattern reuse from chronograph reduces cognitive load — anyone who has read the chronograph daemon understands the dashboard daemon. URL stability lets users bookmark per-project dashboards.

**Negative**: Port range 8501–9500 is wider than the standard "expect dashboard at 8501" convention; users with firewall rules may need to add a range. Birthday collisions in extreme multi-project scenarios are theoretically possible.

**Risks accepted**: 25%-at-24-projects collision rate for the rare power user; mitigated by `PRAXION_DASHBOARD_PORT` override and a future expansion of the range to mod 2000 if usage data shows real collisions.
