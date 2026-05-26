# Local Backend

Integration recipe for the `local` backend of the neo-cloud abstraction.
Back to [SKILL.md](../SKILL.md).

## Contents

- [Configuration](#configuration)
- [Lifecycle Operations — local backend implementation](#lifecycle-operations--local-backend-implementation)
- [wall_clock_seconds_max enforcement](#wall_clock_seconds_max-enforcement)
- [env_vars merging](#env_vars-merging)
- [Mode A vs Mode B — what is different for the user](#mode-a-vs-mode-b--what-is-different-for-the-user)

---

The local backend serves **both Mode A and Mode B**. From Praxion's perspective these modes
are identical — both set `backend: local` in `.ai-state/neo_cloud_backend.yaml` and both
use `subprocess.Popen` to launch training. The local backend cannot distinguish owned hardware
(Mode A) from rented hardware (Mode B), which is the point: Mode B is "free" once Mode A works.

See [skills/ml-training/references/operational-modes.md](../../ml-training/references/operational-modes.md)
for the full Mode A / B / C walkthroughs including SSH setup for Mode B and when to transition
to Mode C.

## Configuration

```yaml
# .ai-state/neo_cloud_backend.yaml
backend: local
```

No additional fields required. No cloud credentials. No container image required
(the `container_image` field in the descriptor is silently ignored).

## Lifecycle Operations — local backend implementation

| Operation | Implementation |
|---|---|
| `create()` | `subprocess.Popen(entry_cmd, stdout=PIPE, stderr=PIPE, env=merged_env)` → returns PID string as `job_id` |
| `start()` | No-op. `Popen` starts the process immediately; `start()` returns without action. |
| `status()` | `poll = proc.poll()`: `None` → `running`; `0` → `completed`; non-zero → `failed` |
| `log_stream()` | Yield lines from `proc.stdout` and `proc.stderr` via a merged reader thread |
| `cancel()` | `os.kill(pid, signal.SIGTERM)`, wait up to 10 s, then `SIGKILL` if still alive |
| `artifact_fetch()` | Paths in `artifact_paths` are already local; verify they exist; return as-is |
| `list()` | Read from a local run registry (e.g., `.ai-state/local_runs.yaml`); return summary list |
| `pricing_query()` | **Returns `0.0`.** No cloud cost for locally-owned or locally-installed hardware. |

### The `pricing_query() → 0.0` canonical pattern

`pricing_query()` returning `0.0` for the local backend is the **canonical proof that the
abstraction is correctly designed** (AC6). Here is why this matters:

- `/run-experiment` calls `pricing_query(gpu_type, gpu_count)` to populate
  `actual_cost_usd` in `TRAINING_RESULTS.md`.
- For a local run, the cost is `$0.00` — owned or rented-box hardware has no per-hour
  cloud charge visible to Praxion.
- The caller never needs to check "is this local mode?" before calling `pricing_query()`.
  It just calls the operation and gets `0.0`.
- If the abstraction were leaking — if `pricing_query()` had to return `None` or raise for
  local runs — then `/run-experiment` would need a `mode:` branch, and the descriptor would
  need a `mode:` field. That would violate AC6.

The `0.0` return is **correct, not a hack**. Owned hardware does incur electricity costs,
but those are out-of-band for Praxion's billing model. Document this explicitly when users ask.

## wall_clock_seconds_max enforcement

The local backend MUST enforce `wall_clock_seconds_max` — the OS will not kill a subprocess
automatically after a time limit.

**Recommended implementation: `signal.alarm`**

```python
import signal
import subprocess

def _timeout_handler(signum, frame):
    raise TimeoutError("wall_clock_seconds_max exceeded")

def create(descriptor):
    proc = subprocess.Popen(
        descriptor["entry_command"].split(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **descriptor.get("env_vars", {})},
    )
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(descriptor["wall_clock_seconds_max"])
    return str(proc.pid)   # job_id
```

When `TimeoutError` is raised, set `status = budget_exhausted` (not `failed`) and terminate
the subprocess with `SIGTERM` → `SIGKILL` if needed.

**Alternative: watchdog thread** — preferred on Windows or when `signal.alarm` is unavailable:

```python
import threading

def _watchdog(proc, timeout_seconds):
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()

threading.Thread(target=_watchdog, args=(proc, descriptor["wall_clock_seconds_max"]),
                 daemon=True).start()
```

## env_vars merging

Merge the descriptor's `env_vars` over the current `os.environ`:

```python
merged_env = {**os.environ, **descriptor.get("env_vars", {})}
```

This ensures the training process inherits PATH, CUDA_VISIBLE_DEVICES, and any project
virtual environment activation that the parent shell has.

## Mode A vs Mode B — what is different for the user

| Aspect | Mode A (owned GPU) | Mode B (rented GPU box) |
|---|---|---|
| Praxion config | `backend: local` | `backend: local` |
| How you get there | Already on the machine | SSH into the rented box first |
| Prerequisites | GPU drivers + framework in venv | SSH + Praxion install on the box + same prerequisites |
| `pricing_query()` | `0.0` | `0.0` (local backend cannot see the rental invoice) |
| `/run-experiment` behavior | Identical | Identical |

Track the rental cost separately (e.g., in a project note or WIP.md step comment).
Praxion does not integrate with rental invoices; that is out of scope for v1.
