# RunPod Direct Adapter

Integration recipe for the `runpod-direct` backend of the neo-cloud abstraction.
This is an **opt-in specialization** for mode C users who have committed to RunPod.
Back to [SKILL.md](../SKILL.md).

## Contents

- [Important: Praxion does not ship a custom MCP server](#important-praxion-does-not-ship-a-custom-mcp-server)
- [Configuration](#configuration)
- [Lifecycle Operations — RunPod MCP tool mapping](#lifecycle-operations--runpod-mcp-tool-mapping)
- [Descriptor → RunPod pod_create mapping](#descriptor--runpod-pod_create-mapping)
- [artifact_fetch via Network Volume](#artifact_fetch-via-network-volume)
- [Community Cloud vs Secure Cloud](#community-cloud-vs-secure-cloud)
- [Security notes](#security-notes)
- [v2 Direct Adapters — same pattern](#v2-direct-adapters--same-pattern)

---

## Important: Praxion does not ship a custom MCP server

**Praxion does NOT author a per-provider MCP server for RunPod.** RunPod already ships
and maintains `@runpod/mcp-server` (npm). Praxion's contribution is:

1. This integration recipe — how to configure and use the vendor-maintained MCP
2. The mapping from `training_job_descriptor` lifecycle operations to MCP tool calls
3. The `runpod-direct` backend config value in `neo_cloud_backend.yaml`

This pattern applies to all v2 direct adapters (Lambda, Crusoe, CoreWeave): Praxion
ships a skill reference + integration recipe; the vendor ships the MCP server or adapter.
Praxion never duplicates infrastructure that a vendor already maintains.

## Configuration

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: runpod-direct
```

**Required environment variable:**

```bash
export RUNPOD_API_KEY="your-api-key-here"
```

Never put the API key in the `training_job_descriptor` — use the env var.

**Install the RunPod MCP server** (requires Node.js 18+):

```bash
npm install -g @runpod/mcp-server@~1.1   # verified 1.1.0, 2026-05-03
```

**Register in Claude Code MCP settings** (`.claude/settings.json` or MCP config):

```json
{
  "mcpServers": {
    "runpod": {
      "command": "runpod-mcp-server",
      "env": {
        "RUNPOD_API_KEY": "${RUNPOD_API_KEY}"
      }
    }
  }
}
```

Once registered, Claude Code can call the MCP tools directly in natural language.
`/run-experiment` uses these same MCP tools programmatically.

## Lifecycle Operations — RunPod MCP tool mapping

| Operation | MCP tool | Key parameters | Notes |
|---|---|---|---|
| `create()` | `pod_create` | `gpu_type_id`, `image_name`, `container_disk_in_gb`, `env` | Returns pod object with `id` as `job_id` |
| `start()` | `pod_start` | `pod_id` | Resumes a stopped pod |
| `status()` | `pod_status` | `pod_id` | Returns pod status enum |
| `log_stream()` | `pod_logs` | `pod_id` | Returns recent log lines; poll periodically for streaming |
| `cancel()` | `pod_stop` | `pod_id` | Stops pod; billing stops at pod termination |
| `artifact_fetch()` | RunPod volume API | `volume_id`, `path` | Use network volume or `scp` from pod IP |
| `list()` | `pod_list` | — | Lists all pods for the authenticated account |
| `pricing_query()` | `pricing` | `gpu_type_id`, `gpu_count` | Returns current $/hr for the GPU type |

### GPU type ID mapping

RunPod uses string IDs for GPU types. Common mappings:

| Descriptor `gpu_type` | RunPod `gpu_type_id` |
|---|---|
| `H100` | `NVIDIA H100 80GB HBM3` |
| `A100_80GB` | `NVIDIA A100-SXM4-80GB` |
| `RTX4090` | `NVIDIA GeForce RTX 4090` |
| `RTX3090` | `NVIDIA GeForce RTX 3090` |
| `A40` | `NVIDIA A40` |
| `L40S` | `NVIDIA L40S` |

Verify current IDs with `pod_list` or the RunPod docs — GPU catalog changes over time.

## Descriptor → RunPod pod_create mapping

```python
# Pseudocode — /run-experiment implementation
pod_config = {
    "gpu_type_id": GPU_TYPE_MAP[descriptor["gpu_type"]],
    "gpu_count": descriptor["gpu_count"],
    "image_name": descriptor["container_image"],
    "container_disk_in_gb": 20,           # default; override via env_vars if needed
    "env": [
        {"key": k, "value": v}
        for k, v in descriptor.get("env_vars", {}).items()
    ],
    "volume_mount_path": "/workspace",    # mount network volume here
    "ports": "22/tcp",                    # enable SSH if artifact_fetch via scp
}
pod = mcp.pod_create(**pod_config)
job_id = pod["id"]
```

## artifact_fetch via Network Volume

RunPod's preferred artifact storage uses **Network Volumes** (persistent, survives pod
termination). Configure before the run:

```bash
# Create a network volume (one-time setup via RunPod console or pod_create)
volume_id = "vol-xxxxxxxx"   # from RunPod console
```

In `training.py`, write checkpoints to `/workspace/checkpoints/` (or the `volume_mount_path`).
After `cancel()` or `status = completed`, use the RunPod volume API to download:

```bash
# Alternative: rsync over SSH if the pod is still running
rsync -avz root@<pod_ip>:/workspace/checkpoints ./local_checkpoints/
```

The pod IP is available in the `pod_status` response.

## Community Cloud vs Secure Cloud

RunPod offers two infrastructure tiers:

| Tier | SLA | Price | Recommended for |
|---|---|---|---|
| Community Cloud | Weaker (spot-like behavior; pods may be interrupted) | Lower (~$2.39/hr for H100 on-demand; lower for interruptible) | Experiments; jobs with checkpoint-resume |
| Secure Cloud | Stronger (dedicated; guaranteed reclamation notice) | Higher (~2×) | Production training; long runs without interruption |

Default to Secure Cloud for training runs that take >2 hours or that do not have
checkpoint-resume logic. Community Cloud is appropriate for short experiments.

## Security notes

- `RUNPOD_API_KEY` via env var only; never in the descriptor or in git
- Network volumes contain training data and checkpoints — ensure volume access policy
  matches your data classification requirements
- Community Cloud pods run on third-party hardware; treat outputs as if they could be
  read by the host — encrypt sensitive checkpoints if needed

## v2 Direct Adapters — same pattern

Lambda Labs, Crusoe Cloud, and CoreWeave are the planned v2 direct adapters. When they
ship official MCP servers or Praxion adds skill references for them, the pattern is identical
to this one:

1. A skill reference file at `skills/neo-cloud-abstraction/references/<provider>-adapter.md`
2. A config value in `neo_cloud_backend.yaml`: `backend: lambda-direct`, `backend: crusoe-direct`, etc.
3. The same 8-operation mapping to that provider's tooling
4. Praxion does not author the provider's MCP server

Until v2 adapters land, use the SkyPilot backend for Lambda and Crusoe:
`backend: skypilot` covers both providers out of the box.
