---
name: neo-cloud-abstraction
description: >
  ML training job dispatch abstraction for Praxion ML/AI projects: mode-invariant
  training_job_descriptor schema, three backends (local subprocess, SkyPilot 20+
  providers, RunPod direct adapter). Triggers: configuring a compute backend,
  dispatching via /run-experiment, reading/writing training_job_descriptor YAML or
  neo_cloud_backend.yaml, debugging backend dispatch errors, choosing local vs
  SkyPilot vs RunPod, subprocess training, GPU cloud dispatch. Activate alongside
  ml-training and llm-training-eval for full pipeline work.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Backend Version Reference"
  - "Tiered Backend Strategy"
---

# Neo-Cloud Abstraction

Praxion's backend abstraction for ML training job dispatch. One `training_job_descriptor`
schema — unchanged across operational modes A, B, and C. The backend implementation changes;
the descriptor does not.

**Satellite files** (loaded on-demand):

- [references/local-backend.md](references/local-backend.md) -- subprocess semantics; serves modes A and B; pricing_query → 0.0; wall_clock enforcement
- [references/skypilot-backend.md](references/skypilot-backend.md) -- SkyPilot ~=0.12 integration; mode C default; YAML translation; 20+ provider coverage
- [references/runpod-direct-adapter.md](references/runpod-direct-adapter.md) -- @runpod/mcp-server ~1.1; mode C opt-in; integration recipe; Praxion does not ship custom MCP

## training_job_descriptor — the invariant contract

This schema is **identical across modes A, B, and C**. The descriptor has **NO `mode:` field**
and **NO `backend:` field** — the backend is a project-level configuration in
`.ai-state/neo_cloud_backend.yaml`, never a descriptor concern. If any field in a descriptor
requires knowing which mode is active, the abstraction is leaking; revise the schema.

```yaml
# training_job_descriptor — NO mode: field. NO backend: field.
job_id: <string>                          # assigned by backend on create(); uuid or slug
run_tag: <string>                         # human-readable tag (e.g., "run-003-lr3e4")
gpu_type: H100 | A100_80GB | RTX4090 | RTX3090 | M2_Ultra | auto
gpu_count: <int>                          # 1, 2, 4, 8
container_image: <docker-uri>             # used by SkyPilot and RunPod; ignored by local backend
env_vars:
  KEY: VALUE                              # passed to the training process
volume_mounts:
  - host_path: /workspace/data
    container_path: /data
    read_only: true
wall_clock_seconds_max: <int>             # hard wall-clock cap; backend MUST enforce
gpu_hours_budget: <float>                 # cost budget; see deployment/gpu-compute-budgeting
artifact_paths:
  - /workspace/checkpoints               # paths to fetch after run completes
entry_command: "python train.py"         # entrypoint; ignored by local backend (uses Popen directly)
```

**Validation rules:**

- `gpu_hours_budget` is REQUIRED for remote backends (SkyPilot, RunPod direct). The local
  backend accepts `0.0` to signal "owned hardware, no $ cap".
- `container_image` is REQUIRED for SkyPilot and RunPod direct. Local backend ignores it.
- `entry_command` is REQUIRED for SkyPilot and RunPod direct. Local backend uses `Popen`
  with the command from WIP.md step context.
- `job_id` is assigned by `create()`, not set by the caller.

**Mode-invariance self-test (AC6):** trace the descriptor through all three backends.
Does any field require `if mode == C` logic? If yes, the schema is wrong.

## Lifecycle Operations

Eight operations form the invariant protocol. Every backend implements all eight.
The local backend's implementations prove the abstraction's correctness (see note below).

