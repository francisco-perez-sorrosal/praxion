# Operational Modes for ML/AI Training

Three modes share one `training_job_descriptor` schema. Mode is a **project-level
configuration** — changing mode requires only updating `neo_cloud_backend.yaml`, not
touching the descriptor or any project code. Back to [SKILL.md](../SKILL.md).

## Contents

- [Mode A — Co-located Owned GPU](#mode-a--co-located-owned-gpu)
- [Mode B — Co-located Rented GPU](#mode-b--co-located-rented-gpu)
- [Mode C — Separated Cloud](#mode-c--separated-cloud-skypilot-or-direct-adapter)
- [When to Transition Between Modes](#when-to-transition-between-modes)
- [Project Config Convention](#project-config-convention)

---

## Mode A — Co-located Owned GPU

**Profile:** Mac M-series, RTX workstation, on-prem server. Praxion and the project
live on the same machine as the GPU.

**Configuration:**

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: local
```

**What Praxion does:**
- `/run-experiment` spawns a subprocess (`subprocess.Popen`) with the entry command
- Metrics stream from stdout/stderr to the configured tracker (MLflow / W&B)
- `wall_clock_seconds_max` is enforced via `signal.alarm` or equivalent
- `pricing_query` returns `0.0` — no cloud cost
- No SSH required; no container image required (image field in descriptor is ignored)

**Prerequisites:** GPU drivers installed locally; training framework (`torch`, `jax`)
installed in the project's virtual environment; `neo_cloud_backend.yaml` exists.

---

## Mode B — Co-located Rented GPU

**Profile:** An H100 (or similar) box rented from Lambda Labs, Vast.ai, or another
provider. You SSH into the box and run Praxion there.

**Configuration:**

```yaml
# .ai-state/neo_cloud_backend.yaml  (on the rented box)
backend: local
```

**Key insight:** Mode B is **identical to Mode A from Praxion's perspective.** Both use
`backend: local`. The local backend uses `subprocess.Popen` semantics and cannot
distinguish owned hardware from rented hardware. Mode B is "free" once Mode A works —
there is nothing additional to implement or configure.

**What is different (user-side, not Praxion-side):**
- SSH into the rented box before invoking Praxion
- Praxion must be installed on the rented box (not the local laptop)
- The project checkout must be on the rented box
- `program.md` lives on the rented box (it is project-local)

**Prerequisites:**
1. SSH access to the rented box (key-based auth recommended)
2. On the rented box: install Claude Code + Praxion plugin
3. On the rented box: `git clone` the project and `cd` into it
4. On the rented box: configure `~/.claude/` as you would locally
5. Set `backend: local` in `.ai-state/neo_cloud_backend.yaml`

**Session workflow:** `ssh user@rented-box`, then invoke Praxion as normal. The only
difference from Mode A is the SSH step at the start of the session.

---

## Mode C — Separated Cloud (SkyPilot or Direct Adapter)

**Profile:** The laptop drives a remote cloud GPU cluster. Neither Praxion nor the
project needs to be installed on the remote machine — the backend handles dispatch.

### Mode C1 — SkyPilot (default-remote, ships with Praxion)

**Configuration:**

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: skypilot
```

**What Praxion does:**
- Translates the `training_job_descriptor` into a SkyPilot YAML task spec
- Invokes `sky launch` to acquire a GPU node from any of SkyPilot's 20+ providers
- Streams metrics via `sky logs --follow`
- Enforces budget via SkyPilot job-level timeout
- `pricing_query` uses `sky show-gpus --gpu <type>`

**Version:** SkyPilot `~=0.12` (PyPI; verified 2026-05-03). Schema changes within
0.12.x are backward-compatible; flag for refresh when 0.13 releases.

**Prerequisites:** SkyPilot installed on the local machine (`pip install "skypilot~=0.12"`);
cloud credentials configured (AWS `~/.aws/credentials`, GCP `~/.config/gcloud/`, etc.).

### Mode C2 — RunPod Direct Adapter (opt-in reference specialization)

**Configuration:**

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: runpod-direct
```

**What Praxion does:**
- Uses the `@runpod/mcp-server` MCP tool set to manage RunPod pods
- Lifecycle operations map to RunPod MCP tools (`pod_create`, `pod_start`, etc.)
- Requires `RUNPOD_API_KEY` environment variable

**Version:** `@runpod/mcp-server ~1.1` (npm; verified 2026-05-03). Vendor-maintained;
verify currency before relying on it in production.

See `skills/neo-cloud-abstraction/references/runpod-direct-adapter.md` for the full
integration recipe.

---

## When to Transition Between Modes

The exploration → commitment lifecycle:

| Stage | Recommended mode | Reasoning |
|---|---|---|
| First experiments (dataset wrangling, architecture search) | A or B | Fastest iteration; no cloud spin-up latency |
| Budget-bounded longer runs (>4 h) | B or C | Rented hardware or cloud is more cost-effective than tying up owned hardware overnight |
| Committed long runs (>24 h, serious scaling) | C (SkyPilot) | SkyPilot manages preemption, spot pricing, and multi-provider availability |
| Provider-specific optimization | C (direct adapter) | When SkyPilot's abstraction overhead matters (e.g., custom networking, volume types) |

**Rule of thumb:** start in Mode A, move to Mode B when you need more VRAM than your
local machine has, move to Mode C when you need multi-GPU or want cloud cost tracking.

---

## Project Config Convention

The backend is declared in `.ai-state/neo_cloud_backend.yaml` at project root (or in
the project config if the project uses a monorepo layout with `.ai-state/` in a
subdirectory):

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: local       # or: skypilot | runpod-direct
# Optional per-backend fields:
# skypilot_cloud: aws  # pin to one provider (default: cheapest available)
# skypilot_region: us-east-1
```

The descriptor (`training_job_descriptor`) does NOT contain a `backend:` or `mode:`
field. Mode is entirely a project-config concern — the same descriptor file runs
unchanged in all three modes.
