---
id: dec-003
title: "Dedicated Phoenix venv separate from chronograph"
status: accepted
category: architectural
date: "2026-03-31"
summary: "Phoenix gets its own venv at ~/.phoenix/venv/ to isolate heavy dependencies from chronograph"
tags: [observability, phoenix, dependencies, isolation]
made_by: agent
agent_type: systems-architect
affected_files: ["scripts/phoenix-ctl", "install.sh"]
affected_reqs: ["REQ-09"]
---

## Context

Phoenix has heavy dependencies (numpy, pandas, sqlalchemy) that could conflict with chronograph's lighter dependency set. Both are Python applications that need to coexist on the same machine.

## Decision

Dedicated Phoenix venv at `~/.phoenix/venv/` separate from chronograph's environment. This isolates the two dependency trees completely.

## Considered Options

### Option 1: Shared chronograph venv

Install Phoenix into the same venv as chronograph.

- (+) Simpler installation (one venv)
- (-) Dependency conflict risk between Phoenix's heavy deps and chronograph's
- (-) Upgrade cascades: updating Phoenix could break chronograph

### Option 2: pipx installation

Use pipx to manage Phoenix as an isolated application.

- (+) Automatic isolation
- (-) Less control over the Python version and venv location
- (-) pipx may not be available on all systems

### Option 3: Dedicated venv (selected)

Separate venv at a well-known path with explicit management scripts.

- (+) Complete dependency isolation
- (+) Full control over installation and upgrade lifecycle
- (+) `phoenix-ctl` script manages the venv explicitly

## Consequences

### Positive

- No dependency conflicts between Phoenix and chronograph
- Independent upgrade cycles for each tool

### Negative

- Two venvs to manage instead of one
- Slightly more complex installation procedure
