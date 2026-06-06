# neo-cloud-abstraction

Backend abstraction for ML training job dispatch in Praxion. Provides a single
`training_job_descriptor` schema that works unchanged across all three operational modes
(owned GPU, rented GPU box, cloud dispatch). The backend implementation changes; the
descriptor does not. Supports four backends: `local` (subprocess, modes A and B),
`skypilot` (20+ cloud providers, mode C default), `runpod-direct` (native MCP
integration, mode C opt-in), and `nebius-direct` (Nebius CLI lifecycle, mode C opt-in).

## When to Use

- Configuring a compute backend (`neo_cloud_backend.yaml`)
- Dispatching a training run via `/run-experiment`
- Reading or writing a `training_job_descriptor` YAML
- Debugging backend dispatch errors (subprocess, SkyPilot, RunPod, Nebius)
- Choosing between local, SkyPilot, RunPod, or Nebius backends
- Understanding the 8-operation lifecycle protocol (`create`, `status`, `cancel`, etc.)

## Activation

Auto-triggers on: `training_job_descriptor`, `neo_cloud_backend.yaml`, `backend: skypilot`,
`backend: runpod-direct`, `backend: nebius-direct`, `gpu_type`, `gpu_hours_budget`,
`wall_clock_seconds_max`, `sky launch`, `pod_create`, `SkyPilot`, `RunPod`, `Nebius`,
`/run-experiment` dispatch.

## Skill Contents

**SKILL.md sections:**
- `training_job_descriptor` — the invariant contract; full schema; validation rules;
  mode-invariance self-test (AC6)
- Lifecycle Operations — 8-operation protocol table; local/SkyPilot/RunPod mappings;
  `pricing_query() → 0.0` pattern explanation
- Tiered Backend Strategy — local → SkyPilot → RunPod/Nebius direct progression; config file format
- Backend Version Reference — library versions (`skypilot`, `@runpod/mcp-server`, `nebius` CLI)
- Security — credential handling; `env_vars` vs secrets separation
- Performance — `wall_clock_seconds_max` enforcement; remote budget caps
- Related Skills

**References (loaded on demand):**
- `references/local-backend.md` — subprocess semantics; `signal.alarm` enforcement;
  Mode A vs Mode B comparison; `pricing_query() → 0.0` deep dive
- `references/skypilot-backend.md` — SkyPilot `~=0.12`; descriptor translation; Python API;
  spot recovery; provider coverage; when to move to RunPod direct
- `references/runpod-direct-adapter.md` — `@runpod/mcp-server ~1.1`; MCP tool mapping;
  network volumes; Community vs Secure Cloud; v2 adapter pattern
- `references/nebius-direct-adapter.md` — `nebius` CLI lifecycle; provision-VM + SSH;
  GPU platform/preset map; InfiniBand `gpu-cluster`; Object Storage artifact fetch

## Related Skills

- `ml-training` — ML archetype vocabulary, six artifact types, operational modes
- `llm-training-eval` — metric thresholds, TRAINING_RESULTS.md schema, PASS/FAIL/WARN
- `experiment-tracking` — MLflow/W&B run logging; connecting the experiment log to results
