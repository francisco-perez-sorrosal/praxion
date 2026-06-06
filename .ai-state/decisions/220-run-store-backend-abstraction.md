---
id: dec-220
title: Pluggable run-store backend abstraction (storage analog of neo-cloud-abstraction)
status: accepted
category: architectural
date: 2026-06-05
summary: A backend-invariant run_store_descriptor selecting local-home / local-custom / s3 / tracker; store_uri is the only field that varies downstream.
tags: [storage, run-store, abstraction, backend, neo-cloud, eval, agentic-eval, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/agent-evals/references/run-ledger-schema.md
  - .ai-state/project_profile.yaml
related: [dec-221, dec-217, dec-219]
---

## Context

The two-tier storage model (`dec-221`) defaults the operational run store to
`$HOME/.<project-name>/` but must also serve projects that want a custom local path, remote S3,
or an external tracker (MLflow / W&B). Praxion already solved the *dispatch* version of this
problem with `neo-cloud-abstraction`: one `training_job_descriptor` schema, invariant across
backends, where only the backend implementation changes. The run store needs the **storage
analog** of that pattern so that switching where runs live changes no schema field and no
consumer code path.

## Decision

Define a **backend-invariant `run_store_descriptor`** with a backend set of four:

| Backend | Resolved `store_uri` | Use |
|---|---|---|
| `local-home` (default) | `$HOME/.<project-name>/runs/<run_id>/` | owned disk; zero-config prototyping |
| `local-custom` | `<run_store_root>/runs/<run_id>/` | custom local mount |
| `s3` | `s3://<bucket>/<prefix>/runs/<run_id>/` | remote object store |
| `tracker` | MLflow / W&B run URI | reuse `experiment-tracking` skill |

The descriptor carries NO backend-conditional field except the resolved `store_uri` — the single
value that varies downstream. Minimal operations: `resolve_uri`, `put`, `get`, `list`, `prune`.
`local-home` is the **reference implementation** that proves the abstraction (no network, no
creds) — exactly as `neo-cloud-abstraction`'s local backend `pricing_query()→0.0` proves its
abstraction. Backend + root are recorded in `project_profile.yaml`
(`run_store_backend` + `run_store_root`). Credentials (S3, tracker) travel **outside** the
descriptor — same secret rule as `neo-cloud-abstraction`.

## Considered Options

### A — Hardcode `$HOME/.<project-name>/`
- Pros: simplest. Cons: no path to remote/tracker storage; forces a fork the moment a project
  needs S3 or MLflow.

### B — Free-form path string in config
- Pros: flexible. Cons: no structure; every consumer must special-case `s3://` vs local vs
  tracker; the abstraction leaks into consumers.

### C — Pluggable backend descriptor mirroring neo-cloud-abstraction (CHOSEN)
- Pros: one schema from owned-disk to S3 to external tracker; reuses a proven, tested shape;
  backend-invariant downstream; `local-home` is the zero-config default and the test seam.
- Cons: a small abstraction surface to maintain.

## Consequences

- **Positive:** consistent with an established Praxion pattern; testable via the local reference
  backend with no creds; `tracker` reuses `experiment-tracking` (MLflow/W&B) rather than
  reinventing run logging.
- **Negative:** marginal over-abstraction for local-only projects — mitigated by `local-home`
  being the default and `s3`/`tracker` being opt-in.
- **Invariance self-test (mirrors neo-cloud AC6):** trace the descriptor through all four
  backends — if any field beyond `store_uri` requires `if backend == s3` logic downstream, the
  abstraction is leaking and the schema is wrong.
