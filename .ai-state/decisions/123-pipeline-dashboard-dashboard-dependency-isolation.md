---
id: dec-123
title: Pipeline Dashboard dependency isolation — dedicated ~/.praxion-dashboard/venv/
status: accepted
category: architectural
date: 2026-05-07
summary: Dashboard installs into its own dedicated venv at ~/.praxion-dashboard/venv/, mirroring phoenix-ctl, so that Streamlit and visualization deps never interfere with user project deps.
tags: [dashboard, dependencies, venv, isolation, phoenix-ctl]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - scripts/praxion-dashboard
  - dashboard_app/package.json
affected_reqs: [REQ-01]
---

## Context

The dashboard introduces a non-trivial dependency tree:

- `streamlit` (~120 MB with transitive deps: tornado, protobuf, altair, pandas, numpy, plotly, pyarrow)
- `pyvis` (~2 MB, optional but useful for fallback DAGs)
- `pyyaml` (already transitive)

This is the largest single dependency footprint Praxion has shipped. Three places it could live:

1. **Praxion's repo-root venv** (`pyproject.toml [project.dependencies]` or a `[project.optional-dependencies]` group). Pulls Streamlit into every clone of Praxion regardless of dashboard use.
2. **The user project's venv**. Conflicts with user's own Streamlit (different version), `numpy` (different ABI), `plotly` (chart-style overrides). High risk of breakage. Praxion currently never installs into the user's venv for any purpose.
3. **A dedicated dashboard venv** (`~/.praxion-dashboard/venv/`). Phoenix-ctl precedent: `~/.phoenix/venv/` houses `arize-phoenix` independently of every other Python environment on the machine.

## Decision

The dashboard installs into a **dedicated `~/.praxion-dashboard/venv/`** managed by the ctl script's `install` subcommand. The user project's Python environment is never touched. Praxion's repo-root `pyproject.toml` is not modified (no Streamlit dep there). The plugin install never installs Streamlit; that happens lazily on first `praxion-dashboard install` (which `/dashboard` invokes implicitly when the plist is missing).

`streamlit_app/requirements.txt` (alongside `streamlit_app/`) pins:

```
streamlit>=1.55,<1.60
plotly>=5.0
pyvis>=0.3
pyyaml>=6.0
```

The ctl creates the venv, `pip install -q -r streamlit_app/requirements.txt` into it, and writes the path into the launchd plist's `ProgramArguments`.

## Considered Options

### Option A — Praxion repo-root venv (`[project.dependencies]`)

**Pros**: One venv to manage; standard. **Cons**: Adds 120 MB to every Praxion clone; users who never run the dashboard pay the cost; Streamlit's release cadence forces Praxion's release cadence; pollutes `pyproject.toml` with UI deps that have nothing to do with skills/agents/rules.

### Option B — User project's venv

**Pros**: One fewer thing to install. **Cons**: Real risk of dependency conflicts (user's `numpy`, `pandas`, their own Streamlit); breaks the strict "Praxion never writes to user project deps" invariant; impossible to debug when things go wrong because two Streamlits get mixed.

### Option C — Dedicated `~/.praxion-dashboard/venv/` (chosen)

**Pros**: Isolation from user deps; isolation from Praxion repo deps; mirrors phoenix-ctl precedent (proven pattern); install is lazy (only users who want the dashboard pay the install cost); easy to uninstall (`rm -rf ~/.praxion-dashboard`); easy to upgrade (`praxion-dashboard install` with new requirements).

**Cons**: Disk usage if the user has both Phoenix and the dashboard installed (~250 MB total in `~/.praxion-dashboard` + `~/.phoenix`). One more home directory entry.

### Option D — `pipx`-style isolated runner

**Pros**: Standard tool. **Cons**: Adds a `pipx` install prerequisite; Praxion does not currently require `pipx`; the ctl + venv pattern is in-house and proven.

## Consequences

**Positive**: User project deps are guaranteed untouched (a hard invariant the rest of Praxion already maintains). Phoenix-ctl precedent reused — anyone who has installed Phoenix understands the pattern. Lazy install means Praxion clone size is unaffected. Versions are pinned in `streamlit_app/requirements.txt` independent of Praxion's release cycle.

**Negative**: Disk usage grows by ~250 MB on machines with both Phoenix and the dashboard. Acceptable for developer machines. Two venvs to update (Phoenix's `pip install -U arize-phoenix`, dashboard's `pip install -U streamlit`); idempotent ctl `install` covers this for the dashboard.

**Risks accepted**: First-time `praxion-dashboard install` takes ~30 seconds (pip download + install). Mitigation: `/dashboard` slash command prints "Installing dashboard, this is a one-time step ~30s" so the wait is contextualized.