| Operation | Signature | Returns | Local backend | SkyPilot backend | RunPod direct |
|---|---|---|---|---|---|
| `create()` | descriptor → job_id | string | Popen spawn; returns PID as job_id | `sky launch` → cluster/job name | `pod_create` MCP tool |
| `start()` | job_id → void | — | No-op (Popen already running) | `sky start <cluster>` | `pod_start` MCP tool |
| `status()` | job_id → Status | enum | Poll subprocess returncode | `sky status <cluster>` | `pod_status` MCP tool |
| `log_stream()` | job_id → stream | iterator | Read stdout/stderr from Popen | `sky logs <cluster>` | `pod_logs` MCP tool |
| `cancel()` | job_id → void | — | `os.kill(pid, SIGTERM)` | `sky cancel <cluster>` | `pod_stop` MCP tool |
| `artifact_fetch()` | job_id, paths → local | list[Path] | Paths already local; return as-is | `sky rsync-down` | RunPod volume API |
| `list()` | → list[JobSummary] | list | Read from local run registry | `sky status --all` | `pod_list` MCP tool |
| `pricing_query()` | gpu_type, gpu_count → $/hr | float | **Returns 0.0** (no cloud cost) | `sky show-gpus <type>` | RunPod `pricing` MCP tool |

**Status enum:** `pending | running | completed | failed | stopped | budget_exhausted`

**The `pricing_query() → 0.0` pattern (local backend):** Returning `0.0` for local hardware
proves the abstraction is correctly designed. If the abstraction leaked — if the caller had
to handle "not applicable for local mode" as a special case — then the descriptor would need
a `mode:` field, violating AC6. The clean return of `0.0` means `/run-experiment` records
`actual_cost_usd: 0.0` in `TRAINING_RESULTS.md` for local runs without any mode awareness.

## Tiered Backend Strategy

<!-- last-verified: 2026-05-03 -->

Three tiers. Choose based on where the project is in the exploration → commitment lifecycle.

| Tier | Config value | Operational modes | When to use |
|---|---|---|---|
| **Local** (default) | `backend: local` | A, B | Owned GPU; rented GPU box with Praxion installed; prototyping; cost-free runs |
| **SkyPilot** (default-remote) | `backend: skypilot` | C | Exploring cloud providers; multi-cloud; spot recovery; first remote run |
| **RunPod direct** (opt-in) | `backend: runpod-direct` | C | Committed to RunPod; want native MCP integration; avoiding SkyPilot indirection |

Start local. Move to SkyPilot when you need remote resources. Move to RunPod direct only
after validating on SkyPilot and deciding to commit.

**Project config file:**

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: local          # local | skypilot | runpod-direct
```

`/run-experiment` reads this file to determine which backend reference to load.

## Backend Version Reference

<!-- last-verified: 2026-05-03 -->

| Backend | Package | Version | Source | Notes |
|---|---|---|---|---|
| Local | stdlib `subprocess` | Python 3.10+ | stdlib | No install required |
| SkyPilot | `skypilot` (PyPI) | `~=0.12` (0.12.1 verified) | PyPI | Pin `~=0.12`; flag for refresh at 0.13+ |
| RunPod direct | `@runpod/mcp-server` (npm) | `~1.1` (1.1.0 verified) | npm | Vendor-maintained; verify before using |

## Security

- **Never put secrets in the descriptor.** Cloud credentials travel outside the descriptor:
  - SkyPilot: `~/.aws/`, `~/.gcp/`, `~/.azure/` credential files or env vars
  - RunPod: `RUNPOD_API_KEY` environment variable
  - Local: no cloud credentials needed
- The descriptor's `env_vars` block is for training hyperparameters and runtime config,
  not for credentials.

## Performance

- **Local backend MUST enforce `wall_clock_seconds_max`** via `signal.alarm(seconds)` or
  a watchdog thread — the OS will not kill a subprocess automatically at a time limit.
- SkyPilot and RunPod support job-level timeouts natively; pass `wall_clock_seconds_max`
  in the YAML translation or pod config.
- Set `gpu_hours_budget` to a non-zero value for all remote runs. A remote run without a
  budget cap is an open-ended billing commitment.

## Related Skills

| Skill | When to load it |
|---|---|
| `ml-training` | ML archetype vocabulary, operational modes, six artifact types |
| `llm-training-eval` | Metric thresholds, TRAINING_RESULTS.md schema, PASS/FAIL/WARN |
| `deployment` → `references/gpu-compute-budgeting.md` | Budget declaration patterns, cost estimation by backend |
| `experiment-tracking` | MLflow / W&B run logging; mapping run IDs to TRAINING_RESULTS.md |
