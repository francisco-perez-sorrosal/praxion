# Nebius Direct Adapter

Integration recipe for the `nebius-direct` backend of the neo-cloud abstraction.
This is an **opt-in specialization** for mode C users who have committed to Nebius AI Cloud.
Back to [SKILL.md](../SKILL.md).

## Contents

- [Important: Praxion does not ship a custom adapter](#important-praxion-does-not-ship-a-custom-adapter)
- [Configuration](#configuration)
- [Lifecycle Operations — Nebius CLI mapping](#lifecycle-operations--nebius-cli-mapping)
- [GPU type → platform/preset mapping](#gpu-type--platformpreset-mapping)
- [Descriptor → instance create mapping](#descriptor--instance-create-mapping)
- [SSH access and code submission](#ssh-access-and-code-submission)
- [Multi-node InfiniBand clusters](#multi-node-infiniband-clusters)
- [artifact_fetch via Object Storage or scp](#artifact_fetch-via-object-storage-or-scp)
- [Pricing](#pricing)
- [Quota and gotchas](#quota-and-gotchas)
- [Security notes](#security-notes)
- [When to use Nebius direct vs the SkyPilot backend](#when-to-use-nebius-direct-vs-the-skypilot-backend)

---

## Important: Praxion does not ship a custom adapter

**Praxion does NOT author a Nebius MCP server or SDK wrapper.** Nebius already ships and maintains
the `nebius` CLI and the `nebius` Python SDK (PyPI). Praxion's contribution is:

1. This integration recipe — how to configure and use the vendor-maintained CLI
2. The mapping from `training_job_descriptor` lifecycle operations to `nebius` CLI commands
3. The `nebius-direct` backend config value in `neo_cloud_backend.yaml`

This is the same pattern as [runpod-direct-adapter.md](runpod-direct-adapter.md): Praxion ships a
skill reference + integration recipe; the vendor ships the tooling. `nebius-direct` is the first of
the opt-in per-provider direct adapters that specialize the tiered-backend strategy
(local default → SkyPilot default-remote → committed-provider direct adapter).

**CLI over raw SDK (deliberate):** the lifecycle below shells out to the `nebius` CLI, not the raw
`nebius` pysdk. The CLI's compute-instance verbs are documented and stable; the pysdk's compute-create
surface is thinner in published examples. For a pluggable dispatch adapter, the CLI is the
lower-risk path. The pysdk remains available for callers who prefer in-process control.

## Configuration

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: nebius-direct
```

**One-time credential setup** (the same `~/.nebius/` credentials power both this adapter and
`sky check nebius`, so the setup is shared with the SkyPilot path):

**1. Install the Nebius CLI** (macOS/Linux):

```bash
curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash
```

**2. Create a service account** in the Nebius console, then generate its key:

```bash
export SA_ID=$(nebius iam service-account get-by-name \
  --name <service-account-name> --format json | jq -r ".metadata.id")
nebius iam auth-public-key generate \
  --service-account-id "$SA_ID" \
  --output ~/.nebius/credentials.json
echo <tenant-id> > ~/.nebius/NEBIUS_TENANT_ID.txt
```

**3. Bind a CLI profile to the project** (`parent-id`):

```bash
nebius config set parent-id <project-id>
```

**Credential precedence:** the `NEBIUS_IAM_TOKEN` env var (short-lived) takes priority if present;
otherwise the CLI renews tokens from `~/.nebius/credentials.json`. **Never put credentials in the
`training_job_descriptor`** — the descriptor's `env_vars` block is for training config only.

## Lifecycle Operations — Nebius CLI mapping

<!-- last-verified: 2026-06-06 -->

Eight operations, same invariant protocol as every backend. Nebius has no native "run-and-stream"
verb, so dispatch is **provision-VM + SSH**, exactly like the RunPod-pod model.

| Operation | Nebius CLI command(s) | Notes |
|---|---|---|
| `create()` | `nebius compute disk create` (CUDA boot disk) → `nebius compute instance create` (`--resources-platform` + `--resources-preset`) | Returns the instance `metadata.id` as `job_id` |
| `start()` | `nebius compute instance start --id <job_id>` | Starts a stopped instance; no-op if `create()` left it running |
| `status()` | `nebius compute instance get --id <job_id>` | Parse `status.state` → map to the Status enum |
| `log_stream()` | SSH to the instance public IP and tail the run log (`ssh user@<ip> 'tail -f <log>'`) | No native log verb — RunPod-style SSH stream |
| `cancel()` | `nebius compute instance delete --id <job_id>` | **Also deletes the managed disks declared in the instance spec** — billing stops at deletion |
| `artifact_fetch()` | `scp` from the instance IP, or pull from Nebius Object Storage (S3-compatible) | See [artifact_fetch](#artifact_fetch-via-object-storage-or-scp) |
| `list()` | `nebius compute instance list --parent-id <project-id>` | Lists instances in the project; filter by `run_tag` label |
| `pricing_query()` | Static published $/GPU-hr table (no live pricing CLI verb) | See [Pricing](#pricing) |

**Status mapping** (`nebius compute instance get` → Status enum):

| Nebius instance state | Praxion Status |
|---|---|
| `CREATING` / `STARTING` | `pending` |
| `RUNNING` | `running` |
| `STOPPED` / `STOPPING` | `stopped` |
| `DELETING` / `DELETED` | `stopped` (or `completed` if the run finished before teardown) |
| `ERROR` | `failed` |

Run completion is determined by the training process exit (observed over SSH / log markers), not by
the instance state — a `RUNNING` instance with a finished `train.py` is `completed`. Tear down with
`cancel()` once artifacts are fetched, or the instance keeps billing.

## GPU type → platform/preset mapping

<!-- last-verified: 2026-06-06 -->

Nebius expresses GPUs as a `--resources-platform` (the GPU family) plus a `--resources-preset`
(the `NgpuNvcpuNgb` packaging). Map the descriptor's `gpu_type` + `gpu_count`:

| Descriptor `gpu_type` | Nebius `--resources-platform` | Example `--resources-preset` (1× / 8×) |
|---|---|---|
| `H100` | `gpu-h100-sxm` | `1gpu-16vcpu-200gb` / `8gpu-128vcpu-1600gb` |
| `H200` | `gpu-h200-sxm` | `1gpu-16vcpu-200gb` / `8gpu-128vcpu-1600gb` |
| `B200` | `gpu-b200-sxm` | `8gpu-128vcpu-…` (dense node) |
| `L40S` | `gpu-l40s` | `1gpu-8vcpu-32gb` and up |

Verify the exact platform string and current preset catalog with
`nebius compute platform list` / the [compute quickstart](https://docs.nebius.com/compute/quickstart) —
the GPU catalog and preset names change over time. Single-GPU presets and dense 8×GPU HGX nodes are
both available; multi-node clusters use NVIDIA Quantum InfiniBand (see below).

## Descriptor → instance create mapping

```bash
# Pseudocode — /run-experiment create() implementation (shell form)
# 1. CUDA boot disk
BOOT_DISK_ID=$(nebius compute disk create \
  --name "${RUN_TAG}-disk" --size-gibibytes 200 --type network_ssd \
  --source-image-family-image-family ubuntu24.04-cuda13.0 \
  --block-size-bytes 4096 --format json | jq -r ".metadata.id")

# 2. subnet
SUBNET_ID=$(nebius vpc subnet list --format json | jq -r ".items[0].metadata.id")

# 3. instance (gpu_type → platform/preset from the table above)
nebius compute instance create \
  --name "${RUN_TAG}" \
  --resources-platform gpu-h100-sxm \
  --resources-preset 1gpu-16vcpu-200gb \
  --boot-disk-existing-disk-id "$BOOT_DISK_ID" \
  --network-interfaces-subnet-id "$SUBNET_ID" \
  --network-interfaces-public-ip-address "{}" \    # allocate a public IP — REQUIRED for SSH; cannot be added later
  --cloud-init-user-data-file ./cloud-init.yaml    # injects SSH pubkey + entry_command (see SSH section)
# returns metadata.id → job_id
```

`env_vars` from the descriptor are written into the cloud-init `runcmd` (or exported in the SSH
session before `entry_command`). `wall_clock_seconds_max` is enforced by `/run-experiment` polling
`status()` and calling `cancel()` at the cap — Nebius does not auto-terminate a VM at a time limit.
`gpu_hours_budget` is enforced the same way (poll elapsed GPU-hours × `pricing_query()`, cancel at cap).

## SSH access and code submission

<!-- last-verified: 2026-06-06 -->

The `nebius-direct` lifecycle is **provision-VM + SSH** — `log_stream()` (tail) and `artifact_fetch()`
(scp) both need a reachable SSH connection. Three things must be set up at `create()` time:

**1. Request a public IP at create — it cannot be added later.** Pass an empty object to the public-IP
field; a VM created without one is unreachable over SSH and must be torn down and re-provisioned:

```bash
nebius compute instance create ... \
  --network-interfaces-public-ip-address "{}"      # allocate a public IP
```

**2. Inject your SSH public key via cloud-init** (the default user on the Ubuntu CUDA image is `user`):

```yaml
# cloud-init.yaml — passed via --cloud-init-user-data-file
users:
  - name: user
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - ssh-ed25519 AAAA... your-run-key
runcmd:
  - [ bash, -lc, "cd /workspace && <entry_command>" ]   # or submit code over SSH (below)
```

**3. Discover the IP once the instance is `RUNNING`:**

```bash
PUBLIC_IP=$(nebius compute instance get --id "$JOB_ID" --format json \
  | jq -r '.status.network_interfaces[0].public_ip_address.address | split("/")[0]')
```

### Submitting the code/system to the VM

Pick one — in order of hackathon convenience:

| Strategy | How | When |
|---|---|---|
| **git clone in cloud-init** | `runcmd: git clone <repo> && cd repo && <entry_command>` | Code is in a reachable git repo; simplest |
| **rsync/scp upload** | `rsync -az -e ssh ./ user@$PUBLIC_IP:/workspace/`, then SSH-run | Local uncommitted code; large local datasets |
| **container image** | bake code into `container_image`, pull + run on the VM | Reproducible; heavier setup |

`log_stream()` then tails over the same connection (`ssh user@$PUBLIC_IP 'tail -f <log>'`), and
`artifact_fetch()` pulls with `scp` / `rsync` **before** `cancel()`.

### SSH security and host-key handling

- Use a **dedicated, ephemeral keypair per run** (not your personal key): inject the public key at
  create, keep the private key local, drop both at teardown.
- **Verify the host key** — don't blanket-disable checking. For automation, pin a per-run `known_hosts`
  with `ssh -o UserKnownHostsFile=./run-known_hosts -o StrictHostKeyChecking=accept-new` (trust-on-first-use,
  catches later tampering) rather than `StrictHostKeyChecking=no`.
- Restrict inbound SSH (22) to your IP via the VM's security group / firewall where possible — the
  public IP is internet-reachable.
- **Managed surfaces need none of this:** Token Factory (API key) and Managed Kubernetes (`kubectl`)
  involve no SSH. SSH/scp management is specific to this direct-VM dispatch path and the GPU-VM serving recipe.

## Multi-node InfiniBand clusters

For distributed training across multiple 8×GPU nodes, create a GPU cluster first, then attach
instances to it so they share the InfiniBand fabric:

```bash
nebius compute gpu-cluster create \
  --name "${RUN_TAG}-cluster" \
  --infiniband-fabric <fabric-id>
# then create instances with --gpu-cluster-id <cluster-id>
```

InfiniBand is available for **`H100:8` and `H200:8` nodes**; single-GPU and non-8× presets do not
get IB. See [compute gpu-cluster CLI reference](https://docs.nebius.com/cli/reference/compute/gpu-cluster).

## artifact_fetch via Object Storage or scp

Nebius **Object Storage is S3-compatible**. Two artifact paths:

- **Object Storage (preferred, survives teardown):** write checkpoints to a bucket from inside
  `train.py`, then pull with any S3 client. Configure once with `aws configure --profile nebius`
  (Nebius Access Key ID + Secret Access Key) and use `aws --profile nebius s3 cp …` / `boto3`.
- **scp (while the instance is still up):** the instance IP is in the `nebius compute instance get`
  response. Fetch **before** `cancel()` — `instance delete` also deletes the managed disks.

```bash
scp -r user@<instance-ip>:/workspace/checkpoints ./local_checkpoints/
```

## Pricing

<!-- last-verified: 2026-06-06 -->

No live pricing CLI verb — `pricing_query()` returns from a static table of published list prices.
Verify against [nebius.com/prices](https://nebius.com/prices) before quoting; reserved/committed use
discounts up to ~35% are not reflected here.

| GPU | Preemptible $/GPU-hr | On-demand $/GPU-hr |
|---|---|---|
| HGX H100 | $2.15 | $3.85 |
| HGX H200 | $2.45 | $4.50 |
| HGX B200 | $3.95 | $7.15 |
| HGX B300 | $4.30 | $7.85 |
| L40S | from $0.74 | from $1.55 |

`pricing_query(gpu_type, gpu_count)` returns `on_demand_rate × gpu_count` (or the preemptible rate
when the preset is preemptible). `/run-experiment` multiplies by elapsed GPU-hours for
`actual_cost_usd` in `TRAINING_RESULTS.md`.

## Quota and gotchas

- **`ResourcesUnavailableError` on create usually means the Compute quota is exceeded, not a bug.**
  Nebius accounts have per-platform GPU quotas; raise them in the console before a large run.
- **Teardown is your responsibility.** A `RUNNING` instance bills until `cancel()`. `/run-experiment`
  calls `cancel()` on terminal status, but an abandoned run keeps charging — confirm with `list()`.
- **`instance delete` drops managed disks.** Fetch artifacts (or write them to Object Storage) first.
- **Regions:** Nebius operates `eu-north1` (Finland, primary) and US regions. Pin the region via the
  CLI profile / subnet selection; confirm the current region list at
  [docs.nebius.com](https://docs.nebius.com) before quoting it.

## Security notes

- Credentials live in `~/.nebius/credentials.json` + `~/.nebius/NEBIUS_TENANT_ID.txt`, or the
  `NEBIUS_IAM_TOKEN` env var — **never in the descriptor or in git**.
- Use a dedicated **service account** with least-privilege project roles for automation, not a
  personal user identity.
- Object Storage buckets hold training data and checkpoints — set the bucket access policy to match
  your data classification.

## When to use Nebius direct vs the SkyPilot backend

Nebius is **also reachable through the [skypilot-backend.md](skypilot-backend.md)** via
`cloud: nebius` — that is the lower-friction first step (no hand-rolled lifecycle; spot, B200, and
InfiniBand come free through SkyPilot). Choose `nebius-direct` when you have **committed to Nebius**
and want native control over the exact VM/cluster lifecycle without the SkyPilot indirection, or need
a Nebius-specific behavior SkyPilot does not expose. Otherwise, validate on `backend: skypilot` +
`cloud: nebius` first, then commit to `nebius-direct`.
